"""Refine embedding-only pairs (cosine>=0.95 on name+description+start, no MinHash pair).
Inputs: out/full/pairs_raw.parquet (raw combined pairs), minhash_sig.npz, body_emb.npz + body_lang.parquet (embed_body.py),
        skills_combined_raw.parquet (names, owners, slop flags of the raw combined run).
An embedding-only pair is KEPT as a near-copy iff
   NOT template_sibling  AND  (est. Jaccard >= 0.3  OR  body cosine >= 0.95)
 template_sibling = names differ but are equal once digits are removed (cic-can-1287 / cic-can-1288, spatial-expert-229/230),
                    OR both sides are slop_skill, OR both unnamed and from the same owner (NeuralBlitz / GenesisRUST variants)
A pair whose bodies are in different detected languages (script or stopword vote; 'unk' never counts) is a TRANSLATION:
 kind='translation', excluded from clustering, surfaced as reason translated_copy_of:<sid> (informational).
Output out/full/pairs.parquet with columns sid_a, sid_b, jaccard, cosine, jaccard_est, body_cosine, kind in
 {minhash, minhash+embedding, embedding, translation, embedding_rejected}; clustering uses minhash* and embedding only."""
import numpy as np, pandas as pd, pyarrow.parquet as pq, re, json, time
t0=time.time()
P=pq.read_table('out/full/pairs_raw.parquet').to_pandas()
z=np.load('out/full/minhash_sig.npz'); sid=z['sid']; S=z['sig']; pos=np.full(sid.max()+1,-1,np.int64); pos[sid]=np.arange(len(sid))
eo=P.jaccard.isna(); E=P[eo].copy()
E['jaccard_est']=(S[pos[E.sid_a.values]]==S[pos[E.sid_b.values]]).mean(1).astype(np.float32); del S
b=np.load('out/full/body_emb.npz'); bpos=np.full(sid.max()+1,-1,np.int64); bpos[b['sid']]=np.arange(len(b['sid'])); BE=b['emb']
ia,ib=bpos[E.sid_a.values],bpos[E.sid_b.values]; ok=(ia>=0)&(ib>=0); bc=np.full(len(E),np.nan,np.float32)
for k in range(0,len(E),200000):
    sl=slice(k,k+200000); m=ok[sl]; x=np.where(m)[0]+k
    bc[x]=(BE[ia[x]].astype(np.float32)*BE[ib[x]].astype(np.float32)).sum(1)
E['body_cosine']=bc
L=pd.read_parquet('out/full/body_lang.parquet').set_index('sid').lang
M=pq.read_table('out/full/skills_combined_raw.parquet',columns=['sid','name','rep_owner','slop_skill']).to_pandas().set_index('sid')
na,nb=M.name.reindex(E.sid_a).values,M.name.reindex(E.sid_b).values
nk=lambda s: re.sub(r'[\s_\-.]+','-',s.lower().strip()).strip('-') if isinstance(s,str) else None
ka=np.array([nk(x) for x in na],object); kb=np.array([nk(x) for x in nb],object)
dd=lambda s: re.sub(r'\d+','#',s) if s else s
sib_name=np.array([(x is not None and y is not None and x!=y and dd(x)==dd(y)) for x,y in zip(ka,kb)])
sa,sb=M.slop_skill.reindex(E.sid_a).fillna(False).values.astype(bool),M.slop_skill.reindex(E.sid_b).fillna(False).values.astype(bool)
oa,ob=M.rep_owner.reindex(E.sid_a).values,M.rep_owner.reindex(E.sid_b).values
unnamed_same=np.array([(x is None and y is None and p==q) for x,y,p,q in zip(ka,kb,oa,ob)])
E['template_sibling']=sib_name|(sa&sb)|unnamed_same
la,lb=L.reindex(E.sid_a).fillna('unk').values,L.reindex(E.sid_b).fillna('unk').values
trans=(la!=lb)&(la!='unk')&(lb!='unk')
keep=(~E.template_sibling.values)&((E.jaccard_est.values>=0.3)|(E.body_cosine.values>=0.95))
E['kind']=np.where(trans,'translation',np.where(keep,'embedding','embedding_rejected'))
E['lang_a'],E['lang_b']=la,lb
R=P[~eo].copy(); R['jaccard_est']=R.jaccard; R['body_cosine']=np.nan; R['kind']=np.where(R.cosine.notna(),'minhash+embedding','minhash')
out=pd.concat([R,E.drop(columns=['template_sibling','lang_a','lang_b'])],ignore_index=True)
out.to_parquet('out/full/pairs.parquet',index=False)
E.to_parquet('out/full/_emb_only_refined.parquet',index=False)
st={'emb_only_raw':int(len(E)),'kind_counts':out.kind.value_counts().to_dict(),
    'rejected_template_sibling':int((E.template_sibling&~trans).sum()),'rejected_low_overlap':int(((~E.template_sibling)&~trans&~keep).sum()),
    'kept_by_jaccard_only':int(((E.kind=='embedding')&(E.jaccard_est>=0.3)&~(E.body_cosine>=0.95)).sum()),
    'kept_by_body_cosine_only':int(((E.kind=='embedding')&(E.jaccard_est<0.3)).sum()),
    'translation_lang_pairs':E[E.kind=='translation'].apply(lambda r:'-'.join(sorted([r.lang_a,r.lang_b])),axis=1).value_counts().head(8).to_dict(),
    'elapsed_s':round(time.time()-t0)}
json.dump(st,open('out/full/refine_pairs_stats.json','w'),indent=1,default=int); print(json.dumps(st,indent=1,default=int))
