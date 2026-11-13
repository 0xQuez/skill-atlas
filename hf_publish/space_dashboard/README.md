---
title: Skill Atlas
emoji: 🗺️
colorFrom: purple
colorTo: cyan
sdk: static
pinned: false
license: mit
short_description: Which agent skills are worth using
---

# Skill Atlas

A website for searching and judging public agent skills (`SKILL.md` files). Built on [GitSkills](https://huggingface.co/datasets/mvaccargiu/gitskills) (Destefanis et al., [arXiv 2608.10906](https://arxiv.org/abs/2608.10906)), CC BY 4.0.

The large search tables (`search_index.parquet`, `skill_details.parquet`) are **not** bundled here. The site fetches them from the Skill Atlas dataset (`parquet_base` in `data/config.json`) so this Space stays small. Hugging Face dataset file URLs support HTTP Range, which the in-browser DuckDB needs.

## Large files

Hugging Face Spaces rejects ordinary git files over 10 MB; those must use Git LFS or Xet. After a production build, these bundled files are typically over that limit even with the Parquet files moved out:

- `_npm/@duckdb/duckdb-wasm@*/dist/duckdb-eh.wasm` (~36 MB)
- `_npm/@duckdb/duckdb-wasm@*/dist/duckdb-mvp.wasm` (~41 MB)

`publish.sh` uploads them with `huggingface_hub`, which uses Xet/LFS automatically. If you upload by hand, enable LFS for `*.wasm` first. Other wasm files (parquet extension, parquet-wasm) may also be over or near 10 MB; the script prints a size report before upload.

Code: [0xQuez/skill-atlas](https://github.com/0xQuez/skill-atlas).
