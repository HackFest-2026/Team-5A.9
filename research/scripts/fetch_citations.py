#!/usr/bin/env python3
"""Forward-citation chase for the anchor papers of the Domain 5A agent.

Re-run:  python3 research/scripts/fetch_citations.py   (from the repo root)
Optional: export S2_API_KEY=... for higher Semantic Scholar rate limits.

For each anchor (arXiv id) it:
  1. resolves the paper on Semantic Scholar (S2) and pages through
     /paper/arXiv:<id>/citations (limit=100, offset paging, retry+backoff on 429);
  2. resolves the same paper on OpenAlex (via the arXiv DOI 10.48550/arXiv.<id>,
     falling back to a title search) and pages through works?filter=cites:<W-id>;
  3. merges both lists (dedup by arXiv id, DOI, then normalised title);
  4. writes data/citations_<short>.csv and data/citations_combined.csv
     (deduplicated across anchors, with the list of anchors each paper cites).
Raw API responses are cached in data/citations_cache/ so a re-run is cheap;
delete that folder to force a fresh pull.
"""
import csv, json, os, re, sys, time, hashlib
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "citations_cache")
os.makedirs(CACHE, exist_ok=True)

ANCHORS = {
    "beyond_browsing": "2410.16464",
    "vacp": "2603.29322",
    "embewebagent": "2602.14865",
    "unbrowse": "2604.00694",
    "typed_actions": "2602.17245",
    "appworld": "2407.18901",
    "tau_bench": "2406.12045",
}
S2 = "https://api.semanticscholar.org/graph/v1"
OA = "https://api.openalex.org"
S2_FIELDS = "title,year,venue,externalIds,citationCount,abstract,isInfluential"
HEADERS = {"User-Agent": "kletech-hackfest-citation-chase/1.0"}
if os.environ.get("S2_API_KEY"):
    HEADERS["x-api-key"] = os.environ["S2_API_KEY"]
OA_MAILTO = os.environ.get("OPENALEX_MAILTO", "")


def get_json(url, params=None, tries=10):
    key = hashlib.sha1((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    delay = 3
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        except requests.RequestException as e:
            print("  net error", e, file=sys.stderr)
            time.sleep(delay); delay = min(delay * 2, 60); continue
        if r.status_code == 200:
            data = r.json()
            with open(path, "w") as f:
                json.dump(data, f)
            return data
        if r.status_code == 404:
            return None
        print(f"  HTTP {r.status_code} on {url} (try {i+1}), sleeping {delay}s", file=sys.stderr)
        time.sleep(delay); delay = min(delay * 2, 60)
    return None


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def s2_citations(arxiv_id):
    meta = get_json(f"{S2}/paper/arXiv:{arxiv_id}", {"fields": "title,year,citationCount,externalIds"})
    out, offset = [], 0
    while True:
        page = get_json(f"{S2}/paper/arXiv:{arxiv_id}/citations",
                        {"fields": S2_FIELDS, "limit": 100, "offset": offset})
        if not page:
            break
        for row in page.get("data", []):
            p = row.get("citingPaper") or {}
            if not p.get("title"):
                continue
            ext = p.get("externalIds") or {}
            out.append({
                "title": p["title"], "year": p.get("year") or "", "venue": p.get("venue") or "",
                "arxiv_id": ext.get("ArXiv") or "", "doi": ext.get("DOI") or "",
                "citation_count": p.get("citationCount") if p.get("citationCount") is not None else "",
                "is_influential": row.get("isInfluential"),
                "abstract": (p.get("abstract") or ""), "source": "s2",
                "s2_id": p.get("paperId") or "",
            })
        if "next" in page and page["next"]:
            offset = page["next"]
            time.sleep(1.2)
        else:
            break
    return meta, out


def oa_reconstruct(inv):
    if not inv:
        return ""
    pos = []
    for w, idxs in inv.items():
        for i in idxs:
            pos.append((i, w))
    return " ".join(w for _, w in sorted(pos))


def oa_works_for(arxiv_id, title=None):
    """All OpenAlex records for the anchor: the arXiv-DOI record plus any
    exact-title duplicates (e.g. the ACL/ICLR proceedings version), since
    OpenAlex splits citations across versions."""
    params = {"mailto": OA_MAILTO} if OA_MAILTO else None
    found = {}
    w = get_json(f"{OA}/works/https://doi.org/10.48550/arXiv.{arxiv_id}", params)
    if w and w.get("id"):
        found[w["id"]] = w
        title = title or w.get("title")
    if title:
        q = re.sub(r"[^\w\s:-]", " ", title)
        res = get_json(f"{OA}/works", {"search": q, "per-page": 10})
        for c in (res or {}).get("results", []):
            if norm_title(c.get("title")) == norm_title(title):
                found[c["id"]] = c
    return list(found.values())


def oa_citations(work_id):
    short = work_id.rsplit("/", 1)[-1]
    out, cursor = [], "*"
    while cursor:
        page = get_json(f"{OA}/works", {"filter": f"cites:{short}", "per-page": 200, "cursor": cursor})
        if not page:
            break
        for w in page.get("results", []):
            ids = w.get("ids") or {}
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            ax = ""
            m = re.search(r"arxiv\.(\d{4}\.\d{4,5})", doi, re.I)
            if m:
                ax = m.group(1)
            loc = (w.get("primary_location") or {}).get("source") or {}
            out.append({
                "title": w.get("title") or w.get("display_name") or "", "year": w.get("publication_year") or "",
                "venue": loc.get("display_name") or "", "arxiv_id": ax, "doi": doi,
                "citation_count": w.get("cited_by_count", ""), "is_influential": "",
                "abstract": oa_reconstruct(w.get("abstract_inverted_index")), "source": "openalex",
                "s2_id": "",
            })
        cursor = (page.get("meta") or {}).get("next_cursor")
        if not page.get("results"):
            break
        time.sleep(0.3)
    return out


def keyset(r):
    keys = []
    if r["arxiv_id"]:
        keys.append("ax:" + r["arxiv_id"].lower())
    if r["doi"]:
        keys.append("doi:" + r["doi"].lower())
    if r["title"]:
        keys.append("t:" + norm_title(r["title"]))
    return keys


def merge(rows):
    merged, index = [], {}
    for r in rows:
        hit = next((index[k] for k in keyset(r) if k in index), None)
        if hit is None:
            merged.append(dict(r)); hit = len(merged) - 1
        else:
            m = merged[hit]
            for f in ("year", "venue", "arxiv_id", "doi", "abstract", "s2_id"):
                if not m.get(f) and r.get(f):
                    m[f] = r[f]
            if m.get("is_influential") in ("", None) and r.get("is_influential") not in ("", None):
                m["is_influential"] = r["is_influential"]
            if r["source"] not in m["source"]:
                m["source"] += "+" + r["source"]
            try:
                m["citation_count"] = max(int(m["citation_count"] or 0), int(r["citation_count"] or 0))
            except ValueError:
                pass
        for k in keyset(merged[hit]):
            index[k] = hit
    return merged


COLS = ["title", "year", "venue", "arxiv_id", "doi", "citation_count", "is_influential", "source", "abstract_snippet"]


def write_csv(path, rows, extra=()):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(extra) + COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            r["abstract_snippet"] = re.sub(r"\s+", " ", r.get("abstract") or "")[:400]
            w.writerow(r)


def main():
    summary, combined = {}, []
    for short, ax in ANCHORS.items():
        print(f"== {short} arXiv:{ax}", file=sys.stderr)
        meta, s2rows = s2_citations(ax)
        title = (meta or {}).get("title")
        works = oa_works_for(ax, title)
        oarows = [r for w in works for r in oa_citations(w["id"])]
        rows = merge(s2rows + oarows)
        rows.sort(key=lambda r: (-(int(r["citation_count"]) if str(r["citation_count"]).isdigit() else 0)))
        write_csv(os.path.join(DATA, f"citations_{short}.csv"), rows)
        summary[short] = {"arxiv": ax, "s2_title": title, "s2_citationCount": (meta or {}).get("citationCount"),
                          "s2_rows": len(s2rows), "openalex_ids": [w["id"] for w in works],
                          "openalex_cited_by": sum(w.get("cited_by_count") or 0 for w in works), "openalex_rows": len(oarows),
                          "merged": len(rows)}
        for r in rows:
            r["anchor"] = short
            combined.append(r)
        print("  ", summary[short], file=sys.stderr)
    # cross-anchor dedup
    groups = {}
    order = []
    idx = {}
    for r in combined:
        hit = next((idx[k] for k in keyset(r) if k in idx), None)
        if hit is None:
            hit = len(order); order.append(dict(r, anchors=set()))
        g = order[hit]
        g["anchors"].add(r["anchor"])
        for f in ("year", "venue", "arxiv_id", "doi", "abstract"):
            if not g.get(f) and r.get(f):
                g[f] = r[f]
        if r.get("is_influential") is True:
            g["is_influential"] = True
        for k in keyset(g) + keyset(r):
            idx[k] = hit
    for g in order:
        g["n_anchors"] = len(g["anchors"])
        g["anchors"] = ";".join(sorted(g["anchors"]))
    order.sort(key=lambda g: (-g["n_anchors"], -(int(g["citation_count"]) if str(g["citation_count"]).isdigit() else 0)))
    write_csv(os.path.join(DATA, "citations_combined.csv"), order, extra=("n_anchors", "anchors"))
    with open(os.path.join(DATA, "citations_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
