"""Recluster from refined pairs (out/full/pairs.parquet with `kind`, written by refine_pairs.py) without recomputing LSH/ANN.
Clusters = connected components over kind in {minhash, minhash+embedding, embedding}; translation / embedding_rejected are kept in
pairs.parquet but not linked. Writes skills.parquet, clusters.parquet, headline_clusters.json."""
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq, json, time, os
t0=time.time(); log=lambda *a: print(round(time.time()-t0),'s',*a,flush=True)
sid=np.load('out/full/minhash_sig.npz')['sid']; n=len(sid)
pos=np.full(sid.max()+1,-1,np.int64); pos[sid]=np.arange(n)
allp=pq.read_table('out/full/pairs.parquet').to_pandas()
link=allp[allp.kind.isin(['minhash','minhash+embedding','embedding'])]
pairs=pd.DataFrame({'a':pos[link.sid_a.values],'b':pos[link.sid_b.values],'jaccard':link.jaccard.values,'cosine':link.cosine.values})
nemb=int(len(np.load('out/full/_emb_sids.npy'))); pk=range(json.load(open('out/full/headline_clusters.json')).get('lsh_candidates',0))
mp=link[link.kind!='embedding']; ep=link[link.cosine.notna()]
# union-find
par=np.arange(n)
def find(x):
    r=x
    while par[r]!=r: r=par[r]
    while par[x]!=r: par[x],x=r,par[x]
    return r
for a,b in zip(pairs.a.values,pairs.b.values):
    ra,rb=find(a),find(b)
    if ra!=rb: par[max(ra,rb)]=min(ra,rb)
root=np.array([find(x) for x in range(n)])
meta=pq.read_table('out/full/skills_meta_raw.parquet').to_pandas().set_index('sid')
meta=meta.loc[sid].reset_index(); meta['root']=root
cs=meta.groupby('root').sid.transform('size'); meta['cluster_size']=cs.values
meta['cluster_id']=np.where(meta.cluster_size>1,sid[meta.root.values],-1)
meta['embedded']=False
if nemb: meta.loc[meta.sid.isin(set(np.load('out/full/_emb_sids.npy').tolist())),'embedded']=True
cm=meta[meta.cluster_id>=0]
cl=cm.groupby('cluster_id').agg(size=('sid','size'),n_files=('n_files','sum'),n_repos_rep=('rep_repo','nunique'),n_owners_rep=('rep_owner','nunique'),
    top_name=('name',lambda s: s.dropna().value_counts().index[0] if s.notna().any() else None),max_stars=('max_stars','max')).reset_index()
pq.write_table(pa.Table.from_pandas(cl,preserve_index=False),'out/full/clusters.parquet')
pq.write_table(pa.Table.from_pandas(meta.drop(columns=['root']),preserve_index=False),'out/full/skills.parquet')
# headline
art_rows=int(meta.n_files.sum()) # non-junk occurrences
H={'non_junk_distinct':n,'non_junk_file_rows':art_rows,'embedded':nemb,'emb_only_pairs':int((link.kind=='embedding').sum()),'emb_only_rejected':int((allp.kind=='embedding_rejected').sum()),'translation_pairs':int((allp.kind=='translation').sum()),'lsh_candidates':int(len(pk)),'minhash_pairs':int(len(mp)),'emb_pairs':int(len(ep)),
 'pairs_total':int(len(pairs)),'clusters':int(len(cl)),'skills_in_clusters':int(cl['size'].sum()),
 'near_copy_rate_distinct_pct':round(100*cl['size'].sum()/n,2),
 'redundant_distinct_beyond_exact':int(cl['size'].sum()-len(cl)),
 'file_rows_in_clusters':int(cl.n_files.sum()),
 'cluster_size_hist':{str(k):int(v) for k,v in pd.cut(cl['size'],[1,2,3,5,10,50,100,1000,10**7],labels=['2','3','4-5','6-10','11-50','51-100','101-1000','1000+']).value_counts().sort_index().items()},
 'largest_cluster':int(cl['size'].max()),'clusters_cross_repo':int((cl.n_repos_rep>1).sum()),'clusters_cross_owner':int((cl.n_owners_rep>1).sum())}
json.dump(H,open('out/full/headline_clusters.json','w'),indent=1); print(json.dumps(H,indent=1)); log('done')
