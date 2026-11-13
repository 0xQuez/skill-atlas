---
title: Eval
toc: false
---

# Can an agent pick better skills using the atlas?

```js
import {n, pct} from "./components/fmt.js";
const E = FileAttachment("data/eval.json").json();
const tasks = FileAttachment("data/eval_tasks.csv").csv();
```

```js
const M = E.metrics, J = E.judged.metrics, S = E.safety.arms, V = E.v1_vs_v2;
const per100 = (x) => Math.round(100 * x);
const LABEL = {B0_bm25_files: "Plain search, every file", B1_bm25: "Plain search", B2_bm25_stars: "Plain search, most stars", A1_atlas_bm25: "Atlas + plain search", A2_atlas_stars: "Atlas + most stars", A3_atlas_api: "Atlas search (API)"};
const ARMS = Object.keys(LABEL);
```

<div class="card answer">
  <h2>Short answer</h2>
  <p class="big">Yes, for avoiding bad picks. With the atlas, an agent's top 5 picks almost never repeat the same skill, it sees more real choices, and it no longer picks skills from known harmful collections. The picks are about as relevant as without the atlas. The atlas filters out bad options; it doesn't yet find better ones.</p>
</div>

## What we found

<div class="grid grid-cols-2">
  <div class="card"><h2>1. Far fewer duplicates</h2><div class="kpi">${per100(M.B0_bm25_files.text_dup_of_earlier.mean)} → ${per100(M.A1_atlas_bm25.text_dup_of_earlier.mean)}</div><div class="kpi-sub">out of 100 picks were copies of a skill already picked, with plain file search vs with the atlas.</div></div>
  <div class="card"><h2>2. More real choices</h2><div class="kpi">${M.B0_bm25_files.distinct_options.mean.toFixed(1)} → ${M.A1_atlas_bm25.distinct_options.mean.toFixed(1)}</div><div class="kpi-sub">different skills in the top 5 (plain search that also skips exact copies: ${M.B1_bm25.distinct_options.mean.toFixed(1)}).</div></div>
  <div class="card"><h2>3. No picks from harmful collections</h2><div class="kpi">${S.B1_bm25.unsafe.v2.picks} → ${S.A1_atlas_bm25.unsafe.v2.picks}</div><div class="kpi-sub">out of ${S.B1_bm25.unsafe.v2.of} picks came from known harmful collections or were high risk, plain search vs atlas. Before this week's fixes the atlas still picked ${S.A1_atlas_bm25.unsafe.v1.picks}.</div></div>
  <div class="card"><h2>4. Same relevance</h2><div class="kpi">${pct(100*J.B1_bm25.relevant.mean, 0)} → ${pct(100*J.A1_atlas_bm25.relevant.mean, 0)}</div><div class="kpi-sub">of picks fit the task in a blind check. Picks that fit well <i>and</i> are reusable: ${pct(100*J.B1_bm25.good.mean, 0)} → ${pct(100*J.A1_atlas_bm25.good.mean, 0)}, too small a gap to be sure.</div></div>
</div>

<p class="muted">The atlas's own search (the API agents call) used to return nothing for ${V.A3_atlas_api.empty_tasks[0]} of ${E.design.n_tasks} searches, because it needed the exact phrase. Now every word just has to appear, and it returned results for all ${E.design.n_tasks}. Its picks fit the task ${pct(100*J.A3_atlas_api.relevant.mean, 0)} of the time, and ${pct(100*J.A3_atlas_api.good.mean, 0)} were good picks, vs ${pct(100*J.B1_bm25.good.mean, 0)} for plain search.</p>

```js
const dupRows = ARMS.map((a) => ({arm: LABEL[a], atlas: a.startsWith("A") ? "with atlas" : "without atlas", v: 100 * M[a].text_dup_of_earlier.mean}));
const safeRows = ARMS.flatMap((a) => [{arm: LABEL[a], when: "before fixes", v: S[a].unsafe.v1.picks}, {arm: LABEL[a], when: "after fixes", v: S[a].unsafe.v2.picks}]);
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Duplicate picks, out of 100</h2>
    ${resize((width) => Plot.plot({width, height: 230, marginLeft: 160, marginRight: 40, x: {label: "duplicate picks per 100", grid: true, domain: [0, 30]}, y: {label: null, domain: dupRows.map((d) => d.arm)},
      color: {domain: ["without atlas", "with atlas"], range: ["#9aa5b1", "#6c5ce7"], legend: true},
      marks: [Plot.barX(dupRows, {x: "v", y: "arm", fill: "atlas"}), Plot.text(dupRows, {x: "v", y: "arm", text: (d) => d.v.toFixed(0), dx: 4, textAnchor: "start"})]}))}
  </div>
  <div class="card">
    <h2>Picks from harmful collections or high risk, out of 300</h2>
    ${resize((width) => Plot.plot({width, height: 230, marginLeft: 160, marginRight: 40, x: {label: "picks", grid: true, domain: [0, 10]}, y: {label: null, domain: ARMS.map((a) => LABEL[a])}, fy: {axis: null, domain: ["before fixes", "after fixes"]},
      color: {domain: ["before fixes", "after fixes"], range: ["#e2a400", "#22a06b"], legend: true},
      marks: [Plot.barX(safeRows, {x: "v", y: "arm", fill: "when", fy: "when", fillOpacity: 0.9}), Plot.text(safeRows, {x: "v", y: "arm", fy: "when", text: (d) => d.v, dx: 4, textAnchor: "start"})]}))}
    <p class="muted">Both counts use today's labels, so the change shows what the atlas now avoids, not a change of yardstick. Plain search has no atlas, so it doesn't change.</p>
  </div>
</div>

## What the atlas doesn't do yet

- **It can't tell if a skill only works in one project.** That was the most common problem in the blind check. Skills marked <i>use</i> were judged reusable ${pct(100*E.label_validity.ok_rate_by_verdict.use.ok_rate, 0)} of the time, about the same as skills marked <i>ignore</i> (${pct(100*E.label_validity.ok_rate_by_verdict.ignore.ok_rate, 0)}, mostly good skills that are copies).
- **It doesn't rank by how well a skill fits the task.** It removes copies, slop and danger from whatever the search found.
- **Its risk rules are rough outside known harmful collections.** In a hand check of 30 newly high-risk skills outside those collections, only 3 really sent secrets or keys somewhere unvetted. Most were security-testing notes or skills with a hard-coded server address.
- **Security-tool collections are not flagged as harmful.** For example AeonDave/malskill is an offensive-security toolkit, not a set of booby-trapped skills, so it keeps normal verdicts.

## Honest caveats

- **One judge, not people.** The blind checks were done by the AI assistant that ran the eval, without seeing which method picked what. ${n(E.judged.n_items)} judgments over ${E.judged.n_tasks} tasks. The ${54} judgments added after the rerun were blind to method, but the judge knew they came from the rerun.
- **Small test.** ${E.design.n_tasks} tasks, 5 picks each. The ranges in "How we measured this" show how sure we are.
- **Some numbers are circular.** The atlas scores 0 "bad" picks by its own labels because it filters on those labels. We don't count that as a win; findings 1, 2 and 4 don't use atlas labels.
- **Finding 3 is a safety check we added after spotting the problem.** It's a fair before/after, but it wasn't planned at the start.

<details class="method">
<summary><b>How we measured this</b></summary>

```js
const ci = (o, s = 100, d = 1) => `${(s*o.mean).toFixed(d)} [${(s*o.ci95[0]).toFixed(d)}, ${(s*o.ci95[1]).toFixed(d)}]`;
const d0 = E.paired_diff["A1_atlas_bm25-B0_bm25_files"], d1 = E.paired_diff["A1_atlas_bm25-B1_bm25"], jd = E.judged.paired_diff["A1_atlas_bm25-B1_bm25"], j3 = E.judged.paired_diff["A3_atlas_api-B1_bm25"], sd = E.safety.paired_v2.unsafe["A1_atlas_bm25-B1_bm25"];
display(html`<ul>
<li>${n(E.design.n_tasks)} pre-registered tasks (${E.design.strata.popular} popular, ${E.design.strata.niche} niche), top-${E.design.k} picks per method over ${n(E.design.corpus_distinct_contents)} distinct skills. Deterministic; no LLM API. 95% ranges: ${E.design.bootstrap}.</li>
<li>Methods: B0 BM25 at file level (exact copies are separate hits); B1 BM25 over name + description; B2 all terms, sorted by stars; A1/A2 the atlas policy on B1/B2 candidates (follow canonical, drop ignore, dedupe, use first); A3 the shipped API with verdict=use.</li>
<li>Duplicate = word 5-shingle Jaccard ≥ 0.5 with an earlier pick (raw text, independent of atlas labels). A1 − B0: ${ci(d0.text_dup_of_earlier)} points; A1 − B1: ${ci(d1.text_dup_of_earlier)}. Distinct options A1 − B0: +${d0.distinct_options.mean.toFixed(2)} [${d0.distinct_options.ci95.map((x) => x.toFixed(2)).join(", ")}].</li>
<li>Unsafe = in out/full/malicious_source.parquet or risk v2 ≥ 40, applied to old and new picks alike. A1 − B1 after fixes: ${ci(sd)} points.</li>
<li>Blind judging: 24 tasks (seed 7), top-3 picks; rel 0/1/2, ok 0/1; good = rel 2 and ok 1. A1 − B1 relevant ${ci(jd.relevant)}, good ${ci(jd.good)}. A3 − B1 good ${ci(j3.good)}.</li>
<li>Files: <code>eval/README.md</code>, <code>eval/results.json</code>, <code>eval/safety.json</code>; old run in <code>eval/v1/</code>.</li>
</ul>`);
```

```js
display(Inputs.table(ARMS.map((a) => ({method: LABEL[a], "duplicates /100": (100*M[a].text_dup_of_earlier.mean).toFixed(1), "different in top 5": M[a].distinct_options.mean.toFixed(2), "unsafe picks before → after": `${S[a].unsafe.v1.picks} → ${S[a].unsafe.v2.picks}`, "empty searches before → after": `${V[a].empty_tasks[0]} → ${V[a].empty_tasks[1]}`, "fit the task": pct(100*J[a].relevant.mean, 0), "good picks": pct(100*J[a].good.mean, 0)})), {layout: "auto"}));
display(Inputs.table(tasks, {columns: ["task_id", "stratum", "need", "query"], rows: 10, layout: "auto"}));
```

</details>
