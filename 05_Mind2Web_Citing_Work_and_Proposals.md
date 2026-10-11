# Mind2Web: Citing Work and What It Proposes

As of 2026-10-05. Gap IDs (G1.1 to G9.3) refer to `03_Reference_Stack_Gaps_and_KPI_Impact.md`. The full list of citing papers is in `data/mind2web_citing_papers.csv`.

**Evidence boundary.** The citation list comes from the Semantic Scholar API (paper `arXiv:2306.06070`), pulled on 2026-10-05. Each proposal below is summarised from its abstract only. We have not read the full papers. Numbers are the authors' own figures. Many 2026 entries are preprints that have not been peer-reviewed. Semantic Scholar can miss papers, so treat 1,506 as a lower bound.

## Summary

- **1,506 papers cite Mind2Web.** By year: 53 in 2023, 240 in 2024, 469 in 2025 and 699 so far in 2026, plus 45 with no year or earlier dates. Semantic Scholar marks 207 of them as citing it in an "influential" way, meaning they build on it rather than just mention it.
- **Most of them are not about our problem.** The bulk are general web or GUI agent models, agent memory, reinforcement learning and surveys. About 40 papers are directly relevant, and they are grouped below.
- **Three findings change our plan:**
  1. **Prior work already exists for "an agent embedded in your own app".** EmbeWebAgent and VACP both expose app state and a registry of per-page functions to an embedded agent, and both include analytics. Our novelty claim has to be narrowed to what they don't do: business-meaning contracts (grain, unit, valid filters), evidence-traced analysis, and a faithfulness check. Both papers go on the alternatives slide.
  2. **There is now an ERP benchmark.** EntWorld has 1,756 tasks across CRM, ITIL and ERP systems and checks results with SQL. That is the same idea as our final-state check. It is the best public stand-in we have found, better than Mind2Web or WorkArena for our domain. Check whether it is available.
  3. **The research direction supports our design choices.** Typed actions instead of clicks, APIs before browsing, and state-machine memory of the app all line up with design choices 1–3 in report 04. Several papers measure the gains (see Group A).

## Group A. Papers that support our architecture

These papers propose what our hackathon cut already does, or what proposal 04 plans.

| Paper | What it proposes | Our matching piece | Gaps |
|---|---|---|---|
| **EmbeWebAgent** (2026, arXiv 2602.14865) | Embed an agent in an existing UI through lightweight frontend hooks: curated ARIA and URL observations, plus a function registry for each page over a WebSocket. Actions range from single clicks to composite operations. Navigation, manipulation and analytics run as MCP tools. | Design choices 1–2 (catalogue file, state in URL); `configure_view` | G5.1, G1.4 |
| **VACP: Visual Analytics Context Protocol** (2026, arXiv 2603.29322) | Make visual-analytics apps "agent-ready" by exposing app state, available interactions and direct execution. Shipped as a library for common chart grammars and web frameworks. Reports higher success with fewer tokens and lower latency than vision or DOM agents. | Widget contracts; `read_widget` | G1.1, G1.3, G9.3 |
| **Web Agents Should Use Typed Actions Instead of Click-Based Browsing** (2026, arXiv 2602.17245, position paper) | Proposes "web verbs": typed functions with structured inputs and outputs, preconditions, postconditions, policy tags and logging hooks. Agents compose verbs into short programs with traces that can be checked. | Pydantic-validated tools; evidence IDs; action log | G3.2, G5.2, G8.2 |
| **Vector: Canonical Intent Graphs** (2026, ICESIC) | Maps different phrasings to stable intent IDs in four steps: parsing, embedding retrieval with a 0.82 cosine threshold, LLM equivalence check, and context enrichment. A risk and confidence score sends each intent down one of four paths: native API, agentic read, agentic write, or manual deep-link. Reports routing F1 0.89 with 24 users. | Routing pipeline (proposal 04 §4); abstain or ask; two-tier confirmation | G2.3, G3.4, G5.4 |
| **ActionEngine** (2026, arXiv 2602.20502) | A crawling agent explores the app offline and builds a state machine of GUI states, the operations available in each, and transitions. At run time, an execution agent writes the whole program in one pass instead of a loop of steps. | Route and state graph plus validation crawl (proposal 04 §1, §3) | G1.3, G1.4, G9.3 |
| **AutoWebWorld** (2026, arXiv 2602.14296) | Model a website as a finite state machine so each action is checked against rules and success means reaching a goal state. | URL state as a checkable state; task-file runner | G8.1, G8.2 |
| **Beyond Browsing: API-Based Web Agents** (ACL 2024, arXiv 2410.16464) | An agent that uses only APIs, and a hybrid agent that uses APIs and browsing. On WebArena, the hybrid agent beats browsing alone by 24 points absolute (38.9% success). | Direct route and API first; Playwright only as a fallback | G5.1 |
| **Internal APIs Are All You Need (Unbrowse)** (2026, arXiv 2604.00694) | A shared route graph of each site's own internal APIs, learned from browsing traffic. Cached API calls took 950 ms against 3,404 ms for Playwright. | Same argument for direct routes over browser automation | G5.1, G9.3 |
| **Build the Web for Agents, Not Agents for the Web** (2025, arXiv 2506.10953, position paper) | Proposes an "Agentic Web Interface" designed for agents, guided by six principles. | Catalogue file as an interface for the agent | G5.1 |
| **Terminal Agents Suffice for Enterprise Automation** (2026, arXiv 2604.00073) | A coding agent with only a terminal and platform APIs matches or beats MCP agents and GUI agents on enterprise tasks, at lower cost. | Supports keeping the tool layer thin | G9.3 |
| **Web Sitemap Knowledge Can Enhance Autonomous Browsing** (ACL 2026) | Title only; Semantic Scholar has no abstract. Check before citing. | Route graph | G1.3 |

## Group B. Enterprise and analytics benchmarks (evaluation stand-ins)

| Paper | What it provides | Use for us |
|---|---|---|
| **EntWorld** (2026, arXiv 2601.17722) | 1,756 tasks across six enterprise domains, including CRM, ITIL and **ERP**. Tasks are generated from the database schema, and results are checked deterministically with SQL instead of by matching action traces. | **Best stand-in for our domain.** Copy its SQL-based final-state check for our task runner. Check its licence and whether the data is released. |
| **WorkArena** (ICML 2024) | 33 task types on ServiceNow, including filtering lists and reading dashboards. Introduced BrowserGym. | Already in report 04. Access is gated. |
| **CRMArena** (NAACL 2025, arXiv 2411.02305) | 9 CRM tasks across service agent, analyst and manager roles, with 16 linked business objects and hidden variables. Top agents succeed on fewer than 40%. | Design reference for analyst-style tasks |
| **SaaS-Bench** (2026, arXiv 2605.15777) | 106 long tasks across 23 deployable SaaS systems, with weighted checkpoints that also give credit for partial progress. | Partial-credit scoring for multi-step tasks |
| **UI-CUBE** (UiPath, 2025, arXiv 2511.17131) | 226 tasks. Simple interactions succeed 67–85% of the time, but complex enterprise workflows fall to 9–19%. | Evidence for avoiding long chains of clicks |
| **AD-Bench** (2026, arXiv 2602.14257) | Real requests for advertising analytics. Ground truth is regenerated by replaying an expert's tool calls, so answers stay correct as data changes. Scores both the answer and how much of the expected trajectory was covered. | Pattern for analytical correctness (G6) and keeping expected answers fresh |
| **DAComp** (2025, arXiv 2512.04324) | 210 data-engineering and data-analysis tasks. Open-ended analysis is graded by an LLM judge against rubrics. | Rubric for "likely causes" answers (G6.1) |
| **ST-WebAgentBench** (2024, arXiv 2410.06703) | 222 enterprise tasks, each with safety policies. Defines **Completion under Policy (CuP)**, which counts a task only if every policy was respected, and a Risk Ratio. Agents' CuP is under two-thirds of their raw completion rate. | **Adopt CuP** as our reliability and safety KPI next to task success |
| **WebStep** (2026, arXiv 2606.15673) | Each site exposes a deterministic map of meaningful states next to the GUI, so progress is tracked step by step, not just at the end. | Our URL state already gives us this; log process metrics too |
| **Online-Mind2Web, "An Illusion of Progress?"** (2025, arXiv 2504.01382) | 300 tasks on 136 live websites, with an LLM judge that agrees with human judgment about 85% of the time. Finds that earlier offline scores overstated progress. | A warning against relying on offline benchmark numbers |
| **WebCanvas / Mind2Web-Live** (2024, arXiv 2406.12373) | 542 tasks, scored on 2,439 key intermediate states rather than exact action matches. | Scores key states, which fits our "accept alternative action orders" rule (report 02 §15) |
| **How Fast Do Agents Rot?** (2026, arXiv 2609.01660) | Task success decays geometrically with the number of steps, controlled by a per-step reliability that stays below 1 even for the largest models. | Fewer steps directly raises success: report the step count for every task |

## Group C. Conversation, human oversight and safety

| Paper | What it proposes | Gaps |
|---|---|---|
| **WebLINX** (ICML 2024, arXiv 2402.05930) | 100K interactions across 2,300 expert demonstrations of chat-driven web navigation. A retrieval model ranks page elements to prune the HTML. | G3.3, G2.2 |
| **MT-Mind2Web / Self-MAP** (ACL 2024, arXiv 2402.15057) | A multi-turn version of Mind2Web, plus planning with memory and self-reflection for follow-up requests. | G3.3 (**more useful to us than Mind2Web itself** for testing follow-ups) |
| **CowPilot** (NAACL 2025 demo, arXiv 2501.16609) | The agent proposes the next step and the user can pause, reject or override it. Joint mode reached 95% success with humans doing 15.2% of the steps. | G9.2 |
| **Magentic-UI** (Microsoft, 2025, arXiv 2507.22358) | Open-source interface for human-in-the-loop agents, with six ways to involve the user, including planning together and approving actions. | G9.2, G5.4 |
| **"Here, Let Me Help"** (CHI 2026) | Study of 30 users classifying when and how people step in on a web agent: explicitly (stop or override) or implicitly (guide or prepare). | G9.2 |
| **The Verifiable Action Card** (2026, arXiv 2609.18411) | Builds the approval prompt from the real pending action, not from model text, and checks the action again just before it runs. | G5.4 for the one write action ("create case") |
| **Commit-Time Authorization** (2026, arXiv 2607.10487) | An approval must still be valid when the effect is committed. In their test suite, 207 of 216 runs committed after the approval had become invalid. | G5.4 |
| **CLAIRE** (2026, arXiv 2609.32787) | Healthcare form filling split into field discovery, mapping, deterministic validation, bounded correction, escalation and an audit trail. Removing validation halved success under stress. | G3.2, G5.2 (an ablation we can copy) |
| **Hybrid World-Model Planning** (2026, arXiv 2606.27806) | Measures how often an agent claims a state that isn't true, and how far the error spreads. A small transition model checks the LLM's predicted state changes. | G5.2, and a metric for "action hallucination" |

## Group D. Element retrieval and memory (relevant to the browser fallback and retrieval stress test)

| Paper | Proposal | Relevance |
|---|---|---|
| **SeeAct** (ICML 2024, arXiv 2401.01614) | GPT-4V acting on Mind2Web. Completed 51.1% of tasks on live sites when grounding was done by hand. Grounding is the bottleneck. | Supports avoiding pixel or DOM grounding |
| **Synapse** (ICLR 2024) | Strip irrelevant state and give whole past trajectories as examples. | Few-shot prompts |
| **Agent Workflow Memory** (ICML 2025, arXiv 2409.07429) | Extract reusable workflows from past runs. +24.6% relative on Mind2Web, +51.1% on WebArena. | Reusing recorded investigation workflows |
| **TRAD** (SIGIR 2024) | Pick examples step by step by matching reasoning. Deployed in RPA at a business insurer. | Retrieval of examples |
| **Prune4Web** (AAAI 2026) | The LLM writes small scoring programs that filter the DOM, giving 25–50× fewer candidate elements. | Playwright fallback only |
| **HyMEM** (2026, arXiv 2603.10291) | Graph-based memory combining symbolic nodes with trajectory embeddings. | Knowledge-graph idea from the brief |

## Most-cited papers that cite Mind2Web (context only)

These are cited the most, but they are general-purpose: SWE-bench (4,105 citations), *A Survey on LLM-based Autonomous Agents* (4,025), WebArena (2,172), ChatGLM (1,796), InternVL 2.5 (1,792), AgentBench (1,414), A-MEM (1,122), CogAgent (898), VisualWebArena (763), LATS (677). Sort the CSV by `citation_count` for the rest.

## What this changes in our plan

| # | Change | Where |
|---|---|---|
| 1 | Add EmbeWebAgent, VACP and "typed actions" to the alternatives slide. State our difference as **meaning, evidence and faithfulness**, not "an agent embedded in the app". | Deck; report 03 "Existing alternatives" |
| 2 | Check EntWorld's licence and data release. If it is usable, run a small ERP subset as an external stand-in next to our own task file. | Report 04 G8.1 |
| 3 | Add **Completion under Policy** (from ST-WebAgentBench) and **step count** (supported by "How Fast Do Agents Rot?") to the KPI table. | Report 04, task runner |
| 4 | For the multi-turn stand-in, use **MT-Mind2Web**, not Mind2Web. | Report 04 G7.2, G8.1 |
| 5 | Bind the confirmation for "create case" to the exact pending action, as in the Verifiable Action Card. | `configure_view` and write tools |
| 6 | Run a validation ablation like CLAIRE's (with and without contract validation) to show that the validator is what helps. | Proposal 04 measurement plan |

## How to refresh this list

The fetch script used the Semantic Scholar Graph API endpoint `/paper/arXiv:2306.06070/citations` with paging, then the `/paper/batch` endpoint to get one-line summaries (TLDRs). The public API rate-limits requests, so expect retries.
