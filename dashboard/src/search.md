---
title: Search
toc: false
---

# Search

<p class="muted">Search all ${n(1877981)} skills. Slop-skills are included and marked, never hidden. Every word you type must appear in the skill's name, its owner/repo, or the start of its description, in any order. Results show exact owner/repo matches first, then skills with all your words in the name, then <i>use</i> before <i>caution</i> before <i>ignore</i>, then originals, then more stars. This is the same search agents get from the API. Tips: <code>owner:anthropics</code> limits to one owner; <code>id:123</code> opens one skill.</p>

```js
import {n, pct, REASON} from "./components/fmt.js";
import {DuckDBClient} from "npm:@observablehq/duckdb";
const cfg = await FileAttachment("data/config.json").json();
const parquetBase = (cfg.parquet_base || "").replace(/\/$/, "");
const idxSrc = parquetBase ? `${parquetBase}/search_index.parquet` : FileAttachment("data/search_index.parquet");
const detSrc = parquetBase ? `${parquetBase}/skill_details.parquet` : FileAttachment("data/skill_details.parquet");
const db = DuckDBClient.of({idx: idxSrc, det: detSrc});
```

```js
const q = view(Inputs.text({label: "Search", placeholder: "terraform module · code review · owner:anthropics · id:590504", value: "terraform module", submit: "Search", width: 520}));
```

<div class="filters">

```js
const verdict = view(Inputs.radio(["any", "use", "caution", "ignore"], {label: "Verdict", value: "any"}));
```

```js
const slop = view(Inputs.radio(["include", "leave out", "only"], {label: "Slop-skills", value: "include"}));
```

```js
const wh = view(Inputs.radio(["include", "leave out", "only"], {label: "Security tools", value: "include"}));
```

```js
const opts = view(Inputs.checkbox(["originals only"], {label: "Options", value: []}));
```

```js
const limit = view(Inputs.select([10, 25, 50], {label: "Show", value: 25}));
```

</div>

```js
// same normalisation as server/build_search.py and the API's tokens()
const SPLIT = /[\s\-_./:,;()\[\]"'`]+/;
const esc = (t) => t.replace(/'/g, "''");
function build(q, verdict, slop, opts, wh = "include") {
  const w = [], toks = [];
  for (const raw of (q || "").toLowerCase().trim().split(/\s+/).filter(Boolean)) {
    if (raw.startsWith("id:") && /^\d+$/.test(raw.slice(3))) w.push(`skill_id = ${raw.slice(3)}`);
    else if (raw.startsWith("owner:") && raw.length > 6) w.push(`starts_with(repo_n, '${esc(raw.slice(6).split(SPLIT).filter(Boolean).join(" "))} ')`);
    else toks.push(...raw.split(SPLIT).filter(Boolean));
  }
  const T = toks.slice(0, 8);
  for (const t of T) w.push(`contains(hay, '${esc(t)}')`);
  if (verdict !== "any") w.push(`verdict = '${verdict}'`);
  if (slop === "leave out") w.push("NOT slop");
  if (slop === "only") w.push("slop");
  if (opts.includes("originals only")) w.push("canon");
  if (wh === "leave out") w.push("NOT wh");
  if (wh === "only") w.push("wh");
  const phrase = esc(T.join(" "));
  const order = T.length ? `ORDER BY (repo_n = '${phrase}') DESC, (${T.map((t) => `contains(name_n, '${esc(t)}')`).join(" AND ")}) DESC, (name_n = '${phrase}') DESC, rk` : "ORDER BY rk";
  return `${w.length ? "WHERE " + w.join(" AND ") : ""} ${order}`;
}
const t0 = performance.now();
const ids = Array.from(await db.query(`SELECT skill_id FROM idx ${build(q, verdict, slop, opts, wh)} LIMIT ${limit}`), (r) => Number(r.skill_id));
// one equality per id (UNION ALL) so DuckDB only fetches the row groups it needs
const point = (cols, list) => list.map((i) => `SELECT ${cols} FROM det WHERE skill_id = ${i}`).join(" UNION ALL ");
const detRows = ids.length ? Array.from(await db.query(point("*", ids))) : [];
const byId = new Map(detRows.map((r) => [Number(r.skill_id), r]));
const canonIds = [...new Set(detRows.map((r) => Number(r.canonical_id)).filter((c) => c && !byId.has(c)))];
const canonRows = canonIds.length ? Array.from(await db.query(point("skill_id, name, top_repo, github_url, verdict", canonIds))) : [];
for (const r of canonRows) byId.set(Number(r.skill_id), r);
const results = ids.map((id) => byId.get(id)).filter(Boolean);
const elapsed = performance.now() - t0;
```

```js
function bar(v, color) { return html`<span class="bar"><span style="width:${Math.max(0, Math.min(100, v ?? 0))}%;background:${color}"></span></span>`; }
function card(r) {
  const id = Number(r.skill_id), cid = r.canonical_id == null ? null : Number(r.canonical_id);
  const canon = cid == null ? null : byId.get(cid);
  let reasons = []; try { reasons = JSON.parse(r.reasons || "[]"); } catch {}
  const flags = (r.risk_flags || "").split(",").filter(Boolean);
  return html`<div class="result">
    <h3><span class="badge ${r.verdict}">${r.verdict}</span>${r.slop_skill ? html`<span class="badge slop">slop-skill</span>` : ""}${r.is_canonical ? html`<span class="badge canon">original</span>` : ""}${r.white_hat ? html`<span class="badge whitehat" title="White-hat security tool: does dangerous things on purpose. Use only for authorised security work.">white hat</span>` : ""}
      <a href="${r.github_url}" target="_blank" rel="noopener">${r.name ?? "(no name)"}</a><span class="meta">#${id}</span></h3>
    <div class="meta">${r.top_repo} · ★ ${n(r.max_stars)} · ${n(r.n_files)} file${Number(r.n_files) === 1 ? "" : "s"} in ${n(r.n_repos)} repo${Number(r.n_repos) === 1 ? "" : "s"}${r.cluster_id != null && Number(r.cluster_id) >= 0 ? ` · ${n(r.cluster_size)} versions in its copy group` : ""}</div>
    ${r.description ? html`<p class="desc">${r.description}</p>` : ""}
    <div class="meta">quality ${bar(r.quality, "#22a06b")} ${r.quality ?? "–"} &nbsp; risk ${bar(r.risk, "#d0454c")} ${r.risk ?? "–"}</div>
    <div style="margin-top:6px">${reasons.length ? reasons.map((x) => html`<span class="chip" title="${x}">${REASON(x)}</span>`) : html`<span class="chip">no problems found</span>`}${flags.map((x) => html`<span class="chip" style="border-color:#d0454c">risk: ${x.replace(/_/g, " ")}</span>`)}</div>
    ${!r.is_canonical && canon ? html`<div class="meta" style="margin-top:6px">→ original: <a href="${canon.github_url}" target="_blank" rel="noopener">${canon.name ?? "(no name)"}</a> in ${canon.top_repo} <span class="badge ${canon.verdict}">${canon.verdict}</span> <span class="meta">#${cid}</span></div>` : ""}
    ${!r.is_canonical && cid == null ? html`<div class="meta" style="margin-top:6px">→ no safe original: every version comes from a harmful-skill collection</div>` : ""}
    ${r.white_hat ? html`<div class="meta" style="margin-top:4px">white hat: a ${r.white_hat_kind === "forensics" ? "forensics" : "hacking-test"} tool that does dangerous things on purpose. Use it only for security work you're allowed to do. <a href="./security">More</a></div>` : ""}
    ${r.slop_skill && r.slop_reasons ? html`<div class="meta" style="margin-top:4px">why slop: ${r.slop_reasons}</div>` : ""}
  </div>`;
}
display(html`<p class="muted" id="status" data-q="${q}|${verdict}|${slop}" data-wh="${wh}">${results.length ? `Top ${results.length} result${results.length === 1 ? "" : "s"}` : "No matches"} · ${(elapsed / 1000).toFixed(2)} s</p>`);
display(html`<div>${results.map(card)}</div>`);
```
