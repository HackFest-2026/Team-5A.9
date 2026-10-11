"""Command line: python -m agent.cli "question"   (add --repl for a conversation, --json for machine output)."""
from __future__ import annotations

import argparse
import json
import sys

from .adapters.wwi import WWIBackend
from .config import Config
from .docs import LLMRetriever
from .llm import LLM
from .loop import Agent


def build_agent(cfg: Config, with_pages: bool = True) -> Agent:
    if cfg.backend == "erpnext":
        from .adapters.erpnext import ERPNextBackend  # noqa: WPS433
        backend = ERPNextBackend()
    else:
        backend = WWIBackend(cfg.wwi_url, cfg.wwi_package)
    llm = LLM(cfg)
    # page lookup is LLM-driven two-stage retrieval (no index to build, nothing to keep in sync)
    pages = LLMRetriever(backend.pages(), llm) if with_pages else None
    return Agent(cfg, backend, llm, pages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent")
    ap.add_argument("question", nargs="*", help="one or more questions, asked in order in the same conversation")
    ap.add_argument("--repl", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--plan-mode", choices=["llm", "slots"])
    ap.add_argument("--gates", choices=["on", "off"])
    ap.add_argument("--trace", action="store_true", help="print trace events")
    a = ap.parse_args(argv)
    cfg = Config()
    if a.plan_mode:
        cfg.plan_mode = a.plan_mode
    if a.gates:
        cfg.gates = a.gates == "on"
    agent = build_agent(cfg)
    sess = agent.new_session()

    def ask(q: str) -> None:
        r = agent.turn(q, sess)
        if a.json:
            print(json.dumps({"status": r.status, "op": r.op, "text": r.text, "notes": r.notes, "deep_link": r.deep_link,
                              "actions": [x["summary"] for x in r.actions], "latency": round(r.latency, 2),
                              "llm_calls": r.llm_calls, "trace": r.trace_path}, ensure_ascii=False))
        else:
            print(f"\n> {q}\n[{r.status}/{r.op}  {r.latency:.1f}s  {r.llm_calls} LLM calls]\n{r.render()}")
            if a.trace:
                for e in r.events:
                    print("   ", json.dumps(e, default=str)[:300])

    for q in a.question:
        ask(q)
    if a.repl or not a.question:
        try:
            while True:
                q = input("\nyou> ").strip()
                if q in ("", "exit", "quit"):
                    break
                ask(q)
        except (EOFError, KeyboardInterrupt):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
