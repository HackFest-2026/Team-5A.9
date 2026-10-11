# Features and limits

## ERPNext (checked against the live instance; features not tested by us are marked)
| Area | Supports |
|---|---|
| CRUD | Full, on every record type, via Desk screens or REST (`/api/resource`). Draft → submitted → cancelled → amended; bulk update, data import, tags, comments, sharing, version history (142,096 versions here). *Writes not tested by us.* |
| Charts | Built in: **Dashboard Chart** from any record type or report (line, bar, pie, donut…), with grouping and sums. Here: **39 charts, 26 number cards, 8 dashboards, 22 workspaces**. *Creating a new chart not tested by us.* |
| Reports | **189**: 169 script, 13 query, 7 report-builder. Includes Sales Analytics, Purchase Analytics, Stock Balance, Stock Ledger, General Ledger, Trial Balance, Profit and Loss, Item-wise Sales Register, Accounts Receivable. |
| Modules on | Selling, Buying, Stock, Accounts, CRM, Manufacturing, Projects, Support, Assets. |
| Control | 50 roles; 3 users here; user permissions (restrict by company, territory, customer…); API key and secret per user; 0 workflows configured. |
| Customisation | Custom fields, print formats, notifications, webhooks, auto-repeat, assignment rules (no code). |
| Size | 384 list pages, 66 settings forms, 16 desk pages, 189 reports, 22 workspaces. |
| Not usable as-is | No email account configured; no payments (all invoices overdue); list count label caps at "1,000+"; customer/supplier forms fail to open on nova2 (fiscal year); realtime broken. |

**Users and the agent signing in (not built):** create users at `/app/user`, give roles and User Permissions (e.g. a Great Lakes rep sees only that territory). The agent should use a **per-user API key** (server-side) so ERPNext enforces what it can see or do; show "signed in as …" in the panel. Estimate: about a day for a read-only per-user ERPNext adapter; plus half to one day for a guarded write (confirmation card, drafts only). The WWI console and agent service have **no accounts at all** today.

## Our WWI console and agent
| Area | Supports |
|---|---|
| Pages | 4 analytics (Overview, Fulfilment, Supply, Analysis), 5 browse lists (Customers 663, Orders 73,595, Stock items 227, Suppliers 13, Purchase lines 8,367) with name/ID search, 7 detail pages (customer, order, order line, item, supplier, purchase order, purchase line). |
| Charts | 6 fixed on the analytics pages **plus a Chart builder (#/charts)**: any published measure, any allowed breakdown, a period and an optional comparison; bars, horizontal bars, line (by month), pie (additive breakdowns), or a single number; live preview from /api/analyze, data table, CSV download, save/edit/delete under My charts. A saved chart stores the request, not numbers, so it always matches the Analysis page. The assistant can propose a chart from a chart question ("chart orders in May 2016 by territory"): a card with a title box and a Save button; nothing is saved until Save is pressed (`agent/chart_proposal.py`, `eval/propose_test.py`, passes). Not yet: filters inside a chart, PNG export, editing a chart by message. |
| Analysis | Compare any measure across two periods; group by none/month/customer/category/buying group/state/territory/salesperson/item/supplier/stock group; sort, top-N, drill-in; deep links reproduce the view. 8 measures published; M06, M08, M09 candidates; M07 rejected. |
| Assistant | Natural-language questions and follow-ups; opens the matching page; ledger journey infographic. |
| API | `analyze`, `resolve`, `related`, `records`, `metric`, `chart`, `contract`, `lookup`, `scenario`, `capabilities`. |
| CRUD | **Workspace layer (12 Oct).** Create customer, supplier, stock item, draft order (lines, item search); edit source customer/supplier/item as an overlay; soft delete/restore; revert; activity log; review before saving; server-side validation. Saved apart from the source; **not counted in analytics**; the agent does not read or write it. Source orders, invoices and stock are not editable. |
| Missing | Export (CSV/PDF/print), accounts and login, chart builder, agent-driven writes. |

## Why the source stays read-only (and how the workspace was built)
**Why:** the evaluation, the frozen task files (checksums) and the independent oracle score the agent against the source data. Editing it would change "+96 orders" and invalidate the 8-of-8 reconciliation and dev results. ERPNext already provides CRUD.
**Chart creation (safe, about half a day):** a chart-builder page (measure, break-down, period, chart type, preview), saved definitions in a separate small store, a "My charts" page, and an agent tool with a confirmation. No data changes; always built from checked `analyze` results.
**CRUD (about 1 to 1.5 days):** writes go to a separate "workspace" store (precedent: the flagged synthetic scenario), kept out of analytics by default; read-before-write gate, a confirmation card, an audit log; soft delete only. **Recommendation:** build the chart builder first; show CRUD in ERPNext (a guarded draft Sales Order); add CRUD to our app only if required.

## Known limits (be upfront with judges)
- Answers take 31–76 s with R1-32B; one question at a time; panel shows a working timer.
- Only a few figures were checked against the key (see 01 §3); held-out unrun.
- ERPNext invoices stop at 24 Feb 2016, so April–May 2016 revenue cannot come from ERPNext. Currency is a placeholder; profit not comparable.
- Stock history in ERPNext is not WWI's real history; only final holdings are reliable.
- No login anywhere in the console; services are open on the lab network.
- The VACP repository has no licence file.
- nova2's copy of the console is the older app; the new one is served from this machine.
