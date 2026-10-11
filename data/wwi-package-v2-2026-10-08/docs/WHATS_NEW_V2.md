# What's new in v2 (and why)

v1 could answer one question at a time about a fixed set of IDs. Real users ask chains of questions: *"Orders went up in May. Where? Which customers? What are they waiting for? Is stock coming?"* v2 adds what an agent needs to follow such a chain, without changing any v1 data or behaviour.

The data rows are byte-identical to v1 (`dataset_version` is still `wwi-data-v1-2026-10-08`). The Contract goes from 0.1.0 to 0.2.0, and the package from 1.0.0 to 2.0.0.

## 1. New questions the app can answer

| Need | Before (v1) | Now (v2) |
|---|---|---|
| Break a number down ("by territory") | Only 6 fixed charts | Any measure by any of 10 dimensions: month, customer, customer category, buying group, state, sales territory, salesperson, item, supplier, stock group |
| Compare periods ("May vs April") | Two separate queries, maths left to the agent | One call returns both totals, the change, % change, and each group's share of the change |
| Filter by region, segment, rep | Not possible | 5 new filters: customer category, buying group, state, sales territory, salesperson |
| Money | Revenue and profit blocked | Invoiced sales (M10) and gross line profit (M11) published **with a label**: the source states no currency, and the profit is gross line profit, not net |
| Units ordered | – | M13 ordered units |
| Sort and top-N | Fixed sort per chart | `sort` (by value, label or change) and `top_n`, with an "All others" row so totals still add up |

## 2. Help the agent needs between steps

- **Names to IDs (`/api/resolve`):** "Litware" becomes supplier 7. Ambiguous names are flagged instead of guessed: "Hudson" matches two salespeople, and "Tailspin Toys" is both a buying group and 200 store names. Unknown names return "none".
- **One-hop context (`/api/related`):** for a customer, order, item, supplier, purchase order or salesperson, one call returns everything linked to it, plus ready-made next steps. Item 80, for example, returns its supplier, stock, unpicked demand, waiting customers and incoming purchase lines.
- **Glossary (`catalog/glossary.json`):** business words mapped to measures and filters ("backlog-ish" words handled carefully):
  - "Revenue" maps to M10, with its caveat.
  - "Open orders" is ambiguous, so the glossary gives the question to ask.
  - "Why did…", "forecast" and "net profit" are unsupported, so the glossary gives the honest reply.
  - "This month" and "last month" are anchored to the archive end date, 31 May 2016.
- **Record map (`catalog/graph.json`):** how records link (customer → order → line → item → supplier / purchase lines), with the traps written down:
  - Purchasing is never allocated to customer orders.
  - Purchases are counted in cartons, not units.
  - An item's nominated supplier can differ from the supplier on its purchase order.
  - Order counts by item overlap.
- **Playbooks (`catalog/playbooks.json`):** 8 step-by-step investigation patterns, including "explain a change", "unpicked-demand triage", "supplier exposure", "customer review" and "order trace".
- **Tool definitions (`catalog/operations.json`):** each operation with a JSON input schema, ready to hand to an LLM as tools.
- **`GET /api/contract`:** all of the above in one call.

## 3. App

- A new **Analysis** page (`#/analysis?...`) shows exactly what `/api/analyze` returns. It has drill-in buttons on every row, and the full request lives in the URL, so a deep link reproduces the view.
- `window.wwiState` reports what the page actually applied, so the agent can check its action worked.
- The v1 pages are unchanged.

## 4. Evaluation material (`evaluation/v2/`)

- **Multi-step task chains:** development and held-out sets, plus labelled single-turn utterances. Their expected answers come from `scripts/oracle_v2.py`, a separate implementation that reads the raw files with its own SQL and never imports the engine.
- **Retrieval test:** `catalog/retrieval/pages.json` lists 293 pages (30 real, 263 labelled decoys), and `retrieval_queries.jsonl` holds 150 queries with gold answers. The KPI "retrieval over hundreds of pages" can now be measured, against a BM25 baseline.

## 5. How it was checked

| Check | Result |
|---|---|
| All v1 checks, run against v2 | 205 data, 277 metric, 31 API, Contract: all pass |
| v2 checks (`scripts/validate_v2.py`) | See `evidence/analysis_validation.json`. They cover:<br>• parity with the v1 engine on 100+ requests<br>• breakdowns adding up to totals<br>• raw-file cross-checks for territories, salespeople, money, categories and states<br>• name resolution and entity hops<br>• 17 invalid requests correctly refused<br>• Contract cross-references<br>• HTTP behaviour |
| Engine vs independent oracle on every task | See `evidence/task_answer_check.json` |

## 6. Limits that still apply

- The data is simulated and frozen in 2016, with no recorded reasons. The agent can show where a change is concentrated, not why it happened.
- Customer category, territory and buying group are current values, not values at the time of the order.
- The money measures are labelled, not converted. To withdraw them, set `M10` and `M11` to `"blocked"` in `catalog/analysis_measures.json`.
- Decoy pages in the retrieval catalogue don't exist in the app. They are there only to make search hard.
