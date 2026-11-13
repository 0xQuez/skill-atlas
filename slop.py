"""slop_skill flag: transparent rule-based detection of bulk-produced, low-effort skill variants.
Rules (a skill is flagged if ANY fires; every firing rule is written to `slop_reasons`):
 R1 owner_farm_cluster : near-copy cluster has >=100 distinct variants, >=90% of them from one owner, and this skill belongs to that owner
 R2 templated_name     : name is template-numbered (e.g. u07780-..., *-skill-269, quantum-expert-83: regex ^[a-z]{0,3}\\d{3,}[-_] or [-_]\\d{2,}$)
                         AND its owner has >=100 distinct skills with such numbered names
 R3 unnamed_mass       : no frontmatter name, owner has >=500 unnamed distinct skills, and the skill sits in a near-copy cluster of >=10 variants, >=90% from this owner
Owner exemptions (EXEMPT_OWNERS, decided by quez 2026-11-09): Klotzkette (German legal-canon skills) and membranedev
(app-integration templates) are templated but deliberate; none of R1-R3 fire for them.
Updates out/full/skills.parquet (slop_skill, slop_reasons) and adds with/without-slop numbers to out/full/headline.json."""
import duckdb, json, os
EXEMPT_OWNERS=["Klotzkette","membranedev"]
CRITERIA={"version":"v0.2","rules":{"R1_owner_farm_cluster":"near-copy cluster >=100 variants, >=90% from one owner, skill owned by that owner","R2_templated_name":"numbered name (^[a-z]{0,3}\\d{3,}[-_] or [-_]\\d{2,}$) and owner has >=100 numbered names","R3_unnamed_mass":"no name, owner has >=500 unnamed skills, cluster >=10 variants >=90% from this owner"},"exempt_owners":EXEMPT_OWNERS,"exemption_reason":"user decision 2026-11-09: deliberate templated collections, not low-effort slop"}
c=duckdb.connect(); c.execute("SET memory_limit='"+os.environ.get('DUCK_MEM','1GB')+"'; SET threads=2")
c.execute("CREATE TABLE s AS SELECT * EXCLUDE (slop_skill, slop_reasons) FROM 'out/full/skills.parquet'" if 'slop_skill' in [r[0] for r in c.execute("describe select * from 'out/full/skills.parquet'").fetchall()] else "CREATE TABLE s AS SELECT * FROM 'out/full/skills.parquet'")
NUM=r"(regexp_matches(name,'^[a-z]{0,3}\d{3,}[-_]') OR regexp_matches(name,'[-_]\d{2,}$'))"
c.execute(f"""CREATE TABLE cl AS SELECT cluster_id, count(*) size, arg_max(rep_owner, n) top_owner, max(n)/count(*)::DOUBLE share FROM
  (SELECT cluster_id, rep_owner, count(*) OVER (PARTITION BY cluster_id, rep_owner) n FROM s WHERE cluster_id>=0) GROUP BY 1""")
c.execute(f"""CREATE TABLE ow AS SELECT rep_owner, count(*) FILTER (WHERE {NUM}) numbered, count(*) FILTER (WHERE name IS NULL) unnamed FROM s GROUP BY 1""")
c.execute(f"""CREATE TABLE f AS SELECT s.sid,
  CASE WHEN cl.size>=100 AND cl.share>=0.9 AND s.rep_owner=cl.top_owner THEN 'owner_farm_cluster: cluster '||cl.cluster_id||' has '||cl.size||' variants, '||round(100*cl.share,1)||'% from '||cl.top_owner END r1,
  CASE WHEN {NUM.replace('name','s.name')} AND ow.numbered>=100 THEN 'templated_name: "'||s.name||'" is numbered; owner '||s.rep_owner||' has '||ow.numbered||' numbered names' END r2,
  CASE WHEN s.name IS NULL AND ow.unnamed>=500 AND cl.size>=10 AND cl.share>=0.9 AND s.rep_owner=cl.top_owner THEN 'unnamed_mass: no name; owner '||s.rep_owner||' has '||ow.unnamed||' unnamed skills; in cluster of '||s.cluster_size END r3
  FROM s LEFT JOIN cl USING(cluster_id) LEFT JOIN ow USING(rep_owner)""")
ex="','".join(EXEMPT_OWNERS)
c.execute(f"UPDATE f SET r1=NULL, r2=NULL, r3=NULL WHERE sid IN (SELECT sid FROM s WHERE rep_owner IN ('{ex}'))")
c.execute("""CREATE TABLE s2 AS SELECT s.*, (r1 IS NOT NULL OR r2 IS NOT NULL OR r3 IS NOT NULL) slop_skill,
  concat_ws(' | ', r1, r2, r3) slop_reasons FROM s JOIN f USING(sid) ORDER BY sid""")
c.execute("COPY s2 TO 'out/full/skills.parquet' (FORMAT parquet)")
q=lambda x: c.execute(x).fetchone()
S={'criteria':CRITERIA}
json.dump(CRITERIA,open('out/full/slop_criteria.json','w'),indent=1)
S['rules']={'R1':int(q("select count(*) from f where r1 is not null")[0]),'R2':int(q("select count(*) from f where r2 is not null")[0]),'R3':int(q("select count(*) from f where r3 is not null")[0])}
S['flagged_skills'],S['flagged_file_rows'],S['flagged_rep_repos'],S['flagged_rep_owners']=map(int,q("select count(*), sum(n_files), count(distinct rep_repo), count(distinct rep_owner) from s2 where slop_skill"))
S['top_flagged_owners']=c.execute("select rep_owner, count(*) n, any_value(slop_reasons) example from s2 where slop_skill group by 1 order by 2 desc limit 10").df().to_dict('records')
def head(where):
    n,files=q(f"select count(*), sum(n_files) from s2 where {where}")
    # recount clusters on the remaining skills only
    cs=c.execute(f"select count(*) clusters, sum(k) members, max(k) largest, count(*) filter (where repos>1) xrepo, count(*) filter (where owners>1) xowner from (select cluster_id, count(*) k, count(distinct rep_repo) repos, count(distinct rep_owner) owners from s2 where {where} and cluster_id>=0 group by 1 having count(*)>=2)").fetchone()
    fam=n-(cs[1] or 0)+cs[0]
    return {'distinct_skills':int(n),'file_rows':int(files),'exact_copy_occurrence_pct':round(100*(1-n/files),2),'clusters':int(cs[0]),'skills_in_clusters':int(cs[1] or 0),
            'near_copy_rate_distinct_pct':round(100*(cs[1] or 0)/n,2),'families_after_exact_and_near':int(fam),'file_rows_redundant_pct_exact_or_near':round(100*(1-fam/files),2),
            'largest_cluster':int(cs[2] or 0),'clusters_cross_repo':int(cs[3]),'clusters_cross_owner':int(cs[4])}
S['with_slop']=head('true'); S['without_slop']=head('not slop_skill')
H=json.load(open('out/full/headline.json')); H['slop']=S; json.dump(H,open('out/full/headline.json','w'),indent=1,default=str)
print(json.dumps(S,indent=1,default=str))
