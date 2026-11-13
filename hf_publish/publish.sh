#!/usr/bin/env bash
# Create (private) Hugging Face dataset + API Space + dashboard Space, then upload.
# Requires: HF_TOKEN, HF_USER. Does not make anything public.
# Usage: HF_TOKEN=... HF_USER=you ./hf_publish/publish.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
: "${HF_TOKEN:?Set HF_TOKEN to a Hugging Face write token (do not paste it into chat).}"
: "${HF_USER:?Set HF_USER to your Hugging Face username.}"

DATASET_ID="${DATASET_ID:-$HF_USER/skill-atlas}"
API_SPACE="${API_SPACE:-$HF_USER/skill-atlas-api}"
WEB_SPACE="${WEB_SPACE:-$HF_USER/skill-atlas-web}"
DATASET_URL="https://huggingface.co/datasets/${DATASET_ID}"
PARQUET_BASE="https://huggingface.co/datasets/${DATASET_ID}/resolve/main"
# Space URLs: "user/name" becomes "user-name.hf.space"
API_URL="https://${API_SPACE//\//-}.hf.space"
WEB_URL="https://${WEB_SPACE//\//-}.static.hf.space"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
"$PY" -c "import huggingface_hub" 2>/dev/null || { echo "Install huggingface_hub first: pip install huggingface_hub"; exit 1; }

echo "Will create PRIVATE repos (nothing is made public):"
echo "  dataset   $DATASET_ID"
echo "  api space $API_SPACE"
echo "  web space $WEB_SPACE"
echo

# --- stage dataset files (hardlink when possible) ---
DS="$ROOT/hf_publish/dataset"
mkdir -p "$DS"
link() { ln -f "$1" "$2" 2>/dev/null || cp -a "$1" "$2"; }
stage_list="
verdicts_compact.parquet
search_api.parquet
headline.json
white_hat_stats.json
slop_criteria.json
malicious_source_stats.json
risk_v2_stats.json
verdict_shift_v1_v2.json
ingest_stats.json
refine_pairs_stats.json
label_translation.csv
label_before.csv
label_after.csv
"
for f in $stage_list; do
  src="$ROOT/out/full/$f"
  [[ -f "$src" ]] || { echo "missing $src"; exit 1; }
  link "$src" "$DS/$f"
done
link "$ROOT/dashboard/src/data/search_index.parquet" "$DS/search_index.parquet"
link "$ROOT/dashboard/src/data/skill_details.parquet" "$DS/skill_details.parquet"
echo "Dataset staging sizes:"
du -h "$DS"/* | sort -h
echo

# --- build dashboard Space (no bundled parquets; fetch from the dataset URL) ---
WEB="$ROOT/hf_publish/space_dashboard"
find "$WEB" -mindepth 1 -maxdepth 1 ! -name README.md ! -name .gitattributes -exec rm -rf {} +
CFG="$ROOT/dashboard/src/data/config.json"
CFG_BAK="$(mktemp)"
cp "$CFG" "$CFG_BAK"
restore_cfg() { cp "$CFG_BAK" "$CFG"; rm -f "$CFG_BAK"; }
trap restore_cfg EXIT
"$PY" -c "
import json
from pathlib import Path
p = Path(r'''$CFG''')
cfg = json.loads(p.read_text())
cfg['parquet_base'] = r'''$PARQUET_BASE'''
p.write_text(json.dumps(cfg, indent=2) + chr(10))
"
BUILD_DIR="$WEB/_build"
(cd "$ROOT/dashboard" && ATLAS_PILL="hosted preview" OBS_OUT="$BUILD_DIR" npm run build)
find "$BUILD_DIR" -name '*.parquet' -delete
# Copy built files into the Space folder, keeping the Space card at README.md
cp "$WEB/README.md" "$WEB/README.card.md"
cp -a "$BUILD_DIR"/. "$WEB/"
rm -rf "$BUILD_DIR"
# Prefer the Space card (YAML front matter) over the Framework-generated README, if any
mv -f "$WEB/README.card.md" "$WEB/README.md"
if [[ -f "$WEB/agents.html" ]]; then
  sed -i "s#http://127.0.0.1:8765#${API_URL}#g" "$WEB/agents.html" || true
fi
restore_cfg
trap - EXIT

echo "Dashboard Space files over 10 MB (need LFS/Xet):"
find "$WEB" -type f -size +10M -printf '%s\t%p\n' | sort -nr || true
echo

# --- stage API Space (copy current server/app.py) ---
API="$ROOT/hf_publish/space_api"
cp "$ROOT/server/app.py" "$API/atlas_server.py"

# --- create repos and upload (private) ---
export DATASET_ID API_SPACE WEB_SPACE DATASET_URL API_URL WEB_URL DS API WEB
HF_TOKEN="$HF_TOKEN" "$PY" - << 'PY'
import os
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
dataset_id = os.environ["DATASET_ID"]
api_space = os.environ["API_SPACE"]
web_space = os.environ["WEB_SPACE"]

def ensure_dataset(repo_id):
    try:
        api.repo_info(repo_id, repo_type="dataset")
        print("dataset exists:", repo_id)
    except Exception:
        api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
        print("created private dataset:", repo_id)

def ensure_space(repo_id, space_sdk):
    try:
        api.repo_info(repo_id, repo_type="space")
        print("space exists:", repo_id)
    except Exception:
        api.create_repo(repo_id, repo_type="space", private=True, exist_ok=True, space_sdk=space_sdk)
        print("created private space:", repo_id, space_sdk)

ensure_dataset(dataset_id)
ensure_space(api_space, "gradio")
ensure_space(web_space, "static")

print("uploading dataset (this is about 1.1 GB and will take a while)...")
api.upload_folder(
    folder_path=os.environ["DS"],
    repo_id=dataset_id,
    repo_type="dataset",
    commit_message="Add Skill Atlas derived data (CC BY 4.0, based on GitSkills)",
)

# Do not store a write-scoped token as a Space secret. Data is baked into
# the API Space (./data), and once the dataset is public no token is needed.
api.add_space_variable(api_space, "SKILL_ATLAS_DATASET", dataset_id)
api.add_space_variable(api_space, "ATLAS_PRODUCTION", "1")
api.add_space_variable(api_space, "DUCKDB_MEMORY", "1GB")
api.add_space_variable(api_space, "RATE_LIMIT_PER_MIN", "60")
api.add_space_variable(api_space, "CORS_ORIGINS", "*")

print("uploading API Space...")
api.upload_folder(
    folder_path=os.environ["API"],
    repo_id=api_space,
    repo_type="space",
    allow_patterns=["README.md", "requirements.txt", "app.py", "atlas_server.py", "entrypoint.py", "data/*"],
    commit_message="Add Skill Atlas API Space",
)

print("uploading dashboard Space...")
api.upload_folder(
    folder_path=os.environ["WEB"],
    repo_id=web_space,
    repo_type="space",
    commit_message="Add Skill Atlas dashboard Space",
)

print()
print("Done. All three repos are PRIVATE.")
print("  dataset:   https://huggingface.co/datasets/" + dataset_id)
print("  api space: https://huggingface.co/spaces/" + api_space)
print("  web space: https://huggingface.co/spaces/" + web_space)
print("Look them over, then make them public from the Hugging Face UI if you want.")
print("After that, put these URLs in the git README:")
print("  HOSTED_DATASET_URL=" + os.environ["DATASET_URL"])
print("  HOSTED_API_URL=" + os.environ["API_URL"])
print("  HOSTED_DASHBOARD_URL=" + os.environ["WEB_URL"])
PY
