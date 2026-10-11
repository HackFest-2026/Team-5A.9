#!/usr/bin/env bash
# Start the agent as an HTTP service (port 8018) for the in-app assistant.
# Needs: the WWI v2 API (./data/wwi-package-v2-2026-10-08/launch.sh 8017 10.9.0.105) and the model (llm/start_deepseek.sh --bg).
cd "$(dirname "$0")"
source r1.env
export WWI_URL="${WWI_URL:-http://10.9.0.105:8017}" AGENT_PLAN_MODE="${AGENT_PLAN_MODE:-slots}"
exec .venv/bin/python -m agent.server --host "${AGENT_HOST:-10.9.0.105}" --port "${AGENT_PORT:-8018}"
