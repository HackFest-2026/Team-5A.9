"""Debug chains: python -m eval.dbg V2D07 V2D23 [--plan-mode slots]
Prints, per step, the model's intent, the expectation, gate events and the outcome."""
import json
import sys

from agent.cli import build_agent
from agent.config import Config
from agent.trace import Trace

from .metrics import score_step
from .run_v2 import EVAL_DIR, load_jsonl


def main() -> None:
    args = sys.argv[1:]
    cfg = Config()
    if "--plan-mode" in args:
        i = args.index("--plan-mode")
        cfg.plan_mode = args[i + 1]
        del args[i : i + 2]
    agent = build_agent(cfg)
    chains = {c["task_id"]: c for c in load_jsonl(EVAL_DIR / "dev_multistep.jsonl")}
    for cid in args:
        sess = agent.new_session()
        print("=====", cid, chains[cid]["description"])
        for st in chains[cid]["steps"]:
            tr = Trace(None)
            res = agent.turn(st["utterance"], sess, tr)
            sc = score_step(st, res, agent.c, st["utterance"])
            und = next((e for e in tr.events if e["kind"] == "understand"), {}).get("intent", {})
            slim = {k: v for k, v in (und or {}).items() if v not in (None, [], "unchanged", {"kind": "unchanged"})}
            print(f"--- step {st['step']} [{'PASS' if sc['pass'] else 'FAIL'}] {st['utterance']}")
            print("   intent:", json.dumps(slim))
            for e in tr.events:
                if e["kind"] in ("sanitize", "gate_reject", "preflight_refuse", "expectation", "finish_check", "period_error"):
                    print("   ", e["kind"], json.dumps({k: v for k, v in e.items() if k not in ("t", "kind")})[:330])
            print("   ->", res.status, res.op, (res.text or "")[:160].replace("\n", " / "))
            if not sc["pass"]:
                print("   WHY:", "; ".join(sc["why"])[:400])


main()
