"""Build out/full/search_api.parquet: one row per skill with a normalised haystack (name + owner/repo + first 200 chars of
description) and a precomputed rank, sorted by that rank so token-AND LIKE scans can stop early. Shared by API and dashboard."""
import duckdb, sys
SRC = sys.argv[1] if len(sys.argv) > 1 else 'out/full/verdicts_compact.parquet'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out/full/search_api.parquet'
NORM = "trim(regexp_replace(lower({}), '[\\s\\-_./:,;()\\[\\]\"''`]+', ' ', 'g'))"
c = duckdb.connect(); c.execute("SET memory_limit='2GB'; SET threads=2; SET temp_directory='out/tmp_duck'")
c.execute(f"""COPY (SELECT skill_id, {NORM.format("coalesce(name,'')")} AS name_n, {NORM.format("coalesce(top_repo,rep_repo,'')")} AS repo_n,
   {NORM.format("coalesce(name,'') || ' ' || coalesce(top_repo,'') || ' ' || coalesce(rep_repo,'') || ' ' || left(coalesce(description,''),200)")} AS hay,
   * EXCLUDE (file_sha, skill_id),
   row_number() OVER (ORDER BY (verdict='use') DESC, (verdict='caution') DESC, is_canonical DESC, max_stars DESC NULLS LAST, skill_id) AS rk
   FROM read_parquet('{SRC}') ORDER BY rk) TO '{OUT}' (FORMAT parquet, ROW_GROUP_SIZE 100000, COMPRESSION zstd)""")
print(c.execute(f"SELECT count(*) FROM read_parquet('{OUT}')").fetchone())
