---
title: About
---

# About Skill Atlas

```js
import {n, pct} from "./components/fmt.js";
const ov = FileAttachment("data/overview.json").json();
```

## What it is

Skill Atlas looks at every public agent skill file (`SKILL.md`) in a large snapshot of GitHub. It answers one question for each skill: **is this worth using?**

It does four things:

1. **Finds copies.** Many skills are copied from repo to repo. We group copies together and pick the original.
2. **Spots slop-skills.** A slop-skill is one of many look-alike skills mass-produced by one account from a template.
3. **Checks for danger.** We look for code that reads passwords or keys and sends them somewhere, for hidden instructions, and for skills that come from collections of deliberately harmful test skills.
4. **Gives a verdict.** Each skill gets `use`, `caution` or `ignore`, with the reasons.

A **near-copy** is a skill whose text is almost the same as another skill, with small edits.

## Where the data comes from

The skills come from **GitSkills** ([mvaccargiu/gitskills](https://huggingface.co/datasets/mvaccargiu/gitskills)), shared under **CC BY 4.0**. Please cite: Destefanis et al., *GitSkills*, arXiv [2608.10906](https://arxiv.org/abs/2608.10906). Our verdicts are built on that data, so the same credit applies. Each skill keeps its own license. Check it on GitHub before you reuse a skill.

## What to keep in mind

- The verdicts come from simple rules, not from a person reading each skill. They catch a lot, but not everything.
- A high risk score means "read this before you run it". It does not prove the skill is harmful.
- The data is a snapshot. Some repos have changed or gone since.
- The atlas can't tell whether a skill only works inside one project. That was the most common problem our reviewer found.

<details class="method">
<summary><b>How we measured this</b> (technical detail)</summary>

```js
const S = ov.safety ?? {};
display(html`<ol>
<li><b>Ingest.</b> ${n(ov.artifact_rows)} SKILL.md files → ${n(ov.distinct_contents)} distinct contents (exact copies collapsed by file hash), from ${n(ov.repos)} repos and ${n(ov.owners)} owners.</li>
<li><b>Junk filter.</b> Under 200 characters, symlinks, redirects and empty files (${n(Object.values(ov.junk_drop_sequential).reduce((a, b) => a + b, 0))} dropped) → ${n(ov.kept)} skills.</li>
<li><b>Near-copy detection.</b> MinHash LSH on word 5-shingles (first 10k tokens, 64 permutations, 16×4 bands), verified at estimated Jaccard ≥ 0.7 (${n(ov.lsh_candidates)} candidates → ${n(ov.minhash_pairs)} pairs). Plus MiniLM-L6-v2 embeddings (FAISS IVF-SQ, cosine ≥ 0.95). An embedding-only pair is kept only if it is not a template sibling and has Jaccard ≥ 0.3 or body cosine ≥ 0.95. Different-language pairs become <code>translated_copy_of</code>. ${n(ov.emb_only_pairs)} embedding pairs kept, ${n(ov.emb_only_rejected)} rejected.${ov.labels.before && ov.labels.after ? ` Hand-checked precision: ${ov.labels.before.true}/${ov.labels.before.n} before the filter, ${ov.labels.after.true}/${ov.labels.after.n} after.` : ""}${ov.labels.translation ? ` Translation tag: ${ov.labels.translation.true}/${ov.labels.translation.n}.` : ""}</li>
<li><b>Copy groups.</b> Union-find over all kept pairs → ${n(ov.clusters)} clusters covering ${n(ov.skills_in_clusters)} skills.</li>
<li><b>Slop-skills.</b> R1 owner farm cluster, R2 templated numbered names, R3 unnamed mass. Klotzkette and membranedev are exempt.</li>
<li><b>Quality and risk.</b> Regex heuristics. Risk v2 adds: <code>secret_access</code> (~/.aws/credentials, ssh keys, keychain, browser cookie and login stores, .netrc, .git-credentials, docker/kube config, full environment dumps), <code>public_raw_ip</code> (URLs to public raw IPs, +20; private and loopback ranges ignored), <code>exfil_endpoint</code> (webhooks, paste sites, tunnels, request bins, +10), <code>post_unknown_host</code>, and <code>secret_exfil_combo</code>: secret access together with any exfiltration signal sets risk to at least 45 (high).${S.risk ? ` ${n(S.risk.newly_high)} skills became high risk; precision on a hand-reviewed sample: ${S.risk.precision}.` : ""}</li>
<li><b>Known malicious sources.</b> Repos that describe themselves as malicious or poisoned skill benchmarks are deny-listed (whole repo, or only their malicious folders or test fixtures). Content also held by an ordinary repo with at least as many stars (and ≥ 5) is exempt, since benchmarks copy real skills as benign controls. Near-copies are flagged only if they carry a line with a strong malicious signal that the original lacks.${S.malicious ? ` ${n(S.malicious.direct)} skills flagged directly, ${n(S.malicious.derived)} as derived copies, ${n(S.malicious.exempt_trusted_copy)} exempted.` : ""}</li>
<li><b>Canonical (the original).</b> One per (cluster, normalised name). Known-malicious members are ranked last and never chosen; if every member is known-malicious, there is no canonical. Then eligible members (not slop, risk &lt; 40, quality ≥ 60) first, ranked by stars, earliest origin date, quality and copy count.</li>
<li><b>Verdict.</b> ignore: junk, known_malicious_source, slop, risk ≥ 40, quality &lt; 40, near copy. caution: risk 20–39, high-weight risk flags, quality 40–59, invalid frontmatter. Otherwise use.</li>
<li><b>Search.</b> Token AND (every word, any order) over a normalised string of name, owner/repo and the first 200 characters of the description. DuckDB's full-text (BM25) extension wasn't available for this DuckDB version, so ranking is rule-based. API and website share one index file.</li>
</ol>`);
```

**Known errors.** 3 of 50 hand-checked embedding pairs were wrong: letter-suffixed template siblings, shared banners before the frontmatter, and same-author rewrites. The translation tag is a cheap script/stop-word test. Origin dates in the snapshot are unreliable, so ranking puts stars first.

</details>
