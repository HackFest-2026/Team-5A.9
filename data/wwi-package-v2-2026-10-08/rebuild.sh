#!/usr/bin/env bash
# Rebuild DuckDB from the shipped Parquet files and run every check (same steps as rebuild.cmd).
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
"$PY" scripts/build_local.py --package .
"$PY" scripts/build_v2.py --package .
"$PY" scripts/validate.py --package .
"$PY" scripts/validate_contract.py --package .
"$PY" scripts/validate_v2.py --package .
"$PY" scripts/check_tasks_v2.py --package .
echo "Rebuild and validation passed."
