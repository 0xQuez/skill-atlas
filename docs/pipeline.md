# Skill Atlas pipeline notes

This is the technical log of how the dataset and site were built. For the short version, see the [README](../README.md).

## History and design notes

## Data kickoff notes (Mon Nov 9, 2026)

## Layout
- `sample/` — clone of giuseppedestefanis/gitskills-sample (no LICENSE file in repo)
- `data/agent_skills_sample.db` — unzipped sample SQLite (291 MB)
- `profile_sample.py` — profiling → `out/profile.json` + charts
- `neardup.py [N]` — MinHash (word 5-shingles, J≥0.7) + all-MiniLM-L6-v2 cosine (name+desc+first 1500 chars) → clusters
- `risk.py [N]` — quality/risk heuristic v0 → `out/scores_v0.csv`, `out/scores_v0_summary.json`
- `.venv/` — torch CPU, sentence-transformers, datasketch, duckdb, pandas, matplotlib, pyarrow

Run: `. .venv/bin/activate && python profile_sample.py && python neardup.py 13000 && python risk.py 5000`

## Data source facts
- Sample: 29,786 file rows, 13,000 distinct contents, 11,841 repos, 10,786 owners.
- Sample is the 13,000 *lowest content hashes* → uniform random over distinct contents. Consequence: near-dup families
  are broken up (a skill's near-twins usually aren't in the sample). Near-dup rates in the sample are a LOWER BOUND
  and scale ~quadratically with sample size (5k: 89 pairs; 12.9k: 698 pairs).
- Full set is on Hugging Face as Parquet: `mvaccargiu/gitskills` → artifacts 31 files / 6.45 GB, siblings 45 files / 6.96 GB,
  repos 0.02 GB. Much more practical than the 41 GB Zenodo SQLite. DuckDB can read hf:// parquet directly.

## License
- Zenodo record 21875637 and HF dataset: CC BY 4.0 (attribution required; derived data/dashboards allowed).
- Sample GitHub repo: no license declared.
- Skill *contents* are third-party files; repo licenses in sample: 6,294 of 11,841 repos have no license, 3,654 MIT, 803 Apache-2.0.
  → Publish derived metadata/scores/embeddings/cluster IDs freely (with attribution); link out to GitHub for full text
  rather than re-hosting unlicensed SKILL.md bodies (or only re-host permissively licensed ones).

See the final report in the conversation for the MVP plan.

## Full-scale pipeline (Mon Nov 9, run on the box; 8 vCPU, ~4–11 GB free RAM)
Data: Hugging Face `mvaccargiu/gitskills` (CC BY 4.0). Siblings table NOT downloaded (has_scripts / has_references already in artifacts).

```bash
. .venv/bin/activate     # torch CPU, sentence-transformers, datasketch, duckdb 2.0, pyarrow, faiss-cpu, xxhash
# 0. download artifacts + repos parquet (~6.1 GB, ~70 s)
python -c "from huggingface_hub import snapshot_download as s; s('mvaccargiu/gitskills',repo_type='dataset',local_dir='hf',allow_patterns=['data/artifacts/*','data/repos/*','data/mining_runs/*','README.md','scripts/*'],max_workers=8)"
# 1. DuckDB ingest -> out/full/atlas.duckdb (tables copies, sidmap, skills, repos, maxstars) + skills_meta_raw.parquet + ingest_stats.json (~1 min)
python ingest.py
# 1b. stream representative text of non-junk skills -> out/full/text/part-*.parquet (sid,name,description,content) (~3 min)
python -u export_text.py
# 3a. embeddings, resumable, background (MiniLM-L6-v2, 256 tok, fp16). Pass A = max_stars>=1, pass B = rest. ~150-220 docs/s
EMB_THREADS=5 nohup python -u embed.py > logs/embed.log 2>&1 &
# 3b. MinHash signatures, 64 perms, word 5-shingles, first 10k tokens (~7 min with 3 procs)
MH_PROCS=3 python -u minhash.py
# 3c. LSH (16x4 bands) + verify est. J>=0.7, FAISS IVF kNN cos>=0.95 on whatever embedding shards exist, union-find clusters (~3 min MinHash-only)
python -u cluster.py
# 5. headline numbers -> out/full/headline.json ; inspection + precision check
python headline.py && python inspect_clusters.py
# slop flag -> skills.parquet (slop_skill, slop_reasons) + headline.json["slop"] with/without numbers
python slop.py
# full-scale quality/risk -> scores.parquet (~3 procs)
SC_PROCS=3 python -u score.py
# verdicts + canonical ids -> verdicts.parquet, verdicts_compact.parquet, headline.json["verdicts"]
python verdict.py
# embedding-only near-copy examples
python emb_examples.py
```
Embedding queue (v2): `python prep_embed.py` builds `out/full/embed_queue.parquet` in priority order (tier 1 = MinHash cluster
representatives + skills in any 100+-star repo, tier 2 = other 1+-star, tier 3 = rest); `embed.py` writes a shard per 25k rows.
Order after embeddings grow: cluster.py -> headline.py -> slop.py -> verdict.py.
Rerun `embed.py` to resume (finished shards in out/full/emb/ are skipped), then rerun `cluster.py` + `headline.py` to fold in more embeddings.

Outputs in `out/full/`: `skills.parquet` (meta + cluster_id/cluster_size/embedded, no text), `text/` (full text),
`clusters.parquet`, `pairs.parquet` (sid_a, sid_b, jaccard, cosine), `embeddings.parquet` (sid, fp16[384]; only shards done at cluster time),
`emb/*.npz` (checkpoints), `minhash_sig.npz`, `headline.json`.

Junk filters (applied in order, on distinct contents): empty, one-line symlink-style path, redirect page, <200 chars.
Notes: MinHash with 64 perms is noisy around the threshold — in a 300-pair check, 79.7% had exact Jaccard >=0.7, 99.7% >=0.6, 100% >=0.5.
Largest clusters are machine-generated "skill farms" chained by transitivity (connected components); the dashboard should show
cross-owner families separately from single-repo farms.

## Agent-facing data model (planned surfaces; nothing built or deployed yet)
Every distinct skill (junk and slop included: searchable, never hidden) gets:
- `skill_id` (= `sid`), `canonical_id` (best member of its near-copy family; own id for singletons), `is_canonical`
  Canonical rule v2 (originals over copies): eligible = not slop AND risk < 40 AND quality >= 60 (whole family if none qualify);
  rank by max_stars (most-starred repo holding that exact content), then earliest origin_date, quality, copy count.
  Stars come before date because the dataset has no reliable per-file origin date: `first_commit_at` covers 21% of family members and
  dates the representative copy's path, and repo `created_at` dates the repo (old dotfiles repos won date-first). In a 6-family spot check,
  date-first picked a copy 5 times; stars-first picked mattpocock/skills, garrytan/gstack, ComposioHQ/awesome-claude-skills.
  `github_url` / `top_repo` point at the most-starred repo holding the content, not an arbitrary copy.
  Canonical v3 (per family + name): `cluster_id` is the family id (browse a family by it); `name_key` = lowercase name with
  whitespace/_/-/. runs collapsed to `-`. The v2 rule picks one canonical per (cluster_id, name_key), so `near_copy_of` always points
  to a same-name skill. Unnamed members fall back to the family-level pick (`family_canonical_id`). A name that appears once in a
  family is its own canonical, except when its text is near-identical (MinHash est. Jaccard >= 0.9) to a better-ranked canonical of
  another name in that family: then it is a renamed copy (`near_copy_of:<id>` + `renamed_copy`, e.g. `cli-anything-musescore` ->
  `musescore`). Chains are resolved so every target is itself canonical. `canon_basis` records which case applied.
- `verdict` = use / caution / ignore and `reasons` (JSON list of machine codes, e.g. `["slop_skill","near_copy_of:123"]`)
- `quality`, `risk`, `risk_flags`, `slop_skill`, `slop_reasons` (human-readable evidence)
Verdict rules live in `verdict.py` docstring; slop rules in `slop.py` docstring and `out/full/slop_criteria.json`.
Slop owner exemptions (quez, 2026-11-09): `Klotzkette`, `membranedev` (deliberate templated collections) — `EXEMPT_OWNERS` in slop.py; post_embed.sh reruns slop.py so it always applies.

Exports for a small server: `out/full/verdicts_compact.parquet` (one row per skill, keyed by skill_id + canonical_id, text truncated,
GitHub link instead of full body), `out/full/verdicts.parquet` (full metadata), `out/full/embeddings.parquet` (skill_id, fp16[384]) for semantic search.

Planned surfaces (build + test locally first; deploy ONLY when quez approves):
- **Hosted remote MCP endpoint (streamable HTTP)**, not a local install package. Tools: `search_skills(query, filters)` (keyword +
  embedding search, returns verdicts), `get_skill_verdict(skill_id|github_url|file_sha)`, `find_canonical(skill_id|text)`.
- **JSON API from the same service** (same three operations as REST endpoints).
- **Static Parquet/JSON exports** (the files above) so others can fork without the service.

## MVP plan (draft)
Stack: Python ingest (DuckDB over HF parquet) → Parquet outputs (skills, clusters, scores, embeddings) →
Observable Framework or Streamlit dashboard reading Parquet via DuckDB-WASM; static deploy (GitHub Pages / HF Space).
Views: semantic map (UMAP of embeddings, colored by cluster/score), search (keyword + semantic), duplicate explorer
(cluster → members + diff), quality/risk leaderboard with per-flag evidence, repo/owner pages, "which skill would an agent pick" eval.
Week: Mon data kickoff (done) · Tue full-parquet ingest + filters (valid frontmatter, len>200) · Wed embeddings + clustering at scale ·
Thu risk v1 (+ SkillSpector/agent-scan cross-check) + selection eval · Fri dashboard views · Sat polish, docs, publish Parquet to HF · Sun launch write-up.

## Known heuristic caveats
- `silently` removed from injection regex (742 hits, noise). Remaining injection hits are mostly security-education skills.
- `reads_secrets` (326/5000) catches `.env` and `os.environ` — too broad; needs context in v1.
- Quality score has ~0 correlation with stars (r=0.005) — stars are repo-level, not skill-level.

## Post-embedding watcher
`nohup ./post_embed.sh <embed_pid> > logs/post_embed.log 2>&1 &` waits for embed.py to exit, then runs
cluster.py -> headline.py -> slop.py -> verdict.py -> emb_examples.py -> compare_headlines.py.
MinHash-only outputs are backed up in `out/full/minhash_only/`; the comparison lands in `out/full/headline_compare.json`.

## Local service: JSON API + MCP (run locally; a hosted Space is prepared in `hf_publish/space_api/`)
`server/app.py`: one Starlette app (MCP Python SDK 2.3 `MCPServer`) that queries `out/full/verdicts_compact.parquet`
in place through DuckDB (nothing is loaded into RAM up front). Locally it binds to 127.0.0.1. On a host, set `HOST`, `ALLOWED_HOSTS`, `RATE_LIMIT_PER_MIN` and `CORS_ORIGINS`. Use `DUCKDB_MEMORY=1GB` (256 MB can run out of memory on multi-word search).

```bash
. .venv/bin/activate && cd server
uvicorn app:app --host 127.0.0.1 --port 8765          # env: SKILL_ATLAS_DATA, SKILL_ATLAS_STATS, DUCKDB_MEMORY, DUCKDB_THREADS
python test_mcp.py http://127.0.0.1:8765/mcp           # MCP client smoke test
```
JSON API: `GET /skills/search?q=&verdict=use|caution|ignore&slop=true|false&limit=` (ILIKE over name, description, owner/repo; max 100),
`GET /skills/{id}/verdict`, `GET /skills/{id}/canonical`, `GET /stats`, `GET /healthz`.
MCP (streamable HTTP, stateless, JSON responses) at `/mcp`: tools `search_skills`, `get_skill_verdict`, `find_canonical`.
Every record has: skill_id, canonical_id, is_canonical, verdict, reasons[], quality, risk, risk_flags[], slop_skill, slop_evidence[],
family {cluster_id,size}, github_url, license.

Docker (for a later deploy to HF Spaces / Fly, only when quez approves): from the repo root
`docker build -f server/Dockerfile -t skill-atlas . && docker run --rm -p 127.0.0.1:8765:8765 skill-atlas`.
Known limits: substring search is a full scan (~0.6–1.2 s on 1.88M rows); upgrade to DuckDB FTS or embeddings later.
Families are connected components, so they can contain many distinct template siblings; canonicals are per (family, name) since v3.

## Embedding-pair refinement (v4, 2026-11-09)
Header-heavy 128-token embeddings over-linked template siblings. Pipeline after `embed.py`/`cluster.py`:
1. `embed_body.py` – MiniLM on the body only (frontmatter stripped, body[:1500], max_seq 128) for skills in embedding-only pairs → `out/full/body_emb.npz`.
2. `body_lang.py` – cheap language guess (non-Latin script share >5%, else prose stopword vote with ≥5 hits and 2× margin) → `body_lang.parquet`.
3. `refine_pairs.py` – an embedding-only pair (cos ≥0.95, no MinHash pair) is kept iff NOT a template sibling (names equal after removing digits, both slop, or both unnamed same owner) AND (MinHash J_est ≥0.3 OR body cosine ≥0.95). Pairs with different detected languages become `kind='translation'` (not clustered). Writes `pairs.parquet` with `kind` ∈ minhash | minhash+embedding | embedding | translation | embedding_rejected (rejected/translation kept for audit).
4. `recluster.py` → skills/clusters/headline_clusters; then `headline.py`, `slop.py`, `verdict.py`, `emb_examples.py`, `compare_headlines.py`.
`verdict.py` adds the info reason `translated_copy_of:<skill_id>` on the less-starred side of a translation pair; it does not change the tier.
Hand labels: `out/full/label_before.csv`, `label_after.csv`, `label_translation.csv`. Known residuals: names differing by a letter (plugin-a/plugin-b), shared non-frontmatter banners (CoPaper.AI header), same-author rewrites.

## Dashboard (static)
Observable Framework 1.13 site in `dashboard/`, with views Overview, Search & triage, Copy families, Slop-skills, For agents, and About & methodology. Charts use Observable Plot. Search runs in the browser with DuckDB-WASM, which is self-hosted in `dist/`, so the page makes no CDN calls at runtime.
```bash
cd dashboard
npm install                      # once
npm run data                     # ../.venv python: out/full/* -> src/data/{overview,families,slop}.json + search parquet
npm run build                    # -> dist/
npm run serve                    # http-server dist on http://127.0.0.1:8770 (supports HTTP Range, required for lazy parquet)
node shoot.mjs                   # headless Chrome: load every view, fail on console errors, write screenshots/*.png (SCHEME=dark for dark)
node test_search.mjs             # search smoke test (owner:, verdict/slop filters, id:, no-match)
```
Payloads:
- **Small aggregates:** overview.json, families.json and slop.json total about 0.3 MB and are inlined at build time.
- **Search index (`search_index.parquet`, 78 MB):** holds the lowercase name, owner/repo and the first 100 characters of the description. It's sorted by copy count, so popular matches stop the scan early.
- **Skill details (`skill_details.parquet`, 247 MB):** sorted by skill_id in 2,048-row groups. Each result is fetched with an equality lookup per id (UNION ALL), because an IN-list made duckdb-wasm read the whole file.
- **First search:** the browser downloads about 55 MB in total, mostly the one-time 36 MB DuckDB wasm. The parquet reads are about 15 MB.
- Do not serve `dist/` with `python -m http.server`, because it has no Range support.

## Eval
`eval/` asks whether an agent picks better skills with the atlas than without it. It covers 60 tasks and 6 arms: 3 baselines and 3 atlas arms, with bootstrap CIs and a blind-judged sample. See `eval/README.md` for the method, results and limitations. Reproduce with `cd eval && ../.venv/bin/python run_eval.py && ../.venv/bin/python analyze.py`. The dashboard has an **Eval** page (`/eval`). The local API now runs with `DUCKDB_MEMORY=1GB`, because at 256 MB it hit out-of-memory errors (HTTP 500) on multi-word searches.
