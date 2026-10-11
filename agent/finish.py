"""Finish gate: code checks (no LLM judge) that run before the agent answers.
(a) applied state == intent  (b) every number is traceable  (c) no repeated calls  (d) step budget."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contract import Contract
from .facts import DATE_RE, NUM_RE, Facts, dec
from .gates import canon_call
from .session import Call
from .slots import canonical, diff_requests


@dataclass
class Expectation:
    """What the user asked for, as slots extracted in step [1] and completed by code."""
    action: str                                  # analyze | records | related | navigate
    request: dict | None = None                  # analyze request / records filters+period
    records_view: str | None = None
    entity: tuple[str, int] | None = None
    page: str | None = None
    scenario_id: str | None = None

    def describe(self) -> dict:
        d: dict[str, Any] = {"action": self.action}
        if self.request:
            d["request"] = {k: v for k, v in self.request.items() if v not in (None, {}, "none")}
        if self.records_view:
            d["records_view"] = self.records_view
        if self.entity:
            d["entity"] = list(self.entity)
        if self.page:
            d["page"] = self.page
        return d


@dataclass
class Violation:
    code: str    # state_mismatch | no_call | unsupported_number | loop | budget
    message: str


@dataclass
class FinishReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def hint(self) -> str:
        return "FINISH CHECK FAILED: " + " | ".join(f"[{v.code}] {v.message}" for v in self.violations)


# ------------------------------------------------------------------------------ (a)
def last_ok(calls: list[Call], name: str) -> Call | None:
    for c in reversed(calls):
        if c.ok and c.name == name:
            return c
    return None


def check_state_match(exp: Expectation, calls: list[Call], c: Contract) -> list[Violation]:
    out: list[Violation] = []
    if exp.action == "analyze":
        call = last_ok(calls, "analyze")
        if call is None:
            return [Violation("no_call", f"no successful analyze call. Call analyze with exactly: {_j(exp.request)}")]
        applied = call.applied or {}
        diffs = diff_requests(exp.request or {}, applied, c)
        if diffs:
            out.append(Violation("state_mismatch", "the applied state differs from what the user asked: " + "; ".join(diffs)
                                 + f". Call analyze again with exactly: {_j(exp.request)}"))
    elif exp.action == "records":
        call = last_ok(calls, "records")
        if call is None:
            return [Violation("no_call", f"no successful records call. Call records(view='{exp.records_view}', ...) with {_j(exp.request)}")]
        ap = call.applied or {}
        want = {k: v for k, v in ((exp.request or {}).get("filters") or {}).items() if v not in (None, "all")}
        got = {k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "all")}
        diffs = []
        if call.data.get("entity") != exp.records_view:
            diffs.append(f"view: want {exp.records_view!r}, got {call.data.get('entity')!r}")
        for k in sorted(set(want) | set(got)):
            if want.get(k) != got.get(k):
                diffs.append(f"filters.{k}: want {want.get(k)!r}, got {got.get(k)!r}")
        for k in ("start", "end"):
            if (exp.request or {}).get(k) != ap.get(k):
                diffs.append(f"{k}: want {(exp.request or {}).get(k)!r}, got {ap.get(k)!r}")
        if diffs:
            out.append(Violation("state_mismatch", "records call differs from the request: " + "; ".join(diffs)))
    elif exp.action == "related":
        call = last_ok(calls, "related")
        if call is None or (call.args.get("entity_type"), call.args.get("entity_id")) != exp.entity:
            out.append(Violation("no_call", f"call related(entity_type, entity_id) for {exp.entity}"))
    elif exp.action == "navigate":
        call = last_ok(calls, "open_page")
        if call is None:
            out.append(Violation("no_call", f"call open_page for {exp.page or exp.scenario_id}"))
    return out


def _j(x: Any) -> str:
    import json
    return json.dumps(x, separators=(",", ":"), default=str)


# ------------------------------------------------------------------------------ (b)
def draft_numbers(text: str) -> list[tuple[str, Decimal]]:
    text = DATE_RE.sub(" ", text)
    out = []
    for m in NUM_RE.finditer(text):
        d = dec(m.group())
        if d is not None:
            out.append((m.group(), d))
    return out


def check_numbers(draft: str, facts: Facts, calls: list[Call], user_text: str, exp: Expectation | None = None) -> list[Violation]:
    allowed: set[Decimal] = set(facts.numbers)
    for m in NUM_RE.finditer(DATE_RE.sub(" ", user_text)):
        d = dec(m.group())
        if d is not None:
            allowed.add(d)
    for m in DATE_RE.finditer(user_text):
        for part in m.group().split("-"):
            allowed.add(Decimal(int(part)))
    if exp and exp.request:
        for k in ("start", "end", "compare_start", "compare_end"):
            v = exp.request.get(k)
            if v:
                for part in str(v).split("-"):
                    allowed.add(Decimal(int(part)))
        if exp.request.get("top_n"):
            allowed.add(Decimal(exp.request["top_n"]))
    rows = max([len(c.data.get("rows") or []) for c in calls if c.ok and c.name == "analyze"] or [0])
    cap = max(rows, facts.small_int_cap) + 1
    bad: list[str] = []
    for tok, d in draft_numbers(draft):
        if d in allowed or abs(d) in allowed or -d in allowed:
            continue
        places = len(tok.rstrip("%").split(".")[1]) if "." in tok else 0
        if places == 0 and "%" not in tok and abs(d) <= cap and d == d.to_integral_value() and "," not in tok:
            continue  # a small count such as "top 3"
        if places > 0 and any(a for a in allowed if _scale(a) > places and _round(a, places) == d):
            continue  # an honest rounding of a traced value
        bad.append(tok)
    if bad:
        return [Violation("unsupported_number", f"these numbers are not in any tool result or code-computed fact: {bad}. "
                          "Quote figures exactly as given in the facts, and do not invent others.")]
    return []


def _scale(d: Decimal) -> int:
    return max(0, -d.as_tuple().exponent)  # type: ignore[operator]


def _round(d: Decimal, places: int) -> Decimal:
    return d.quantize(Decimal(1).scaleb(-places))


CURRENCY_RE = re.compile(r"\b(usd|dollars?|euros?|eur|gbp|pounds?|rupees?|inr)\b|[$€£₹]", re.I)
CAUSE_RE = re.compile(r"\b(because|caused by|due to|as a result of|driven by the fact)\b", re.I)


def check_style(draft: str) -> list[Violation]:
    """Rules from the data contract: the source states no currency, and the data records no causes."""
    out = []
    if CURRENCY_RE.search(draft):
        out.append(Violation("currency", "do not name or symbolise a currency: the source states none; say 'sample amount (currency not stated in source)' or just give the number"))
    if CAUSE_RE.search(draft):
        out.append(Violation("cause", "do not claim a cause: the data only shows where a change is concentrated"))
    return out


# ------------------------------------------------------------------------------ (c), (d)
def check_loops(calls: list[Call]) -> list[Violation]:
    seen: set[str] = set()
    for c in calls:
        k = canon_call(c.name, c.args)
        if k in seen:
            return [Violation("loop", f"the call {c.name} was repeated with identical arguments")]
        seen.add(k)
    return []


def check_budget(attempts: int, budget: int) -> list[Violation]:
    return [Violation("budget", f"{attempts} calls exceed the budget of {budget}")] if attempts > budget else []


def finish_checks(exp: Expectation, calls: list[Call], c: Contract, attempts: int, budget: int) -> FinishReport:
    """State match + loops + budget (the numbers check runs on the drafted answer separately)."""
    rep = FinishReport()
    rep.violations += check_state_match(exp, calls, c)
    rep.violations += check_loops(calls)
    rep.violations += check_budget(attempts, budget)
    return rep
