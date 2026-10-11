# State and evidence

Tags: **[VERIFIED]** seen running on 10–11 Oct. **[RECORDED]** read from a saved result file, not re-run. **[NOT MEASURED]** do not claim.

## 1. Data
- **WWI sample** (Microsoft Wide World Importers): 21 source tables, 73,595 sales orders, 231,412 order lines, 2013-01 to 2016-05. Raw Parquet in `data/wwi-package-v2-2026-10-08/data/raw/` (identical to v1's raw data).
- **v1** (`data/wwi-data-v1-2026-10-08/`) is untouched. **v2** adds: `analyze`, `resolve`, `related`, `contract`, `lookup` APIs; an Analysis page; an independent oracle (`scripts/oracle_v2.py`, never imports the engine); 31 dev + 15 held-out multi-step chains (87 + 40 steps), 218 utterances, 150 retrieval queries over 293 pages (30 real, 263 synthetic decoys).
- **Measures:** M01 orders created, M02 unpicked units, M03 orders with unpicked, M04 stock on hand, M05 incoming units, M13 units ordered = verified; M10 revenue and M11 profit = published with a currency caveat (currency is not stated in the source); M07 rejected (always zero); M06, M08, M09 candidates.
- **Key story figures [VERIFIED]:** April 2016 = 1,951 orders, May = 2,047, +96 (4.92%); Great Lakes +65; item 80 holds 20 units. Synthetic fixture: item 1227, order 74595, 120 ordered, 20 in stock, nothing incoming.

## 2. ERPNext
- **ERPNext 15.119.3 / Frappe 15.118.0, MariaDB 10.6, site `frontend`, company "Wide World Importers".** Loaded through ERPNext's own insert/submit logic (loader in `data/erpnext-loader/`). **[VERIFIED]**
- **Counts:** 73,596 sales orders (73,595 WWI + 1 flagged synthetic), 64,500 sales invoices, 2,074 purchase orders, 1,914 purchase receipts, 663 customers, 228 items.
- **Data cut-off: 24 Feb 2016.** Invoices and receipts after that were deliberately not loaded (the stock-flow stage slowed to about 1 record/s as the stock ledger grew; the user chose to stop). Sales orders cover everything to 31 May 2016.
- **Reconciliation [VERIFIED]:** `data/erpnext-loader/reconcile_feb2016.py` → **8 of 8 PASS** (counts; M10 by month and total; M02 and M05 per item), expected values derived from raw Parquet. The older `reconcile.py` compares against all history and fails on purpose (9 fails); ignore it.
- **Schema audit [VERIFIED]** (`data/erpnext-loader/schema_check.py`, output `evidence/erpnext_schema_check.json`): across 12 document types and their child tables (40 tables): 0 missing mandatory fields, 0 broken links; general ledger balanced (193,500 entries, debits = credits); 0 negative stock; all 208,928 invoice lines linked to a sales order; all documents submitted; no custom DocTypes created. We added only `wwi_*` ID custom fields. Correct stock check = bin equals last running balance (228 of 228). *A naive sum-of-changes check fails because v15 stores stock reconciliations with zero change; that was a flaw in my test, not in the data.*
- **Fidelity limits:** only final holdings (M04) are faithful; running stock history is inflated (10 items passed 1M units before the closing reset; max 20.6M) because WWI's stock flows do not add up. Many-to-many stock groups sit in a custom field; ERPNext recomputes profit (M11 not comparable); USD is a placeholder; tax differs by cents.
- **Where ERPNext runs:** `http://10.9.0.105:8081` (this machine) and `http://10.9.0.108:8081` (nova2, restored from the zip). The working app is under `/app`; the page you land on after login (`/home`) is the customer portal.
- **Names:** sales orders `SAL-ORD-2026-…` (first ~26,000) and `SO-WWI-<id>` (rest; explicit names avoid a shared-counter lock); invoices `ACC-SINV-2026-…`.

## 3. The agent [built here, 10 Oct; I found it and did not write it in this conversation]
- **Code:** `agent/` (about 3,700 lines with `eval/` and `tests/`): six tools (`lookup`, `resolve`, `analyze`, `records`, `related`, `open_page`), gates before each call, a code-checked finish gate, faithfulness check (every number traces to a tool result or code arithmetic), session carry-over. Plan: `research/01_API_AGENT_BUILD_PLAN.md`.
- **Dev results [RECORDED]** (31 dev chains = 87 steps, single run, k=1; **held-out NOT run**):

| Variant | Chain success | Step pass | Hallucinated actions | Latency/step |
|---|---|---|---|---|
| Qwen2.5-14B emits the calls | 6.5% | 34.5% | 23.0% | 20 s |
| DeepSeek-R1-32B emits the calls | 9.7% | 27.6% | 3.4% | 32 s |
| **R1-32B extracts slots; code builds the calls** | **41.9%** | **70.1%** | **2.3%** | **8 s** |

  Best run also: destination 71.3%, UI state 74.7%, resolution 98.9%, analytic 77.0%, faithfulness 100%. The slots design was built after seeing dev failures, so it may be tuned to dev. **No gates-off ablation has been run** (`--gates off` exists).
- **Retrieval [RECORDED]** (140 queries, DeepSeek two-stage): exact-page hit@1 61.4%, hit@3 73.6%, hit@5 77.9%, MRR 0.677 (lenient hit@1 70.7%). Note: only 11 real pages in our app; the rest of the 293 are decoys.
- **Live demo [VERIFIED 11 Oct]:** 16 unit tests pass; "orders May vs April by territory" → +96 (4.92%), Great Lakes largest; follow-up → Great Lakes +65 (Michigan +28, Ohio +14, Wisconsin +14). Only +96, 4.92%, +65 and the 1,951/2,047 counts were checked against the key. Two more suggested prompts (unpicked items, top-5 customers) return answers; their numbers are unchecked. Latency with R1-32B: 31–76 s per answer; one question at a time.

## 4. The console and embedded assistant [VERIFIED 11 Oct]
- **WWI console** (`data/wwi-package-v2-2026-10-08/app/`; originals backed up in `app.orig-2026-10-11/` and `scripts/serve_v2.py.orig-2026-10-11`): redesigned shell; 9 sidebar entries; 16 routes (4 analytics pages, 5 browse lists, 7 detail pages). Browse lists with name search; overview chart now shows the full 2013–2016 trend.
- **Assistant:** `app/assistant.js/.css` plus `agent/server.py` (HTTP service). Asking opens the Analysis page itself with filters set.
- **Trail and ledger infographic [VERIFIED in browser test]:** `agent/ledger.py` builds the **real trail** of each question, a variable number of steps in the order they happened: You asked → Read the question (model slots) → Resolve names (if any) → Built the exact request (code) → Called each tool (endpoint, arguments, result, time) → Checked the result (finish gate) → Wrote the answer (draft pass/fail) → Answer ready → then, in the browser, Opened the *named* page → Read the page (heading, scope line, rows, figures) → Compared with the answer. Each step names who did it (you / model / code / data API / this page), when, where and the exact values, with a "where it went" path and an expandable step log. Before 12 Oct this was a fixed eight-step picture (Ask … Confirm) that looked the same for every question. Tests: `eval/ui_test.py` (a second, different question yields its own trail).
- **Workspace CRUD [VERIFIED, 22 of 22 browser/API checks]:** `scripts/workspace.py` + `/api/ws/*` in `serve_v2.py`, UI in `app/workspace.js`. New customer, supplier, stock item and draft order (with lines and an item search); edit any source customer/supplier/item as an overlay (only changed fields stored); soft delete and restore; revert to source; activity log. Review step before every save; writes need the header `X-Sapience-Write: 1`; server validates (required, length, references exist, quantities). Stored in `data/wwi-package-v2-2026-10-08/workspace/workspace.db` (separate from the source; delete the file to reset). Tests: `eval/ws_test.py`. Analytics and the agent do not read the workspace.
- **Browser test** `eval/ui_test.py`: all checks pass (every page, search, assistant, journey, no console errors). Screenshots: `evidence/ui_screenshots/` (14 files).
- **Bugs found and fixed:** search form reloaded the page (async handler returned a Promise); a CSS class clash tinted the page; Analysis page showed the previous page's content while loading.

## 5. VACP on ERPNext
- **nova2's bridge [RECORDED + partly VERIFIED]:** `VACP/packages/examples/erpnext-bridge` (about 1,200 lines, built on VACP's kit), injected via an nginx `sub_filter` (`compose.vacp.yml`). Actions: `navigate`, `open_record`, `set_period`, `set_filters`, `clear_filters`, `set_page`, `reset`, `query` (with `desk_view.matches_query`). Bundle live at `http://10.9.0.108:8081/vacp/vacp-bridge.js` [VERIFIED]. Its test `test_erpnext_vacp.py`: **202 of 203 pass** [VERIFIED]; the one failure is the first `navigate` landing on `/app/home` (possibly startup timing; not investigated). Read-only guarantee held (row counts unchanged).
- **My prototype [VERIFIED]:** `data/erpnext-loader/spike_vacp_erpnext.py`, own `window.__vacp` (not VACP's kit), 23 of 23 checks vs SQL. Superseded by nova2's bridge for real use.
- **Their listed limits:** Customer and Supplier forms cannot open (FiscalYearError, no fiscal year covers 2026); realtime push broken; every invoice shows overdue (no payments); lists take ~5–6 s to refresh under a date filter; the Desk's count label caps at "1,000+".
- **VACP repository has no licence file.** Its source is used on nova2; our own earlier decision was to reuse the design, not the code. Unresolved.

## 6. The Sapience build on nova2 (the user's parallel local build)
- Zip `Sapience_Server_Handoff_2026-10-11.zip` extracted in `/home/nova2/hackathon/API_BASED_AGENT/extracted/`. Read, not re-run. Same six tools; **built on WWI v1** (v1-derived `serve.py`, v1 catalog; no `analyze`/`resolve`/`related`). Its own audit (Brain14) lists open defects: filters ignored, capped groups marked complete, unstable ties, weak finish proof, no durable sessions, no live hosted-model success. It has a vanilla UI with correlation fixes (11/11 UI tests reported), a MariaDB session-store design, cloud-only model policy.
- Comparison note placed at `/home/nova2/hackathon/API_BASED_AGENT/PLAN01_RECOMMENDATIONS_2026-10-11.md`.

## 7. Not done [NOT MEASURED]
Held-out evaluation; any baseline or gates-off comparison; joined API+VACP loop; per-user ERPNext access for the agent; agent-driven writes; chart builder; ERPNext writes; durable session state; WebArena-Verified runs (researched only, about 100 GB of images); Brain14 probes against v2.

## 8. Evidence index
| Path | Proves |
|---|---|
| `data/erpnext-loader/evidence/reconciliation.json`, `reconcile_feb2016.py` | ERPNext vs answer key |
| `data/erpnext-loader/evidence/erpnext_schema_check.json`, `schema_check.py` | ERPNext schema integrity |
| `data/erpnext-loader/evidence/vacp_erpnext_spike.txt` | my VACP prototype, 23 of 23 |
| `evidence/dev_chains_*.json`, `retrieval.json`, `traces/` | agent dev results and per-turn traces |
| `evidence/ui_screenshots/` and `eval/ui_test.py` | console, assistant, ledger infographic |
| `/tmp/erpnext_vacp_test.log` on nova2 | nova2's 203-check run (not durable) |

## Additional evaluations, 11 Oct 2026 (R1-32B, slots mode, R1-written answers; files in `evidence/`) [MEASURED]
- **Held-out, 15 chains, run once** (`heldout_slots_r1.json`): 20.0% of chains (3 of 15), 52.5% of steps, destination 52.5%, UI state 55.0%, analytic 60.0%, faithfulness 100%, hallucinated actions 5.0%, 13.6 s per step. Dev numbers overstate generalisation; main failure is the wrong measure (M13 for M01 on "order volume").
- **Gates off, dev** (`abl_gates_off_r1.json`): 51.6% of chains (16 of 31), 74.7% of steps, hallucinated actions 6.9%; with gates 58.1% (18 of 31), 4.6%. One run, a two-chain difference.
- **Pass^3, dev** (`passk3_r1.json`): pass@1 58.1%, pass^3 58.1%, so the same 18 chains passed every time. Steps 75.9%.
- **Single-turn utterances, dev, 218** (`dev_utts_r1.json`): intent 85.3%, slots 81.7%, resolution 99.5%, view 79.8%, totals 75.7%, overall pass 64.2%, faithfulness 100%, hallucinated actions 4.1%, 20.3 s.
- **Model-emits-calls, dev, same code** (`ctl_llm_r1.json`): 38.7% of chains.
- **WebArena:** not run. CMU and archive.org mirrors return 403; Google Drive returns a download-quota error; Docker storage on `/` has about 20 GB free.
