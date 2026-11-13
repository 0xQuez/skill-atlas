"""Blind judging pool: 24 tasks (12 popular, 12 niche; seed 7), top-3 picks of every arm, de-duplicated by (task, skill), shuffled.
The judge sees only the task need, the skill name, description and the start of its body — no repo, stars, arm, verdict or flags."""
import re, numpy as np, pandas as pd, duckdb
P = pd.read_csv('picks.csv'); T = pd.read_csv('tasks.csv'); rng = np.random.default_rng(7)
pick = list(rng.choice(T[T.stratum == 'popular'].task_id, 12, replace=False)) + list(rng.choice(T[T.stratum == 'niche'].task_id, 12, replace=False))
S = P[(P['rank'] <= 3) & P.task_id.isin(pick)][['task_id', 'skill_id']].drop_duplicates()
S = S.sample(frac=1, random_state=11).reset_index(drop=True); S['item'] = np.arange(len(S))
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
J = pd.DataFrame(rows); J.to_csv('judge_pool_hidden_key.csv', index=False)
with open('judge_pool.txt', 'w') as f:
    for r in J.itertuples():
        f.write(f"[{r.item}] NEED: {r.need}\n  name={r.name} | chars={r.chars}\n  desc: {r.description}\n  body: {r.body_head}\n\n")
print(len(J), 'items; tasks', pick)
