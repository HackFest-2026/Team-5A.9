# Open work, in suggested order

Effort figures are my estimates. Held for the user's go-ahead: the **joined API + VACP loop** (paused on request).

## Before any demo
1. Rehearse the demo path end to end after a cold start (`./start_all.sh`), including the first ERPNext navigation (nova2's one failing check).
2. Decide the open questions in `02_DECISIONS.md` (cloud vs local model, held-out timing, VACP licence, deck counts, AI disclosure).
3. Confirm the unchecked answers shown in the chips (unpicked items, top-5 customers) against the answer key.

## Build (suggested order)
| # | Item | Effort | Notes |
|---|---|---|---|
| 1 | **Joined API + VACP loop** (on hold) | 3–5 h first loop | Load our assistant panel into the ERPNext Desk with nova2's nginx `sub_filter`; `/ask` returns `ui_actions`; panel executes via `window.__vacp.execute` and reports back; finish gate compares the API figure with `desk_view.matches_query`. Start with orders-in-a-period (M01). Measure map: M01 → Sales Order by `transaction_date`; M04 → Bin; revenue stays caveated. |
| 2 | **Chart builder** in the console | ~0.5 day | Builder page, saved definitions in a separate store, "My charts", agent tool with confirmation. Safe: no data changes. |
| 3 | **ERPNext adapter with per-user API keys** | ~1 day | Read-only; show "signed in as"; test that a restricted user sees less. |
| 4 | **Guarded write in ERPNext** (draft Sales Order) | 0.5–1 day | Read-before-write gate, confirmation card, drafts only, audit log. |
| 5 | ~~CRUD in our app (workspace overlay)~~ | done 12 Oct | See `01` and `04`. Remaining: let the agent open a pre-filled form (with confirmation); ERPNext-side guarded write is item 4. |
| 6 | Real-page retrieval over ERPNext | ~0.5 day | Index its 384 lists, 189 reports, 22 workspaces for a genuine hundreds-of-pages test (today's 293 are mostly decoys). |
| 7 | Latency | varies | 31–76 s per answer with R1-32B. Options: Qwen-14B (weak), streaming steps, caching, shorter drafts. |

## New ability (12 Oct): the assistant proposes charts
- Question-to-chart proposal with a confirm step. Known reading issue: "April and May" in one question is read as April (current) against May (baseline), which is a valid reading but may not be the one meant. Consider asking when two months are named without "compared".
- Next abilities in the same pattern: draft order (needs customer and item resolved, then confirm), edit a chart's title by message.

## Defects found while testing the trail (12 Oct; not fixed)
- **"Show the stock position of USB missile launcher (Green)"** was read as M02 (stored unpicked units) and answered "0 units across all history". The label "stock position" is wrong for that measure; stock on hand (175,609 in the source) is not what was reported. The new trail shows the slip (Read the question → M02). Needs a glossary mapping for "stock position / stock on hand" to a holdings view, or a clarify.
- **Carried-over scope:** in one conversation, "How many orders did Great Lakes place in May 2016?" after a comparison question was answered as a comparison (+65 vs April) because the comparison scope was kept. Designed behaviour ("scope kept after a verified answer"), but surprising for a new question; consider dropping `compare` when the user states a single period and no "compare/vs/than".
- Answer latency varied from 6 s to 31 s in tests today (the model was shared with other load); earlier figures of 31–76 s are in `01`.

## Evaluation
- **Gates-off ablation** (`--gates off`) so each gate's contribution is measured.
- **Held-out run** (15 chains) once, after freezing code, prompts and model; report with `pass^k` (k=3).
- **Brain14 probes against v2** to confirm the expected fixes.
- **WebArena-Verified**, one site (Shopping Admin) plus the hard subset, reported with full configuration; about 100 GB of images, so optional.

## Housekeeping
- Sync the new console, agent service and docs to nova2 and rebuild `wwi-transfer.zip`.
- Change the default ERPNext passwords before sharing the machine; create a read-only agent user.
- Auto-start services on boot (systemd or cron `@reboot`).
- Investigate nova2's first-navigate failure (`/app/home` instead of the Sales Order list).
- Reconcile Sapience's v1 backend with v2 (see `PLAN01_RECOMMENDATIONS_2026-10-11.md` on nova2).
- Deck: another conversation updates it from `PPT_UPDATE_CONTEXT_2026-10-11.md`; refresh that file after any change here.
