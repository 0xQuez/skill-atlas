"""Skill Atlas eval: does an agent pick better skills WITH the atlas than WITHOUT it?
Deterministic (no LLM API available on the box). Corpus = all 1,877,981 distinct SKILL.md contents (GitSkills, exact copies collapsed).
Arms (top-k, k=5), all fed the same keyword query per task:
  B0  bm25_files  : BM25 at file level: each exact copy of a content is a separate hit (copies tie, so they cluster)
  B1  bm25        : BM25 over name+description, top-k by score                       (no atlas)
  B2  bm25_stars  : docs matching ALL query terms, sorted by stars (GitHub-search-like)  (no atlas; falls back to bm25 top-100)
  A1  atlas_bm25  : B1's ranked candidates (top 300) -> find_canonical -> drop 'ignore' -> dedupe canonical -> 'use' first, then 'caution'
  A2  atlas_stars : same atlas policy applied to B2's ranked candidates
  A3  atlas_api   : shipped JSON API /skills/search?q=<query>&verdict=use&limit=k (v1: phrase ILIKE; v2: every word, any order), as deployed locally
Outputs: picks.csv (raw), per_task.csv, results.json (metrics + bootstrap CIs) — see README.md."""
import json, re, time, urllib.parse, urllib.request, numpy as np, pandas as pd, duckdb
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
t0 = time.time(); K = 5; RNG = np.random.default_rng(20261109); NBOOT = 10000
F = '../out/full/'
c = duckdb.connect(); c.execute("SET memory_limit='3GB'; SET threads=2")
D = c.execute(f"""select skill_id, name, description, top_repo, coalesce(max_stars,0) stars, n_files, canonical_id, is_canonical, cluster_id,
   verdict, quality, risk, coalesce(risk_flags,'') risk_flags, slop_skill from '{F}verdicts_compact.parquet' order by skill_id""").fetchdf()
print('corpus', len(D), round(time.time()-t0), 's')
pos = pd.Series(np.arange(len(D)), index=D.skill_id.values)
# ---------- BM25 index over name + description ----------
TOK = r"(?u)[a-z0-9#+]+"
text = (D.name.fillna('').str.replace(r'[-_:/]', ' ', regex=True) + ' ' + D.description.fillna('')).str.lower()
cv = CountVectorizer(token_pattern=TOK, lowercase=False, dtype=np.float32, min_df=2)
X = cv.fit_transform(text.values).tocsc(); del text
vocab = cv.vocabulary_; N = X.shape[0]
dl = np.asarray(X.sum(axis=1)).ravel(); avgdl = dl.mean(); k1, b = 1.2, 0.75
df = np.diff(X.indptr); idf = np.log(1 + (N - df + 0.5) / (df + 0.5))
norm = (k1 * (1 - b + b * dl / avgdl)).astype(np.float32)
print('bm25 index', X.shape, X.nnz, round(time.time()-t0), 's')
def qterms(q): return [t for t in re.findall(TOK, q.lower().replace('-', ' ')) if t in vocab]
def bm25(q):
    terms = qterms(q); s = np.zeros(N, np.float32); hits = np.zeros(N, np.int8)
    for t in terms:
        j = vocab[t]; col = X.getcol(j); r = col.indices; tf = col.data
        s[r] += idf[j] * tf * (k1 + 1) / (tf + norm[r]); hits[r] += 1
    return s, hits, len(terms)
def topn(s, n):
    nz = np.flatnonzero(s > 0)
    if len(nz) == 0: return np.array([], int)
    o = nz[np.lexsort((D.skill_id.values[nz], -s[nz]))]  # score desc, id asc
    return o[:n]
HI = {'pipe_to_shell', 'secret_literal', 'prompt_injection_lang', 'disable_safety', 'base64_decode'}
def atlas_policy(cand_rows):
    use, cau, seen = [], [], set()
    for r in cand_rows:
        if pd.isna(D.canonical_id.values[r]): continue   # v2: no safe original (all versions from known-malicious sources)
        cid = int(D.canonical_id.values[r]); cr = int(pos[cid]) if cid in pos.index else r
        if cid in seen: continue
        seen.add(cid); v = D.verdict.values[cr]
        if v == 'use': use.append(cr)
        elif v == 'caution': cau.append(cr)
        if len(use) >= K: break
    return (use + cau)[:K]
def api(q):
    u = 'http://127.0.0.1:8765/skills/search?' + urllib.parse.urlencode({'q': q, 'verdict': 'use', 'limit': K})
    return [int(pos[r['skill_id']]) for r in json.load(urllib.request.urlopen(u, timeout=60))['results']]
T = pd.read_csv('tasks.csv'); rows = []; cov = {}
for t in T.itertuples():
    s, hits, nt = bm25(t.query)
    b1 = topn(s, 300)
    allm = np.flatnonzero(hits == nt) if nt else np.array([], int)
    if len(allm) >= K: b2 = allm[np.lexsort((D.skill_id.values[allm], -s[allm], -D.stars.values[allm]))][:300]
    else: b2 = topn(s, 100); b2 = b2[np.lexsort((D.skill_id.values[b2], -D.stars.values[b2]))]
    cov[t.task_id] = {'bm25_matches': int((s > 0).sum()), 'all_term_matches': int(len(allm))}
    b0 = [r for r in b1[:K] for _ in range(int(min(D.n_files.values[r], K)))][:K]  # file-level: exact copies are separate hits
    arms = {'B0_bm25_files': b0, 'B1_bm25': list(b1[:K]), 'B2_bm25_stars': list(b2[:K]), 'A1_atlas_bm25': atlas_policy(b1), 'A2_atlas_stars': atlas_policy(b2), 'A3_atlas_api': api(t.query)}
    for arm, picks in arms.items():
        for rank, r in enumerate(picks, 1):
            rows.append({'task_id': t.task_id, 'stratum': t.stratum, 'query': t.query, 'arm': arm, 'rank': rank, 'row': int(r)})
P = pd.DataFrame(rows)
P = P.join(D.reset_index(drop=True), on='row')
P['flag_slop'] = P.slop_skill.astype(bool)
P['flag_near_copy'] = ~P.is_canonical.astype(bool)
P['flag_risky'] = (P.risk.fillna(0) >= 40) | P.risk_flags.apply(lambda f: bool(HI & set(f.split(','))))
P['flag_low_quality'] = P.quality.fillna(0) < 40
P['flag_ignore'] = P.verdict.eq('ignore')
P['flag_any_bad'] = P[['flag_slop', 'flag_near_copy', 'flag_risky', 'flag_low_quality']].any(axis=1)
# ---------- non-circular: raw-text duplicates within top-k (true 5-shingle Jaccard on content) ----------
ids = sorted(set(P.skill_id.astype(int)))
c.execute("create temp table ids as select unnest(?) sid", [ids])
TX = dict(c.execute(f"select t.sid, t.content from '{F}text/*.parquet' t join ids using(sid)").fetchall())
def sh(sid):
    w = re.findall(r'\w+', (TX.get(sid) or '').lower())[:10000]
    return {hash(' '.join(w[i:i+5])) for i in range(max(1, len(w) - 4))}
SH = {s: sh(s) for s in ids}
def jac(a, b): A, B = SH[a], SH[b]; return len(A & B) / max(1, len(A | B))
P['text_dup_of_earlier'] = False; P['max_j_earlier'] = 0.0
for (tid, arm), g in P.groupby(['task_id', 'arm']):
    sids = list(g.sort_values('rank').skill_id.astype(int))
    for i, (ix, s) in enumerate(zip(g.sort_values('rank').index, sids)):
        m = max([jac(s, e) for e in sids[:i]], default=0.0)
        P.at[ix, 'max_j_earlier'] = m; P.at[ix, 'text_dup_of_earlier'] = m >= 0.5
P['log10_stars'] = np.log10(P.stars.astype(float) + 1)
P.drop(columns=['row']).to_csv('picks.csv', index=False)
# ---------- per-task metrics + bootstrap ----------
M = ['flag_slop', 'flag_near_copy', 'flag_risky', 'flag_low_quality', 'flag_ignore', 'flag_any_bad', 'text_dup_of_earlier', 'log10_stars']
pt = P.groupby(['arm', 'task_id', 'stratum'])[M].mean().reset_index()
cnt = P.groupby(['arm', 'task_id']).size().rename('n_picks').reset_index()
dist = P.groupby(['arm', 'task_id']).apply(lambda g: int((~g.text_dup_of_earlier).sum()), include_groups=False).rename('distinct_options').reset_index()
pt = pt.merge(cnt, on=['arm', 'task_id']).merge(dist, on=['arm', 'task_id'])
pt.to_csv('per_task.csv', index=False)
tasks = list(T.task_id); ARMS = ['B0_bm25_files', 'B1_bm25', 'B2_bm25_stars', 'A1_atlas_bm25', 'A2_atlas_stars', 'A3_atlas_api']
def boot(arm, metric, sub=None, other=None):
    a = pt[pt.arm == arm].set_index('task_id')[metric]
    tl = [x for x in tasks if (sub is None or x.startswith(sub)) and x in a.index and (other is None or x in pt[pt.arm == other].task_id.values)]
    va = a.loc[tl].values.astype(float)
    vb = pt[pt.arm == other].set_index('task_id')[metric].loc[tl].values.astype(float) if other else 0
    v = va - vb; idx = RNG.integers(0, len(v), (NBOOT, len(v))); bs = v[idx].mean(1)
    return {'mean': round(float(v.mean()), 4), 'ci95': [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)], 'n_tasks': len(v)}
R = {'design': {'k': K, 'n_tasks': len(T), 'strata': T.stratum.value_counts().to_dict(), 'corpus_distinct_contents': int(N), 'bootstrap': f'{NBOOT} resamples over tasks, percentile 95% CI, seed 20261109',
                'arms': {'B0_bm25_files': 'BM25 at file level (each exact copy is its own hit, as in GitHub code search), top-5', 'B1_bm25': 'BM25 over name+description, top-5', 'B2_bm25_stars': 'all query terms must match, ranked by stars (GitHub-search-like)',
                         'A1_atlas_bm25': 'B1 candidates -> canonical -> drop ignore -> dedupe -> use first', 'A2_atlas_stars': 'B2 candidates with the same atlas policy',
                         'A3_atlas_api': 'shipped /skills/search?verdict=use (v2: every query word must match, any order)'}},
     'coverage': {a: {'tasks_with_k_picks': int((pt[pt.arm == a].n_picks == K).sum()), 'tasks_with_0': int(len(tasks) - (pt.arm == a).sum()), 'mean_picks': round(float(pt[pt.arm == a].n_picks.sum() / len(tasks)), 2)} for a in ARMS},
     'metrics': {}, 'paired_diff': {}, 'by_stratum': {}}
for a in ARMS: R['metrics'][a] = {m: boot(a, m) for m in M + ['distinct_options']}
for a, b_ in [('A1_atlas_bm25', 'B0_bm25_files'), ('A1_atlas_bm25', 'B1_bm25'), ('A2_atlas_stars', 'B2_bm25_stars'), ('A1_atlas_bm25', 'B2_bm25_stars')]:
    R['paired_diff'][f'{a}-{b_}'] = {m: boot(a, m, other=b_) for m in M + ['distinct_options']}
for st, pre in [('popular', 'p'), ('niche', 'n')]:
    R['by_stratum'][st] = {a: {m: boot(a, m, sub=pre) for m in ['flag_any_bad', 'flag_near_copy', 'flag_slop', 'text_dup_of_earlier', 'distinct_options']} for a in ARMS}
R['coverage_per_task'] = cov; R['elapsed_s'] = round(time.time() - t0)
json.dump(R, open('results_auto.json', 'w'), indent=1)
for a in ARMS: print(a, R['coverage'][a], {m: R['metrics'][a][m]['mean'] for m in M + ['distinct_options']})
print('elapsed', R['elapsed_s'])
