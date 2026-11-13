"""Combine deterministic metrics (results_auto.json) with blind judgments (judgments.csv) -> results.json.
Judged subset: 24 tasks (12 popular, 12 niche), top-3 picks per arm. rel: 0 not relevant / 1 partial / 2 directly serves the need.
ok: 1 = substantive, coherent, reusable outside its origin project, no suspicious instructions (judged without seeing repo, stars, arm or verdict)."""
import json, numpy as np, pandas as pd
RNG = np.random.default_rng(20261109); NB = 10000
R = json.load(open('results_auto.json'))
P = pd.read_csv('picks.csv'); J = pd.read_csv('judge_pool_hidden_key.csv'); L = pd.read_csv('judgments.csv')
JL = J.merge(L, on='item')[['task_id', 'skill_id', 'rel', 'ok']]
tasks = sorted(J.task_id.unique())
S = P[(P['rank'] <= 3) & P.task_id.isin(tasks)].merge(JL, on=['task_id', 'skill_id'], how='left')
assert S.rel.notna().all()
S['relevant'] = S.rel >= 1; S['direct'] = S.rel == 2; S['good'] = (S.rel == 2) & (S.ok == 1)
S['good_distinct'] = S.good & ~S.text_dup_of_earlier
S.to_csv('judged_picks.csv', index=False)
ARMS = ['B0_bm25_files', 'B1_bm25', 'B2_bm25_stars', 'A1_atlas_bm25', 'A2_atlas_stars', 'A3_atlas_api']
JM = ['relevant', 'direct', 'ok', 'good']
pt = S.groupby(['arm', 'task_id'])[JM].mean()
pts = S.groupby(['arm', 'task_id']).good_distinct.sum().rename('good_distinct_options_top3')
pt = pt.join(pts).reset_index()
def boot(arm, m, other=None):
    a = pt[pt.arm == arm].set_index('task_id')[m]
    tl = [t for t in tasks if t in a.index and (other is None or t in set(pt[pt.arm == other].task_id))]
    v = a.loc[tl].values.astype(float) - (pt[pt.arm == other].set_index('task_id')[m].loc[tl].values.astype(float) if other else 0)
    bs = v[RNG.integers(0, len(v), (NB, len(v)))].mean(1)
    return {'mean': round(float(v.mean()), 4), 'ci95': [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)], 'n_tasks': len(v)}
R['judged'] = {'protocol': __doc__.strip(), 'n_items': int(len(L)), 'n_tasks': len(tasks), 'tasks': tasks,
               'judge': 'the AI assistant that ran the eval, blind to arm/repo/stars/verdict/flags; not a human, no external LLM API (none configured on the box)',
               'metrics': {a: {m: boot(a, m) for m in JM + ['good_distinct_options_top3']} for a in ARMS},
               'paired_diff': {f'{a}-{b}': {m: boot(a, m, b) for m in JM + ['good_distinct_options_top3']}
                               for a, b in [('A1_atlas_bm25', 'B0_bm25_files'), ('A1_atlas_bm25', 'B1_bm25'), ('A2_atlas_stars', 'B2_bm25_stars'), ('A3_atlas_api', 'B1_bm25')]}}
# validity of atlas labels against blind judgments (item level, all judged items)
JV = J.merge(L, on='item').merge(P[['skill_id', 'verdict', 'is_canonical', 'slop_skill', 'quality', 'risk']].drop_duplicates('skill_id'), on='skill_id')
R['label_validity'] = {
    'ok_rate_by_verdict': {v: {'n': int((JV.verdict == v).sum()), 'ok_rate': round(float(JV[JV.verdict == v].ok.mean()), 3)} for v in ['use', 'caution', 'ignore']},
    'ok_rate_by_canonical': {str(k): {'n': int((JV.is_canonical == k).sum()), 'ok_rate': round(float(JV[JV.is_canonical == k].ok.mean()), 3)} for k in [True, False]},
    'note': 'Non-canonical items are mostly copies of good skills, so their ok-rate can be high: near_copy_of says "use the original", not "this content is bad".'}
# post-hoc external safety check (added after inspecting picks): repos that self-declare as malicious-skill benchmarks
MAL = ['lxyeternal/MalSkillBench', 'qyb156/PoisonedSkills', 'AeonDave/malskill', 'trailofbits/overtly-malicious-skills']
P['flag_mal_bench'] = P.top_repo.isin(MAL)
ptm = P.groupby(['arm', 'task_id']).flag_mal_bench.mean().reset_index()
def bootm(arm, other=None):
    a = ptm[ptm.arm == arm].set_index('task_id').flag_mal_bench
    tl = [t for t in a.index if other is None or t in set(ptm[ptm.arm == other].task_id)]
    v = a.loc[tl].values.astype(float) - (ptm[ptm.arm == other].set_index('task_id').flag_mal_bench.loc[tl].values.astype(float) if other else 0)
    bs = v[RNG.integers(0, len(v), (NB, len(v)))].mean(1)
    return {'mean': round(float(v.mean()), 4), 'ci95': [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)], 'n_tasks': len(v), 'picks': int(P[(P.arm == arm)].flag_mal_bench.sum())}
import duckdb
corp = duckdb.sql(f"select top_repo, count(*) n, sum((verdict='use')::int) use_n from '../out/full/verdicts_compact.parquet' where top_repo in {tuple(MAL)} group by 1 order by n desc").fetchall()
R['malicious_benchmark_check'] = {'post_hoc': True, 'repos': MAL, 'per_arm': {a: bootm(a) for a in ARMS},
    'diff': {'A1_atlas_bm25-B1_bm25': bootm('A1_atlas_bm25', 'B1_bm25'), 'A2_atlas_stars-B2_bm25_stars': bootm('A2_atlas_stars', 'B2_bm25_stars')},
    'corpus': [{'repo': r, 'skills': n, 'verdict_use': u} for r, n, u in corp]}
print(json.dumps(R['malicious_benchmark_check'], indent=0)[:1500])
json.dump(R, open('results.json', 'w'), indent=1)
for a in ARMS: print(a, {m: (R['judged']['metrics'][a][m]['mean'], R['judged']['metrics'][a][m]['ci95']) for m in JM + ['good_distinct_options_top3']})
for k, v in R['judged']['paired_diff'].items(): print(k, {m: (v[m]['mean'], v[m]['ci95']) for m in v})
print(json.dumps(R['label_validity'], indent=0))
