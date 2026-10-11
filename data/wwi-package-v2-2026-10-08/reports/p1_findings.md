# P1 findings — 8 October 2026

The existing SQL Server source was acquired read-only into 21 normalized Parquet entities. Invoice headers/lines, stock transactions and segment/geography lookups are included. Existing source controls reconcile. The source connection is closed; further analysis uses local DuckDB.

## Full-history story decision

There are 3,147 stored underpicked lines across 3,085 orders, totalling 360,276 units. May-created orders contribute 168 lines, 161 orders and 17,710 units. Thus 2,924 orders (94.78% of unpicked orders) fall outside May.

Backorder targets account for 3,080 / 3,085 orders (99.84%) and 359,190 / 360,276 units (99.70%). Five non-target orders account for 1,086 units. The safe story is **stored unpicked backorders with related incoming supply**, not supplier failure or customer allocation.

Unpicked order dates span 2013-01-12 to 2016-05-31. The full monthly distribution and date-age buckets are retained in `evidence/cutoff/`. Chain traversal finds 7,538 links and distinct targets, maximum depth three, no cycles and no backwards date sequences. Current underpicked targets dated later than their referencing original: 0; same date: 3080. These counts describe retained rows, not a complete lifecycle.

## Cut-off analysis

Final 1 / 3 / 7 calendar days contain 806 / 1,629 / 4,637 units: 0.224% / 0.452% / 1.287% of all 360,276 units. They contain 9 / 17 / 47 orders: 0.292% / 0.551% / 1.524% of all 3,085 orders. May-only denominators and shares are exported separately.

The final-week cohort is visible but does not explain the full-history cohort. These windows are descriptive, not a causal truncation test. Stored expected dates can extend into June. A claim that May backlog rose or operational failure occurred is unsupported.

April: 1951 orders created, 135 with stored unpicked lines, 15050 stored unpicked units. May: 2047 orders created, 161 with stored unpicked lines, 17710 stored unpicked units. These are creation cohorts viewed in one stored state, not period-end historical backlog.

The daily calendar includes zero-activity dates. `reports/daily_may.svg` visualizes unpicked units by creation date. The original source query and outputs remain unchanged.

## Parity and portability

The first local validation passed 203 checks covering source counts, Arrow types, PK/FK coverage, independent Python row totals, sorted May evidence, complete item evidence, multi-group semi-joins, and explicit transport edge cases. Exact decimals and integer widths remain typed. Scale-seven datetime2 uses a microsecond timestamp plus residual 100ns companion; source timestamps remain naive. Omitted binary/spatial types are listed in the manifest.

The moved-folder rebuild result is recorded separately in `evidence/offline_move_probe.json`. Do not treat count agreement or boundary probes as an atomic snapshot. Two acquisition attempts stopped before export on transient logged transactions; subsequent acquisition waits for measured quiescence and records transaction identities/types. No source settings or business rows were changed.

## Screening wording

No PowerPoint was edited, as instructed by the user. Suggested wording is in `reports/deck_claims.md`. Exact historical reconstruction and supplier/customer lateness remain optional P3, gated after P2. P1 does not certify integrity, currency, agent accuracy or no-code integration.
