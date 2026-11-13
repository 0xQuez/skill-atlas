---
title: For agents
---

# For agents

<div class="card" style="border-left:4px solid #e2a400">
<b>API address.</b> Locally the service is at <code>http://127.0.0.1:8765</code>. The hosted endpoint will be at <code>HOSTED_API_URL</code> (coming soon).
</div>

Agents can ask Skill Atlas about a skill before they install it or follow it. Three steps:

1. **Search** for what the skill should do.
2. **Read the verdict.** `use` means go ahead. `caution` means read the reasons first. `ignore` means don't use this one.
3. **If it's a copy, use the original.** The `canonical_id` field points to it.

Each answer also says why (`reasons`), lists risky patterns (`risk_flags`), says whether it's a slop-skill, and links to GitHub. Security tools carry `category: "white_hat_security"` and a `white_hat_note`: they do dangerous things on purpose, so use them only for security work you're allowed to do. The tag never changes the verdict.

## Search rules

Every word you type must appear somewhere in the skill's name, its GitHub owner/repo, or the start of its description. Word order doesn't matter. Results show exact owner/repo matches first, then skills with all your words in the name, then `use` before `caution` before `ignore`, then originals before copies, then more GitHub stars. The website search uses the same rules.

## MCP tools

| Tool | What you send | What you get |
|---|---|---|
| `search_skills` | `query`, optional `verdict` (`use`, `caution`, `ignore`), optional `slop` (true/false), optional `white_hat` (`include`, `exclude`, `only`; default `include`), `limit` (default 10, max 100) | a ranked list of skills |
| `get_skill_verdict` | `skill_id` | one skill: verdict, reasons, scores, link to the original |
| `find_canonical` | `skill_id` | the original version of this skill, or a note that no safe original exists |

### Connect an MCP client

```json
{
  "mcpServers": {
    "skill-atlas": { "url": "http://127.0.0.1:8765/mcp" }
  }
}
```

```python
# pip install "mcp>=2.3"
import asyncio
from mcp import Client

async def main():
    async with Client("http://127.0.0.1:8765/mcp") as c:
        res = await c.call_tool("search_skills", {"query": "terraform module", "verdict": "use", "limit": 3})
        print(res.content[0].text)

asyncio.run(main())
```

## Web API

| Method | Path | Notes |
|---|---|---|
| GET | `/skills/search?q=&verdict=&slop=&white_hat=&limit=` | same rules as above |
| GET | `/skills/{skill_id}/verdict` | one skill |
| GET | `/skills/{skill_id}/canonical` | the original version |
| GET | `/stats` | headline numbers |
| GET | `/healthz` | `{"ok": true}` |

```bash
curl -s "http://127.0.0.1:8765/skills/search?q=react+native+testing&verdict=use&limit=3" | jq '.results[] | {skill_id, name, verdict, github_url}'
```

## What the reasons mean

| Reason | Effect | Meaning |
|---|---|---|
| `known_malicious_source` | ignore | The text comes from a collection of deliberately harmful test skills, or copies its harmful part. |
| `near_copy_of:<id>` | ignore | A copy. Use skill `<id>` instead. |
| `renamed_copy` | ignore | A copy published under a different name. |
| `slop_skill` | ignore | One of many template look-alikes from one account. |
| `risk_high` | ignore | Risk score 40 or more, for example code that reads passwords or keys and sends data out. |
| `quality_low` | ignore | Too thin or broken to be useful. |
| `junk:*` | ignore | Empty, a redirect, or too short. |
| `risk_medium`, `risk_flag:<flag>` | caution | Some risky patterns. Read before running. |
| `quality_medium`, `invalid_frontmatter` | caution | Usable but rough. |
| `translated_copy_of:<id>` | none | A translation of skill `<id>`. For information only. |

### A simple policy for agents

```text
1. search_skills(query, verdict="use") and take the top result.
2. If nothing fits, search without the verdict filter, then call find_canonical on a hit.
3. Never install a skill marked "ignore". For "caution", show the reasons to the user first.
```
