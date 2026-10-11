# API-Based and In-App Agents: Evidence-Checked Literature Review

As of 2026-10-09. Written for KLE Tech Hackfest 2026, Domain 5A (Context-Aware Application Agent). This review covers two agent patterns:

1. **The API-based agent** calls the app's server through named, parameterised operations (`analyze`, `resolve`, `related`). It never writes free SQL.
2. **The VACP-style in-app agent** works through an in-page bridge (`window.__vacp` with `getCapabilities`, `getState` and `execute`). It reads state and runs semantic actions instead of clicking.

It also covers **evaluation design** for the KPIs in the brief.

The companion file is [`api_agents_papers.csv`](api_agents_papers.csv), with one row per paper (91 rows). The IDs P01–P91 used below are its row IDs. That file holds the full headline numbers, implementation notes, risks, hybrid evidence and small-model evidence for every paper.

## How to read this

**Evidence rules**
- Every arXiv ID (87 of 91 rows) was resolved through the arXiv API on 2026-10-09, and its title matched.
- The three rows without an arXiv ID were checked on their official pages: BFCL (PMLR), the WebMCP spec (W3C CG) and MCP Apps (MCP SEP). One vendor blog (dbt Labs) is included and labelled as such.
- Numbers come **only** from the papers themselves.
  - "verified-fulltext" means we read them in the paper body, tables or figures.
  - "verified-abstract" means only the abstract was read.
  - The CSV `verification` column gives this level for every row.
- I personally re-checked the three numbers that matter most (marked ✔) against the paper text.

**Caveats**
- Most 2026 entries are unrefereed arXiv preprints.
- Almost every headline number comes from frontier closed models (GPT-4o/5.x, Claude, Gemini). Where a paper reports open 7B–72B models, that is listed separately in [section 5](#5-what-to-expect-from-local-14b32b-models-doing-tool-calling).
- A venue is given only where it was seen in arXiv comments, ACL Anthology, PMLR or OpenReview. Otherwise the paper is marked "arXiv preprint".

**Not covered:** the CLAIRE, Verifiable Action Card and Commit-Time Authorization papers cited in report 07 were outside this review's scope and were not re-checked.

---

## 1. Bottom line

1. **API access beats clicking, and API plus UI beats either, but only when API coverage is partial.**
   - On WebArena with GPT-4o: browsing 14.8%, API-only 29.2%, hybrid 38.9% ✔ ([Beyond Browsing](https://arxiv.org/abs/2410.16464)).
   - Desktop studies show the same ordering: MCPWorld 70.65 / 53.23 / 75.12; CoAct-1 50.68 / 35.73 / 60.76.
   - When the declared interface is complete, as in VACP, adding screenshots and DOM brought no consistent gain and cost more tokens and time.
2. **A declared in-app interface is the single biggest lever in the in-app setting.**
   - VACP: UI+DOM agents 28.89–51.11% success against VACP-only 91.11–100% ✔. The paper used 15 tasks × 3 runs with GPT-5.2, Claude Sonnet 4.5 and Gemini 3 Pro.
   - CI4A (component-level registry): 75.3–86.3% against 26.4–70.3% for DOM agents.
   - TwinBI (dashboard state + semantic layer): exact match 43.3% → 63.3%.
3. **A small, hand-written, composable set of operations beats a large auto-generated one.**
   - The Tool Illusion re-ran three tool sources across five backbones. Human-crafted API tools raised WebArena success by 12.7–19.6 points, for weak models too (GPT-5-nano 10.1 → 22.5).
   - Synthesised UI-macro tools gave small or negative gains for strong models.
4. **Semantics behind lookup tools, plus deterministic validation, beats free text-to-SQL by large margins.**
   - Knowledge-graph context: 16.7% → 54.2% (GPT-4).
   - Ontology check-and-repair: → 72.55%.
   - A data contract exposed through tools: hard-task accuracy 13.9–37.0% → 55.1–77.4%.
   - GROUND hallucination rate: 0.79 → 0.00.
   - A rule-gated **7B** Qwen2.5-Coder agent beat a direct-prompted **32B** model: Business Truth Rate 0.562 vs 0.300.
5. **Model choice: R1-distill models are worse at tool calling than plain Qwen2.5-Instruct.**
   - BFCL v3 (Qwen3 Technical Report): DeepSeek-R1-Distill-Qwen-32B 53.5, Qwen2.5-14B-Instruct 58.7, Qwen2.5-32B-Instruct 62.8 ✔.
   - Long reasoning before a call hurts: Qwen2.5-7B scores 82.5% with a 32-token chain of thought and 18.0% with 256 tokens.
   - **Route every tool or action call through Qwen2.5-14B-Instruct.** Use R1-Distill-32B only to reason and narrate over data that has already been retrieved.
6. **Multi-turn and nested calling is where 14B–32B models break.**
   - Qwen2.5-14B on the BFCL paper: simple single calls 69.7, but multi-turn base 19.5. Qwen2.5-32B multi-turn: 29.5.
   - Nested sequences (one call's output feeding the next): ≤0.22 full-sequence accuracy for 7–70B models on NESTFUL.
   - So keep the server responsible for binding results between calls, and keep each turn to one or a few independent calls.

---

## 2. Ranked shortlist (a): the API-based agent

What to implement or borrow in 48 hours with local Qwen2.5-14B and R1-Distill-32B. Ranked by expected effect on our KPIs per hour of work.

| Rank | Paper | What to implement | Why (verified evidence) |
|---|---|---|---|
| 1 | **Beyond Browsing** (P01), [arXiv 2410.16464](https://arxiv.org/abs/2410.16464), Findings of ACL 2025, [code](https://github.com/yueqis/API-Based-Agent) MIT | Use it as the template for the API agent. Expose operations with OpenAPI-style docs. Add a two-stage `get_api_documentation(op)` tool: list names and one-liners first, then fetch the full schema for the chosen op, so a 14B context is not flooded. Run the same task file in API-only, VACP-only and hybrid modes. | WebArena, GPT-4o: browsing 14.8%, API-only 29.2%, hybrid 38.9% (full text). The hybrid beat both on every site. Cost caveat: about $0.1/task browsing against about $1.4 hybrid, because the API docs inflate prompts. |
| 2 | **The Tool Illusion** (P08), [arXiv 2604.03465](https://arxiv.org/abs/2604.03465), COLM 2026 | A design rule for the operation catalogue: about 20–40 hand-written, deterministic, composable ops rather than hundreds of synthesised ones. Measure token and step overhead per catalogue size. | Human-crafted API tools: +12.7 to +19.6 points on WebArena across 5 backbones (GPT-5-mini 19.3 → 38.9; GPT-5-nano 10.1 → 22.5). WALT and SkillWeaver tools gave little or negative gain for GPT-5. |
| 3 | **Context-layer ablation** (P79), [arXiv 2609.22259](https://arxiv.org/abs/2609.22259), [code](https://github.com/flyersworder/agentic-data-contracts) MIT | Copy the tool surface for the semantic layer: `list_metrics`, `lookup_metric`, `lookup_relationships`, `trace_metric_impacts` (our `related`), and inspect-then-run. Keep one YAML of metric definitions that both the tools and the validator read. | DABstep hard tasks, schema-only vs contract-behind-tools: GLM 13.9 → 55.1%, DeepSeek 22.6 → 56.6%, GPT-5.6 37.0 → 77.4%. Pasting the same knowledge into the prompt helped far less (22.9–50.3%). |
| 4 | **QueryProof** (P81), [arXiv 2608.09254](https://arxiv.org/abs/2608.09254), [code](https://github.com/k-w-lee/query_proof) MIT | Run post-execution assertions on every op result: required filters and period actually applied, non-empty, no impossible values. Use rules derived from the semantic layer to decide whether to answer, clarify or abstain. | A rule-gated Qwen2.5-Coder-**7B** scored 0.562 Business Truth Rate against 0.300 for a direct-prompted **32B** (+0.237, CI [+0.112, +0.375]). False success fell from 0.754 to 0.351, and there were 0 wrong numbers on answerable tasks. The authors note the effect's magnitude is uncertain (80 tasks, one run). |
| 5 | **GROUND** (P80), [arXiv 2608.26157](https://arxiv.org/abs/2608.26157), plus **OBQC** (P76), [arXiv 2405.11706](https://arxiv.org/abs/2405.11706) | Before any call runs, a validator checks that the metric exists, the dimension is valid for the metric's grain, filter values are in domain, the date range is valid and the join path is allowed. It returns machine-readable errors, allows up to 3 repair attempts, then abstains. Count "unknown" separately from "wrong". | GROUND (Claude Opus 4.8, synthetic set of 100): value accuracy 0.000 direct → 0.951; any-hallucination rate 0.79 → 0.00. OBQC (GPT-4): 54.2% → 72.55% accuracy, with error falling to 19.44%. |
| 6 | **Model routing:** Qwen3 Tech Report (P16), [arXiv 2505.09388](https://arxiv.org/abs/2505.09388); BFCL (P15), [PMLR](https://proceedings.mlr.press/v267/patil25a.html); Brief Is Better (P19), [arXiv 2604.02155](https://arxiv.org/abs/2604.02155) | Qwen2.5-14B-Instruct emits all calls. Have it state the operation name first (or use vLLM `guided_choice` over op names), then fill the arguments under a JSON schema. Cap reasoning before a call at about 32–64 tokens. R1-Distill-32B only narrates over retrieved evidence. | R1-Distill-Qwen-32B scores 53.5 on BFCL v3, below Qwen2.5-14B at 58.7 ✔. Naming the function first ("FR-CoT") gave 83.0% with 0% hallucinated names on Qwen2.5-7B (BFCL Multiple). Free-form 256-token reasoning gave 18.0%. |
| 7 | **EasyTool** (P27), [NAACL 2025](https://aclanthology.org/2025.naacl-long.44/), [code](https://github.com/microsoft/JARVIS/tree/main/easytool) MIT; **ToolRet** (P26), [arXiv 2503.01763](https://arxiv.org/abs/2503.01763); **AnyTool** (P31), [arXiv 2402.04253](https://arxiv.org/abs/2402.04253) | Offline, rewrite every page, widget and op description into a fixed template: purpose, when to use, when not to use, typed args with enums, one example. Retrieve over these docs hierarchically (module → page → op) with BM25 plus a dense model and an instruction prefix, and put only the top-k in the prompt. | EasyTool: doc tokens −70.43%; Mistral-7B ToolBench pass rate 0.0 → 70.5; retrieval NDCG@1 45.7 → 76.7. ToolRet: an instruction prefix adds about 9–16 nDCG@10, and a reranker *hurt*. AnyTool: removing the hierarchy dropped pass rate from 58.9 to 22.4. |
| 8 | **NESTFUL** (P25), [EMNLP 2025](https://arxiv.org/abs/2409.03797); **RestGPT** (P34), [arXiv 2306.06624](https://arxiv.org/abs/2306.06624), [code](https://github.com/Yifan-Song793/RestGPT) MIT | The server binds results between calls: `analyze` accepts entity names and resolves them internally, or prior results are referenced by handle and validated. Ops return compact typed summaries reshaped by code, not by the LLM (RestGPT's schema parser). | NESTFUL: best 7–8B full-sequence accuracy 0.22; Llama-3.1-70B 0.07; GPT-4o 0.28. RestGPT on TMDB: success 75.0 against 46.0 without the schema parser and 44.0 without the planner. |
| 9 | **Terminal Agents Suffice** (P03), [arXiv 2604.00073](https://arxiv.org/abs/2604.00073), no code | Add a short "skills" markdown: how to answer the common analytics intents with our ops. Optionally allow a sandboxed composition step (Python over op results, no SQL) for multi-step comparisons. | 729 tasks on ServiceNow, GitLab and ERPNext. Open model Qwen-3.6-27B: terminal 54.5%, MCP tool-use 31.9%, web 34.8%; on ERPNext 56.0 / 48.3 / 34.3. The skills file took Sonnet from 72.7% to 76.1% and cut cost from $0.56 to $0.38. |
| 10 | **ActionEngine** (P63), [arXiv 2602.20502](https://arxiv.org/abs/2602.20502), no code | Hand-write the page/state graph with the ops available in each state and their output schemas. Let the planner emit one complete program over named ops in a single call, run it deterministically, and re-plan only on a structured failure. This means fewer LLM calls on vLLM. | WebArena, 655 tasks, Claude Opus 4.6: 91.2% against 82.7% for Claude Code with Playwright MCP. Latency 27 s against 87 s; 1.5–3.5 LLM calls per task against 7–16. |

Runners-up: ComInsight (P90) to enumerate verifiable "atomic insights" before the LLM composes "likely causes"; Unbrowse (P02) for its three-path executor (cache → direct → browser fallback); TinyAgent (P35) for parallel DAG plans and a classifier-based tool selector; ToolACE (P22) for the warning that retrieved few-shot examples of *other* tools hurt.

## 3. Ranked shortlist (b): the VACP / in-app pattern

| Rank | Paper | What to implement | Why (verified evidence) |
|---|---|---|---|
| 1 | **VACP** (P59), [arXiv 2603.29322](https://arxiv.org/abs/2603.29322), [repo](https://github.com/ETH-IVIA-Lab/VACP), **no licence** | Mirror the repo contract: `window.__vacp = {version, getCapabilities(request?), getState(request?), execute(call)}`. Our `{getCapabilities, getState, execute}` already matches it. The details to copy from `schema.ts`:<br>• stable `vacp://` refs<br>• a node and edge capability graph (`contains`, `controls`, `derivedFrom`, `targets`)<br>• action descriptors `{name, description, parameters, targetRef}`<br>• scoped capability requests (by refs, prefixes, kinds, layers)<br>• state requests in `full`, `delta` or `auto` mode with a hash token, to keep tokens low<br>• calls `{callId, name, params}`, returning `{ok, result}` or `{ok:false, error}`<br>• the standard actions `vacp.apply_state`, `vacp.data_schema` and `vacp.data_sql`<br>Expose only 3 static tools to the model: `vacp_capabilities`, `vacp_state`, `vacp_execute`. | Success (Fig. 6), S1 UI+DOM vs S3 VACP-only:<br>• Claude: 28.89% vs 91.11%<br>• Gemini: 46.67% vs 100%<br>• GPT-5.2: 51.11% vs 97.78% ✔<br>S3 used fewer tokens and finished faster than the UI scenarios. "Latency" here means whole-task duration. **The repo has no licence, so borrow the design, not the code.** The paper itself uses snake_case names (`get_state`, `get_capabilities`, `execute_interaction`, …). |
| 2 | **Typed web verbs** (P04), [arXiv 2602.17245](https://arxiv.org/abs/2602.17245), ICML 2026 position paper | Give every action descriptor four extra fields:<br>• preconditions<br>• postconditions, checked by re-reading `getState` after `execute` (this is our UI-state correctness check)<br>• a policy tag: read-only, state-changing or needs confirmation<br>• a logging hook | Position paper. The only evidence is "more than ten websites… over one hundred distinct complex tasks, all of which completed successfully", with no baseline. Cite it for the design, not for numbers. |
| 3 | **CI4A** (P66), [arXiv 2601.14790](https://arxiv.org/abs/2601.14790) | Have each widget (filter, date picker, grid, chart) register on mount and unregister on unmount, with its own state view and tool signatures. Include enums, ranges and required flags. Route `callTool` through the widget's own change handlers so the UI and the agent cannot diverge. | Refactored WebArena, 182 tasks, GPT-5: 75.3% structured / 86.3% with vision, against 26.4–70.3% for baselines. Average steps 10.7 → 4.5. |
| 4 | **EmbeWebAgent** (P60), [arXiv 2602.14865](https://arxiv.org/abs/2602.14865), IBM tech report, no code | • Expose only the actions valid on the current route (page-filtered function sets).<br>• Provide an explicit `navigate(url)` whose enum is the deep-link map.<br>• Send action metadata once per page and push observations only when the state changes.<br>• Copy the integration-test harness: replay an observation and assert the exact call, params or target URL. | No success-rate numbers: it is a demo plus tests. The shim is about 150 lines of code and the registry about 200. |
| 5 | **WebMCP spec** (P61), [W3C CG draft](https://webmachinelearning.github.io/webmcp/) | Shape descriptors so they could later be published unchanged through `document.modelContext.registerTool`: `{name, title, description, inputSchema, annotations{readOnlyHint, consequentialHint, untrustedContentHint}}`. Gate confirmation on `consequentialHint`. Fire a `toolchange`-like event on navigation. | A Community Group Draft Report (8 Oct 2026), not a standard. The current IDL uses `document.modelContext`; older blogs say `navigator.modelContext`. **No paper benchmarks WebMCP task success**; only security papers exist. |
| 6 | **WidgetVA** (P69), [arXiv 2609.24094](https://arxiv.org/abs/2609.24094) | Split bridge actions into state-changing actions and side-effect-free perception queries (Inspect, Summarize, Compute). Expose cross-widget links ("filter A affects chart B") in state. Ship a small library of analysis workflows: aggregate → detail, and period-over-period. | Moving from flat tools to widget abstraction on multi-widget tasks: Answer +5.8, Trace +15.1, State +23.1 points (average over models). For the open Qwen3-VL-30B-A3B, Trace and State rose but Answer did not. |
| 7 | **TwinBI** (P70), [arXiv 2606.13731](https://arxiv.org/abs/2606.13731) | Keep one app-state object (route, filters, dates, sort, active widget) synced from UI events, plus an interaction log as provenance. The dashboard and the agent query the same semantic layer, so the numbers match the screen. | Same gpt-5-mini Playwright agent, 30 queries: exact match 43.3% → 63.3%; partial credit 48.3% → 70.8%; average steps 16.47 → 6.90; timeouts 40% → 10%. |
| 8 | **WALT** (P07), [arXiv 2510.01524](https://arxiv.org/abs/2510.01524), [code](https://github.com/SalesforceAIResearch/WALT) MIT | URL-parameter promotion: make `set_filters`, `set_sort` and `set_date_range` deterministic deep-link writes validated by replay tests. Keep about 8 tools per page. | WebArena 50.1% and VisualWebArena 52.9% with GPT-5 + GPT-5-mini. Tools cut steps by 1.3–1.4×. The Tool Illusion found WALT's tools help weaker backbones more. |
| 9 | **UFO2** (P09), [arXiv 2504.14603](https://arxiv.org/abs/2504.14603), [code](https://github.com/microsoft/UFO) MIT, with **AXIS** (P05), [arXiv 2409.17140](https://arxiv.org/abs/2409.17140) | Use one action schema whose executor routes to a server op or to the bridge. Use "speculative multi-action": emit filter + date + sort in one turn and check `getState` between them, which cuts LLM round-trips. Go API-first, with the UI only as fallback. | UFO2 ablation, GUI-only → GUI+API: GPT-4o 16.3 → 22.4%; o1 16.3 → 24.5%, with steps 16.0 → 6.6. AXIS on Word: 84.0% against 52.0% for a UI-only agent. |
| 10 | **Guardrails:** Screenshots or Tools? (P14), [arXiv 2608.03327](https://arxiv.org/abs/2608.03327); WebMCP Tool Surface Poisoning (P72), [arXiv 2606.06387](https://arxiv.org/abs/2606.06387) | • A hard allowlist of action names, retried on a miss.<br>• A postcondition check before the agent may say "done".<br>• A registry frozen at load time, with no runtime registration from other scripts.<br>• Validate that each executed action exists in the snapshot the agent planned against.<br>• After a successful call, drop the stale state from history. | Adding MCP tools gave the *non-reasoning* Qwen3-VL-8B-Instruct −5.9 points: it produced 97 invented tool names and a 33.0% false-success rate. The reasoning variant gained +4.0. **This is a direct warning for Qwen2.5-14B-Instruct.** |

## 4. Ranked shortlist (c): evaluation designs to copy

| Rank | Source | Design element | How it maps to our KPIs |
|---|---|---|---|
| 1 | **AppWorld** (P40), [ACL 2024](https://arxiv.org/abs/2407.18901), [code](https://github.com/stonybrooknlp/appworld) Apache-2.0 | Database diff from start to end state. Every expected change must be present, and nothing outside the expected-plus-allowed set may change (collateral damage). Also group variants into a scenario and pass the scenario only if all variants pass. | UI-state correctness and write safety. Apply the diff to the URL/state store as well as the DB. GPT-4o: 48.8 / 30.2 task completion (Normal / Challenge); Llama-3-70B: 24.4 / 7.0. |
| 2 | **tau-bench** (P41), [arXiv 2406.12045](https://arxiv.org/abs/2406.12045), MIT; **MCPMark** (P55) | pass^k = mean over tasks of C(c,k)/C(n,k), the chance that all k runs succeed. Report it next to pass@1. Write each task so only one final state is valid. | Reliability of multi-step success. GPT-4o pass^1 61.2 (retail); pass^8 below 25%. |
| 3 | **ToolSandbox** (P45), [arXiv 2408.04682](https://arxiv.org/abs/2408.04682), Apple custom licence | **Milestones:** a DAG of required events, giving ordered partial credit. **Minefields:** forbidden events; any hit scores the task 0. | Minefields on no-fit requests (unknown page, invalid filter value, a write without confirmation) measure **action hallucination** directly. |
| 4 | **ST-WebAgentBench** (P50), [ICLR 2026](https://arxiv.org/abs/2410.06703), Apache | Completion under Policy (CuP): a task counts only if it was completed with zero policy violations. Report a Risk Ratio per policy dimension. | Safety KPI. GPT-4o agents: completion 24.3% against CuP 15.0%. CuP falls from 18.2% with 1 policy to 7.1% with 5 or more. |
| 5 | **AD-Bench** (P53), [arXiv 2602.14257](https://arxiv.org/abs/2602.14257), no code | Store the expert's *tool trajectory*, not just the answer, and replay it against current data to regenerate the gold answer. Score answer Pass@k plus trajectory coverage: required ops, in order, with the key params. | Analytical correctness that survives re-seeding data. It is the closest analogue to analytics through named tools. Qwen3-30B-A3B Pass@1 39.6% against 76.9% for the best model. |
| 6 | **QueryProof** (P81) + **GROUND** (P80) | Put clarify, abstain and refuse items (about half of the set in QueryProof) into the test file. Score Business Truth Rate (a correct abstention counts as correct) and False Success Rate. Break hallucinations down by type: schema, metric, join, grain, filter. | Faithfulness and near-zero hallucination. A false-success rate is what judges will ask about. |
| 7 | **WorkArena / WorkArena++** (P43, P44), [code](https://github.com/ServiceNow/WorkArena) Apache-2.0 | Give each task `setup()`, `validate()`, `cheat()` (a scripted oracle) and `teardown()`. Run `cheat()` in CI to prove every task can be solved. Write each task twice: L2 with explicit steps and L3 with the goal only. | Intent-to-destination accuracy (the L3 − L2 gap isolates planning). WorkArena++: humans 93.9% against GPT-4o 2.1%. |
| 8 | **MCP-Atlas** (P58), [arXiv 2602.00933](https://arxiv.org/abs/2602.00933), MIT | Claim-level scoring: list 3–6 atomic claims per analysis answer, judge each as 1, 0.5 or 0, and pass at ≥0.75 coverage. Use a public/private split as an over-fitting check. | Analytical faithfulness without full LLM-judge prose grading. |
| 9 | **BFCL** (P15) + **MCP-Bench** (P57), [arXiv 2508.20453](https://arxiv.org/abs/2508.20453), Apache-2.0 | **BFCL:** match calls by AST (op plus typed args), with an *irrelevance* split. **MCP-Bench:** use "fuzzed" instructions that never name the tool, and rule-based trace metrics (valid op-name rate, schema-valid args rate, runtime success). | Intent-to-destination accuracy, argument (slot) correctness and hallucination rate, all computed from traces without a judge. |
| 10 | **WebStep** (P65), [arXiv 2606.15673](https://arxiv.org/abs/2606.15673); **WorkBench** (P46), [MIT](https://github.com/olly-styles/WorkBench); **TheAgentCompany** (P49), [MIT](https://github.com/TheAgentCompany/TheAgentCompany) | **WebStep:** log the semantic state on every transition, so you can see where a run went wrong. **WorkBench:** a side-effect rate. **TheAgentCompany:** partial score = 0.5·(checkpoints earned / total) + 0.5·full success. | Multi-step success with partial credit, step counts, and the point where a run first went wrong. |

Also worth borrowing:
- InsightBench (P86) and the EDA-utility paper (P91): plant known causes in the synthetic ERP data, then score whether the agent's "likely causes" recover them (Jaccard over 5 repeats).
- DAComp (P88): hierarchical rubrics for open "why" questions, with judge-to-human kappa reported.
- The Sequeda benchmark (P75): a quadrant design, question complexity × schema complexity.
- BEAVER (P84): an oracle-hint ablation that gives the agent the gold slots to separate routing errors from execution errors.
- EnterpriseOps-Gym (P52): a slice of tasks that cannot be done, scored on correct refusal with zero side effects.
- EntWorld (P51): tasks generated from the ERP schema with ground-truth SQL, checked by running them inside a rolled-back transaction.

---

## 5. What to expect from local 14B–32B models doing tool calling

Measured numbers from papers. None is our own measurement, so treat them as priors, not targets.

| Source | Model(s) | Setting | Result | Level |
|---|---|---|---|---|
| BFCL paper (P15), PMLR 267 | Qwen2.5-14B-Instruct (FC) | Overall | 49.2. Simple AST 69.7; irrelevance (abstain) 77.7; **multi-turn base 19.5**; missing-function 17.0; missing-param 16.5; agentic SQL 30.0 | full text |
| BFCL paper (P15) | Qwen2.5-32B-Instruct (FC) | Overall | 55.6. Simple AST 72.8; irrelevance 81.9; multi-turn base 29.5. GPT-4o (top): 66.4 | full text |
| Qwen3 Tech Report (P16) ✔ | R1-Distill-Qwen-32B / 14B | BFCL v3 | **53.5 / 49.5** | full text |
| Qwen3 Tech Report (P16) ✔ | Qwen2.5-32B / 14B / 7B-Instruct | BFCL v3 | **62.8 / 58.7 / 55.8**. QwQ-32B 66.4; Qwen3-14B (thinking) 70.4 | full text |
| ACBench (P18), ICML 2025 | Qwen2.5-7B vs R1-Distill-Qwen-7B | Tool use (T-Eval) | 70% → 43.6% after R1 distillation. 4-bit quantization costs only 1–3% on tool use | full text |
| DeepSeek-R1 (P17), Nature 2025 | R1 | Limitations section | Structured output "remain[s] suboptimal"; R1 "cannot leverage tools" | full text |
| Brief Is Better (P19) | Qwen2.5-7B-Instruct | BFCL v3 Multiple, 200 tasks | 32-token reasoning: 82.5%; 256 tokens: 18.0%; name-first FR-CoT: 83.0% with 0% invented names | full text |
| CRMArena (P47), NAACL 2025 | deepseek-r1; llama3.1-70b | Function-calling mode | R1 **9.0** in FC mode against 35.1 with ReAct; llama3.1-70b 41.1 (FC) | full text |
| Terminal Agents (P03) | Qwen-3.6-27B | 729 enterprise tasks | Terminal 54.5%; MCP tool-use 31.9%; web 34.8%. ERPNext: 56.0 / 48.3 / 34.3 | full text |
| NESTFUL (P25), EMNLP 2025 | 7–70B open models | Nested call sequences | Full-sequence accuracy ≤0.22 (Hammer2.0-7B); Llama-3.1-70B 0.07; GPT-4o 0.28 | full text |
| MCP-Bench (P57) | qwen3-30b-a3b; llama-3.1-8b | 28 MCP servers | Overall score 0.627; 0.428. gpt-5: 0.749 | full text |
| EnterpriseOps-Gym (P52) | Qwen3-30B (thinking); Qwen3-4B | 1,150 enterprise tasks | 16.8%; 13.7%. Best model 37.4% | full text |
| AppWorld (P40) | Llama-3-70B; DeepSeek-Coder-33B | API apps, code agent | 24.4 / 7.0; 13.1 / 5.8 (Normal / Challenge) | full text |
| tau-bench (P41) | Llama-3-70B | Retail / airline | pass^1 14.8 / 14.4 (GPT-4o 61.2 / 35.2) | full text |
| QueryProof (P81) | Qwen2.5-Coder-7B (scaffolded) vs 32B (direct) | Analytics, 80 tasks | Business Truth Rate 0.562 against 0.300 | full text |
| Screenshots or Tools? (P14) | Qwen3-VL-8B Instruct vs Thinking | Hybrid GUI+MCP | Tools −5.9 vs +4.0 points; Instruct invented 97 tool names | full text |

**What this means for us**
- With a small catalogue, good schemas and constrained names, expect **single-call selection in roughly the 70–80% range** for Qwen2.5-14B, by analogy with BFCL simple AST 69.7 and irrelevance 77.7.
- Expect **multi-turn, stateful sequences to be 20–30%** unless the design removes them.
- So:
  - Use one call (or one independent batch) per step.
  - Let the server do the binding between calls.
  - Use enum or guided decoding for op and page names.
  - Keep reasoning before a call short.
  - Validate, retry once, then abstain.
  - Keep R1-Distill-32B out of the call path entirely.
- Run native vLLM tool calling against a plain JSON prompt on our own gold set. ToolRL and IFFC (P21, P39) show that prompt format alone moves scores by more than 10 points.
- **Leaderboard note (not a paper):** the official BFCL V4 leaderboard, fetched 2026-10-09 (last updated 2026-04-12), does not list Qwen2.5 or R1-distill models. Do not quote it for them.

## 6. Does hybrid API + UI beat either alone?

| Source | Setting | UI only | API/tools only | Hybrid | Read |
|---|---|---|---|---|---|
| Beyond Browsing (P01) ✔ | WebArena, GPT-4o | 14.8% | 29.2% | **38.9%** | Hybrid wins on every site. API coverage was partial, and some endpoints were hand-added. |
| MCPWorld (P12) | 201 desktop tasks, Claude 3.7 | 70.65% | 53.23% | **75.12%** | The gain is mostly on hard tasks (51.11 vs 35.56). |
| CoAct-1 (P10) | OSWorld, OpenAI models | 50.68% | 35.73% (coding) | **60.76%** | A clean three-way ablation. |
| UFO2 (P09) | OSWorld-W | 16.3% | — | 22.4% (GPT-4o), 24.5% (o1) | Adding APIs also cut o1's steps from 16.0 to 6.6. |
| OSWorld-MCP (P13) | OSWorld + 158 MCP tools | o3 8.3% | — | 20.4% | Tools are under-used: invocation rate ≤36.3%. Qwen2.5-VL-72B gained only +4.4. |
| Terminal Agents (P03) | 729 enterprise tasks | Opus 79.9% (web) | 78.7% (terminal) | 81.4% | Small gain at higher cost. No gain for Sonnet (72.0 vs 72.2 / 72.7). |
| VACP (P59) | 15 VA tasks | 28.89–51.11% | 91.11–100% (VACP-only) | 95.56–100% (VACP+UI+DOM) | **Mixed.** Once the declared interface is complete, adding UI costs tokens and time without a consistent gain. |
| CI4A (P66) | Refactored WebArena | — | 75.3% (structured + semantic) | 86.3% (vision + semantic) | Visual verification added 11 points. |
| Screenshots or Tools? (P14) | OSWorld-MCP, 8B models | 30.5 / 25.4% | — | 34.5 / **19.5%** | Hybrid **hurts** the non-reasoning model. |

**Conclusion**
- Hybrid helps when the API does not cover the whole app, and on long tasks.
- When the app declares everything, as ours will, the UI channel is better used for *verification and showing the user*, VACP's "dual-channel" recommendation, than for acting.
- Small non-reasoning models can get worse when given more channels, so route between the channels deterministically rather than letting the 14B model choose.

## 7. Semantic layer vs free text-to-SQL (evidence for "no free SQL")

| Source | Comparison | Result | Level |
|---|---|---|---|
| Sequeda et al. (P75), [arXiv 2311.07509](https://arxiv.org/abs/2311.07509), [data](https://github.com/datadotworld/cwd-benchmark-data) Apache-2.0 | GPT-4 SQL vs a knowledge-graph view, 43 insurance questions | 16.7% → 54.2%. On high-schema-complexity questions, 0% → 35.7–38.5% | full text |
| OBQC (P76) | + ontology check and LLM repair (max 3) | 72.55% accuracy, 8% unknown, 19.44% error | full text |
| Semantic-layer paired study (P78) | Schema vs schema + a 4 KB semantic document, 3 frontier models | +17 to +23 points (45.5–50.5% → 67.7–68.7%) | **abstract only** |
| Context-layer ablation (P79) | Data contract behind tools vs schema | Hard tasks 13.9–37.0% → 55.1–77.4% | full text |
| GROUND (P80) | Governed semantic layer vs direct / RAG | Value accuracy 0.000 → 0.951; hallucination 0.79 → 0.00 | full text |
| dbt Labs blog (P77) | Semantic Layer vs text-to-SQL, 11 questions × 20 runs | e.g. gpt-5.3-codex 84.1% → 100%, **but 0% on multi-hop questions the layer had not modelled** | vendor blog, not peer-reviewed |
| Spider 2.0 (P83), ICLR 2025 | Free enterprise SQL | o1-preview 21.3%; Qwen2.5-72B 6.17% | full text |
| BI-Bench (P89) | Tools vs plain SQL | Qwen3-8B 5.2 → 19.8 with tools (35.0 after RL) | full text |

**Takeaways**
- The coverage caveat is real: a question the semantic layer did not model scores 0.
- So keep the guarded single-SELECT fallback (report 07) labelled "not on screen", and pre-model the multi-hop paths: order → line → product → supplier.

---

## 8. Checks against the seed notes (reports 05 and 07)

| Seed claim | What the paper actually says | Verdict |
|---|---|---|
| Beyond Browsing: "ACL 2024… hybrid beats browsing by 24 points absolute (38.9%)" | 14.8% → 38.9% with GPT-4o ✔. The venue is **Findings of ACL 2025**; v1 reported 35.8%, and v3 reports 38.9%. Hybrid costs about 14× more per task than browsing ($1.4 vs $0.1). | Number confirmed. **Correct the venue, and mention the cost.** |
| Unbrowse: 950 ms vs 3,404 ms; 3.6× mean; 5.4× median; 94 domains | Confirmed in the full text. But it measures **latency only, not accuracy**, on one host, and the authors are from Unbrowse AI. Cold start is median 8.2 s. | Confirmed. Add the caveats. |
| Terminal agents "match or beat MCP and GUI agents at lower cost" | Terminal ≈ web in success and far cheaper than web. But **MCP tool-use was cheaper than terminal** for Sonnet ($0.51 vs $0.56) and Opus ($0.58 vs $1.22). Web beat terminal on GitLab for every model, and terminal fails where state lives only in the UI (dashboard chart values). | **Partly true.** Say "matches web agents at a fraction of the cost and clearly beats MCP tool-use on success". |
| VACP: "higher success with fewer tokens and lower latency than vision/DOM agents" | Success is confirmed by a wide margin. "Latency" is whole-task median duration. Token savings depend on the model (Gemini VACP-only ≈85k median tokens is more than Claude UI+DOM ≈10k). 15 tasks, frontier models only, no statistical tests. Small models get one qualitative sentence. **The repo has no licence.** | Confirmed with caveats. **Do not copy VACP code.** |
| EntWorld: "best stand-in; check licence and data release" | **Not publicly released** as of 2026-10-09: no code or data link, no HF dataset, and the `entworld` GitHub org is unrelated. The text says human performance is 37.39% while Table 1 says 85% (estimated). | **Drop it as a runnable stand-in.** Borrow only its schema-to-task generation method. Consider EnterpriseOps-Gym (Apache-2.0, released) instead. |
| ST-WebAgentBench: 222 tasks; CuP under two-thirds of completion | The abstract says 222 tasks; the current full text says 375 tasks with 3,057 policies. CR 24.3% vs CuP 15.0% (about 62%). Venue: ICLR 2026. | Confirmed. Note the task-count discrepancy. |
| AD-Bench: replay expert tool calls to keep ground truth fresh | Confirmed. **No code or data released.** The judge is also an evaluated model. | Confirmed. Copy the method only. |
| Report 07 §8: "the whole contract fits in the prompt, so no retrieval step" | Holds for 4 pages. But the brief's KPI is retrieval over **hundreds** of pages. RAG-MCP (all tools in prompt: 13.62% selection vs 43.13% with retrieval) and ToolRet show that selection degrades as catalogues grow. | **Build the retriever** (BM25 + dense + EasyTool-style docs) for the scale test, even if the demo app is small. |
| Report 07 §8: few-shot prompts (Synapse) | ToolACE: retrieved few-shot examples of *other* tools fell below zero-shot (irrelevance 23.66 vs 83.81 fine-tuned). | Use few-shot only for the *same* op, or none. |
| Implicit assumption that R1-Distill-32B can drive tools | BFCL v3: 53.5, below Qwen2.5-14B (58.7). ACBench and CRMArena (R1 9.0 in FC mode) agree. | **R1-distill should not emit calls.** |
| WorkArena "ICML 2024" | arXiv metadata says "preprint". The venue was not confirmed in this review. | Unverified here. Check before citing the venue. |

## 9. Open items and things that could not be verified

- **Code or data not found:** Terminal Agents, AXIS, UltraCUA, The Tool Illusion, EmbeWebAgent, ActionEngine, CI4A, AD-Bench, EntWorld, RAG-MCP, ScaleMCP, Brief Is Better, IFFC, ComInsight.
- **No licence declared, so treat as all-rights-reserved:** VACP, MSR-Web-Verbs, OSWorld-MCP, GROUND, TwinBI, BI-Agent, WidgetVA, WebMall-Interfaces.
- **Non-commercial:** CoAct-1, CRMArena and CRMArena-Pro (CC-BY-NC-4.0).
- **Non-standard:** ToolSandbox (Apple licence).
- **Abstract-only items:** P78 (the full-text HTML returned 404), P82, P84, P91.
- **Internal inconsistencies in the papers:** SkillWeaver (31.8% vs 39.8% relative), DAComp (Table 5 vs Table 8), DABstep (numeric tolerance), Sequeda (38.5 vs 38.7), EntWorld (human score), ST-WebAgentBench (222 vs 375 tasks).
- **Venues seen only in search listings:** WALT and OSWorld-MCP (ICLR 2026), and Hammer (ICLR 2025). OSWorld-MCP's ICLR-version numbers differ from arXiv v1 and were not verified.
- **WebMCP:** browser shipping status (Chrome origin trial, Edge flag) was seen only in blogs.
- **The Semantic Scholar API was rate-limited (HTTP 429) throughout.** Discovery used the arXiv API, OpenAlex, web search and arXiv HTML full text. Citation-based discovery may therefore have missed papers.

## 10. Full catalogue

Every row is in [`api_agents_papers.csv`](api_agents_papers.csv), with these fields: title, year, venue, arXiv/DOI, URL, cluster, core idea, headline results, verification level, code URL, licence, implement/borrow, risks, three relevance scores (0–5), hybrid evidence, small-model evidence, and the arXiv title check.

"Fit" scores 0–5 for the API agent, the VACP agent and evaluation design.

### A. API, tool and hybrid web/computer agents

| ID | Paper | Year | Venue (as seen) | Code / licence | Evidence level | Fit: API / VACP / Eval |
|---|---|---|---|---|---|---|
| P01 | [Beyond Browsing: API-Based Web Agents](https://arxiv.org/abs/2410.16464) | 2024 | Findings of ACL 2025 (ACL Anthology 2025.findings-acl.577); … | [repo](https://github.com/yueqis/API-Based-Agent), MIT | full text | 5 / 4 / 4 |
| P02 | [Internal APIs Are All You Need: Shadow APIs, Shared Discovery, and the Case Against …](https://arxiv.org/abs/2604.00694) | 2026 | arXiv preprint | [repo](https://github.com/unbrowse-ai/unbrowse), MIT (unbrowse); unbrowse-bench: no licence … | full text | 4 / 3 / 2 |
| P03 | [Terminal Agents Suffice for Enterprise Automation](https://arxiv.org/abs/2604.00073) | 2026 | arXiv preprint (under review) | none found, not checked (no repo) | full text | 5 / 3 / 4 |
| P04 | [Web Agents Should Use Typed Actions Instead of Click-Based Browsing](https://arxiv.org/abs/2602.17245) | 2026 | ICML 2026 Position Paper Track (per arXiv comments) | [repo](https://github.com/nlweb-ai/MSR-Web-Verbs), none detected (GitHub API license=null; no … | full text (also in app_declared_interfaces) | 5 / 5 / 2 |
| P05 | [AXIS: Efficient Human-Agent-Computer Interaction with API-First LLM-Based Agents](https://arxiv.org/abs/2409.17140) | 2024 | arXiv preprint | none found, not checked (no repo) | full text | 3 / 4 / 2 |
| P06 | [SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills](https://arxiv.org/abs/2504.07079) | 2025 | arXiv preprint | [repo](https://github.com/OSU-NLP-Group/SkillWeaver), MIT | full text | 3 / 4 / 2 |
| P07 | [WALT: Web Agents that Learn Tools](https://arxiv.org/abs/2510.01524) | 2025 | ICLR 2026 (per ICLR proceedings listing seen in search) | [repo](https://github.com/SalesforceAIResearch/WALT), MIT | full text | 3 / 5 / 3 |
| P08 | [The Tool Illusion: Rethinking Tool Use in Web Agents](https://arxiv.org/abs/2604.03465) | 2026 | COLM 2026 (per arXiv comments) | none found, not checked (no repo) | full text | 5 / 4 / 4 |
| P09 | [UFO2: The Desktop AgentOS](https://arxiv.org/abs/2504.14603) | 2025 | arXiv preprint | [repo](https://github.com/microsoft/UFO), MIT | full text | 3 / 4 / 2 |
| P10 | [CoAct-1: Computer-using Multi-Agent System with Coding Actions](https://arxiv.org/abs/2508.03923) | 2025 | arXiv preprint | [repo](https://github.com/SalesforceAIResearch/CoAct-1), CC-BY-NC-4.0 (LICENSE.txt; GitHub reports … | full text | 3 / 4 / 2 |
| P11 | [UltraCUA: A Foundation Model for Computer Use Agents with Hybrid Action](https://arxiv.org/abs/2510.17790) | 2025 | arXiv preprint | none found, not checked (no official repo) | full text | 2 / 3 / 2 |
| P12 | [MCPWorld: A Unified Benchmarking Testbed for API, GUI, and Hybrid Computer Use Agents](https://arxiv.org/abs/2506.07672) | 2025 | arXiv preprint | [repo](https://github.com/SAAgent/MCPWorld), MIT | full text | 3 / 4 / 5 |
| P13 | [OSWorld-MCP: Benchmarking MCP Tool Invocation In Computer-Use Agents](https://arxiv.org/abs/2510.24563) | 2025 | ICLR 2026 (per ICLR virtual poster listing seen in search; … | [repo](https://github.com/X-PLUG/OSWorld-MCP), none found (GitHub reports no licence) | full text | 3 / 3 / 5 |
| P14 | [Screenshots or Tools? Eliciting Tool Use and Managing Multimodal Context in Hybrid …](https://arxiv.org/abs/2608.03327) | 2026 | arXiv preprint | [repo](https://github.com/redai-studio/hybrid-routing-agent), Apache-2.0 | full text | 4 / 4 / 4 |

### B. REST/OpenAPI tool use, tool retrieval and small-model function calling

| ID | Paper | Year | Venue (as seen) | Code / licence | Evidence level | Fit: API / VACP / Eval |
|---|---|---|---|---|---|---|
| P15 | [The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of …](https://proceedings.mlr.press/v267/patil25a.html) | 2025 | ICML 2025 (PMLR 267:48371-48392) | [repo](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard), Apache-2.0 (read from the repo LICENSE file; … | full text | 5 / 3 / 5 |
| P16 | [Qwen3 Technical Report](https://arxiv.org/abs/2505.09388) | 2025 | arXiv preprint | [repo](https://github.com/QwenLM/Qwen3), not checked (no LICENSE file found at repo … | full text | 5 / 4 / 4 |
| P17 | [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948) | 2025 | Nature 645:633-638 (2025) | [repo](https://github.com/deepseek-ai/DeepSeek-R1), MIT (read from the repo LICENSE file) | full text | 3 / 3 / 1 |
| P18 | [Can Compressed LLMs Truly Act? An Empirical Evaluation of Agentic Capabilities in LLM …](https://arxiv.org/abs/2505.19433) | 2025 | ICML 2025 (poster, per arXiv comment) | [repo](https://github.com/pprp/ACBench), MIT (read from the repo LICENSE file) | full text | 4 / 3 / 2 |
| P19 | [Brief Is Better: Non-Monotonic Chain-of-Thought Budget Effects in Function-Calling …](https://arxiv.org/abs/2604.02155) | 2026 | arXiv preprint | none found, none found | full text | 5 / 5 / 3 |
| P20 | [Nemotron-Research-Tool-N1: Exploring Tool-Using Language Models with Reinforced Reasoning](https://arxiv.org/abs/2505.00024) | 2025 | arXiv preprint | [repo](https://github.com/NVlabs/Tool-N1), Apache-2.0 (read from the repo LICENSE file) | full text | 4 / 3 / 3 |
| P21 | [ToolRL: Reward is All Tool Learning Needs](https://arxiv.org/abs/2504.13958) | 2025 | NeurIPS 2025 (main track, per NeurIPS proceedings listing) | [repo](https://github.com/qiancheng0/ToolRL), Apache-2.0 (read from the repo LICENSE file) | full text | 3 / 2 / 3 |
| P22 | [ToolACE: Winning the Points of LLM Function Calling](https://arxiv.org/abs/2409.00920) | 2024 | ICLR 2025 | [repo](https://huggingface.co/Team-ACE), not checked | full text | 4 / 3 / 3 |
| P23 | [APIGen: Automated Pipeline for Generating Verifiable and Diverse Function-Calling Datasets](https://arxiv.org/abs/2406.18518) | 2024 | NeurIPS 2024 Datasets and Benchmarks Track | [repo](https://github.com/SalesforceAIResearch/xLAM), Apache-2.0 for the code repo (read from … | full text | 4 / 3 / 5 |
| P24 | [Hammer: Robust Function-Calling for On-Device Language Models via Function Masking](https://arxiv.org/abs/2410.04587) | 2024 | ICLR 2025 (per mlanthology/AMiner listings; OpenReview page … | [repo](https://github.com/MadeAgents/Hammer), Apache-2.0 (read from the repo LICENSE file) | full text | 4 / 3 / 3 |
| P25 | [NESTFUL: A Benchmark for Evaluating LLMs on Nested Sequences of API Calls](https://arxiv.org/abs/2409.03797) | 2024 | EMNLP 2025 main (ACL Anthology 2025.emnlp-main.1702) | [repo](https://github.com/IBM/NESTFUL), Apache-2.0 (read from the repo LICENSE file; … | full text | 5 / 4 / 5 |
| P26 | [Retrieval Models Aren't Tool-Savvy: Benchmarking Tool Retrieval for Large Language Models …](https://arxiv.org/abs/2503.01763) | 2025 | ACL 2025 (per arXiv comment) | [repo](https://github.com/mangopy/tool-retrieval-benchmark), Apache-2.0 (read from the repo LICENSE file) | full text | 5 / 5 / 5 |
| P27 | [EASYTOOL: Enhancing LLM-based Agents with Concise Tool Instruction](https://aclanthology.org/2025.naacl-long.44/) | 2024 | NAACL 2025 (long) | [repo](https://github.com/microsoft/JARVIS/tree/main/easytool), MIT (read from the microsoft/JARVIS LICENSE … | full text | 5 / 5 / 2 |
| P28 | [Tool Documentation Enables Zero-Shot Tool-Usage with Large Language Models](https://arxiv.org/abs/2308.00675) | 2023 | arXiv preprint | none found, none found | full text | 4 / 4 / 1 |
| P29 | [ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs](https://arxiv.org/abs/2307.16789) | 2023 | ICLR 2024 | [repo](https://github.com/OpenBMB/ToolBench), Apache-2.0 (read from the repo LICENSE file) | full text | 4 / 3 / 3 |
| P30 | [StableToolBench: Towards Stable Large-Scale Benchmarking on Tool Learning of Large …](https://arxiv.org/abs/2403.07714) | 2024 | Findings of ACL 2024 (2024.findings-acl.664) | [repo](https://github.com/THUNLP-MT/StableToolBench), Apache-2.0 (read from the repo LICENSE file) | full text | 3 / 2 / 5 |
| P31 | [AnyTool: Self-Reflective, Hierarchical Agents for Large-Scale API Calls](https://arxiv.org/abs/2402.04253) | 2024 | ICML 2024 (PMLR 235:11812-11829) | [repo](https://github.com/dyabel/AnyTool), Apache-2.0 (read from the repo LICENSE file) | full text | 5 / 5 / 2 |
| P32 | [Gorilla: Large Language Model Connected with Massive APIs](https://arxiv.org/abs/2305.15334) | 2023 | NeurIPS 2024 | [repo](https://github.com/ShishirPatil/gorilla), Apache-2.0 (read from the repo LICENSE file) | full text | 4 / 3 / 4 |
| P33 | [API-Bank: A Comprehensive Benchmark for Tool-Augmented LLMs](https://arxiv.org/abs/2304.08244) | 2023 | EMNLP 2023 | [repo](https://github.com/AlibabaResearch/DAMO-ConvAI), MIT (read from the repo LICENSE file) | full text | 4 / 3 / 4 |
| P34 | [RestGPT: Connecting Large Language Models with Real-World RESTful APIs](https://arxiv.org/abs/2306.06624) | 2023 | arXiv preprint | [repo](https://github.com/Yifan-Song793/RestGPT), MIT (read from the repo LICENSE file) | full text | 5 / 4 / 3 |
| P35 | [TinyAgent: Function Calling at the Edge](https://arxiv.org/abs/2409.00608) | 2024 | EMNLP 2024 Demo (per arXiv comment) | [repo](https://github.com/SqueezeAILab/TinyAgent), MIT (read from the repo LICENSE file) | full text | 5 / 4 / 4 |
| P36 | [Octopus v2: On-device language model for super agent](https://arxiv.org/abs/2404.01744) | 2024 | arXiv preprint | none found, not checked | full text | 3 / 4 / 1 |
| P37 | [RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation](https://arxiv.org/abs/2505.03275) | 2025 | arXiv preprint | none found, none found | full text | 4 / 5 / 2 |
| P38 | [ScaleMCP: Dynamic and Auto-Synchronizing Model Context Protocol Tools for LLM Agents](https://arxiv.org/abs/2505.06416) | 2025 | arXiv preprint | none found, none found | full text | 4 / 5 / 3 |
| P39 | [Small Reasoning Models are Instruction Followers in Function Calling](https://arxiv.org/abs/2608.22472) | 2026 | arXiv preprint | none found, none found | full text | 4 / 4 / 2 |

### C. Benchmarks with API/tool app environments and enterprise tasks

| ID | Paper | Year | Venue (as seen) | Code / licence | Evidence level | Fit: API / VACP / Eval |
|---|---|---|---|---|---|---|
| P40 | [AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding …](https://arxiv.org/abs/2407.18901) | 2024 | ACL 2024 (arXiv comment: 'ACL'24 Camera Ready') | [repo](https://github.com/stonybrooknlp/appworld), Apache-2.0 (LICENSE file in repo root, … | full text | 5 / 3 / 5 |
| P41 | [tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains](https://arxiv.org/abs/2406.12045) | 2024 | arXiv preprint | [repo](https://github.com/sierra-research/tau-bench), MIT | full text | 5 / 3 / 5 |
| P42 | [tau^2-Bench: Evaluating Conversational Agents in a Dual-Control Environment](https://arxiv.org/abs/2506.07982) | 2025 | arXiv preprint | [repo](https://github.com/sierra-research/tau2-bench), MIT | full text | 4 / 4 / 5 |
| P43 | [WorkArena: How Capable Are Web Agents at Solving Common Knowledge Work Tasks?](https://arxiv.org/abs/2403.07718) | 2024 | arXiv preprint (comment: preprint) | [repo](https://github.com/ServiceNow/WorkArena), Apache-2.0 | full text | 3 / 5 / 5 |
| P44 | [WorkArena++: Towards Compositional Planning and Reasoning-based Common Knowledge Work …](https://arxiv.org/abs/2407.05291) | 2024 | arXiv preprint | [repo](https://github.com/ServiceNow/WorkArena), Apache-2.0 | full text | 3 / 5 / 5 |
| P45 | [ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool …](https://arxiv.org/abs/2408.04682) | 2024 | arXiv preprint | [repo](https://github.com/apple/ToolSandbox), Apple custom licence (LICENSE begins … | full text | 5 / 4 / 5 |
| P46 | [WorkBench: a Benchmark Dataset for Agents in a Realistic Workplace Setting (+ WorkBench …](https://arxiv.org/abs/2405.00823) | 2024 | arXiv preprint | [repo](https://github.com/olly-styles/WorkBench), MIT | full text | 5 / 2 / 5 |
| P47 | [CRMArena: Understanding the Capacity of LLM Agents to Perform Professional CRM Tasks in …](https://arxiv.org/abs/2411.02305) | 2024 | NAACL 2025 (arXiv comment) | [repo](https://github.com/SalesforceAIResearch/CRMArena), CC-BY-NC-4.0 (LICENSE.txt in repo); HF … | full text | 5 / 2 / 4 |
| P48 | [CRMArena-Pro: Holistic Assessment of LLM Agents Across Diverse Business Scenarios and …](https://arxiv.org/abs/2505.18878) | 2025 | arXiv preprint | [repo](https://github.com/SalesforceAIResearch/CRMArena), CC-BY-NC-4.0 (same repo as CRMArena) | full text | 5 / 2 / 4 |
| P49 | [TheAgentCompany: Benchmarking LLM Agents on Consequential Real World Tasks](https://arxiv.org/abs/2412.14161) | 2024 | arXiv preprint | [repo](https://github.com/TheAgentCompany/TheAgentCompany), MIT | full text | 3 / 3 / 4 |
| P50 | [ST-WebAgentBench: A Benchmark for Evaluating Safety and Trustworthiness in Web Agents](https://arxiv.org/abs/2410.06703) | 2024 | ICLR 2026 (arXiv comment) | [repo](https://github.com/segev-shlomov/ST-WebAgentBench), Apache (LICENSE text: 'All code and data is … | full text | 3 / 5 / 5 |
| P51 | [EntWorld: A Holistic Environment and Benchmark for Verifiable Enterprise GUI Agents](https://arxiv.org/abs/2601.17722) | 2026 | arXiv preprint | none found, Unknown / not released | full text | 4 / 4 / 5 |
| P52 | [EnterpriseOps-Gym: Environments and Evaluations for Stateful Agentic Planning and Tool …](https://arxiv.org/abs/2603.13594) | 2026 | arXiv preprint | [repo](https://github.com/ServiceNow/EnterpriseOps-Gym), Apache-2.0 (repo LICENSE; HF dataset tag … | full text | 5 / 2 / 5 |
| P53 | [AD-Bench: A Real-World, Trajectory-Aware Advertising Analytics Benchmark for LLM Agents](https://arxiv.org/abs/2602.14257) | 2026 | arXiv preprint | none found, n/a (no repo given) | full text (also in analytics_bi_agents) | 5 / 4 / 5 |
| P54 | [SaaS-Bench: Can Computer-Use Agents Leverage Real-World SaaS to Solve Professional …](https://arxiv.org/abs/2605.15777) | 2026 | arXiv preprint | [repo](https://github.com/UniPat-AI/SaaS-Bench), Apache-2.0 | full text | 2 / 4 / 4 |
| P55 | [MCPMark: A Benchmark for Stress-Testing Realistic and Comprehensive MCP Use](https://arxiv.org/abs/2509.24002) | 2025 | arXiv preprint | [repo](https://github.com/eval-sys/mcpmark), Apache-2.0 | full text | 5 / 3 / 5 |
| P56 | [MCP-Universe: Benchmarking Large Language Models with Real-World Model Context Protocol …](https://arxiv.org/abs/2508.14704) | 2025 | arXiv preprint | [repo](https://github.com/SalesforceAIResearch/MCP-Universe), Apache-2.0 (GitHub search API licence field) | full text | 4 / 2 / 4 |
| P57 | [MCP-Bench: Benchmarking Tool-Using LLM Agents with Complex Real-World Tasks via MCP …](https://arxiv.org/abs/2508.20453) | 2025 | arXiv preprint | [repo](https://github.com/Accenture/mcp-bench), Apache-2.0 (seen on GitHub repo page; API … | full text | 4 / 1 / 4 |
| P58 | [MCP-Atlas: A Large-Scale Benchmark for Tool-Use Competency with Real MCP Servers](https://arxiv.org/abs/2602.00933) | 2026 | arXiv preprint | [repo](https://github.com/scaleapi/mcp-atlas), MIT | full text | 4 / 2 / 5 |

### D. App-declared interfaces (VACP, WebMCP, component registries)

| ID | Paper | Year | Venue (as seen) | Code / licence | Evidence level | Fit: API / VACP / Eval |
|---|---|---|---|---|---|---|
| P59 | [VACP: Visual Analytics Context Protocol](https://arxiv.org/abs/2603.29322) | 2026 | arXiv preprint (cs.HC; v1 31 Mar 2026) | [repo](https://github.com/ETH-IVIA-Lab/VACP), none declared (GitHub API license=null; no … | full text | 3 / 5 / 4 |
| P60 | [EmbeWebAgent: Embedding Web Agents into Any Customized UI](https://arxiv.org/abs/2602.14865) | 2026 | arXiv preprint (Technical Report; IBM Research Europe) | [repo](https://youtu.be/Cy06Ljee1JQ), n/a (no code release found); paper CC BY 4.0 | full text | 4 / 4 / 3 |
| P61 | [WebMCP (W3C Web Machine Learning Community Group Draft Community Group Report)](https://webmachinelearning.github.io/webmcp/) | 2026 | W3C Community Group Draft Report (not a W3C Standard, not … | [repo](https://github.com/webmachinelearning/webmcp), spec under W3C Community Contributor License … | full text | 3 / 5 / 1 |
| P62 | [Build the web for agents, not agents for the web](https://arxiv.org/abs/2506.10953) | 2025 | arXiv preprint (position paper) | none found, n/a | full text | 2 / 4 / 1 |
| P63 | [ActionEngine: From Reactive to Programmatic Web Agents via State Machine Memory](https://arxiv.org/abs/2602.20502) | 2026 | arXiv preprint | none found, n/a | full text | 5 / 4 / 3 |
| P64 | [AutoWebWorld: Synthesizing Infinite Verifiable Web Environments via Finite State Machines](https://arxiv.org/abs/2602.14296) | 2026 | arXiv preprint | [repo](https://evanwu1125.github.io/AWW_homepage/), unknown | full text | 2 / 3 / 4 |
| P65 | [Where Did It Go Wrong? Process-Level Evaluation of Web Agents with Semantic State …](https://arxiv.org/abs/2606.15673) | 2026 | arXiv preprint | [repo](https://jiwanchung.github.io/webstep), unknown | full text | 2 / 3 / 5 |
| P66 | [CI4A: Semantic Component Interfaces for Agents Empowering Web Automation](https://arxiv.org/abs/2601.14790) | 2026 | arXiv preprint | none found, unknown | full text | 3 / 5 / 3 |
| P67 | [Building the Web for Agents: A Declarative Framework for Agent-Web Interaction (VOIX)](https://arxiv.org/abs/2511.11287) | 2025 | arXiv preprint; a version titled 'VOIX: A Web-Native … | none found, unknown (paper CC BY 4.0) | full text | 3 / 5 / 2 |
| P68 | [MCP vs RAG vs NLWeb vs HTML: A Comparison of the Effectiveness and Efficiency of …](https://arxiv.org/abs/2511.23281) | 2025 | arXiv preprint (OpenAlex also lists ACM DOI … | [repo](https://github.com/wbsg-uni-mannheim/WebMall-Interfaces), none detected (no LICENSE file found on … | full text | 5 / 3 / 5 |
| P69 | [WidgetVA: A Widget-Centric Framework and Benchmark for Agentic Visual Analytics](https://arxiv.org/abs/2609.24094) | 2026 | arXiv preprint (cs.HC) | [repo](https://github.com/Hiverwin/widgetva), none detected (no LICENSE file found on main) | full text | 3 / 5 / 5 |
| P70 | [TwinBI: An Agentic Digital Twin for Efficient Augmented Interactions with Business …](https://arxiv.org/abs/2606.13731) | 2026 | arXiv preprint | [repo](https://github.com/simonjisu/TwinBI), none detected (no LICENSE file found on main) | full text (also in analytics_bi_agents) | 5 / 5 / 4 |
| P71 | [Designing Agent-Ready Websites for AI Web Agents: A Framework for Machine Readability, …](https://arxiv.org/abs/2607.12056) | 2026 | arXiv preprint | none found, unknown | full text | 1 / 3 / 3 |
| P72 | [WebMCP Tool Surface Poisoning: Runtime Manipulation Attacks on LLM Agents](https://arxiv.org/abs/2606.06387) | 2026 | arXiv preprint (cs.CR) | none found, unknown (paper CC BY 4.0) | full text | 1 / 4 / 2 |
| P73 | [WebMCP-Phalanx: Enforcing and Characterizing Trust Boundaries for Browser-Integrated LLM …](https://arxiv.org/abs/2608.24017) | 2026 | arXiv preprint (cs.CR) | none found, unknown | full text | 1 / 3 / 1 |
| P74 | [MCP Apps: Interactive User Interfaces for MCP (SEP-1865, MCP extension; builds on MCP-UI …](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp) | 2025 | Model Context Protocol Specification Enhancement Proposal … | [repo](https://github.com/modelcontextprotocol/ext-apps), ext-apps: Apache-2.0 for new contributions … | verified via official SEP page summary … | 2 / 2 / 0 |

### E. Analytics and BI agents, semantic layers vs text-to-SQL

| ID | Paper | Year | Venue (as seen) | Code / licence | Evidence level | Fit: API / VACP / Eval |
|---|---|---|---|---|---|---|
| P75 | [A Benchmark to Understand the Role of Knowledge Graphs on Large Language Model's Accuracy …](https://arxiv.org/abs/2311.07509) | 2023 | arXiv preprint | [repo](https://github.com/datadotworld/cwd-benchmark-data), Apache-2.0 (GitHub API) | full text | 4 / 3 / 5 |
| P76 | [Increasing the LLM Accuracy for Question Answering: Ontologies to the Rescue!](https://arxiv.org/abs/2405.11706) | 2024 | arXiv preprint | [repo](https://github.com/datadotworld/cwd-benchmark-data), Apache-2.0 (GitHub API) | full text | 5 / 3 / 5 |
| P77 | [Semantic Layer vs. Text-to-SQL: 2026 Benchmark Update (dbt Labs)](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026) | 2026 | vendor blog, not peer-reviewed | [repo](https://github.com/dbt-labs/dbt-llm-sl-bench), NOASSERTION (GitHub API; licence not … | full text | 4 / 3 / 4 |
| P78 | [Semantic Layers for Reliable LLM-Powered Data Analytics: A Paired Benchmark of Accuracy …](https://arxiv.org/abs/2604.25149) | 2026 | arXiv preprint | none found, n/a (no code link found) | full text | 4 / 3 / 4 |
| P79 | [Which Part of the Context Layer Does the Work? Separating Semantic Content from Retrieval …](https://arxiv.org/abs/2609.22259) | 2026 | arXiv preprint | [repo](https://github.com/flyersworder/agentic-data-contracts), MIT (GitHub API) | full text | 5 / 4 / 5 |
| P80 | [GROUND: Reducing Hallucinations in LLM-Based Enterprise Analytics Through Governed …](https://arxiv.org/abs/2608.26157) | 2026 | arXiv preprint | [repo](https://github.com/aravindsp/ground-benchmark), none declared (GitHub API license=null) | full text | 5 / 3 / 5 |
| P81 | [Business Truth, not SQL Accuracy: A Rule-Gated 7B Analytics Agent Outperforms a …](https://arxiv.org/abs/2608.09254) | 2026 | arXiv preprint | [repo](https://github.com/k-w-lee/query_proof), MIT (GitHub API) | full text | 5 / 3 / 5 |
| P82 | [Never the Number: Structural Abstention for AI Systems Whose Answers Are Consumed as Fact](https://arxiv.org/abs/2608.13926) | 2026 | arXiv preprint (technical report) | none found, n/a | abstract only | 5 / 4 / 3 |
| P83 | [Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows](https://arxiv.org/abs/2411.07763) | 2024 | ICLR 2025 (Oral) per arXiv comments | [repo](https://github.com/xlang-ai/Spider2), MIT (GitHub API) | full text | 2 / 1 / 3 |
| P84 | [BEAVER: An Enterprise Benchmark for Text-to-SQL](https://arxiv.org/abs/2409.02038) | 2024 | arXiv preprint | [repo](https://beaverbench.github.io/), not verified (repo not resolved; GitHub API … | abstract only | 2 / 2 / 4 |
| P85 | [BIRD-INTERACT: Re-imagining Text-to-SQL Evaluation for Large Language Models via Lens of …](https://arxiv.org/abs/2510.05318) | 2025 | ICLR 2026 (Oral) per arXiv comments | [repo](https://github.com/bird-bench/BIRD-Interact), MIT (GitHub API) | full text | 3 / 2 / 4 |
| P86 | [InsightBench: Evaluating Business Analytics Agents Through Multi-Step Insight Generation](https://arxiv.org/abs/2407.06423) | 2024 | ICLR 2025 per arXiv comments | [repo](https://github.com/ServiceNow/insight-bench), MIT (GitHub API) | full text | 3 / 3 / 5 |
| P87 | [DABstep: Data Agent Benchmark for Multi-step Reasoning](https://arxiv.org/abs/2506.23719) | 2025 | arXiv preprint | [repo](https://huggingface.co/datasets/adyen/DABstep), Dataset CC BY 4.0 (per paper); code licence … | full text | 3 / 2 / 5 |
| P88 | [DAComp: Benchmarking Data Agents across the Full Data Intelligence Lifecycle](https://arxiv.org/abs/2512.04324) | 2025 | arXiv preprint | [repo](https://da-comp.github.io), not verified (repo not resolved; GitHub API … | full text | 3 / 2 / 5 |
| P89 | [BI-Agent and BI-Bench: Towards Automating End-to-End Business Intelligence](https://arxiv.org/abs/2609.20886) | 2026 | arXiv preprint | [repo](https://github.com/Hu-Chuxuan/bi-agent), none declared (GitHub API license=null) | full text | 4 / 3 / 4 |
| P90 | [Structured Composition of Verifiable Atomic Insights for Table-to-Report Generation](https://arxiv.org/abs/2610.03525) | 2026 | arXiv preprint | none found, n/a (no repo given) | full text | 4 / 3 / 4 |
| P91 | [Business Utility of Large Language Models as Exploratory Data Analysis Agents](https://arxiv.org/abs/2606.00051) | 2026 | arXiv preprint | none found, not verified | abstract only | 3 / 2 / 5 |
