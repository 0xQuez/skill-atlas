#!/usr/bin/env python3
"""Download Skill Atlas data from the HF dataset if needed, then start the API on $PORT (default 7860)."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("SKILL_ATLAS_DATA_DIR", "/data"))
REPO = os.environ.get("SKILL_ATLAS_DATASET", "").strip()
FILES = ("verdicts_compact.parquet", "search_api.parquet", "headline.json")


def ensure_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in FILES if not (DATA_DIR / f).exists()]
    if not missing:
        return
    if not REPO:
        raise SystemExit(
            "Missing data files "
            + ", ".join(missing)
            + " and SKILL_ATLAS_DATASET is not set. "
            "Set it to the Hugging Face dataset id (for example USER/skill-atlas), "
            "or copy the files into SKILL_ATLAS_DATA_DIR."
        )
    from huggingface_hub import hf_hub_download

    for name in missing:
        print(f"downloading {name} from {REPO}", flush=True)
        hf_hub_download(repo_id=REPO, filename=name, repo_type="dataset", local_dir=str(DATA_DIR))


def main() -> None:
    ensure_data()
    os.environ.setdefault("SKILL_ATLAS_DATA", str(DATA_DIR / "verdicts_compact.parquet"))
    os.environ.setdefault("SKILL_ATLAS_SEARCH", str(DATA_DIR / "search_api.parquet"))
    os.environ.setdefault("SKILL_ATLAS_STATS", str(DATA_DIR / "headline.json"))
    if not os.environ.get("HOST") and os.environ.get("SPACE_HOST"):
        os.environ["HOST"] = os.environ["SPACE_HOST"]
    import uvicorn

    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
