# Real ERP or our own WWI app? A data and API comparison

*Prepared 9 Oct 2026 for KLE Tech Hackfest 2026, Domain 5A (Context-Aware Application Agent).*

## How this was done, and what to trust

- **Repositories inspected:** the source of all five candidates, at their current default branch:

  | System | Commit | Date |
  |---|---|---|
  | Bigcapital | `0ca638f` | 9 Oct 2026 |
  | IDURAR | `e935dec` | 14 Aug 2026 |
  | metasfresh | `c5d976e` | 9 Oct 2026 |
  | OpenBoxes | `d389a10` | 8 Oct 2026 |
  | ERPNext | `d5b6f7e` | 9 Oct 2026 |
  | Frappe | `2d6ef5f` | — |

- **Where the clones are:** `/tmp/claude-1001/-home-dheeraj-Agentic-Hackathon/7641398a-3fbe-4651-8b33-c19f8a1e19c8/scratchpad/erp_src/<name>`. They are shallow, blobless clones. That directory is session scratch space, so re-clone if you need the files later.
- **We built and ran nothing.** We installed nothing, ran no ERP code and no Docker. Every finding comes from reading schema files, controllers, `package.json` files and Docker Compose files, plus the official docs and the GitHub API.
- **The hour estimates and load speeds are judgement calls.** We measured none of them. Treat them as ±50%.
- **Evidence paths** are relative to each repository's root. An "M/" prefix is a shorthand for a migrations folder, defined in that ERP's section.
- **Some spot-checks were re-verified by hand:**
  - IDURAR's model list and licence.
  - Bigcapital's module list, throttle default and Swagger setup.
  - ERPNext's Sales Analytics options and demo data.
  - metasfresh's seed URL and React version.
  - OpenBoxes' React version and GSP page count.

---

## 1. The short answer

1. **No candidate ships data you could analyse.**

   | ERP | Shipped data |
   |---|---|
   | ERPNext | 3 customers and 5 sales orders |
   | Bigcapital | Import templates of fake text |
   | OpenBoxes | Opening stock with no transactions |
   | metasfresh | A German base database; we could not open it, and no sales history is indicated |
   | IDURAR | Nothing |

   Whatever you choose, **WWI stays the business data.** The only real question is which app sits on top of it.
2. **On how well the data model fits, ERPNext is the clear winner.** It natively covers the following, which none of the other React candidates covers as well:
   - Customer Group, Territory and Sales Person (all trees), with a Sales Team on orders.
   - Picked qty and delivered qty on order lines.
   - Bin stock and reorder levels.
   - Purchase lines in cartons, with a conversion factor.

   It also has a reporting RPC that already does breakdowns by month or by territory, and filters that live in the URL.
3. **On API hygiene, Bigcapital is the clear winner.** It has Swagger/OpenAPI, API keys, a Postman workspace, and P&L reports with built-in previous-period and previous-year comparison. **But it has no sales orders, purchase orders, picking, reorder levels, salespeople or customer groups.** About half of the WWI story would disappear in it.
4. **Three candidates should be dropped.**
   - **IDURAR:** the open-source version has been cut down to Client, Invoice and Payment, and HEAD looks broken.
   - **OpenBoxes:** it is a humanitarian supply-chain system with no notion of sales or revenue. It runs on Java 8 and its pages are mostly server-rendered GSP.
   - **metasfresh:** the model is excellent, but it needs PostgreSQL, RabbitMQ, Elasticsearch and two JVMs. Its filters live in server-side views that expire, not in the URL. Loading 3.5 years of history means opening accounting periods and running heavy document logic.
5. **The team is right that the WWI app is better for scoring.** It has an independent oracle, frozen held-out tasks and 276 of 276 steps matching. No ERP gives you that unless you load WWI into it and re-prove parity.

   The team is **wrong if it thinks the WWI app wins outright.** The brief describes "a no-code business application" whose metadata is "exported from the no-code platform". Frappe/ERPNext *is* a metadata-driven low-code platform, so it matches that wording better than a hand-built app. Its `/api/v2/doctype/<dt>/meta` endpoint and its report definitions *are* the "application metadata" input the brief describes.
6. **Recommendation: Option A (section 7).**
   - Keep the WWI app as the **scored benchmark**.
   - Port the same agent to **ERPNext through its REST/RPC API**, with a loaded **slice** of WWI (masters plus Jan–May 2016).
   - Show **parity** on the measures that survive the mapping.

   This proves the agent is not tailored to our own app, which is the client's "API-based agents" expectation, without risking the scored KPIs. Budget: about 35–55 hours.

---

## 2. The baseline: WWI data and our own app

Sources: `data/wwi-package-v2-2026-10-08/docs/DATASET_GUIDE.md`, `docs/V2_SPEC.md` and `app/`.

| Aspect | Our WWI package v2 |
|---|---|
| Data | 21 tables, 1 Jan 2013 to 31 May 2016. 663 customers, 73,595 orders, 231,412 order lines (ordered vs picked, backorder link), 70,510 invoices / 228,265 lines (tax, line profit), 227 items (holdings, reorder level, target level), 13 suppliers, 2,074 POs / 8,367 lines in cartons, 236,667 stock transactions, 9 sales territories, 10 salespeople |
| Ground truth | The independent oracle (`scripts/oracle_v2.py`) matches the engine on 276 of 276 graded steps. Tests: 31 dev and 15 held-out multi-step chains, 218 labelled utterances, and 150 retrieval queries over 293 pages (30 real, 263 decoys) |
| API | `POST /api/analyze`, `/api/resolve`, `/api/related`; `GET /api/contract`. Invalid requests return 422 and are never silently ignored. Every response echoes what was applied and returns a deep link. There is no OpenAPI and no auth; tool schemas are in `catalog/operations.json` |
| Frontend | **Plain JavaScript, not React** (`app/app.js`, `app/analysis.js`). Hash routes put all state in the URL (`#/analysis?measure_id=..&group_by=..`). `window.wwiState` is already exposed. Charts are hand-drawn inline SVG, with no chart library |
| Run cost | One Python process and DuckDB (44 MB). Seconds to start |
| Weakness | Built by us, for our agent. A judge can ask: "Would this work on an app you didn't write?" It has only 4 top-level pages, while the brief talks about hundreds of pages and components |

---

## 3. Entity mapping: how each WWI concept lands in each ERP

Key: ✅ native · 🟡 partial or needs a workaround · ❌ missing.

| WWI entity | ERPNext | metasfresh | Bigcapital | OpenBoxes | IDURAR (HEAD) |
|---|---|---|---|---|---|
| Customers | ✅ Customer | ✅ C_BPartner (IsCustomer) | ✅ contacts (customer) | 🟡 destination Location | 🟡 Client (name, address string) |
| Customer categories | ✅ Customer Group (tree) | ✅ C_BP_Group | ❌ | 🟡 LocationGroup | ❌ |
| Buying groups | 🟡 custom field, or a second group level | 🟡 parent group or partner relation | ❌ | 🟡 Organization | ❌ |
| Sales orders and lines | ✅ Sales Order / Item | ✅ C_Order / C_OrderLine | 🟡 estimates or receipts only, no SO | 🟡 Requisition + Shipment | ❌ (removed) |
| Ordered vs picked qty | ✅ `qty`, `picked_qty`, `delivered_qty` | ✅ QtyOrdered/QtyDelivered and shipment schedule | ❌ single quantity | ✅ PicklistItem.quantityPicked | ❌ |
| Backorder link | 🟡 open qty on the same SO; link via custom field | 🟡 open qty on the same line | ❌ | ❌ | ❌ |
| Invoices and lines, with tax | ✅ Sales Invoice and taxes table | ✅ C_Invoice / Line / Tax | ✅ sales_invoices, items_entries, tax_rates | ❌ supplier side only | 🟡 one tax rate per invoice, free-text lines |
| Recorded line profit | 🟡 computed from valuation (will not match WWI) | 🟡 from cost detail | 🟡 FIFO/average COGS | ❌ | ❌ |
| Payments | ✅ Payment Entry | ✅ C_Payment | ✅ payment_receives | ❌ | ✅ Payment |
| Stock items | ✅ Item | ✅ M_Product | ✅ items (inventory) | ✅ Product | ❌ (removed) |
| Stock groups (many-to-many) | 🟡 single-parent Item Group tree | 🟡 single category | 🟡 single category | ✅ tags / productGroups | ❌ |
| Warehouse holdings | ✅ Bin (actual, ordered, reserved, projected) | ✅ MD_Stock / M_Storage | ✅ items_warehouses_quantity | ✅ ProductAvailability | ❌ |
| Reorder / target level | ✅ Item Reorder (level, qty) | ✅ M_Replenish (min, max) | ❌ | ✅ InventoryLevel (min, reorder, max) | ❌ |
| Stock transactions | ✅ Stock Ledger Entry | ✅ M_Transaction | ✅ inventory_transactions | ✅ Transaction / Entry | ❌ |
| Suppliers | ✅ Supplier / Supplier Group | ✅ C_BPartner (IsVendor) | ✅ contacts (vendor) | ✅ Organization | ❌ (removed) |
| Purchase orders | ✅ Purchase Order | ✅ C_Order (IsSOTrx = N) | ❌ (bills only) | ✅ Order (PURCHASE_ORDER) | ❌ |
| Units per carton | ✅ uom, conversion_factor, stock_qty | ✅ HU packing instruction / UOM conversion | ❌ | ✅ quantityPerUom / ProductPackage | ❌ |
| Receipts | ✅ Purchase Receipt | ✅ M_InOut | 🟡 bill with inventory | ✅ Receipt | ❌ |
| Salespeople | ✅ Sales Person tree + Sales Team | ✅ SalesRep_ID | ❌ (creating user only) | ❌ | 🟡 the `assigned` admin user |
| Sales territories | ✅ Territory tree | ✅ C_SalesRegion | 🟡 branches as a stand-in | ❌ | ❌ |
| **Native fit (of 20)** | **≈16 ✅** | **≈15 ✅** | **≈8 ✅** | **≈11 ✅ (sales side weak)** | **≈1 ✅** |

---

## 4. Each ERP in detail

### 4.1 ERPNext / Frappe (the backup option, and the strongest candidate)

**Data model.** Doctype JSON files under `erpnext/`:

- **Customer and groupings:**
  - `selling/doctype/customer/customer.json`
  - Customer Group: `setup/doctype/customer_group/customer_group.json`
  - Territory: `setup/doctype/territory/territory.json`
  - Sales Person: `setup/doctype/sales_person/sales_person.json`
  - Sales Team child table: `selling/doctype/sales_team/sales_team.json`
- **Sales Order Item fields:** `qty`, `conversion_factor`, `stock_qty`, `delivered_qty`, `picked_qty` and `billed_amt`.
- **Pick List:** `stock/doctype/pick_list/`.
- **Bin:** `stock/doctype/bin/bin.json` (`actual_qty`, `ordered_qty`, `reserved_qty`, `projected_qty`).
- **Item Reorder:** `warehouse_reorder_level` and `warehouse_reorder_qty`.
- **Purchase Order Item:** `uom`, `conversion_factor` and `received_qty`, which map WWI cartons exactly.
- **Gaps:**
  - Many-to-many stock groups (use tags or a custom child table).
  - The backorder link (use a custom field).
  - Recorded line profit: `accounts/report/gross_profit/gross_profit.py` recomputes it from valuation, so it will not equal WWI's `LineProfit`.

**Shipped data.**

- `erpnext/setup/demo.py` plus `erpnext/setup/demo_data/*.json`, triggered from a setup-wizard checkbox.
- It creates 3 customers, 3 suppliers, 10 items, 5 sales orders, 10 purchase orders and 5 payments, all within the current year. That is not enough for analytics.
- We found no working public demo: demo.erpnext.com returned 502. A Frappe Cloud trial is the realistic hosted route.
- The Data Import doctype (`frappe/core/doctype/data_import/`) takes CSV, XLSX or Google Sheets for any doctype, with "submit after import". It inserts one document at a time with full validation, so it is slow but correct.

**Server API.**

- **REST:** `/api/resource/<DocType>` accepts `fields`, `filters`, `group_by`, `order_by` and paging. Fields may be `count(...)`, `sum(...)` or `avg(...)` (`frappe/client.py:26`, `frappe/database/query.py`).
  - Example: "orders by territory by month" is one call against Sales Order.
- **v2:** `/api/v2/document/..`, `/api/v2/doctype/<dt>/meta` (field schemas, which is ready-made agent metadata), `/count`, and bulk update.
- **RPC:** `/api/method/<path>`.
- **Reports** run through `frappe.desk.query_report.run(report_name, filters)` and return columns, rows and a chart. Relevant built-in reports:
  - **Sales Analytics:** monthly, quarterly or yearly ranges, by Customer, Customer Group, Item, Item Group or Territory, but **not by Sales Person**.
  - **Gross Profit:** grouped by item, customer, territory, sales person, month and more.
  - **Stock:** Stock Balance, Stock Projected Qty, Stock Ageing.
  - **Orders:** Sales Order Analysis (pending qty and delay), Purchase Order Analysis.
  - **Receivables:** Accounts Receivable.
  - **Sales history:** Item-wise Sales History, Sales Person-wise Transaction Summary.
  - "Territory-wise Sales" is built on Opportunities, so it is not useful here.
- **No OpenAPI.** The `/meta` endpoint and an admin-only `/api/v2/discovery` stand in for it.
- **Auth:** `Authorization: token <key>:<secret>`, or a session or OAuth2.
- **Rate limit:** off by default (site config `rate_limit`).
- **Writes:** send `docstatus: 1` to submit a document.

**Frontend and VACP.**

- **Not React.** The Desk is Frappe's own JavaScript plus some Vue 3.
- **But it is the easiest to *drive*.** List views and query reports write their filters into the URL:
  - `/app/sales-order?status=To%20Deliver&customer=X`
  - `/app/query-report/Sales%20Analytics?tree_type=Territory&range=Monthly`

  (`frappe/public/js/frappe/list/base_list.js`, `views/reports/query_report.js`, `router.js`)
- **It exposes useful globals:** `frappe.set_route`, `frappe.route_options`, `cur_list`, `frappe.query_report.set_filter_value()` and `frappe.get_meta`.
- **Hook point:** a small custom Frappe app that declares `app_include_js = "vacp.bundle.js"` in `hooks.py`. `erpnext/hooks.py` uses the same mechanism. For a quicker demo, inject the script with Playwright `addInitScript` instead.
- Estimate: 1–2 days for a bridge that covers lists and reports.

**Run cost and licence.**

- `frappe_docker` `pwd.yml` (image `frappe/erpnext:v16.x`) runs:
  - MariaDB 11.8
  - Two Redis instances
  - Gunicorn, nginx and socket.io
  - Three workers and a scheduler

  It needs 4 GB of RAM at minimum; 8 GB is comfortable.
- **Pin v16.** The develop branch needs Python 3.14 and Frappe v17.
- **Licence:** ERPNext is GPL-3.0 and Frappe is MIT.
  - An agent talking over HTTP is a separate work.
  - A hosted demo is not "distribution" under GPL-3.0, unlike AGPL.

**Effort.**

| Task | Hours |
|---|---|
| (a) Run with demo data | 2–4 |
| (b) Full WWI load: engineering (company, fiscal years 2013–2016, tax template, trees, items with carton UOM, reorder levels, opening stock, custom fields) | 40–60 |
| (b) Full WWI load: run time, posting about 150k documents in date order | 5–15 |
| Slice: masters plus Jan–May 2016 (about 10k orders, at roughly 2,000 a month) | 15–25 |

For the slice, keep Sales Invoices as `update_stock = 0` and skip Delivery Notes to avoid stock-valuation ordering issues.

### 4.2 Bigcapital (best API, worst fit for an order-centric story)

**Data model.** M/ = `packages/server/src/database/tenant/migrations/`.

- Customers and vendors: M/`20200104232644_create_contacts_table.ts`
- Sales invoices: M/`20200715193633…`
- Line items: polymorphic, M/`20200722173423_create_items_entries_table.ts`
- Estimates: M/`20200713192127_create_sales_estimates_table.ts`
- Other tables: `bills`, `warehouses`, `items_warehouses_quantity`, `inventory_transactions`, `inventory_cost_lot_tracker`, `tax_rates` and `branches`.
- **`packages/server/src/modules/` contains no SalesOrders, PurchaseOrders, UOM or reorder module.** We verified this. It is a double-entry accounting product.

**Shipped data.**

- No demo dataset. The tenant seeds create only the chart of accounts, roles and tax rates.
- `packages/server/static/demo-sheets/*.csv` are import templates, for example 48 fake invoices, all from April 2024.
- An import wizard (`modules/Import/Import.controller.ts`) handles customers, vendors, items, invoices, bills, payments and more. Each file is limited to 5 MB and runs as one transaction.

**Server API.**

- **REST** under `/api` (`packages/server/src/main.ts:19`), with **Swagger at `/swagger`** (`main.ts:30-31`) and public docs at https://docs.bigcapital.app/api-reference.
- **Auth:** a Bearer JWT plus an `organization-id` header, or `bc_…` API keys.
- **Reports** live at `/api/reports/*`:
  - P&L and balance sheet: `fromDate` and `toDate`, `displayColumnsBy=day|week|month|quarter|year`, `previousPeriod` and `previousYear` change columns, and a filter by branch.
  - Sales-by-items and purchases-by-items.
  - Inventory valuation and inventory item details.
  - Receivable and payable aging.
  - Customer and vendor balances.
- **Sales-by-items has no month grouping and no customer filter.**
- **Throttle:** 300 requests per minute globally by default, through Redis (`packages/server/src/common/config/throttle.ts`). `THROTTLE_GLOBAL_LIMIT` changes it.
- **No bulk create.**
- **Each organisation gets its own MySQL database.**

**Frontend and VACP.**

- Stack: React 18.2, Vite 5, react-router 5.3, Redux 4 with RTK, TanStack Query 5, and Blueprint 4. **There is no chart library.**
- **Report pages keep every filter in the URL** through `useAppQueryString`, for example `/financial-reports/profit-loss-sheet?fromDate=…&displayColumnsBy=month&previousYear=true`. List pages keep table state in Redux.
- **Hook point:** a `<VacpBridge>` inside `<Router>` in `packages/webapp/src/components/App.tsx`, using `history`, the store and `queryClient`. Estimate: 6–10 hours.
- Of the ERPs, this is the most "VACP-native" React frontend.

**Run cost and licence.**

- `docker-compose.prod.yml` runs:
  - Envoy, the webapp and the server (images on Docker Hub)
  - MariaDB and Redis
  - Gotenberg and Garage S3
  - ClickHouse (optional)

  Estimate: 2–3 GB of RAM.
- **AGPL-3.0.** Injecting a bridge into the webapp and exposing it on a network obliges you to offer that modified source. A public fork satisfies this.

**Effort.**

| Task | Hours |
|---|---|
| (a) Run, with no meaningful data | 2–4 |
| (b) Load WWI | 20–35 |

The load is **very lossy**. You lose purchase orders, picking and backorders, cartons, reorder levels, salespeople, categories, buying groups and stored profit, and territories survive only as branches. About 70k invoices at the default throttle take more than 4 hours. Backdated postings also set off inventory-cost recomputation.

### 4.3 metasfresh (a rich model with a heavy footprint)

**Data model.** This is ADempiere lineage; tables are confirmed in `backend/de.metas.adempiere.adempiere/base/src/main/java-gen/org/compiere/model/I_*.java`.

| Area | Tables |
|---|---|
| Partners, orders, invoices | C_BPartner, C_BP_Group, C_Order, C_OrderLine (QtyOrdered, QtyDelivered, QtyReserved, QtyInvoiced), C_Invoice, C_InvoiceLine, C_InvoiceTax |
| Shipping, picking, stock | M_InOut, `M_ShipmentSchedule` (picking and open qty), M_Replenish (Level_Min/Max), M_Transaction, MD_Stock |
| Territories and salespeople | C_SalesRegion, SalesRep_ID |
| Cartons | `M_HU_PI_Item_Product.Qty` (units per carton, in `backend/de.metas.handlingunits.base/...`) |
| Gaps | Backorders are open qty on the same line, so there is no link. Product categories are single-parent. Invoice lines carry no profit |

**Shipped data.**

- `docker-builds/Dockerfile.db-init` downloads the base dump `https://metasfresh.com/wp-content/releases/db_seeds/metasfresh-5_172_gh24566.pgdump` (28 MB). It is German-first, with a "Hauptlager" warehouse.
- **We could not open it to confirm whether it has any transactions.** The docs start with a "set up my company" wizard, which suggests it does not.
- No public demo.
- An import framework exists: `I_BPartner`, `I_Product`, `I_Order`, `I_Replenish`, and `POST /api/v2/import`.

**Server API.**

- **The UI's own REST API** (`/rest/api`, session login) is the useful one for analytics. It has Swagger through springfox:
  - `POST /documentView/{windowId}` creates a filtered view.
  - `GET …/{viewId}?orderBy=` reads it.
  - `/menu` returns the full navigation tree.
  - `/dashboard/kpis` reads KPIs, whose datasource can be SQL or Elasticsearch.

  Source: `backend/de.metas.ui.web.base/.../view/ViewRestController.java`.
- **The business API `/api/v2`** (token auth) is mostly writes: upsert partners, sales order candidates, purchase orders, receipts and invoice candidates. It has almost no aggregate reads.
- No rate limit was found.

**Frontend and VACP.**

- Stack: React 16.14, Redux 4.1 with RTK, react-router 5 and d3 (`frontend/package.json`).
- The UI is **metadata-driven** (windows, tabs, fields and filter descriptors all come from the server). In principle you could generate VACP capabilities for every window from one adapter.
- **But the URL holds only `viewId`, `page` and `sort`.** Filters sit in server-side views that expire (`frontend/src/containers/DocumentListContainer.js`), so deep links do not survive a restart.
- **Hook point:** the Redux store. `frontend/src/index.jsx` already sets `window.store` under Cypress.

**Run cost and licence.**

- `docker-builds/compose/compose.yml` runs PostgreSQL 15, RabbitMQ 3.9, Elasticsearch 7.17, two Java services and nginx. Expect 5–7 GB of RAM.
- **GPL-2.0** (`backend/LICENSE.md`).

**Effort.**

| Task | Hours |
|---|---|
| (a) Run | 3–6 |
| (b) Load WWI through the API | 24–40, plus slow document processing |
| (b) Load WWI by direct SQL | 12–20, leaving schedules, accounting and the Elasticsearch index inconsistent |

You must also create and open accounting periods for 2013–2016 first.

### 4.4 OpenBoxes (supply chain, not sales)

**Data model.** 119 Grails domain classes are under `grails-app/domain/org/pih/warehouse/`, with 360 Liquibase changelogs in `grails-app/migrations/`.

- **The purchase side maps well.**
  - `Order` with type PURCHASE_ORDER.
  - `OrderItem.quantityPerUom`, which holds the units per carton.
  - Receipts.
  - `InventoryLevel` (min, reorder and max).
  - `Transaction` / `TransactionEntry`.
  - `PicklistItem.quantityPicked`.
- **There are no customers.** Destinations are `Location` rows.
- **There are no customer invoices.** `dom/invoice/Invoice` is supplier-side.
- **No salespeople, territories, tax or profit.**
- **No backorder link.**

**Shipped data.**

- A configuration wizard loads 58 medical products, 18 locations and opening stock, with **no orders**.
- There is a hosted demo at https://demo.openboxes.com/openboxes, with self-signup.
- XLS and CSV imports exist, through `BatchController` and `/api/bulkData/import`.

**Server API.**

- About 220 `/api/...` routes are defined in `grails-app/controllers/org/pih/warehouse/UrlMappings.groovy`.
- **No OpenAPI.** There are Markdown docs in `docs/api-guide/`.
- **Auth:** a session cookie, plus a session-bound "current location".
- **Dashboards** (`/api/dashboard/*`) cover fill rate, stock-outs, inventory value, expiry and delayed shipments.

**Frontend and VACP.**

- Stack: React 16.8.6, Redux 4, react-router 5 and chart.js 2.
- **620 `.gsp` files.** Most pages are server-rendered.
- React list pages sync their filters to the query string. GSP pages reload the whole page, so a bridge must re-attach on every load. Difficulty: medium-high.

**Run cost and licence.**

- **Java 8 only** (Grails 3.3), with MariaDB or MySQL. An official image exists: `ghcr.io/openboxes/openboxes`.
- RAM: 4 GB or more.
- **EPL-1.0.**

**Effort.**

| Task | Hours |
|---|---|
| (a) Run | 2–4, but the analytics stay empty |
| (b) Load WWI | 30–50; customers, invoices and money are lost |

It cannot answer "what were our sales?" at all.

### 4.5 IDURAR ERP/CRM (drop it)

- **The open-source edition has been hollowed out.**
  - `backend/src/models/` at HEAD contains only `Client`, `Invoice` and `Payment`, plus the core models (verified).
  - Inventory, Supplier, Product, Order, Purchase and Quote were deleted between May 2024 and July 2025, in commits `b6e06ab4`, `50a71c72` and `3518aee2`.
  - The README points to a paid "Entreprise" edition.
- **HEAD looks broken.**
  - `backend/src/setup/setup.js` requires the deleted `PaymentMode` and `Taxes` models.
  - `frontend/src/router/routes.jsx` references `<Quote/>` and `<Taxes/>` without importing them.
- **Its "summary" endpoints ignore dates.** The date `$match` is commented out, so "this month" labels show all-time totals.
- **No demo data, no Docker, no OpenAPI.** Lists accept only a single exact-match filter.
- **Licence:** HEAD is AGPL-3.0 (verified), but `backend/package.json` still says "Fair-code License". Before Sept 2024 it was "IDURAR License 1.0", which bans SaaS use, so avoid older tags.
- Stack: React 18.3, RTK 2 and antd 5. It would be easy to bridge, but there is nothing in it worth bridging.

---

## 5. Comparison against our WWI app

Scores run from 1 (poor) to 5 (strong). The WWI-app column assumes our own package. Each ERP column assumes **WWI loaded into it**, because the shipped data is useless everywhere.

| Axis | WWI + our app | ERPNext | Bigcapital | metasfresh | OpenBoxes | IDURAR |
|---|---|---|---|---|---|---|
| **Analytical richness of the data**, as loaded | **5.** Everything in WWI, curated with traps documented | **4.** Most of WWI survives. Profit is recomputed; stock groups and backorder links are lossy | **2.** Invoices, payments and stock only | **4.** Similar to ERPNext | **2.** Purchase and stock side only | **1** |
| **Ground-truth verifiability** | **5.** Independent oracle, frozen holdout, 276/276 | **3.** The oracle still applies to M01, M13, M10, M04 and M05 after the load. M11 and backorder chains will not match | **2.** Only invoice totals | **2.** Heavy document logic changes what you loaded | **2** | **1** |
| **API quality for an API-based agent** | **3.** Purpose-built and strict, but narrow, with no auth and no OpenAPI | **4.** Generic REST with group_by and sum, a report RPC, metadata endpoints and token auth. No OpenAPI | **4.** OpenAPI, API keys, reports with period comparison. But reports have no customer or month breakdown, and it is throttled | **3.** Swagger, but the view API is stateful and the business API is write-oriented | **2.** Session cookie and location context, no OpenAPI | **1** |
| **VACP feasibility** | **5.** We own the code, state is already in the URL, `window.wwiState` exists (but it is not React or Vega-Lite) | **3.** Not React, but globals plus URL filters plus an official script hook | **4.** React 18; report filters are in the URL | **3.** React, but filters live in expiring server views | **2.** Mostly GSP | **2** |
| **Credibility as a "real app"** | **2.** Self-built, 4 pages | **5.** A widely used ERP, metadata-driven, closest to the brief's "no-code platform", with hundreds of doctypes and reports | **3.** A real product, but accounting only | **4.** A real ERP, less known | **3.** A real system, wrong domain | **1** |
| **Setup risk** (low risk scores high) | **5** | **3.** Docker is easy; the load is the risk | **3** | **1** | **2** (Java 8) | **2** (broken HEAD) |

**How to read it.**

- **No ERP beats our app on ground truth or setup risk.**
- **ERPNext beats our app on credibility and on how general its API is.** That is exactly what the client is asking for.
- **Bigcapital beats ERPNext on API documentation and React,** but loses on the data, which is what the analytics in this project depend on.

---

## 6. VACP notes that apply to every option

- **Licence.** The VACP repository (https://github.com/ETH-IVIA-Lab/VACP) has **no LICENSE file**. The GitHub API reports `license: null`, and `package.json` is `"private": true`. Legally, that means all rights are reserved.
  - Re-implement the *interface* (`getCapabilities`, `getState`, `execute`, as described in `docs/reference/tool-contract.md` and arXiv 2603.29322) in our own code. Do not vendor their packages.
  - Alternatively, ask the authors.
- **Providers.** The only providers that exist are Vega-Lite and vgplot/Mosaic (`packages/lib/providers/`), and `@vacp/core` has no React dependency.
  - **None of the five ERPs, and not our own app, uses Vega-Lite**, so every bridge will be custom.
  - The cheapest way to show "real" VACP is to render our own app's charts with Vega-Lite. VACP also has a DuckDB data-handle package, `@vacp/duckdb`, and our data is already in DuckDB.
- **Deep links decide how well the after-action check works.** Our app, ERPNext (lists and reports), Bigcapital (reports) and OpenBoxes (React lists) all put filters in the URL. metasfresh and IDURAR do not.

---

## 7. Solution options

### Option A: our app is the scored benchmark, plus ERPNext through its API as a generality demo (recommended)

**What we build**

1. **Keep the WWI app and evaluation exactly as they are.** All KPI numbers are reported from it.
2. **Put an adapter interface behind the agent,** with tools such as `navigate`, `set_filters`, `query_measure`, `read_state` and `resolve`. Today's WWI tools become adapter #1.
3. **Run ERPNext v16** with `frappe_docker` `pwd.yml`.
4. **Load a WWI slice** through Data Import or the REST API:
   - All masters: 663 customers, groups, territories, 10 sales persons, 227 items with carton UOM and reorder levels, 13 suppliers.
   - Opening stock.
   - **Jan–May 2016** orders, invoices and POs. That is roughly 10k orders, at about 2,000 a month.
   - Custom fields for `buying_group`, `wwi_backorder_of` and `wwi_line_profit`.
5. **Write adapter #2 against ERPNext:**
   - `/api/resource` with `group_by` and `sum`.
   - `query_report.run` for Sales Analytics, Gross Profit, Stock Projected Qty and Purchase Order Analysis.
   - `/api/v2/doctype/<dt>/meta` to build the page and filter catalogue automatically.
6. **Run the dev and holdout chains that the slice can answer.** For example, May vs April orders by territory gives Great Lakes +65. Report **parity with the oracle** as a separate "transfer" table.
7. **Optional stretch:** a `window.__vacp` script injected into Desk with Playwright `addInitScript`, mapping `execute` onto `frappe.set_route` and `query_report.set_filter_value`.

**Effort**

| Step | Hours |
|---|---|
| Docker setup | 3–4 |
| Slice load | 15–25 |
| Adapter | 10–15 |
| Parity runs | 4–6 |
| Bridge stretch | 8–12 |
| **Total** | **about 35–55** (25–40 without the bridge) |

**Risk: medium, and contained.**

- If the ERPNext load slips, the scored submission is untouched. We demo ERPNext with fewer documents and say so honestly.
- Two specific risks:
  - Valuation-based profit will differ, so show M10 sales but not M11 profit in ERPNext.
  - Sales Analytics cannot group by Sales Person, so use Gross Profit grouped by Sales Person, or a `group_by` on the Sales Team table.

**What it proves**

- KPIs measured against independent ground truth.
- The same agent works on a real, metadata-driven ERP through its server API.
- The Contract and metadata layer generalises, because ERPNext's catalogue is generated from `/meta` rather than hand-written.
- This answers the judges' "did you build the app for the agent?" question and the client's "API-based agents" expectation.

### Option B: move entirely to ERPNext, with all of WWI loaded

**What we build**

- Load all 3.5 years: about 150k submitted documents, in date order.
- Re-point the whole agent and the KPIs at ERPNext.
- Rebuild the evaluation answer key against ERPNext, with the oracle used to validate the load.

**Effort:** 60–90 hours, including 5–15 hours of unattended load time and the debugging of re-posting.

**Risk: high.**

- One valuation or fiscal-year mistake means a reload.
- M11 profit and the backorder chains no longer match the oracle.
- We would lose the frozen-holdout story we already have.

**What it proves:** the strongest "real app" credibility. It is not worth it before the deadline unless the team has two people free for a week.

### Option C: our app only, hardened to look like an enterprise API

**What we build**

- Publish an OpenAPI 3 spec generated from `catalog/operations.json`.
- Add token auth and paging.
- Switch the charts to Vega-Lite.
- Implement `window.__vacp` natively, with `getCapabilities` from the Contract, `getState` from `wwiState`, and `execute` mapped to routes and filters.

**Effort:** 15–25 hours. **Risk:** low.

**What it proves:** the best KPIs and the cleanest VACP demo. It is still open to "it only works on your own app", and it ignores the client's preference for a real API.

### Alternatives considered and rejected

- **Bigcapital as adapter #2** in place of ERPNext. Choose it only if the client weights a documented OpenAPI and a React UI above data fit. Its parity would be limited to invoiced sales (M10) and stock. About 30–45 hours, AGPL obligations included.
- **metasfresh:** the right model, but the wrong run cost and the wrong deep-link behaviour for a hackathon.
- **OpenBoxes and IDURAR:** a domain mismatch and a hollowed-out codebase respectively.

---

## 8. Recommendation

**Choose Option A, and fold in Option C's cheap parts:** the OpenAPI spec for our own API, Vega-Lite charts, and the native `__vacp` bridge on our app.

The reasoning, plainly:

- **Our app wins on what the KPIs measure:** ground truth, failure honesty and deep links.
- **ERPNext wins on what the judges and the client will question:** whether it is a real app, whether it uses a real API, and whether the metadata comes from a platform.

Holding both, with a parity table between them, turns the weakness of each into evidence. Build the ERPNext load on a **slice**, not the full history: the extra 2013–2015 data adds load risk and no new kind of question.

If the team must pick **only one** platform, keep our WWI app (Option C). Our app is better for scoring the agent, but the team should not tell judges it is "as realistic as an ERP".

---

## 9. Facts most likely to surprise the team

1. **Every candidate needs WWI loaded.**
   - ERPNext's demo is 3 customers and 5 sales orders in the current year.
   - Bigcapital's is a set of fake-text import templates.
   - OpenBoxes has opening stock only.
   - IDURAR has nothing.
   - metasfresh's seed is a German base database, and its docs suggest no sales history.
2. **Two shortlisted "ERPs" cannot represent the WWI story at all.**
   - IDURAR's open-source code now has only Client, Invoice and Payment, and HEAD looks broken.
   - Bigcapital has no sales orders, purchase orders, picking, reorder levels or salespeople.
3. **VACP has no licence.** Its only chart providers are Vega-Lite and Mosaic, and our own app is plain JavaScript with SVG charts, not React or Vega-Lite. So "VACP on React" is not automatically easier on any candidate. We must write the bridge ourselves in every case.

Also worth knowing:

- ERPNext's Sales Analytics cannot break down by Sales Person.
- ERPNext recomputes gross profit from stock valuation, so WWI's recorded profit will not match.
- Bigcapital throttles at 300 requests per minute by default.
- metasfresh will refuse to complete 2013–2016 documents until those accounting periods are created and opened.

---

## 10. Evidence index

| Topic | Where |
|---|---|
| ERPNext doctypes | `erpnext/selling/doctype/{customer,sales_order,sales_order_item,sales_team}/`, `erpnext/setup/doctype/{customer_group,territory,sales_person}/`, `erpnext/stock/doctype/{bin,pick_list,item_reorder,uom_conversion_detail}/` |
| ERPNext demo data | `erpnext/setup/demo.py`, `erpnext/setup/demo_data/*.json` |
| ERPNext reports | `erpnext/selling/report/sales_analytics/`, `erpnext/accounts/report/gross_profit/gross_profit.py`, `erpnext/stock/report/stock_projected_qty/`, `erpnext/buying/report/purchase_order_analysis/` |
| Frappe API | `frappe/client.py` (get_list group_by), `frappe/api/v2.py`, `frappe/desk/query_report.py`, `frappe/rate_limiter.py`, `frappe/core/doctype/data_import/` |
| Frappe URL filters and hooks | `frappe/public/js/frappe/list/base_list.js`, `frappe/public/js/frappe/views/reports/query_report.js`, `frappe/public/js/frappe/router.js`; `erpnext/hooks.py` (`app_include_js`); https://github.com/frappe/frappe_docker (`pwd.yml`) |
| Bigcapital | `packages/server/src/main.ts` (Swagger, `/api`), `packages/server/src/common/config/throttle.ts`, `packages/server/src/modules/` (no order modules), `packages/server/src/modules/FinancialStatements/`, `packages/server/src/modules/Import/`, `packages/server/static/demo-sheets/`, `packages/webapp/src/components/App.tsx`, `docker-compose.prod.yml`, https://docs.bigcapital.app/api-reference |
| metasfresh | `docker-builds/Dockerfile.db-init` (seed URL), `docker-builds/compose/compose.yml`, `backend/de.metas.ui.web.base/.../view/ViewRestController.java`, `.../dashboard/DashboardRestController.java`, `backend/de.metas.handlingunits.base/.../I_M_HU_PI_Item_Product.java`, `frontend/package.json`, `frontend/src/containers/DocumentListContainer.js`, `backend/LICENSE.md` |
| OpenBoxes | `grails-app/domain/org/pih/warehouse/` (order, requisition, picklist, inventory, invoice), `grails-app/controllers/org/pih/warehouse/UrlMappings.groovy`, `docs/api-guide/`, `package.json`, `gradle.properties`, `docker/docker-compose.yml`, `LICENSE.md`, https://demo.openboxes.com/openboxes |
| IDURAR | `backend/src/models/`, `backend/src/setup/setup.js`, `frontend/src/router/routes.jsx`, `LICENSE`, `backend/package.json`; GitHub commits `b6e06ab4`, `50a71c72`, `3518aee2`, `18a35f25` (the licence change) |
| VACP | https://github.com/ETH-IVIA-Lab/VACP: `docs/reference/tool-contract.md`, `packages/lib/providers/{vega-lite,vgplot}`, `packages/lib/protocol/{core,duckdb,kit,gateway,diagrams}`, root `package.json` (private, no licence) |
| Our WWI package | `data/wwi-package-v2-2026-10-08/docs/{DATASET_GUIDE,V2_SPEC}.md`, `app/app.js`, `app/analysis.js`, `catalog/operations.json`, `evaluation/v2/` |

## Late correction (Bigcapital import, 9 Oct)

From reading the source code (the app was not run), only 14 resources are registered for CSV/XLSX import:

- Account
- BillPayment
- CreditNote
- Customer
- Expense
- Item
- ItemCategory
- ManualJournal
- PaymentReceived
- SaleEstimate
- SaleInvoice
- UncategorizedBankTransaction
- Vendor
- VendorCredit

**Not registered:**

- **Bills:** `Bills/commands/BillsImportable.ts` defines the class but has no `@ImportableService` decorator.
- **Tax rates:** not registered either.
- **Sales receipts:** no import service at all.

The import registry throws "No importable service found" for these. WWI's 2,074 purchase orders would therefore have to be loaded one by one through `POST /api/bills`, under the default limit of 300 requests per minute (`THROTTLE_GLOBAL_LIMIT`), and before sales, so that stock never goes negative.

This does not change the recommendation, because Bigcapital remains a fallback only.
