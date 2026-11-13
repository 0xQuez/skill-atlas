"""Step 3c: candidate pairs + clusters.
MinHash LSH: 16 bands x 4 rows over 64-perm signatures; verify est. Jaccard >= 0.7. Buckets > 200 members are linked
star+chain (each member vs bucket head and vs previous member) instead of all-pairs.
Embeddings (whatever shards exist in out/full/emb): FAISS IVF (nlist 4096, nprobe 16) inner-product kNN k=10, keep cos >= 0.95.
Clusters = connected components of (jac>=0.7 OR cos>=0.95). Writes out/full/{pairs,clusters,skills,embeddings}.parquet + headline.json"""
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq, glob, time, json, os, sys
t0=time.time(); log=lambda *a: print(round(time.time()-t0),'s',*a,flush=True)
JT=0.7; CT=0.95; BANDS=16; R=4; BIG=200
z=np.load('out/full/minhash_sig.npz'); sid=z['sid']; S=z['sig']; n=len(sid); log('sigs',S.shape)
pos=np.full(sid.max()+1,-1,np.int64); pos[sid]=np.arange(n)
I=[];J=[]
for b in range(BANDS):
    blk=S[:,b*R:(b+1)*R].astype(np.uint64)
    key=blk[:,0]
    with np.errstate(over='ignore'):
        for j in range(1,R): key=key*np.uint64(0x100000001B3)^blk[:,j]
    empty=(S[:,0]==0xFFFFFFFF); key[empty]=np.uint64(np.arange(empty.sum()))  # never bucket empty docs
    o=np.argsort(key,kind='stable'); ks=key[o]
    starts=np.flatnonzero(np.r_[True,ks[1:]!=ks[:-1]]); ends=np.r_[starts[1:],n]; sz=ends-starts
    # buckets of size 2..BIG: all pairs; >BIG: star+chain
    for s,e in zip(starts[sz>1],ends[sz>1]):
        m=o[s:e]
        if len(m)<=BIG:
            a,c=np.triu_indices(len(m),1); I.append(m[a]); J.append(m[c])
        else:
            I.append(np.r_[np.repeat(m[0],len(m)-1),m[1:-1]]); J.append(np.r_[m[1:],m[2:]])
    log('band',b,'buckets>1',int((sz>1).sum()),'max',int(sz.max()))
I=np.concatenate(I); J=np.concatenate(J); lo=np.minimum(I,J); hi=np.maximum(I,J)
pk=np.unique(lo.astype(np.int64)*n+hi); lo=pk//n; hi=pk%n; log('lsh candidates',len(pk))
jac=np.empty(len(lo),np.float32)
for k in range(0,len(lo),2_000_000):
    jac[k:k+2_000_000]=(S[lo[k:k+2_000_000]]==S[hi[k:k+2_000_000]]).mean(1)
keep=jac>=JT; mp=pd.DataFrame({'a':lo[keep],'b':hi[keep],'jaccard':jac[keep]}); log('minhash pairs',len(mp))
del S
# embeddings
shards=sorted(glob.glob('out/full/emb/shard_?????.npz')); ep=pd.DataFrame(columns=['a','b','cosine'])
if shards:
    import faiss
    faiss.omp_set_num_threads(int(os.environ.get('FAISS_THREADS','8')))
    d=384; esid=np.concatenate([np.load(f)['sid'] for f in shards]); nemb=len(esid); log('embeddings to index',nemb)
    nl=min(4096,max(16,nemb//200))
    idx=faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(d),d,nl,faiss.ScalarQuantizer.QT_fp16,faiss.METRIC_INNER_PRODUCT)
    # train on a sample drawn across shards
    tr=np.concatenate([np.load(f)['emb'][::max(1,nemb//200000)] for f in shards]).astype(np.float32); idx.train(tr); del tr
    w=pq.ParquetWriter('out/full/embeddings.parquet',pa.schema([('sid',pa.int32()),('emb',pa.list_(pa.float16(),d))]))
    for f in shards:
        z_=np.load(f); idx.add(z_['emb'].astype(np.float32))
        w.write_table(pa.table({'sid':z_['sid'],'emb':pa.FixedSizeListArray.from_arrays(pa.array(z_['emb'].ravel()),d)}))
    w.close(); idx.nprobe=16; log('index built, nlist',nl)
    A_=[];B_=[];C_=[]; off=0
    for f in shards:
        Q=np.load(f)['emb'].astype(np.float32); D,Ix=idx.search(Q,10)
        rows=np.repeat(np.arange(off,off+len(Q)),10); D=D.ravel(); Ix=Ix.ravel(); m=(D>=CT)&(Ix>=0)&(Ix!=rows)
        A_.append(rows[m]); B_.append(Ix[m]); C_.append(D[m]); off+=len(Q)
    del idx
    ea=pos[esid[np.concatenate(A_)]]; eb=pos[esid[np.concatenate(B_)]]; ec=np.concatenate(C_).astype(np.float32)
    ep=pd.DataFrame({'a':np.minimum(ea,eb),'b':np.maximum(ea,eb),'cosine':ec}); ep=ep[(ep.a>=0)&(ep.b>=0)&(ep.a!=ep.b)]
    ep=ep.groupby(['a','b'],as_index=False).cosine.max()
    np.save('out/full/_emb_sids.npy',esid); log('emb pairs',len(ep))
else: nemb=0
pairs=mp.merge(ep,on=['a','b'],how='outer')
pairs['a_sid']=sid[pairs.a.values]; pairs['b_sid']=sid[pairs.b.values]
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
pq.write_table(pa.Table.from_pandas(pairs[['a_sid','b_sid','jaccard','cosine']].rename(columns={'a_sid':'sid_a','b_sid':'sid_b'}),preserve_index=False),'out/full/pairs.parquet')
cm=meta[meta.cluster_id>=0]
cl=cm.groupby('cluster_id').agg(size=('sid','size'),n_files=('n_files','sum'),n_repos_rep=('rep_repo','nunique'),n_owners_rep=('rep_owner','nunique'),
    top_name=('name',lambda s: s.dropna().value_counts().index[0] if s.notna().any() else None),max_stars=('max_stars','max')).reset_index()
pq.write_table(pa.Table.from_pandas(cl,preserve_index=False),'out/full/clusters.parquet')
pq.write_table(pa.Table.from_pandas(meta.drop(columns=['root']),preserve_index=False),'out/full/skills.parquet')
# headline
art_rows=int(meta.n_files.sum()) # non-junk occurrences
H={'non_junk_distinct':n,'non_junk_file_rows':art_rows,'embedded':nemb,'emb_only_pairs':int(pairs.jaccard.isna().sum()),'lsh_candidates':int(len(pk)),'minhash_pairs':int(len(mp)),'emb_pairs':int(len(ep)),
 'pairs_total':int(len(pairs)),'clusters':int(len(cl)),'skills_in_clusters':int(cl['size'].sum()),
 'near_copy_rate_distinct_pct':round(100*cl['size'].sum()/n,2),
 'redundant_distinct_beyond_exact':int(cl['size'].sum()-len(cl)),
 'file_rows_in_clusters':int(cl.n_files.sum()),
 'cluster_size_hist':{str(k):int(v) for k,v in pd.cut(cl['size'],[1,2,3,5,10,50,100,1000,10**7],labels=['2','3','4-5','6-10','11-50','51-100','101-1000','1000+']).value_counts().sort_index().items()},
 'largest_cluster':int(cl['size'].max()),'clusters_cross_repo':int((cl.n_repos_rep>1).sum()),'clusters_cross_owner':int((cl.n_owners_rep>1).sum())}
json.dump(H,open('out/full/headline_clusters.json','w'),indent=1); print(json.dumps(H,indent=1)); log('done')
