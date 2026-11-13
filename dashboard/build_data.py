"""Pre-aggregate Skill Atlas outputs for the static dashboard.
Inputs : ../out/full/{verdicts_compact.parquet, skills.parquet, headline.json, headline_compare.json, slop_criteria.json,
          emb_only_examples.json, refine_pairs_stats.json, label_*.csv}
Outputs: src/data/*.json (small aggregates, inlined at build time)
         src/data/search_index.parquet  (lazy: skill_id + lowercase search text, sorted by copy count desc)
         src/data/skill_details.parquet (lazy: per-skill card fields, sorted by skill_id, small row groups for range reads)"""
import json, os, time, duckdb, csv
t0=time.time(); F='../out/full/'; O='src/data/'
c=duckdb.connect(); c.execute("SET memory_limit='3GB'; SET threads=2; SET preserve_insertion_order=true")
c.execute(f"create view v as select *, split_part(top_repo,'/',1) owner from '{F}verdicts_compact.parquet'")
H=json.load(open(F+'headline.json')); C=json.load(open(F+'headline_compare.json'))
R=json.load(open(F+'refine_pairs_stats.json'))
def q(sql): return c.execute(sql).fetchdf()
def rec(df): return json.loads(df.to_json(orient='records'))
# ---------- overview ----------
hist_q=rec(q("select (quality//10)*10 bin, verdict, count(*) n from v where quality is not null group by all order by bin"))
hist_r=rec(q("select least(risk,60)//5*5 bin, count(*) n from v where risk is not null group by all order by bin"))
basis=rec(q("select coalesce(canon_basis,'?') basis, count(*) n, sum(is_canonical::int) canon from v group by all order by n desc"))
canon_v=rec(q("select verdict, count(*) n from v where is_canonical group by all"))
def lab(fn):
    p=F+fn
    if not os.path.exists(p): return None
    rows=list(csv.DictReader(open(p))); t=sum(r['label'].strip().lower()=='true' for r in rows); return {'n':len(rows),'true':t}
ov={k:H.get(k) for k in ['artifact_rows','distinct_contents','repos','owners','kept','non_junk_file_rows','exact_copy_occurrence_pct',
    'clusters','skills_in_clusters','near_copy_rate_distinct_pct','file_rows_redundant_pct_exact_or_near','largest_cluster',
    'families_after_exact_and_near','clusters_cross_repo','clusters_cross_owner','cluster_size_hist','junk_drop_sequential',
    'emb_only_pairs','emb_only_rejected','translation_pairs','minhash_pairs','pairs_total','lsh_candidates','top_aggregator_repos']}
ov['slop']={'with':H['slop']['with_slop'],'without':H['slop']['without_slop'],'flagged_skills':H['slop']['flagged_skills'],
            'flagged_file_rows':H['slop']['flagged_file_rows']}
ov['verdicts']=H['verdicts']; ov['quality_hist']=hist_q; ov['risk_hist']=hist_r; ov['canon_basis']=basis; ov['canonical_verdicts']=canon_v
ov['compare']={'minhash_only_near_copy_pct':C.get('near_copy_rate_distinct_pct',{}).get('minhash_only'),
               'minhash_only_without_slop':(C.get('slop_without',{}).get('minhash_only') or {}).get('near_copy_rate_distinct_pct'),
               'verdicts':C.get('verdicts')}
ov['refine']=R; ov['labels']={'before':lab('label_before.csv'),'after':lab('label_after.csv'),'translation':lab('label_translation.csv')}
ov['emb_examples']=json.load(open(F+'emb_only_examples.json')).get('examples',[])[:10]
ov['generated']=time.strftime('%Y-%m-%d %H:%M %Z')
ov['safety']={'malicious': json.load(open(F+'malicious_source_stats.json')) if os.path.exists(F+'malicious_source_stats.json') else None,
              'risk': json.load(open(F+'risk_v2_stats.json')) if os.path.exists(F+'risk_v2_stats.json') else None}
if os.path.exists(F+'white_hat_stats.json'):
    W=json.load(open(F+'white_hat_stats.json'))
    W['top_repos']=rec(q("select coalesce(top_repo,rep_repo) repo, count(*) n, sum((verdict='use')::int) use_n from v where white_hat group by 1 order by n desc limit 15"))
    W['risk_bands']=rec(q("select case when risk>=40 then 'high (40+)' when risk>=20 then 'some (20-39)' else 'low (<20)' end band, count(*) n from v where white_hat group by 1 order by 1"))
    W.pop('repo_skills_not_tagged_sample',None)
    ov['white_hat']=W
json.dump(ov,open(O+'overview.json','w'))
# ---------- families ----------
fam=q("""
with top as (select cluster_id, count(*) size, sum(n_files) files, count(distinct owner) owners, count(distinct top_repo) repos,
       avg(slop_skill::int) slop_share, count(distinct name_key) names, sum(is_canonical::int) canonicals,
       sum((verdict='use')::int) use_n, sum((verdict='caution')::int) caution_n, sum((verdict='ignore')::int) ignore_n,
       any_value(family_canonical_id) fcid, max(max_stars) max_stars
     from v where cluster_id is not null and cluster_id >= 0 group by cluster_id order by size desc limit 300),
own as (select cluster_id, list(struct_pack(o:=owner, n:=n) order by n desc)[1:5] top_owners from
       (select v.cluster_id, owner, count(*) n from v join top using(cluster_id) group by all) group by cluster_id),
nm as (select cluster_id, list(struct_pack(k:=k, n:=n) order by n desc)[1:5] top_names from
       (select v.cluster_id, coalesce(name_key,'(no name)') k, count(*) n from v join top using(cluster_id) group by all) group by cluster_id)
select top.*, c.name canon_name, c.top_repo canon_repo, c.github_url canon_url, c.canon_basis canon_basis, c.verdict canon_verdict,
       c.max_stars canon_stars, c.slop_skill canon_slop, own.top_owners, nm.top_names
from top left join v c on c.skill_id=top.fcid left join own on own.cluster_id=top.cluster_id left join nm on nm.cluster_id=top.cluster_id order by size desc""")
json.dump(rec(fam),open(O+'families.json','w'))
# ---------- slop ----------
so=q("""select owner, count(*) n, sum(n_files) files, count(distinct top_repo) repos, count(distinct cluster_id) clusters,
   sum((slop_reasons like '%owner_farm_cluster%')::int) r1, sum((slop_reasons like '%templated%')::int) r2,
   sum((slop_reasons like '%unnamed_mass%')::int) r3, any_value(slop_reasons) example
   from v where slop_skill group by owner order by n desc limit 40""")
rules=q("""select sum((slop_reasons like '%owner_farm_cluster%')::int) r1, sum((slop_reasons like '%templated%')::int) r2,
   sum((slop_reasons like '%unnamed_mass%')::int) r3, count(*) n from v where slop_skill""")
ex=q("""select owner, count(*) n, sum(n_files) files, count(distinct cluster_id) clusters, max(cluster_size) max_cluster,
   sum((verdict='use')::int) use_n from v where owner in ('Klotzkette','membranedev') group by owner""")

crit=json.load(open(F+'slop_criteria.json'))
json.dump({'criteria':crit,'rules':rec(rules)[0],'headline_rules':H['slop'].get('rules'),'owners':rec(so),'exempt':rec(ex),
           'flagged_rep_repos':H['slop'].get('flagged_rep_repos'),'flagged_rep_owners':H['slop'].get('flagged_rep_owners')},open(O+'slop.json','w'))
# ---------- search payloads ----------
# same index file the API uses (server/build_search.py): normalised name / owner-repo / description[:200], sorted by rank
c.execute(f"""copy (select skill_id, name_n, repo_n, hay, verdict, slop_skill slop, is_canonical canon, white_hat wh, rk from '{F}search_api.parquet' order by rk)
   to '{O}search_index.parquet' (format parquet, compression zstd, compression_level 9, row_group_size 100000)""")
c.execute(f"""copy (select skill_id, canonical_id, is_canonical, name, left(description,240) description, top_repo, github_url,
   canon_basis, max_stars, n_files, n_repos, cluster_id, cluster_size, quality, risk, risk_flags, slop_skill,
   left(slop_reasons,200) slop_reasons, verdict, cast(reasons as varchar) reasons, renamed_copy, white_hat, white_hat_kind from v order by skill_id)
   to '{O}skill_details.parquet' (format parquet, compression zstd, compression_level 9, row_group_size 2048)""")
for f in sorted(os.listdir(O)): print(f, round(os.path.getsize(O+f)/1e6,2),'MB')
print('done', round(time.time()-t0),'s')
# ---------- eval (from ../eval/results.json, if present) ----------
if os.path.exists('../eval/results.json'):
    E = json.load(open('../eval/results.json'))
    keep = {k: E[k] for k in ['design', 'coverage', 'metrics', 'paired_diff', 'by_stratum', 'judged', 'label_validity', 'malicious_benchmark_check', 'safety', 'v1_vs_v2'] if k in E}
    keep['judged'] = {k: v for k, v in keep['judged'].items() if k != 'tasks'}
    json.dump(keep, open(O + 'eval.json', 'w')); print('eval.json', round(os.path.getsize(O + 'eval.json') / 1e3, 1), 'kB')
