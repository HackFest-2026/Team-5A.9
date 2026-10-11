# Page and component retrieval set

This folder holds the search space for the KPI "retrieval quality over hundreds of pages and components" (precision, recall and MRR). The real WWI app has only 11 pages and a few widgets. Finding the right one among so few would prove nothing, so the catalogue is padded with pages that a wholesale ERP would plausibly have but this app does not.

## Files

- `pages.json`: 293 entries. Each entry has `id`, `title`, `module`, `route`, `page_type`, `description`, `widgets`, `filters`, `keywords`, `functional` and `synthetic_decoy`.
- `../../evaluation/v2/retrieval_queries.jsonl`: 150 queries. Each query has `gold` (best first), `acceptable`, `difficulty` and `note`.
- `../../scripts/retrieval_baseline.py`: a pure-stdlib BM25 baseline. It writes `../../evidence/retrieval_baseline.json`.

## Real entries and decoys

- **30 real entries** (`functional: true`):
  - **11 pages.** `overview`, `fulfilment`, `supply`, `analysis` and the detail pages `customer`, `order`, `order-line`, `item`, `purchase`, `purchase-line` and `supplier`. Their routes are the real app routes (`#/overview`, `#/order/{id}` and so on).
  - **19 widgets.** These include all 13 widgets in `catalog/widgets.json`, under the same ids. The other 6 are table panels that the app renders but `widgets.json` does not list: `overview-orders-table`, `fulfilment-unpicked-lines`, `supply-incoming-lines`, `customer-orders-table`, `item-related-incoming` and `supplier-incoming-table`. Each widget's route is the route of its page.
- **263 synthetic decoys** (`synthetic_decoy: true`, `functional: false`):
  - They are spread across Sales, Customers, Purchasing, Warehouse, Logistics, Finance, HR, Marketing, Support, Admin and Reports.
  - Their routes are `#/decoy/<id>`, and **none of these routes exist**. An agent must never navigate to a decoy or claim that one shows data. If a decoy is the best match, the honest reply is "that page is not available in this app".
  - Many decoys are deliberate **hard negatives**: their wording is close to a real page but they mean something else. Examples are *Stock reorder rules editor* (versus the read-only reorder-level chart), *Supplier delivery performance scorecard* (versus incoming units by supplier), *Picking wave planner* (versus picking status), *Monthly revenue budget* and *Sales by territory forecast* (versus actuals on Analysis), *Profit and loss statement* (net profit, not recorded line profit), *Available-to-promise inquiry* and *Stock valuation report* (versus holdings counted in units).

## Rules for retrievers

Rank on the text fields only: title, description, keywords, widgets, filters and module. Do not use `functional`, `synthetic_decoy`, the `#/decoy/` route or the id as ranking features. One query in four has a decoy as its gold answer, so a system that simply drops decoys is penalised.

## Queries

| Target | n | Notes |
|---|---|---|
| Real page or widget | 88 | Varied business phrasing, often without the page's own words |
| Decoy | 38 | Make the search space fair; these are lexically easier |
| Hard | 14 | 11 hard negatives and 3 multi-intent requests; for a multi-intent request the first step's page is gold |
| None fits | 10 | `gold: []`, note `none-fits`. Examples: payroll tax and W-2 forms, weather, web analytics, travel, bill of materials, share price, CO2, competitor prices, translation, 401(k). No page or decoy covers these |

By difficulty there are 61 easy, 70 medium and 19 hard queries.

## Scoring

Precision@1, strict P@1, recall@5 and MRR@10 are computed on the 140 answerable queries:

- **Precision@1:** the top-1 result is in gold or acceptable.
- **Strict P@1:** the top-1 result is in gold.
- **Recall@5:** computed over gold only.
- **MRR@10:** uses the first gold or acceptable result.
- **Route@1:** the top-1 result has the same route as a gold or acceptable entry. This is destination-level accuracy, so a widget on the right page counts.

None-fits queries are handled by abstaining when the top score is below a threshold. The script reports three things:

- **None-fits abstention:** the share of none-fits queries where the system abstained.
- **False abstention:** the share of answerable queries where the system abstained.
- **End-to-end accuracy:** an answerable query counts as correct when the system does not abstain and its top-1 result is relevant. A none-fits query counts as correct when the system abstains.

Run the baseline:

```
python -I scripts/retrieval_baseline.py [--threshold 8.0]
```

## Baseline (BM25, threshold 8.0)

| Group | P@1 | strict P@1 | R@5 | MRR@10 | Route@1 |
|---|---|---|---|---|---|
| Overall (140 answerable) | 0.586 | 0.471 | 0.732 | 0.683 | 0.593 |
| Real targets (93) | 0.409 | 0.290 | 0.613 | 0.548 | 0.419 |
| Decoy targets (47) | 0.936 | 0.830 | 0.968 | 0.951 | 0.936 |
| Easy / medium / hard | 0.623 / 0.508 / 0.786 | | 0.836 / 0.623 / 0.786 | 0.743 / 0.603 / 0.795 | |

None-fits handling:

- **Abstention:** the baseline abstains on 0.40 of none-fits queries, with a false-abstention rate of 0.236. End-to-end accuracy is 0.520.
- **Best threshold:** the best threshold in the sweep is 6.0, giving end-to-end accuracy of 0.560. It was tuned on this same set, so it is optimistic.

The baseline is weakest on the real pages, which is where the agent matters. For example, "payroll tax returns" retrieves *Return authorisation form*, and "revenue by territory" retrieves *Monthly revenue budget*. A useful agent should clearly beat it on real-target P@1 and MRR, and on none-fits abstention.
