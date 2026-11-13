---
title: Skill Atlas API
emoji: 🗺️
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 6.31.0
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
short_description: Search API and MCP tools for agent skill verdicts
startup_duration_timeout: 30m
---

# Skill Atlas API

Read-only JSON API and MCP (streamable HTTP at `/mcp`) over the Skill Atlas verdicts.

This Space runs on Gradio + ZeroGPU (CPU only; the GPU is unused) because Docker Spaces need a paid Hugging Face plan. Data is baked into the Space so it can start without a token. Built on [GitSkills](https://huggingface.co/datasets/mvaccargiu/gitskills) (Destefanis et al., arXiv 2608.10906), CC BY 4.0.

## Endpoints

- `GET /healthz` — liveness
- `GET /stats` — headline numbers
- `GET /skills/search?q=&verdict=&slop=&white_hat=&limit=`
- `GET /skills/{id}/verdict`
- `GET /skills/{id}/canonical`
- `POST /mcp` — MCP tools `search_skills`, `get_skill_verdict`, `find_canonical`

There are no write endpoints. Request bodies are capped. A simple per-IP rate limit is on by default (60 requests per minute). CORS defaults to `*`.

Code: [0xQuez/skill-atlas](https://github.com/0xQuez/skill-atlas).
