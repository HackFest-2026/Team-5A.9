"""Gates that run in code BEFORE a tool is executed: schema, grounding, read-before-write, loop and budget.
A rejected call costs one repair attempt; the message tells the model exactly how to fix it."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .contract import Contract
from .session import FILTER_KIND, Call, Session
from .slots import RECORD_VIEWS, RELATED_TYPES, RESOLVE_TYPES
from .tools import DETAIL_PAGES, LIST_PAGES, TOOL_NAMES

DETAIL_KIND = {"customer": "customer", "order": "order", "item": "stock_item", "supplier": "supplier", "purchase": "purchase_order"}


@dataclass
class Verdict:
    ok: bool
    gate: str = ""
    messages: list[str] = field(default_factory=list)
    args: dict | None = None  # normalised arguments to execute when ok

    def hint(self) -> str:
        return f"[{self.gate} gate] " + " | ".join(self.messages)


def canon_call(name: str, args: dict) -> str:
    return name + ":" + json.dumps(args, sort_keys=True, default=str)


class Gates:
    """`state_changing` names tools that would modify the app. v1 has none, so the read-before-write gate is
    checked on every call but never triggered; it is unit-tested with a fake tool."""

    def __init__(self, contract: Contract, session: Session, step_budget: int = 8,
                 state_changing: set[str] | None = None, enabled: bool = True):
        self.c, self.s = contract, session
        self.step_budget = step_budget
        self.state_changing = state_changing or set()
        self.enabled = enabled

    # ---------------------------------------------------------------- entry point
    def check(self, name: str, args: dict, turn_calls: list[Call], attempts: int, user_confirmed: bool = False) -> Verdict:
        if not self.enabled:
            return Verdict(True, "off", args=args)
        if name not in TOOL_NAMES and name not in self.state_changing:
            return Verdict(False, "schema", [f"unknown tool '{name}'. Available tools: {', '.join(TOOL_NAMES)}"])
        if attempts >= self.step_budget:
            return Verdict(False, "budget", [f"step budget of {self.step_budget} calls is used up; answer with what you have"])
        if not isinstance(args, dict) or "__unparsed__" in args:
            return Verdict(False, "schema", ["arguments must be a JSON object"])
        # loop detector: an identical call that already succeeded adds nothing
        key = canon_call(name, args)
        if any(canon_call(c.name, c.args) == key and c.ok for c in turn_calls):
            return Verdict(False, "loop", ["identical call already made this turn; use its result instead of repeating it"])
        v = self._schema(name, args)
        if not v.ok:
            return v
        a = v.args if v.args is not None else args
        g = self._grounding(name, a)
        if not g.ok:
            return g
        w = self._read_before_write(name, a, turn_calls, user_confirmed)
        if not w.ok:
            return w
        return Verdict(True, "ok", args=a)

    # --------------------------------------------------------------------- schema
    def _schema(self, name: str, a: dict) -> Verdict:
        errs: list[str] = []
        if name == "analyze":
            norm, errs = self.c.validate_analyze(a)
            return Verdict(True, "schema", args=norm) if not errs else Verdict(False, "schema", errs)
        if name == "records":
            if a.get("view") not in RECORD_VIEWS:
                errs.append(f"view must be one of {list(RECORD_VIEWS)}")
            errs += self._check_filters(a.get("filters") or {}, allow_status=True)
            for k in ("start", "end"):
                if a.get(k) and len(str(a[k])) != 10:
                    errs.append(f"{k} must be YYYY-MM-DD")
            if bool(a.get("start")) != bool(a.get("end")):
                errs.append("give both start and end, or neither")
            extra = set(a) - {"view", "date_basis", "start", "end", "filters", "limit", "scenario_id"}
            if extra:
                errs.append(f"unknown field(s) {sorted(extra)}")
            if not errs:
                a = dict(a)
                a["filters"] = {k: v for k, v in (a.get("filters") or {}).items() if v is not None}
            return Verdict(True, "schema", args=a) if not errs else Verdict(False, "schema", errs)
        if name == "related":
            if a.get("entity_type") not in RELATED_TYPES:
                errs.append(f"entity_type must be one of {list(RELATED_TYPES)}")
            if not isinstance(a.get("entity_id"), int):
                errs.append("entity_id must be an integer")
            return Verdict(not errs, "schema", errs, a)
        if name == "resolve":
            if a.get("kind") not in RESOLVE_TYPES:
                errs.append(f"kind must be one of {list(RESOLVE_TYPES)}")
            if not str(a.get("name", "")).strip():
                errs.append("name is required")
            return Verdict(not errs, "schema", errs, a)
        if name == "open_page":
            page = a.get("page")
            if page not in LIST_PAGES and page not in DETAIL_PAGES:
                errs.append(f"page '{page}' does not exist in the app. Pages: {list(LIST_PAGES) + list(DETAIL_PAGES)}")
            if page in DETAIL_PAGES and not isinstance(a.get("id"), int):
                errs.append(f"page '{page}' needs an integer id")
            return Verdict(not errs, "schema", errs, a)
        if name == "lookup":
            if not str(a.get("term", "")).strip():
                errs.append("term is required")
            return Verdict(not errs, "schema", errs, a)
        return Verdict(True, "schema", args=a)

    def _check_filters(self, flt: dict, allow_status: bool) -> list[str]:
        errs = []
        for k, v in flt.items():
            if v is None:
                continue
            if k == "sales_territory":
                if v not in self.c.territories:
                    errs.append(f"sales_territory '{v}' is not valid. Use one of {self.c.territories}")
            elif k == "status":
                if v not in self.c.status_values:
                    errs.append(f"status '{v}' is not valid. Use one of {self.c.status_values}")
            elif k in FILTER_KIND:
                if not isinstance(v, int):
                    errs.append(f"filter {k} must be an integer id")
            else:
                errs.append(f"unknown filter '{k}'. Filters: {self.c.id_filters + ['sales_territory', 'status']}")
        return errs

    # ------------------------------------------------------------------ grounding
    def _grounding(self, name: str, a: dict) -> Verdict:
        """Every entity ID must come from resolve(), a result row, or the user's own words."""
        bad: list[str] = []
        reg = self.s.registry
        if name in ("analyze", "records"):
            for k, v in (a.get("filters") or {}).items():
                if k in FILTER_KIND and v is not None and not reg.has(FILTER_KIND[k], v):
                    bad.append(f"{k}={v} was never returned by resolve() or shown in a result and the user did not give it")
        elif name == "related":
            if not reg.has(a["entity_type"], a["entity_id"]):
                bad.append(f"{a['entity_type']} id {a['entity_id']} was never returned by resolve() or a result")
        elif name == "open_page" and a.get("page") in DETAIL_KIND:
            if not reg.has(DETAIL_KIND[a["page"]], a.get("id")):
                bad.append(f"{a['page']} id {a.get('id')} was never returned by resolve() or a result")
        if bad:
            return Verdict(False, "grounding", bad + ["call resolve(kind, name) with the name the user typed, then use the id it returns. Never invent ids."])
        return Verdict(True, "grounding", args=a)

    # ------------------------------------------------------------ read before write
    def _read_before_write(self, name: str, a: dict, turn_calls: list[Call], confirmed: bool) -> Verdict:
        if name not in self.state_changing:
            return Verdict(True, "rbw", args=a)
        target = a.get("id") or a.get("entity_id")
        read = any(c.ok and c.name in ("records", "related") and (c.args.get("entity_id") == target or
                   (c.args.get("filters") or {}).get(a.get("filter_key", "")) == target) for c in turn_calls)
        msgs = []
        if not read:
            msgs.append(f"read the entity first (records/related) before calling {name}")
        if not confirmed:
            msgs.append(f"{name} changes state: the user must explicitly confirm before it runs")
        return Verdict(not msgs, "read_before_write", msgs, a)
