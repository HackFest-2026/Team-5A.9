# WWI v2 findings — 8 October 2026

Completed the data foundation, Application Contract, local dashboard, synthetic branch and frozen evaluation corpus described in `09_v2_WWI_Execution_Plan.md`. No PowerPoint was edited; all findings and screening wording are new Markdown files. No SQL Server installation, restore, simulator execution or source-data change was performed.

## What changed from the previous diagnostics

The prior case-focused diagnostics are preserved. This package adds a full normalized 21-entity typed extract, materialized DuckDB, offline Windows x64 runtime, parameterized backend, three dashboard views and seven detail types, six verified measure definitions, six chart definitions, one separate synthetic fixture, and 12 development/18 held-out task definitions. Optional history and recorded-date lateness reviews were performed only after P2 acceptance. No ERP, agent training or measured agent scoring is included.

## Source, acquisition and scope

Source: `DESKTOP-K46JKQF` / `WideWorldImporters`, SQL Server `13.0.5026.0`, Enterprise Evaluation. Existing Windows-authenticated `lpc:localhost` was used with installed ODBC Driver 13 and Python x64. Driver 17/18 were absent; the usable installed Microsoft driver succeeded without a security-configuration change. DW was absent. Business order dates: **2013-01-01 through 2016-05-31**. The source connection was closed after acquisition.

| Entity | Exported rows |
|---|---:|
| Sales.Customers | 663 |
| Sales.Orders | 73,595 |
| Sales.OrderLines | 231,412 |
| Warehouse.StockItems | 227 |
| Warehouse.StockItemHoldings | 227 |
| Purchasing.PurchaseOrders | 2,074 |
| Purchasing.PurchaseOrderLines | 8,367 |
| Purchasing.Suppliers | 13 |
| Sales.Invoices | 70,510 |
| Sales.InvoiceLines | 228,265 |
| Warehouse.StockItemTransactions | 236,667 |
| Sales.CustomerCategories | 8 |
| Sales.BuyingGroups | 2 |
| Warehouse.StockGroups | 10 |
| Warehouse.StockItemStockGroups | 442 |
| Warehouse.PackageTypes | 14 |
| Application.People | 1,111 |
| Application.Cities | 37,940 |
| Application.StateProvinces | 53 |
| Application.Countries | 190 |
| Application.SystemParameters | 1 |

Explicit schema/PK/FK/computed definitions/descriptions/collations are preserved. All rows of the selected entities were exported, including invoices, invoice lines, stock transactions, customer categories, buying groups, stock groups/bridge and geography. Unused binary/spatial columns are enumerated as omitted in the manifest. Out-of-scope FK lookups (delivery methods, supplier categories, colors and transaction types) are listed in `evidence/parity.json`; no labels from them are invented. Geography and buying-group data are acquired but are not published filter operations in this version.

Integer widths, exact decimal precision/scale, booleans, Unicode, NULL versus empty text, raw JSON and naive timestamps remain typed. Scale-seven datetime2 is represented by timestamp microseconds plus a named `__100ns` residual companion (0–9); together these preserve all seven fractional digits, including year 9999. ID equality is the supported entity-selection method; SQL Server collation is recorded, and free-text/case-insensitive SQL Server search equivalence is not claimed.

Acquisition is an **observed stable window, not a certified atomic snapshot**. Snapshot isolation was disabled. Two attempts stopped before business export on transient logged transactions; retained evidence shows the failure. The subsequent acquisition required bounded quiescence probes, no active user workload and matching pre/post controls. Probes cannot prove that every possible intervening write was absent. No NOLOCK, configuration changes or business procedures were used. Physical integrity remains uncertified because the earlier optional CHECKDB did not complete.

## Full-history unpicked/backorder findings

Remaining units are `max(Quantity - PickedQuantity, 0)` at surviving order-line grain, then aggregated. Full history contains **3,147 lines, 3,085 distinct orders and 360,276 units**. May-created orders contribute **168 lines, 161 orders and 17,710 units**. The other 2,924 orders are **94.78%** of all unpicked orders.

Backorder targets account for **3,080/3,085 orders (99.84%)** and **359,190/360,276 units (99.70%)**; five non-target orders account for 1,086 units. EXISTS filters avoid a multiplying self-join. Traversal finds 7,538 links/distinct targets, maximum depth three, no cycles or backward creation-date sequences. All 3,080 unpicked targets retain the **same** creation date as their referencing original; none move into a later creation-date cohort. Acquired simulator definitions explicitly copy original dates and move uncompleted lines to the target, then set the original's BackorderOrderID. They were inspected, never run.

Unpicked creation dates span 2013-01-12 to 2016-05-31. Monthly/full daily distributions, item concentration, chain paths, samples and age buckets are in `evidence/cutoff/`. Age is a date difference to the disclosed 2016-05-31 display boundary, not elapsed operational waiting time or an as-of stock snapshot.

| Creation cohort | Orders created | Orders with stored unpicked quantities | Stored unpicked units |
|---|---:|---:|---:|
| April 2016 | 1,951 | 135 | 15,050 |
| May 2016 | 2,047 | 161 | 17,710 |

Creation volume increases by 96 orders (4.92%). These rows cannot establish that historical period-end backlog increased.

| Final calendar window ending May 31 | Unpicked orders | Units | Order share of all 3,085 | Unit share of all 360,276 |
|---|---:|---:|---:|---:|
| 1 day | 9 | 806 | 0.292% | 0.224% |
| 3 days | 17 | 1,629 | 0.551% | 0.452% |
| 7 days | 47 | 4,637 | 1.524% | 1.287% |

With May-only denominators (161 orders /17,710 units), those windows contain 5.59%/10.56%/29.19% of orders and 4.55%/9.20%/26.18% of units. Calendar spines include zero-activity days. `daily_may.svg` is a standalone daily chart. Thresholds are descriptive, not causal tests. The final week is visible within May but does not explain the large older cohort. Expected dates extend into June.

**Story decision:** lead with verified orders created and retain **stored unpicked backorders with related incoming supply** as the investigation. Descriptive stored-state measures are valid; a supplier-failure, abnormal-shortage, late-delivery-rise or historical May-backlog-growth narrative is unsupported. Matching a purchase by item is related supply, not customer allocation; holdings are not available-to-promise.

## Revenue, recorded profit and current segments

The first P2 investigation reconciled all 228,265 invoice lines using exact DuckDB decimals and an independent Python Decimal raw-row oracle. Quantity × UnitPrice totals **172,261,341.2000**, tax **25,782,098.25**, ExtendedPrice **198,043,439.45**, and recorded LineProfit **85,729,180.90** (currency unverified). ExtendedPrice equals quantity × price plus tax on every row; tax rounding and arithmetic exceptions are zero. The exception CSV still has headers and a recorded zero count. All acquired invoice headers have IsCreditNote=false and all line extended amounts are positive: there is no populated negative/credit cohort to test, and no double-negation was applied.

**M10 and M11 are blocked for publication:** acquired transaction fields do not independently establish the currency. Profit semantics are not audited net profit. Ordered value by OrderDate also reconciles independently, but its currency provenance is unresolved, so no currency-labelled fallback card was substituted and no ordered value is labelled revenue. This nonblocking result is retained in `evidence/candidates/`.

M12_orders_category is verified: current **sold-to** category attribution, inheriting M01's creation-date definition. It reconciles to all 73,595 orders. Current attributes are not asserted to be historical memberships.

| Current sold-to category | Orders | Share of 73,595 |
|---|---:|---:|
| Computer Store | 5,041 | 6.85% |
| Corporate | 4,896 | 6.65% |
| Gift Store | 5,089 | 6.91% |
| Novelty Shop | 52,547 | 71.40% |
| Supermarket | 6,022 | 8.18% |

Buying-group evidence: Tailspin Toys 23,296 orders; Wingtip Toys 23,123; explicit no-group 27,176. These sum to 73,595; buying-group filtering is retained as acquired enrichment rather than exposed UI capability. All 70,510 invoices reference an existing order, with zero NULL/orphan mappings and no order with multiple invoices in this extract; revenue arithmetic did not require an Orders join.

## Published measures, charts and filters

Verified definitions: M01 distinct orders created; M02 positive remaining item-unit counts; M03 distinct orders with a positive remaining line; M04 undated per-item holdings/reorder/target levels; M05 positive remaining outers × QuantityPerOuter under nonfinalized header/line flags; M12_orders_category orders by current sold-to category. Unlike products' unit totals are counts, not money, equivalent goods or physical volume.

The four selected primary charts are monthly orders (calendar spine), top unpicked items (units descending with ID tie break), holdings versus reorder (per item, never demand-join summed), and incoming units by **actual PO supplier**. Current-category order bars and an order-grain picking-status split add two verified views. Picking status uses header completion NULL/non-NULL, not delivery or quantity-based finalization.

Overview, Fulfilment and Supply have customer, order, order-line, item, purchase, purchase-line and supplier panels. Record results are deterministically sorted and paginated (default50, maximum200). Holdings show up to50 sorted items as a preview; any explicit item ID exposes its own evidence. Dates/units/provenance and related-supply limitations are displayed. Partial selected months use the visible inclusive/exclusive request interval; the archive ending May31 is not evidence of later completion. Screenshots are in `evidence/ui/`.

Supported backend filters: customer/item/nominated supplier/stock group/order/order-line/status on compatible sales queries; item/actual supplier/stock group/PO/purchase-line/open flags on purchasing; item/nominated supplier/stock group for undated holdings. Stock groups use existence filtering, not a multiplying bridge join. Unsupported entity/metric combinations reject. The UI exposes dates, customer/item/supplier IDs and scenario; additional allowlisted IDs are accessible through the backend/CLI. Category is a published grouping, not an arbitrary dynamic category filter.

Creation measures require OrderDate. Record browsing separately supports expected delivery and header/line picking-completion dates. Purchasing supports PO-date or expected-date intervals. Holdings omit active dates, retaining period intent visibly as investigation context. Invoice/confirmation dates are acquired but unverified money/confirmation metrics are not exposed. All intervals use inclusive start/exclusive end; timestamps stay naive. Changing scenario clears stale entity choices. Detail routes retain compatible IDs and state is persisted in the URL. Errors clear stale content and set completed=false.

Typed Pydantic models and generated JSON schemas validate measures, filters, charts, views, widgets, contract version and requests. The capability API exposes only verified measures. The interface is a local companion API, not an installed no-code platform or an automatic agent.

## Synthetic scenario and frozen evaluation corpus

Exactly one additive fixture, `no_incoming_v1` version1.0.0, seed0, is separate from raw source data. New item1227/order74595/line232412 do not collide with source IDs. It reuses verified source customer11/supplier4/package7/6 lookups, adds 120 ordered/0 picked units and holdings20, and adds no purchasing. Expected demand120, holdings20, qualifying incoming0, with a persistent SYNTHETIC label. The fixture supplies no reason for missing supply. Base results still match raw-source controls and independent raw-row calculations.

Frozen corpus: 12 development tasks,18 held-out (6 view/filter,6 follow-up/context,4 comparison/drill-down,2 ambiguous/no-fit). Each has initial state, versions, allowed operations, retained/replaced filters, independently computed values/IDs and final-state assertions. Fault cases specify future harness injection for ignored item filters and stale selection context. Expectations and holdout files are maintainer-only and return404 from the public local server. No prompt tuning or agent runs occurred. **15/18 is a future target, not measured accuracy.** Hashes and freeze time are in `evaluation/freeze.json`.

## Optional history and lateness verdicts

Estimated surviving open lines at exclusive boundaries April1/May1/June1: **2,942 /3,041 /3,147**. Independent raw calculations match; final3,147 agrees with stored NULL-completion and quantity-unpicked lines. Samples are explainable, but agreement at the final boundary does not certify earlier histories. Date-only creation, line movement/backorders and missing amendment/cancellation/delete/partial-pick timelines invalidate an exact lifecycle claim. Exact outstanding units and historical inventory are **blocked**; stock movements alone do not certify a complete signed movement ledger plus opening balance. M09 remains an approximation outside primary charts.

Supplier candidate: 8,358 eligible finalized fully received lines, **0 recorded last receipt dates after stored expected PO dates**;9 open/partial lines have NULL receipt dates and are unknown/excluded, not on-time. The chart is rejected as uniform zero in this narrow eligible population. Final receipt is not first receipt or certified original-promise performance.

Customer candidate: 70,426 confirmed eligible invoices; **4,470 (6.35%)** calendar confirmations after referenced stored order expectations;84 NULL confirmations are unknown/excluded. April116/1,856 =6.25%; May107/1,864 =5.74%. No assertion that lateness rose in May is supported. Samples preserve raw JSON/promoted confirmation values and the referenced order, with no original/backorder promise collapse. M08 remains a stored-date candidate; causal service performance is unsupported. Monthly counts, rates, zero counts, missing/invalid values and join checks are retained.

M06 date-based picking duration remains candidate: OrderDate is date-only, incomplete orders excluded/reported, and completed-cohort median is11hours in each monthly output. It is not exact processing time. No optional candidate is exposed as a verified dashboard measure.

## Validation, portability and effort

Source/parity/type/PK/FK/raw-oracle/fixture validation: **205 checks passed**. Independent metric/filter/chart/record domain: **277 checks passed**. HTTP behavior/security-surface checks: **31 passed**. Contract schemas and references pass; browser checks inspect actual returned records and state, not only routes. These are implementation tests, not agent evaluation. The tested domains are explicit; exhaustive filter combinations are not claimed.

Final moved-folder acceptance rebuilds materialized tables from relative Parquet using its own bundled runtime while pyodbc.connect and socket connections are denied in that process. It validates source parity and Contract, queries all six verified measures/six charts/seven record entities, and separately checks fixture120/0. The live SQL service was not stopped; instrumentation establishes the tested process did not use it. Proof: `evidence/offline_move_final.json`.

Raw Parquet occupies14,580,711bytes; the initial materialized database50,868,224bytes. Runtime and dependency versions/licenses are bundled for Windows x64. Main metric probes use fresh connections, three repeat runs each (0.0044–0.0781seconds observed); repeated result hashes agree. This is local observed timing, not a cold filesystem-cache benchmark or a guaranteed SLA. Build/check/investigation elapsed times and acquisition failures are logged. Planning budgets were not feasibility guarantees; money arithmetic took seconds and review stayed within the60-minute cap; optional probes stayed within their120-minute caps.

## Handoff and approved wording

Unzip the versioned package, run `rebuild.cmd` if rebuilding, then `launch.cmd` and open localhost8017. `README.md` gives exact CLI/API operations and explicit fresh-directory source refresh instructions. Ordinary rebuild/query needs no SQL Server, SSMS, internet or credentials. Stop the local server before an explicit rebuild. The package can be moved; no absolute-path data views are retained.

Approved screening claim: **“Orders created in May with quantities still unpicked, traced to holdings, related incoming supply and supplier, in the stored sample state.”** No slides were edited. Remaining integration dependencies are a future no-code/agent frontend and a future scored evaluation harness. Any money publication needs independently established currency; exact historical inventory/backlog needs complete event evidence. No additional dataset search, warehouse installation, simulator extension or model training was undertaken.
