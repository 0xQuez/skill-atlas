"""Step 5: full-scale headline numbers -> out/full/headline.json"""
import duckdb, json
c=duckdb.connect('out/full/atlas.duckdb',read_only=True); c.execute("SET memory_limit='1GB'; SET threads=2")
q=lambda s: c.execute(s).df()
H=json.load(open('out/full/ingest_stats.json')); H.update(json.load(open('out/full/headline_clusters.json')))
H['families_after_exact_and_near']=H['non_junk_distinct']-H['redundant_distinct_beyond_exact']
H['file_rows_redundant_pct_exact_or_near']=round(100*(1-H['families_after_exact_and_near']/H['non_junk_file_rows']),2)
cl="'out/full/clusters.parquet'"; sk="'out/full/skills.parquet'"
def fam(where,k=5):
    out=[]
    for r in q(f"select * from {cl} where {where} order by size desc limit {k}").itertuples():
        names=q(f"select coalesce(name,'(no name)') name,count(*) n from {sk} where cluster_id={r.cluster_id} group by 1 order by 2 desc limit 4")
        repos=q(f"select rep_repo,count(*) n from {sk} where cluster_id={r.cluster_id} group by 1 order by 2 desc limit 4")
        top=q(f"select rep_repo, max(rep_stars) s from {sk} where cluster_id={r.cluster_id} group by 1 order by 2 desc nulls last limit 1")
        out.append({'cluster_id':int(r.cluster_id),'distinct_variants':int(r.size),'file_rows':int(r.n_files),'rep_repos':int(r.n_repos_rep),'rep_owners':int(r.n_owners_rep),
          'top_names':list(zip(names.name,names.n.astype(int))),'top_repos':list(zip(repos.rep_repo,repos.n.astype(int))),'most_starred_rep_repo':[top.rep_repo[0],int(top.s[0] or 0)]})
    return out
H['top5_largest_families']=fam('true')
H['top5_cross_owner_families']=fam('n_owners_rep>=10')
H['top5_single_repo_farms']=fam('n_repos_rep=1')
H['top_aggregator_repos']=q("""with a as (select repo_full_name, file_sha from 'hf/data/artifacts/*.parquet')
 select a.repo_full_name repo, count(*) files, count(distinct a.file_sha) distinct_contents,
  round(100*avg(case when cp.n_repos>1 then 1 else 0 end),1) pct_files_also_in_other_repos, any_value(r.stars) stars
 from a join copies cp using(file_sha) left join repos r on r.full_name=a.repo_full_name
 group by 1 order by files desc limit 10""").to_dict('records')
H['repos_by_skill_files_ge_1000']=int(q("select count(*) n from (select repo_full_name from 'hf/data/artifacts/*.parquet' group by 1 having count(*)>=1000)").n[0])
json.dump(H,open('out/full/headline.json','w'),indent=1,default=str); print(json.dumps(H,indent=1,default=str))
