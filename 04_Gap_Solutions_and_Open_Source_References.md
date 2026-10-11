# Gap Solutions and Open-Source References

As of 2026-10-05. Companion to `03_Reference_Stack_Gaps_and_KPI_Impact.md`; gap IDs (G1.1 to G9.3) are the ones defined there.

Report 03 assessed tools that **operate** a UI. This report gives each gap a hackathon-sized answer. The appendices keep the wider survey: approaches that other fields already use for similar problems, and the open-source projects that implement them.

**Evidence boundary.** Nothing here has been built or measured by us. For every project in the reference tables we read the GitHub page on 2026-10-05 for licence, archive status and last commit, and the licence file itself where GitHub showed no standard licence. Feature notes marked "README" were read today; other feature notes should be confirmed before we depend on them. Papers, standards and proprietary products named in the tables are method references and were not checked today.

## Summary

For the hackathon we build a small version: seven pieces of our own code and four small libraries. It needs no vector database, semantic-layer engine, browser automation or tracing platform. Every one of the 28 gaps still gets an answer:

- **6 gaps are removed by four design choices**, so there is nothing to build for them.
- **16 gaps are covered by the seven pieces.**
- **6 gaps get a cheap version** that is enough for a demo.

The wider survey of approaches and the checked open-source references are kept in the appendices, for the deck's alternatives slide and for work after the hackathon.

This cut assumes we build our own small web app. If the organisers supply a platform, design choices 1 and 2 need rechecking.

## Hackathon cut

### Four design choices that remove gaps

| # | Choice | Gaps removed | Why it works |
|---|---|---|---|
| 1 | One catalogue file defines the pages, widgets, filters and measures. The app renders from it and the agent reads it. | G1.4 | The app and the agent's knowledge can't drift apart. It also makes "exported metadata" real. |
| 2 | View state lives in the URL: page, filters, sort and selection are query parameters. | G5.1 | Navigating and setting filters is one URL change, so Playwright isn't needed. |
| 3 | The agent never writes SQL. It picks a widget or named measure and passes filters. Each one has a single parameterised query, shared with the screen. | G4.1, G4.2, G4.3 | No wrong joins, no numbers that differ from the screen and no injected SQL. Use a read-only database login as well. |
| 4 | The whole catalogue goes in the prompt. Four pages and about twenty widgets fit easily. | G2.1 | There is no retrieval step to confuse similar components. |

### What we build

| # | Piece | Gaps covered | Made of |
|---|---|---|---|
| 1 | **Widget contracts** in the catalogue: grain, unit, allowed filters and values, and which filter requires which. Every tool call is validated against them. Add a few SQL assertions that the riskiest descriptions are true (backorder direction, carton conversion). | G1.1, G1.2, G1.3, G3.2 | Pydantic models and one validator |
| 2 | **Context from the app on every turn:** current page, filters and selection, kept with the conversation. | G2.2, G3.3 | A dictionary in the conversation state |
| 3 | **`configure_view`** that returns the state the app actually applied. Compare it with what was asked. On a mismatch, retry once, then go back to the previous URL and say so. | G5.2, G5.3 | One tool |
| 4 | **`resolve_entity`** that turns names into IDs from the database. Several matches means asking the user with options. "No matching view" and a short list of unsupported asks are valid outcomes. | G2.3, G3.4 | One tool, RapidFuzz |
| 5 | **`read_widget` and `compare_periods`.** The comparison takes one filter set and returns the top contributors from a GROUP BY. The answer says "contributors", and says "cause" only when a linking record is shown. | G6.1, G6.2 | Two tools |
| 6 | **Evidence IDs** on every tool result. Answers are labelled observed, calculated or inferred, and a check blocks any number that isn't in a tool result. | G6.3, G9.1 | A small checker and three badges |
| 7 | **A task file and a runner** that checks page, final state and answer values, plus a log of every tool call. KPIs are computed from the log. Start from the existing 12-request manifest and grow it to about 25. | G8.1, G8.2 | A JSON file and a plain script |

### Where a cheap version is enough

| Gap | Cheap version | What we leave out |
|---|---|---|
| G3.1 Planning | A plain tool-calling loop with a step limit. Branches follow from what the tools return. | A separate planner |
| G5.4 Confirmation | Two tiers: reads and view changes run, and creating a case asks first. | A policy engine |
| G7.1 Scenarios | Three or four seeded scenarios from report 02 §24.1, chosen as pairs that differ in one fact. | The remaining branches |
| G7.2 Utterances | Phrasings from a few people outside the team, plus LLM paraphrases. Report each source separately. | Simulated users |
| G9.2 Preview and undo | Show each action as it runs. Undo is the previous URL. | Editing a plan before it runs |
| G9.3 Latency | One URL per state change, streamed answers, and measured latency in the results. | Parallel calls, caching and model routing |

### What we skip, and how to cover it

The brief's reference stack names a vector index, a knowledge graph, text-to-query and Playwright. The cut doesn't need them at four pages, but judges may look for them. Two optional extras cover that if time allows:

- **Retrieval stress test:** pad the catalogue to a few hundred entries and measure precision, recall and MRR with keyword plus embedding search (bm25s, FlagEmbedding). Report 01 §11 already frames this as a separately labelled test.
- **Guarded free SQL:** one fallback tool for questions no widget answers. It allows a single SELECT over approved views (SQLGlot check, read-only login, row cap) and labels its answers "not on screen".

Everything else in Appendix A goes on the deck as future work: semantic-layer engines, planners, durable workflows, policy engines, causal inference, generative-UI frameworks and tracing platforms.

### Stack

| Need | Pick | Licence |
|---|---|---|
| Agent loop, conversation state, pausing for a question | LangGraph | MIT |
| Tool-argument validation | Pydantic | MIT |
| Name matching | RapidFuzz | MIT |
| Relative dates against the scenario clock | dateparser | BSD-3-Clause |
| Chat panel (optional, React only) | CopilotKit | MIT |
| Optional extras | bm25s, FlagEmbedding, SQLGlot | MIT |

The rest is already in hand or ours to choose: the restored SQL Server database, a hosted model with tool calling, and whichever web framework the team knows best.

### Build order

Each step leaves a working demo, so we can stop after any of them.

1. Catalogue file, app pages rendered from it, and state in the URL. Write the first tasks into the task file.
2. `configure_view` and `read_widget` with validation and read-back. "Show unpicked orders for May" works by chat.
3. Context and `resolve_entity`. "Show the supplier for this item" works as a follow-up.
4. `compare_periods`, evidence IDs and labels. The period comparison from report 02 §26.2 works.
5. Runner and log, which give KPI numbers for the final presentation.
6. More scenarios, then the optional extras.

### Decisions that would change this

- **Platform:** if the organisers supply one, or we pick a low-code platform from Appendix C, check that it can keep view state in the URL and expose its page definitions. If it can't, Playwright comes back in.
- **Build time and team size:** these decide how far down the build order we get.
- **Model hosting:** the cut assumes a hosted model with tool calling. A local model needs constrained generation (Outlines) and a different latency plan.
- **Database:** staying on SQL Server is fine for the cut. It only matters later, because it narrows the semantic-layer options to Cube or an Ibis-based layer.
- **Licences:** everything in the stack table is MIT or BSD. Copyleft only matters if we pick ToolJet, Budibase or ERPNext as the platform.

## Appendix A. Full survey: solutions by layer

This is the wider survey behind the cut. Six borrowed patterns cover 21 of the 28 gaps:

| # | Pattern | Borrowed from | Gaps it addresses |
|---|---|---|---|
| 1 | **Semantic layer:** measures, grain and units defined once and requested by name | Business intelligence | G1.1, G4.1, G4.2, G6.2 |
| 2 | **Typed contracts** checked against the catalogue before any call runs | Compilers, task-oriented dialogue | G1.3, G2.3, G3.2, G5.4 |
| 3 | **Apply, read back, compare, restore** for every UI change | Infrastructure as code, distributed systems | G5.2, G5.3, G9.2 |
| 4 | **One shared investigation context** that every turn and tool reads and writes | Dialogue state tracking | G2.2, G3.3, G3.4 |
| 5 | **Evidence ledger:** answers refer to recorded results and never restate numbers freely | Data lineage, intelligence analysis | G6.1, G6.3, G9.1 |
| 6 | **Seeded scenarios scored on final state**, with KPIs computed from traces | Agent benchmarks, software testing | G7.1, G7.2, G8.1, G8.2 |

The other seven gaps (G1.2, G1.4, G2.1, G3.1, G4.3, G5.1, G9.3) have individual fixes in the tables below.

### Metadata (G1)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G1.1 Shape, not meaning | BI semantic layers (LookML, MetricFlow, Cube, Malloy) | Declare each measure once with its grain, unit, formula and allowed dimensions. The agent asks for a named measure, never a raw column. In the prototype this is the widget contract from report 02 §27.1, written as YAML or Pydantic. | Cube, MetricFlow, Malloy, Boring Semantic Layer; Apache Ossie as a neutral format |
| G1.2 Metadata can be wrong | Data engineering (data contracts, expectation tests); text-to-SQL value profiling (BIRD "evidence", CHESS) | Treat each description as a claim with an executable check. The backorder direction becomes a SQL assertion run on every build. A description that fails is marked unverified and kept out of the index. Attach profiled sample values to field descriptions. | Great Expectations, Pandera, CHESS |
| G1.3 Static graph | Model-based GUI testing (state machines); REST API fuzzing (RESTler infers which call must come before which); JSON Schema conditional rules | Add typed edges to the graph: `requires` (filter B needs filter A), `excludes`, and `carries_to` (a selection passes to another page). Valid combinations become a schema check. The order for setting state is a topological sort of `requires`. | XState, GraphWalker, RESTler, NetworkX, Pydantic |
| G1.4 Drift | Search indexing (re-index by content hash); API contract testing; synthetic monitoring | Hash every catalogue entry and re-index only what changed. Stamp the catalogue version on every trace. Run a scheduled Playwright check that opens every route in the deep-link map and fails on a missing page or widget. | LangChain indexing API, LlamaIndex ingestion pipeline, Playwright |

### Retrieval (G2)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G2.1 Near-identical components | Tool retrieval over thousands of APIs (ToolLLM, AnyTool); web search (hybrid search plus reranking); contextual retrieval | Route down the navigation tree (module, then page, then widget) and avoid one flat search. Index each component with its path and what sets it apart from its siblings. Combine keyword and embedding search, then rerank. Put near-duplicates in the test set as hard negatives. | FlagEmbedding (BGE embeddings and rerankers), bm25s, ToolBench |
| G2.2 Words only | Conversational search (query rewriting, TREC CAsT); copilot frameworks where the app publishes its state | The front end publishes the current page, filters and selection every turn. Resolve "its" and "this order" against that state first, rewrite the request so it stands alone, then retrieve. | CopilotKit, AG-UI, LlamaIndex condense-question engine |
| G2.3 No "nothing fits" answer | Out-of-scope intent detection (CLINC150); Corrective RAG (grades retrieved results before using them) | Make "no matching view" a normal outcome with its own tool result. Set the score threshold from labelled unsupported requests. List known unsupported asks (delivery prediction, stock allocation) in the catalogue so they match something explicit. | semantic-router, CLINC OOS dataset, CRAG (paper) |

### Planning (G3)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G3.1 Greedy, single-intent | Plan-then-execute agents (ReWOO, LLMCompiler); operations runbooks | Plan first as a small graph of steps, run it, and re-plan when a result contradicts the plan. Encode the report 02 §24.1 branches (hold, reservation, revised promise, no incoming supply) as conditional edges and not as one fixed tool sequence. | LangGraph, LLMCompiler |
| G3.2 Slots not checked | Compilers (type-check before running); schema-guided dialogue (SGD); text-to-SQL value linking | Tool arguments are typed models whose allowed values come from the catalogue. An ID must come from a resolver tool or an earlier result, and the controller rejects any ID with no source. Dates are parsed by a library against the frozen scenario clock, not by the model. | Pydantic, Instructor, Outlines, RapidFuzz, dateparser, Guardrails AI |
| G3.3 No carry-over | Dialogue state tracking (MultiWOZ, SGD); durable agent state | One investigation context holds the scenario, page, filters, selection, comparison scope and evidence so far. It is saved per conversation, and every tool reads from it and writes to it. | LangGraph checkpointers |
| G3.4 Ambiguity guessed | Clarifying questions in conversational search (ClariQ); ambiguous text-to-SQL (AMBROSIA); Rasa CALM (the model understands, code enforces the flow) | Ask only when it matters: the top two destinations score close together, a resolver returns several entities, or a required slot is empty. For low-risk reads, act and state the assumption. Offer the candidates as buttons. | LangGraph `interrupt`; Rasa as a pattern only |

### Text-to-query (G4)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G4.1 Valid SQL, wrong meaning | BI handling of fan-out joins (Looker symmetric aggregates, Malloy); verified-query libraries (Snowflake Cortex Analyst, Vanna) | The model picks a measure, dimensions and filters, and the semantic layer writes the SQL, so joins across grains can't double-count. Seed a verified-query library with the three reference workflows. Reject free SQL that joins tables of different grain. Carry units as types so cartons and units can't be added. | Malloy, Cube, MetricFlow, SQLGlot, pint |
| G4.2 Query numbers differ from the screen | Headless BI (one definition serves the dashboard and the API); financial reconciliation | `read_widget` runs the same query the widget renders from and returns its hash. An ad-hoc figure is labelled "not on screen" and reconciled against a widget total where one exists. With no API, read the widget's own network response. | Cube, Playwright network interception |
| G4.3 Weak safety | Database security (least privilege, row-level security); query firewalls | A read-only login with SELECT on approved views only. Parse every query and allow one SELECT over approved objects with an enforced row cap. Set a driver timeout. Scope tenant or scenario with SQL Server row-level security. | SQLGlot (T-SQL dialect); OPA at scale |

### Orchestration (G5)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G5.1 Fragile browser fallback | Test automation (role and test-ID locators, self-healing locators); dashboards that keep state in the URL; pages that expose their own tools (WebMCP) | Prefer no browser: set state through a deep link or state API in one call. Where a browser is needed, target accessibility roles and stable test IDs, not CSS paths. | Playwright MCP, Stagehand, browser-use, WebMCP |
| G5.2 No check after acting | Infrastructure as code (Terraform plan and apply, Kubernetes reconcile loops); test assertions | `configure_view` returns the applied state. The controller compares requested with applied, and reads back through a second channel (URL or DOM). Any difference is reported as a failure. | Playwright assertions, DeepDiff |
| G5.3 No recovery plan | Distributed systems (the saga pattern: every step has an undo); durable execution; database savepoints | Save the UI state as a deep link before a plan runs. Classify errors: retry a transient one, re-plan on a bad argument, tell the user when the request is unsupported. On failure, restore the saved state. | LangGraph checkpointers, tenacity, Temporal |
| G5.4 All-or-nothing confirmation | MCP tool annotations (read-only, destructive, idempotent); coding-agent permission modes; maker-checker in finance | Give every tool a risk tier. Reads run freely. Reversible UI changes run with an undo. Persistent writes such as creating a case need confirmation. Business writes stay out of scope. | MCP specification, LangGraph `interrupt`, OPA |

### Analysis (G6)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G6.1 False cause and effect | AIOps and BI root-cause tools (Adtributor, Tableau Explain Data, Power BI decomposition tree); causal inference (DoWhy's refutation step) | Compute each dimension's contribution to the change in code. "Item X accounts for a given share of the increase" is arithmetic, not a cause. Allow the word "cause" only when a linking record exists, such as a hold reason or a revised commitment. For each hypothesis, run a query that could disprove it. | DoWhy, PyRCA, statsmodels; InsightBench for evaluation |
| G6.2 Inconsistent comparisons | Semantic-layer time comparisons (MetricFlow offset windows, Cube compare-date-range) | One `compare_periods(measure, period_a, period_b, filters)` tool. It takes a single filter set, so the two sides can't differ in population or unit. It flags partial periods and periods of unequal length. | Cube, MetricFlow, pint |
| G6.3 Faithfulness not built in | Data lineage (W3C PROV, OpenLineage); attributed question answering; program-aided reasoning | Every tool result goes into an evidence ledger with an ID, query hash and source view. The model writes the answer with references to ledger entries and the renderer fills in the numbers. A final check blocks any number that isn't in the ledger. | OpenLineage (event model), Ragas, DeepEval |

### Data (G7)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G7.1 Synthetic data lacks edge cases | Software testing (metamorphic tests, fault injection); root-cause benchmarks with planted causes (RCAEval) | Author contrast pairs: two scenarios that differ in one fact and have different correct answers. Check the report 02 §24.2 invariants automatically on every seed. | Faker, Pandera, Great Expectations |
| G7.2 Utterances written by the team | NLP behavioural testing (CheckList); simulated users (tau-bench); Wizard-of-Oz collection | Hold out utterances written by people outside the team. Add perturbations (paraphrase, typos, reordered slots) and simulated users with different personas. Report accuracy separately for each source. | CheckList, tau-bench, Ragas test-set generation, promptfoo |

### Evaluation (G8)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G8.1 Public benchmarks are only stand-ins | Web-agent and tool-agent benchmarks (WebArena, WorkArena, tau-bench, AppWorld) | Write our own task file: start state, request, expected destination, expected final UI state, expected values with tolerance, and evidence IDs. A task passes only when page, state and answer are all right, checked by code against the final state. Run each task several times and report consistency. | Inspect AI or promptfoo as the harness; WebArena, WorkArena and tau-bench as designs |
| G8.2 KPIs undefined, no action trace | Observability (OpenTelemetry spans); LLM tracing | One span per tool call, carrying requested arguments, applied arguments and catalogue version. Define action hallucination as calls that fail catalogue validation or use an ID with no source, divided by all calls. Each KPI then becomes a query over traces. | Langfuse, OpenLLMetry, OpenTelemetry GenAI conventions |

### UX (G9)

| Gap | Borrowed from | What we would do | References |
|---|---|---|---|
| G9.1 Fact and inference not labelled | Intelligence analysis standards (ICD 203 separates reported information from judgement); evidence grading in medicine (GRADE) | Three typed answer blocks: observed (a record), calculated (formula and inputs) and inferred (hypothesis, supporting evidence, what would confirm it). Each renders differently and links to its view. | CopilotKit, assistant-ui, A2UI, Vega-Lite |
| G9.2 Explanations only after the fact | Terraform plan and apply; coding-agent plan mode; undo stacks | Before multi-step or confirm-tier actions, show the plan and the state change (filters before and after). Let the user edit or skip a step. Keep an undo stack of saved states. | LangGraph (`interrupt`, state edit, time travel), CopilotKit human-in-the-loop |
| G9.3 Latency stacks up | Compilers (independent steps run in parallel, as in LLMCompiler); caching; model routing | Run independent reads in parallel. Set all UI state in one deep link. Use a small model or embedding router for intent and the large model only for analysis. Cache the catalogue prompt and repeated queries. Navigate first and stream numbers after. | LLMCompiler, semantic-router, LiteLLM, GPTCache, Cube pre-aggregations |

## Appendix B. Open-source references checked

Licence and last commit as read on 2026-10-05.

### Meaning and data quality

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [Cube](https://github.com/cube-js/cube) | Apache-2.0; some packages MIT | 2026-10-04 | Semantic layer with an API. An MS SQL driver package is in the repo. |
| [MetricFlow](https://github.com/dbt-labs/metricflow) | Apache-2.0 from v0.209 (earlier versions AGPL, then BSL) | 2026-09-29 | README doesn't mention SQL Server. Confirm engine support first. |
| [Malloy](https://github.com/malloydata/malloy) | MIT | 2026-10-02 | README engine list has no SQL Server (BigQuery, Snowflake, DuckDB, PostgreSQL, MySQL, Trino, Presto, Databricks). |
| [Boring Semantic Layer](https://github.com/boringdata/boring-semantic-layer) | MIT | 2026-08-24 | Small Python layer on Ibis. [Ibis](https://github.com/ibis-project/ibis) (Apache-2.0) has an MSSQL backend in its source tree. |
| [Apache Ossie](https://github.com/apache/ossie) | Apache-2.0 | 2026-10-05 | Formerly Open Semantic Interchange; incubating. A YAML/JSON spec for semantic models, not an engine. |
| [SQLGlot](https://github.com/tobymao/sqlglot) | MIT | 2026-10-05 | SQL parser. A T-SQL dialect is in the repo. |
| [Great Expectations](https://github.com/fivetran/great_expectations) | Apache-2.0 | 2026-10-02 | Repo now sits under the Fivetran organisation. |
| [Pandera](https://github.com/unionai-oss/pandera) | MIT | 2026-10-05 | Lighter schema checks for dataframes. |
| [pint](https://github.com/hgrecco/pint) | BSD-style | 2026-10-04 | Units as types. |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | Apache-2.0 | 2026-10-02 | Lineage standard. Useful as a model for ledger entries. |
| [CHESS](https://github.com/ShayanTalaei/CHESS) | Apache-2.0 | 2024-11-13 | Research code for text-to-SQL with value retrieval. |

### Retrieval

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | MIT | 2026-08-24 | BGE embedding and reranker models. |
| [bm25s](https://github.com/xhluca/bm25s) | MIT | 2026-10-02 | Keyword search in Python. |
| [semantic-router](https://github.com/aurelio-labs/semantic-router) | MIT | 2026-09-29 | Embedding-based routing. |
| [ToolBench](https://github.com/OpenBMB/ToolBench) | Apache-2.0 | 2025-05-21 | Research code behind ToolLLM. |
| [CLINC OOS](https://github.com/clinc/oos-eval) | CC-BY-3.0 | 2021-06-01 | Dataset with out-of-scope intents. |
| [CRAG](https://github.com/HuskyInSalt/CRAG) | No licence file found | 2024-10-08 | Use the paper, not the code. |

### Planning, validation and state

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | 2026-10-03 | Graph-based agent runtime from the makers of LangChain, which the brief names. |
| [LangChain](https://github.com/langchain-ai/langchain), [LlamaIndex](https://github.com/run-llama/llama_index) | MIT | 2026-10-04, 2026-10-01 | Both named in the brief. |
| [LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler) | MIT | 2024-07-10 | Research code. Take the pattern. |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | 2026-10-02 | Typed models and validators. |
| [Instructor](https://github.com/567-labs/instructor) | MIT | 2026-09-11 | Structured output from hosted models. |
| [Outlines](https://github.com/dottxt-ai/outlines) | Apache-2.0 | 2026-08-24 | Constrained generation, mainly for local models. |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | Apache-2.0 | 2026-08-26 | Output validators. |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT | 2026-09-12 | Fuzzy matching for entity names. |
| [dateparser](https://github.com/scrapinghub/dateparser) | BSD-3-Clause | 2026-10-05 | Relative dates against a fixed base date. |
| [XState](https://github.com/statelyai/xstate) | MIT | 2026-10-04 | State machines with guards (JavaScript). |
| [GraphWalker](https://github.com/GraphWalker/graphwalker-project) | MIT | 2026-05-24 | Model-based testing. |
| [RESTler](https://github.com/microsoft/restler-fuzzer) | MIT | 2026-02-13 | Infers dependencies between API calls. |
| [NetworkX](https://github.com/networkx/networkx) | BSD-3-Clause | 2026-10-02 | In-memory graph; enough for a small catalogue. |
| [Rasa Open Source](https://github.com/RasaHQ/rasa) | Apache-2.0 | 2025-12-18 | README says maintenance mode; CALM lives in Rasa's newer product. Pattern only. |
| [SGD dataset](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) | CC-BY-SA-4.0 | Archived 2026-04-19 | Schema-guided dialogue data. |

### Orchestration

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [Playwright](https://github.com/microsoft/playwright) | Apache-2.0 | 2026-10-05 | Named in the brief. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Apache-2.0 | 2026-09-28 | README: works from accessibility snapshots, with no vision model. |
| [Stagehand](https://github.com/browserbase/stagehand) | MIT | 2026-10-04 | README: `act`, `observe` and `extract`; `act` self-heals when a page changes. |
| [browser-use](https://github.com/browser-use/browser-use) | MIT | 2026-10-03 | LLM-driven browser agent. |
| [WebMCP](https://github.com/webmachinelearning/webmcp) | W3C Software and Document Licence | 2026-10-02 | Proposal for pages to expose tools to agents. Its status page lists origin trials in Chrome 149 and Edge 150. |
| [DeepDiff](https://github.com/qlustered/deepdiff) | MIT | 2026-07-29 | Compares requested and applied state. |
| [tenacity](https://github.com/jd/tenacity) | Apache-2.0 | 2026-10-01 | Retry policies. |
| [Temporal](https://github.com/temporalio/temporal) | MIT | 2026-10-04 | Durable workflows. Scale-up only. |
| [OPA](https://github.com/open-policy-agent/opa) | Apache-2.0 | 2026-10-05 | Policy as code. Scale-up only. |
| [MCP specification](https://github.com/modelcontextprotocol/modelcontextprotocol) | Moving from MIT to Apache-2.0 | 2026-10-03 | Source of the tool annotation idea. |

### Analysis

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [DoWhy](https://github.com/py-why/dowhy) | MIT | 2026-10-04 | Causal inference with refutation tests. |
| [PyRCA](https://github.com/salesforce/PyRCA) | BSD-3-Clause | 2026-06-02 | Root-cause analysis for metrics. |
| [statsmodels](https://github.com/statsmodels/statsmodels) | BSD-3-Clause | 2026-10-05 | Trend decomposition and tests. |
| [InsightBench](https://github.com/ServiceNow/insight-bench) | MIT | 2025-10-06 | Benchmark for multi-step analytics agents. |
| [RCAEval](https://github.com/phamquiluan/RCAEval) | MIT | 2026-09-29 | README: 735 failure cases with known root causes, for microservices. A design reference for planted causes. |

### Evaluation, data and tracing

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | MIT | 2026-10-05 | Evaluation framework from the UK AI Security Institute. |
| [promptfoo](https://github.com/promptfoo/promptfoo) | MIT | 2026-10-05 | Test runner for prompts and agents. |
| [WebArena](https://github.com/web-arena-x/webarena) | Apache-2.0 | 2025-11-26 | Scores tasks by final state. |
| [WorkArena](https://github.com/ServiceNow/WorkArena) | Apache-2.0 | 2026-09-28 | Closest public analogue: README lists list filtering and dashboard reading on ServiceNow. Access is gated behind a request form. |
| [tau-bench](https://github.com/sierra-research/tau-bench), [tau2-bench](https://github.com/sierra-research/tau2-bench) | MIT | 2026-03-18, 2026-09-28 | Simulated users, policies the agent must follow, and repeated-run consistency. |
| [CheckList](https://github.com/marcotcr/checklist) | MIT | 2023-09-26 | Perturbation tests. Quiet repo; the method is what matters. |
| [Faker](https://github.com/joke2k/faker) | MIT | 2026-09-29 | Seeded synthetic values. |
| [Ragas](https://github.com/vibrantlabsai/ragas) | Apache-2.0 | 2026-02-24 | Repo moved to `vibrantlabsai`. Faithfulness metrics and test-set generation. |
| [DeepEval](https://github.com/confident-ai/deepeval) | Apache-2.0 | 2026-10-05 | Faithfulness and tool-use metrics. |
| [Langfuse](https://github.com/langfuse/langfuse) | MIT outside the `ee` folders | 2026-10-05 | Self-hosted tracing. |
| [OpenLLMetry](https://github.com/traceloop/openllmetry) | Apache-2.0 | 2026-10-04 | OpenTelemetry instrumentation for LLM calls. |

### UX and latency

| Project | Licence | Last commit | Note |
|---|---|---|---|
| [CopilotKit](https://github.com/CopilotKit/CopilotKit) | MIT | 2026-10-05 | README: generative UI, shared state and human-in-the-loop for in-app agents. |
| [AG-UI](https://github.com/ag-ui-protocol/ag-ui) | MIT | 2026-10-02 | README: event protocol between agent and front end; LangGraph supported. |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | MIT | 2026-10-04 | React chat components. |
| [A2UI](https://github.com/a2ui-project/a2ui) | Apache-2.0 | 2026-10-02 | README: the agent sends declarative JSON and the client renders only pre-approved components. |
| [Vega-Lite](https://github.com/vega/vega-lite) | BSD-3-Clause | 2026-10-01 | Charts from a JSON spec that can be validated. |
| [LiteLLM](https://github.com/BerriAI/litellm) | MIT outside the `enterprise` folder | 2026-10-05 | Model routing. |
| [GPTCache](https://github.com/zilliztech/GPTCache) | MIT | 2026-09-22 | Semantic response cache. |

### Treat with care

| Project | Issue found today |
|---|---|
| [Vanna](https://github.com/vanna-ai/vanna) | Archived 2026-03-29. Keep the verified-query idea, not the dependency. |
| [Kuzu](https://github.com/kuzudb/kuzu) | Embedded graph database, archived 2025-10-10. Use NetworkX or plain tables for the knowledge graph. |
| [Soda Core](https://github.com/sodadata/soda-core) | Now Elastic License 2.0, not Apache. |
| [Phoenix](https://github.com/Arize-ai/phoenix) | Elastic License 2.0: fine to self-host, not to offer as a hosted service. |
| [SDV](https://github.com/sdv-dev/SDV) | Business Source License 1.1 (source-available). Faker plus our own scenario scripts avoids it. |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | AGPL-3.0, the same concern as BrowserOS in report 03. |
| [WrenAI](https://github.com/Canner/WrenAI) | Multi-licensed by folder (Apache-2.0, CC-BY-4.0, AGPL-3.0). Check the path before reusing code. |
| [HumanLayer](https://github.com/humanlayer/humanlayer) | README says the code is deprecated. |
| [data-diff](https://github.com/datafold/data-diff), [Chaos Genius](https://github.com/chaos-genius/chaos_genius) | Archived in 2024. |

## Appendix C. Platform options

Report 02 notes that no platform has been chosen. The choice decides how hard G1.4, G5.1 and G5.2 are. If the platform stores the app definition as files we can read, the catalogue is generated from the app and can't drift from it. If it keeps view state in the URL or behind an API, the browser fallback is rarely needed.

Licences were checked today. Feature notes were not; confirm them in each product's documentation.

| Platform | Licence | Why it is worth a look |
|---|---|---|
| [Appsmith](https://github.com/appsmithorg/appsmith) | Apache-2.0 | Low-code builder for internal tools. Pages and widgets are stored as JSON, and widgets can be driven from page parameters. |
| [Apache Superset](https://github.com/apache/superset) | Apache-2.0 | README: no-code chart builder, a lightweight semantic layer and an API. Dashboards, charts and filters are exportable metadata. |
| [Frappe](https://github.com/frappe/frappe) with [ERPNext](https://github.com/frappe/erpnext) | MIT; ERPNext GPL-3.0 | A real ERP whose pages, lists, reports and filters are all described by metadata. |
| [ToolJet](https://github.com/ToolJet/ToolJet), [Budibase](https://github.com/Budibase/budibase) | AGPL-3.0; GPLv3 overall | Similar builders with copyleft licences. |
