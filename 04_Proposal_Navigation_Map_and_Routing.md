# Proposal: Navigation Map and Metadata-Driven Routing

As of 2026-10-05. Gap IDs (G1.1 to G9.3) refer to `03_Reference_Stack_Gaps_and_KPI_Impact.md`.

## Summary

Build an authoritative **route and state graph** of the app from its own definitions, then **enrich** it with business meaning and **validate** it with a rendered crawl. The agent routes by structural filtering, then hybrid retrieval, then reranking. It **abstains or asks** when nothing fits, and it **checks** every action against the graph before and after carrying it out.

This addresses the intent-to-destination, UI-state correctness, retrieval and reliability KPIs. It does not by itself solve analytical faithfulness.

## Components

### 1. Route and state graph (the authoritative map)

- **Source:** our own ERP UI's router config and page definitions, since we build the UI on Wide World Importers. Where the no-code platform supplies a metadata export (navigation hierarchy, deep-link map, filter schemas), that export is the source instead.
- **Contents:**
  - **Nodes:** directory, page and widget.
  - **Edges:** parent and child links, drill-downs (e.g. order line → item → purchase order), and "related" pages.
  - **Each route template with typed parameters:** `/orders/:orderId`, not individual instances.
  - **Each filter:** its field, type and allowed values or ranges; which filters depend on others; the order state must be set in; and its default.
  - **Sort options and deep-link encoding** for every page.

### 2. Semantic enrichment (meaning on top of structure)

For each page and widget, record:

- **Purpose:** the business question it answers.
- **Entity and grain:** order, order line, item or PO, and what one row represents.
- **Supported slots:** customer, item, supplier, date fields and status.
- **Synonyms and user phrasing:** "stuck", "backlog", "not picked".
- **3–5 example utterances**, taken from the labelled corpus.
- **How it differs from similar pages:** e.g. "use Order Lines, not Orders, for item-level gaps".
- **Out of scope:** what it cannot answer.
- **Provenance:** each description is marked as *native*, *corrected* (e.g. backorder direction) or *synthetic*.

### 3. Validation crawl (Playwright, rendered)

- Load each route template with sample parameters, logged in, and record which widgets and filters actually appear.
- Compare the results against the graph and flag missing routes, widgets that have disappeared, and filters that don't match. This is the drift detector.
- Store the snapshots as the expected UI states. The same snapshots are reused to check state after each action.

### 4. Routing pipeline (at run time)

1. **Extract intent and slots** from the request, together with the **current context** (page, selection, active filters).
2. **Filter by structure:** keep only pages whose grain and filters can satisfy the slots.
3. **Hybrid retrieval** over the enriched descriptions: keyword (BM25) search for IDs and field names, vector search for meaning.
4. **LLM rerank** of the top 5–10 candidates, using the "differs from" notes and the current context.
5. **Abstain or ask a clarifying question** if no candidate fits, or if the top two scores are within a set margin.
6. **Check parameters** against the graph: real IDs, valid dates and allowed values.
7. **Act** through a direct route or state API: deep link plus filter state.
8. **Read the resulting UI state back** and compare it with the requested state. Retry or report on a mismatch.

### 5. Browser fallback (only where no direct route or API exists)

- Playwright, guided by the graph rather than by free exploration.
- Element grounding can borrow from UI-annotation corpora (Mind2Web, WebUI, Rico style), which the brief lists as acceptable stand-ins.
- The same read-back check after each action as in step 8.

## What it fixes

| Gap | How the proposal addresses it | KPI affected |
|---|---|---|
| G1.1 Shape, not meaning | Enrichment adds purpose, grain and slots | UI-state, retrieval |
| G1.2 Wrong metadata | Provenance tags; corrected descriptions take precedence | Analytical faithfulness |
| G1.3 Static graph | Graph records filter types, allowed values, dependencies and setting order | UI-state, reliability |
| G1.4 Drift | The validation crawl compares the graph with the rendered app | Intent → destination, reliability |
| G2.1 Near-identical components | Structural filter + "differs from" notes + rerank | Intent → destination, retrieval (precision, MRR) |
| G2.2 Words only | Current context is passed to the structural filter and the reranker | Intent → destination, UX |
| G2.3 No "nothing fits" answer | Abstain or ask when the margin is small or no page can take the slots | Intent → destination, reliability |
| G3.2 Slots not checked | Parameters checked against the graph before acting | UI-state, reliability |
| G3.4 Ambiguity guessed | Clarifying question triggered by close scores | Multi-step success |
| G5.1 Fragile browser | Direct routes and APIs first; fallback guided by the graph | Multi-step success, reliability |
| G5.2 No check after acting | UI state read back and compared with the requested state | UI-state, reliability |
| G8.2 No action trace | Every step is logged with expected and observed state, giving a dataset to score | Reliability (invented-action rate becomes measurable) |

## What it does not fix (other workstreams)

- **G3.1 multi-step planning**, **G3.3 carry-over between turns** (beyond passing context to routing) and **G5.3 recovery** need an investigation-state and planner design.
- **G4.1–G4.3 text-to-query meaning and safety**, and **G6.1–G6.3 analytical faithfulness**, need a semantic measures layer and traceable queries.
- **G7 data** needs synthetic scenarios with different correct answers, plus held-out utterances not written by the team.
- **G9 UX** needs labels separating fact from inference, and a plan the user can review before it runs.

## Considered and rejected

| Idea | Why it was rejected | Kept instead |
|---|---|---|
| Building the route tree by crawling with curl | Single-page apps return an empty shell; login walls; sees route instances, not templates; filter state is invisible | Generate the graph from our own router and metadata; use a rendered Playwright crawl only to validate |
| E-commerce call-to-action and gaze data for routing | Shows where people look, not which page answers a question; designed for purchase funnels, not ERP investigation | UI-annotation corpora only for element grounding in the fallback; saliency at most as a later UX enhancement |

## How we will measure it

Run an ablation on the labelled utterance set, including a held-out paraphrased subset:

| Configuration | Measures |
|---|---|
| A. Raw page names only | Top-1 accuracy, MRR |
| B. + Enriched descriptions | Top-1 accuracy, MRR |
| C. + Structural slot filtering | Top-1 accuracy, MRR |
| D. + Rerank, abstain and context | Top-1 accuracy, MRR, abstention precision |
| D + parameter check + read-back | UI-state exact match, invented-action rate |
