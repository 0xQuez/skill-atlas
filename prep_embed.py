"""Build out/full/embed_queue.parquet: (rank, sid, tier, text) in embedding priority order, text = name. description\\n content[:1500].
Tier 1 = MinHash cluster representatives (sid == cluster_id) + skills whose content is in any repo with >=100 stars.
Tier 2 = remaining skills in any repo with >=1 star. Tier 3 = everything else. Random order within a tier (seed 42)."""
import pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc, numpy as np, glob, time
t=time.time()
m=pq.read_table('out/full/skills.parquet',columns=['sid','cluster_id','max_stars']).to_pandas()
tier=np.where((m.cluster_id==m.sid)|(m.max_stars>=100),1,np.where(m.max_stars>=1,2,3))
rng=np.random.default_rng(42); key=tier*10_000_000+rng.permutation(len(m))
order=np.argsort(key,kind='stable'); rank=np.empty(len(m),np.int64); rank[order]=np.arange(len(m))
rk=dict(zip(m.sid.values,rank)); tr=dict(zip(m.sid.values,tier))
parts=[]
for f in sorted(glob.glob('out/full/text/part-*.parquet')):
    d=pq.read_table(f).to_pandas()
    txt=[f"{a or ''}. {b or ''}\n{(c or '')[:1500]}" for a,b,c in zip(d.name,d.description,d.content)]
    parts.append(pa.table({'rank':d.sid.map(rk).values,'sid':d.sid.values.astype(np.int32),'tier':d.sid.map(tr).values.astype(np.int8),'text':pa.array(txt,pa.large_string())}))
T=pa.concat_tables(parts); T=T.take(pc.sort_indices(T,[('rank','ascending')]))
pq.write_table(T,'out/full/embed_queue.parquet',row_group_size=25000,compression='zstd')
print('rows',T.num_rows,'tiers',dict(zip(*np.unique(T['tier'].to_numpy(),return_counts=True))),round(time.time()-t),'s')
