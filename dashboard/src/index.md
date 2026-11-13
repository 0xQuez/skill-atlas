---
title: Overview
toc: false
---

```js
import {n, pct, short, VCOLORS, REASON} from "./components/fmt.js";
const ov = FileAttachment("data/overview.json").json();
```

```js
const v = ov.verdicts.verdict_distribution;
const vtot = v.use + v.caution + v.ignore;
const s = ov.slop;
const mal = ov.verdicts.reason_counts.known_malicious_source ?? 0;
```

<div class="hero">
  <h1>Which agent skills are worth using?</h1>
  <p>We looked at ${n(ov.artifact_rows)} skill files on GitHub. Most of them are copies. Skill Atlas groups the copies, finds the original, flags junk and danger, and gives every skill a simple verdict: <b>use</b>, <b>caution</b> or <b>ignore</b>.</p>
</div>

<div class="grid grid-cols-4">
  <div class="card"><h2>Skill files</h2><div class="kpi">${short(ov.artifact_rows)}</div><div class="kpi-sub">in ${n(ov.repos)} GitHub repos</div></div>
  <div class="card"><h2>Different skills</h2><div class="kpi">${short(ov.kept)}</div><div class="kpi-sub">after removing exact copies and junk</div></div>
  <div class="card"><h2>Files that are copies</h2><div class="kpi">${pct(ov.file_rows_redundant_pct_exact_or_near, 0)}</div><div class="kpi-sub">exact or near-copies of another skill</div></div>
  <div class="card"><h2>Originals</h2><div class="kpi">${short(ov.verdicts.canonical_count)}</div><div class="kpi-sub">one best version per group of copies</div></div>
</div>

<div class="grid grid-cols-4">
  <div class="card"><h2>Use</h2><div class="kpi" style="color:var(--sa-use)">${short(v.use)}</div><div class="kpi-sub">${pct(100*v.use/vtot, 0)} of skills · fine to use</div></div>
  <div class="card"><h2>Caution</h2><div class="kpi" style="color:var(--sa-caution)">${short(v.caution)}</div><div class="kpi-sub">${pct(100*v.caution/vtot, 0)} · read the reasons first</div></div>
  <div class="card"><h2>Ignore</h2><div class="kpi" style="color:var(--sa-ignore)">${short(v.ignore)}</div><div class="kpi-sub">${pct(100*v.ignore/vtot, 0)} · copies, slop, junk or danger</div></div>
  <div class="card"><h2>From harmful collections</h2><div class="kpi" style="color:var(--sa-ignore)">${short(mal)}</div><div class="kpi-sub">deliberately harmful test skills, marked ignore</div></div>
</div>

<p class="muted">A <b>near-copy</b> is a skill whose text is almost the same as another one, with small edits. A <b>slop-skill</b> is one of many look-alike skills mass-produced by one account from a template. We found ${n(s.flagged_skills)} slop-skills. They stay searchable.</p>

```js
const vRows = ["each skill once", "each file"].flatMap((unit) => {
  const d = unit === "each skill once" ? ov.verdicts.verdict_distribution : ov.verdicts.verdict_file_rows;
  const t = d.use + d.caution + d.ignore;
  return ["use", "caution", "ignore"].map((k) => ({unit, verdict: k, n: d[k], share: d[k] / t}));
});
const hist = Object.entries(ov.cluster_size_hist).map(([size, count]) => ({size, count}));
const reasons = Object.entries(ov.verdicts.reason_counts).filter(([r]) => !r.startsWith("junk:"))
  .map(([reason, count]) => ({reason: REASON(reason), code: reason, count})).sort((a, b) => b.count - a.count).slice(0, 14);
const funnel = [
  {stage: "skill files", n: ov.artifact_rows},
  {stage: "different texts", n: ov.distinct_contents},
  {stage: "minus junk", n: ov.kept},
  {stage: "groups of copies", n: ov.families_after_exact_and_near},
  {stage: "originals", n: ov.verdicts.canonical_count},
  {stage: "verdict: use", n: v.use}
];
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Verdicts</h2>
    ${resize((width) => Plot.plot({width, height: 150, marginLeft: 110, x: {percent: true, label: "share (%)"}, y: {label: null}, color: {...VCOLORS, legend: true},
      marks: [Plot.barX(vRows, Plot.stackX({x: "share", y: "unit", fill: "verdict", order: ["use","caution","ignore"], tip: {format: {share: (d) => (100*d).toFixed(1) + "%", n: (d) => n(d)}}, channels: {n: "n"}})),
              Plot.textX(vRows, Plot.stackX({x: "share", y: "unit", z: "verdict", order: ["use","caution","ignore"], text: (d) => d.share > 0.08 ? `${(100*d.share).toFixed(0)}%` : "", fill: "white", fontWeight: 600}))]}))}
    <p class="muted">Counted per file, more is "ignore", because copied files point to their original.</p>
  </div>
  <div class="card">
    <h2>How big groups of copies get</h2>
    ${resize((width) => Plot.plot({width, height: 240, marginTop: 40, x: {label: "versions in the group", domain: hist.map((d) => d.size)}, y: {type: "log", label: "groups", grid: true, ticks: [1, 10, 100, 1000, 10000, 100000], tickFormat: short},
      marks: [Plot.barY(hist, {x: "size", y1: 1, y2: "count", fill: "var(--sa-accent)", tip: true}), Plot.text(hist, {x: "size", y: "count", text: (d) => short(d.count), dy: -8})]}))}
    <p class="muted">${n(ov.clusters)} groups. The biggest has ${n(ov.largest_cluster)} versions. It's a slop farm.</p>
  </div>
</div>

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Why skills get their verdict</h2>
    ${resize((width) => Plot.plot({width, height: 400, marginLeft: 210, marginRight: 50, x: {label: "skills", grid: true, tickFormat: short}, y: {label: null},
      marks: [Plot.barX(reasons, {x: "count", y: "reason", sort: {y: "-x"}, fill: (d) => d.code.startsWith("risk") || d.code === "known_malicious_source" ? "#d0454c" : d.code.startsWith("quality") ? "#e2a400" : d.code === "slop_skill" ? "#7a5af8" : "#6c8ebf", tip: true}),
              Plot.text(reasons, {x: "count", y: "reason", text: (d) => short(d.count), dx: 4, textAnchor: "start"})]}))}
    <p class="muted">One skill can have several reasons.</p>
  </div>
  <div class="card">
    <h2>From files to recommendations</h2>
    ${resize((width) => Plot.plot({width, height: 400, marginLeft: 130, marginRight: 80, x: {label: null, tickFormat: short, grid: true}, y: {label: null, domain: funnel.map((d) => d.stage)},
      marks: [Plot.barX(funnel, {x: "n", y: "stage", fill: (d, i) => i === 5 ? "#22a06b" : "#6c5ce7", fillOpacity: 0.85, tip: true}), Plot.text(funnel, {x: "n", y: "stage", text: (d) => short(d.n), dx: 4, textAnchor: "start"})]}))}
  </div>
</div>

<p class="muted">Built ${ov.generated}. Technical details are on the <a href="./about">About</a> page.</p>
