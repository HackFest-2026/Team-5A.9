# Context pack for updating the Sapience deck (11 Oct 2026)

Read this file first, then only the files in §7. It is written for a fresh conversation that must update the existing deck with what has been built since the v4 deck was made. Every claim has a status tag. **Do not turn an unverified item into a result.**

## 0. Rules you must follow
- **Team name is Sapience** (not "Sapiens"; the older `Sapiens_*.pptx` files are out of date).
- **Do not read `Do_not_open/`** (private notes). If you already have, disregard it.
- **No claude.ai artifacts.** Edit the .pptx itself.
- **Font size 15 pt or larger** everywhere in the deck, footers and source notes included.
- **Edit a copy:** save as a new file (for example `Sapience_Hackfest_Deck_v5.pptx`). Never overwrite the v4 file.
- **Keep the deck's honesty convention.** v4 labels things "proposed", "planned" or "pending" until measured, and says "Targets are not achieved results". Keep that. Anything marked [NOT MEASURED] below stays "pending".
- **No personas in the deck.** This was a decision recorded in the Sapience handoff notes; confirm with the user if unsure.
- **Prefix shell commands** with `wsrun --student 01fe23bcs197` (that exact flag) if you run any.
- **Check the result visually** by rendering slides to images. Look for text overflow, overlapping shapes and any font under 15 pt.

## 1. The deck to update
- **File:** `/home/dheeraj/Agentic_Hackathon/Sapience_Hackfest_Deck_v4 (1).pptx`. It has 13 slides and was saved 11 Oct, 10:08.
- **Older decks** (`Sapiens_*`) are history. Ignore them.
- **Outline and what v4 currently says:**

| # | Title | Current wording that is now out of date |
|---|---|---|
| 1 | Cover | Keep (team names/USNs already correct) |
| 2 | What are we trying to solve? | Fine |
| 3 | Existing approaches (GUI/browser, API/tool, application-native) | Fine; could add the Figure 4 point (§3) |
| 4 | Proposed solution | "Proposed integrated behavior" |
| 5 | Objectives | Targets: **15 of 18** held-out tasks, 100% faithful, 100% context, 0 false completion. See the conflict in §5 |
| 6 | System architecture | "Business API and UI-context components exist; integration remains pending" |
| 7 | Example workflow | Verified April 1,951 / May 2,047 / +96 / 4.92%; "integrated assistant workflow remains proposed" |
| 8 | Context and state persistence | Planned, not built |
| 9 | Why is our solution better? | "Comparative performance has not yet been measured" |
| 10 | Dataset information | WWI, 21 tables, 73,595 sales orders, 231,412 order lines, 2013–2016. "ERPNext / Frappe: workflow reference, native mapping planned" |
| 11 | Evaluation plan | WebArena (812 tasks) plus "12 + 18 development + held-out tasks". See §5 |
| 12 | Research references | 8 references |
| 13 | Data sources and AI disclosure | Lists "OpenAI Codex" only. See §5 |

## 2. Evidence ledger (what is true now, and how sure we are)
Status tags: **[VERIFIED]** I ran it on 10–11 Oct and saw the output. **[RECORDED]** read from a saved result file, not re-run. **[NOT MEASURED]** don't claim it.

### Dataset and ERPNext
- **[VERIFIED]** ERPNext 15.119.3 (Frappe 15.118.0), MariaDB 10.6, running with the WWI data loaded through ERPNext's own business logic:
  - 73,596 sales orders (73,595 WWI + 1 clearly flagged synthetic case: item 1227, 120 ordered, 20 in stock, nothing on order);
  - 64,500 sales invoices; 2,074 purchase orders; 1,914 purchase receipts; 663 customers; 228 items.
- **[VERIFIED] Scope is data through 24 Feb 2016.** Invoices and receipts after that date were deliberately not loaded (user decision, to save time). Sales orders cover all history to 31 May 2016. Say this on slide 10; don't say ERPNext holds the "full" history.
- **[VERIFIED]** Reconciliation against an independent answer key (the `oracle_v2` scripts read the raw files): **8 of 8 checks pass** (`reconcile_feb2016.py`):
  - orders per month and units ordered, exact (41 months);
  - invoiced sales before tax per month and in total, to the cent;
  - stock on hand for all 228 items;
  - units still to pick, per item;
  - units on order, per item.
- **[VERIFIED]** Stories: April 1,951 vs May 2,047 orders (+96, 4.92%); Great Lakes +65; item 80 holds 20 units.
- **Caveats to keep:** WWI states no currency, and ERPNext needed one, so USD is a placeholder, and answers keep the label "currency not stated in source". ERPNext recomputes profit, so M11 profit isn't comparable. Tax differs by cents because of rounding.
- **Live at** `http://10.9.0.105:8081` (this machine) and `http://10.9.0.108:8081` (nova2). Use `/app`, not the portal page.

### The API-based agent (built on this machine, 10 Oct)
- **[VERIFIED, 11 Oct]** It runs end to end: the 16 unit tests pass, and a live two-turn demo with DeepSeek-R1-32B answered:
  - "orders May vs April by territory" → +96 orders (4.92%), Great Lakes the largest contributor, with an in-app link;
  - the follow-up "which states inside Great Lakes moved" → +65, with Michigan +28, Ohio +14, Wisconsin +14.
  - Only +96, 4.92% and +65 were checked against known values; the state figures and territory shares were not.
- **Design:** six task-level tools (`lookup`, `resolve`, `analyze`, `records`, `related`, `open_page`), gates before each call, a code-checked finish gate, and a faithfulness check that every number traces to a tool result. Model arithmetic is never used.
- **[RECORDED] Dev-split results (31 multi-step chains = 87 steps; single run; held-out NOT run):**

| Variant | Chain success | Step pass | Hallucinated actions | Latency/step |
|---|---|---|---|---|
| Qwen2.5-14B emits the calls | 6.5% | 34.5% | 23.0% | 20 s |
| DeepSeek-R1-32B emits the calls | 9.7% | 27.6% | 3.4% | 32 s |
| **R1-32B extracts slots; code builds the calls** | **41.9%** | **70.1%** | **2.3%** | **8 s** |

  - For the best run: destination 71.3%, UI state 74.7%, resolution 98.9%, analytic 77.0%, faithfulness 100%.
  - **Caveat:** the best variant was designed after seeing dev failures, so it may be tuned to dev. Say "development set, single run". It is not the held-out score.
- **[RECORDED]** Retrieval over 293 pages (140 queries): exact-page hit@1 61.4%, hit@3 73.6%, hit@5 77.9%, MRR 0.677; lenient hit@1 70.7%.
- **[VERIFIED, 11 Oct] The agent is now embedded in the application.** The WWI console at `http://10.9.0.105:8017` was redesigned (professional look; all pages in the sidebar) and has a side panel, "Sapience Assistant", that calls the agent service (`http://10.9.0.105:8018`, `agent/server.py`; `POST /ask`, `GET /health`). Asking "How did orders in May 2016 compare with April, by territory?" in the panel opens the Analysis page with the filters set, states +96 (4.92%), and lists the actions taken. The follow-up in the same conversation (Great Lakes states, +65) also works. A headless-browser test, `eval/ui_test.py`, passes all 19 checks (every page renders, search works, the assistant answers and navigates, no console errors); screenshots are in `evidence/ui_screenshots/`.
- **The console's pages:** 4 analytics pages (Overview, Fulfilment, Supply, Analysis) plus 5 browse lists (Customers, Orders, Stock items, Suppliers, Purchase orders), each opening a record detail page (customer, order, order line, item, supplier, purchase order, purchase line). That is 16 routes; the original sidebar listed only 4 and the rest were reachable only from links inside tables.
- **Not yet embedded:** ERPNext's Desk has no assistant panel; the VACP bridge there is still a separate prototype. The assistant answers from the WWI data API, not from ERPNext.
- **Run everything after a reboot:** `./start_all.sh` (model on :8090, console on :8017, agent on :8018).

### VACP on ERPNext
- **[VERIFIED]** A prototype bridge, injected into the stock ERPNext Desk with no rebuild, passed **23 of 23 checks** against SQL on nova2:
  - navigate with no reload;
  - set period (April 2016 = 1,951) and status/customer filters, matching SQL;
  - five invalid calls refused with the URL unchanged;
  - net sales Dec 2015 = 4,458,811.25; a grouped query of 2,048 orders; browser Back; hard reload.
- **Caveats:** it is our own `window.__vacp`, not VACP's kit. Tested in headless Chromium on Sales Order and Sales Invoice lists only, and territory filtering is untested. The VACP repo has no licence file. One call took 10.4 s (an unexplained outlier); typical latency is 0.4–1.2 s.
- **[NOT MEASURED]** VACP's own "near-perfect" result (its paper) hasn't been independently replicated.

### The Sapience build on nova2 (read, not re-run by us)
- **Present:** a canonical read-only WWI API, a vanilla web workspace with UI-correlation fixes, a hosted-model transport, a state-persistence design.
- **Their own reports:** 65 Python tests passed, 11 of 11 UI tests, and a browser walkthrough.
- **[RECORDED] Their audit lists unfinished items:** filters ignored, groups capped but marked complete, finish proof, route lifecycle, a model loop on the old parser, no durable sessions, no live hosted-model success. It is built on WWI v1, not v2.

### Not done yet (keep "pending" in the deck)
- **The held-out evaluation:** 15 chains; no run.
- **The joined API + VACP agent:** the agent is embedded in the WWI console, but it does not yet drive ERPNext through the bridge, and ERPNext has no assistant panel.
- **Durable session state** (MariaDB) and the assistant UI panel.
- **WebArena-Verified runs:** researched only; nothing run (the stack is roughly 100 GB of images).
- **Any comparison against a baseline** (screen-only agent, or an agent with gates off).

## 3. Story for the unified solution
- **Thesis:** one agent, two channels. The API is for **knowing** (exact analysis over all rows); VACP is for **doing and showing** (operating the real app). Each covers the other's gap.
- **The gap evidence:** Beyond Browsing (Findings of ACL 2025, Figure 4) sampled 100 WebArena tasks for an API-only agent:
  - 33% correct;
  - **50% unsolvable because the endpoint doesn't exist**;
  - 11% API-usage error; 6% misunderstanding.
  - On the API-solvable half, 66% were right.
  - Its hybrid agent (API + clicking) reached 38.9%, against 29.2% API-only and 14.8% browsing-only; the hybrid fell back to raw clicking.
- **Our claim (a hypothesis, not a result):** typed, declared in-app actions fill the missing-endpoint gap more reliably than blind clicking.
- **Routing rule:** analysis → API; operate or show the app → VACP action; both → the API answers and VACP puts the user on the matching page; no endpoint → a declared VACP action.
- **The strongest demo moment:** the API's total and the number read back from the real ERPNext page agree (April 2016 = 1,951). Two independent channels confirm each other. (May's 2,047 on the page still needs a rehearsal run.)
- **Honest wording to use:** "both channels are built and verified individually; joining them is the last step." Not "fully integrated".

## 4. Suggested edits (slide by slide)
- **4, 6:** keep "proposed" language for the unified runtime. Add "API agent and ERPNext VACP bridge implemented and individually verified (development set)".
- **7:** keep the verified April/May figures. Add one line that the same totals were read back from the live ERPNext page (April = 1,951).
- **9:** keep "not yet measured" for comparative claims, but add the dev table in §2 as measured evidence for the "code builds the calls" design choice.
- **10:** replace "native mapping planned" with the loaded ERPNext facts in §2, including "data through 24 Feb 2016" and the reconciliation result.
- **11:** add the real task counts and the dev results; keep the held-out run as pending.
- **12:** consider adding WebArena-Verified (ServiceNow, NeurIPS 2025 workshop), WALT (arXiv 2510.01524), Plan-Then-Execute (arXiv 2605.14290) and "Callability Is Not Operability" (arXiv 2608.23628). Check authors and venues on arXiv before adding; I did not verify author lists.
- **13:** see §5.

## 5. Conflicts the user must decide (do not guess)
1. **Task counts.** Slides 5 and 11 say "15 of 18" and "12 + 18 development + held-out tasks". The v2 evaluation set actually has **31 development chains (87 steps) and 15 held-out chains (40 steps)**, plus 218 utterances and 150 retrieval queries. The target "15 of 18" doesn't match 15 chains. Ask which set the deck should report.
2. **Model.** Slide 6 says "cloud model". The best results here come from a **local** DeepSeek-R1-32B. The Sapience handoff says cloud-only (OpenRouter or Ollama Cloud). Ask which to state.
3. **AI disclosure (slide 13).** It lists OpenAI Codex only. The work in this repo (ERPNext load, agent, VACP prototype, research notes) was done with Claude Code (Anthropic). The user should add it so the disclosure is accurate.
4. **Data scope wording (slide 10).** Source data is Jan 2013 to May 2016. ERPNext's invoices stop at 24 Feb 2016. Confirm the wording.

## 6. Do not claim
- A held-out score, or any accuracy comparison against a baseline.
- That the API agent and VACP are "integrated" or that "VACP closes the 50% gap" as a finding.
- That the 41.9% generalises. It's a dev-set number from one run.
- Full-history invoices in ERPNext, or M11 profit.
- That our bridge is VACP's official code.

## 7. Files to read, in order
On this machine (`/home/dheeraj/Agentic_Hackathon`):
1. `Sapience_Hackfest_Deck_v4 (1).pptx` (the deck).
2. `research/00_SYNTHESIS_PLAN.md` §9 (the story and WebArena standard) and `research/01_API_AGENT_BUILD_PLAN.md`.
3. `evidence/dev_chains_slots_r1.json`, `dev_chains_r1.json`, `dev_chains_full_r1.json`, `retrieval.json` (the dev results).
4. `data/erpnext-loader/evidence/vacp_erpnext_spike.txt` and `reconciliation.json`; `data/erpnext-loader/reconcile_feb2016.py`.
5. `data/wwi-package-v2-2026-10-08/evaluation/v2/README.md` (task sets) and `docs/V2_SPEC.md` (measures M01–M13).
6. `agent/` and `README.md` (only if code detail is needed).

On nova2 (`ssh nova2@10.9.0.108`, folder `/home/nova2/hackathon/API_BASED_AGENT`):
- `PLAN01_RECOMMENDATIONS_2026-10-11.md` (the comparison of the two builds) and `extracted/Sapience_Server_Handoff/Brain/08_COMPACT_CONTEXT.md`, `14_Corrective_Handoff_Review_2026-10-11.md`, `17_FINAL_SWEEP_AND_PRESENTATION_SOURCE_BRIEF.md`.
