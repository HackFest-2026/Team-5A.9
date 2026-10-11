# WWI package v2: specification

v2 extends the v1 package so an agent can carry out **multi-step** investigations.

Same source data as v1 (`dataset_version` stays `wwi-data-v1-2026-10-08`; raw Parquet is byte-identical). Contract version goes `0.1.0 -> 0.2.0`; package version `2.0.0`. Every v1 file, endpoint and check keeps working unchanged; v2 only adds.

Conventions (unchanged from v1): periods are `[start, end)` dates, inclusive start / exclusive end, within 2013-01-01..2016-06-21; naive dates; base scenario unless `scenario_id` says otherwise; customer attributes (category, buying group, delivery city/state/territory) are the **current stored** values, not values at order time.

## 1. Measures available to `/api/analyze`

| ID | Name | Definition (exact) | Grain | Date basis | Status |
|---|---|---|---|---|---|
| M01 | Orders created | `COUNT(DISTINCT OrderID)` over order lines in scope | order | `order_date` (Orders.OrderDate) | verified (v1) |
| M02 | Stored unpicked units | `SUM(GREATEST(Quantity - PickedQuantity, 0))` over order lines | order line | `order_date` | verified (v1) |
| M03 | Orders with unpicked quantities | `COUNT(DISTINCT OrderID)` over lines with `Quantity - PickedQuantity > 0` | order | `order_date` | verified (v1) |
| M13 | Ordered units | `SUM(Quantity)` over order lines | order line | `order_date` | new, verified in v2 |
| M05 | Related incoming units | `SUM((OrderedOuters - ReceivedOuters) * QuantityPerOuter)` over purchase lines where `NOT PurchaseOrders.IsOrderFinalized AND NOT IsOrderLineFinalized AND OrderedOuters > ReceivedOuters` | purchase line | `none`, `purchase_order_date` (PurchaseOrders.OrderDate) or `expected_delivery_date` (PurchaseOrders.ExpectedDeliveryDate) | verified (v1) |
| M10 | Invoiced sales excluding tax | `SUM(InvoiceLines.ExtendedPrice - InvoiceLines.TaxAmount)` | invoice line | `invoice_date` (Invoices.InvoiceDate) | published with label (see note) |
| M11 | Recorded gross line profit | `SUM(InvoiceLines.LineProfit)` | invoice line | `invoice_date` | published with label (see note) |

Money note: M10/M11 arithmetic reconciles exactly on all 228,265 invoice lines. The source states no currency; the company is described by Microsoft as US-based. Unit label: `"sample amount (currency not stated in source)"`. M11 is recorded line profit, **not** net profit. Values are decimals serialized as strings with 2 decimals.

Order measures (M01, M02, M03, M13) need `date_basis: "order_date"`; period optional (no period = all history). M05 needs `none` / `purchase_order_date` / `expected_delivery_date`. M10/M11 need `invoice_date`.

## 2. Dimensions (`group_by`)

| Dimension | Label source | Applies to | Additive? |
|---|---|---|---|
| `none` | – | all | – |
| `month` | `strftime(<date basis column>, '%Y-%m')` | all with a dated basis (not M05 with `none`) | yes |
| `customer` | Customers.CustomerName (key CustomerID; for orders Orders.CustomerID, for invoices Invoices.CustomerID) | order + invoice measures | yes |
| `customer_category` | CustomerCategories.CustomerCategoryName via the customer | order + invoice | yes |
| `buying_group` | BuyingGroups.BuyingGroupName via the customer; NULL -> label `"No buying group"`, id `null` | order + invoice | yes |
| `state_province` | StateProvinces.StateProvinceName via Customers.DeliveryCityID -> Cities.StateProvinceID | order + invoice | yes |
| `sales_territory` | StateProvinces.SalesTerritory via the same path | order + invoice | yes |
| `salesperson` | People.FullName via Orders.SalespersonPersonID (orders) or Invoices.SalespersonPersonID (invoices) | order + invoice | yes |
| `stock_item` | StockItems.StockItemName via line StockItemID | all | yes for line measures (M02, M13, M10, M11, M05); **overlapping** for order counts (M01, M03: an order with 3 items counts in 3 groups) |
| `supplier` | Suppliers.SupplierName: item's nominated StockItems.SupplierID for order/invoice measures; PurchaseOrders.SupplierID for M05 | all | as stock_item |
| `stock_group` | StockGroups.StockGroupName via StockItemStockGroups | all | **overlapping always** (an item can be in several groups) |

Customer-side dimensions are invalid for M05 (purchasing is not allocated to customers) -> 422.

## 3. Filters (all optional, all `eq`, positive integer IDs unless noted)

v1 filters: `customer_id, stock_item_id, supplier_id, stock_group_id, order_id, order_line_id, purchase_order_id, purchase_line_id, status`.
v2 adds: `customer_category_id`, `buying_group_id`, `state_province_id`, `sales_territory` (string, one of: `Far West, Great Lakes, Mideast, New England, Plains, Rocky Mountain, Southeast, Southwest, External`), `salesperson_id`.

Applicability: customer-side filters (`customer_id`, the five new ones, `order_id`, `order_line_id`) are valid for order and invoice measures, invalid for M05. `purchase_order_id`, `purchase_line_id` valid only for M05. `supplier_id` = item's nominated supplier for order/invoice measures, PO supplier for M05. `status` for order measures: `all | quantity-not-yet-picked | picking-incomplete | picking-complete` (v1 semantics: line UnpickedUnits>0, order PickingCompletedWhen NULL / NOT NULL); for M05 `all | incoming`; invalid for M10/M11 unless `all`. Invalid combinations -> HTTP 422 `{completed:false}`; **never silently ignored**.

## 4. Operations (HTTP, localhost)

### `POST /api/analyze`
```json
{"measure_id":"M01","date_basis":"order_date","start":"2016-05-01","end":"2016-06-01",
 "compare_start":"2016-04-01","compare_end":"2016-05-01",
 "group_by":"sales_territory","filters":{},"sort":"value_desc","top_n":10,"scenario_id":"base"}
```
- No `compare_*`: returns `total` and (if grouped) `rows: [{key, label, value, share}]`. `share = value/total` (null for overlapping dimensions).
- With `compare_*` (the baseline period; `start/end` is the current period): returns `total_baseline, total_current, change, pct_change` (null when baseline=0) and rows `{key,label,baseline,current,change,share_of_change}`; `share_of_change = change/total change` (null if total change is 0 or the dimension overlaps).
- `sort`: `value_desc` (default), `value_asc`, `label_asc`, `label_desc`, `change_desc`, `change_asc`, `abs_change_desc` (compare default). Tie-break: key ascending.
- `top_n` 1..50 (default 10). For additive dimensions, remaining groups are summed into one row `{key:null,label:"All others (n groups)",is_other:true,...}` (a real group can also have key null, e.g. "No buying group"; use `is_other` to tell them apart) so rows always add up to the total.
- Response always echoes `applied` (the full validated request), `measure` (id, name, unit, definition), `dimension` (id, additive), and `deep_link` (the Analysis page route reproducing the result).

### `POST /api/resolve`
`{"text":"litware","types":["supplier"],"limit":5}` -> `{status: unique|ambiguous|none, candidates:[{type,id,name,score,match}]}`. Types: `customer, stock_item, supplier, customer_category, buying_group, stock_group, state_province, sales_territory, salesperson`. Match kinds: `exact` (casefolded full name or alias), `alias`, `prefix`, `token`, `fuzzy`. `unique` only when exactly one best candidate is exact/alias or clearly ahead; otherwise `ambiguous` (agent must ask) or `none`.

### `POST /api/related`
`{"entity_type":"stock_item","entity_id":80}` -> the entity's summary plus linked entities with counts and next-step suggestions (each a ready `analyze`/`records` request and a deep link). Types: `customer, order, stock_item, supplier, purchase_order, salesperson`.

### `GET /api/contract`
Returns every Contract document (measures, filters, dimensions, glossary, graph, playbooks, operations, views, widgets, charts, version) for the agent to load once.

## 5. New Contract documents (catalog/)

- `dimensions.json`: section 2 as data.
- `glossary.json`: business words -> measure / filter / date basis; ambiguous words with the clarifying question to ask; unsupported asks with the honest-limit reply.
- `graph.json`: entities, keys, display names, relationships (from, to, join, cardinality, meaning), detail routes.
- `playbooks.json`: named multi-step investigation patterns (ordered steps, each an operation + how its output feeds the next).
- `operations.json`: tool definitions (name, purpose, endpoint, JSON input schema, when to use) for agent tool-calling.
- `retrieval/`: padded page catalogue for the retrieval KPI (real pages + labelled synthetic decoys).

## 6. App

New page `#/analysis?measure_id=..&group_by=..&start=..&end=..&compare_start=..&compare_end=..&sort=..&top_n=..&<filters>` that renders exactly what `/api/analyze` returns (total cards, ranked bars, change table) and exposes `window.wwiState` (route + applied request) for the agent's after-action check.

## 7. Evaluation additions (evaluation/v2/)

- `dev_multistep.jsonl`: development multi-step chains (each step: utterance, expected operation(s), expected key outputs, context carried from the previous step).
- `holdout_multistep.jsonl`: held-out chains, frozen with hashes; never used for prompt tuning.
- `dev_utterances.jsonl`: single-turn labelled utterances (intent, target view, measure, dimension, filters incl. names needing resolution, period).
- Expected values are computed by `scripts/oracle_v2.py`, an **independent** implementation reading raw Parquet with its own SQL (no import of the engine).
- `retrieval_queries.jsonl`: queries with gold page IDs for precision/recall/MRR.
