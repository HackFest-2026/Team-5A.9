# API-based agent for the WWI v2 app

Implements `research/01_API_AGENT_BUILD_PLAN.md`: one agent core, six task-level tools, code gates before acting, a code finish gate before answering.

## Run

```bash
# 1. the app + API (once)
data/wwi-package-v2-2026-10-08/launch.sh 8017

# 2. the model. DeepSeek-R1-32B with JSON-schema-constrained output (llama.cpp, no tool parser needed):
source r1.env            # LLM_URL / LLM_MODEL / LLM_CALL_STYLE=json / LLM_KEY read from the key file
#    or Qwen2.5-14B on vLLM with native tool calling:  LLM_URL=http://127.0.0.1:8011/v1 LLM_MODEL=qwen2.5-14b LLM_CALL_STYLE=tools

.venv/bin/python -m agent.cli "How did orders in May 2016 compare with April, by territory?" "Which states inside Great Lakes moved?"
.venv/bin/python -m pytest tests -q                       # gate / finish-gate / calendar unit tests
.venv/bin/python -m eval.run_v2 --split dev --out evidence/run.json [--k 3] [--plan-mode slots] [--gates off]
.venv/bin/python -m eval.retrieval --modes llm            # retrieval P / R / MRR over the 293 pages
.venv/bin/python -m eval.dbg V2D07                         # per-step intent / expectation / gate events for one chain
```

The held-out chains are read only with `--final`. Do not tune on them.

## Flow (agent/loop.py)

```
user request
 [1] understand  LLM, schema-constrained -> Intent (a delta over the carried state). Dates, defaults, carry-over: code (slots.py)
 [2] resolve     code calls resolve(): unique -> id; ambiguous -> ask; none -> abstain
 [3] plan        expectation = slots; LLM emits the tool calls (or --plan-mode slots compiles them in code)
 [4] execute     per call: schema gate -> grounding gate -> read-before-write -> loop/budget -> API -> result check
                 rejected or failed call -> repair hint fed back (max 3) -> else abstain
 [5] finish      applied state == slots; no loop; budget (code, no LLM judge)
 [6] answer      LLM drafts from code-computed facts; every number must trace to a tool result or code arithmetic;
                 2 failed drafts -> deterministic template
```

| Plan item | File |
|---|---|
| tools (lookup, resolve, analyze, records, related, open_page) | `agent/tools.py` |
| schema / grounding / read-before-write / loop / budget gates, repair | `agent/gates.py`, `agent/loop.py` |
| finish gate, faithfulness and style checks | `agent/finish.py`, `agent/facts.py` |
| Contract -> pydantic models, validation rules | `agent/contract.py` |
| two-stage documentation retrieval (LLM-driven) | `agent/docs.py` |
| trace (JSONL per turn: every LLM call, tool call, gate verdict) | `agent/trace.py` |
| scoring against the independent answer key, no LLM judge | `eval/metrics.py` |

Choices worth knowing: arithmetic is never done by the model (`facts.py`); IDs the user never typed and no result showed are rejected (action-hallucination KPI); the model's optional slots (`status`, `sort`, `top_n`, `group_by`) are dropped unless the user's words support them (`Agent.sanitize`); the page lookup returns `available_in_app`, so a decoy page can never be opened.

## Results

See `evidence/` (JSON per run). Numbers and their configuration are in the final report from the session; dev-set numbers only, the held-out chains were not run.

