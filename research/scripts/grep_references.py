#!/usr/bin/env python3
"""Check arXiv full texts for references to the anchors.

Semantic Scholar and OpenAlex had little or no citation data for the
2026 anchors (VACP, EmbeWebAgent, Unbrowse, typed actions). This script fetches
the arXiv HTML of candidate 2026 papers and searches it for each anchor's title
or name. Candidates are the 2026 papers in data/citations_combined.csv and in
data/mind2web_citing_papers.csv, plus any ids passed on the command line.

Output: data/citations_fulltext_hits.csv (arxiv_id, title, html_ok, hits per anchor).
Results are cached in data/citations_cache/html_hits.json, so a re-run only
fetches new ids. Uses GREP_WORKERS (default 3) parallel requests.
Usage: python3 research/scripts/grep_references.py [extra arxiv ids...]
"""
import csv, json, os, re, sys, time
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "citations_cache", "html_hits.json")

PATTERNS = {
    "beyond_browsing": r"Beyond Browsing",
    "vacp": r"Visual Analytics Context Protocol|\bVACP\b",
    "embewebagent": r"EmbeWebAgent|Embedding Web Agents into Any Customized UI",
    "unbrowse": r"Internal APIs Are All You Need|Unbrowse",
    "typed_actions": r"Typed Actions Instead of Click|Web Verbs",
    "appworld": r"AppWorld",
    "tau_bench": r"τ-bench|τ-Bench|tau-bench|τ2-bench|τ²-bench|tau2-bench|Tool-Agent-User Interaction",
}
PATTERNS = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
WORKERS = int(os.environ.get("GREP_WORKERS", "3"))


def candidates():
    ids = {}
    for fn, tcol in (("citations_combined.csv", "title"), ("mind2web_citing_papers.csv", "title")):
        p = os.path.join(DATA, fn)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p)):
            ax = (r.get("arxiv_id") or "").strip()
            if ax and (ax.startswith("26") or str(r.get("year")) == "2026"):
                ids.setdefault(ax, r[tcol])
    for ax in sys.argv[1:]:
        ids.setdefault(ax, "")
    return ids


def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    ids = candidates()
    todo = [a for a in ids if a not in cache]
    print(f"{len(ids)} candidates, {len(todo)} to fetch", file=sys.stderr)
    def work(ax):
        for attempt in range(3):
            try:
                r = requests.get(f"https://arxiv.org/html/{ax}", timeout=60,
                                 headers={"User-Agent": "kletech-hackfest-citation-chase/1.0"})
            except requests.RequestException:
                time.sleep(5); continue
            if r.status_code in (429, 503):
                time.sleep(30); continue
            ok = r.status_code == 200 and "ltx_document" in r.text
            text = r.text if ok else ""
            m = re.search(r"<title>(.*?)</title>", text, re.S)
            return ax, {"html_ok": ok, "html_title": (m.group(1).strip() if m else ""),
                        **{k: len(p.findall(text)) for k, p in PATTERNS.items()}}
        return ax, None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for n, (ax, res) in enumerate(ex.map(work, todo)):
            if res is not None:
                cache[ax] = res
            if n % 50 == 0:
                json.dump(cache, open(CACHE, "w"))
                print(f"  {n}/{len(todo)}", file=sys.stderr)
    json.dump(cache, open(CACHE, "w"))
    out = os.path.join(DATA, "citations_fulltext_hits.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arxiv_id", "title", "html_ok"] + list(PATTERNS) + ["n_anchors_fulltext"])
        for ax, title in sorted(ids.items()):
            c = cache.get(ax, {})
            hits = [c.get(k, 0) for k in PATTERNS]
            w.writerow([ax, title or c.get("html_title", ""), c.get("html_ok")] + hits + [sum(1 for h in hits if h)])
    print("wrote", out)


if __name__ == "__main__":
    main()


def augment_anchor_csvs():
    """Append papers found only by full-text search to data/citations_<anchor>.csv
    (source = arxiv-fulltext). Self-matches (the anchor's own text) are skipped.
    fetch_citations.py rewrites these files, so run this script after it."""
    anchors_ax = {"beyond_browsing": "2410.16464", "vacp": "2603.29322", "embewebagent": "2602.14865",
                  "unbrowse": "2604.00694", "typed_actions": "2602.17245",
                  "appworld": "2407.18901", "tau_bench": "2406.12045"}
    hits = list(csv.DictReader(open(os.path.join(DATA, "citations_fulltext_hits.csv"))))
    for anchor, self_ax in anchors_ax.items():
        path = os.path.join(DATA, f"citations_{anchor}.csv")
        if not os.path.exists(path):
            continue
        rows = list(csv.DictReader(open(path)))
        have = {r["arxiv_id"] for r in rows if r["arxiv_id"]}
        fields = list(rows[0].keys()) if rows else ["title", "year", "venue", "arxiv_id", "doi", "citation_count",
                                                    "is_influential", "source", "abstract_snippet"]
        added = 0
        for h in hits:
            ax = h["arxiv_id"]
            if ax == self_ax or ax in have or not h[anchor].isdigit() or int(h[anchor]) == 0:
                continue
            title = re.sub(r"\s+", " ", h["title"] or "")
            rows.append({f: "" for f in fields} | {"title": title, "year": "20" + ax[:2], "arxiv_id": ax,
                                                    "source": "arxiv-fulltext"})
            added += 1
        if added:
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
        print(f"{anchor}: +{added} from full text", file=sys.stderr)


if __name__ == "__main__":
    augment_anchor_csvs()
