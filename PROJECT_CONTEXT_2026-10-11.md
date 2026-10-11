# Sapience: end-to-end project context (11 Oct 2026)

Read this first in a fresh conversation. It covers the problem, the story, what is built, the evidence, the deck, the open decisions and the claims we must not make. Status tags: **[MEASURED]** a result file in `evidence/` I produced and read; **[VERIFIED]** checked by running or reading the primary source in this work; **[REPORTED]** taken from a handoff note (the user's context pack or the nova2 documents) and not re-run here; **[PENDING]** not done; do not present it as a result.

## 0. Rules from the user (still in force)
- **Team name is Sapience** (not "Sapiens"). Members on the cover: Karthik NHM, Rakshita Kulkarni, Vikas U B, Yashas A B. Event: KLE Tech Hackfest 2026, Domain 5A, Context-Aware Application Agent.
- **Do not read `Do_not_open/`** (private).
- **Prefix every shell command with `wsrun --student 01fe23bcs197`** (one flag, exactly that). Wrap compound commands as `wsrun --student 01fe23bcs197 bash -c '...'`. Beware nested quotes in `bash -c`; write patch scripts to files instead.
- **Deck rules:** edit a copy, never the v4 file; every font at least 15 pt; keep the honesty convention (labels such as "proposed", "pending", "development set, single run"); no personas; no claude.ai artifacts.
- **Decisions the user made on 11 Oct:** slides on the task set (objectives and evaluation plan) are on hold, so leave "15 of 18" and "12 + 18" alone; AI disclosure slide left as is (OpenAI Codex only); the model line says the system can use a local or a cloud model; Qwen must not appear in the deck; the data-scope slide shows the ERPNext facts and the 24 Feb 2016 cut-off only.

## 1. The problem and the KPIs (from `problem_statement.md` and `CLAUDE.md`)
Build an assistant that understands a whole no-code business application (pages, widgets, data views, filters, charts) and lets users operate and analyse it in natural language: work out intent, go to the right page and set filters/dates/sort, retrieve and combine data, reason about trends and period-to-period changes, and present the answer in the app's context. KPIs: intent-to-destination accuracy; UI-state correctness; multi-step task success with average steps and latency; analytical correctness and faithfulness (every answer traces to supporting views); retrieval precision, recall and MRR over hundreds of pages; action hallucination near zero; error and recovery rate.

## 2. The story the deck tells (user's framing, kept honest)
1. **API-based approach first.** Beyond Browsing (Findings of ACL 2025, Fig. 4) sampled 100 WebArena tasks for an API-only agent: 33% correct, **50% unsolvable because the needed endpoint does not exist**, 11% API-usage error, 6% misunderstanding. The hybrid (API + browsing) reached 38.9%, API-only 29.2%, browsing-only 14.8%. The user's wording is "low-quality API design"; the paper's wording is "no endpoint exists" (a coverage gap). The deck uses the paper's wording.
2. **Then VACP.** Declared, typed in-app actions (navigate, set period, set filters, open record, read state) could cover what has no endpoint. This is **our hypothesis, not a result**. VACP's own "near-perfect" results are not independently replicated.
3. **One agent, two channels (proposed).** API for knowing (exact analysis over all rows), VACP for doing and showing (operating the real app). Routing rule: analysis goes to the API; operate or show goes to a VACP action; both means the API answers and VACP puts the user on the matching page; no endpoint means a declared VACP action.
4. **Honest wording:** "both channels are built and verified individually; joining them is the last step." Never "fully integrated".
5. **Best demo moment:** the API's April total and the number read back from the real ERPNext page agree (April 2016 = 1,951). Two independent channels confirm each other. May's 2,047 on the page still needs a rehearsal run.

## 3. Data
- **WWI v2 package** at `data/wwi-package-v2-2026-10-08/` (Contract 0.2.0; data rows identical to v1). Read-only app and API (`launch.sh`, port 8017): `POST /api/analyze`, `/api/resolve`, `/api/related`, `/api/records`, `/api/metric`, `/api/chart`, `GET /api/contract`, `/api/lookup`. 73,595 orders, 231,412 order lines, 21 source tables; dates to 31 May 2016 (data range 2013-01-01 to 2016-06-21, end dates exclusive).
- **Measures:** M01 orders created, M02 stored unpicked units, M03 orders with unpicked quantities, M13 ordered units, M05 related incoming units (undated or by purchase/expected-delivery date), M10 invoiced sales excluding tax, M11 recorded gross line profit. M10 and M11 carry the label "sample amount (currency not stated in source)"; M11 is gross line profit, not net. Customer-side dimensions are invalid for M05. Ten dimensions (month, customer, customer category, buying group, state, sales territory, salesperson, item, supplier, stock group). Item, supplier and stock-group breakdowns of order counts overlap, so rows must not be summed and no shares shown.
- **Limits that apply:** frozen 2016 data, no recorded reasons (show where a change is concentrated, never why), customer attributes are current values, "this month" means May 2016 (archive end 31 May 2016).
- **ERPNext 15.119.3 / Frappe 15.118 with WWI loaded [REPORTED]:** 73,596 sales orders (73,595 WWI plus one flagged synthetic case, item 1227), 64,500 sales invoices, 2,074 purchase orders, 1,914 purchase receipts, 663 customers, 228 items. **Invoices and receipts stop at 24 Feb 2016** (deliberate, user decision); sales orders run to 31 May 2016. Reconciliation against the independent oracle: 8 of 8 checks pass (`data/erpnext-loader/reconcile_feb2016.py`). USD is a technical placeholder (the source states no currency); ERPNext recomputes profit, so M11 is not comparable. Live at `http://10.9.0.105:8081` and `http://10.9.0.108:8081` (nova2); use `/app`. Passwords are install defaults; do not write them into documents.
- **Evaluation assets (`evaluation/v2/`):** 31 development chains (87 steps), 15 held-out chains (40 steps, **sealed; never use for tuning; do not read their answers**), 218 labelled utterances, 150 retrieval queries over 293 pages (30 real, 263 decoys; 10 queries have no fitting page). Expected values come from an independent oracle (`scripts/oracle_v2.py`). An older v1 set has 12 development and 18 held-out tasks.

## 4. Approach 1: the API-based agent (built on this machine, 10 Oct)
**Code:** `agent/` (about 14 modules), `eval/`, `tests/`, `README.md`. Plan source: `research/01_API_AGENT_BUILD_PLAN.md` (four-paper design: Beyond Browsing, LedgerAgent plus Reason Less Verify More, Mingbird, The Tool Illusion plus Beyond Text-to-SQL).

**Flow (`agent/loop.py`):**
1. **Understand** (`understand.py`): the LLM, with JSON-schema-constrained output, returns an Intent that is only a *delta* over the carried state. Every field is required; enums carry an explicit `"unchanged"` value (forcing optional fields made the model invent values; leaving them optional made it skip them).
2. Code guards on the intent (`Agent.sanitize`): drop `status`, `sort`, `top_n`, `group_by` unless the user's words support them; fill a missing period from calendar words (`slots.fallback_periods`); drop ids the user never typed and no result showed.
3. **Resolve** names by calling `resolve` (unique means use the id, ambiguous means ask, none means abstain); a reply to a clarifying question is understood together with the question it answers.
4. **Merge** into the carried state in code (`slots.merge_state`): dates, relative periods, comparisons, filters, geography narrowing, breakdown reset when you filter to the dimension you were grouped by.
5. **Plan and execute.** Two modes: `slots` (code compiles the calls from the intent) or `llm` (the model emits the calls). Every call passes the gates (`gates.py`): schema (pydantic models generated from the Contract), grounding (ids must come from `resolve`, a result row or the user), read-before-write (no write tools exist in v1, so it never triggers), loop detector, step budget 8, up to 3 repairs, then abstain.
6. **Finish gate** (`finish.py`, code only, no LLM judge): applied state equals the intent, no repeated calls, budget respected, and every number in the answer traces to a tool result or to code arithmetic (`facts.py`). Currency symbols and causal wording are rejected. After two failed drafts a deterministic template answer is used.
7. **Answer** with the figure facts, caveats added by code, an in-app deep link and the list of actions taken.

**Six tools (`tools.py`):** `lookup`, `resolve`, `analyze`, `records`, `related`, `open_page`. `lookup(kind="page")` uses a two-stage retrieval driven by the LLM (`docs.py`: pick modules, then rank pages from enumerated ids) and reports `available_in_app` so a decoy page can never be opened. A BM25 and bge-m3 index also exists in `docs.py` but is not the product path; the bge-m3 server is down.

**Models and servers (state on 11 Oct):**
- **DeepSeek-R1-Distill-Qwen-32B** (llama.cpp) at `http://10.9.0.105:8090/v1`, API key in `/home/dheeraj/llm/api_key.txt` (never print it), two parallel requests. Use `source r1.env` (sets `LLM_URL`, `LLM_MODEL`, `LLM_CALL_STYLE=json`, `LLM_KEY` from the key file). Constrained JSON works only through `/v1/completions` with `json_schema` and a pre-filled empty think block; the chat endpoint ignores the schema (`agent/llm.py`, call style `json`). About 30 tokens/s.
- **Qwen2.5-14B-Instruct-AWQ on vLLM (:8011) and bge-m3 (:8012) stopped during the session** (not by us). The user chose R1 instead of restarting them. Qwen runs exist in `evidence/` as history; **Qwen must not appear in the deck.**
- **WWI app:** a LAN-bound instance runs at `http://10.9.0.105:8017` (set `WWI_URL`).

**Nemotron:** the nova2 (Sapience) build is configured for a cloud model, `nvidia/nemotron-3-nano-30b-a3b:free` on OpenRouter (Ollama Cloud as a second transport). **No live run is verified [REPORTED].** None of our measured results used Nemotron. The deck says: hosted model configured, not run live; results used DeepSeek-R1-32B.

**Tests:** 16 unit tests pass (`pytest tests`): gates, grounding, schema repair hints, finish gate, faithfulness, calendar maths [VERIFIED].

**Commands:**
```
source r1.env
.venv/bin/python -m agent.cli "How did orders in May 2016 compare with April, by territory?" "Which states inside Great Lakes moved?"
.venv/bin/python -m eval.run_v2 --split dev --what chains --workers 2 --plan-mode slots --out evidence/run.json
.venv/bin/python -m eval.show_fail evidence/run.json      # why steps failed
.venv/bin/python -m eval.dbg V2D07 --plan-mode slots      # per-step intent, expectation, gate events
.venv/bin/python -m eval.retrieval --modes llm            # retrieval KPI
```
`eval.run_v2` refuses the held-out split without `--final`. Run long jobs in the background (`nohup ... &`) and poll; the user dislikes long waits.

## 5. Evidence [MEASURED], all on the development split, one run each, held-out NOT run
Same 31 chains (87 steps). Files in `evidence/`.

| Run | Chain success | Step pass | Hallucinated actions | Latency/step | File |
|---|---|---|---|---|---|
| Qwen2.5-14B emits the calls (older code) | 6.5% | 34.5% | 23.0% | 20 s | `dev_chains_r1.json` |
| R1-32B emits the calls (older code, before the planner fix) | 9.7% | 27.6% | 3.4% | 32 s | `dev_chains_full_r1.json` |
| R1-32B slots, code builds the calls (older code, template answers) | 41.9% | 70.1% | 2.3% | 8 s | `dev_chains_slots_r1.json` |
| **R1-32B slots, current code, R1-written answers** | **58.1% (18 of 31)** | **77.0%** | **4.6% (4 of 87)** | **19.3 s (p95 39 s)** | `ctl_slots_r1.json` |

Current run (the deck's KPI slide): destination 78.2% (68 of 87), UI state 79.3% (69 of 87), analytic 78.2% (68 of 87), faithfulness 100% (1.3% of answers fell back to the template), 2.8 steps per chain, 1.2 tool calls per step.
**Retrieval over 293 pages** (140 rankable queries; LLM two-stage, R1): exact-page hit@1 61.4%, hit@3 73.6%, hit@5 77.9%, MRR 0.677 (lenient hit@1 70.7%, MRR 0.75); by difficulty MRR easy 0.786, medium 0.568, hard 0.714 (`retrieval.json`). A BM25 reference I ran earlier gave MRR 0.595, hit@1 48.6% (printed once, file overwritten).

**Caveats to state with any of these numbers:**
- **Not a controlled comparison.** The first three rows used earlier code; many fixes came after seeing dev failures, so the current run is tuned to this set. The 41.9% to 58.1% jump is mostly code improvements.
- The same-code rerun where R1 emits the calls (`ctl_llm_r1.json`) **did not complete**; the comparison is **[PENDING]**. `traces/controlled.sh` runs both reruns (it points `WWI_URL` at 10.9.0.105:8017).
- Faithfulness checks numbers (and currency/cause wording), not every claim in the prose.
- Not measured: held-out score, any baseline comparison (screen-only agent, gates off), error and recovery rate, the 218-utterance set, WebArena-Verified (stack is about 100 GB; nothing run).

## 6. Approach 2: VACP on ERPNext (built on this machine and nova2, 10 to 11 Oct)
- **[REPORTED] prototype** `data/erpnext-loader/spike_vacp_erpnext.py`: our own `window.__vacp` (`getCapabilities`, `getState`, `execute`) injected into the stock ERPNext Desk with no rebuild. Actions: `navigate`, `set_period`, `set_filters`, `clear_filters`, `open_record`, `query`. **23 of 23 checks passed against SQL on nova2:** navigation without reload, April 2016 = 1,951 orders, status/customer filters matching SQL, five invalid calls refused with the URL unchanged, net sales Dec 2015 = 4,458,811.25, a grouped query of 2,048 orders, Back, hard reload.
- **Caveats:** it is our own bridge, not VACP's kit; tested in headless Chromium on the Sales Order and Sales Invoice lists only; territory filtering untested; the VACP repo has no licence file, so only independently implemented patterns are used; one `set_period` call took 10.4 s (unexplained), typical 0.4 to 1.2 s.
- **Lessons:** `frappe.set_route` with filter options is ignored when the list is already open (use `cur_list.filter_area.set`); ERPNext remembers per-user list filters, so `navigate` must clear them; the list count label caps at "1,000+" (use `frappe.client.get_count`).

## 7. The Sapience build on nova2 [REPORTED, read-only access, nothing re-run]
`ssh nova2@10.9.0.108`, folder `/home/nova2/hackathon/API_BASED_AGENT` (handoff zip extracted under `extracted/Sapience_Server_Handoff/`). Most useful files: `PLAN01_RECOMMENDATIONS_2026-10-11.md`, `Brain/08_COMPACT_CONTEXT.md`, `Brain/12_Whole_Picture_Integration_Map_2026-10-11.md`, `Brain/14_Corrective_Handoff_Review_2026-10-11.md`, `Brain/17_FINAL_SWEEP_AND_PRESENTATION_SOURCE_BRIEF.md`.
- **Built:** a read-only WWI/DuckDB API (HTTP, v1 routes), a vanilla-JS ERP-style workspace, UI context snapshots (`sapiens-context-0.2`: `ui_instance_id`, `context_revision`, `snapshot_seq`, request/render ids), an isolated hosted-model transport (OpenRouter and direct Ollama Cloud, 39 offline mocked tests), six tool wrappers, partial gates and finish. 65 Python tests passed (22 corrective, 39 hosted-transport, 4 fixture); UI context tests also pass (the notes give different counts: 7, 8 and 11; do not quote one).
- **Unfinished (their own audit):** the build is on WWI v1 (filters ignored, top-50 groups marked complete, names matched as strings, one measure), finish accepts a failed analyze with an empty answer, the model loop is still a keyword parser, no durable sessions (MariaDB `SessionRepository` with compare-and-swap and idempotency is designed, not built), no assistant routes or panel, no live hosted-model success. Their plan note recommends adopting our v2 backend and the slots-first design.
- **Their framing (cloud-only inference, MariaDB state, ERPNext as future adapter):** conflicts slightly with our local R1 runs; the deck says "local or cloud".

## 8. The deck: `Sapience_Hackfest_Deck_v5.pptx` (20 slides)
**Build:** `python3 deck/build_v5.py` (python-pptx; reads every number from `evidence/`; never writes the v4 file `Sapience_Hackfest_Deck_v4 (1).pptx`, md5 b9e9cacc...). Architecture and workflow drawing code is in `deck/arch_slides.py`. Render check: LibreOffice 25.8 unpacked without root at `/tmp/claude-1001/lo` (temporary; `render.sh deck.pptx outdir dpi`); validator: the pptx skill's `scripts/office/validate.py` (needs `.venv` with `defusedxml`, `lxml`). Not opened in PowerPoint.

| # | Slide | Notes |
|---|---|---|
| 1 | Cover | unchanged |
| 2 | What are we trying to solve? | unchanged |
| 3 | Existing approaches | unchanged |
| 4 | Where API-only agents fall short | new: Fig. 4 numbers as native charts; "API agent first, then VACP for the half with no endpoint"; hypothesis labelled |
| 5 | Proposed solution | footer: components built and verified separately |
| 6 | Objectives | **unchanged (on hold)**: "15 of 18" |
| 7 | System architecture | rebuilt: three rows (API-based, VACP, unified, dashed) after the Beyond Browsing figure |
| 8 | Approach 1: API-based agent | pipeline plus LedgerAgent, The Tool Illusion, Mingbird; Nemotron configured note |
| 9 | Approach 2: VACP, in-app actions | Task / VACP / Application bands after the VACP figure |
| 10 | Example workflow | timeline of 8 numbered nodes; example "Compare total orders in April and May 2016."; dashed after step 5 |
| 11 | Context and state persistence | unchanged (planned) |
| 12 | Why is our solution better? | footer points to the run comparison slide |
| 13 | Dataset information | 4th tile now "24 Feb 2016, ERPNext invoice cut-off"; ERPNext facts line |
| 14 | Evaluation plan | **unchanged (on hold)**: WebArena 812, "12 + 18" |
| 15 | Development-set KPI results | current run, KPI table incl. retrieval; "tuned on these chains" |
| 16 | What drove the result | three R1 runs, not a controlled comparison; rerun pending |
| 17 | Built and verified so far | API agent, ERPNext data, bridge, Sapience workspace; not done yet list |
| 18 | Research references | unchanged |
| 19 | Research references (continued) | new refs 13 to 16, hyperlinked |
| 20 | Data sources and AI disclosure | **unchanged (user's choice)** |

**References added (authors and venues checked on arXiv/OpenReview on 11 Oct):** 13 WebArena Verified (El hattami, Thakkar, Chapados, Pal; NeurIPS 2025 workshop, no arXiv entry), 14 WALT (Prabhu et al., arXiv 2510.01524), 15 Web Agents Should Adopt the Plan-Then-Execute Paradigm (Piet et al., arXiv 2605.14290), 16 Callability Is Not Operability (Wang, arXiv 2608.23628). Existing refs 1 to 12 are as in v4 (2 Beyond Browsing, 3 VACP, 4 LedgerAgent, 5 Reason Less Verify More, 6 The Tool Illusion, 7 Beyond Text-to-SQL, 8 Mingbird).

## 9. Open decisions and next steps
1. **Task set (user said hold):** report the v2 set (31 dev chains / 15 held-out chains) or keep v1 (12 + 18 with the 15-of-18 target). Slides 6 and 14 still carry v1 numbers while the results use v2.
2. **Finish the controlled rerun** (`traces/controlled.sh`) so slide 16 can drop "pending".
3. **Held-out run:** only once, after freezing prompts, guards and tools, with `--final`; disclose that the dev set was used for tuning.
4. **Join the channels:** the agent drives the ERPNext bridge (needs Playwright or the in-page chat); then rehearse May's 2,047 on the live page.
5. **Not yet reported:** error and recovery rate, the 218-utterance set, gates on/off ablation, pass^k, a screen-only baseline.
6. **Adopt from nova2:** durable session state, UI correlation work; **adopt on nova2:** v2 backend and slots-first calls.
7. **Possible agent work:** the failure families still seen on dev (carry-over of group_by and top_n, record views and status for "open lines", scenario switching); inspect with `eval.show_fail`.

## 10. Do not claim
A held-out score; any baseline comparison; that the API agent and VACP are integrated; that VACP closes the 50% gap (hypothesis only); that 58.1% generalises (dev, tuned, one run); Nemotron results (none exist); full-history invoices or M11 profit in ERPNext; that our bridge is VACP's official code; a currency for the amounts; causes for changes; dynamic pricing (not implemented).

## 11. Where things are
`/home/dheeraj/Agentic_Hackathon/`: `agent/`, `eval/`, `tests/`, `evidence/`, `traces/` (run logs and per-turn traces), `deck/`, `research/` (plans and literature), `data/` (WWI v1 and v2 packages, ERPNext loader), `README.md`, `PPT_UPDATE_CONTEXT_2026-10-11.md` (earlier deck context pack), `Sapience_Hackfest_Deck_v4 (1).pptx` (original), `Sapience_Hackfest_Deck_v5.pptx` (current).
