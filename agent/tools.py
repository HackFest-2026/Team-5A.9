"""The six task-level tools. Each takes typed arguments, returns compact data plus an `applied` echo,
and gives recovery hints in its errors. Gates run *before* execute(); this module does not validate."""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote

from .adapters.base import Backend, BackendError
from .contract import Contract
from .docs import LLMRetriever, PageIndex
from .session import DIM_KIND, Call, Session
from .slots import RECORD_VIEWS, RELATED_TYPES, RESOLVE_TYPES

TOOL_NAMES = ("lookup", "resolve", "analyze", "records", "related", "open_page")
DETAIL_PAGES = {"customer": "customer", "order": "order", "item": "stock_item", "supplier": "supplier", "purchase": "purchase_order"}
LIST_PAGES = ("overview", "fulfilment", "supply", "analysis")


def tool_specs(c: Contract) -> list[dict]:
    """OpenAI-style tool definitions, generated from the Contract so enums can never drift."""
    flt_props: dict[str, Any] = {f: {"type": "integer"} for f in c.id_filters}
    flt_props["sales_territory"] = {"type": "string", "enum": c.territories}
    flt_props["status"] = {"type": "string", "enum": c.status_values}
    filters = {"type": "object", "properties": flt_props, "additionalProperties": False,
               "description": "Only set filters the user asked for. IDs must come from resolve() or the user."}
    date = {"type": "string", "description": "YYYY-MM-DD"}
    return [
        {"type": "function", "function": {
            "name": "lookup",
            "description": "Meaning of a business word (glossary: measure, caveat, whether it is ambiguous or unsupported) "
                           "or find an app page. Example: lookup(term='revenue') -> M10 with caveat.",
            "parameters": {"type": "object", "properties": {
                "term": {"type": "string"},
                "kind": {"type": "string", "enum": ["glossary", "page"]}}, "required": ["term"]}}},
        {"type": "function", "function": {
            "name": "resolve",
            "description": "Turn a name the user typed into an ID. Statuses: unique / ambiguous (ask the user) / none. "
                           "Example: resolve(kind='supplier', name='Litware') -> supplier 7.",
            "parameters": {"type": "object", "properties": {
                "kind": {"type": "string", "enum": list(RESOLVE_TYPES)},
                "name": {"type": "string"}}, "required": ["kind", "name"]}}},
        {"type": "function", "function": {
            "name": "analyze",
            "description": "Any aggregate: a measure, optionally broken down by a dimension, filtered, sorted, and compared "
                           "with a baseline period (end dates are exclusive). Example: May vs April orders by territory = "
                           "analyze(measure_id='M01', start='2016-05-01', end='2016-06-01', compare_start='2016-04-01', "
                           "compare_end='2016-05-01', group_by='sales_territory').",
            "parameters": {"type": "object", "properties": {
                "measure_id": {"type": "string", "enum": list(c.measures)},
                "date_basis": {"type": "string", "enum": sorted({b for m in c.measures.values() for b in m['date_bases']})},
                "start": date, "end": date, "compare_start": date, "compare_end": date,
                "group_by": {"type": "string", "enum": c.dimensions},
                "filters": filters,
                "sort": {"type": "string", "enum": ["value_desc", "value_asc", "label_asc", "label_desc",
                                                    "change_desc", "change_asc", "abs_change_desc"]},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 50}},
                "required": ["measure_id"]}}},
        {"type": "function", "function": {
            "name": "records",
            "description": "Inspect source rows (orders, purchase lines, ...). Example: records(view='orders', start='2016-05-01', "
                           "end='2016-06-01', filters={'customer_id': 950}).",
            "parameters": {"type": "object", "properties": {
                "view": {"type": "string", "enum": list(RECORD_VIEWS)},
                "date_basis": {"type": "string", "enum": ["order_date", "none", "purchase_order_date", "expected_delivery_date"]},
                "start": date, "end": date, "filters": filters,
                "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
                "required": ["view"]}}},
        {"type": "function", "function": {
            "name": "related",
            "description": "One-hop context for an entity: linked records, counts and next steps. "
                           "Example: related(entity_type='stock_item', entity_id=80).",
            "parameters": {"type": "object", "properties": {
                "entity_type": {"type": "string", "enum": list(RELATED_TYPES)},
                "entity_id": {"type": "integer"}}, "required": ["entity_type", "entity_id"]}}},
        {"type": "function", "function": {
            "name": "open_page",
            "description": "Get the deep link that shows the result in the app (read-only, nothing changes). "
                           "Example: open_page(page='customer', id=950).",
            "parameters": {"type": "object", "properties": {
                "page": {"type": "string", "enum": list(LIST_PAGES) + list(DETAIL_PAGES)},
                "id": {"type": "integer"},
                "scenario_id": {"type": "string", "enum": c.scenarios}}, "required": ["page"]}}},
    ]


def compact_analyze(d: dict, max_rows: int = 12) -> dict:
    keep = ("measure", "dimension", "total", "total_baseline", "total_current", "change", "pct_change", "periods",
            "group_count", "deep_link")
    out = {k: d[k] for k in keep if k in d}
    ap = d.get("applied", {})
    out["applied"] = {k: v for k, v in ap.items() if v not in (None, "") and k not in ("dataset_version",)}
    out["applied"]["filters"] = {k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "all")}
    rows = d.get("rows") or []
    out["rows"] = rows[:max_rows]
    if len(rows) > max_rows:
        out["rows_truncated"] = len(rows) - max_rows
    return out


def compact_related(d: dict, max_items: int = 5) -> dict:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k in ("query_wall_seconds", "next_steps"):
            continue
        out[k] = v[:max_items] if isinstance(v, list) else v
    out["next_steps"] = [{"label": s.get("label"), "operation": s.get("operation"), "request": s.get("request")}
                         for s in (d.get("next_steps") or [])[:4]]
    return out


def compact_records(d: dict, max_rows: int = 6) -> dict:
    out = {k: d[k] for k in ("entity", "total_rows", "has_more", "limit", "offset", "provenance") if k in d}
    out["rows"] = (d.get("rows") or [])[:max_rows]
    ap = d.get("applied_filters") or {}
    out["applied"] = {k: v for k, v in ap.items() if v not in (None, "") and k != "dataset_version"}
    out["applied"]["filters"] = {k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "all")}
    return out


class ToolBox:
    def __init__(self, backend: Backend, contract: Contract, session: Session, pages: "LLMRetriever | PageIndex | None" = None):
        self.backend, self.c, self.s, self.pages = backend, contract, session, pages

    # ------------------------------------------------------------------ dispatch
    def execute(self, name: str, args: dict) -> Call:
        t0 = time.time()
        try:
            fn = getattr(self, f"_{name}")
        except AttributeError:
            return Call(name, args, False, {}, f"unknown tool '{name}'. Tools: {', '.join(TOOL_NAMES)}")
        try:
            call = fn(args)
        except BackendError as e:
            call = Call(name, args, False, {}, f"backend unavailable: {e}")
        call.latency = time.time() - t0
        return call

    def _real_routes(self) -> set[str]:
        routes = {v["route"] for v in self.c.views.values()}
        for v in self.c.views.values():
            routes.update(v.get("detail_destinations") or [])
        return routes

    @staticmethod
    def _route_exists(route: str | None, real: set[str]) -> bool:
        if not route:
            return False
        path = route.split("?")[0]
        if path in real:
            return True
        return any("{id}" in r and re.fullmatch(re.escape(r).replace(r"\{id\}", r"[^/]+"), path) for r in real)

    # --------------------------------------------------------------------- tools
    def _lookup(self, a: dict) -> Call:
        term, kind = a.get("term", ""), a.get("kind") or "glossary"
        if kind == "page":
            if self.pages is None:
                return Call("lookup", a, False, {}, "page search is not available")
            hits = self.pages.search(term, k=5)
            real = self._real_routes()
            for h in hits:  # a page the app does not have must never be opened or described as showing data
                h["available_in_app"] = self._route_exists(h.get("route"), real)
            return Call("lookup", a, True, {"pages": hits})
        hits = self.c.glossary_find(term)
        if not hits:
            return Call("lookup", a, True, {"matches": [], "hint": "no glossary entry; try kind='page' or ask the user"})
        out = []
        for g in hits:
            out.append({k: g.get(k) for k in ("term", "status", "maps_to", "note", "clarify_question", "unsupported_reply")})
        return Call("lookup", a, True, {"matches": out})

    def _resolve(self, a: dict) -> Call:
        kind, name = a["kind"], a["name"]
        r = self.backend.resolve(name, [kind], 5)
        if r.get("completed") is False:
            return Call("resolve", a, False, r, r.get("error"))
        for cand in r.get("candidates", []):
            self.s.registry.add(DIM_KIND.get(cand["type"], cand["type"]), cand["id"], "resolve")
        view = {"status": r.get("status"), "candidates": r.get("candidates", [])[:5], "ask": r.get("ask")}
        return Call("resolve", a, True, {**r, "view": view}, applied={"kind": kind, "name": name})

    def _analyze(self, a: dict) -> Call:
        r = self.backend.analyze(a)
        if r.get("completed") is False:
            return Call("analyze", a, False, r, r.get("error"))
        dim = DIM_KIND.get(r.get("dimension", {}).get("id", ""), None)
        for row in r.get("rows", []):
            if dim and row.get("key") is not None and not row.get("is_other"):
                self.s.registry.add(dim, row["key"], "analyze-row")
        return Call("analyze", a, True, r, applied=r.get("applied"), deep_link=r.get("deep_link"))

    def _records(self, a: dict) -> Call:
        req = {"id": a["view"], "filters": a.get("filters") or {}, "limit": a.get("limit", 50), "offset": 0}
        for k in ("date_basis", "start", "end", "scenario_id"):
            if a.get(k):
                req[k] = a[k]
        if "date_basis" not in req:
            req["date_basis"] = "order_date" if a["view"] in ("orders", "order_lines") and req.get("start") else "none"
        r = self.backend.records(req)
        if r.get("completed") is False:
            return Call("records", a, False, r, r.get("error"))
        self.s.registry.harvest(r.get("rows"), "records-row")
        return Call("records", a, True, r, applied=r.get("applied_filters"))

    def _related(self, a: dict) -> Call:
        r = self.backend.related(a["entity_type"], a["entity_id"], a.get("scenario_id", self.s.state.scenario_id))
        if r.get("completed") is False:
            return Call("related", a, False, r, r.get("error"))
        self.s.registry.add(a["entity_type"], a["entity_id"], "related")
        self.s.registry.harvest(r, "related")
        link = self.backend.route_for(a["entity_type"], a["entity_id"])
        return Call("related", a, True, r, applied={"entity_type": a["entity_type"], "entity_id": a["entity_id"]}, deep_link=link)

    def _open_page(self, a: dict) -> Call:
        page = a["page"]
        scen = a.get("scenario_id") or self.s.state.scenario_id
        if page in DETAIL_PAGES:
            if a.get("id") is None:
                return Call("open_page", a, False, {}, f"page '{page}' needs an id")
            link = self.backend.route_for(DETAIL_PAGES[page], a["id"])
            return Call("open_page", a, True, {"deep_link": link}, applied={"page": page, "id": a["id"]}, deep_link=link)
        view = self.c.views.get(page)
        if view is None:
            return Call("open_page", a, False, {}, f"unknown page '{page}'. Pages: {', '.join(self.c.views)}")
        if page == "analysis":
            # the analysis deep link is produced by the app itself from the validated state
            st = self.s.state
            if not st.measure_id:
                return Call("open_page", a, False, {}, "nothing to show yet: run analyze first")
            r = self.backend.analyze(st.to_request())
            if r.get("completed") is False:
                return Call("open_page", a, False, r, r.get("error"))
            return Call("open_page", a, True, {"deep_link": r["deep_link"]}, applied=r.get("applied"), deep_link=r["deep_link"])
        params = []
        if scen != "base":
            params.append(f"scenario_id={scen}")
        link = f"#/{page}" + (("?" + "&".join(params)) if params else "")
        return Call("open_page", a, True, {"deep_link": link}, applied={"page": page, "scenario_id": scen}, deep_link=link)

    # ---------------------------------------------------------- views for the model
    def view(self, call: Call) -> dict:
        """What the LLM sees of a call (compact; the full data stays in Call.data for checks)."""
        if not call.ok:
            return {"error": call.error, "completed": False}
        if call.name == "analyze":
            return compact_analyze(call.data)
        if call.name == "related":
            return compact_related(call.data)
        if call.name == "records":
            return compact_records(call.data)
        if call.name == "resolve":
            return call.data["view"]
        return call.data
