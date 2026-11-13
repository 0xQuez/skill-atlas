"""Inspect largest clusters + estimate MinHash pair precision against exact 5-shingle Jaccard on a random sample."""
import duckdb, re, numpy as np, pandas as pd, json, sys
c=duckdb.connect(); c.execute("SET memory_limit='3GB'; SET threads=4")
q=lambda s: c.execute(s).df()
top=q("select * from 'out/full/clusters.parquet' order by size desc limit 12"); print(top.to_string())
for cid in top.cluster_id[:6]:
    d=q(f"""select name, count(*) n from 'out/full/skills.parquet' where cluster_id={cid} group by 1 order by 2 desc limit 6""")
    r=q(f"""select rep_repo, count(*) n, max(max_stars) stars from 'out/full/skills.parquet' where cluster_id={cid} group by 1 order by 2 desc limit 5""")
    print('\nCLUSTER',cid,'names:',list(zip(d.name,d.n)),'\n repos:',list(zip(r.rep_repo,r.n,r.stars)))
# precision sample
p=q("select sid_a,sid_b,jaccard from 'out/full/pairs.parquet' where jaccard is not null using sample 300 rows (reservoir, 7)")
ids=",".join(map(str,set(p.sid_a)|set(p.sid_b)))
t=q(f"select sid, content from 'out/full/text/*.parquet' where sid in ({ids})").set_index('sid').content
sh=lambda x:{' '.join(w[i:i+5]) for w in [re.findall(r'\w+',(x or '').lower())[:10000]] for i in range(max(1,len(w)-4))}
p['true_j']=[len((A:=sh(t[a]))&(B:=sh(t[b])))/max(1,len(A|B)) for a,b in zip(p.sid_a,p.sid_b)]
print('\nprecision sample n=',len(p),'true_j>=0.7:',round((p.true_j>=0.7).mean(),3),'>=0.6:',round((p.true_j>=0.6).mean(),3),'>=0.5:',round((p.true_j>=0.5).mean(),3),'median true_j',round(p.true_j.median(),3))
