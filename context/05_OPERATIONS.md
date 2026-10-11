# Operations: start, reach, test, fix

All commands below go with the prefix `wsrun --student 01fe23bcs197`.

## Machines
| | This machine | nova2 |
|---|---|---|
| Address | `10.9.0.105` (user `dheeraj`) | `10.9.0.108` (user `nova2`; key login works; files in `/home/nova2/hackathon`) |
| Repo | `/home/dheeraj/Agentic_Hackathon` | `/home/nova2/hackathon` (our zip extracted at `wwi-transfer/`; Sapience handoff at `API_BASED_AGENT/`; VACP repo at `VACP/`) |
| GPUs | 2 × 24 GB; **GPU 1** runs DeepSeek; GPU 0 left alone | none (no `nvidia-smi`) |

## Services and ports (this machine)
| Port | Service | Notes |
|---|---|---|
| 8090 | DeepSeek-R1-32B, OpenAI-compatible `/v1` | Needs the API key in `/home/dheeraj/llm/api_key.txt` (never copy it elsewhere). Start `llm/start_deepseek.sh --bg`, stop `stop_deepseek.sh`. About 23.5 GB on GPU 1. |
| 8017 | WWI console + data API (v2) | `data/wwi-package-v2-2026-10-08/launch.sh 8017 10.9.0.105` (default binds localhost only). Analytics read-only; workspace writes (`/api/ws/*`, header `X-Sapience-Write: 1`) go to `workspace/workspace.db`. No login. Restart it after editing `serve_v2.py` or `workspace.py` (static files in `app/` are re-read on every request). |
| 8018 | Agent service for the in-app assistant | `./run_agent_server.sh` (sets `WWI_URL`, slots mode, sources `r1.env`). `POST /ask`, `POST /reset`, `GET /health`. |
| 8081 | ERPNext (Desk at `/app`) | `/home/dheeraj/erpnext/compose.yml`, project `wwi-erpnext`; 9 containers; frontend bound to `10.9.0.105:8081`. Data in `/home/dheeraj/erpnext/volumes/` (owned by container users). |
| (8080 is Label Studio, unrelated) | | |
nova2: ERPNext on `10.9.0.108:8081` (+ the VACP bundle at `/vacp/vacp-bridge.js`), metasfresh on 80/8082/8085, a dashboard/LLM relay on 5185, something on 8090.

## Start everything (after any reboot)
`cd /home/dheeraj/Agentic_Hackathon && ./start_all.sh` → starts the model, the console and the agent, skipping what is already listening. ERPNext containers restart on their own after a reboot (seen once). A reboot at 09:39 on 11 Oct had stopped every other service.
Open `http://10.9.0.105:8017`, click "Ask the assistant".

## Tests
- Agent unit tests: `.venv/bin/python -m pytest tests -q -p no:cacheprovider` (16 pass; need the WWI API up).
- Browser test of the console, assistant and journey: only nova2 has Playwright: `ssh nova2@10.9.0.108 'cd /home/nova2/hackathon && VACP/.venv/bin/python wwi-transfer/Agentic_Hackathon/data/erpnext-loader/ui_test.py http://10.9.0.105:8017'` (copy of `eval/ui_test.py`; screenshots land in `/tmp/ui_shots` on nova2). Takes 3–5 minutes (model latency).
- Workspace CRUD test (create, edit, revert, draft order, delete, restore, activity log, API guards, source untouched): `scp eval/ws_test.py nova2@10.9.0.108:/home/nova2/hackathon/` then `ssh nova2@10.9.0.108 'cd /home/nova2/hackathon && VACP/.venv/bin/python ws_test.py http://10.9.0.105:8017'` (about 1 minute; leaves its test records in the workspace, so delete `data/wwi-package-v2-2026-10-08/workspace/workspace.db` afterwards; the server recreates it). Screenshots in `/tmp/ws_shots` on nova2, copies in `evidence/ui_screenshots/`.
- ERPNext reconciliation: copy `erp_measures.py` into the backend container, run it, then `data/erpnext-loader/reconcile_feb2016.py` with a Python that has duckdb (`/home/dheeraj/erpnext/.venv`). Schema audit: `schema_check.py` the same way.
- nova2's ERPNext VACP test: `VACP/.venv/bin/python test_erpnext_vacp.py http://10.9.0.108:8081` from `/home/nova2/hackathon` (takes minutes; prints at the end).
- Agent evaluation: `source r1.env; AGENT_PLAN_MODE=slots .venv/bin/python -m eval.run_v2 --split dev --out evidence/run.json`; add `--k 3`, `--gates off`. **`--final` reads the held-out chains: use once, after freezing, never tune on it.**

## Moving to another machine
`data/TRANSFER.md` is the guide. `/home/dheeraj/transfer/wwi-transfer.zip` (160 MB, includes the 123 MB ERPNext backup; sha256 starts `83100184`) is already restored on nova2. **Changes made after that (embedded agent, console redesign, ledger, `start_all.sh`) are not in the zip.** The v2 `.venv` here was rebuilt on 11 Oct (without `pyodbc`).

## Gotchas learned
- `pkill -f <pattern>` can kill your own shell; stop a service by the PID listening on its port instead.
- `kill` is a shell builtin: inside a container use `docker exec C bash -c 'kill PID'`.
- The default `node` on this machine is v12 (no `??` support); syntax-check JS on nova2 (Node 24) or by the browser test.
- ERPNext login: type `Administrator` in the first box (not an email); "Login with Email Link" needs email, which is not configured. The page after login is the portal; use `/app`.
- ERPNext database tuning (16 GB buffer pool, relaxed commit flush) was applied live and reverts if the database container restarts.
- The WWI console's `launch.sh` and the agent service must both use the LAN IP, or other machines cannot reach them.
- An earlier health check that passed the API key through the `wsrun` wrapper was blocked by the safety classifier; do not pass the key through wrappers.
- The list of 11 "pages" in the original app was just sidebar links; detail pages are reached by record links (now also from the Browse lists).
- Backups of the originals before the redesign: `app.orig-2026-10-11/` and `scripts/serve_v2.py.orig-2026-10-11`.
