---
language:
  - en
license: cc-by-4.0
task_categories:
  - text-classification
  - text-retrieval
pretty_name: Skill Atlas
tags:
  - agents
  - skills
  - skill-md
  - verdicts
  - near-duplicates
size_categories:
  - 1M<n<10M
---

# Skill Atlas

Verdicts, copy groups and a search index for about **1.9 million** public agent skills (`SKILL.md` files on GitHub).

This dataset is derived from **[GitSkills](https://huggingface.co/datasets/mvaccargiu/gitskills)** ([Destefanis et al., arXiv 2608.10906](https://arxiv.org/abs/2608.10906)), shared under **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**. Please credit GitSkills if you use these files. The Skill Atlas code is MIT, at [0xQuez/skill-atlas](https://github.com/0xQuez/skill-atlas).

Skill Atlas answers one question for each skill: **is this worth using?** Each row has a verdict (`use`, `caution` or `ignore`), reasons, a pointer to the original version of a near-copy, slop and risk flags, and a white-hat tag for legitimate security tools.

It **filters out bad options**. It does not yet find better ones. In a 60-task test, near-duplicate picks in an agent's top 5 dropped from 26% to under 1%, with no loss in relevance. See the repo's `eval/README.md`.

## What's in this dataset

| File | Role |
|---|---|
| `verdicts_compact.parquet` | One row per distinct skill (1,877,981). The main table. Descriptions are included; full skill bodies are not (those stay on GitHub). |
| `search_api.parquet` | Same skills plus a normalised search string (`hay`, `name_n`, `repo_n`) and rank `rk`. Used by the JSON API and MCP server. |
| `search_index.parquet` | Smaller search columns for the website (DuckDB-WASM). |
| `skill_details.parquet` | Card fields for the website, sorted by `skill_id` with small row groups so the browser can fetch one skill without reading the whole file. |
| `headline.json` | Snapshot totals used by `/stats` and the Overview page. |
| `white_hat_stats.json` | White-hat tagging counts and the hand-check note. |
| `slop_criteria.json` | The three slop rules and the owner exemptions. |
| `malicious_source_stats.json` | Counts for the known-harmful-collection list. |
| `risk_v2_stats.json` | Risk v2 counts and the precision note. |
| `verdict_shift_v1_v2.json` | How verdicts changed between v1 and v2. |
| `ingest_stats.json`, `refine_pairs_stats.json` | Pipeline counts. |
| `label_translation.csv`, `label_before.csv`, `label_after.csv` | Hand labels for near-copy and translation checks. |

Embeddings, MinHash signatures, the full DuckDB database and other internal intermediates are **not** included. They are large and only needed to rebuild the atlas from scratch (see the git repo).

## Verdicts

| Verdict | Meaning |
|---|---|
| `use` | Fine to use. |
| `caution` | Read the reasons first (medium risk or rough quality). |
| `ignore` | A copy, slop-skill, junk, or danger. If it is a copy, use `canonical_id` instead. |

Counts in this snapshot: **use** 1,163,380; **caution** 139,907; **ignore** 574,694.

Common `reasons` (a skill can have several):

- `near_copy_of:<id>` — a copy; use skill `<id>`
- `renamed_copy` — a copy published under a different name
- `slop_skill` — one of many template look-alikes from one account
- `known_malicious_source` — from a collection of deliberately harmful test skills, or a copy of the harmful part
- `risk_high` / `risk_medium` / `risk_flag:<flag>` — danger heuristics
- `quality_low` / `quality_medium` / `invalid_frontmatter` — thin or rough
- `junk:*` — empty, a redirect, or too short
- `translated_copy_of:<id>` — a translation; information only, does not change the verdict

`canonical_id` is the original (best) version in the same copy group and name. Known-malicious skills are never chosen as the original. If every member is known-malicious, `canonical_id` is null.

## Slop-skills

A slop-skill is one of many look-alike skills mass-produced by one account from a template. Three rules (see `slop_criteria.json`): a huge near-copy cluster dominated by one owner; numbered templated names from an owner who has many of them; or a mass of unnamed skills from one owner. They stay in the dataset and in search; they are tagged, not removed. `Klotzkette` and `membranedev` are exempt (deliberate templated collections).

## White-hat security tools

`white_hat` marks legitimate offensive-security, pentest, CTF, forensics or malware-analysis tools. They do dangerous things on purpose. Use them only for security work you're allowed to do. The tag never changes the verdict or the risk score.

- 13,981 skills in about 1,900 repos (`white_hat_kind` is `offensive` or `forensics`; `category` is `white_hat_security`)
- In a hand check of 40 tagged skills, 36 were real security tools, 2 were wrong and 2 were unclear
- Real toolkits such as AeonDave/malskill are tagged white-hat; they are not on the harmful-collection list

## Columns (`verdicts_compact.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `skill_id` | int | Stable id for this distinct content |
| `canonical_id` | int or null | Id of the original in this name group |
| `file_sha` | string | Content hash from GitSkills |
| `name`, `description` | string | From the skill front matter (description may be truncated) |
| `rep_repo`, `rep_path` | string | The GitSkills representative copy |
| `github_url` | string | Link to that copy on GitHub |
| `top_repo` | string | Most-starred repo that holds this exact content |
| `license` | string | Declared license of the representative repo, if any |
| `max_stars`, `n_files`, `n_repos` | int | Popularity and how widely the text is copied |
| `cluster_id`, `cluster_size` | int | Near-copy family |
| `name_key` | string | Normalised name used to pick the original |
| `is_canonical` | bool | This row is the original for its (family, name) |
| `family_canonical_id` | int | Family-level original (fallback) |
| `canon_basis` | string | Which rule picked the original |
| `renamed_copy` | bool | Same text, different name |
| `origin_date` | timestamp | Best-effort date from the snapshot (often unreliable) |
| `quality`, `risk` | int | Heuristic scores, 0–100-ish |
| `risk_flags` | string | Comma-separated flag names |
| `slop_skill`, `slop_reasons` | bool, string | Slop tag and evidence |
| `verdict`, `reasons` | string, JSON | The verdict and machine-readable reasons |
| `white_hat`, `white_hat_kind`, `category` | bool, string, string | White-hat tag |

`search_api.parquet` adds `name_n`, `repo_n`, `hay` (normalised search text) and `rk` (rank). The two website files are column subsets, optimised for browser range requests.

## Known limitations

- Verdicts come from rules, not from a person reading each skill. They catch a lot, but not everything.
- A high risk score means "read this before you run it". It does not prove the skill is harmful. **Risk-flag precision:** of 370 skills newly marked high-risk in v2, 289 were in known harmful collections. In a hand review of 30 of the other 81, only 3 really sent secrets or keys to an unvetted host; 14 were offensive-security or CTF notes with live attack commands, 11 were ordinary skills with a hard-coded server IP, and 2 were pattern mistakes.
- The atlas cannot tell when a skill only works inside one project.
- Origin dates in the snapshot are unreliable, so the original is picked by stars first, then date.
- This is a snapshot. Some GitHub repos have changed or gone since.
- Near-copy detection can still miss or over-link a few cases (letter-suffixed template siblings, shared banners, same-author rewrites).

## License and attribution

These files are licensed under **CC BY 4.0**, as a work based on GitSkills. Please cite:

- Destefanis et al., *GitSkills*, arXiv [2608.10906](https://arxiv.org/abs/2608.10906), [Hugging Face dataset](https://huggingface.co/datasets/mvaccargiu/gitskills)
- Skill Atlas, https://github.com/0xQuez/skill-atlas

Skill *contents* remain under each file's own license. Many source repos declare none. This dataset links to GitHub rather than re-hosting full skill bodies.
