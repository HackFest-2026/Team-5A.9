# Story and design

## The thesis
> "API-only agents fail on about half of real tasks because the endpoint does not exist. Screen-only agents fail because they click blindly. Sapience gives one agent both: a typed API to *read and analyse*, and VACP to *act inside the app*. Each covers the other's gap."

Analogy for an audience: an analyst with a **calculator** (API: exact numbers, cannot show anything) and a **colleague who can drive the app** (VACP: operates the real screen, poor at arithmetic). Together the answer is correct and the user sees it.

## The evidence behind the gap (Beyond Browsing, Findings of ACL 2025, Figure 4)
100 sampled WebArena tasks, API-only agent: **33% correct, 50% unsolvable because the needed endpoint does not exist**, 11% API-usage errors, 6% task misunderstanding. On the API-solvable half, 66% were right. "Unsolvable" means a missing endpoint, not poor reasoning. Per-site coverage: GitLab 988 endpoints (good), Map 53, Shopping 556 (fair), Reddit 31 (poor); adding 13 hand-written Reddit endpoints raised success from 9.4% to 18.9%. Agent types: browsing 14.8%, API-only 29.2%, hybrid 38.9%.
**Our claim (a hypothesis, not a result):** typed, declared in-app actions fill the missing-endpoint gap more reliably than blind clicking. VACP's own "near-perfect" result has not been independently replicated; say what we measured on our own app.

## Two channels and a routing rule
- Analytic question (compare, trend, rank, total) → **API** (`analyze`).
- Operate or show the app (go to, filter, open) → **VACP action**.
- Both → the API answers, VACP puts the user on the matching page.
- No endpoint exists → a declared VACP action.
- **Strongest demo moment:** the API's figure and the number read back from the real page agree (April 2016 = 1,951). Two independent channels confirm each other. In the console this already happens (step 08 of the journey); across the ERPNext Desk it is the on-hold "joined loop".

## What each VACP part is (for explaining it)
`getCapabilities` is the **menu** (the buttons that exist here); `getState` is the **screen** (what is open now, with which filters); `execute` **presses a button** and reports what actually changed. Invalid requests are rejected and the screen does not change.

## The four-paper design (we borrow ideas, not code)
| Paper | What it gives | In our code |
|---|---|---|
| **Beyond Browsing** (API-based web agents) | The agent shape: call APIs from documentation; two-stage doc retrieval for large APIs; hybrid fallback | `agent/loop.py`, `agent/docs.py` |
| **The Tool Illusion** (+ Beyond Text-to-SQL) | A **small set of hand-written, task-level tools**: one `analyze(...)` call instead of six raw steps; server does the filtering and arithmetic. Human-crafted tools lifted WebArena success by 12.7–19.6 points across five models; generated tools helped little | `agent/tools.py` (six tools) |
| **LedgerAgent** (+ Reason Less, Verify More) | A **ledger** of facts actually observed (IDs, values), recorded only from successful reads and shown every turn; code checks before acting; `must_read_before_write` | `session.py` registry, `gates.py`, `facts.py`, `ledger.py` |
| **Mingbird** | A **finish gate**: the agent cannot say "done" until a check passes; loop detection; rescue malformed calls (its gate re-reads the task; ours is stricter and code-only) | `agent/finish.py` |

Caveats: the papers' reported gains are their own self-built benchmarks (some single runs; LedgerAgent got worse in one domain), so they do not transfer automatically. We have **not** run gates-off, so the individual contribution of each is unproven.

## Journey and ledger (what the infographic shows)
The infographic is the **real trail** of the question (changed 12 Oct; it used to be a fixed eight-step picture). Its length varies: a question with a name adds a "Called resolve" step; a follow-up says the earlier scope was available. Every step names who did it (You / Language model / Code check / Data API / This page), the time since the question, the endpoint or page, and the exact values (arguments, totals, filters, page heading, figures read from the page). A "Where it went" strip shows the path (Assistant panel → POST /api/analyze → #/analysis). Built from the agent's trace events and tool calls; the last three steps are added by the browser. The ledger table lists the only values the answer may use, marked "tool result" or "computed by code" (+96 = 2,047 − 1,951; percentages never computed by the model). "Follow up" here means the scope is kept, or reused from the earlier turn. The last step compares the page's figures with the answer for both comparison and single-total answers; for other pages it confirms the page loaded without an error.

## The 90-second demo
1. Ask "How many orders in April 2016, and show me." Trace shows **API: 1,951**, then **VACP: Sales Order list, April 2016, 1,951**, then "both channels agree". (The ERPNext half needs the joined loop; today the console half works.)
2. Ask something invalid (status "Almost Done"). VACP refuses; the screen does not change.
3. Open the VACP overlay and show the menu of allowed actions.
Deck: three boxes, *Brain (Sapience agent) → Eyes (API: knows) and Hands (VACP: does)*, above the Figure 4 chart.

## The design-for-agents rules we use (API structure)
Task-level operations, not raw tables; few, well-named tools; typed and enumerated parameters; one worked example per tool; echo the applied state in every response; errors that say how to recover; complete endpoint coverage. No controlled study found showing one *format* (OpenAPI vs YAML) beats another; the evidence is about content and coverage.

## Other research kept for reference
WALT (tool learning from sites), Plan-Then-Execute (81% of WebArena tasks solvable by a typed programmatic plan), Callability Is Not Operability (valid call ≠ usable interface; state echo and postconditions), WebArena-Verified (deterministic evaluator, 812 tasks, hard subset). Files: `research/api_agents_literature.md`, `citation_chase.md`, `erp_data_comparison.md`, `00_SYNTHESIS_PLAN.md` §9.
