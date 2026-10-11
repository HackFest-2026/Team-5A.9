# Decisions and why

## Made by the user
| Decision | Why / context |
|---|---|
| Local LLM = DeepSeek-R1-Distill-Qwen-32B (Q4_K_M) on **GPU 1** via llama.cpp, exposed on the LAN with an API key | Run locally; build against CUDA 12.2 (driver 535 cannot run Ollama, which needs 550+). Do not worry about GPU 0. |
| Run services on **10.9.0.105** (not Tailscale) | Reachability from the lab network. |
| Build **both** an API-based agent and a VACP agent | The client expects API agents; VACP is our differentiator. |
| Load the **full history** into ERPNext, merge the synthetic case (item 1227) into the same company, flagged | Show a real ERP holding our data; keep the test case visible but labelled. |
| **Stop the invoice load at 24 Feb 2016** ("nothing more and nothing less") | Time. The stock-flow stage slowed to about 1 record/s. |
| Team name **Sapience** | Corrects older "Sapiens". |
| Embed the agent in the application | The agent must be in the app, not a terminal tool. |
| **Hold** the joined API + VACP loop | The user paused it; do not start it without being asked. |
| No claude.ai artifacts; deck font ≥ 15 pt; private notes in `Do_not_open/` | Standing preferences. |

## Made during the work (with the reasoning)
- **v2 over v1 as the backend.** v2's `analyze`/`resolve`/`related` and independent oracle fix the defects Sapience's own audit lists (filters ignored, capped groups marked complete, unstable ties, no name resolution). Expected fix; not yet proven by re-running their probes.
- **Reliability comes from the harness, not the model.** Measured: letting the model emit calls scored 6.5% (Qwen-14B) and 9.7% (R1-32B); letting the model only extract slots and code build the calls scored 41.9%. R1 is also used because local DeepSeek ignores native tool calls.
- **Six small task-level tools** (Tool Illusion), a ledger of observed facts and grounding (LedgerAgent / Reason Less Verify More), and a code finish gate (Mingbird). We adopt the ideas, not the papers' code. See `03_STORY_AND_DESIGN.md`.
- **Read-only console and agent.** The data and oracle must stay fixed for the benchmark to mean anything. Writes, if built, go to a separate labelled layer. Chart creation is safe (stores a definition, not data). See `04_FEATURES_AND_LIMITS.md`.
- **ERPNext in Docker** (one compose file, images `frappe/erpnext:v15.119.3`, `mariadb:10.6`, `redis:6.2-alpine`). Portable by backup/restore; moved to nova2 as a 123 MB backup in a zip. The load runs through ERPNext's business logic (73k orders over REST would take days).
- **Loader speedups:** database tuned live (16 GB buffer pool, relaxed commit flush); four parallel workers for sales orders with explicit names (the order-number counter row was the lock that serialised workers). Invoices cannot be parallelised (valuation depends on date order).
- **WebArena-Verified is the external benchmark** (deterministic scoring, same sites as Beyond Browsing). Our own WWI/ERPNext tasks score the brief's KPIs because WebArena has no ERP or analytics site. Not yet run.
- **Embedded assistant is a separate HTTP service** (`:8018`) with CORS, one question at a time, so the page stays static and the agent stays Python.
- **The infographic is data-driven,** built server-side from the agent's actual calls and events, with steps 07–08 confirmed in the browser against the page's own state. It is not decoration.
- **Workspace CRUD as an overlay (12 Oct).** The user asked for CRUD in the app. Writing into the source would change the figures the answer key and 8-of-8 reconciliation depend on, so edits are stored in a separate SQLite file with an audit log and soft delete; source rows are never modified.
- **The infographic shows the real trail, not a fixed picture (12 Oct).** The user noticed the eight boxes were the same every time.
- **Rejected/not done and why:** parallelising invoices (unsafe); a gates-off ablation (not yet run); WebArena runs (heavy setup); build our own VACP bridge for ERPNext (nova2 already has a better one).

## Open decisions for the user
1. **Cloud or local model** for the demo (slides say "cloud"; best results are local R1-32B; the Sapience build says cloud-only).
2. **Held-out run:** when to freeze and run it (15 chains; do not tune on them).
3. **VACP licence:** use its source on nova2 as is, or reuse only the design?
4. **Task counts in the deck:** "15 of 18" does not match 31 dev + 15 held-out chains.
5. **AI disclosure:** add Claude Code (Anthropic); the deck lists only OpenAI Codex.
6. ~~Whether edits should count in analytics.~~ **Decided in the build (12 Oct): no.** Workspace edits are labelled, stored separately and ignored by `/api/analyze`, the oracle and the agent. Say so if judges ask.
7. **Which to build next:** chart builder, ERPNext per-user adapter, a guarded write in ERPNext, or the joined loop (on hold).
