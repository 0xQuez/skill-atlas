"""Step 1b: stream representative contents (non-junk) from HF parquet into out/full/text/part-XXXXX.parquet (sid, name, description, content).
Streams file by file with pyarrow (DuckDB 2.0 parallel COPY of large text stalled on this box)."""
import pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc, duckdb, glob, os, time
t=time.time(); os.makedirs('out/full/text',exist_ok=True)
keep=pq.read_table('out/full/skills_meta_raw.parquet',columns=['file_sha','sid','junk'])
keep=keep.filter(pc.is_null(keep['junk']))
shas=keep.column('file_sha'); sids=keep.column('sid')
total=0
for i,f in enumerate(sorted(glob.glob('hf/data/artifacts/*.parquet'))):
    out=f'out/full/text/part-{i:05d}.parquet'
    if os.path.exists(out): continue
    pf=pq.ParquetFile(f); w=None
    for rb in pf.iter_batches(batch_size=20000,columns=['file_sha','dedup_primary','name','description','content']):
        tb=pa.Table.from_batches([rb]); tb=tb.filter(pc.equal(tb['dedup_primary'],1))
        idx=pc.index_in(tb['file_sha'],value_set=shas)
        m=pc.is_valid(idx); tb=tb.filter(m); idx=idx.filter(m)
        tb=pa.table({'sid':pc.take(sids,idx),'name':tb['name'],'description':tb['description'],'content':tb['content']})
        if w is None: w=pq.ParquetWriter(out+'.tmp',tb.schema,compression='zstd')
        w.write_table(tb,row_group_size=10000); total+=tb.num_rows
    if w: w.close(); os.rename(out+'.tmp',out)
    print(i,total,round(time.time()-t),'s',flush=True)
print('DONE rows',total)
