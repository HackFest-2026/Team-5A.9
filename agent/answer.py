"""Step [6]: answer text. The LLM drafts from code-computed facts; a numbers check rejects any figure that is
not traceable; after two failed drafts a deterministic template (always faithful) is used instead."""
from __future__ import annotations

import re
from typing import Any

from .contract import Contract
from .facts import Facts, derive, fmt_num
from .finish import Expectation, check_numbers, check_style
from .llm import LLM, LLMError
from .session import Call, jdump
from .tools import ToolBox

SYSTEM = """You write the final answer for a business user of an analytics app.
Use ONLY the FACTS provided. Quote every number exactly as written in the facts (same digits and decimals); never compute, round or add numbers of your own.
2 to 5 short sentences in plain language. Name the period and any filter. Say where a change is concentrated, never why it happened.
Talk only about groups that are listed in the facts (at most the first 3 rows), and use the up/down words exactly as given. Never describe a group that is not listed.
Never write a currency name or symbol ($, USD, dollars, euros): write plain numbers. Never use "because", "due to" or "caused by".
Do not mention tools, JSON or ids. Do not repeat caveats that are listed under NOTES: they are appended automatically."""


def notes_for(calls: list[Call], c: Contract, glossary_term: str | None = None) -> list[str]:
    """Caveats added by code, never by the model."""
    notes: list[str] = []
    seen_measures: set[str] = set()
    for call in calls:
        if not call.ok or call.name != "analyze":
            continue
        mid = call.data.get("measure", {}).get("id")
        if mid in seen_measures:
            continue
        seen_measures.add(mid)
        m = c.measures.get(mid, {})
        if "currency not stated" in (m.get("unit") or ""):
            notes.append("Amounts are 'sample amount (currency not stated in source)', excluding tax." if mid == "M10"
                         else "Amounts are 'sample amount (currency not stated in source)'; this is recorded gross line profit, not net profit.")
        elif m.get("caveat"):
            sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", m["caveat"]) if s.strip() and not re.search(r"\d", s)]
            if sentences:
                notes.append(" ".join(sentences))
        if m.get("default_date_basis") == "none" and not call.data.get("applied", {}).get("start"):
            notes.append("This is undated stored state; the period does not apply to it.")
        if call.data.get("dimension", {}).get("additive") is False:
            notes.append("Groups overlap (one order or item can appear in several), so rows do not add up to the total and no shares are shown.")
        if (call.data.get("applied", {}).get("scenario_id") or "base") != "base":
            notes.append("This is the SYNTHETIC scenario, not real data.")
    if glossary_term:
        g = next((x for x in c.glossary if x["term"] == glossary_term), None)
        if g and g.get("unsupported_reply"):
            notes.append(g["unsupported_reply"])
    out: list[str] = []
    for n in notes:
        if n not in out:
            out.append(n)
    return out


def template_answer(exp: Expectation, calls: list[Call], facts: Facts, tb: ToolBox) -> str:
    """Deterministic, always faithful: restates the code-computed facts."""
    data_calls = [c for c in calls if c.ok and c.name in ("analyze", "records", "related", "open_page")]
    if not data_calls:
        return "I could not retrieve anything for this request."
    last = data_calls[-1]
    if last.name == "analyze":
        lines = [ln.removeprefix("ANALYSIS: ") for ln in facts.lines if not ln.startswith("NOTE:")]
        return "\n".join(lines[:9])
    if last.name == "records":
        d = last.data
        rows = d.get("rows") or []
        ids = ", ".join(str(r.get("OrderID") or r.get("PurchaseOrderLineID") or r.get("StockItemID") or r.get("CustomerID") or r.get("SupplierID") or "?") for r in rows[:10])
        more = " (more available)" if d.get("has_more") else ""
        return f"Found {fmt_num(d.get('total_rows', len(rows)))} {d.get('entity')} records{more}. First rows: {ids}."
    if last.name == "related":
        d = last.data
        ent = d.get("entity") or {}
        name = next((v for k, v in ent.items() if k.endswith("Name") and isinstance(v, str)), None) or f"{last.args.get('entity_type')} {last.args.get('entity_id')}"
        bits = []
        for k, v in d.items():
            if isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values()) and v:
                bits.append(f"{k.replace('_', ' ')}: " + ", ".join(f"{kk} {fmt_num(vv)}" for kk, vv in v.items()))
        return f"{name}. " + " ".join(bits[:4])
    return f"Opened {last.deep_link}."


def compose(llm: LLM | None, user_text: str, exp: Expectation, calls: list[Call], c: Contract, tb: ToolBox,
            max_drafts: int = 2) -> tuple[str, str, list[dict]]:
    """Return (text, source, events). source is 'llm' or 'template'."""
    facts = derive(calls, c)
    events: list[dict] = []
    if llm is not None:
        views = [tb.view(x) for x in calls if x.ok and x.name in ("records", "related")]
        facts_txt = "\n".join(facts.lines) if facts.lines else ""
        body = f"QUESTION: {user_text}\nFACTS:\n{facts_txt}"
        if views:
            body += "\nDATA: " + jdump(views, 3000)
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}]
        for i in range(max_drafts):
            try:
                reply = llm.chat(msgs, max_tokens=350)
            except LLMError as e:
                events.append({"draft": i, "error": str(e)[:200]})
                break
            draft = reply.content.strip()
            viol = check_numbers(draft, facts, calls, user_text, exp) + check_style(draft)
            events.append({"draft": i, "ok": not viol, "latency": round(reply.latency, 2),
                           "violations": [v.message for v in viol]})
            if not viol and draft:
                return draft, "llm", events
            msgs = msgs + [{"role": "assistant", "content": draft},
                           {"role": "user", "content": viol[0].message if viol else "Write the answer."}]
    return template_answer(exp, calls, facts, tb), "template", events
