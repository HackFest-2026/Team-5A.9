#!/usr/bin/env bash
# One-time setup on Linux/macOS: creates .venv with the exact pinned libraries, then builds the database.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m venv .venv
.venv/bin/pip install -q -r requirements-lock.txt
./rebuild.sh
