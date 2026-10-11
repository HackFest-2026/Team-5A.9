"""Run the agent on the v2 task files and write scores.

  python -m eval.run_v2 --split dev --out evidence/dev_run.json [--k 3] [--plan-mode llm|slots] [--gates on|off]

The held-out chains are only read with --final. Do not tune prompts on them."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.cli import build_agent
from agent.config import ROOT, Config
from agent.loop import Agent
from agent.trace import Trace

from .metrics import pct, score_step

EVAL_DIR = Config().wwi_package / "evaluation" / "v2"


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def run_chain(agent: Agent, chain: dict, trace_dir: Path | None) -> dict:
    sess = agent.new_session()
    steps = []
    for st in chain["steps"]:
        tr = Trace(trace_dir) if trace_dir else Trace(None)
        res = agent.turn(st["utterance"], sess, tr)
        sc = score_step(st, res, agent.c, st["utterance"])
        sc.update({"step": st["step"], "utterance": st["utterance"], "answer": res.text[:300], "link": res.deep_link,
                   "trace": res.trace_path})
        steps.append(sc)
    return {"task_id": chain["task_id"], "family": chain["family"], "split": chain["split"],
            "success": all(s["pass"] for s in steps), "steps": steps}


def run_utterance(agent: Agent, u: dict, trace_dir: Path | None) -> dict:
    sess = agent.new_session()
    tr = Trace(trace_dir) if trace_dir else Trace(None)
    res = agent.turn(u["utterance"], sess, tr)
    step = {"expected_operation": u["expected_operation"], "expected_request": u.get("expected_request"),
            "names_to_resolve": [{"text": n["text"], "type": n["type"], "expected_id": n.get("expected_id")}
                                 for n in (u.get("names_to_resolve") or []) if isinstance(n, dict)],
            "expected_view": u.get("expected_view"),
            "expected_result": {"total": u["expected_total"]} if u.get("expected_total") is not None and u["expected_operation"] == "analyze" else {}}
    sc = score_step(step, res, agent.c, u["utterance"])
    sc.update({"id": u["id"], "intent": u.get("intent"), "utterance": u["utterance"], "answer": res.text[:200], "link": res.deep_link})
    return sc


def summarise(chains: list[dict], utts: list[dict]) -> dict:
    out: dict = {}
    steps = [s for ch in chains for s in ch["steps"]]
    if chains:
        out["chains"] = {
            "n": len(chains), "chain_success_pct": pct(sum(c["success"] for c in chains), len(chains)),
            "step_pass_pct": pct(sum(s["pass"] for s in steps), len(steps)),
            "destination_acc_pct": pct(sum(s["dest_ok"] and s["op_ok"] for s in steps), len(steps)),
            "ui_state_acc_pct": pct(sum(s["state_ok"] for s in steps), len(steps)),
            "resolution_acc_pct": pct(sum(s["resolution_ok"] for s in steps), len(steps)),
            "analytic_acc_pct": pct(sum(s["analytic_ok"] for s in steps), len(steps)),
            "faithfulness_pct": pct(sum(s["faithful_ok"] for s in steps), len(steps)),
            "hallucinated_actions_total": sum(s["halluc"] for s in steps),
            "hallucinated_action_rate_pct": pct(sum(1 for s in steps if s["halluc"]), len(steps)),
            "avg_steps_per_chain": round(statistics.mean(len(c["steps"]) for c in chains), 2),
            "avg_tool_calls_per_step": round(statistics.mean(s["attempts"] for s in steps), 2),
            "avg_llm_calls_per_step": round(statistics.mean(s["llm_calls"] for s in steps), 2),
            "latency_mean_s": round(statistics.mean(s["latency"] for s in steps), 2),
            "latency_p95_s": round(sorted(s["latency"] for s in steps)[int(0.95 * (len(steps) - 1))], 2),
            "template_answer_pct": pct(sum(s["answer_source"] == "template" for s in steps if s["status"] == "answered"),
                                       max(1, sum(s["status"] == "answered" for s in steps))),
        }
        fam: dict[str, list] = defaultdict(list)
        for c in chains:
            fam[c["family"]].append(c["success"])
        out["chains"]["by_family"] = {k: f"{sum(v)}/{len(v)}" for k, v in sorted(fam.items())}
    if utts:
        out["utterances"] = {
            "n": len(utts),
            "intent_acc_pct": pct(sum(u["op_ok"] for u in utts), len(utts)),
            "slot_acc_pct": pct(sum(u["state_ok"] for u in utts), len(utts)),
            "resolution_acc_pct": pct(sum(u["resolution_ok"] for u in utts), len(utts)),
            "view_acc_pct": pct(sum(u["dest_ok"] for u in utts), len(utts)),
            "total_acc_pct": pct(sum(u["analytic_ok"] for u in utts), len(utts)),
            "faithfulness_pct": pct(sum(u["faithful_ok"] for u in utts), len(utts)),
            "pass_pct": pct(sum(u["pass"] for u in utts), len(utts)),
            "hallucinated_action_rate_pct": pct(sum(1 for u in utts if u["halluc"]), len(utts)),
            "latency_mean_s": round(statistics.mean(u["latency"] for u in utts), 2),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "holdout"], default="dev")
    ap.add_argument("--final", action="store_true", help="required to read the held-out chains")
    ap.add_argument("--what", choices=["chains", "utterances", "both"], default="both")
    ap.add_argument("--k", type=int, default=1, help="repeat each chain k times (pass^k)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--plan-mode", choices=["llm", "slots"])
    ap.add_argument("--gates", choices=["on", "off"])
    ap.add_argument("--model", help="served model name")
    ap.add_argument("--llm-url")
    ap.add_argument("--llm-key")
    ap.add_argument("--call-style")
    ap.add_argument("--no-llm-answer", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "evidence" / "run.json"))
    ap.add_argument("--traces", action="store_true", help="write per-turn JSONL traces")
    a = ap.parse_args(argv)
    if a.split == "holdout" and not a.final:
        print("refusing to touch held-out chains without --final", file=sys.stderr)
        return 2
    cfg = Config()
    if a.plan_mode:
        cfg.plan_mode = a.plan_mode
    if a.gates:
        cfg.gates = a.gates == "on"
    if a.model:
        cfg.llm_model = a.model
    if a.llm_url:
        cfg.llm_url = a.llm_url
    if a.llm_key:
        cfg.llm_key = a.llm_key
    if a.call_style:
        cfg.llm_call_style = a.call_style
    if a.no_llm_answer:
        cfg.llm_answer = False
    agent = build_agent(cfg)
    tdir = (ROOT / "traces" / time.strftime("eval-%Y%m%d-%H%M%S")) if a.traces else None
    chains_in: list[dict] = []
    utts_in: list[dict] = []
    if a.what in ("chains", "both"):
        chains_in = load_jsonl(EVAL_DIR / ("dev_multistep.jsonl" if a.split == "dev" else "holdout_multistep.jsonl"))
    if a.what in ("utterances", "both") and a.split == "dev":
        utts_in = load_jsonl(EVAL_DIR / "dev_utterances.jsonl")
    if a.limit:
        chains_in, utts_in = chains_in[: a.limit], utts_in[: a.limit]
    t0 = time.time()
    runs: list[list[dict]] = []
    for k in range(a.k):
        with ThreadPoolExecutor(a.workers) as ex:
            runs.append(list(ex.map(lambda ch: run_chain(agent, ch, tdir), chains_in)))
        print(f"chains run {k + 1}/{a.k} done ({time.time() - t0:.0f}s)", file=sys.stderr)
    utts: list[dict] = []
    if utts_in:
        with ThreadPoolExecutor(a.workers) as ex:
            utts = list(ex.map(lambda u: run_utterance(agent, u, tdir), utts_in))
        print(f"utterances done ({time.time() - t0:.0f}s)", file=sys.stderr)
    first = runs[0] if runs else []
    summary = summarise(first, utts)
    if chains_in:
        per_chain = list(zip(*[[c["success"] for c in r] for r in runs]))
        summary["pass_at_1_pct"] = pct(sum(sum(p) / len(p) for p in per_chain), len(per_chain))
        summary[f"pass_pow_{a.k}_pct"] = pct(sum(all(p) for p in per_chain), len(per_chain))
    summary["config"] = {"split": a.split, "plan_mode": cfg.plan_mode, "gates": cfg.gates, "model": cfg.llm_model,
                         "llm_answer": cfg.llm_answer, "k": a.k, "step_budget": cfg.step_budget,
                         "wall_seconds": round(time.time() - t0, 1)}
    out = {"summary": summary, "chains": runs, "utterances": utts}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
