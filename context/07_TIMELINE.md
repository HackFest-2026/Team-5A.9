# Timeline (what was asked and what came of it)

## 8–9 Oct (earlier sessions, from the saved summary)
- Validated and explained the WWI data package (v1). Set up the local DeepSeek-R1-Distill-Qwen-32B on the LAN with an API key (llama.cpp built for CUDA 12.2; Ollama impossible on driver 535); wrote a connection guide.
- Asked why some measures were blocked (M07 always zero; M10/M11 currency not stated) and made the data more comprehensive for multi-step tasks: **v2 package** (analyze/resolve/related/contract/lookup, Analysis page, oracle, 46 chains, 218 utterances, 293-page retrieval set). Engine bugs fixed (text-sorted tie-breaks; scenario scope).
- Compared candidate ERPs (ERPNext, metasfresh, Bigcapital, OpenBoxes, IDURAR) and explained ERP vs data, VACP and API agents; planned both agents; ran literature and citation research with agents (`research/`).
- Planned and ran the **ERPNext load** (Docker): masters, opening stock, purchase orders, sales orders, then stock flow (receipts + invoices), closing stock reconciliation, synthetic case.

## 9–10 Oct
- Load speed: tuned MariaDB live; four parallel sales-order workers with explicit names (the order counter row was the bottleneck). Invoices ran at about 1/s and falling (valuation reads history).
- User could only spare 3 more hours; chose to stop. The planned stop at 31 Dec 2015 did not trigger (kill failed); stopped by hand at **24 Feb 2016**. Reconciliation found 20 missing invoices (14 on the cut day, 6 earlier, cause unknown); loaded them; re-ran → **8 of 8** PASS.
- Built `wwi-transfer.zip` with an ERPNext backup; wrote `data/TRANSFER.md`. Restored ERPNext on nova2 (`10.9.0.108:8081`); counts matched.
- Exposed ERPNext on the LAN; explained login (Administrator, not email) and the portal vs `/app`.
- Wrote a VACP-on-ERPNext prototype and tested it on nova2: 23 of 23. (Bugs fixed on the way: filters ignored when a list is already open; saved list filters; count label cap.)
- Final sweep on API-agent papers; added the Beyond Browsing Figure 4 story and the WebArena-Verified decision to the plan; wrote `research/01_API_AGENT_BUILD_PLAN.md`.
- An agent (`agent/`, `eval/`, `tests/`) and dev results appeared on this machine, dated 10 Oct 16:18–17:54.

## 11 Oct
- User built a parallel "Sapience" implementation locally and put a handoff zip on nova2. I read it, found it built on **v1**, and wrote a comparison and recommendations note into `API_BASED_AGENT/`. Team name confirmed: Sapience.
- The machine had rebooted; services were down. Restarted DeepSeek on GPU 1, rebuilt the v2 virtualenv, started the WWI API, exposed it on `10.9.0.105:8017`, ran the agent end to end.
- Wrote `PPT_UPDATE_CONTEXT_2026-10-11.md` for a separate conversation updating the deck.
- Answered: where the agent lives (nowhere yet), why only four pages, whether ERPNext's schema was followed (audit above).
- **Embedded the agent:** redesigned the console, added Browse lists, built `agent/server.py` and the assistant panel; browser test passes; added `start_all.sh`.
- Clarified CRUD and users in ERPNext; read nova2's new ERPNext VACP bridge (202 of 203 checks pass); proposed the joined loop, then **put it on hold at the user's request**.
- Explained the three companion ideas (Tool Illusion, LedgerAgent, Mingbird).
- **Built the ledger/journey infographic** (data-driven, with browser confirmation) after the user's reference image.
- Compared ERPNext and console features; explained why the console is read-only and how chart creation and CRUD could be added.
- Created this `context/` folder.

## 12 Oct
- Asked: which ERPNext features to use natively with a reskin, CRUD in the existing app, and a ledger view that shows the real steps and pages instead of a constant picture.
- **Workspace CRUD built and tested** (22 of 22 checks): separate store, review-before-save, audit log, soft delete, revert, draft orders.
- **Ledger replaced by the real trail** (variable steps, who/when/where/exact values, page opened and read in the browser, step log, path strip). Browser test extended (a second question yields its own trail); passes.
- Found two agent defects while testing (see `06_OPEN_WORK.md`): a "stock position" question answered with unpicked units, and a carried-over comparison scope.

- **Chart builder built and tested** (28 of 28 checks). Deck v9 built from v5 with VACP additions (slides 8, 11, 12, 13 new, 14, 15, 21); `context/08_VACP_ADDITIONS.md` lists what nova2 added to the VACP repo. The machine rebooted around 15:13 on 12 Oct (services restarted with start_all.sh); the other session's evaluation run was interrupted by it.

## What the user has repeatedly stressed
Little time left; make it work and look professional; show it intuitively (judges); keep honest status; keep the agent built into the app; keep private notes private.
