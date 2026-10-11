#!/usr/bin/env python3
"""Keyword relevance screen over data/citations_combined.csv.

Writes data/citations_screened.csv: every citing paper with a relevance score
(title weighted 2x, abstract 1x) for the Domain 5A agent, sorted by
n_anchors then score. This is only a triage aid; the final shortlist in
research/citation_chase.md was chosen by reading abstracts and full texts.
Run after fetch_citations.py (and grep_references.py, which adds columns).
"""
import csv, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")

GROUPS = [  # (weight, regex)
    (3.0, r"agent[- ]ready|agentic web interface|agent[- ]native|declarativ|in-app|embedded agent|embedding (web )?agents|webmcp|"
          r"typed action|semantic action|api[- ]based|api[- ]first|api agents|hybrid|gui[- ]api|shadow api|function registry|"
          r"agent[- ]callable|tool program|web verbs?|structured (state|observation|interface)|context protocol|model context protocol|\bmcp\b"),
    (2.0, r"enterprise|\berp\b|\bcrm\b|business|analytic|dashboard|\bbi\b|spreadsheet|text-to-sql|\bsql\b|data analysis|tabular|"
          r"visual analytics|workflow automation|customer service|airline|retail"),
    (2.0, r"verif|faithful|hallucinat|grounded|guardrail|policy compliance|policy[- ]adherence|confirm|reliab|consisten|pass\^k|"
          r"rollback|undo|side effect|safety|audit|provenance"),
    (1.5, r"plan[- ]then[- ]execute|plan-and-execute|programmatic|code as action|code actions|compil|precondition|postcondition|"
          r"state machine|world model"),
    (1.0, r"benchmark|tool[- ]agent[- ]user|user simulat|multi-turn|tool use|tool-use|function calling|tool calling"),
    (-1.5, r"reinforcement learning|\bgrpo\b|policy optimization|\brl\b|fine-tun|pretrain|survey|review of"),
]
GROUPS = [(w, re.compile(p, re.I)) for w, p in GROUPS]


def score(title, abstract):
    s = 0.0
    for w, rx in GROUPS:
        if rx.search(title or ""):
            s += 2 * w
        if rx.search(abstract or ""):
            s += w
    return round(s, 1)


def main():
    src = os.path.join(DATA, "citations_combined.csv")
    rows = list(csv.DictReader(open(src)))
    ft = {}
    ftp = os.path.join(DATA, "citations_fulltext_hits.csv")
    if os.path.exists(ftp):
        for h in csv.DictReader(open(ftp)):
            names = [k for k in ("beyond_browsing", "vacp", "embewebagent", "unbrowse", "typed_actions",
                                 "appworld", "tau_bench") if h[k].isdigit() and int(h[k]) > 0]
            ft[h["arxiv_id"]] = ";".join(names)
    for r in rows:
        r["relevance_score"] = score(r["title"], r["abstract_snippet"])
        r["fulltext_mentions"] = ft.get(r["arxiv_id"], "")
    rows.sort(key=lambda r: (-int(r["n_anchors"]), -r["relevance_score"]))
    cols = ["relevance_score", "fulltext_mentions"] + [c for c in rows[0].keys() if c not in ("relevance_score", "fulltext_mentions")]
    with open(os.path.join(DATA, "citations_screened.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows screened")


if __name__ == "__main__":
    main()
