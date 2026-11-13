"""Step 3a (v2): resumable embeddings in priority order from out/full/embed_queue.parquet.
MiniLM-L6-v2, max_seq_length 128 (96% of texts exceed 256 tokens; 128 is ~2.2x faster, mean cos vs 256 = 0.89 on a 400-row check), batch 64, L2-normalised fp16. One checkpoint shard per 25k-row row group:
out/full/emb/shard_XXXXX.npz (sid, emb). Rerun to resume. Progress -> stdout (logs/embed.log)."""
import os, glob, time, numpy as np, pyarrow.parquet as pq, torch
torch.set_num_threads(int(os.environ.get('EMB_THREADS','8')))
from sentence_transformers import SentenceTransformer
os.makedirs('out/full/emb',exist_ok=True)
pf=pq.ParquetFile('out/full/embed_queue.parquet'); G=pf.metadata.num_row_groups
m=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device='cpu'); m.max_seq_length=int(os.environ.get('EMB_MAXLEN','128'))
t0=time.time(); done=0; total=pf.metadata.num_rows
print(time.strftime('%H:%M:%S'),'start; row groups',G,'rows',total,flush=True)
for g in range(G):
    out=f'out/full/emb/shard_{g:05d}.npz'
    if os.path.exists(out): done+=pf.metadata.row_group(g).num_rows; continue
    d=pf.read_row_group(g).to_pandas(); t=time.time()
    E=m.encode(d.text.tolist(),batch_size=64,normalize_embeddings=True,show_progress_bar=False).astype(np.float16)
    np.savez(out+'.tmp.npz',sid=d.sid.values.astype(np.int32),emb=E); os.rename(out+'.tmp.npz',out)
    done+=len(d); rate=len(d)/(time.time()-t)
    print(time.strftime('%H:%M:%S'),f'shard {g}/{G} tier {int(d.tier.iloc[0])}-{int(d.tier.iloc[-1])} rows {len(d)} {rate:.0f}/s cum {done}/{total} ETA {(total-done)/rate/3600:.2f} h',flush=True)
print('DONE',flush=True)
