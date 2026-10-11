# Citation chase: papers that cite our anchor architectures

As of 2026-10-09, for KLE Tech Hackfest 2026, Domain 5A. The raw lists are in `data/citations_*.csv`. The scripts are in `research/scripts/` (see "How to re-run" at the end).

## Evidence boundary

- **Where the lists come from.**
  - Semantic Scholar Graph API, endpoint `/paper/arXiv:<id>/citations`, pulled 2026-10-09.
  - OpenAlex `cites:` filter, run over every OpenAlex record of each anchor. OpenAlex sometimes keeps the arXiv version and the conference version as separate records.
  - A search of arXiv full texts. Semantic Scholar has almost no citation data yet for the four 2026 anchors, so we downloaded the arXiv HTML of 1,699 papers from 2026 and searched each one for the anchors' titles. These papers were the 2026 citers of Mind2Web, Beyond Browsing, AppWorld and τ-bench.
  - The full-text search cannot find a paper that cites a 2026 anchor but none of those four papers. A visual-analytics paper that cites only VACP, for example, would be missed.
- **Verification labels.**
  - **[FT]**: the number was read from the paper's arXiv HTML full text, using an automated reader. We did not recompute it.
  - **[AB]**: the number comes from the abstract only.
  - Every number is the authors' own. Almost every paper below is a 2026 preprint that has not been peer-reviewed.
- **Corrections to `05_Mind2Web_Citing_Work_and_Proposals.md`.**
  - Beyond Browsing appeared at **Findings of ACL 2025** (DOI 10.18653/v1/2025.findings-acl.577), not ACL 2024.
  - The typed-actions paper was first posted under the title "Web Verbs: Typed Abstractions for Reliable Task Composition on the Agentic Web". A web search lists it as an ICML 2026 position paper. We did not check that listing directly.

## 1. Citing papers found, per anchor

| # | Anchor (verified arXiv ID) | Semantic Scholar | OpenAlex (all records) | Found only in full text | Rows in CSV | "Influential" (Semantic Scholar) |
|---|---|---|---|---|---|---|
| 1 | Beyond Browsing: API-Based Web Agents (2410.16464) | 88 | 7 (2 records) | +1 (VOIX) | 91 | 9 |
| 2 | VACP: Visual Analytics Context Protocol (2603.29322) | 1 | 0 | +2 | 3 | 0 |
| 3 | EmbeWebAgent (2602.14865) | 0 | 0 | 0 | 0 | 0 |
| 4 | Internal APIs Are All You Need / Unbrowse (2604.00694) | 0 | 0 | 0 | 0 | 0 |
| 5 | Web Agents Should Use Typed Actions (2602.17245) | 0 | 0 | +1 (Tool Illusion) | 1 | 0 |
| 6 | AppWorld (2407.18901, ACL 2024) | 409 | 14 (2 records) | +15 (text mentions) | 426 | 67 |
| 7 | τ-bench (2406.12045) | 1,407 | 7 | +7 (text mentions) | 1,416 | 174 |

- **Overlap across anchors.** There are 1,724 unique citing papers across all anchors, counted before the full-text additions.
  - 185 cite two or more anchors. Most of them pair AppWorld with τ-bench.
  - Only two cite three anchors: TheAgentCompany and Self-Challenging Agents, which both cite Beyond Browsing, AppWorld and τ-bench. Neither is an architecture we would adopt.
  - **Only one paper cites a 2026 anchor together with another anchor:** *The Tool Illusion* (2604.03465), which cites Beyond Browsing and the typed-actions paper.
- **What the counts mean.** The 2026 anchors have almost no forward citations yet. That is expected six to eight months after posting. Our notes treat the in-app bridge pattern (EmbeWebAgent, VACP, typed actions) as established, but it has **no independent replication** in the literature. The "better solutions" found below therefore come mostly from papers that cite Beyond Browsing, AppWorld or τ-bench.

### Notable citers, per anchor

**1. Beyond Browsing.** The citers split into three groups:

- **Reverse-engineering tools from a site that has no API:**
  - WALT (2510.01524)
  - Doc2Agent (2506.19998)
  - SkillWeaver
- **Interfaces built for agents:**
  - ASIL (2608.26991)
  - VOIX (2511.11287)
  - Agent-Ready Websites (2607.12056)
  - ToolPro (2606.19992)
  - AXIS (2409.17140)
- **Evidence about how much APIs help:**
  - The Tool Illusion (2604.03465)
  - Terminal Agents Suffice (2604.00073)
  - Agent-Callable Feature Coverage, ACFC (2609.35789)
  - MCP vs RAG vs NLWeb vs HTML (2511.23281)
  - Plan-Then-Execute (2605.14290)
  - Agent JIT Compilation (2605.21470)

WebChallenger (2606.10423) is the strongest fallback browser agent that runs on an open model.

**2. VACP.** Three citers, all from visual analytics: bonsai (2604.19247), MIVAIS (2609.04983) and marimo-lens (2609.19839). None of them improves on VACP.
- bonsai uses VACP as its channel to the "application's internal state".
- MIVAIS suggests VACP-driven agents could stand in for pilot participants in user studies.
- marimo-lens adds one idea worth copying: the user points at a rendered result, and that selection is passed to the agent together with the computation that produced it.

**3. EmbeWebAgent and 4. Unbrowse.** We found no citing papers in either API or in the 1,699 full texts. All the speed-up figures for Unbrowse are the authors' own.

**5. Typed actions.** One citer, *The Tool Illusion*, which shares authors with the typed-actions paper according to the Microsoft Research author pages found in a web search. Related papers that make the same argument without citing it:
- Plan-Then-Execute
- Agent JIT, which uses tools with preconditions and postconditions
- ASIL

**6. AppWorld and 7. τ-bench.** These are the large pools. The citers relevant to us are about three things:
- Making stateful tool agents reliable: LedgerAgent, Reason Less Verify More, Solver-Aided Verification, Policy-Adherence guard code, OODA-Tool, Mingbird, RubricRefine.
- Enterprise and analytics agents: Analytic Agent (Beyond Text-to-SQL), Text2Dashboard, Argo-Bench, DAB, DI-Bench, EnterpriseOps-Gym, Agent-Diff, Thinkingbox.
- Evaluation validity: False Success, Lost in Simulation, Benchmarking the Benchmarks, Do Agent Benchmarks Do What They Say.

τ²-bench (578 citations) is τ-bench's own successor, and the version that recent papers now evaluate on.

## 2. Better solutions worth adopting (ranked)

Ranked by how much each would raise our KPIs within 48 hours on local Qwen2.5-14B or DeepSeek-R1-Distill-32B. Faithful numbers, UI-state correctness, multi-step success and near-zero action hallucination count most.

| Rank | Paper (anchors cited) | What it improves over the anchor | Headline numbers (as reported) | Code | Doable in 48 hours with local 14–32B? |
|---|---|---|---|---|---|
| 1 | **LedgerAgent** (2606.20529; AppWorld, τ-bench) [link](https://arxiv.org/abs/2606.20529) | Keeps the facts the agent has observed (IDs, records, constraints) in a typed **ledger**, separate from the prompt. The ledger is rebuilt only from successful *read* calls and rendered into every prompt. Before any write, code predicates over the ledger allow, revise or block the call. This addresses decisions made on stale or misremembered values, which is our faithfulness KPI. | τ²-bench, open models, pass^1 / pass^4. Average gains: Kimi K2.5 +3.4 / +5.6, GLM-5 +4.7 / +7.6, MiniMax-M2.5 +7.3 / +8.3. Example: MiniMax retail 33.6 → 58.1 pass^1. **Telecom got worse** for all three open models (e.g. Kimi 90.8 → 76.5). [FT] | None released | **Yes.** Our ledger holds the page, filters, date range, entity IDs and every number read, each tagged with its evidence ID. Answers may quote only ledger values. No training needed. |
| 2 | **Reason Less, Verify More** (2607.07405; τ-bench) [link](https://arxiv.org/abs/2607.07405) | Deterministic, read-only gates run before each write. The generic one, `must_read_before_write`, blocks a write to any record not read in the current session. | τ²-bench airline, gpt-4o-mini: 29.6% → 42.0% (+12.4 pp, P=0.0012). A disjoint 15-seed replication gave +12.3 pp. gpt-5.2: 61.2 → 71.6 (not replicated). One gate carried most of the gain; another was only 5% precise. [FT] | "Released upon publication" | **Yes.** It is about 30 lines. Apply it to our one write action ("create case") and to `configure_view`, which must only take filter values that were read from `getCapabilities`. |
| 3 | **ASIL** (2608.26991; Beyond Browsing) [link](https://arxiv.org/abs/2608.26991) | Generalises VACP's and EmbeWebAgent's bridge to any software. Observations are typed JSON with six fields: metadata, app state, interactive elements, environment, navigation, data summary. Actions take the form `{action_type, target, params}` and are checked by final-state validators. | 380 tasks: GPT-5.4 scored 81.6 with ASIL vs 6.6 by screenshot-and-click. **Qwen3.5-27B scored 75.8 with no training.** Under five actions per task. Matched only draw.io's own MCP contract (55 vs 55). [FT] | Yes: github.com/sharryXR/ASIL, plus benchmark and models on Hugging Face | **Yes, adopt the schema.** Shape `window.__vacp.getState()` like ASIL's observation, and `execute()` like its action object with a `batch` type. Skip their SFT and RL. |
| 4 | **Agent-Callable Feature Coverage (ACFC)** (2609.35789; Beyond Browsing, AppWorld) [link](https://arxiv.org/abs/2609.35789) | Turns "use APIs" into a measurable **GUI–API parity** audit. Each capability is scored 0–3 on whether an agent can call it (Accessibility), find and understand it (Discoverability) and use it safely (Controllability). | 10 self-hosted apps. API-only agents completed 56/58 covered tasks with Opus 4.8, and 45/58 with **Gemma 4 31B (open)**. They completed **0/19** tasks whose capability was not exposed. Thinner documentation dropped Opus to 50/58 (p=0.031). [FT] | Replication package on Zenodo (doi 10.5281/zenodo.21098126) | **Yes, as a spreadsheet.** List every page, filter, sort and chart in our catalogue and score it. Any widget scoring 0 is one the agent can only hallucinate about. |
| 5 | **Terminal Agents Suffice** (2604.00073; Beyond Browsing, AppWorld) [link](https://arxiv.org/abs/2604.00073) | Includes **ERPNext**. Shows that *off-the-shelf* tool servers lose badly because they don't cover enough. It also states that **reading dashboard charts through APIs is awkward**. | 729 tasks (ServiceNow, GitLab, ERPNext). Overall: MCP tool-use 32.9–39.2%, web 68.9–79.9%, terminal 72.7–78.7%. A terminal-plus-Playwright hybrid scored 81.4% (Opus 4.6). Terminal was 2–7× cheaper than web on ServiceNow. [FT] | "Upon acceptance" | Use the lesson, not the system. Our API pattern only wins if our named operations cover the tasks (see rank 4). Charts go through the VACP bridge. |
| 6 | **Plan-Then-Execute** (2605.14290) and **Agent JIT Compilation** (2605.21470); both cite Beyond Browsing [PTE](https://arxiv.org/abs/2605.14290) · [JIT](https://arxiv.org/abs/2605.21470) | Beyond Browsing is still a ReAct loop: page and data content flow back into each next-action decision. PTE commits to a program over typed tools *before* seeing untrusted data. JIT validates candidate plans against pre- and postconditions and runs the cheapest valid one. | PTE (manual analysis, no agent run): 699/860 WebArena tasks (81.28%) can be solved with a purely programmatic plan, given complete APIs. JIT: about 10.4× speed-up and +28 pp accuracy over Browser-Use on 37 tasks in 5 apps. [FT] | PTE: none. JIT: no URL found. | **Yes for analysis questions.** The 32B model emits a JSON plan (a DAG of named operations), we validate it against the catalogue, then execute it deterministically. It also cuts the number of LLM calls. |
| 7 | **Analytic Agent: Beyond Text-to-SQL** (2605.21027; τ-bench) [link](https://arxiv.org/abs/2605.21027) | Our domain exactly: natural-language questions answered through **governed analytics APIs**, with no raw SQL. Four endpoints: `aggregate_metrics`, `leaderboard`, `timeseries`, `records`. Dates are resolved **deterministically**, not by the LLM. Chart type is chosen by rules. Permissions are checked per target, and there is at most one clarifying question. | 90 expert use cases, end-to-end accuracy: Gemini-2.5-Pro 77.22%, Flash 71.67%, Flash-Lite 16.12%. **No baseline, Gemini models only.** [FT] | Not released | **Yes.** Copy the four-endpoint taxonomy and the deterministic date resolver for our ERP data. |
| 8 | **Mingbird** (2610.02001; AppWorld, τ-bench) [link](https://arxiv.org/abs/2610.02001) | Harness fixes for small open models. A **finish gate** re-reads the task before accepting "done". Loop detection works on call signatures. Tool prefill is kept flat. Malformed tool calls are rescued. | τ²-bench with the same qwen3.5:4b in every arm: 0.856 vs 0.791 (native agent) vs 0.737 (opencode). Removing the finish gate cost 0.098. These are self-built benchmarks with single runs. [FT] | Yes: github.com/Mingbird/Mingbird-agent (Apache-2.0) | **Yes.** Add the finish gate and loop detection to our controller. They target exactly the failures we expect from Qwen-14B. |
| 9 | **False Success** (2606.09863; AppWorld, τ-bench) [link](https://arxiv.org/abs/2606.09863) | Shows that agents claim completion when the state says otherwise, and that LLM judges cannot detect it. | False success is 45–48% of failures in single-control τ²-bench domains and 75.8% in self-assessing AppWorld traces. LLM judges reach AUROC ≤ 0.65. TF-IDF detectors reach 0.83 and 0.95. [AB] | n/a | **Yes, as a rule.** Never accept the model's "done". Re-read `getState()` and compare it with the requested UI state. That is our UI-state KPI check. |
| 10 | **VOIX** (2511.11287; Beyond Browsing) [link](https://arxiv.org/abs/2511.11287) | The closest prior art to `window.__vacp`. Pages declare `<tool>` and `<context>` HTML elements inside React or Vue components, so tools appear only when they are relevant. Results come back through a `return` event. It was built and tested **in a 3-day hackathon** with Qwen3-235B. | Per-task latency was 0.9–14.4 s, against 4.4–1,271 s for Perplexity Comet and BrowserGym. These were single runs on different apps. SUS 72.3 with 16 developers. [FT] | No URL in the paper | **Yes.** Cite it as prior art next to VACP and EmbeWebAgent. Copy the component-scoped declarations. |
| 11 | **OODA-Tool** (2608.24368; τ-bench) [link](https://arxiv.org/abs/2608.24368) | Separates tracking the task state from producing the next action. Observe → Orient (one of 5 modes, including "need clarification") → Decide (structure) → Act (bind values from state), with checks between stages. | ToolDial: Qwen3-14B 94.90 vs 90.42 (Direct) vs 84.77 (ReAct). Qwen3-8B 89.52 vs 83.58. **All arms were LoRA-fine-tuned.** At 1.7B, latency was 2.36× Direct. [FT] | None | **Partly.** Use the 5-mode Orient step as a prompt-level router. The reported gains needed fine-tuning. |
| 12 | **WebChallenger** (2606.10423; Beyond Browsing) [link](https://arxiv.org/abs/2606.10423) | The best fallback browser agent on **open weights**. PageMem turns the DOM into sections with summaries. A site map is explored once, and compound actions replace multi-step clicks. | GLM-4-32B controller: WebArena 56.3%, WorkArena-L1 70.9%. In ablation, removing the observation pipeline cost 17.6 points. [FT] | Yes: github.com/jayoohwang1/webchallenger | Only for the Playwright fallback, and only if time allows. |

**Also worth knowing, but not adopting in 48 hours:**
- **WALT** (2510.01524). It learns tools from sites that have no API, scoring 50.1% on WebArena against 38.9% for Beyond Browsing's hybrid agent [FT]. We own our app's API, so we don't need it.
- **Thinkingbox** (2608.19741). A benchmark of 507 policy-conditioned business workflows. Opus 5 drops from 66.5% pass@1 to 47.5% pass^20 [AB]. Code is at github.com/microsoft/thinkingbox. **Report pass^k, not only pass@1.**
- **Argo-Bench** (2610.02122). 210 data tasks on an ERP warehouse modelled on Oracle E-Business Suite, with 235 tables [AB].
- **DAB** (2603.20576). The best agent reaches 57% pass@1 [AB]; code is at github.com/ucbepic/DataAgentBench.
- **Text2Dashboard** (2610.06914). The model proposes and deterministic hooks execute, with read-only SQL. 6/8 strict on metadata and SQL tasks; the authors say this is small and not production-ready [AB].
- **Is Bash All You Need?** (2609.11999). With frontier models, bash beats typed tools by 21.8–24.5 pp on TheAgentCompany [AB]. Where policy requires a fixed tool catalogue, it recommends **programmatic tool calling**: programs restricted to typed tools. That is our case.

### Does any citing paper clearly supersede an anchor?

- **τ-bench → τ²-bench.** Yes. The same group's successor adds dual control, and the recent reliability papers above all evaluate on it. Use τ²-bench, or Thinkingbox for business workflows, as the external reference.
- **Beyond Browsing → WALT?** Not clearly. WALT beats Beyond Browsing's published 38.9%, but with a stronger backbone. *The Tool Illusion* compared them with the same backbone (GPT-5). On WebArena it found Hybrid-Agent at 49.9% and WALT at 50.9% with tools [FT]. Hybrid-Agent was the only framework that gained on every backbone (+12.4 to +19.6 pp).
- **VACP, EmbeWebAgent, typed actions → ASIL?** ASIL is the strongest *generalisation* of the same idea. It brings a released benchmark, released code and open-model results, but it does not cite these papers or do analytics-specific chart semantics. Treat it as the evidence base for our bridge, not as a replacement for VACP.
- **AppWorld, Unbrowse:** nothing found that supersedes them.

## 3. What the citing literature says about the anchors' weaknesses

**Beyond Browsing (API-first and hybrid)**
- **Too many tools costs tokens and steps.** Hybrid-Agent exposes about 437 tools per site. It has the highest token cost and is the only framework to become *less* step-efficient (*Tool Illusion*) [FT].
- **It assumes the site has documented APIs.** WALT calls them "often undocumented or proprietary" [FT].
- **API coverage decides the outcome.**
  - Off-the-shelf MCP servers reached only 32.9–39.2% across ServiceNow, GitLab and ERPNext, against about 70–80% for web or terminal agents (*Terminal Agents Suffice*) [FT].
  - Agents completed 0/19 tasks whose capability had no exposed interface (ACFC) [FT].
  - Postmill's 16 REST APIs cover only 33% of its tasks (PTE) [FT].
- **ReAct over API results is still open to prompt injection,** because untrusted content can steer the next action (PTE) [FT].

**VACP, EmbeWebAgent, typed actions (declared in-app interfaces)**
- **No independent replication.** The three VACP citers only reuse it. EmbeWebAgent and Unbrowse have no citers.
- **Declarations drift.** Declared tools fall out of sync with the GUI as the UI changes. There is also an abstraction dilemma: low-level tools are easy to maintain but slow, while high-level tools are fast but brittle. Developers defaulted to plain CRUD tools (VOIX) [FT].
- **The shape of the schema matters as much as having one.** Rewriting a schema into functionally equivalent variants moved success "from complete failure to 97%" (*Action-Space Shaping*, 2609.34971) [AB].
- **Schema-valid output is not the same as a correct action.** Even the strongest model managed only about 80% semantic success at 100% schema validity (*When JSON Is Not Enough*, 2607.18261) [AB]. Typed verbs need semantic validation behind them.
- **Typed tools do not always win.** With frontier models, bash beat typed tools on enterprise tasks (*Is Bash All You Need?*) [AB]. Tool gains are inconsistent and depend on who built the tools (*Tool Illusion*) [FT].
- **The typed-actions paper is a position paper.** Its case studies have no benchmark numbers.

**AppWorld and τ-bench (as evaluation)**
- **Simulated users are unreliable.** Agent success varies by up to 9 pp depending on which LLM plays the user, with systematic miscalibration (*Lost in Simulation*, 2601.17087) [AB].
- **The evaluators have defects.** An executable-contract audit found τ²-bench evaluator defects. In one case the grader rewards a refuel of a suspended line (2609.37315) [AB]. Repeated runs of the same tool-calling setup spanned 18.9 pp on LiveMCPBench (2607.02577) [AB].
- **Agents claim success that the state doesn't show.** False success is 45–48% of τ²-bench failures and 75.8% of failures in self-assessing AppWorld traces. LLM judges cannot detect it (2606.09863) [AB].
- **pass@1 overstates reliability** (Thinkingbox) [AB].

## 4. What this changes in our plan

1. **Add a ledger and pre-write gates** (LedgerAgent, Reason Less Verify More). Keep a typed ledger of observed state with an evidence ID for every number. Answers may cite only ledger values. Add deterministic gates, including `must_read_before_write` and "filter value ∈ getCapabilities()". Run an ablation with and without gates.
2. **Shape `window.__vacp` like ASIL.** `getState()` returns ASIL's six-field JSON. `execute()` takes `{action_type, target, params}` and supports `batch`. A final-state validator re-reads `getState()` after each `execute`. Cite VOIX and ASIL as prior art next to VACP and EmbeWebAgent.
3. **Run a GUI–API parity audit** (ACFC) over our catalogue before the demo. Report the coverage score as a KPI.
4. **Plan, then execute, for analysis questions** (PTE and JIT). The model emits one JSON plan over the named operations (Analytic Agent's four-endpoint taxonomy fits), and we validate and run it deterministically. Dates are resolved by code, not by the LLM.
5. **Harness fixes for local models** (Mingbird): a finish gate, signature-level loop detection and a flat tool prefill.
6. **Evaluation.** Report **pass^k**, not just pass@1. Never use an LLM judge as the only completion check; compare the final state instead. Use τ²-bench, not τ-bench, as the external reference.

## How to re-run

From the repository root:

```
python3 research/scripts/fetch_citations.py     # Semantic Scholar + OpenAlex, writes data/citations_<anchor>.csv, citations_combined.csv, citations_summary.json
python3 research/scripts/grep_references.py     # arXiv full-text search for anchor titles; adds full-text-only citers to the CSVs
python3 research/scripts/screen_citations.py    # keyword relevance score, writes data/citations_screened.csv
```

- API responses are cached in `data/citations_cache/`. Delete that folder for a fresh pull.
- The public Semantic Scholar API returned HTTP 429 repeatedly, and the script retries with backoff. Set `S2_API_KEY` to go faster.
- `citations_screened.csv` is a triage aid only. The shortlist above was chosen by reading the abstracts and, for 12 papers, the full text: LedgerAgent, Reason Less Verify More, ASIL, ACFC, Terminal Agents, PTE, Agent JIT, Analytic Agent, Mingbird, VOIX, OODA-Tool, WebChallenger. *Tool Illusion* and WALT were also read in full.
