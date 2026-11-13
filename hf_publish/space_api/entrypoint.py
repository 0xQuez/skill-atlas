#!/usr/bin/env python3
"""Locate or download Skill Atlas data, then set environment paths.

On Hugging Face Gradio Spaces, /data is often not writable, so we prefer:
  1) files baked into ./data next to this package
  2) a download into /tmp/skill-atlas-data
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = [
    Path(os.environ["SKILL_ATLAS_DATA_DIR"]) if os.environ.get("SKILL_ATLAS_DATA_DIR") else None,
    HERE / "data",
    Path("/tmp/skill-atlas-data"),
]
CANDIDATES = [p for p in CANDIDATES if p is not None]
FILES = ("verdicts_compact.parquet", "search_api.parquet", "headline.json")
REPO = os.environ.get("SKILL_ATLAS_DATASET", "0xQuez/skill-atlas").strip()


def _complete(folder: Path) -> bool:
    return all((folder / name).is_file() for name in FILES)


def ensure_data() -> Path:
    for folder in CANDIDATES:
        if _complete(folder):
            print(f"using existing data in {folder}", flush=True)
            return folder
    dest = Path("/tmp/skill-atlas-data")
    dest.mkdir(parents=True, exist_ok=True)
    if not REPO:
        raise SystemExit("Skill Atlas data files are missing and SKILL_ATLAS_DATASET is not set.")
    from huggingface_hub import hf_hub_download
    for name in FILES:
        if (dest / name).is_file():
            continue
        print(f"downloading {name} from {REPO}", flush=True)
        hf_hub_download(repo_id=REPO, filename=name, repo_type="dataset", local_dir=str(dest))
    if not _complete(dest):
        raise SystemExit(f"data still incomplete in {dest}")
    return dest


def apply_env(folder: Path) -> None:
    os.environ.setdefault("SKILL_ATLAS_DATA", str(folder / "verdicts_compact.parquet"))
    os.environ.setdefault("SKILL_ATLAS_SEARCH", str(folder / "search_api.parquet"))
    os.environ.setdefault("SKILL_ATLAS_STATS", str(folder / "headline.json"))
    if not os.environ.get("HOST") and os.environ.get("SPACE_HOST"):
        os.environ["HOST"] = os.environ["SPACE_HOST"]
    os.environ.setdefault("ATLAS_PRODUCTION", "1")
    os.environ.setdefault("DUCKDB_MEMORY", "1GB")
    os.environ.setdefault("RATE_LIMIT_PER_MIN", "60")


if __name__ == "__main__":
    apply_env(ensure_data())
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("atlas_server:app", host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
