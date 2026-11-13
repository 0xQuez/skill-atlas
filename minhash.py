"""Step 3b: MinHash signatures for all non-junk distinct skills.
Tokens = lowercase \\w+ words (first 10,000), shingles = word 5-grams, 64 hash functions (multiply-shift, 32-bit).
Output out/full/minhash_sig.npz (sid int32, sig uint32[n,64]). Parallel over text parts."""
import os, glob, re, zlib, time, numpy as np, pyarrow.parquet as pq
from multiprocessing import Pool
K=64; MAXTOK=10000; rng=np.random.default_rng(1)
A=(rng.integers(1,2**63,K,dtype=np.uint64)|np.uint64(1)); B=rng.integers(0,2**63,K,dtype=np.uint64)
WR=re.compile(r'\w+'); M=np.uint64(0x9E3779B97F4A7C15)
def sig(text):
    w=WR.findall(text.lower())[:MAXTOK]
    if not w: return np.full(K,0xFFFFFFFF,np.uint32)
    h=np.fromiter((zlib.crc32(x.encode()) for x in w),np.uint64,len(w))
    if len(h)>=5:
        s=h[:-4].copy()
        for j in range(1,5): s=s*M+h[j:len(h)-4+j]
    else: s=np.array([h.sum()*M],np.uint64)
    s=np.unique(s)
    with np.errstate(over='ignore'):
        v=((A[:,None]*s[None,:]+B[:,None])>>np.uint64(32)).astype(np.uint32)
    return v.min(1)
def work(f):
    t=pq.read_table(f,columns=['sid','content']).to_pandas()
    S=np.stack([sig(c or '') for c in t.content]) if len(t) else np.zeros((0,K),np.uint32)
    return t.sid.values.astype(np.int32),S
if __name__=='__main__':
    t0=time.time(); parts=sorted(glob.glob('out/full/text/part-*.parquet'))
    with Pool(int(os.environ.get('MH_PROCS','3'))) as p:
        R=[]
        for i,r in enumerate(p.imap(work,parts)): R.append(r); print(i,len(r[0]),round(time.time()-t0),'s',flush=True)
    sid=np.concatenate([r[0] for r in R]); S=np.concatenate([r[1] for r in R]); o=np.argsort(sid)
    np.savez('out/full/minhash_sig.npz',sid=sid[o],sig=S[o]); print('DONE',len(sid),round(time.time()-t0),'s')
