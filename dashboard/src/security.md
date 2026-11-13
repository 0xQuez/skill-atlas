---
title: Security tools
toc: false
---

# Security tools (white hat)

```js
import {n, pct} from "./components/fmt.js";
const ov = FileAttachment("data/overview.json").json();
```

```js
const W = ov.white_hat;
```

<div class="card answer">
  <p class="big">Some skills are <b>white-hat security tools</b>. They're built for hacking tests, red-team work, capture-the-flag games and malware analysis. They do dangerous things on purpose: scan networks, break logins, run exploits. That's what they're for. Use them only for security work you're allowed to do.</p>
</div>

These are not the same as the [harmful collections](./about). Those are skills built to trick an agent. White-hat tools are honest about what they do.

<div class="grid grid-cols-4">
  <div class="card"><h2>White-hat skills</h2><div class="kpi">${n(W.skills_tagged)}</div><div class="kpi-sub">in ${n(W.repos_with_tagged_skills)} repos</div></div>
  <div class="card"><h2>Attack and testing</h2><div class="kpi">${n(W.by_kind.offensive)}</div><div class="kpi-sub">pentest, red team, CTF, exploits</div></div>
  <div class="card"><h2>Forensics</h2><div class="kpi">${n(W.by_kind.forensics)}</div><div class="kpi-sub">malware analysis, incident evidence</div></div>
  <div class="card"><h2>Checked by hand</h2><div class="kpi">${W.precision.right} of ${W.precision.sample}</div><div class="kpi-sub">random tagged skills really were security tools</div></div>
</div>

## What the tag changes

- **The verdict stays the same.** A white-hat skill can still be <i>use</i>, <i>caution</i> or <i>ignore</i>. Of the tagged skills, ${n(W.verdicts_of_tagged.use)} are <i>use</i>, ${n(W.verdicts_of_tagged.caution)} <i>caution</i> and ${n(W.verdicts_of_tagged.ignore)} <i>ignore</i> (mostly copies).
- **The danger score stays the same.** ${n(W.high_risk_tagged)} of them score high risk, because they really do risky things. The tag explains why.
- **You can filter.** Search has a "Security tools" filter: include, leave out, or only. Agents can pass <code>white_hat=include|exclude|only</code>. Each result says <code>category: "white_hat_security"</code>.

```js
display(Plot.plot({height: 360, marginLeft: 260, marginRight: 50, x: {label: "white-hat skills", grid: true}, y: {label: null},
  marks: [Plot.barX(W.top_repos, {x: "n", y: "repo", fill: "#2f6fd6", sort: {y: "-x"}}), Plot.text(W.top_repos, {x: "n", y: "repo", text: (d) => n(d.n), dx: 4, textAnchor: "start"})]}));
```
<p class="muted">The repos with the most white-hat skills. AeonDave/malskill, an offensive-security toolkit, has ${n(W.curated_counts["AeonDave/malskill"])}.</p>

## What it gets wrong

- **Some misses.** A skill with no name or description, like a bare list of attack payloads, is often not tagged. In our hand check of risky skills, ${W.recall.hit} of ${W.recall.of} hacking notes got the tag.
- **Some wrong tags.** In ${W.precision.sample} random tagged skills, ${W.precision.wrong} weren't security tools and ${W.precision.unclear} were unclear.
- **Defensive work is left out on purpose.** Skills that detect attacks, harden systems or check compliance are not tagged.

<details class="method">
<summary><b>How we measured this</b></summary>

A skill is tagged when (a) its own name or description uses a clear offensive-security term (pentest, red team, CTF, privilege escalation, Metasploit, Burp Suite, Kerberoasting, malware analysis and so on) together with a second security word, or (b) it sits in a white-hat repo and its own text has a security word. White-hat repos: a reviewed list (AeonDave/malskill, grisuno/LazyOwn, dazeb/ai-supply-chain-lab and three SANS "Find Evil" forensics repos), plus ${n(W.white_hat_repos_listed - W.curated.length)} repos whose name or description says red team, pentest, CTF, bug bounty, DFIR and the like. Skills are left out when the name or text is defensive (detect, harden, audit, policy, compliance) without an offensive action, and skills on the harmful-collection list are never tagged. Skills with no name or description are judged on their first 3,000 characters. Code: <code>white_hat.py</code>; output <code>out/full/white_hat.parquet</code> and <code>white_hat_stats.json</code>.

${W.precision.note}

</details>
