# WWI portable evidence package — v2

**v2 (package 2.0.0, Contract 0.2.0)** adds multi-step analysis on top of v1 without changing any v1 data or behaviour. Start with `docs/WHATS_NEW_V2.md`; the exact definitions are in `docs/V2_SPEC.md`.

- **Windows:** double-click `launch.cmd`; open http://127.0.0.1:8017 (new **Analysis** page in the menu). `rebuild.cmd` rebuilds and runs all checks.
- **Linux/macOS:** `./setup_linux.sh` once (creates `.venv` from `requirements-lock.txt` and rebuilds), then `./launch.sh [port] [host]`.
- **New API:** `POST /api/analyze`, `POST /api/resolve`, `POST /api/related`, `GET /api/contract`, `GET /api/lookup?type=...`. All v1 routes are unchanged.
- **Checks:** `scripts/validate_v2.py --package . [--url http://127.0.0.1:8017]`, plus all v1 validators.

The v1 README follows unchanged.

---

## v1 README

Windows x64. No SQL Server, SSMS, internet, credentials, Python installation or pip is needed for ordinary use. The bundled runtime and all required libraries are included. Extract the whole folder; keep its relative structure. Source simulated-business data is under data/raw; one labelled scenario is under data/synthetic.

## Start and rebuild

1. Double-click `launch.cmd`. It starts the read-only localhost dashboard and opens your browser at http://127.0.0.1:8017. Close its console or press Ctrl+C to stop it. If the port is already occupied, use the existing WWI tab or stop its prior server.
2. For a rebuild, stop the local dashboard first, then double-click `rebuild.cmd`. It rebuilds DuckDB from local Parquet, validates205 source/type/key/isolation checks and validates Contract schemas. No acquire step is called.
3. Run additional domain checks with `runtime\python.exe scripts\validate_metrics.py --package .` (277 checks; independent raw oracle).

The moved-folder/no-source acceptance proof is evidence/offline_move_final.json. Reports/findings.md is the main analysis. No PPT was edited.

## Query from PowerShell

Open PowerShell in the extracted package:

```powershell
& .\runtime\python.exe .\scripts\query_local.py --kind metric --id M02
& .\runtime\python.exe .\scripts\query_local.py --kind metric --id M04 --request '{"date_basis":"none","filters":{"stock_item_id":80}}'
& .\runtime\python.exe .\scripts\query_local.py --kind records --id purchase_lines --request '{"date_basis":"none","filters":{"stock_item_id":80,"status":"incoming"}}'
& .\runtime\python.exe .\scripts\serve.py --package . --port 8018
```

All-history M02 is360276; M03 is3085. Supply M05 requires date_basis none/purchase_order_date/expected_delivery_date. Date pairs are inclusive-start/exclusive-end, within2013-01-01 to2016-06-21; naive source calendar/time conventions are preserved. Typed validation rejects unsupported combinations. A single record page is default50/max200; use offset to page. Request schema: catalog/schemas/request.schema.json. Positive explicit IDs select entities; unknown valid IDs return empty/zero results.

## API and interface

GET /api/capabilities exposes verified measures/charts/views/version only; GET /api/scenario returns the labelled fixture specification. POST /api/metric, /api/chart, /api/records use `{ "id":"M02", "dataset_version":"wwi-data-v1-2026-10-08", "scenario_id":"base", "date_basis":"order_date", "start":"2016-05-01", "end":"2016-06-01", "filters":{}, "limit":50, "offset":0 }`. Unknown fields/IDs-of-operations, incompatible filters/date bases, bad versions/intervals/page limits return422 with completed=false. No arbitrary SQL endpoint or source write exists.

Metric response: dataset/scenario, metric_id, date_basis, applied_filters (full typed request), columns, rows, query_id, limit/offset. Values for scalar count metrics are integers; holdings are per-item rows; category values are distinct-order counts. Chart response includes chart_id,measure_id,rows,caption. Record response includes entity,total_rows,rows,limit,offset,has_more,provenance and applied_filters. Integer IDs remain integers; booleans remain booleans; dates/timestamps serialize as naive strings; exact decimal amounts serialize as decimal strings, never floating currency. Evidence files keep source values and NULLs. Contract models and generated schemas are under scripts and catalog/schemas.

Dashboard: Overview/Fulfilment/Supply plus customer, order, order-line, item, purchase, purchase-line and supplier panels. URL hash query state survives reload. Explicit details state their actual all-date or retained-period scope. Holdings preview up to50 sorted items; filter Item ID for any specific item. Supply explicitly displays purchasing date basis and undated holdings scope. No currency-labelled revenue/profit, historical backlog, customer allocation, ATP or causal supplier-failure claim is published.

## Maintainer operations and provenance

P1 and P2 are accepted; evidence contains205 parity,277 metric,31 HTTP checks and browser outcomes. The checks are not measured agent success. Optional investigations require explicit stage and investigation:

```powershell
& .\runtime\python.exe .\scripts\optional_history.py --package . --stage p3 --investigation history
& .\runtime\python.exe .\scripts\optional_lateness.py --package . --stage p3 --investigation lateness
```

They never run implicitly during rebuild/serve. Source acquisition is explicit only, uses a locally authorized installed Microsoft ODBC driver and Windows authentication, and must write a new version directory. This package's acquire script refuses an existing manifest even with --refresh:

```powershell
& .\runtime\python.exe .\scripts\acquire.py --server lpc:localhost --database WideWorldImporters --auth windows --output 'D:\WWI-new-version' --refresh
```

Refresh requires SQL Server access and the external system ODBC driver; ordinary package use does not. Copy the maintainer scripts/runtime to a fresh package for a future refresh/build workflow; do not replace this approved data version. Acquisition logs preserve failures and quiescence/pre-post controls. Stable counts are not atomic snapshot certification. Initial query SQL/results are in sql/source and evidence/source_controls; local operations log SQL, parameters, results, times and failures to evidence/acquisition_log.jsonl and evidence/query_runs. Older exploratory local failures are described in reports/execution_notes.md.

Typed Parquet has100ns residual companions for datetime2 scale7. Original SQL collations and omitted fields are recorded; no string-search collation equivalence is advertised. Key/relationship validation covers the exported scope; unexported FK parent tables are explicit. No certified physical integrity, complete event history or audited accounting is claimed.

Evaluation files are maintainer-only (12development/18held-out); do not place held-out answers into prompts or public UI metadata. Future target15/18 is not measured performance. If scoring cases are used to tune, disclose contamination and replace them. The package contains no LLM runner/no-code-platform integration.

## Integrity and licenses

manifest.json records acquisition/raw file schemas,counts,hashes and package status. artifact_manifest.json records the delivered static files (excluding itself and live query logs/cache). These are shipment checksums, not expected hashes after a physical DuckDB rebuild. Raw Parquet hashes are checked during validation. ZIP checksum is provided beside the ZIP. Python and third-party library licenses remain under runtime; WWI publisher attribution is under licenses.
