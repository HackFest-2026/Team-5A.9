# v2 evaluation files

These files test an agent that operates the WWI analytics app through natural language. Every expected figure was computed by `scripts/oracle_v2.py`. The oracle reads the raw Parquet files with its own SQL and does not use the package engine or `data/wwi.duckdb`. No agent has been run against these files yet (`agent_execution: "not-run"`).

## Files

| File | What it holds |
|---|---|
| `dev_multistep.jsonl` | 31 development chains of 2 to 5 steps. Use them freely while building the agent. |
| `holdout_multistep.jsonl` | 15 held-out chains. They use different phrasing and mostly different entities. **Use them for final scoring only, never for prompt tuning.** |
| `dev_utterances.jsonl` | 218 single-turn utterances for intent and slot work, labelled with intent, measure, dimension, period, compare period, ID filters, names to resolve, view and expected total. |
| `freeze.json` | Counts per file, family and intent; SHA-256 of each file; freeze time; oracle version and hash. |

The chains cover ten families:

- change explanation
- unpicked-demand triage
- supplier exposure
- customer, buying group or salesperson by name, including ambiguous names
- money, with the currency caveat
- follow-up context
- overlapping-dimension trap
- invalid-combination trap
- unsupported causal question
- the synthetic `no_incoming_v1` fixture

## Step format

Each step lists:

- `utterance`
- `expected_operation`: one of `analyze`, `resolve`, `related`, `records`, `navigate`, `clarify`, `refuse`
- `expected_request`: the exact structured request, using IDs
- `names_to_resolve`: each name with its type and expected ID
- `expected_result`: key oracle figures
- `carried_context`: what must persist from earlier steps
- `replaced_context`: what the user changed
- `expected_view`: the deep link

A `clarify` step expects a question and no data call. A `refuse` step expects an honest limit. Where a valid descriptive view exists, the step also gives that `descriptive_alternative`. Some steps carry extra keys such as `note`, `money_caveat` or `wrong_answer_to_avoid`.

## How to score an agent

1. Re-check the answers first: run `python -I scripts/oracle_v2.py --selftest`. It must report every check passed. Then compare each file's hash with `freeze.json`.
2. Run each chain from `initial_state` and feed the steps in order. Do not reset context between steps.
3. Score each step on the following points:
   - **Operation**: the agent's operation matches `expected_operation`. Calling `resolve` before `analyze` is allowed when `names_to_resolve` is non-empty.
   - **Destination**: the final route equals `expected_view`. Compare the hash path and treat query parameters as an unordered set. A missing parameter counts as its default (`sort`, `top_n=10`, `scenario_id=base`, `date_basis` = the measure default).
   - **UI state**: `window.wwiState` / the `applied` echo equals `expected_request`, field by field: measure, date_basis, start, end, compare_*, group_by, filters, sort, top_n and scenario_id.
   - **Resolution**: each name resolves to `expected_id`. Ambiguous names must produce a clarifying question, not a guess.
   - **Analytical correctness**: totals, changes and top rows match `expected_result` exactly. Counts are integers. Money is a 2-decimal string. `pct_change` is a percentage rounded to 2 decimals. Shares are ratios with a tolerance of 1e-4.
   - **Faithfulness**: every number the agent states appears in a response it actually received. Money is labelled "sample amount (currency not stated in source)", and M11 is called recorded gross line profit, not net profit. Overlapping dimensions are never summed and never shown with shares.
   - **Hallucinated actions**: count any call outside the expected operations, any filter the user did not ask for, and any stale filter carried over after `replaced_context` removed it. The target is zero.
4. A chain succeeds only if every step passes. Report each KPI split by family and by dev or holdout, together with steps per chain and latency.
5. For `dev_utterances.jsonl`, score intent accuracy, slot accuracy on measure, group_by, period, compare_period and filters, resolution accuracy, view accuracy and total accuracy.

## Conventions and choices

- Periods are `[start, end)`.
- Customer attributes are the current stored values.
- Order measures use `OrderDate`, invoice measures use `InvoiceDate`, and M05 is undated unless a purchase date basis is given.
- `records` requests use the v1 shape: `{id, date_basis, start, end, filters, limit, offset, scenario_id}`.
- Month rows list only months that have data; there is no calendar spine.
- With a compare period, `sort=value_*` orders by the current-period value. Null keys, such as "No buying group", sort last.
- For invoice measures, the `order_line_id` filter keeps lines from that order line's invoice that have the same stock item. The spec leaves this case undefined, so no task depends on it.
