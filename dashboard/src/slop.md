---
title: Slop-skills
toc: false
---

# Slop-skills

```js
import {n, pct, short} from "./components/fmt.js";
const sl = FileAttachment("data/slop.json").json();
const ov = FileAttachment("data/overview.json").json();
```

<p class="muted">A <b>slop-skill</b> is one of many look-alike skills mass-produced by one account from a template. We mark them <i>ignore</i>, but we never hide them. Search can include them, leave them out, or show only them.</p>

<div class="grid grid-cols-4">
  <div class="card"><h2>Slop-skills found</h2><div class="kpi" style="color:#7a5af8">${n(sl.rules.n)}</div><div class="kpi-sub">from ${n(sl.flagged_rep_owners)} accounts in ${n(sl.flagged_rep_repos)} repos</div></div>
  <div class="card"><h2>Rule 1: one account, one big group</h2><div class="kpi">${n(sl.rules.r1)}</div><div class="kpi-sub">one account publishes many versions of the same skill</div></div>
  <div class="card"><h2>Rule 2: numbered names</h2><div class="kpi">${n(sl.rules.r2)}</div><div class="kpi-sub">names like skill-001, skill-002 from one template</div></div>
  <div class="card"><h2>Rule 3: unnamed in bulk</h2><div class="kpi">${n(sl.rules.r3)}</div><div class="kpi-sub">huge batches of skills with no name</div></div>
</div>

<p class="muted">A skill can break more than one rule, so the three rule counts add up to more than the total.</p>

```js
const owners = sl.owners.slice(0, 20);
const rr = owners.flatMap((d) => [["rule 1", d.r1], ["rule 2", d.r2], ["rule 3", d.r3]].map(([rule, v]) => ({owner: d.owner, rule, v})));
const ws = [
  {metric: "skills that are near-copies", with: ov.slop.with.near_copy_rate_distinct_pct, without: ov.slop.without.near_copy_rate_distinct_pct},
  {metric: "files that are copies", with: ov.slop.with.file_rows_redundant_pct_exact_or_near, without: ov.slop.without.file_rows_redundant_pct_exact_or_near}
].flatMap((d) => [{metric: d.metric, set: "with slop", v: d.with}, {metric: d.metric, set: "without slop", v: d.without}]);
```

<div class="grid grid-cols-3">
  <div class="card grid-colspan-2">
    <h2>Accounts with the most slop-skills</h2>
    ${resize((width) => Plot.plot({width, height: 520, marginLeft: 170, marginRight: 60, x: {type: "log", label: "skills", grid: true, ticks: [1, 10, 100, 1000, 10000, 100000], tickFormat: short}, y: {label: null, domain: owners.map((d) => d.owner)}, color: {legend: true, domain: ["rule 1","rule 2","rule 3"], range: ["#7a5af8","#00b8d9","#e2a400"]},
      marks: [Plot.barX(owners, {x1: 1, x2: "n", y: "owner", fill: "var(--theme-foreground-faintest)"}),
              Plot.dot(rr.filter((d) => d.v > 0), {x: "v", y: "owner", fill: "rule", r: 5, tip: true}),
              Plot.text(owners, {x: "n", y: "owner", text: (d) => short(d.n), dx: 6, textAnchor: "start", fontSize: 10})]}))}
  </div>
  <div class="card">
    <h2>How much slop inflates the copy numbers</h2>
    ${resize((width) => Plot.plot({width, height: 260, marginLeft: 10, marginRight: 50, x: {label: "%", domain: [0, 70], grid: true}, fy: {label: null}, y: {axis: null}, color: {domain: ["with slop","without slop"], range: ["#7a5af8","#00b8d9"], legend: true},
      marks: [Plot.barX(ws, {x: "v", y: "set", fy: "metric", fill: "set"}), Plot.text(ws, {x: "v", y: "set", fy: "metric", text: (d) => pct(d.v, 1), dx: 4, textAnchor: "start"}), Plot.axisFy({anchor: "left", dx: 10, textAnchor: "start", frameAnchor: "top", dy: -14, label: null})]}))}
    <p class="muted">The biggest group of copies has ${n(ov.slop.with.largest_cluster)} versions with slop and ${n(ov.slop.without.largest_cluster)} without.</p>
  </div>
</div>

<div class="card" style="border-left:4px solid #22a06b">
  <h2>Exceptions</h2>
  <p>We don't count <b>${sl.criteria.exempt_owners.join(" and ")}</b> as slop (${sl.criteria.exemption_reason}). Their skills still get checked for copies, quality and risk.</p>
  ${Inputs.table(sl.exempt, {columns: ["owner", "n", "files", "max_cluster", "use_n"], header: {n: "skills", max_cluster: "biggest group", use_n: "marked use"}, layout: "auto"})}
</div>

## All accounts with slop-skills

```js
display(Inputs.table(sl.owners, {columns: ["owner", "n", "files", "repos", "r1", "r2", "r3", "example"], header: {n: "slop-skills", r1: "rule 1", r2: "rule 2", r3: "rule 3", example: "example evidence"}, layout: "auto", rows: 15, width: {example: 520},
  format: {example: (v) => html`<span class="muted">${v}</span>`, owner: (v) => html`<a href="https://github.com/${v}" target="_blank" rel="noopener">${v}</a>`}}));
```
