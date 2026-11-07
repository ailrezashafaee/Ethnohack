#!/usr/bin/env bash
# Runs all stages in order. Finished work is skipped or read from the caches in data/,
# so with the committed data this reproduces the published results without new LLM calls.
set -euo pipefail
cd "$(dirname "$0")"

# list.worldfloraonline.org does not send its intermediate certificate; this bundle completes it.
export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-config/wfo_ca_bundle.pem}"

python src/ingest_perseus.py --xml data/00_source/phi0978.phi001.perseus-eng1.xml --books 20
python src/extract.py --all
python src/evaluate.py --split test     # extraction quality on the held-out chapters
python src/resolve_plants.py --blind 41
python src/map_conditions.py
python src/check_evidence.py
python src/build_graph.py
