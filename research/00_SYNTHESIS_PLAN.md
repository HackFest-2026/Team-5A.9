# Plan: two agents, one data decision (9 Oct 2026)

This plan merges three research reports in this folder:

- `api_agents_literature.md`: 91 papers, ranked.
- `citation_chase.md`: papers citing the leading designs.
- `erp_data_comparison.md`: five ERPs compared with WWI.

Key claims were spot-checked against primary sources (arXiv, GitHub and the code itself).

## 1. Data: ERP vs ours

**Finding.** None of the candidate ERPs ships data you can analyse. Checked against the official sources:

- ERPNext's demo data is 3 customers, 5 sales orders, 10 items and 10 purchase orders.
- Bigcapital has only import templates. It has no sales-order or purchase-order modules at all: just invoices, estimates, receipts and bills.
- OpenBoxes has opening stock but no orders.
- The open-source IDURAR is stripped down to clients, invoices and payments.

So **WWI's data is needed whichever app we use.** The real choice is which *app* sits on top of it.

| Axis (1–5) | WWI + our app | ERPNext | Bigcapital | metasfresh | OpenBoxes | IDURAR |
|---|---|---|---|---|---|---|
| Data richness (with WWI loaded) | 5 | 4 | 2 | 4 | 2 | 1 |
| Verifiable ground truth | 5 | 3 | 2 | 2 | 2 | 1 |
| API for an agent | 3 | 4 | 4 | 3 | 2 | 1 |
| VACP feasibility | 5 | 3 | 4 | 3 | 2 | 2 |
| "Real app" credibility | 2 | 5 | 3 | 4 | 3 | 1 |
| Setup safety | 5 | 3 | 3 | 1 | 2 | 2 |

**Decision.**

1. **Primary: WWI and our app, which is the scored benchmark.** It is the only option with an independent answer key: 276 of 276 graded steps match. Both agents are built and evaluated here first.
2. **Cheap upgrades to our app:**
   - publish an OpenAPI spec generated from `catalog/operations.json`;
   - add token authentication;
   - build a native `window.__vacp` bridge into the app.

   These make it look and behave like an enterprise API.
3. **Stretch: ERPNext as a second target.** ERPNext is the best ERP fit: about 16 of WWI's 20 entities, group-by on its list API, filters in the URL, and a `/meta` endpoint that describes every page.
   - Load a slice of WWI into it: all customers, items and suppliers, plus Jan–May 2016 orders, invoices and purchase orders (about 10,000 orders).
   - Add a second "adapter" so the same agent runs against ERPNext's REST API.
   - Report how closely its answers agree with our answer key on the measures that survive the move.
   - Estimated at 35–55 hours, so do it only after both agents work on our app. It answers "did you build the app for the agent?" and the client's real-API expectation.
4. **Drop IDURAR and OpenBoxes. Keep Bigcapital only as a fallback** if the client weights a documented OpenAPI and React UI above data fit.

## 2. Model choice (changes our setup)

| Model | BFCL v3 (Qwen3 report) | Use |
|---|---|---|
| Qwen2.5-14B-Instruct (vLLM on GPU 0, tool parser on) | 58.7 | **Emits every tool call** |
| DeepSeek-R1-Distill-Qwen-32B (llama.cpp on GPU 1) | 53.5 | Optional: planning or explanations only, never emitting calls |

Expect roughly 70–80% on single calls and only **20–30% on long multi-turn sequences** at this model size. Reliability must therefore come from the **harness**: gates, validators and a small tool set, not from the model.

## 3. Shared core (used by both agents)

| Component | What it does | Source |
|---|---|---|
| Contract loader | Loads `/api/contract` once: measures, dimensions, glossary, graph, playbooks | Ours (v2) |
| Small hand-written tool set | About 6 composable operations, not hundreds | The Tool Illusion (2604.03465); Beyond Text-to-SQL (2605.21027) |
| Name resolution, then clarify or abstain | Ask when a name is ambiguous; never guess | QueryProof, GROUND/OBQC |
| **Deterministic gates before acting** | Must read before changing state; parameters checked against the Contract; up to 3 repairs, then abstain | LedgerAgent (2606.20529); Reason Less, Verify More (2607.07405): +12 pp on τ²-bench |
| **Finish gate** | Before saying "done", check the applied state matches the intent (`applied` echo or `window.wwiState`), and detect loops | Mingbird (2610.02001, Apache-2.0); False Success: LLM judges reach AUROC ≤ 0.65, so check with code, not an LLM |
| Faithfulness check | Every figure in the answer must trace to a tool result, or to code arithmetic over tool results | Ours; MCP-Atlas claim-level scoring |
| Code shapes the data | Code, not the LLM, binds one call's output to the next and reshapes results | NESTFUL, RestGPT |

## 4. Agent 1: API-based (what the client expects)

- **Template:** Beyond Browsing's API agent, with two-stage API-doc retrieval. Its code is MIT-licensed.
- **Tools:** `analyze`, `resolve`, `related`, `records`, `metric`, plus Contract lookups (`list_metrics`, `lookup_metric`), following the "context layer" tool surface (2609.22259).
- **Scale:** for the hundreds-of-pages retrieval KPI, retrieve documentation instead of putting every tool in the prompt. Tool selection fell from 43.13% with retrieval to 13.62% with all tools in context (EasyTool, ToolRet, AnyTool).
- **Plan first:** where possible, commit to a checked plan, then execute it, and re-plan only on failure (ActionEngine; Plan-Then-Execute, 2605.14290).

## 5. Agent 2: VACP-style in-app bridge (our differentiator)

- **We write the bridge ourselves**, mirroring VACP's published interface: `window.__vacp.getCapabilities / getState / execute`. The VACP repository has **no licence**, and its chart adapters target Vega-Lite and Mosaic, which our app doesn't use.
- **Actions:**
  - `navigate`;
  - `configure_view` (measure, dimension, period, filters, sort);
  - `drill`;
  - `select_entity`.

  Each action declares pre- and postconditions (typed web verbs).
- Read-only queries are kept separate from state-changing actions (WidgetVA).
- Only actions valid on the current page are exposed (EmbeWebAgent).
- The action list is frozen when the page loads, and action names come from an allowlist, as protection against tool poisoning.
- **Access:** through Playwright's `page.evaluate` (MCP-style tools), or a chat panel inside the page.
- **Generalising the design:** ASIL (2608.26991, code released) uses typed JSON state plus `{action_type, target, params}` actions. It scored 81.6 vs 6.6 for screenshot-and-click, and 75.8 with an untrained 27B open model.
- **Evidence:** in VACP's own tests, screen-and-page agents succeeded 28–51% of the time, against "near-perfect" with VACP. **Risk:** the pattern has no independent replication yet, and declared tools can drift out of sync with the UI. Mitigate by generating the action list from the same Contract the UI uses.
- **Hybrid rule:** with a complete declared interface, also acting through the UI gave no gain. Use the UI channel to **verify and show the user**, not to act.

## 6. Evaluation (both agents, same tasks)

- **Task sets:**
  - v1: 30 tasks;
  - v2: 46 multi-step chains and 218 utterances;
  - retrieval: 150 queries over 293 pages.
- **Metrics to copy:**
  - **pass^k**, success across k repeated runs (τ-bench);
  - **milestones and minefields**, for partial credit and for action hallucination (ToolSandbox);
  - **state diff** of intended vs applied state (AppWorld style);
  - **false-success rate**;
  - **claim-level faithfulness**;
  - **Completion under Policy** (ST-WebAgentBench).
- **Ablations:** API agent vs VACP agent vs hybrid; gates ON vs OFF; Qwen2.5-14B vs R1-32B as the caller.
- Keep v2's held-out tests out of all tuning. Use τ²-bench rather than τ-bench if we cite an external benchmark.

## 7. Order of work

1. Shared core and the API agent on our app, with `analyze`, `resolve` and `related` already built. Run the v1 and v2 development sets.
2. Native `window.__vacp` bridge, then the VACP agent on the same tasks.
3. Evaluation harness with pass^k, gates on and off, and the agent comparison.
4. OpenAPI spec and authentication for our API.
5. *(Stretch)* ERPNext slice and adapter.

## 8. Corrections to earlier notes

- *Beyond Browsing* appeared in **Findings of ACL 2025**, not ACL 2024. Its hybrid agent scored 38.9%, API-only 29.2% and browsing 14.8%, at about 14× the cost per task.
- **EntWorld isn't publicly released.** EnterpriseOps-Gym (Apache-2.0) is the released alternative.
- Unbrowse reports latency only, measured by the company's own authors.
- Code licences:
  - **no licence:** VACP, MSR-Web-Verbs, TwinBI, GROUND, WidgetVA;
  - **non-commercial (CC-BY-NC):** CRMArena, CoAct-1.

## 9. Addendum (10 Oct 2026): story, benchmark, final sweep

### 9.1 The gap our story is built on (Beyond Browsing, Figure 4)
Beyond Browsing analysed its API-only agent on 100 randomly sampled WebArena tasks:

| Outcome | Share |
|---|---|
| Correct | 33% |
| **Unsolvable with APIs alone** (the endpoint needed does not exist) | **50%** |
| API-usage error | 11% |
| Task misunderstanding | 6% |

- On the 50 tasks that APIs *could* solve, the agent got 66% right.
- "Unsolvable" means a missing endpoint, for example "no API to retrieve or delete reviews". It doesn't mean the model reasoned badly.
- Endpoint coverage varied by site: GitLab 988 (Good), Map 53, Shopping 556 (Fair), Reddit 31 (Poor).
- On Reddit, adding 13 hand-written endpoints raised success from 9.4% to 18.9%. Coverage is the lever.
- The hybrid (API + browsing) agent reached 38.9%, against 29.2% for API only and 14.8% for browsing only.

**Our claim:** the unsolvable half is a *coverage* problem. VACP closes it by turning the application's own UI capabilities into typed, declared actions that sit alongside the API:
- `navigate`, `configure_view`, `drill`, `select_entity`;
- reading the rendered view state through `getState`.

So "no endpoint exists" becomes "a declared action exists". This replaces the hybrid agent's raw clicking, which is the weakest channel (14.8%).

**Caveat to state openly:** VACP covers only what the page exposes. A capability that isn't in the UI either (or isn't declared) stays unsolvable. And VACP's own "near-perfect" results haven't been independently replicated, so we measure it ourselves.

### 9.2 Benchmark standard
- **External standard: WebArena, run through WebArena-Verified** (ServiceNow, NeurIPS 2025 workshop).
  - All 812 tasks were audited and the evaluators fixed.
  - Scoring is deterministic: no LLM judge, no substring matching.
  - It ships on Docker and PyPI, with a smaller "Hard" subset. Its size is reported as 137 or 258 tasks; check the repo before citing either.
  - It runs the same sites Beyond Browsing used, so our numbers are directly comparable to the 29.2%, 38.9% and 50% figures.
  - Report the configuration with every number: subset, scaffold, model, step budget and attempts.
- **Domain evaluation: our WWI v2 tasks plus ERPNext.** WebArena has no ERP or analytics site, so it can't test multi-step analysis or app-level UI state. Our task sets stay the place where those KPIs are scored:
  - 46 multi-step chains, 218 utterances and 150 retrieval queries over 293 pages;
  - an independent answer key.
- **Cost warning:** the full WebArena stack is several large Docker images, about 100 GB or more. Start with a single site, Shopping Admin or GitLab, plus the Hard subset.

### 9.3 Final sweep result: decision kept
No new paper beat the chosen design. Three papers sharpen it:
- **WALT** (Salesforce, arXiv 2510.01524): reverse-engineers website functionality into callable tools (search, filter, create, and so on), evaluated on WebArena and VisualWebArena. It is the closest relative to "VACP fills the endpoint gap", so cite it as related work. I haven't checked whether its code is released.
- **Plan-Then-Execute** (arXiv 2605.14290, already in the plan): reports that 81.28% of WebArena tasks are solvable by a purely programmatic plan over a typed API layer. This supports adding declared actions.
- **Callability Is Not Operability** (arXiv 2608.23628): a valid call isn't enough. The interface must also return state, effect semantics and postconditions. This supports our `applied` echo, `getState` and the finish gate.
- **Unbrowse / Internal APIs** (2604.00694): latency only, measured by its own authors. Background reading only.

### 9.4 API structure rules we adopt
See the explanation given on 10 Oct. In short:
- task-level operations, not raw tables;
- typed and enumerated parameters, with one example per tool;
- echo the applied state;
- error messages that state how to recover;
- retrieve documentation in two stages when there are more than about 100 endpoints.
