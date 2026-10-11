# Reference Stack Gaps and KPI Impact

As of 2026-10-05. Source: the Domain 5A problem statement (Context-Aware Application Agent). The gaps are our analysis of the organiser's reference stack, not statements by the organiser.

## Summary

The reference stack covers how the agent **finds** the right component (vector index, RAG) and **calls** tools (LLM tool calling, Playwright). It is missing three things, and those are what decide the hardest KPIs:

- **Meaning:** a semantic layer that defines what each filter and measure means and records where each fact came from.
- **State:** an investigation that carries its context across turns and pages, with UI changes checked after they are made.
- **Honesty:** observed fact, calculated measure and inference kept apart, with every number traceable to a view.

## Gaps by layer

| ID | Layer | Gap | What goes wrong |
|---|---|---|---|
| G1.1 | Metadata | Describes shape but not meaning | The right widget is found but misread (orders vs lines, cartons vs units) |
| G1.2 | Metadata | Metadata can be wrong | Exported descriptions contradict the data (e.g. backorder direction); RAG repeats the error |
| G1.3 | Metadata | Static graph | No valid filter combinations, dependencies between filters, or order for setting state |
| G1.4 | Metadata | Drift | The index goes stale; links point to routes that no longer exist |
| G2.1 | Retrieval | Near-identical components | Similar "Orders" pages crowd each other out, so precision and MRR fall |
| G2.2 | Retrieval | Words only | Follow-ups like "its supplier" ignore what is currently selected |
| G2.3 | Retrieval | No "nothing fits" answer | A page is always returned, which leads to invented actions |
| G3.1 | Planning | Greedy, single-intent | No branching or re-planning in multi-step requests |
| G3.2 | Planning | Slots not checked | Invented IDs, dates and filter values |
| G3.3 | Planning | No carry-over between turns | Selection and filters are lost on follow-ups |
| G3.4 | Planning | Ambiguity guessed | The agent acts instead of asking a clarifying question |
| G4.1 | Text-to-query | Valid SQL, wrong meaning | Joins double-count demand; units and periods get mixed |
| G4.2 | Text-to-query | Query numbers differ from the screen | The answer contradicts the widget on the same page |
| G4.3 | Text-to-query | Weak safety | No read-only role, row or time limits, or tenant scoping |
| G5.1 | Orchestration | Fragile browser fallback | Selectors break; failed clicks go unnoticed |
| G5.2 | Orchestration | No check after acting | A filter fails silently and success is still reported |
| G5.3 | Orchestration | No recovery plan | No retry, rollback or return to a known state |
| G5.4 | Orchestration | All-or-nothing confirmation | No risk level per action: too many prompts or unsafe writes |
| G6.1 | Analysis | False cause and effect | "Likely causes" the data doesn't support |
| G6.2 | Analysis | Inconsistent comparisons | Mismatched populations, periods or units |
| G6.3 | Analysis | Faithfulness not built in | Numbers can't be traced back to a query or view |
| G7.1 | Data | Synthetic data lacks edge cases | No scenarios with different correct answers to test reasoning |
| G7.2 | Data | Utterances written by the team | Measured accuracy is higher than real use would show |
| G8.1 | Evaluation | Public benchmarks are only stand-ins | Nothing tests right page + right state + right answer together |
| G8.2 | Evaluation | KPIs undefined, no action trace | Results can't be defended, and invented actions can't be counted |
| G9.1 | UX | Fact and inference not labelled | Users re-check everything by hand |
| G9.2 | UX | Explanations only after the fact | Steps can't be inspected, edited or undone beforehand |
| G9.3 | UX | Latency stacks up | Sequential steps take 10–30 seconds per request |

## Gap-to-KPI mapping

● = main effect · ○ = secondary effect

| Gap | Intent → destination | UI-state correctness | Multi-step success / latency | Analytical faithfulness | Retrieval quality | Reliability & safety | UX |
|---|---|---|---|---|---|---|---|
| G1.1 Shape, not meaning | | ● | | ○ | ○ | | |
| G1.2 Wrong metadata | | | | ● | | | |
| G1.3 Static graph | | ● | | | | ○ | |
| G1.4 Drift | ● | | | | ○ | ○ | |
| G2.1 Near-identical components | ● | | | | ● | | |
| G2.2 Words only | ● | | | | ● | | ○ |
| G2.3 No "nothing fits" | ● | | | | | ● | |
| G3.1 Greedy planning | ○ | | ● | | | | |
| G3.2 Slots not checked | | ● | | | | ● | |
| G3.3 No carry-over | | ● | ○ | | | | ● |
| G3.4 Ambiguity guessed | | | ● | | | | |
| G4.1 Valid SQL, wrong meaning | | | | ● | | | |
| G4.2 Query ≠ screen | | | | ● | | | ○ |
| G4.3 Weak SQL safety | | | | | | ● | |
| G5.1 Fragile browser | | | ● | | | ○ | |
| G5.2 No check after acting | | ● | | | | ● | |
| G5.3 No recovery | | | ● | | | ● | |
| G5.4 Confirmation not tiered | | | | | | ● | ○ |
| G6.1 False cause and effect | | | | ● | | | |
| G6.2 Inconsistent comparisons | | | | ● | | | |
| G6.3 Faithfulness not built in | | | | ● | | | |
| G7.1 Thin synthetic data | | | ● | ○ | | | |
| G7.2 Team-written utterances | ● | | | | | | |
| G8.1 Benchmarks are stand-ins | ○ | ○ | ○ | ○ | ○ | ○ | |
| G8.2 KPIs undefined, no trace | | ● | | | | ● | |
| G9.1 Fact and inference unlabelled | | | | ○ | | | ● |
| G9.2 Explanations only after | | | | | | | ● |
| G9.3 Latency | | | ● | | | | ● |

The gaps cluster under **UI-state correctness**, **analytical faithfulness** and **reliability**. Retrieval is the only KPI the stack covers reasonably well. As specified, none of the KPIs can be measured: the stack has no exact definitions, no action trace and no set of known-good answers.

## Existing alternatives

Assessed from each project's GitHub README on 2026-10-05.

| Tool | What it is | Gaps it eases | Gaps it leaves | Licence / notes |
|---|---|---|---|---|
| [BrowserOS](https://github.com/browseros-ai/BrowserOS) | Chromium fork built for agents; MCP browser control; session replay | G5.1 partly; audit trail toward G8.2 | All of G1–G4, G6, G7; separate browser, not embedded in the app | AGPL-3.0 (modified network use must release source); heavy to run |
| [Terminal Browser](https://github.com/zenbu-labs/terminal-browser) | Chromium (via Electron) drawn inside a terminal; `terminal-browser action` CLI for agents; page recording | G5.1 marginally | All of G1–G4, G6, G7; terminal interface is wrong for business users | MIT; anonymous usage data on by default; full input needs a macOS Swift helper |
| Playwright (named in the brief) | Library for automating browsers in tests | G5.1 when scripted with checks | Everything above the action layer | Apache-2.0; best fit for a checked fallback |

All three can **operate** a UI but don't **understand** it. They have no model of the app, nothing to stop invalid UI state, and no grounded analysis. That is the space our solution targets.

## Gap coverage by prior work: VACP

Added 2026-10-08. VACP (Visual Analytics Context Protocol, arXiv 2603.29322, March 2026) is the closest published work to our design. It lets a visual-analytics app describe itself to an AI agent through an API: `get_state()` (current view and selection), `get_capabilities()` (interactions valid right now, with typed parameters), `get_schema()` and `inspect_data()` (data structure and queries), and `execute_interaction()` (actions validated before running, with snapshot IDs that reject stale actions). Optional state history allows reverting. The authors report about 95% task completion against 28–51% for screenshot and DOM agents, on 15 tasks across 5 apps, and list developer overhead, loss of visual cues and limited scale as limitations.

**Evidence boundary.** This mapping is based on the paper's abstract and a summary of its method and evaluation sections, not a full reading. Recheck the paper before the deck cites a specific feature.

**Result:** of the 28 gaps, VACP addresses 5, partly addresses 10 and leaves 13 untouched.

### Addressed by VACP (5)

| Gap | How VACP covers it |
|---|---|
| G1.3 No record of legal states | `get_capabilities()` lists the interactions valid right now, with typed and range-limited parameters |
| G2.2 Context ignored (words only) | `get_state()` gives the current view and selection on every step |
| G3.2 Slot values not checked | Every action's parameters are validated against type and range constraints before running |
| G5.1 Fragile browser clicking | Direct execution through the API; no clicking |
| G9.3 Latency | Reported fewer tokens and lower latency than screenshot or DOM agents |

### Partly addressed by VACP (10)

| Gap | What VACP gives | What's missing |
|---|---|---|
| G1.1 Shape, not meaning | Data schema and a semantic state graph | Business meaning: unit, level of detail, period |
| G1.4 Drift | State is read live from the app | The mapping is hand-maintained (the authors' stated developer overhead) |
| G3.3 No carry-over between turns | The app holds current state | Conversation memory across turns |
| G4.1 Valid SQL, wrong meaning | Structured data queries instead of free SQL | Declared measures that prevent wrong grain or units |
| G4.2 Numbers differ from screen | Inspects the app's own data model | No explicit guarantee that a figure equals the widget's value |
| G4.3 Query safety | No free SQL | Read-only scoping and limits not described |
| G5.2 No check after acting | Snapshot IDs reject stale actions, validated before running | No explicit read-back comparing requested and applied state |
| G5.3 No recovery | Optional state history allows reverting | No retry-then-undo policy |
| G8.2 No action trace or KPIs | Measured completion, tokens and latency | No trace-based KPI definitions |
| G9.2 No preview or undo | Revert via state history | No plan preview before acting |

### Not addressed by VACP (13), and our answer

| Gap | Our answer (report 04) |
|---|---|
| G1.2 Metadata can be wrong | Claim checks: SQL tests on each definition, with provenance tags |
| G2.1 Near-identical components | Whole Contract in the prompt at our scale; optional retrieval stress test |
| G2.3 No "nothing fits" answer | Routing can return "none fits"; known unsupported requests are listed |
| G3.1 Greedy planning | Cheap version: tool loop with a step limit |
| G3.4 Ambiguity guessed | `resolve_entity` asks when several matches exist |
| G5.4 Untiered confirmation | Two tiers; writes confirmed against the exact pending action |
| G6.1 False cause and effect | "Contributors", not "causes", unless a linking record exists |
| G6.2 Inconsistent comparisons | `compare_periods` applies one filter set to both periods |
| G6.3 Faithfulness not built in | Evidence IDs; a figure without a source blocks the answer |
| G7.1 Thin synthetic data | One labelled contrast scenario (no incoming supply) |
| G7.2 Team-written test phrasing | Held-out questions written by people outside the team |
| G8.1 Benchmarks only stand-ins | Our own task file, scored on the final state |
| G9.1 Fact vs inference unlabelled | Observed, calculated and inferred labels |

### What this means for our positioning

- **Don't claim the five VACP-covered gaps as our innovation.** Cite VACP for them.
- **Our differentiation lies in the 13 untouched gaps and the missing halves of the partial ones.** The strongest five:
  - meaning declared and tested (G1.1, G1.2);
  - read-back after acting (G5.2);
  - traceable figures (G6.3);
  - honest analysis (G6.1, G6.2);
  - fact and inference labels (G9.1).
- **Not fully solved by VACP or our build:**
  - G2.1 (scale): deliberately sidestepped at four pages.
  - G3.1 (planning): a cheap version only.
  - G7.2 (test phrasing): depends on recruiting outside testers.

  State these as limitations.

### Gaps that remain in VACP

What VACP still lacks for the brief, grouped by kind.

**Not in VACP at all**

| Gap | Why it matters for the brief | Our answer |
|---|---|---|
| No business meaning of measures (unit, level of detail, period) | The agent can find the right chart and still misread it, e.g. orders vs order lines, or cartons vs units | The Contract declares each measure's meaning |
| No checks that the metadata is true | If the app's own description is wrong (like WWI's backorder field), the agent trusts it | Claim checks: SQL tests on each definition |
| No traceable figures | Numbers in an answer can't be traced back to a view | Every figure tied to its measure, filters and period; untraced figures block the answer |
| No fact vs inference labels | Users must re-check everything by hand | Observed, calculated and inferred labels |
| No honest analysis rules | "Likely causes" can be invented, and comparisons can mix populations | "Contributors", not "causes"; one filter set applied to both periods |
| No "nothing fits" answer or clarifying question | The agent acts even when no view answers the question | Routing can say "none fits" or ask |
| No confirmation tiers for writes | Read-only analytics never needed them; business apps do | Writes confirmed against the exact pending action |
| No multi-turn memory | Follow-ups like "this item" or "same period" fail | Checkpointed conversation state |

**Only half-done in VACP**

| Gap | What VACP has | What's missing |
|---|---|---|
| Checking the result | Validates before acting and rejects stale state | No explicit read-back comparing requested and applied state, then retry or undo |
| Data access | Structured queries over the chart's data | No guarantee that the agent's figure equals the widget's own value |
| Recovery | Optional state history to revert | No retry-then-undo policy |
| Keeping in sync with the app | State is read live | The mapping to the app is written and maintained by hand |

**Evaluation gaps**

- **Small and narrow:** 15 tasks on research charting tools, not business workflows.
- **Five of the brief's seven KPIs are unmeasured:** intent-to-destination, filter-level UI-state correctness, analytical faithfulness, retrieval at scale, and an action-hallucination rate.
- **No safety metric,** such as Completion under Policy or a false-success rate.

**Limitations the VACP authors state**

- **Developer overhead:** each app must be instrumented by hand. We share this cost; our Contract is also per-app.
- **Loss of visual cues:** patterns humans see in a chart are lost when only structure is exposed.
- **Scalability unproven:** not tested on large, highly dynamic apps. We sidestep this at four pages but don't solve it either.

**In one line:** VACP lets the agent see and operate an analytics app safely. It doesn't let the agent understand what the numbers mean, prove where each figure came from, or confirm that its actions worked. Those three are our contribution. The per-app setup cost and scale remain open for both VACP and us, and should be stated as shared limitations.

### Reviewer answer: why VACP over the other papers

For use when a reviewer asks this during or after the presentation.

**Short answer (about 30 seconds)**

> "We treat VACP as our closest reference, not a dependency. We picked it on three criteria: it targets the same kind of app we do, interactive analytics with charts and filters; it uses the same core idea, the app describes itself to the agent instead of the agent reading screenshots; and it's the only close paper with a measured comparison, about 95% task completion against 28 to 51% for screen-reading agents. Other papers each support one piece of our design, such as APIs over clicking or typed actions, but none combines all three. What VACP doesn't do is what we add: declared business meaning for each measure, checking the screen after every action, and a source for every figure in the answer."

**If they push further**

- **"Why not EmbeWebAgent?"** "It shows an agent can be embedded in a real front end, but it reports no benchmark or success rates. We cite it for architecture, not evidence."
- **"Why not the API-based agents, like Beyond Browsing?"** "They prove direct calls beat clicking: 38.9% against 14.8% on WebArena. But they're on general websites, with no analytics and no notion of what a number means. They support one design choice, not the whole approach."
- **"Isn't 15 tasks a weak basis?"** "Yes, which is why we use VACP for direction, not as proof. Our own evaluation is designed to measure what VACP didn't: page accuracy, filter-level correctness, traced figures and false-success rate, with our checks switched on and off."
- **"So what's actually new in yours?"** "Three things VACP and the others don't have. Measures carry declared meaning, meaning unit, level of detail and period, and those definitions are tested. Every action is confirmed on the live page afterwards. And every figure in an answer carries its source, or the answer is blocked. We don't claim the embedded agent or validated actions as ours."

**What not to say**

- Not "VACP proves our approach works." It's a different domain, and only 15 tasks.
- Not "nobody has done this." VACP and EmbeWebAgent are close prior work; our claim is the combination, applied to business apps.
- Not "we use VACP." We borrow its idea, not its code or protocol.

## How published work measures the brief's KPIs

Added 2026-10-08. Each KPI in the brief is matched to the papers that measure something equivalent.

**Evidence boundary.**
- ✓ marks papers checked against the paper body or full abstract: VACP, EmbeWebAgent, Beyond Browsing, WebArena, WebLINX and UI-CUBE.
- The others come from the abstract summaries in report 05.
- Mind2Web's per-step metrics and WebLINX's intent-match metric are recalled, not re-read.

Recheck any paper before the deck cites a specific metric.

| Brief's KPI | Papers and the metric they use |
|---|---|
| **1. Intent-to-destination accuracy** | **Vector:** routing F1 0.89 (phrasing → correct intent, 24 users) · **Mind2Web:** element accuracy and step success (right element per step), the closest to "right destination" · **WebLINX ✓:** turn-level intent and element match in conversational navigation |
| **2. UI-state correctness** | **WebArena ✓:** programmatic checks of the final state (database, API or page inspection) · **EntWorld:** SQL-verified final state · **WebCanvas:** key intermediate states reached · **WebStep:** semantic state tracked step by step. None measures filters, dates and sort individually. |
| **3. Multi-step task success, steps, latency** | **WebArena ✓:** end-to-end success (14.4% GPT-4 vs 78.2% humans) · **Beyond Browsing ✓:** 14.8% browsing, 29.2% API, 38.9% hybrid · **UI-CUBE ✓:** 67–85% on simple interactions vs 9–19% on complex workflows · **CRMArena:** under 40% on CRM tasks · **SaaS-Bench:** weighted partial credit · **How Fast Do Agents Rot?:** success vs number of steps · **VACP ✓:** completion about 95% vs 28–51%, plus tokens and latency |
| **4. Analytical quality and faithfulness** | **AD-Bench:** answer accuracy plus coverage of the expected tool-call trajectory · **DAComp:** rubric-graded open-ended analysis · **InsightBench:** multi-step analytics evaluation (listed in report 04 as a design reference; not abstract-checked) · **WebArena ✓:** exact or fuzzy match on information-seeking answers |
| **5. Retrieval quality (precision / recall, MRR)** | **Mind2Web (MindAct):** recall@50 of 85–89% for candidate elements · **WebLINX:** ranking of page elements to prune the page (recall-style metrics) · **Prune4Web:** 25–50× fewer candidate elements. None measures retrieval over app pages or components at scale. |
| **6. Reliability and safety** | **ST-WebAgentBench:** Completion under Policy and Risk Ratio · **Hybrid World-Model Planning:** hallucinated-state rate, the closest to "action hallucination" · **CLAIRE:** success under stress with and without validation (1.0 → 0.5) · **Commit-Time Authorization:** 207 of 216 runs committed after approval had lapsed · **EmbeWebAgent ✓:** integration tests on action correctness and latency (no benchmark) · **Unbrowse:** latency, 950 ms vs 3,404 ms |
| **7. User experience** | **CowPilot:** 95% success with humans doing 15.2% of steps · **"Here, Let Me Help" (CHI 2026):** 30-user study of how people intervene · **Magentic-UI:** human-in-the-loop interaction modes. No paper measures "perceived usefulness as an in-app companion" directly. |

### What this means for our evaluation

- **Well covered in the literature:** multi-step task success (KPI 3) and reliability (KPI 6). We can borrow definitions directly, especially Completion under Policy and the hallucinated-state rate.
- **Covered only by proxies:**
  - **Intent-to-destination (KPI 1):** papers measure element or intent match, not page routing.
  - **UI-state correctness (KPI 2):** papers check the whole final state, not filter by filter.
  - **Retrieval (KPI 5):** papers rank elements within a single page, not pages across an app.

  These are where we define our own metrics: top-1 page accuracy, per-filter exact match and F1, and recall@k and MRR over the padded Contract catalogue.
- **Weakest:** analytical faithfulness (KPI 4) has only two or three recent preprints (AD-Bench, DAComp, plus InsightBench as a design reference). UX usefulness (KPI 7) has user studies but no standard metric.
- **Deck wording:** KPIs 3 and 6 follow published definitions; KPIs 1, 2, 4 and 5 are our own definitions adapted from these papers.

### The two closest papers: VACP and EmbeWebAgent

Both were checked against the paper bodies.

**What each measured**

- **VACP:** 15 tasks across 5 visual-analytics apps. It compares four setups:
  - S1: screenshot + DOM;
  - S2: DOM + serialized state;
  - S3: VACP only;
  - S4: VACP + UI + DOM.

  The models were GPT-5.2, Claude Sonnet 4.5 and Gemini 3. The metrics were task completion rate, token consumption and latency.
- **EmbeWebAgent:** no benchmark and no success rates. It reports an integration test suite (pytest) checking action correctness and latency, tracing (Phoenix) for performance and session isolation, and one demonstration on a chemistry-analysis app.

| Brief's KPI | VACP | EmbeWebAgent |
|---|---|---|
| 1. Intent-to-destination accuracy | Not measured | Not measured |
| 2. UI-state correctness | Not measured separately (folded into task completion) | Not measured; tests check action correctness, not resulting UI state |
| 3. Multi-step task success, steps, latency | Yes: completion about 95% (S3/S4) vs 28–51% (S1), plus latency. Steps not reported. | Latency only, in integration tests. No task-success rate. |
| 4. Analytical quality and faithfulness | Not measured | Not measured |
| 5. Retrieval quality | Not measured | Not measured |
| 6. Reliability and safety | Indirect: validates actions and rejects stale ones, but reports no hallucination or error rate. Token cost reported. | Partly: action-correctness tests and session isolation via tracing, but no rate reported. |
| 7. User experience | Not measured | Demo only; no user study |

**What this means for us**

- **They give us one usable number between them:** VACP's 95% vs 28–51% task completion. It supports "declaring the app to the agent beats screen-reading", but it's on 15 analytics tasks, not business workflows.
- **EmbeWebAgent is architecture evidence, not performance evidence.** It shows embedding is feasible, not that it works well. Cite it for design, never for results.
- **Neither measures five of the seven KPIs:** intent routing, filter-level UI state, analytical faithfulness, retrieval or an action-hallucination rate. Those are exactly the metrics our evaluation adds, which makes the evaluation part of our contribution.
- **Fair comparison:** report our task success the way VACP does, with our checks on vs off and against a screen-reading baseline if time allows, so reviewers can compare like with like.
