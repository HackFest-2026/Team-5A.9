# The WWI dataset: a complete guide

Written for team members who did not build the dataset. It covers what the data is, how it was built, every metric and its status, why some metrics are blocked, and exactly what changed between v1 and v2.

## 1. In one paragraph

The dataset is **Wide World Importers (WWI)**, Microsoft's official sample database for SQL Server (MIT licence). WWI is a **fictional** wholesale company in the San Francisco Bay Area that imports novelty goods (mugs, t-shirts, USB gadgets, toys) and sells them to shops across the US. The data is **simulated** and covers **1 Jan 2013 to 31 May 2016**. We use it as the "business data" behind a small analytics app, and the agent we are building answers questions about it by operating that app.

There are two packages:

| Folder | Built by | What it is |
|---|---|---|
| `data/wwi-data-v1-2026-10-08/` | A separate data agent, 7–8 Oct | The data, a small read-only app, 6 verified metrics and 30 test tasks. **Approved and untouched.** |
| `data/wwi-package-v2-2026-10-08/` | Claude (this session), 8 Oct | A copy of v1 with additions for multi-step analysis. **The data rows are identical**; only tools, documents and tests were added. |

## 2. What is in the data

### The business, in plain words

1. **Customers** (663 shops and people) place **orders**. Each order has **order lines**: one per product, with the quantity ordered and the quantity picked so far.
2. Warehouse staff **pick** the goods. If there is not enough stock, the unpicked part moves to a new **backorder**. The original order points to it through `BackorderOrderID`.
3. Picked orders are **invoiced** (70,510 invoices). The invoice lines carry price, tax and recorded profit.
4. The warehouse holds **stock** of 227 products. Each product has a quantity on hand and a reorder level.
5. WWI buys stock from 13 **suppliers** through **purchase orders**. These are counted in **outers** (cartons); one carton of item 80 holds 12 units.

### The 21 tables

| Group | Table | Rows | Meaning |
|---|---|---:|---|
| Sales | Customers | 663 | Shops and individuals; category, buying group, delivery city |
| | Orders | 73,595 | One per order; date, customer, salesperson, backorder link |
| | OrderLines | 231,412 | Product, quantity ordered, quantity picked |
| | Invoices | 70,510 | One per invoiced order |
| | InvoiceLines | 228,265 | Price, tax, extended price, recorded line profit |
| | CustomerCategories | 8 | Novelty Shop, Supermarket, Gift Store, Computer Store, Corporate and others |
| | BuyingGroups | 2 | Tailspin Toys and Wingtip Toys (store chains) |
| Warehouse | StockItems | 227 | Products: name, supplier, units per carton |
| | StockItemHoldings | 227 | Stock on hand, reorder level, target level (one row per product) |
| | StockItemTransactions | 236,667 | Stock movements |
| | StockGroups and the bridge table | 10 groups, 442 links | Product groups (Mugs, T-Shirts, Toys…). One product can be in several groups |
| | PackageTypes | 14 | Each, Carton, Bag… |
| Purchasing | Suppliers | 13 | Fabrikam, Litware, Contoso… |
| | PurchaseOrders | 2,074 | Order date, expected delivery date, finalised flag |
| | PurchaseOrderLines | 8,367 | Cartons ordered and received |
| Reference | People | 1,111 | Staff, including 10 salespeople |
| | Cities, StateProvinces, Countries | 37,940 / 53 / 190 | Geography; each state belongs to one of 9 sales territories |
| | SystemParameters | 1 | Company settings |

Nine photo, map and password columns were left out on purpose. They are listed in `manifest.json`.

### Traps the agent must know

These are why a "just write SQL" agent goes wrong on this data:

- **Cartons vs units.** Purchase lines count cartons. Multiply by `QuantityPerOuter` to get units: item 80's 1,831 cartons are 21,972 units.
- **Purchasing is not reserved for customers.** An incoming purchase for item 80 is *related* to customers waiting for item 80. It is not *allocated* to any particular order.
- **There are two kinds of supplier.** An item has a *nominated* supplier, and each purchase order has its *actual* supplier. They can differ.
- **Products belong to several groups.** An item can be in Mugs and in Novelty Items at the same time, so totals by product group overlap and must not be added up.
- **Customer attributes are today's values.** Category, buying group and territory are the stored values now, not the values at the time of each order.
- **Backorders keep the original date.** A backorder keeps the original order's creation date, so backorders do not show up as "new" orders in a later month.
- **It is a snapshot.** The data is the stored state at 31 May 2016. There is no history of what was open at the end of April.
- **The data is simulated.** No column records a reason for anything (why late, why short). The data can show *where* something is concentrated, never *why*.

## 3. How v1 was built (by the data agent)

1. **Copied out of SQL Server.** The data was extracted from the WideWorldImporters database on the Windows machine `DESKTOP-K46JKQF` (SQL Server 2016 Evaluation), read-only. The agent made two failed attempts, then succeeded in a quiet window, with row counts checked before and after. This gives a stable copy, but not a certified point-in-time snapshot.
2. **Saved in portable formats.** Every table was saved as Parquet with exact types: decimals stay exact, and SQL Server's 7-digit timestamps are kept with an extra column. A DuckDB database was built from the Parquet files.
3. **Checked against the source.** 205 checks compared row counts, keys and types with SQL Server.
4. **Tested every metric idea against the raw data,** with an independent calculation, and gave each a verdict: verified, candidate, rejected or blocked (section 4).
5. **Wrote the Application Contract,** the "description of the app" the agent reads (`catalog/`):
   - 3 pages (Overview, Fulfilment, Supply) and 7 detail pages;
   - 10 widgets, 13 filters, 12 metric definitions and 6 charts;
   - all validated against schemas.
6. **Built a local read-only app and API.** The API runs only named, pre-written queries; it never runs free-form SQL. It returns the filters it actually applied, and rejects invalid requests with an error instead of ignoring them.
7. **Added one synthetic test case,** `no_incoming_v1` (section 6).
8. **Wrote 30 test tasks:** 12 for development and 18 held back for final scoring.
9. **Ran checks:** 277 metric checks, 31 API checks, and a moved-folder offline rebuild test. The Windows Python runtime is bundled, so the package runs with no installation.

## 4. The metrics (measures)

A **measure** is a named calculation with a fixed definition, unit and date basis. A **filter** narrows which rows it covers (a customer, an item, a period). A **figure** is a number in an answer, and every figure must trace back to a measure.

### All measures and their status

| ID | Name | Plain definition | Example | v1 status | v2 status |
|---|---|---|---|---|---|
| **M01** | Orders created | Count of distinct orders created in the period (includes backorders) | May 2016: 2,047; April: 1,951 | ✅ Verified | ✅ Verified |
| **M02** | Unpicked units | Units ordered but not yet picked: sum of max(ordered − picked, 0) | May-created orders: 17,710; all history: 360,276 | ✅ Verified | ✅ Verified |
| **M03** | Orders with unpicked units | Distinct orders with at least one line still unpicked | May: 161; all history: 3,085 | ✅ Verified | ✅ Verified |
| **M04** | Stock and reorder level | Per item: on hand, reorder level, target level (undated) | Item 80: 20 on hand, reorder at 5 | ✅ Verified | ✅ Verified |
| **M05** | Incoming units | Cartons not yet received × units per carton, on open purchase lines | Item 80: 21,972 | ✅ Verified | ✅ Verified |
| **M12** | Orders by customer category | M01 grouped by the customer's current category | Novelty Shop: 52,547 of 73,595 | ✅ Verified | ✅ Verified (any measure can now be grouped by category) |
| **M13** | Ordered units | Sum of quantity ordered | – | – (did not exist) | ✅ Verified (**new in v2**) |
| **M06** | Time to pick | Median time from order date to picking completed | 11 hours median | 🟡 Candidate | 🟡 Candidate |
| **M08** | Delivery confirmation lateness | Share of invoices confirmed after the expected date | 6.35% overall; April 6.25%, May 5.74% | 🟡 Candidate | 🟡 Candidate |
| **M09** | Open lines at a past date | Estimated lines still open on 1 Apr / 1 May / 1 Jun | 2,942 / 3,041 / 3,147 | 🟡 Candidate (approximation) | 🟡 Candidate |
| **M07** | Supplier lateness | Purchase lines received after the expected date | 0 of 8,358 | ❌ Rejected | ❌ Rejected |
| **M10** | Invoiced sales (revenue) | Sum of (extended price − tax) on invoice lines | All history: 172,261,341.20 | ⛔ Blocked | ⚠️ **Published with a caveat** (my decision; see 5.5) |
| **M11** | Recorded profit | Sum of recorded `LineProfit` | All history: 85,729,180.90 | ⛔ Blocked | ⚠️ **Published with a caveat** (my decision) |

### What the statuses mean

- **Verified:** the definition is unambiguous, two independent calculations agree, and the number means what its name says. The agent may use it.
- **Candidate:** it can be computed, but has a known weakness that could mislead. It is kept in the evidence but not shown in the app.
- **Rejected:** the data makes it meaningless, for example a value that is always zero.
- **Blocked:** the arithmetic is right, but part of its *meaning* cannot be proven from the data.

## 5. Why some metrics are blocked, rejected or held back

The data agent followed one rule: **show a number only if every part of its meaning is proven by the data.** A wrong-but-confident number is the exact failure our project argues against, since judges will see the agent's figures. So the rule is deliberately strict.

### 5.1 M07 supplier lateness: rejected

Of the 8,358 fully received purchase lines, **zero** were received after their expected date. The simulator always delivers on time. A chart of zero is useless, and it would invite the false conclusion "suppliers are perfect". **The data caused this, not a choice.**

### 5.2 M06 time to pick: candidate

The order date has no time of day (dates only), but picking completion has a full timestamp. So "hours to pick" is measured from midnight, not from when the order was placed. The median of 11 hours is an artefact of that, not real processing time. Incomplete orders are also excluded.

### 5.3 M08 confirmation lateness: candidate

It can be computed (4,470 of 70,426 invoices, 6.35%). But "expected delivery date" might not be the original promise, because backorders inherit dates, and there are no reasons recorded. It also shows lateness *fell* in May (5.74% vs 6.25%), so it can't support a "late deliveries rose in May" story. That's why the deck wording was changed. It could be promoted later with a clear label.

### 5.4 M09 open lines at a past date: candidate

The database stores only the current state. To know what was open on 1 May, you would need a full history of every pick, cancellation and amendment, and that history doesn't exist. The estimate (2,942 / 3,041 / 3,147) assumes lines are never edited. It is correct at the final date but unprovable for earlier dates. This is why the agent must never claim "the backlog grew in May".

### 5.5 M10 revenue and M11 profit: blocked in v1, published with a caveat in v2

- **The arithmetic is perfect.** All 228,265 invoice lines reconcile to the cent:
  - sales before tax: 172,261,341.20
  - tax: 25,782,098.25
  - total including tax: 198,043,439.45
  - recorded profit: 85,729,180.90
- **The currency is not stated anywhere.** There is no currency column, and Microsoft's documentation says only that the company and all its customers are in the US. Labelling the figures "$" would be an assumption.
- **"Profit" is gross line profit.** It is the profit recorded per invoice line, before overheads, not the company's net profit.

**What I changed in v2:** I published both, with honest labels: "sample amount (currency not stated in source)", and "recorded gross line profit, not net profit". The brief explicitly mentions revenue, and judges will almost certainly ask "what were our sales?". Answering "not available" undersells the demo, and the label keeps it honest. **This was my call and is still yours to confirm.** To revert, set `M10` and `M11` to `"status": "blocked"` in `catalog/analysis_measures.json`. v1's original endpoint still hides money, as v1 decided.

## 6. The synthetic test case (`no_incoming_v1`)

The real data has no example of "customers are waiting for an item and **no** supply is coming", which is an important branch for the agent. So the data agent added one clearly labelled fake case, kept separate from the real data:

- Item **1227**, labelled "SYNTHETIC investigation item — no incoming supply", with supplier Fabrikam (4).
- Order **74595** for customer 11: 120 units ordered, 0 picked.
- 20 units in stock, and no purchase orders.

Every fake record carries `IsSynthetic = true`. Choosing this scenario shows **only** the fake records, not real data plus fake. The fake case records no reason for the missing supply, so the agent must not invent one.

## 7. What I (Claude) changed: v1 → v2

### What did not change

- All 21 data tables are byte-identical.
- Every v1 page, API route and file still works. All v1 checks (205 data, 277 metric, 31 API, Contract) pass against v2.

### What was added

1. **One flexible analysis call** (`/api/analyze`). Any measure (M01, M02, M03, M05, M10, M11, M13) can be:
   - **broken down** by month, customer, customer category, buying group, state, sales territory, salesperson, item, supplier or product group;
   - **compared** across two periods, returning both totals, the change, the % change, and each group's share of the change;
   - **sorted** and cut to a top N, with an "All others" row so totals still add up.
2. **Five new filters:** customer category, buying group, state, sales territory and salesperson.
3. **Name lookup** (`/api/resolve`): "Litware" becomes supplier 7. Ambiguous names are flagged rather than guessed: "Hudson" is two salespeople, and "Tailspin Toys" is a buying group and also 200 store names.
4. **Linked records** (`/api/related`): one call returns everything connected to a customer, order, item, supplier, purchase order or salesperson, plus suggested next steps.
5. **New Contract documents:**
   - a glossary mapping business words to measures; "open orders" is flagged as needing a question back, and "why did…" gets an honest "can't tell";
   - a map of how records link, with the traps listed;
   - 8 step-by-step investigation playbooks;
   - tool definitions an LLM can use directly.
6. **An Analysis page** in the app, with drill-in buttons. The address reproduces the exact view.
7. **Test material:**
   - 46 multi-step task chains (31 for development, 15 held back) and 218 labelled single questions. The expected answers come from a **separate implementation** that reads the raw files with its own code and never saw the engine.
   - A search test: 293 pages (30 real, 263 realistic decoys) and 150 questions, plus a simple baseline. The baseline picks the right real page first only 41% of the time.
8. **Linux scripts:** `setup_linux.sh`, `launch.sh` and `rebuild.sh`.

### Decisions and fixes worth knowing

- **Money published with a caveat** (5.5). This is a reversible decision.
- **Scenario rule:** the separate answer key had treated the synthetic scenario as real data plus the fake item. I kept v1's documented rule (fake records only), corrected 2 expected answers, and logged the correction in `evaluation/v2/freeze.json`.
- **A bug the answer key caught:** my engine sorted tied rows by ID as text ("10" before "2"). Fixed.
- **`pct_change`** is a percentage, for example 4.92 (meaning 4.92%).
- **v2 checks:** 310 of 310 pass, the engine matches the independent answer key on 276 of 276 graded steps, and a clean Linux install from scratch passes everything.

## 8. Facts you can safely use (the story)

- Orders created: April 1,951 → May 2,047, **+96 (+4.92%)**.
- That rise is concentrated in the **Great Lakes** territory (+65, 68% of the change), then Mideast (+23) and Southwest (+19). By salesperson, Sophia Hinton is the largest (+35).
- Orders created in May with units still unpicked: **161 orders, 17,710 units**. Across all history: 3,085 orders and 360,276 units. Almost all of these (3,080 orders) are backorders.
- Item 80 (a t-shirt) from Fabrikam:
  - 20 units in stock;
  - 21,972 units still unpicked;
  - purchase order 2073 is bringing 1,831 cartons × 12 = 21,972 units, an exact match.
- Item 193 (packing tape) from Litware: purchase order 2074 is bringing 2,804 cartons × 24 = 67,296 units, again matching the unpicked demand.
- Only 9 purchase lines are open, on purchase orders 2073 and 2074, all expected on 20 June 2016. Only Fabrikam and Litware have open demand or incoming supply.
- **Approved one-line claim:** "Orders created in May with quantities still unpicked, traced to holdings, related incoming supply and supplier, in the stored sample state."

**Do not claim:**
- late deliveries rose;
- the backlog grew;
- suppliers failed;
- any cause;
- net profit;
- a currency.

## 9. Where things are (v2 package)

| Path | What |
|---|---|
| `data/raw/*.parquet` | The 21 tables |
| `data/synthetic/no_incoming_v1/` | The fake test case |
| `data/wwi.duckdb` | Database rebuilt from the Parquet files |
| `catalog/` | The Application Contract: measures, analysis_measures, filters, dimensions, glossary, graph, playbooks, operations, views, widgets, charts; `retrieval/pages.json` |
| `scripts/engine.py`, `analysis_v2.py` | Query engines (v1 and v2) |
| `scripts/serve_v2.py` | App and API server |
| `scripts/oracle_v2.py` | The independent answer key |
| `scripts/validate*.py`, `check_tasks_v2.py` | Checks |
| `evaluation/` (v1), `evaluation/v2/` | Test tasks, expected answers, freeze hashes |
| `reports/findings.md` | The data agent's full report (v1) |
| `evidence/` | Logged query results and validation outputs |
| `docs/V2_SPEC.md`, `docs/WHATS_NEW_V2.md` | v2 exact specification and summary |
