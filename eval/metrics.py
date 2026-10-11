"""Scoring against the v2 answer key. Pure code: no LLM judge. Follows evaluation/v2/README.md."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, unquote_plus

from agent.contract import Contract
from agent.facts import derive
from agent.finish import Expectation, check_numbers
from agent.loop import AgentResult
from agent.slots import canonical, diff_requests

DATA_TOOLS = ("analyze", "records", "related")
MONEY_MEASURES = ("M10", "M11")


# --------------------------------------------------------------------------- views
def norm_view(view: str | None, c: Contract) -> tuple[str, frozenset] | None:
    """Hash path plus an unordered set of params, with defaults dropped (README: a missing param counts as its default)."""
    if not view:
        return None
    path, _, query = view.partition("?")
    params = {k: unquote_plus(v) for k, v in parse_qsl(query, keep_blank_values=False)}
    if path.startswith("#/analysis"):
        mid = params.get("measure_id")
        m = c.measures.get(mid or "", {})
        has_cmp = "compare_start" in params
        defaults = {"scenario_id": "base", "top_n": "10", "group_by": "none",
                    "date_basis": m.get("default_date_basis"),
                    "sort": "abs_change_desc" if has_cmp else "value_desc", "status": "all"}
        params = {k: v for k, v in params.items() if defaults.get(k) != v}
    else:
        params = {k: v for k, v in params.items() if not (k == "scenario_id" and v == "base")}
    return path, frozenset(params.items())


# --------------------------------------------------------------------------- numbers
def _d(x: Any) -> Decimal | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        return Decimal(str(x))
    except InvalidOperation:
        return None


def num_eq(a: Any, b: Any, tol: float = 0.0) -> bool:
    da, db = _d(a), _d(b)
    if da is None or db is None:
        return a == b
    return abs(da - db) <= Decimal(str(tol))


def _flatten(o: Any, out: list) -> None:
    if isinstance(o, dict):
        for v in o.values():
            _flatten(v, out)
    elif isinstance(o, list):
        for v in o:
            _flatten(v, out)
    else:
        out.append(o)


def analytic_ok(step: dict, calls: list, op: str) -> tuple[bool, str]:
    exp = step.get("expected_result") or {}
    if not exp or step["expected_operation"] in ("clarify", "refuse", "navigate", "resolve"):
        return True, ""
    wanted = step["expected_operation"]
    call = next((c for c in reversed(calls) if c.ok and c.name == wanted), None)
    if call is None:
        return False, f"no successful {wanted} call"
    d = call.data
    if wanted == "analyze":
        for k in ("total", "total_baseline", "total_current", "change"):
            if k in exp and not num_eq(exp[k], d.get(k)):
                return False, f"{k}: want {exp[k]} got {d.get(k)}"
        if "pct_change" in exp and not num_eq(exp["pct_change"], d.get("pct_change"), 0.011):
            return False, f"pct_change: want {exp['pct_change']} got {d.get('pct_change')}"
        if "group_count" in exp and exp["group_count"] != d.get("group_count"):
            return False, f"group_count: want {exp['group_count']} got {d.get('group_count')}"
        for i, er in enumerate(exp.get("rows") or []):
            rows = d.get("rows") or []
            if i >= len(rows):
                return False, f"row {i} missing"
            for k, v in er.items():
                if k in ("groups", "is_other"):
                    continue  # cosmetic fields of the "All others" row
                got = rows[i].get(k)
                tol = 1e-4 if k in ("share", "share_of_change") else 0.0
                if k == "label" and isinstance(v, str) and v.startswith("All others") and isinstance(got, str) and got.startswith("All others"):
                    continue  # the group count in the label is cosmetic
                if not num_eq(v, got, tol):
                    return False, f"row {i}.{k}: want {v} got {got}"
        return True, ""
    if wanted == "records":
        if "total_rows" in exp and exp["total_rows"] != d.get("total_rows"):
            return False, f"total_rows: want {exp['total_rows']} got {d.get('total_rows')}"
        if "order_ids" in exp:
            got = [r.get("OrderID") for r in d.get("rows") or []]
            if got != exp["order_ids"][: len(got)] and set(got) != set(exp["order_ids"]):
                return False, f"order ids differ: want {exp['order_ids'][:5]}.. got {got[:5]}.."
        return True, ""
    # related: the answer key names fields differently from the API, so check that each key figure appears in the response
    flat: list = []
    _flatten(d, flat)
    missing = []
    for k, v in exp.items():
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            if not any(num_eq(v, x) or v == x for x in flat):
                missing.append(f"{k}={v}")
    return (not missing), ("missing in response: " + ", ".join(missing[:4]) if missing else "")


# --------------------------------------------------------------------------- state
def state_ok(step: dict, res: AgentResult, c: Contract) -> tuple[bool, list[str]]:
    op = step["expected_operation"]
    req = step.get("expected_request")
    if op in ("clarify", "refuse", "resolve") or not req:
        return True, []
    if op == "analyze":
        call = next((x for x in reversed(res.calls) if x.ok and x.name == "analyze"), None)
        if call is None:
            return False, ["no analyze applied"]
        d = diff_requests(req, call.applied or {}, c)
        return not d, d
    if op == "records":
        call = next((x for x in reversed(res.calls) if x.ok and x.name == "records"), None)
        if call is None:
            return False, ["no records applied"]
        ap = call.applied or {}
        diffs = []
        if call.data.get("entity") != req.get("id"):
            diffs.append(f"view: want {req.get('id')} got {call.data.get('entity')}")
        want = {k: v for k, v in (req.get("filters") or {}).items() if v not in (None, "all")}
        got = {k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "all")}
        for k in sorted(set(want) | set(got)):
            if want.get(k) != got.get(k):
                diffs.append(f"filters.{k}: want {want.get(k)} got {got.get(k)}")
        for k in ("start", "end"):
            if (req.get(k) or None) != (ap.get(k) or None):
                diffs.append(f"{k}: want {req.get(k)} got {ap.get(k)}")
        return not diffs, diffs
    if op == "related":
        call = next((x for x in reversed(res.calls) if x.ok and x.name == "related"), None)
        if call is None:
            return False, ["no related applied"]
        ok = (call.args.get("entity_type"), call.args.get("entity_id")) == (req.get("entity_type"), req.get("entity_id"))
        return ok, [] if ok else [f"entity: want {req.get('entity_type')} {req.get('entity_id')} got {call.args}"]
    if op == "navigate":
        return True, []
    return True, []


def resolution_ok(step: dict, res: AgentResult) -> bool:
    names = step.get("names_to_resolve") or []
    if not names:
        return True
    applied_vals: set[str] = set()
    for call in res.calls:
        if call.ok and call.name in DATA_TOOLS:
            ap = call.applied or {}
            for v in (ap.get("filters") or {}).values():
                if v is not None:
                    applied_vals.add(str(v))
            if call.name == "related":
                applied_vals.add(str(call.args.get("entity_id")))
    for n in names:
        want = str(n.get("expected_id"))
        rec = next((r for r in res.resolutions if r["text"].lower() == n["text"].lower()), None)
        if rec is not None and str(rec.get("id")) == want:
            continue
        if want in applied_vals:
            continue
        if step["expected_operation"] in ("clarify",) and res.op == "clarify":
            continue
        return False
    return True


def faithful_ok(step: dict, res: AgentResult, c: Contract, utterance: str) -> tuple[bool, str]:
    if res.status not in ("answered",):
        return True, ""
    facts = derive(res.calls, c)
    exp = Expectation(res.op, request=(res.expectation or {}).get("request"))
    viol = check_numbers(res.text, facts, res.calls, utterance, exp)
    if viol:
        return False, viol[0].message
    # caveat rules from the README
    measures = {x.data.get("measure", {}).get("id") for x in res.calls if x.ok and x.name == "analyze"}
    blob = (res.text + " " + " ".join(res.notes)).lower()
    if measures & set(MONEY_MEASURES) and "currency not stated" not in blob:
        return False, "money answer lacks the 'currency not stated' label"
    if "M11" in measures and "not net profit" not in blob:
        return False, "M11 not described as gross line profit, not net"
    if re.search(r"\b(usd|dollars?|euros?|eur|gbp|pounds?)\b|[$€£]", blob):
        return False, "currency named although the source states none"
    for x in res.calls:
        if x.ok and x.name == "analyze" and x.data.get("dimension", {}).get("additive") is False:
            if re.search(r"% of (the )?total|share", res.text.lower()):
                return False, "share shown for an overlapping dimension"
    return True, ""


def hallucinated(step: dict, res: AgentResult) -> int:
    """Calls outside the expected operation, filters the user did not ask for, stale filters."""
    op = step["expected_operation"]
    n = 0
    data_calls = [x for x in res.calls if x.name in DATA_TOOLS]
    if op in ("clarify", "refuse"):
        return len(data_calls)
    if op == "resolve":
        return 0
    for x in data_calls:
        if x.name != op:
            n += 1
    req = step.get("expected_request") or {}
    want = {k for k, v in (req.get("filters") or {}).items() if v not in (None, "all")}
    call = next((x for x in reversed(res.calls) if x.ok and x.name == op), None)
    if call is not None and op in ("analyze", "records"):
        got = {k for k, v in ((call.applied or {}).get("filters") or {}).items() if v not in (None, "all")}
        n += len(got - want)
    return n


# --------------------------------------------------------------------------- step score
def score_step(step: dict, res: AgentResult, c: Contract, utterance: str) -> dict:
    op_ok = res.op == step["expected_operation"] or (step["expected_operation"] == "resolve" and res.op in ("related", "analyze"))
    exp_view = step.get("expected_view")
    dest_ok = True
    if exp_view and step["expected_operation"] not in ("clarify", "refuse"):
        dest_ok = norm_view(res.deep_link, c) == norm_view(exp_view, c)
    s_ok, s_diff = state_ok(step, res, c)
    a_ok, a_why = analytic_ok(step, res.calls, res.op)
    r_ok = resolution_ok(step, res)
    f_ok, f_why = faithful_ok(step, res, c, utterance)
    h = hallucinated(step, res)
    why = []
    if not op_ok:
        why.append(f"op: want {step['expected_operation']} got {res.op}")
    if not dest_ok:
        why.append(f"dest: want {exp_view} got {res.deep_link}")
    if not s_ok:
        why.append("state: " + "; ".join(s_diff))
    if not r_ok:
        why.append("resolution")
    if not a_ok:
        why.append("analytic: " + a_why)
    if not f_ok:
        why.append("faithful: " + f_why)
    if h:
        why.append(f"hallucinated actions: {h}")
    return {"op_ok": op_ok, "dest_ok": dest_ok, "state_ok": s_ok, "resolution_ok": r_ok, "analytic_ok": a_ok,
            "faithful_ok": f_ok, "halluc": h, "pass": op_ok and dest_ok and s_ok and r_ok and a_ok and f_ok and h == 0,
            "why": why, "latency": res.latency, "attempts": res.attempts, "llm_calls": res.llm_calls,
            "status": res.status, "answer_source": res.answer_source}


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 1) if d else 0.0
