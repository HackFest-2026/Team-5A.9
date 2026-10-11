"""The trail and the ledger of one turn, built only from what the agent actually did (its trace events and tool calls).

`trail`   - the real sequence of steps for this question, in order: what was asked, how it was read, which names were resolved, which
            endpoint was called with which arguments and what came back, which checks ran, how the answer was written. Every item says
            who did it (you / model / code / tool / browser), when (seconds since the question), where (page or endpoint) and the exact
            values involved. The browser appends the last items (open the page, read it, compare) because only it can see the page.
`facts`   - the ledger proper: every value the answer may use, with the call that produced it, or "code" for values the agent
            computed itself (differences and percentages are never computed by the model).
`expect`  - the figures the opened page must show, so the browser can confirm the match.
"""
from __future__ import annotations

import calendar
import json
from datetime import date
from typing import Any

from .facts import fmt_num, signed

ENDPOINT = {"analyze": "POST /api/analyze", "resolve": "POST /api/resolve", "records": "POST /api/records",
            "related": "POST /api/related", "lookup": "glossary / page index", "open_page": "page link check"}
MEASURE_FALLBACK = {"M01": "Orders created", "M02": "Unpicked units", "M03": "Orders with unpicked units", "M04": "Stock on hand",
                    "M05": "Incoming purchase units", "M10": "Invoiced sales", "M11": "Gross profit", "M13": "Units ordered"}


def _short(s: Any, n: int = 90) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _month(y: int, m: int) -> str:
    return f"{calendar.month_name[m]} {y}"


def _range(a: str | None, b: str | None) -> str:
    """'2016-05-01' → '2016-06-01' reads as 'May 2016' when it is exactly one calendar month."""
    if not a or not b:
        return "—"
    try:
        s, e = date.fromisoformat(a), date.fromisoformat(b)
        nxt = date(s.year + (s.month == 12), s.month % 12 + 1, 1)
        if s.day == 1 and e == nxt:
            return _month(s.year, s.month)
        return f"{a} → {b} (end not included)"
    except ValueError:
        return f"{a} → {b}"


def _spec(p: dict | None) -> str:
    if not p:
        return ""
    k = p.get("kind")
    if k == "month":
        return _month(p["year"], p["month"])
    if k == "quarter":
        return f"Q{p['quarter']} {p['year']}"
    if k == "year":
        return str(p["year"])
    if k == "month_range":
        return f"{_month(p['year'], p['month'])} to {_month(p.get('end_year') or p['year'], p.get('end_month') or p['month'])}"
    if k in ("this_month", "last_month", "all_time"):
        return k.replace("_", " ")
    if k == "last_n_months":
        return f"last {p.get('n')} months"
    return "" if k == "unchanged" else json.dumps(p)


def _kv(pairs: list[tuple[str, Any]]) -> list[list[str]]:
    return [[k, str(v)] for k, v in pairs if v not in (None, "", [], {})]


def _flat(d: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}" for k, v in d.items() if v not in (None, {}, [], ""))


def _call_summary(c) -> tuple[str, list[tuple[str, Any]]]:
    """One line plus detail pairs describing what a tool call returned."""
    d, a = c.data or {}, c.args or {}
    if not c.ok:
        return f"Failed: {_short(c.error, 120)}", [("Error", c.error)]
    if c.name == "analyze":
        m = d.get("measure") or {}
        name = m.get("name") or MEASURE_FALLBACK.get(a.get("measure_id"), a.get("measure_id"))
        ap = d.get("applied") or a
        rows = d.get("rows") or []
        cmp_ = bool(ap.get("compare_start"))
        if cmp_ and d.get("change") is not None:
            line = f"{fmt_num(d.get('total_current'))} vs {fmt_num(d.get('total_baseline'))} ({signed(d['change'])}" + (f", {d['pct_change']:+.2f}%" if d.get("pct_change") is not None else "") + ")"
        elif d.get("total_current") is not None or d.get("total") is not None:
            line = f"{fmt_num(d.get('total_current', d.get('total')))} {m.get('unit') or ''}".strip()
        else:
            line = f"{len(rows)} rows"
        if d.get("group_count"):
            line += f" · {d['group_count']} groups"
        top = [f"{r.get('label')}: {signed(r['change']) if cmp_ and r.get('change') is not None else fmt_num(r.get('value', r.get('current')))}" for r in rows[:3] if r.get("label") is not None]
        return line, [("Measure", f"{name} ({a.get('measure_id')})"), ("Current period", _range(ap.get("start"), ap.get("end"))),
                      ("Compared with", _range(ap.get("compare_start"), ap.get("compare_end")) if cmp_ else None),
                      ("Total", fmt_num(d["total"]) if d.get("total") is not None and not cmp_ else None),
                      ("Filters", _flat({k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "", [])})),
                      ("Total now", fmt_num(d.get("total_current")) if d.get("total_current") is not None else None),
                      ("Total before", fmt_num(d.get("total_baseline")) if d.get("total_baseline") is not None else None),
                      ("Change", signed(d["change"]) if d.get("change") is not None else None),
                      ("Grouped by", ap.get("group_by") if ap.get("group_by") not in (None, "none") else None),
                      ("Groups returned", d.get("group_count")), ("Top rows", "; ".join(top))]
    if c.name == "resolve":
        cands = d.get("candidates") or []
        top = [f"{x.get('name')} ({x.get('type')} #{x.get('id')})" for x in cands[:3]]
        st = d.get("status")
        return f"{st}: {top[0]}" if top and st == "unique" else f"{st or 'no result'}" + (f" ({len(cands)} candidates)" if cands else ""), \
            [("Looked for", a.get("name")), ("In", a.get("kind")), ("Result", st), ("Candidates", "; ".join(top))]
    if c.name == "records":
        rows = d.get("rows") or []
        return f"{fmt_num(d.get('total_rows', len(rows)))} records", [("View", a.get("view")), ("Filters", _flat(a.get("filters") or {})), ("Records", d.get("total_rows")), ("Shown", len(rows))]
    if c.name == "lookup":
        n = len(d.get("pages") or d.get("matches") or [])
        return f"{n} match{'es' if n != 1 else ''}", [("Term", a.get("term")), ("Searched", a.get("kind") or "glossary")]
    keys = list(d.keys())[:6]
    return "OK", [("Returned", ", ".join(keys))]


def _intent_pairs(i: dict, measures: dict[str, str]) -> tuple[str, list[tuple[str, Any]]]:
    def keep(v):
        return v not in (None, "", [], {}, "unchanged")
    mid = i.get("measure_id")
    meas = f"{measures.get(mid) or MEASURE_FALLBACK.get(mid) or mid} ({mid})" if keep(mid) else None
    per, cmpp = _spec(i.get("period")), _spec(i.get("compare_period"))
    names = [f"{n.get('text')} → {n.get('type')}" for n in (i.get("names") or [])]
    bits = [b for b in [mid if keep(mid) else None, per, f"vs {cmpp}" if cmpp else None, f"by {i.get('group_by')}" if keep(i.get("group_by")) and i.get("group_by") != "none" else None, ", ".join(names)] if b]
    pairs = [("Action", i.get("action")), ("Measure", meas), ("Period", per), ("Compared with", cmpp if cmpp else (i.get("compare") if keep(i.get("compare")) else None)),
             ("Grouped by", i.get("group_by") if keep(i.get("group_by")) else None), ("Names to resolve", "; ".join(names)),
             ("Territory", i.get("territory")), ("Sort", i.get("sort") if keep(i.get("sort")) else None), ("Top N", i.get("top_n")),
             ("Status filter", i.get("status")), ("Playbook", i.get("playbook")), ("Glossary term", i.get("glossary_term"))]
    return " · ".join(bits) or str(i.get("action") or "question"), pairs


def build_ledger(res: Any, followed_up: bool) -> dict:
    calls = list(res.calls or [])
    events = list(res.events or [])
    exp = res.expectation or {}
    answered = res.status == "answered"
    ana = next((c for c in calls if c.ok and c.name == "analyze"), None)
    data = ana.data if ana else {}
    measure = data.get("measure") or {}
    unit = measure.get("unit") or ""
    applied = data.get("applied") or {}
    compare = bool(applied.get("compare_start") or exp.get("compare_start"))
    measures = {}
    if measure.get("id"):
        measures[measure["id"]] = measure.get("name")

    trail: list[dict] = []

    def add(who: str, title: str, detail: str = "", where: str = "", kv=None, status: str = "done", t: float | None = None, note: str = "") -> dict:
        it = {"n": len(trail) + 1, "who": who, "title": title, "detail": _short(detail, 110), "where": where, "kv": _kv(kv or []), "status": status,
              "t": None if t is None else round(t, 1), "note": note}
        trail.append(it)
        return it

    tool_events = [e for e in events if e.get("kind") == "tool_call"]
    ci = 0
    for e in events:
        k, t = e.get("kind"), e.get("t")
        if k == "turn":
            add("you", "You asked", f"“{_short(e.get('text'), 80)}”", "Assistant panel",
                [("Question", e.get("text")), ("Conversation", "follow-up: the scope from your last answer was available" if followed_up else "new conversation")], t=t)
        elif k == "understand":
            line, pairs = _intent_pairs(e.get("intent") or {}, measures)
            add("model", "Read the question", line, "language model → slots",
                pairs + [("Time", f"{e.get('latency')} s"), ("Retries", e.get("retries") or None)], t=t,
                note="The model only fills slots (measure, period, grouping, names). It does not build the query.")
        elif k == "sanitize":
            add("code", "Removed guesses", _short("; ".join(e.get("dropped") or []), 100), "code check",
                [("Dropped", "; ".join(e.get("dropped") or []))], t=t, note="Settings the model added that your words did not support.")
        elif k == "gate_reject":
            add("code", "Gate corrected a step", _short("; ".join(e.get("messages") or []), 100), f"gate: {e.get('gate') or 'check'}",
                [("Tool", e.get("tool")), ("Gate", e.get("gate")), ("Reason", "; ".join(e.get("messages") or []))], t=t)
        elif k == "expectation":
            rq = e.get("request") or {}
            add("code", "Built the exact request", f"{measures.get(rq.get('measure_id')) or MEASURE_FALLBACK.get(rq.get('measure_id')) or rq.get('measure_id')} · {_range(rq.get('start'), rq.get('end'))}" + (f" vs {_range(rq.get('compare_start'), rq.get('compare_end'))}" if rq.get("compare_start") else ""), "code",
                [("Measure", rq.get("measure_id")), ("Date basis", rq.get("date_basis")), ("Current period", _range(rq.get("start"), rq.get("end"))),
                 ("Compared with", _range(rq.get("compare_start"), rq.get("compare_end")) if rq.get("compare_start") else None),
                 ("Grouped by", rq.get("group_by")), ("Filters", _flat(rq.get("filters") or {})), ("Data scope", rq.get("scenario_id"))], t=t,
                note="Dates, defaults and ids were filled in by code, then checked against the app's contract before any call.")
        elif k == "preflight_refuse":
            add("code", "Refused before calling", _short("; ".join(e.get("errors") or []), 100), "contract check", [("Reasons", "; ".join(e.get("errors") or []))], status="failed", t=t)
        elif k == "tool_call":
            c = calls[ci] if ci < len(calls) and calls[ci].name == e.get("tool") else next((x for x in calls if x.name == e.get("tool")), None)
            ci += 1
            if c is None:
                add("tool", f"Called {e.get('tool')}", "", ENDPOINT.get(e.get("tool"), ""), [("Arguments", _flat(e.get("args") or {}))], status="done" if e.get("ok") else "failed", t=t)
                continue
            line, pairs = _call_summary(c)
            add("tool", f"Called {c.name}", line, ENDPOINT.get(c.name, c.name),
                [("Arguments", _flat({k2: v for k2, v in (c.args or {}).items()}))] + pairs + [("Time", f"{c.latency:.2f} s")], status="done" if c.ok else "failed", t=t)
        elif k == "finish_check":
            ok, vio = e.get("ok"), e.get("violations") or []
            add("code", "Checked the result", "Matches the request" if ok else _short("; ".join(vio), 100), "finish gate",
                [("Result", "passed" if ok else "failed"), ("Problems", "; ".join(vio))], status="done" if ok else "failed", t=t,
                note="The finish gate compares what the tools returned with what the request needed.")
        elif k == "answer_draft":
            ok = e.get("ok")
            add("model", f"Wrote the answer (draft {int(e.get('draft', 0)) + 1})", "Passed the number check" if ok else _short("; ".join(e.get("violations") or [e.get("error", "failed")]), 100),
                "language model → text", [("Result", "every number traced to a tool result" if ok else "rejected"), ("Problems", "; ".join(e.get("violations") or [])), ("Time", f"{e.get('latency')} s" if e.get("latency") else None)],
                status="done" if ok else "failed", t=t)
        elif k == "error":
            add("code", "Stopped", _short(e.get("error"), 100), "", [("Error", e.get("error"))], status="failed", t=t)

    # how the answer ended up
    if answered:
        src = getattr(res, "answer_source", "")
        if ana and compare and data.get("change") is not None:
            head = f"{signed(data['change'])} {unit}".strip() + (f" ({data['pct_change']:+.2f}%)" if data.get("pct_change") is not None else "")
        elif ana and (data.get("total_current") is not None or data.get("total") is not None):
            head = f"{fmt_num(data.get('total_current', data.get('total')))} {unit}".strip()
        elif ana and data.get("rows"):
            head = f"{len(data['rows'])} groups"
        else:
            head = "Answer ready"
        add("code" if src != "llm" else "model", "Answer ready", head, "assistant panel",
            [("Headline", head), ("Wording by", "the language model (draft passed the check)" if src == "llm" else "a plain template (the model's drafts failed the check)"),
             ("Model calls", res.llm_calls), ("Total time", f"{res.latency:.1f} s")], t=res.latency)
    elif res.status == "clarify":
        add("model", "Asked you a question", _short(res.text, 100), "assistant panel", [("Question", res.text)], status="ask", t=res.latency)
    elif res.status in ("abstain", "refuse"):
        add("code", "Declined to answer", _short(res.text, 100), "assistant panel", [("Why", res.text)], status="failed", t=res.latency)

    # steps only the browser can do
    if res.deep_link and answered:
        route = res.deep_link.lstrip("#/").split("?")[0]
        add("browser", "Open the page", route, "#/" + route, [("Link", res.deep_link)], status="pending")
        add("browser", "Read the page", "", "", [], status="pending")
        add("browser", "Compare with the answer" if (ana and (data.get("total_current") is not None or data.get("total") is not None)) else "Confirm the page loaded", "", "", [], status="pending")

    # ---- ledger facts
    facts: list[dict] = []
    names = [r for r in (res.resolutions or []) if r]
    for n in names:
        if n.get("id") is not None:
            facts.append({"label": f'"{n.get("text")}"', "value": f'{n.get("type")} #{n.get("id")}', "source": "resolve", "by": "tool"})
    if ana:
        a = data.get("applied") or {}
        if compare:
            facts.append({"label": f"{measure.get('name')} · {a.get('compare_start')} → {a.get('compare_end')}", "value": fmt_num(data.get("total_baseline")), "source": "analyze", "by": "tool"})
            facts.append({"label": f"{measure.get('name')} · {a.get('start')} → {a.get('end')}", "value": fmt_num(data.get("total_current")), "source": "analyze", "by": "tool"})
            if data.get("change") is not None:
                facts.append({"label": "Change", "value": signed(data["change"]), "source": f"{fmt_num(data.get('total_current'))} − {fmt_num(data.get('total_baseline'))}", "by": "code"})
            if data.get("pct_change") is not None:
                facts.append({"label": "Change, %", "value": f"{data['pct_change']:+.2f}%", "source": "change ÷ baseline", "by": "code"})
        elif data.get("total_current") is not None or data.get("total") is not None:
            flt = _flat({k: v for k, v in (a.get("filters") or {}).items() if v not in (None, "", [])})
            facts.append({"label": f"{measure.get('name')} · {a.get('start')} → {a.get('end')}" + (f" · {flt}" if flt else ""), "value": fmt_num(data.get("total_current", data.get("total"))), "source": "analyze", "by": "tool"})
        for i, r in enumerate((data.get("rows") or [])[:3], 1):
            if r.get("label") is not None and r.get("value") is not None:
                facts.append({"label": f"#{i} by {data.get('dimension', {}).get('id', 'group')}", "value": f"{r['label']}: {fmt_num(r['value'])}", "source": "analyze", "by": "tool"})

    expect = None
    req = {k: applied.get(k) for k in ("measure_id", "start", "end", "compare_start", "compare_end", "group_by")}
    if ana and data.get("total_current") is not None:
        expect = {"total_current": data.get("total_current"), "total_baseline": data.get("total_baseline"), "change": data.get("change"), "request": req}
    elif ana and data.get("total") is not None:
        expect = {"total": data.get("total"), "request": req}
    return {"trail": trail, "facts": facts, "expect": expect, "followed_up": followed_up, "question": next((e.get("text") for e in events if e.get("kind") == "turn"), "")}
