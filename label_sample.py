"""Print a compact view of N sampled embedding-only pairs for hand-labelling. usage: label_sample.py <pairs.parquet> <seed> <N> <out.csv>"""
import sys, re, duckdb, pandas as pd
src,seed,N,out=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
p=pd.read_parquet(src).sample(N,random_state=seed).reset_index(drop=True)
ids=",".join(map(str,set(p.sid_a)|set(p.sid_b)))
c=duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2; SET preserve_insertion_order=false")
t=c.execute(f"select sid,name,content from 'out/full/text/*.parquet' where sid in ({ids})").df().set_index('sid')
m=c.execute(f"select sid, coalesce(top_repo,rep_repo) repo from 'out/full/verdicts.parquet' where sid in ({ids})").df().set_index('sid').repo
FM=re.compile(r'^\ufeff?\s*---\s*\n.*?\n---\s*(\n|$)',re.S)
def body(x): m_=FM.match(x or ''); return re.sub(r'\s+',' ',(x[m_.end():] if m_ else x))
for i,r in p.iterrows():
    a,b=t.loc[r.sid_a],t.loc[r.sid_b]; ba,bb=body(a.content),body(b.content)
    print(f"#{i} cos={r.cosine:.3f} j={r.get('jest',float('nan')):.2f} len={len(ba)}/{len(bb)} | {a['name']} [{m[r.sid_a]}] || {b['name']} [{m[r.sid_b]}]")
    print("  A:",ba[:230]); print("  B:",bb[:230])
p.to_csv(out,index=False)
