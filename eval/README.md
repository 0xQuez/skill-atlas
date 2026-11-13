# Can an agent pick better skills using the atlas?

**Short answer:** Yes, for avoiding bad picks. With the atlas, an agent's top 5 picks almost never repeat the same skill, it sees more real choices, and it no longer picks skills from known harmful collections. The picks are about as relevant as without the atlas. The atlas filters out bad options; it doesn't yet find better ones.

## What we found (60 tasks, 5 picks each, re-run Nov 10 with the v2 atlas)

1. **Far fewer duplicates.** With plain file search, 26 out of 100 picks were copies of a skill already picked. With the atlas, 1 out of 100.
2. **More real choices.** The top 5 held 3.7 different skills with plain file search and 5.0 with the atlas.
3. **No picks from harmful collections.** Plain search picked 7 out of 300 skills from known harmful collections or with high risk. The atlas picked 0. Before the v2 fixes it picked 5.
4. **Same relevance.** In a blind check, 93% of plain-search picks fit the task, against 94% with the atlas. Good, reusable picks: 40% vs 46%, a gap too small to be sure about.

The atlas's own search API used to return nothing for 15 of 60 searches, because it needed the exact phrase. Now each word just has to appear, and it returned results for all 60 (0 of 60 empty).

## Old vs new run

| | v1 (Nov 9) | v2 (Nov 10) |
|---|---|---|
| Atlas + plain search: duplicates per 100 picks | 0.7 | 1.0 |
| Atlas + plain search: unsafe picks (of 300) | 5 | 0 |
| Atlas + plain search: good picks (judged) | 43.1% | 45.8% |
| Atlas API: empty searches (of 60) | 15 | 0 |
| Atlas API: duplicates per 100 | 2.2 | 0 |
| Atlas API: picks that fit the task / good | 83.3% / 50.0% | 98.6% / 61.1% |
| Plain-search arms (B0, B1, B2) | unchanged | unchanged |

Unsafe means the skill is in `out/full/malicious_source.parquet` or has a v2 risk ≥ 40. The same v2 labels are applied to both runs (`safety.py` → `safety.json`). Atlas vs plain search after the fixes: −2.3 points [−5.0, −0.3].

## What the atlas doesn't do yet

- It can't tell when a skill only works in one project. This was the most common problem in the blind check. Skills marked *use* were judged reusable 66% of the time, and skills marked *ignore* 69% of the time.
- It doesn't rank by fit. It only removes copies, slop and danger from what the search found.
- Its risk rules are rough outside known harmful collections. In a hand check of 30 such newly high-risk skills, 3 really sent secrets somewhere unvetted.

## Honest caveats

- One AI judge (the assistant that ran the eval), not people. The 54 new items judged for v2 (`make_judge_pool_v2.py`, items 221–274) were blind to method, but the judge knew they came from the rerun.
- 60 tasks is a small test. The 95% ranges come from 10,000 bootstrap resamples.
- "Bad picks by atlas labels" is 0% for the atlas by construction, so it's not counted as a win.
- The safety check was added after the problem was found.
- The test is deterministic. No LLM agent is involved.

The v1 files are in `eval/v1/`.

---

# Technical detail


Everything here is local and deterministic. No LLM API is configured on the box, so there is no LLM-agent arm. The relevance and usability judgments were made blind by the AI assistant that ran the eval, not by a human (see Limitations).

## Reproduce
```bash
cd eval
../.venv/bin/python run_eval.py        # ~2 min: BM25 index over 1.88M skills, 6 arms x 60 tasks -> picks.csv, per_task.csv, results_auto.json
../.venv/bin/python make_judge_pool.py # blind pool: 24 tasks x top-3 of every arm -> judge_pool.txt / judge_pool_hidden_key.csv
#   judgments.csv = blind labels for the 275 pooled items (221 v1 + 54 v2 top-up) (rel 0/1/2, ok 0/1, note)
../.venv/bin/python make_judge_pool_v2.py # v2 top-up: unjudged (task, skill) pairs from the rerun
../.venv/bin/python analyze.py         # bootstrap CIs, judged metrics, label validity, malicious-benchmark check -> results.json
../.venv/bin/python safety.py          # unsafe-pick share, v1 vs v2 picks -> safety.json (+ results.json)
```
The A3 arm calls the local API at `127.0.0.1:8765`. That server was restarted with `DUCKDB_MEMORY=1GB`, because at 256 MB it returned HTTP 500 (DuckDB out of memory) on multi-word searches.

## Method
- **Tasks** (`tasks.csv`): 60 realistic agent needs, 30 *popular* (PR review, docx, Playwright, Docker, …) and 30 *niche* (RNA-seq, Verilog, GeoPandas, Kafka, …). Each has a short keyword query, written before any results were seen.
- **Corpus:** all 1,877,981 distinct SKILL.md contents in GitSkills (exact copies collapsed). That's already kinder to the baselines than raw GitHub search, which is why B0 adds the file-level view.
- **Arms** (top-k = 5; every arm uses the same query):

| Arm | Atlas? | How it ranks |
|---|---|---|
| B0 `bm25_files` | no | BM25 over name+description at **file level**: every exact copy is its own hit (like GitHub code search) |
| B1 `bm25` | no | BM25 over name+description, distinct contents |
| B2 `bm25_stars` | no | docs containing all query terms, sorted by stars (GitHub-search-like "most stars") |
| A1 `atlas_bm25` | yes | B1's ranked candidates → `find_canonical` → drop `ignore` → dedupe canonicals → `use` first, then `caution` |
| A2 `atlas_stars` | yes | same atlas policy on B2's candidates |
| A3 `atlas_api` | yes | the shipped `/skills/search?q=…&verdict=use` (substring match on the whole query) |

- **Label-based metrics (circular).** These measure picks with the atlas's own labels: slop-skill, near copy (non-canonical), risky (risk ≥ 40 or a high-weight flag), low quality (< 40), and any of these.
- **Checks that don't use the atlas's verdicts:**
  1. **Raw-text duplicates in the top 5:** a pick counts as a duplicate if its true 5-shingle Jaccard with an earlier pick is ≥ 0.5. *Distinct options* = picks that aren't duplicates. This is a related but separate measurement from the MinHash ≥ 0.7 families.
  2. **Blind judgments:** 221 (task, skill) items from the top 3 of every arm on 24 tasks (12 popular, 12 niche). The judge saw only the need, name, description and the first 600 characters of the body; no repo, stars, arm, verdict or flags. Labels: **rel** (2 directly serves the need, 1 partial, 0 not relevant) and **ok** (substantive, coherent, reusable outside its origin project, nothing suspicious). *Good* = rel 2 and ok.
  3. **Post-hoc safety check:** picks from repos that describe themselves as malicious-skill benchmarks (MalSkillBench, PoisonedSkills, AeonDave/malskill, trailofbits/overtly-malicious-skills).
- **Statistics:** per-task means; 95% percentile bootstrap over tasks (10,000 resamples, seed 20261109), paired for arm-vs-arm differences.

## Results (60 tasks, top 5; v1 numbers, see the table above for v2)

| | B0 files | B1 BM25 | B2 stars | **A1 atlas** | A2 atlas+stars | A3 API |
|---|---|---|---|---|---|---|
| bad by atlas labels (copy/slop/risky/low-q) | 19.7% | 19.3% | 13.7% | **0%** | 0% | 0% |
| raw-text duplicate picks (J ≥ 0.5) | 26.3% | 7.3% | 8.0% | **0.7%** | 1.0% | 2.2% |
| distinct options out of 5 | 3.68 | 4.63 | 4.60 | **4.97** | 4.95 | 4.60* |
| tasks with a full top-5 | 60 | 60 | 60 | 60 | 60 | **40** (15 got 0) |

\*A3 is averaged over the 45 tasks where it returned anything.

**Paired differences, A1 minus baseline (95% CI)**
- **Raw-text duplicates:** −25.7 pts vs B0 [−32.3, −19.7]; −6.7 pts vs B1 [−9.3, −4.3]
- **Distinct options:** +1.28 vs B0 [+0.98, +1.60]; +0.33 vs B1 [+0.22, +0.47]
- **Bad by atlas labels:** −19.3 pts vs B1 [−24.7, −14.7]. Most of this is near copies (−16.3 pts); slop, risky and low quality are each −1.3 pts.
- **Atlas on the stars ranking (A2 vs B2):** bad −13.7 pts [−17.7, −9.7]; duplicates −7.0 pts [−10.3, −4.0]

**Blind judgments (24 tasks, top 3)**

| | B0 | B1 | B2 | A1 | A2 | A3 |
|---|---|---|---|---|---|---|
| relevant (rel ≥ 1) | 90% | 93% | 76% | 94% | 78% | 83% |
| directly relevant (rel 2) | 53% | 53% | 42% | 56% | 38% | 54% |
| usable (ok) | 46% | 50% | 72% | 56% | 71% | 78% |
| good (rel 2 and ok) | 40% | 40% | 42% | 43% | 38% | 50% |
| good, distinct options in top 3 | 1.04 | 1.13 | 1.04 | 1.29 | 1.13 | 1.33 |

- **A1 vs B1:** relevance +1.4 pts [−2.8, +6.9], good +2.8 pts [−4.2, +11.1], usable +5.6 pts [−1.4, +12.5]. No significant difference: the atlas did not cost relevance, and it did not measurably raise judged usefulness.
- **A1 vs B0:** good distinct options +0.25 [0.00, +0.50], borderline.
- **A3 vs B1:** usable +29.6 pts [+7.4, +51.9], but on fewer tasks, because A3 often returns nothing.
- **Do the atlas labels match the blind judgments?** Mostly not:
  - Usable rate was 66% for verdict `use` (n=188) and 71% for `ignore` (n=24). The `ignore` items here are mostly near copies of good skills, so "ignore this copy" ≠ "bad content".
  - The main quality problem the judge saw was **project-locked skills**: tied to one repo, paths or internal tooling. Neither the quality heuristic nor the verdict detects this.

**Safety check (post hoc)**
- The atlas currently labels known malicious-benchmark skills as `use`: MalSkillBench 2,837 of 5,554; PoisonedSkills 1,769 of 4,225; AeonDave/malskill 246 of 259; trailofbits 3 of 3.
- A1 picked them as often as plain BM25 (5 picks each, Δ 0.0 [−1.0, +1.0] pts). One of A1's picks was a PoisonedSkills "AWS IAM Privilege Escalation Scanner" whose body contains covert credential-theft code (verdict `use`, risk 19).
- **Do not claim the atlas makes skill choice safer until this is fixed** (for example, deny-list self-declared malicious benchmarks and their copies, and treat `reads_secrets` + `raw_ip_url` as high-risk).

## Limitations
- **Circularity:** the "0% bad" result holds by construction. The atlas filters on the same labels being scored. Treat it as "the filter works as specified", not as evidence of quality.
- **Judge:** one judge, the AI assistant that ran the eval. It was blind to arm and labels but is not a human expert, labelled from the first 600 characters, and could miss payloads deeper in a file. There's no inter-annotator agreement. 24 tasks / 221 items gives wide CIs.
- **Tasks and queries:** written by the same assistant; keyword queries only, with no query reformulation or browsing as a real agent might do. The niche/popular split is a judgment call.
- **Baselines** run on name+description BM25 over a de-duplicated corpus (B1/B2). Real GitHub search is noisier (B0 is closer). Stars are the most-starred holder's.
- **Shipped API:** A3 uses whole-query substring matching, so 15 of 60 multi-word queries returned nothing. Its search needs token-level matching before launch.
- **The safety check** was added after looking at the picks.
