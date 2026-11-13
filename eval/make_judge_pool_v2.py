"""v2 top-up: (task, skill) pairs in the same 24 judged tasks that the v2 rerun picked in a top-3 but that were never judged.
Same blind format; items numbered after the v1 pool and appended to judge_pool_hidden_key.csv (v1 key kept as v1/judge_pool_hidden_key.csv)."""
import re, shutil, os, numpy as np, pandas as pd, duckdb

P = pd.read_csv('picks.csv'); T = pd.read_csv('tasks.csv'); J0 = pd.read_csv('judge_pool_hidden_key.csv')
if not os.path.exists('v1/judge_pool_hidden_key.csv'): shutil.copy('judge_pool_hidden_key.csv', 'v1/judge_pool_hidden_key.csv')
tasks = sorted(J0.task_id.unique())
S = P[(P['rank'] <= 3) & P.task_id.isin(tasks)][['task_id', 'skill_id']].drop_duplicates()
S = S.merge(J0[['task_id', 'skill_id']], how='left', indicator=True); S = S[S._merge == 'left_only'][['task_id', 'skill_id']]
S = S.sample(frac=1, random_state=12).reset_index(drop=True); S['item'] = np.arange(len(S)) + int(J0.item.max()) + 1
c = duckdb.connect(); c.execute("SET memory_limit='2GB'")
c.execute("create temp table ids as select unnest(?) sid", [sorted(set(S.skill_id.astype(int)))])
TX = dict(c.execute("select t.sid, t.content from '../out/full/text/*.parquet' t join ids using(sid)").fetchall())
FM = re.compile(r'^\ufeff?\s*---\s*\n(.*?)\n---\s*(\n|$)', re.S)
def parts(t):
    t = t or ''; m = FM.match(t); body = t[m.end():] if m else t
    fm = m.group(1) if m else ''
    nm = re.search(r'^name:\s*(.+)$', fm, re.M); ds = re.search(r'^description:\s*(.+)$', fm, re.M)
    return (nm.group(1).strip()[:80] if nm else ''), (ds.group(1).strip()[:300] if ds else ''), re.sub(r'\s+', ' ', body)[:600], len(t)
rows = []
for r in S.itertuples():
    nm, ds, body, L = parts(TX.get(int(r.skill_id)))
    rows.append({'item': r.item, 'task_id': r.task_id, 'skill_id': int(r.skill_id), 'need': T.set_index('task_id').need[r.task_id], 'name': nm, 'description': ds, 'body_head': body, 'chars': L})
J = pd.DataFrame(rows); pd.concat([J0, J]).to_csv('judge_pool_hidden_key.csv', index=False)
with open('judge_pool_v2.txt', 'w') as f:
    for r in J.itertuples():
        f.write(f"[{r.item}] NEED: {r.need}\n  name={r.name} | chars={r.chars}\n  desc: {r.description}\n  body: {r.body_head}\n\n")
print(len(J), 'new items')
