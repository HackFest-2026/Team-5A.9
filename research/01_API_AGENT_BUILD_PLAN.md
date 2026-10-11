# Build plan: API-based agent (10 Oct 2026)

- **Builds on:** `00_SYNTHESIS_PLAN.md` §3–4 and §9. The four-paper design was decided after the final sweep.
- **Target:** one agent core that runs against (1) our WWI v2 app API, then (2) ERPNext through an adapter. It is evaluated on our v2 tasks, with WebArena-Verified as the external standard.

## 0. The four papers and what each one gives us

| Paper | What we take | Where it lives |
|---|---|---|
| **Beyond Browsing** (Findings of ACL 2025) | The agent's shape: an LLM loop that calls APIs from documentation; two-stage documentation retrieval for large APIs; the hybrid fallback idea | `agent/loop.py`, `agent/docs.py` |
| **LedgerAgent + Reason Less, Verify More** | Checks in code **before** acting: read before changing state, validate parameters against the Contract, up to 3 repairs, then abstain | `agent/gates.py` |
| **Mingbird** (Apache-2.0) | The **finish gate**: before answering, check that the applied state matches the intent; detect loops; code checks, not an LLM judge | `agent/finish.py` |
| **The Tool Illusion + Beyond Text-to-SQL** | A **small, task-level tool set** (about 6 tools), not raw tables or hundreds of endpoints | `agent/tools.py` |

## 1. Architecture

```
user request
   │
   ▼
[1] Understand ── LLM: intent + slots (measure, dims, period, filters, entity names)
   │
[2] Resolve ───── tool resolve(): names → IDs; ambiguous → ask the user; none → abstain
   │
[3] Plan ──────── LLM writes a short plan (list of tool calls) ─► plan gate (code)
   │
[4] Execute loop  for each step: pre-call gate → API call → result check
   │               on error: repair (≤3) using the error message → else abstain
   │
[5] Finish gate ─ applied state == intent? every number traceable? no loops?
   │
[6] Answer ────── text + cited figures + deep link + list of actions taken
```

**Models:**
- **Qwen2.5-14B-Instruct** emits the tool calls, served by vLLM with a tool parser.
- **R1-32B** (already running on `:8090`) is optional, for planning or explanations only.
- **Fallback while the 14B isn't served:** R1-32B with JSON-schema-constrained output (llama.cpp grammar), so malformed calls are impossible.

## 2. Tool set (task-level, typed, with the applied state echoed back)

| Tool | Purpose | Backed by (WWI v2) | Backed by (ERPNext adapter) |
|---|---|---|---|
| `lookup(term)` | Contract and glossary: which measure, dimension or page means what | `/api/lookup`, `/api/contract` | Local Contract file plus `getdoctype` metadata |
| `resolve(kind, name)` | Entity name → ID, with candidates if ambiguous | `/api/resolve` | `/api/resource/<Doctype>?filters=[name like]` |
| `analyze(measure, group_by, period, filters, sort, top_n)` | All aggregates, trends and comparisons | `/api/analyze` | `frappe.client.get_list` with `group_by`, plus our measure map |
| `records(view, filters, limit)` | Inspect rows | `/api/records` | `/api/resource/...` |
| `related(entity)` | Graph hop: item → orders → supplier, and so on | `/api/related` | Link fields on the record type |
| `open_page(page, state)` | Return a **deep link** with the filters set (read-only) | Our app's routes | `/app/<doctype>?filter=...` |

Rules from §9.4:
- every parameter is typed or enumerated;
- one worked example per tool in its description;
- every response includes `applied: {...}`;
- errors say how to recover.

Arithmetic (differences, percentages, ranking) is done **in code** over tool results, never by the LLM.

## 3. Gates (the reliability layer)

1. **Schema gate:** every call is validated with pydantic against the Contract. Unknown measure or field, or a bad date → reject with a repair hint.
2. **Grounding gate:** entity IDs must come from an earlier `resolve` result in this session. No invented IDs, which is the action-hallucination KPI.
3. **Read-before-write gate:** any state-changing call needs a prior read of the same entity **and** explicit user confirmation. v1 has no write tools, so this is checked but never triggered.
4. **Repair policy:** up to 3 retries, with the gate's or API's error message fed back. Then abstain with a reason ("couldn't find customer X; did you mean …?").
5. **Finish gate:**
   - (a) the `applied` state of the final call equals the slots extracted in step [1];
   - (b) every number in the draft answer appears in a tool result, or comes from code arithmetic over them;
   - (c) no repeated identical calls (loop detector);
   - (d) the step budget isn't exceeded (8).

## 4. Documentation retrieval (Beyond Browsing two-stage)

- **WWI v2:** 6 tools, so all of them go in the prompt (single stage).
- **ERPNext:** many record types. **Stage 1:** a one-line list of the record types we expose (about 15). **Stage 2:** a `get_doc(doctype)` tool returns the fields and filters on demand.
- **Retrieval KPI over 293 pages:** a vector index (bge-m3, already on GPU 0) over the Contract's pages and components feeds `lookup`, scored with precision, recall and MRR on the 150-query set.

## 5. Code layout

The new folder is `agent/`, next to `data/`:
```
agent/
  config.py        endpoints, model URL, budgets
  llm.py           OpenAI-compatible client (vLLM / llama.cpp), JSON-schema output
  contract.py      loads /api/contract → pydantic models for tool params
  tools.py         6 tools; backend = "wwi" | "erpnext"
  adapters/wwi.py, adapters/erpnext.py
  gates.py         schema, grounding, read-before-write, repair
  finish.py        state match, faithfulness, loop detection
  loop.py          understand → resolve → plan → execute → finish → answer
  trace.py         JSONL trace per run (every call, gate verdict, latency)
  cli.py           `python -m agent.cli "question"`
eval/
  run_v2.py        v1 30 tasks + v2 46 chains + 218 utterances → scores
  metrics.py       destination acc, UI-state acc, task success, pass^k, faithfulness, false-success, latency
  webarena/        WebArena-Verified harness (one site first)
```

## 6. Milestones

| # | Deliverable | Done when | Estimate |
|---|---|---|---|
| M1 | `llm.py`, `contract.py`, `tools.py` on WWI v2; CLI answers one question end to end | Answers "orders May vs April by territory" correctly, with the trace | 0.5 day |
| M2 | Gates and finish gate | Unit tests: invented ID rejected, bad measure repaired, wrong filter caught by the finish gate | 0.5 day |
| M3 | Evaluation harness on v1 and v2 dev sets | Scores table produced; held-out set untouched | 0.5 day |
| M4 | Ablations: gates on vs off; 14B vs R1-32B; pass^k (k=3) | Table in `evidence/` | 0.5 day |
| M5 | ERPNext adapter (5 measures: M01, M02, M05, M10 through 2015, M13) | Same questions answered from ERPNext and agree with the answer key | 1 day |
| M6 | WebArena-Verified, one site (Shopping Admin) with the Hard subset | Number reported with its full config, compared with Beyond Browsing's 20.3% (API) and 41.2% (hybrid) on Shopping Admin | 1–2 days (setup-heavy) |
| M7 | VACP agent reuses the core (separate plan) | — | — |

## 7. KPIs reported (from the brief)

- intent-to-destination accuracy;
- UI-state correctness;
- multi-step task success, with average steps and latency;
- analytical correctness and faithfulness;
- retrieval precision, recall and MRR;
- action-hallucination rate;
- error and recovery rate.

All of these come from `trace.py` logs plus the answer key, with no LLM judge.

## 8. Risks

- **The 14B model is weak at long chains** (20–30%). Mitigation: plan first, task-level tools, gates; report pass^k honestly.
- **Serving the 14B needs GPU 0.** Fallback: R1-32B with constrained JSON.
- **The ERPNext data stops at the end of 2015 for invoices,** so scope M10 on ERPNext to 2013–2015.
- **WebArena setup cost.** Do one site only, and it's optional for the demo.
