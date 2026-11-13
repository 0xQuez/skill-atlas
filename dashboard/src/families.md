---
title: Copies
toc: false
---

# Copies

```js
import {n, pct, short, VCOLORS} from "./components/fmt.js";
const fam = FileAttachment("data/families.json").json();
const ov = FileAttachment("data/overview.json").json();
```

<p class="muted">Many skills are copied from repo to repo, often with small edits. A <b>near-copy</b> is a skill whose text is almost the same as another one. We put copies in a group and pick the <b>original</b>: the best version, usually the one in the most-starred repo. Everything else in the group points to it. If a group has several names, each name gets its own original. Here are the ${fam.length} biggest of ${n(ov.clusters)} groups.</p>

```js
const top = fam.slice(0, 30).map((d) => ({...d, label: `${d.canon_name ?? d.top_names?.[0]?.k ?? "(no name)"}`.slice(0, 38)}));
```

<div class="card">
  <h2>The 30 biggest groups of copies</h2>
  ${resize((width) => Plot.plot({width, height: 640, marginLeft: 250, marginRight: 120, x: {type: "log", label: "versions in the group", grid: true, ticks: [1, 10, 100, 1000, 10000], tickFormat: short}, y: {label: null, domain: top.map((d) => d.label)}, color: {...VCOLORS, legend: true, label: "verdict of the original"},
    marks: [Plot.barX(top, {x1: 1, x2: "size", y: "label", fill: (d) => d.slop_share > 0.5 ? "#7a5af8" : "#9aa5b1", fillOpacity: 0.35}),
            Plot.dot(top, {x: "size", y: "label", r: 4, fill: (d) => d.canon_verdict ?? "ignore", tip: {channels: {owners: "owners", "slop share": (d) => pct(100*d.slop_share, 0), original: "canon_repo"}}}),
            Plot.text(top, {x: "size", y: "label", text: (d) => `${short(d.size)} · ${d.owners} owner${d.owners === 1 ? "" : "s"}`, dx: 8, textAnchor: "start", fontSize: 10})]}))}
  <p class="muted">Purple bars are groups made mostly of slop-skills. The dot shows the verdict of the group's original.</p>
</div>

```js
const search = view(Inputs.search(fam, {placeholder: "Filter by name, repo or owner…", columns: ["canon_name", "canon_repo", "cluster_id"], format: (n) => `${n} groups`}));
```

```js
display(Inputs.table(search.map((d) => ({
  original: d.canon_name ?? "(no name)", url: d.canon_url, repo: d.canon_repo, verdict: d.canon_verdict ?? "none",
  versions: d.size, files: d.files, owners: d.owners, names: d.names, "slop %": Math.round(100 * d.slop_share),
  "top owners": (d.top_owners ?? []).map((o) => `${o.o} (${o.n})`).join(", "), group: d.cluster_id
})), {
  rows: 18, layout: "auto",
  columns: ["original", "repo", "verdict", "versions", "files", "owners", "names", "slop %", "top owners", "group"],
  format: {original: (v, i, data) => html`<a href="${data[i].url}" target="_blank" rel="noopener">${v}</a>`, verdict: (v) => html`<span class="badge ${v}">${v}</span>`, "top owners": (v) => html`<span class="muted">${v}</span>`},
  width: {"top owners": 260}
}));
```
