#!/usr/bin/env bash
# Start everything the in-app assistant needs, skipping what is already listening:
#   1. DeepSeek-R1-32B on GPU 1        http://10.9.0.105:8090/v1
#   2. WWI console + data API          http://10.9.0.105:8017
#   3. Agent service (assistant)       http://10.9.0.105:8018
# Run again after any reboot. Logs: /tmp/wwi_v2_api.log, /tmp/agent_server.log, /home/dheeraj/llm/server.log
HOST=10.9.0.105
up(){ ss -ltn 2>/dev/null | grep -q "$HOST:$1 "; }
wait_for(){ for _ in $(seq 1 60); do curl -s -o /dev/null -m 2 "$1" && return 0; sleep 3; done; return 1; }
cd "$(dirname "$0")"
if up 8090; then echo "model:   already up"; else echo "model:   starting (about 1 minute)"; (cd /home/dheeraj/llm && ./start_deepseek.sh --bg >/dev/null 2>&1); fi
if up 8017; then echo "console: already up"; else echo "console: starting"; nohup data/wwi-package-v2-2026-10-08/launch.sh 8017 $HOST >/tmp/wwi_v2_api.log 2>&1 & fi
wait_for http://$HOST:8017/api/capabilities && echo "console: ready  http://$HOST:8017"
if up 8018; then echo "agent:   already up"; else echo "agent:   starting"; nohup ./run_agent_server.sh >/tmp/agent_server.log 2>&1 & fi
wait_for http://$HOST:8018/health && echo "agent:   ready  http://$HOST:8018/health"
K=$(cat /home/dheeraj/llm/api_key.txt 2>/dev/null)
wait_for_model(){ for _ in $(seq 1 60); do [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' -H "Authorization: Bearer $K" http://$HOST:8090/v1/models)" = 200 ] && return 0; sleep 3; done; return 1; }
wait_for_model && echo "model:   ready  http://$HOST:8090/v1" || echo "model:   NOT answering yet (check /home/dheeraj/llm/server.log)"
