"""Step 1: build out/full/atlas.duckdb with `skills` (one row per distinct content) + junk filters.
Reads hf/data/{artifacts,repos}/*.parquet (HF dataset mvaccargiu/gitskills, CC BY 4.0)."""
import duckdb, time, json, os
ROOT=os.path.dirname(os.path.abspath(__file__))
TMP=os.path.join(ROOT, "tmp"); os.makedirs(TMP, exist_ok=True)
t=time.time()
c=duckdb.connect(os.path.join(ROOT, "out/full/atlas.duckdb"))
c.execute(f"SET memory_limit='3GB'; SET threads=4; SET temp_directory='{TMP}'; SET preserve_insertion_order=false")
c.execute("CREATE OR REPLACE VIEW art AS SELECT * FROM 'hf/data/artifacts/*.parquet'")
c.execute("CREATE OR REPLACE TABLE repos AS SELECT * FROM 'hf/data/repos/*.parquet'")
c.execute("""CREATE OR REPLACE TABLE copies AS
 SELECT file_sha, count(*) n_files, count(DISTINCT repo_full_name) n_repos,
        count(DISTINCT split_part(repo_full_name,'/',1)) n_owners
 FROM art GROUP BY file_sha""")
c.execute("CREATE OR REPLACE TABLE sidmap AS SELECT file_sha, (row_number() OVER (ORDER BY file_sha) - 1)::INTEGER sid FROM copies")
c.execute("""CREATE OR REPLACE TABLE skills AS
 SELECT m.sid, a.file_sha, a.repo_full_name rep_repo, split_part(a.repo_full_name,'/',1) rep_owner,
  a.path rep_path, a.filename, a.location_class, a.frontmatter_valid, a.name, a.description, a.body_chars,
  length(a.content) content_chars, length(trim(a.content)) trimmed_chars, (position(chr(10) IN trim(a.content))=0) one_line,
  a.has_scripts, a.has_references, a.sibling_count, a.composition_truncated,
  a.first_commit_at, a.last_commit_at, a.commit_count,
  cp.n_files, cp.n_repos, cp.n_owners, r.stars rep_stars, r.license rep_license, r.language rep_language, r.is_fork rep_is_fork,
  CASE WHEN length(a.content)<2000 THEN a.content END short_content
 FROM art a JOIN sidmap m USING(file_sha) JOIN copies cp USING(file_sha) LEFT JOIN repos r ON r.full_name=a.repo_full_name
 WHERE a.dedup_primary=1""")
print('skills built',round(time.time()-t),'s')
# max stars over all repos holding a copy (for subset prioritisation)
c.execute("""CREATE OR REPLACE TABLE maxstars AS SELECT a.file_sha, max(coalesce(r.stars,0)) max_stars
 FROM art a LEFT JOIN repos r ON r.full_name=a.repo_full_name GROUP BY a.file_sha""")
c.execute("ALTER TABLE skills ADD COLUMN max_stars BIGINT")
c.execute("UPDATE skills s SET max_stars=m.max_stars FROM maxstars m WHERE m.file_sha=s.file_sha")
# junk flags (independent) and sequential drop
c.execute("""ALTER TABLE skills ADD COLUMN junk VARCHAR""")
c.execute(r"""UPDATE skills SET junk = CASE
  WHEN trimmed_chars IS NULL OR trimmed_chars=0 THEN 'empty'
  WHEN trimmed_chars<300 AND one_line AND regexp_matches(trim(short_content),'^[A-Za-z0-9_.~/\-]+$') AND regexp_matches(trim(short_content),'(/|\.md$)') THEN 'symlink_path'
  WHEN short_content IS NOT NULL AND (regexp_matches(short_content,'(?i)^\s*redirecting') OR regexp_matches(short_content,'(?i)http-equiv=.?refresh') OR regexp_matches(short_content,'(?i)^\s*(moved|this (file|skill) (has )?moved)')) THEN 'redirect'
  WHEN content_chars<200 THEN 'under_200_chars'
  ELSE NULL END""")
R={}
R['artifact_rows']=c.execute("select count(*) from art").fetchone()[0]
R['distinct_contents']=c.execute("select count(*) from skills").fetchone()[0]
R['repos']=c.execute("select count(*) from repos").fetchone()[0]
R['owners']=c.execute("select count(distinct owner) from repos").fetchone()[0]
R['junk_drop_sequential']=dict(c.execute("select junk,count(*) from skills where junk is not null group by 1 order by 2 desc").fetchall())
R['kept']=c.execute("select count(*) from skills where junk is null").fetchone()[0]
R['exact_copy_occurrence_pct']=round(100*(1-R['distinct_contents']/R['artifact_rows']),2)
print(json.dumps(R,indent=1)); json.dump(R,open('out/full/ingest_stats.json','w'),indent=1)
c.execute("COPY (SELECT * EXCLUDE(short_content) FROM skills ORDER BY sid) TO 'out/full/skills_meta_raw.parquet' (FORMAT parquet)")

# text export moved to export_text.py (DuckDB parallel COPY of large text stalled)
print('done',round(time.time()-t),'s')
