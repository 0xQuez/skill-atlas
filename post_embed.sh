#!/usr/bin/env bash
# Watcher: wait for the embedding job to exit, then fold embeddings into clusters and regenerate everything downstream.
# Usage: nohup ./post_embed.sh <embed_pid> > logs/post_embed.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")"; . .venv/bin/activate
PID=${1:-42701}
echo "$(date '+%F %T %Z') waiting for embed PID $PID"
while kill -0 "$PID" 2>/dev/null; do sleep 60; done
echo "$(date '+%F %T %Z') embed exited; shards: $(ls out/full/emb/shard_?????.npz | wc -l)/75; last log: $(tail -1 logs/embed.log)"
grep -q '^DONE' logs/embed.log || echo "WARNING: embed.log has no DONE line; proceeding with the shards that exist (partial coverage)"
set -e
run(){ echo "$(date '+%F %T %Z') >>> $*"; "$@"; }
run python -u cluster.py          # ANN pairs (cos>=0.95, IVF-SQfp16 nprobe16 k=10) + MinHash pairs -> recluster -> skills/clusters/pairs/embeddings
run python -u headline.py         # base headline.json
run python -u slop.py             # slop_skill + with/without numbers
run python -u verdict.py          # canonical_id, verdicts, compact export
run python -u emb_examples.py     # embedding-only near-copies
run python -u compare_headlines.py
echo "$(date '+%F %T %Z') ALL DONE"
