"""Lexical BM25 baseline for the page/component retrieval KPI (pure standard library).

Indexes catalog/retrieval/pages.json (title, description, keywords, widget names), ranks every
entry for each query in evaluation/v2/retrieval_queries.jsonl and scores the ranking.

Metrics (answerable queries = queries whose gold list is non-empty):
  precision@1    top-1 entry is in gold or acceptable
  strict_p@1     top-1 entry is in gold
  recall@5       share of gold ids found in the top 5
  mrr@10         1 / rank of the first gold-or-acceptable entry within the top 10 (0 if none)
  route@1        top-1 entry's route equals the route of a gold or acceptable entry (destination-level
                 accuracy: a widget on the right page counts)
None-fits handling: the system abstains ("no page fits") when the top BM25 score is below a
threshold. Reported: abstention accuracy on none-fits queries, false-abstention rate on
answerable queries, and end-to-end accuracy (answerable: not abstained and top-1 relevant;
none-fits: abstained). A threshold sweep is included; the best threshold in the sweep is tuned
on this same query set and is therefore optimistic.

The ranker deliberately ignores the functional / synthetic_decoy flags, ids and routes.

Usage: python -I scripts/retrieval_baseline.py [--threshold 8.0] [--out evidence/retrieval_baseline.json]
"""
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = set("""a an and are as at be by can do does did for from has have how i in is it its me my
of on or our show so than that the their them then there these this to us was we what when where
which who why will with you your give get see tell let please want need much many all any""".split())
K1, B = 1.2, 0.75
TITLE_WEIGHT = 2  # title tokens are repeated this many times


def stem(t):
    for suf in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


def tokens(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


def doc_text(p):
    return " ".join([p["title"]] * TITLE_WEIGHT + [p["description"], " ".join(p["keywords"]), " ".join(p["widgets"])])


class BM25:
    def __init__(self, docs):
        self.ids = [d["id"] for d in docs]
        self.tf = [Counter(tokens(doc_text(d))) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / len(self.len)
        df = Counter(t for c in self.tf for t in c)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def rank(self, query):
        q = tokens(query)
        scores = []
        for i, c in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = c.get(t)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
            scores.append((s, self.ids[i]))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return scores


def evaluate(queries, rankings, threshold, routes):
    groups = defaultdict(lambda: defaultdict(list))
    for q, ranked in zip(queries, rankings):
        top_score = ranked[0][0]
        abstain = top_score < threshold
        ids = [i for _, i in ranked]
        keys = ["overall", "difficulty:" + q["difficulty"], "target:" + q["_kind"]]
        for k in keys:
            g = groups[k]
            if q["gold"]:
                rel = set(q["gold"]) | set(q["acceptable"])
                g["precision@1"].append(1.0 if ids[0] in rel else 0.0)
                g["strict_p@1"].append(1.0 if ids[0] in q["gold"] else 0.0)
                g["route@1"].append(1.0 if routes[ids[0]] in {routes[i] for i in rel} else 0.0)
                g["recall@5"].append(len(set(ids[:5]) & set(q["gold"])) / len(q["gold"]))
                rr = 0.0
                for r, i in enumerate(ids[:10], 1):
                    if i in rel:
                        rr = 1.0 / r
                        break
                g["mrr@10"].append(rr)
                g["false_abstention"].append(1.0 if abstain else 0.0)
                g["end_to_end_accuracy"].append(1.0 if (not abstain and ids[0] in rel) else 0.0)
            else:
                g["none_fits_abstention"].append(1.0 if abstain else 0.0)
                g["end_to_end_accuracy"].append(1.0 if abstain else 0.0)
    out = {}
    for k, g in groups.items():
        out[k] = {m: round(sum(v) / len(v), 4) for m, v in g.items()}
        out[k]["n_answerable"] = len(g["precision@1"])
        out[k]["n_none_fits"] = len(g["none_fits_abstention"])
    order = ["overall"] + sorted(k for k in out if k != "overall")
    return {k: out[k] for k in order}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=str(ROOT / "catalog/retrieval/pages.json"))
    ap.add_argument("--queries", default=str(ROOT / "evaluation/v2/retrieval_queries.jsonl"))
    ap.add_argument("--threshold", type=float, default=8.0,
                    help="abstain ('no page fits') when the top BM25 score is below this")
    ap.add_argument("--out", default=str(ROOT / "evidence/retrieval_baseline.json"))
    a = ap.parse_args()

    pages = json.loads(Path(a.pages).read_text())["items"]
    queries = [json.loads(l) for l in Path(a.queries).read_text().splitlines() if l.strip()]
    functional = {p["id"]: p["functional"] for p in pages}
    routes = {p["id"]: p["route"] for p in pages}
    for q in queries:  # labels for reporting only; never used for ranking
        q["_kind"] = "none_fits" if not q["gold"] else ("real" if functional[q["gold"][0]] else "decoy")

    index = BM25(pages)
    rankings = [index.rank(q["query"]) for q in queries]

    sweep = []
    for t in [x / 2 for x in range(0, 41)]:
        o = evaluate(queries, rankings, t, routes)["overall"]
        sweep.append({"threshold": t, "end_to_end_accuracy": o["end_to_end_accuracy"],
                      "none_fits_abstention": o["none_fits_abstention"], "false_abstention": o["false_abstention"]})
    best = max(sweep, key=lambda s: (s["end_to_end_accuracy"], -s["threshold"]))

    result = {
        "method": "BM25 (k1=1.2, b=0.75) over title x2 + description + keywords + widget names; "
                  "lowercase, stopwords, light suffix stemming; no flags/ids/routes used",
        "pages": len(pages),
        "pages_functional": sum(1 for p in pages if p["functional"]),
        "pages_decoy": sum(1 for p in pages if p["synthetic_decoy"]),
        "queries": len(queries),
        "threshold": a.threshold,
        "metrics": evaluate(queries, rankings, a.threshold, routes),
        "threshold_sweep": sweep,
        "best_threshold_on_this_set_optimistic": best,
        "per_query": [
            {"id": q["id"], "difficulty": q["difficulty"], "target": q["_kind"], "gold": q["gold"],
             "top5": [[i, round(s, 3)] for s, i in r[:5]], "abstained": r[0][0] < a.threshold}
            for q, r in zip(queries, rankings)
        ],
    }
    Path(a.out).write_text(json.dumps(result, indent=1) + "\n")
    m = result["metrics"]
    print(f"pages={result['pages']} (functional {result['pages_functional']}, decoy {result['pages_decoy']}) "
          f"queries={len(queries)} threshold={a.threshold}")
    print(f"{'group':24s} {'n':>4s} {'P@1':>6s} {'sP@1':>6s} {'R@5':>6s} {'MRR10':>6s} {'Rte@1':>6s} {'abst':>6s} {'fAbst':>6s} {'E2E':>6s}")
    for k, v in m.items():
        print(f"{k:24s} {v['n_answerable'] + v['n_none_fits']:4d} "
              + " ".join(f"{v.get(x, float('nan')):6.3f}" for x in
                         ["precision@1", "strict_p@1", "recall@5", "mrr@10", "route@1", "none_fits_abstention",
                          "false_abstention", "end_to_end_accuracy"]))
    print("best threshold on this set (optimistic):", best)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
