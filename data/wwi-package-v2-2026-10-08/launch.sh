#!/usr/bin/env bash
# Start the read-only app and API. Usage: ./launch.sh [port] [host]   (defaults 8017, 127.0.0.1)
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python scripts/serve_v2.py --package . --port "${1:-8017}" --host "${2:-127.0.0.1}"
