"""Near-duplicate prototype on a subset of distinct skills (dedup_primary=1).
Two signals: MinHash-LSH Jaccard on word 5-shingles of the full text, and MiniLM cosine on name+description+first 1500 chars of body.
Clusters = connected components. Outputs out/neardup_*.json/csv."""
import sqlite3, re, json, time, sys
import numpy as np, pandas as pd
from datasketch import MinHash, MinHashLSH
N=int(sys.argv[1]) if len(sys.argv)>1 else 5000
t0=time.time()
c=sqlite3.connect('data/agent_skills_sample.db')
df=pd.read_sql(f"""select a.file_sha,a.repo_full_name,a.path,a.name,a.description,a.content,
  (select count(*) from artifacts b where b.file_sha=a.file_sha) copies, r.stars
  from artifacts a left join repos r on r.full_name=a.repo_full_name
  where a.dedup_primary=1 and length(a.content)>200 order by a.file_sha limit {N}""",c)
df=df.reset_index(drop=True); n=len(df); print('subset',n)
def norm(t): return re.sub(r'\s+',' ',t.lower())
# MinHash
toks=[re.findall(r'\w+',norm(t)) for t in df.content]
lsh=MinHashLSH(threshold=0.7,num_perm=128); mh=[]
for i,tk in enumerate(toks):
    m=MinHash(num_perm=128); sh={' '.join(tk[j:j+5]) for j in range(max(1,len(tk)-4))}
    m.update_batch([s.encode() for s in sh]); mh.append(m); lsh.insert(str(i),m)
mpairs=set()
for i,m in enumerate(mh):
    for j in lsh.query(m):
        j=int(j)
        if j>i and m.jaccard(mh[j])>=0.7: mpairs.add((i,j))
print('minhash pairs',len(mpairs),round(time.time()-t0),'s')
# Embeddings
from sentence_transformers import SentenceTransformer
model=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device='cpu')
txt=[f"{a or ''}. {b or ''}\n{(c or '')[:1500]}" for a,b,c in zip(df.name,df.description,df.content)]
E=model.encode(txt,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
np.save('out/emb_subset.npy',E); print('embedded',round(time.time()-t0),'s')
S=E@E.T; np.fill_diagonal(S,0)
res={'subset':n,'minhash_pairs_j>=0.7':len(mpairs)}
def comps(pairs):
    p=list(range(n))
    def f(x):
        while p[x]!=x: p[x]=p[p[x]]; x=p[x]
        return x
    for i,j in pairs: p[f(i)]=f(j)
    g={}
    for i in range(n): g.setdefault(f(i),[]).append(i)
    return [v for v in g.values() if len(v)>1]
for th in (0.90,0.95,0.98):
    ii,jj=np.where(np.triu(S>=th,1)); pr=list(zip(ii,jj)); cl=comps(pr)
    res[f'emb_cos>={th}']={'pairs':len(pr),'clusters':len(cl),'skills_in_clusters':sum(map(len,cl)),'largest':max(map(len,cl)) if cl else 0}
mcl=comps(mpairs); res['minhash_clusters']={'clusters':len(mcl),'skills_in_clusters':sum(map(len,mcl)),'largest':max(map(len,mcl)) if mcl else 0}
# combined: emb>=0.95 OR minhash>=0.7
ii,jj=np.where(np.triu(S>=0.95,1)); comb=set(zip(ii.tolist(),jj.tolist()))|mpairs; ccl=comps(comb)
res['combined(emb>=0.95 | jac>=0.7)']={'pairs':len(comb),'clusters':len(ccl),'skills_in_clusters':sum(map(len,ccl)),'largest':max(map(len,ccl)),
  'file_occurrences_covered':int(df.copies.iloc[[i for c_ in ccl for i in c_]].sum())}
# distinct repos per cluster & examples
ex=[]
for cl in sorted(ccl,key=len,reverse=True):
    sub=df.iloc[cl]; ex.append({'size':len(cl),'distinct_repos':int(sub.repo_full_name.nunique()),
      'members':[{'name':r.name,'repo':r.repo_full_name,'path':r.path,'stars':r.stars,'exact_copies':int(r.copies),'chars':len(r.content)} for r in sub.itertuples()][:8]})
res['cluster_size_hist']=pd.Series([len(x) for x in ccl]).value_counts().sort_index().to_dict()
res['clusters_spanning_2plus_repos']=sum(1 for e in ex if e['distinct_repos']>1)
res['elapsed_s']=round(time.time()-t0)
json.dump({'summary':res,'clusters':ex},open('out/neardup_clusters.json','w'),indent=1,default=str)
print(json.dumps(res,indent=1,default=str))
for e in ex[:12]: print(e['size'],e['distinct_repos'],[(m['name'],m['repo'],m['chars']) for m in e['members'][:4]])
