"""Find near-copies that only embeddings caught: pairs with cosine>=0.95, no MinHash pair, exact 5-shingle Jaccard < 0.5,
different representative owners. Prints counts + examples; writes out/full/emb_only_examples.json"""
import duckdb, re, json, numpy as np, pandas as pd
c=duckdb.connect(); c.execute("SET memory_limit='3GB'; SET threads=4"); q=lambda s:c.execute(s).df()
H={}
H['emb_pairs_total']=int(q("select count(*) n from 'out/full/pairs.parquet' where cosine is not null and kind in ('embedding','minhash+embedding')").n[0])
H['emb_only_pairs']=int(q("select count(*) n from 'out/full/pairs.parquet' where kind='embedding'").n[0])
p=q("""select p.*, a.rep_repo ra, b.rep_repo rb, a.rep_owner oa, b.rep_owner ob, a.name na, b.name nb, a.max_stars sa, b.max_stars sb
 from 'out/full/pairs.parquet' p join 'out/full/skills.parquet' a on a.sid=p.sid_a join 'out/full/skills.parquet' b on b.sid=p.sid_b
 where p.kind='embedding'""")
H['emb_only_cross_owner']=int((p.oa!=p.ob).sum())
s=p[(p.oa!=p.ob)].sample(min(400,int((p.oa!=p.ob).sum())),random_state=3)
ids=",".join(map(str,set(s.sid_a)|set(s.sid_b)))
t=q(f"select sid, content from 'out/full/text/*.parquet' where sid in ({ids})").set_index('sid').content
sh=lambda x:{' '.join(w[i:i+5]) for w in [re.findall(r'\w+',(x or '').lower())[:10000]] for i in range(max(1,len(w)-4))}
s['true_j']=[len((A:=sh(t[a]))&(B:=sh(t[b])))/max(1,len(A|B)) for a,b in zip(s.sid_a,s.sid_b)]
H['sample_emb_only_cross_owner_n']=len(s); H['sample_true_j_lt_0.5_pct']=round(100*(s.true_j<0.5).mean(),1); H['sample_true_j_median']=round(float(s.true_j.median()),3)
ex=s[(s.true_j<0.4)].sort_values(['cosine'],ascending=False)
ex=ex.assign(stars=ex[['sa','sb']].max(1)).sort_values('stars',ascending=False).head(12)
H['examples']=[{'cosine':round(float(r.cosine),3),'true_jaccard':round(r.true_j,3),'a':[r.na,r.ra,int(r.sa or 0)],'b':[r.nb,r.rb,int(r.sb or 0)],
  'a_head':t[r.sid_a][:300],'b_head':t[r.sid_b][:300]} for r in ex.itertuples()]
json.dump(H,open('out/full/emb_only_examples.json','w'),indent=1,default=str)
for k,v in H.items():
    if k!='examples': print(k,v)
for e in H['examples']: print('\n',e['cosine'],e['true_jaccard'],e['a'],'<->',e['b'],'\n A:',e['a_head'][:200].replace('\n',' '),'\n B:',e['b_head'][:200].replace('\n',' '))
