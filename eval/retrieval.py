"""Retrieval KPI over the 293-page catalogue (30 real pages, 263 decoys): precision, recall and MRR.

  python -m eval.retrieval --modes llm [--baseline-bm25] [--limit N]

`llm` = the agent's own retriever: two-stage, driven by the configured LLM (DeepSeek-R1-32B), see agent/docs.py.
BM25 is only a reference baseline. `gold` is best-first; `acceptable` pages also count in the lenient columns.
Queries with empty gold ("nothing fits") cannot be ranked and are reported separately."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from agent.config import ROOT, Config
from agent.docs import BM25, LLMRetriever, page_text
from agent.llm import LLM

from .run_v2 import EVAL_DIR, load_jsonl

KS = (1, 3, 5)


def score(queries: list[dict], rank_fn: Callable[[str], list[str]], workers: int, label: str) -> dict:
    def one(q: dict) -> list[str]:
        try:
            return rank_fn(q["query"])
        except Exception as e:  # noqa: BLE001 - count a failed query as a miss, keep going
            print(f"  query {q['id']} failed: {e}", file=sys.stderr)
            return []

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        orders = list(ex.map(one, queries))
    wall = time.time() - t0
    rr, rr_len = [], []
    hit = {k: [] for k in KS}
    hit_len = {k: [] for k in KS}
    prec = {k: [] for k in KS}
    rec = {k: [] for k in KS}
    by_diff: dict[str, list[float]] = defaultdict(list)
    decoy_gold = []
    for q, order in zip(queries, orders):
        gold = set(q["gold"])
        ok = gold | set(q.get("acceptable") or [])
        first = next((r for r, i in enumerate(order, 1) if i in gold), None)
        first_len = next((r for r, i in enumerate(order, 1) if i in ok), None)
        rr.append(1 / first if first else 0.0)
        rr_len.append(1 / first_len if first_len else 0.0)
        by_diff[q.get("difficulty", "?")].append(rr[-1])
        for k in KS:
            top = set(order[:k])
            hit[k].append(1.0 if gold & top else 0.0)
            hit_len[k].append(1.0 if ok & top else 0.0)
            prec[k].append(len(ok & top) / k)
            rec[k].append(len(gold & top) / len(gold))
        if q["gold"][0].startswith("decoy"):
            decoy_gold.append(rr[-1])
    f = lambda xs: round(100 * statistics.mean(xs), 1)  # noqa: E731
    out = {
        "retriever": label, "n": len(queries),
        "MRR_gold": round(statistics.mean(rr), 3), "MRR_lenient": round(statistics.mean(rr_len), 3),
        **{f"hit@{k}_gold_pct": f(hit[k]) for k in KS},
        **{f"hit@{k}_lenient_pct": f(hit_len[k]) for k in KS},
        **{f"precision@{k}_lenient_pct": f(prec[k]) for k in KS},
        **{f"recall@{k}_gold_pct": f(rec[k]) for k in KS},
        "MRR_gold_by_difficulty": {d: round(statistics.mean(v), 3) for d, v in sorted(by_diff.items())},
        "wall_seconds": round(wall, 1), "seconds_per_query": round(wall / max(1, len(queries)), 2),
    }
    if decoy_gold:
        out["MRR_gold_decoy_targets"] = round(statistics.mean(decoy_gold), 3)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="llm")
    ap.add_argument("--baseline-bm25", action="store_true", help="also report the lexical reference baseline")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "retrieval.json"))
    a = ap.parse_args(argv)
    cfg = Config()
    pages = json.loads((cfg.wwi_package / "catalog" / "retrieval" / "pages.json").read_text())["items"]
    allq = load_jsonl(EVAL_DIR / "retrieval_queries.jsonl")
    queries = [q for q in allq if q["gold"]]
    if a.limit:
        queries = queries[: a.limit]
    ids = [p["id"] for p in pages]
    results = []
    if "llm" in a.modes.split(","):
        r = LLMRetriever(pages, LLM(cfg))
        results.append(score(queries, r.rank_ids, a.workers, f"llm-two-stage ({cfg.llm_model})"))
    if a.baseline_bm25:
        bm = BM25([page_text(p) for p in pages])
        import numpy as np
        results.append(score(queries, lambda q: [ids[i] for i in np.argsort(-bm.scores(q), kind="stable")[:10]], 1, "bm25 (reference)"))
    out = {"pages": len(pages), "queries_total": len(allq), "queries_none_fit_excluded": len(allq) - len([q for q in allq if q["gold"]]),
           "results": results}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "MRR_gold_by_difficulty"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
