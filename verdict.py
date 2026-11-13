"""Agent-facing verdicts. Inputs: out/full/skills.parquet (clusters + slop), out/full/scores.parquet, out/full/skills_meta_raw.parquet (junk rows).
canonical_id (v3): computed per (family cluster_id, name_key) group; unnamed members use the family-level canonical;
  a name-singleton is its own canonical unless its text is near-identical (MinHash J>=0.9) to a better-ranked canonical of another
  name in the same family (then near_copy_of + renamed_copy). family_canonical_id keeps the family-level pick.
  v2 ranking inside each group:  eligible = not slop AND risk<40 AND quality>=60 (if none, whole family);
  rank by max_stars (most-starred repo holding the exact content), then earliest origin_date, quality, n_files; singletons -> own sid.
  Why stars before date: the dataset has no reliable per-file origin date. first_commit_at exists for 21% of family members and
  describes the representative copy's path (mattpocock/skills content carries a 2026-07-14 date from a copy), and repo created_at
  dates the repo, not the skill (2013/2015 dotfiles repos won date-first). Date-first picked a copy in 5 of 6 spot-checked families;
  stars-first picked the known original (mattpocock/skills, garrytan/gstack, ComposioHQ/awesome-claude-skills).
  origin_date = first_commit_at if sampled, else created_at of the most-starred holder repo if >= 2025-10-01, else NULL.
verdict (first matching tier wins; ALL fired reasons are kept in `reasons`, a JSON list of machine codes):
  ignore : junk:<type> | known_malicious_source (malicious_source.py: content from a self-described malicious/poisoned skill
           collection, or a near-copy carrying its payload; never canonical, canonical_id NULL when no safe member exists) | slop_skill | risk_high (risk>=40) | quality_low (quality<40) | near_copy_of:<canonical_id>
  caution: risk_medium (20<=risk<40) | risk_flag:<pipe_to_shell|secret_literal|prompt_injection_lang|disable_safety|base64_decode> | quality_medium (40<=quality<60) | invalid_frontmatter
  use    : none of the above
  info   : translated_copy_of:<sid> (body in another language than a better-starred twin; does not change the tier)
Writes out/full/verdicts.parquet (one row per distinct content, junk included so everything stays searchable) and updates headline.json."""
import duckdb, json
c=duckdb.connect(); c.execute("SET memory_limit='1GB'; SET threads=2")
c.execute("""CREATE TABLE s AS SELECT k.*, sc.quality, sc.risk, sc.risk_flags, sc.n_domains, ms.source_kind IS NOT NULL mal, ms.source_kind mal_kind
  FROM 'out/full/skills.parquet' k LEFT JOIN 'out/full/scores.parquet' sc USING(sid) LEFT JOIN 'out/full/malicious_source.parquet' ms USING(sid)""")
# canonical ranking v2 (originals over copies): eligible = not slop AND risk<40 AND quality>=60 (fallback: whole family);
# order = eligible first, max_stars desc (stars of the most-starred repo holding the exact content), earliest origin_date, quality desc,
# quality desc, n_files desc, sid asc.
# best-known holder of each exact content = the most-starred repo that contains it (rep_repo is an arbitrary copy)
c.execute("""CREATE TABLE holder AS SELECT a.file_sha, arg_max(a.repo_full_name, coalesce(r.stars,0)) top_repo, arg_max(a.path, coalesce(r.stars,0)) top_path,
  arg_max(r.created_at, coalesce(r.stars,0)) top_repo_created_at
  FROM (SELECT file_sha, repo_full_name, path FROM 'hf/data/artifacts/*.parquet') a LEFT JOIN 'hf/data/repos/*.parquet' r ON r.full_name=a.repo_full_name GROUP BY 1""")
# origin_date: file first_commit_at if sampled; else top holder repo created_at, but only if on/after 2025-10-01 (the SKILL.md format
# launched Oct 2025, so an older repo's creation date says nothing about when the skill was written -> NULL, ranked after dated members)
c.execute("""CREATE TABLE s2 AS SELECT s.*, h.top_repo, h.top_path,
  coalesce(TRY_CAST(s.first_commit_at AS TIMESTAMP),
           CASE WHEN TRY_CAST(h.top_repo_created_at AS TIMESTAMP) >= TIMESTAMP '2025-10-01' THEN TRY_CAST(h.top_repo_created_at AS TIMESTAMP) END) origin_date,
  CASE WHEN s.first_commit_at IS NOT NULL THEN 'first_commit_at'
       WHEN TRY_CAST(h.top_repo_created_at AS TIMESTAMP) >= TIMESTAMP '2025-10-01' THEN 'top_repo_created_at'
       ELSE 'unknown' END origin_date_source
  FROM s LEFT JOIN holder h USING(file_sha)""")
c.execute("DROP TABLE s"); c.execute("ALTER TABLE s2 RENAME TO s")
# v3: canonical per (family, normalised name). name_key = lowercase name with whitespace/_/-/. runs collapsed to '-'.
c.execute(r"""ALTER TABLE s ADD COLUMN name_key VARCHAR""")
c.execute(r"""UPDATE s SET name_key = nullif(trim(regexp_replace(lower(trim(name)), '[\s_\-.]+', '-', 'g'), '-'), '')""")
c.execute("""ALTER TABLE s ADD COLUMN rk DOUBLE[]""")
c.execute("""UPDATE s SET rk = [ mal::DOUBLE, (NOT (NOT slop_skill AND coalesce(risk,100)<40 AND coalesce(quality,0)>=60))::DOUBLE,
    -coalesce(max_stars,0)::DOUBLE, coalesce(epoch(origin_date), 9e12)::DOUBLE, -coalesce(quality,0)::DOUBLE, -n_files::DOUBLE, sid::DOUBLE ]""")
c.execute("CREATE TABLE fam AS SELECT cluster_id, arg_min(sid, rk) family_canonical_id FROM s WHERE cluster_id>=0 GROUP BY 1")
c.execute("CREATE TABLE grp AS SELECT cluster_id, name_key, arg_min(sid, rk) gcanon, count(*) gsize FROM s WHERE cluster_id>=0 AND name_key IS NOT NULL GROUP BY 1,2")
c.execute("""CREATE TABLE base AS SELECT s.sid, s.cluster_id, s.name_key, s.rk, fam.family_canonical_id, grp.gcanon, grp.gsize,
   CASE WHEN s.cluster_id<0 THEN s.sid WHEN s.name_key IS NULL THEN fam.family_canonical_id ELSE grp.gcanon END canon0,
   CASE WHEN s.cluster_id<0 THEN 'singleton' WHEN s.name_key IS NULL THEN 'unnamed_family_fallback' WHEN grp.gsize>1 THEN 'name_group' ELSE 'name_singleton' END canon_basis
  FROM s LEFT JOIN fam USING(cluster_id) LEFT JOIN grp USING(cluster_id, name_key)""")
# renamed copies: a name-singleton whose text is near-identical (MinHash est. Jaccard >= 0.9) to the canonical of another name group in
# the same family, where that canonical ranks better, points to it (highest Jaccard wins). Strict rank order prevents cycles; one extra hop
# resolves chains.
c.execute("""CREATE TABLE ren AS SELECT x.sid, arg_max(y.sid, p.j) target, max(p.j) jac FROM
  (SELECT sid_a a, sid_b b, jaccard j FROM 'out/full/pairs.parquet' WHERE jaccard>=0.9 UNION ALL SELECT sid_b, sid_a, jaccard FROM 'out/full/pairs.parquet' WHERE jaccard>=0.9) p
  JOIN base x ON x.sid=p.a AND x.canon_basis='name_singleton'
  JOIN base y ON y.sid=p.b AND y.cluster_id=x.cluster_id AND y.name_key<>x.name_key AND y.canon0=y.sid AND y.rk < x.rk
  GROUP BY 1""")
c.execute("""CREATE TABLE cmap AS SELECT b.sid, b.family_canonical_id, b.canon_basis,
   CASE WHEN ren.target IS NOT NULL THEN coalesce(r2.target, ren.target) ELSE b.canon0 END canonical_id, ren.target IS NOT NULL renamed_copy, ren.jac renamed_jaccard
  FROM base b LEFT JOIN ren USING(sid) LEFT JOIN ren r2 ON r2.sid=ren.target""")
# a known-malicious member can only win a group where every member is malicious; then there is no safe pick -> NULL
c.execute("UPDATE cmap SET canonical_id=NULL FROM s WHERE s.sid=cmap.canonical_id AND s.mal")
c.execute("UPDATE cmap SET family_canonical_id=NULL FROM s WHERE s.sid=cmap.family_canonical_id AND s.mal")
# resolve chains (e.g. unnamed -> family canonical that is itself a renamed copy) to a fixpoint so every target is canonical
for _ in range(10):
    n=c.execute("""UPDATE cmap SET canonical_id=t.canonical_id FROM cmap t WHERE t.sid=cmap.canonical_id AND t.canonical_id<>cmap.canonical_id""").fetchone()[0]
    if not n: break
HI="['pipe_to_shell','secret_literal','prompt_injection_lang','disable_safety','base64_decode']"
c.execute(f"""CREATE TABLE v AS SELECT s.*, cm.canonical_id, coalesce(cm.canonical_id=s.sid, false) is_canonical, cm.family_canonical_id, cm.canon_basis, cm.renamed_copy,
 list_filter([
   CASE WHEN mal THEN 'known_malicious_source' END,
   CASE WHEN slop_skill THEN 'slop_skill' END,
   CASE WHEN risk>=40 THEN 'risk_high' END,
   CASE WHEN quality<40 THEN 'quality_low' END,
   CASE WHEN cm.canonical_id<>s.sid THEN 'near_copy_of:'||cm.canonical_id END,
   CASE WHEN cm.renamed_copy THEN 'renamed_copy' END], lambda x: x IS NOT NULL) ign,
 list_filter(list_concat([
   CASE WHEN risk>=20 AND risk<40 THEN 'risk_medium' END,
   CASE WHEN quality>=40 AND quality<60 THEN 'quality_medium' END,
   CASE WHEN coalesce(frontmatter_valid,0)<>1 THEN 'invalid_frontmatter' END],
   list_transform(list_filter(string_split(coalesce(risk_flags,''),','), lambda f: list_contains({HI}, f)), lambda f: 'risk_flag:'||f)), lambda x: x IS NOT NULL) cau
 FROM s JOIN cmap cm USING(sid)""")
# translations (refine_pairs.py kind='translation'): the less-starred side gets an informational reason translated_copy_of:<other>
import os
if os.path.exists('out/full/pairs.parquet') and 'kind' in [r[0] for r in c.execute("DESCRIBE SELECT * FROM 'out/full/pairs.parquet'").fetchall()]:
    c.execute("""CREATE TABLE tr AS WITH p AS (SELECT sid_a a, sid_b b FROM 'out/full/pairs.parquet' WHERE kind='translation'),
      d AS (SELECT p.a x, p.b y FROM p UNION ALL SELECT p.b, p.a FROM p)
      SELECT d.x sid, arg_max(d.y, coalesce(sy.max_stars,0)) tgt FROM d JOIN s sx ON sx.sid=d.x JOIN s sy ON sy.sid=d.y
      WHERE coalesce(sy.max_stars,0) > coalesce(sx.max_stars,0) OR (coalesce(sy.max_stars,0) = coalesce(sx.max_stars,0) AND d.y < d.x) GROUP BY 1""")
else:
    c.execute("CREATE TABLE tr (sid INTEGER, tgt INTEGER)")
c.execute("""CREATE TABLE out AS
 SELECT sid, file_sha, name, description, rep_repo, rep_owner, rep_path, rep_license, rep_stars, max_stars, n_files, n_repos, n_owners,
   cluster_id, cluster_size, name_key, canonical_id, is_canonical, family_canonical_id, canon_basis, renamed_copy, origin_date, origin_date_source, top_repo, top_path, quality, risk, risk_flags, slop_skill, slop_reasons, embedded,
   CASE WHEN len(ign)>0 THEN 'ignore' WHEN len(cau)>0 THEN 'caution' ELSE 'use' END verdict,
   to_json(list_concat(ign,cau, CASE WHEN tr.tgt IS NOT NULL THEN ['translated_copy_of:'||tr.tgt] ELSE [] END)) reasons, NULL::VARCHAR junk
 FROM v LEFT JOIN tr USING(sid)
 UNION ALL
 SELECT sid, file_sha, name, description, rep_repo, rep_owner, rep_path, rep_license, rep_stars, max_stars, n_files, n_repos, n_owners,
   -1, 1, NULL, sid, true, sid, 'junk', false, NULL, NULL, NULL, NULL, NULL, NULL, NULL, false, NULL, false, 'ignore', to_json(['junk:'||junk]), junk
 FROM 'out/full/skills_meta_raw.parquet' WHERE junk IS NOT NULL""")
c.execute("COPY (SELECT * FROM out ORDER BY sid) TO 'out/full/verdicts.parquet' (FORMAT parquet)")
# compact server-loadable export keyed by skill_id (= sid) and canonical_id; small enough to hold in RAM in a tiny HTTP/MCP service
c.execute("""COPY (SELECT sid AS skill_id, canonical_id, file_sha, name, left(description,300) description, rep_repo, rep_path,
  'https://github.com/'||coalesce(top_repo,rep_repo)||'/blob/HEAD/'||coalesce(top_path,rep_path) AS github_url, coalesce(top_repo,rep_repo) AS top_repo, rep_license license, max_stars, n_files, n_repos,
  cluster_id, cluster_size, name_key, is_canonical, family_canonical_id, canon_basis, renamed_copy, origin_date, quality::SMALLINT quality, risk::SMALLINT risk, risk_flags, slop_skill, slop_reasons, verdict, reasons
  FROM out ORDER BY sid) TO 'out/full/verdicts_compact.parquet' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 100000)""")
c.execute("COPY (SELECT * FROM out WHERE verdict='use' ORDER BY max_stars DESC NULLS LAST LIMIT 200) TO 'out/full/verdicts_sample_top_use.json' (FORMAT json, ARRAY true)")
f=lambda q: c.execute(q).df()
D={'verdict_distribution':dict(f("select verdict, count(*) n from out group by 1 order by 2 desc").values.tolist()),
   'verdict_file_rows':dict(f("select verdict, sum(n_files)::BIGINT n from out group by 1 order by 2 desc").values.tolist()),
   'reason_counts':dict(f("select regexp_replace(r,':\\d+$','') r, count(*) n from (select unnest(from_json(reasons,'[\"VARCHAR\"]')) r from out) group by 1 order by 2 desc").values.tolist()),
   'only_reason_near_copy':int(f("select count(*) n from out where verdict='ignore' and reasons like '[\"near_copy_of:%' and json_array_length(reasons)=1").n[0]),
   'canonical_count':int(f("select count(*) n from out where is_canonical").n[0]),
   'canonical_on_malicious':int(f("select count(*) n from out o where is_canonical and reasons like '%known_malicious_source%'").n[0]),
   'malicious_without_safe_canonical':int(f("select count(*) n from out where canonical_id is null").n[0]),
   'use_among_canonical_nonjunk':int(f("select count(*) n from out where is_canonical and verdict='use'").n[0])}
D['verdict_distribution']={k:int(v) for k,v in D['verdict_distribution'].items()}; D['verdict_file_rows']={k:int(v) for k,v in D['verdict_file_rows'].items()}; D['reason_counts']={k:int(v) for k,v in D['reason_counts'].items()}
H=json.load(open('out/full/headline.json')); H['verdicts']=D; json.dump(H,open('out/full/headline.json','w'),indent=1,default=str)
print(json.dumps(D,indent=1))

# white-hat security tag (label only; verdicts unchanged): rebuild tags from this output, then add columns to verdicts_compact.parquet
import white_hat; white_hat.main(); white_hat.apply()
