"""Documentation retrieval over the page/component catalogue: BM25 + bge-m3 dense, fused with RRF.
Ranking uses text only (title, module, description, widgets, filters, keywords), never ids, routes or flags."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from .config import Config

_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to in on for and or is are was were be by with at as it this that from how what which show me my our we i do does did".split())


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOK.findall(text.lower()):
        if t in _STOP:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def page_text(p: dict) -> str:
    parts = [p.get("title", ""), p.get("module", ""), p.get("page_type", ""), p.get("description", "")]
    parts += list(p.get("widgets") or []) + list(p.get("filters") or []) + list(p.get("keywords") or [])
    return ". ".join(x for x in parts if x)


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(len(docs), 1)
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = tokens(query)
        out = np.zeros(len(self.tf))
        for i, c in enumerate(self.tf):
            s = 0.0
            for t in q:
                if t in c:
                    f = c[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            out[i] = s
        return out


class Embedder:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = httpx.Client(timeout=120)

    def embed(self, texts: list[str], batch: int = 32) -> np.ndarray:
        vecs = []
        for i in range(0, len(texts), batch):
            r = self.http.post(
                f"{self.cfg.embed_url}/embeddings",
                json={"model": self.cfg.embed_model, "input": texts[i : i + batch]},
                headers={"Authorization": "Bearer EMPTY"},
            )
            r.raise_for_status()
            vecs += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        a = np.array(vecs, dtype=np.float32)
        return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


class LLMRetriever:
    """Two-stage documentation retrieval driven by the LLM (Beyond Browsing): stage 1 picks the relevant modules,
    stage 2 ranks the pages of those modules. Output ids are enumerated in the JSON schema, so a page that is not
    in the catalogue can never be returned. No lexical or embedding scoring is involved."""

    def __init__(self, pages: list[dict], llm: Any, max_modules: int = 3, top_k: int = 5):
        self.pages, self.llm, self.max_modules, self.top_k = pages, llm, max_modules, top_k
        self.by_module: dict[str, list[dict]] = {}
        for p in pages:
            self.by_module.setdefault(p.get("module") or "Other", []).append(p)

    def _modules_prompt(self, query: str) -> list[dict]:
        lines = []
        for m, ps in sorted(self.by_module.items()):
            sample = "; ".join(p["title"] for p in ps[:6])
            lines.append(f"- {m} ({len(ps)} pages), e.g. {sample}")
        sys = ("You help a user find a page in a business app. First decide which modules of the app could hold the page. "
               "Pick the most likely module first and at most %d modules. Modules:\n%s" % (self.max_modules, "\n".join(lines)))
        return [{"role": "system", "content": sys}, {"role": "user", "content": query}]

    def _rank_prompt(self, query: str, cands: list[dict]) -> list[dict]:
        lines = [f"[{p['id']}] {p['title']}: {(p.get('description') or '')[:150]}" for p in cands]
        sys = ("You help a user find the page of a business app that answers their request. Rank the best matching pages, "
               "best first (at most %d), using their id in brackets. Prefer the page whose purpose matches the request, "
               "not one that merely shares words.\nPAGES:\n%s" % (self.top_k, "\n".join(lines)))
        return [{"role": "system", "content": sys}, {"role": "user", "content": query}]

    def rank_ids(self, query: str) -> list[str]:
        mods = list(self.by_module)
        s1 = {"type": "object", "properties": {"modules": {"type": "array", "items": {"enum": mods}, "minItems": 1,
                                                           "maxItems": self.max_modules}}, "required": ["modules"]}
        obj, _ = self.llm.json_out(self._modules_prompt(query), s1, "modules", max_tokens=60)
        chosen = [m for m in dict.fromkeys(obj.get("modules", [])) if m in self.by_module][: self.max_modules]
        cands = [p for m in chosen for p in self.by_module[m]]
        ids = [p["id"] for p in cands]
        s2 = {"type": "object", "properties": {"ranking": {"type": "array", "items": {"enum": ids}, "minItems": 1,
                                                           "maxItems": self.top_k}}, "required": ["ranking"]}
        obj2, _ = self.llm.json_out(self._rank_prompt(query, cands), s2, "ranking", max_tokens=80)
        return list(dict.fromkeys(obj2.get("ranking", [])))

    def search(self, query: str, k: int = 5) -> list[dict]:
        by_id = {p["id"]: p for p in self.pages}
        out = []
        for i in self.rank_ids(query)[:k]:
            p = by_id[i]
            out.append({"id": p["id"], "title": p["title"], "route": p.get("route"), "module": p.get("module"),
                        "description": (p.get("description") or "")[:200]})
        return out


class PageIndex:
    def __init__(self, pages: list[dict], cfg: Config, cache_dir: Path | None = None, dense: bool = True):
        self.pages = pages
        self.texts = [page_text(p) for p in pages]
        self.bm25 = BM25(self.texts)
        self.emb: np.ndarray | None = None
        self.embedder: Embedder | None = None
        if dense:
            self.embedder = Embedder(cfg)
            key = hashlib.sha1(("|".join(self.texts) + cfg.embed_model).encode()).hexdigest()[:16]
            cache = (cache_dir or cfg.trace_dir) / f"page_emb_{key}.npy"
            try:
                if cache.exists():
                    self.emb = np.load(cache)
                else:
                    self.emb = self.embedder.embed(self.texts)
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    np.save(cache, self.emb)
            except (httpx.HTTPError, OSError):
                self.emb = None  # dense unavailable: fall back to BM25 only

    def rank(self, query: str, mode: str = "hybrid") -> list[int]:
        b = self.bm25.scores(query)
        order_b = list(np.argsort(-b, kind="stable"))
        if mode == "bm25" or self.emb is None or self.embedder is None:
            return [int(i) for i in order_b]
        q = self.embedder.embed([query])[0]
        d = self.emb @ q
        order_d = list(np.argsort(-d, kind="stable"))
        if mode == "dense":
            return [int(i) for i in order_d]
        rrf: dict[int, float] = {}
        for order in (order_b, order_d):
            for r, i in enumerate(order[:60]):
                rrf[int(i)] = rrf.get(int(i), 0.0) + 1.0 / (60 + r + 1)
        return sorted(rrf, key=lambda i: -rrf[i])

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        out = []
        for i in self.rank(query, mode)[:k]:
            p = self.pages[i]
            out.append({"id": p["id"], "title": p["title"], "route": p.get("route"), "module": p.get("module"),
                        "description": (p.get("description") or "")[:200]})
        return out
