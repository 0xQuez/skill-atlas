---
title: Skill Atlas API
emoji: 🗺️
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Search API and MCP tools for agent skill verdicts
suggested_hardware: cpu-basic
---

# Skill Atlas API

Read-only JSON API and MCP (streamable HTTP at `/mcp`) over the Skill Atlas verdicts.

Data is pulled from the Hugging Face dataset (`SKILL_ATLAS_DATASET`, default `HF_USER/skill-atlas`) at startup, unless the Parquet files are already in `/data`. Built on [GitSkills](https://huggingface.co/datasets/mvaccargiu/gitskills) (Destefanis et al., arXiv 2608.10906), CC BY 4.0.

## Endpoints

- `GET /healthz` — liveness
- `GET /stats` — headline numbers
- `GET /skills/search?q=&verdict=&slop=&white_hat=&limit=`
- `GET /skills/{id}/verdict`
- `GET /skills/{id}/canonical`
- `POST /mcp` — MCP tools `search_skills`, `get_skill_verdict`, `find_canonical`

There are no write endpoints. Request bodies are capped (`MAX_REQUEST_BODY`, default 1 MB). A simple per-IP rate limit is on by default (`RATE_LIMIT_PER_MIN`, default 60). CORS defaults to `*`. The service checks the `Host` header against `HOST` / `SPACE_HOST` / `ALLOWED_HOSTS`.

## Environment

| Variable | Purpose |
|---|---|
| `SKILL_ATLAS_DATASET` | Hugging Face dataset id (`user/skill-atlas`) |
| `SKILL_ATLAS_DATA_DIR` | Where to store or find the Parquet files (default `/data`) |
| `HOST` / `SPACE_HOST` / `ALLOWED_HOSTS` | Allowed Host headers |
| `CORS_ORIGINS` | Default `*` |
| `RATE_LIMIT_PER_MIN` | Default `60` |
| `DUCKDB_MEMORY` | Default `1GB` |
| `MAX_REQUEST_BODY` | Default `1048576` |
| `HF_TOKEN` | Needed only if the dataset repo is private |

Code: [0xQuez/skill-atlas](https://github.com/0xQuez/skill-atlas).
