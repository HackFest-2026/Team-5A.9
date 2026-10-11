"""Step [1]: the LLM turns the request into an Intent (a delta over the carried state), JSON-schema constrained.
Dates, defaults and context carry-over are completed by code in slots.py."""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .contract import Contract
from .llm import LLM, LLMError
from .session import Session, jdump
from .slots import build_intent_model, normalize_intent

SYSTEM = """You turn a user's request about a business analytics app into a JSON intent. Output JSON only, with every field.

action:
- analyze: numbers, totals, rankings, breakdowns, trends, comparisons of periods.
- records: show the underlying rows ("show the orders / purchase lines / order lines of ..."). Set records_view (orders, order_lines, purchase_orders, purchase_lines, items, holdings, customers, suppliers).
- related: everything linked to ONE entity (customer, order, item, supplier, purchase order, salesperson): stock on hand, what is on order, who supplies it, "open it". Set related_type.
- navigate: open a page or switch scenario (page / scenario_id).
- clarify: the user's key word is marked AMBIGUOUS in the glossary. Set glossary_term to that term.
- refuse: the request needs something marked UNSUPPORTED in the glossary (forecast, net profit, another currency, past backlog, delivery lateness, changing business data). Set glossary_term. Changing what the view shows ("replace that item with 184", "switch to April") is NOT changing data: it is analyze.
  If the user only asks WHY something changed, do not refuse: use analyze, playbook explain_change, glossary_term "why / root cause".

Every field: use "unchanged" (or null / []) unless THIS message sets or changes it. The system carries measure, period, group_by, filters and sort over from the previous state.
- measure_id: from the glossary meaning. "sales"/"revenue" = M10, "profit" = M11, "incoming" = M05, "units still to pick" = M02 (a count of units), "orders that still have units to pick" = M03 (a count of orders), "orders" = M01, "units ordered" = M13.
- group_by only when the user asks for a breakdown ("by X", "per X", "split", "which X"). Naming one customer or item does NOT mean group_by customer or item.
- period: calendar words only, never dates. "May 2016" = {"kind":"month","year":2016,"month":5}. Year defaults to 2016. "January to March" = month_range. "this month"/"last month" = those kinds. "all time" = all_time. Not mentioned = {"kind":"unchanged"}.
- compare: "vs April"/"compared with April" = "explicit" + compare_period (April). "went up/down", "changed", "vs the previous month" = "previous_period". "none" removes the comparison.
- names: every business name the user typed (person, customer, store, supplier, item, region, category, group) with its type. Keep the full name exactly as typed, including anything in brackets: "Wingtip Toys (Edmund, WI)". Never invent IDs. Numbers the user typed ("item 80", "PO 2073") go in ids.
- territory: only for the sales territory values. State names (Michigan) are names of type state_province.
- use_row: when the user points at a row of the previous result ("the top one", "that top item", "the second one") give its 1-based position and leave names empty.
- clear: filters or period the user explicitly drops ("across all customers again").
- group_by words: salespeople/reps = salesperson; region/territory = sales_territory; state = state_province; customer category/segment = customer_category; buying group = buying_group; store/customer = customer; item/product = stock_item; supplier/vendor = supplier; product group = stock_group; trend/over time/by month = month.
- sort/top_n only when the user asks for a ranking direction or a count ("top 5" = top_n 5; "fell the most" = change_asc; "grew the most" = change_desc). A plain "how did X change" leaves sort "unchanged".
- status: null unless the user explicitly talks about picking being complete/incomplete or about incoming purchase lines. "Units still to pick" is already the measure M02, not a status.
- type of a name: follow the words around it ("that buying group" = buying_group, "the customer" = customer, "the Supermarket increase" = customer_category).
- playbook: explain_change (why did X change), unpicked_triage, supplier_exposure, customer_review, money_summary, order_trace, or null."""

_BLANK = {
    "action": "analyze", "measure_id": "unchanged", "group_by": "unchanged", "period": {"kind": "unchanged"},
    "compare": "unchanged", "compare_period": None, "date_basis": None, "names": [], "ids": [], "territory": None,
    "status": None, "clear": [], "sort": "unchanged", "top_n": None, "use_row": None, "records_view": None,
    "related_type": None, "page": None, "scenario_id": None, "glossary_term": None, "playbook": None,
}
_M = lambda y, m: {"kind": "month", "year": y, "month": m}  # noqa: E731
EXAMPLES: list[tuple[str, dict]] = [
    ("How did orders in May 2016 compare with April?",
     {"measure_id": "M01", "period": _M(2016, 5), "compare": "explicit", "compare_period": _M(2016, 4)}),
    ("Break that down by sales territory.", {"group_by": "sales_territory"}),
    ("Which customers in Michigan drove that, top 5?",
     {"group_by": "customer", "names": [{"text": "Michigan", "type": "state_province"}], "top_n": 5}),
    ("What's the supply picture for that top item?", {"action": "related", "related_type": "stock_item", "use_row": 1}),
    ("List Emily Whittle's May orders.",
     {"action": "records", "records_view": "orders", "period": _M(2016, 5), "names": [{"text": "Emily Whittle", "type": "customer"}]}),
    ("Compare May and April 2016 orders by customer category.",
     {"measure_id": "M01", "group_by": "customer_category", "period": _M(2016, 5), "compare": "explicit", "compare_period": _M(2016, 4)}),
    ("Show the open purchase line on PO 2074 for item 80.",
     {"action": "records", "records_view": "purchase_lines", "status": "incoming",
      "ids": [{"filter": "purchase_order_id", "value": 2074}, {"filter": "stock_item_id", "value": 80}]}),
    ("Who supplies it?", {"action": "related", "related_type": "supplier"}),
    ("How much of that one do we have on hand, and is anything on order?",
     {"action": "related", "related_type": "stock_item", "use_row": 1}),
    ("Replace that item with 184.", {"ids": [{"filter": "stock_item_id", "value": 184}]}),
    ("Show invoiced sales by month for January to May 2016.",
     {"measure_id": "M10", "group_by": "month", "period": {"kind": "month_range", "year": 2016, "month": 1, "end_year": 2016, "end_month": 5}}),
    ("Orders in the Southeast in Q1 2016.",
     {"measure_id": "M01", "period": {"kind": "quarter", "year": 2016, "quarter": 1}, "territory": "Southeast"}),
    ("How many units is that in total?", {"measure_id": "M02", "clear": ["group_by"]}),
    ("Restrict incoming to deliveries expected in June 2016.",
     {"measure_id": "M05", "date_basis": "expected_delivery_date", "period": _M(2016, 6)}),
    ("Show open orders in May 2016.", {"action": "clarify", "glossary_term": "open orders"}),
    ("Forecast next month's sales.", {"action": "refuse", "glossary_term": "forecast"}),
    ("Incoming units for item 80?",
     {"measure_id": "M05", "period": {"kind": "all_time"}, "ids": [{"filter": "stock_item_id", "value": 80}]}),
]


def examples_text() -> str:
    lines = ["Examples:"]
    for q, partial in EXAMPLES:
        full = {**_BLANK, **partial}
        lines.append(f'"{q}" -> {json.dumps(full, separators=(",", ":"))}')
    return "\n".join(lines)


def force_required(schema: dict) -> dict:
    """Every field must be decided. Enums carry an explicit "unchanged" value, so forcing cannot invent changes."""
    schema["required"] = list(schema["properties"])
    defs = schema.get("$defs", {})
    for key, req in (("NameRef", ["text", "type"]), ("IdRef", ["filter", "value"]), ("PeriodSpec", ["kind"])):
        if key in defs:
            defs[key]["required"] = req
    return schema


def build_messages(text: str, session: Session, c: Contract) -> list[dict]:
    st = session.state
    ctx = (
        f"CONTEXT\nReference date: {c.reference_date}. Scenario: {st.scenario_id}.\n"
        f"Previous state: {jdump(st.describe()) if st.measure_id else 'none (first request)'}\n"
        f"Entities mentioned so far: {session.mentioned_text()}\n"
        f"Rows of the previous result: {session.last_rows_text()}"
    )
    sys = "\n\n".join([SYSTEM, examples_text(), c.prompt_summary(), c.glossary_prompt(), ctx])
    return [{"role": "system", "content": sys}, {"role": "user", "content": text}]


def understand(llm: LLM, c: Contract, Intent: Any, text: str, session: Session) -> tuple[Any, dict]:
    """Return (Intent, meta). Retries once with the validation error if the model's JSON is invalid."""
    schema = force_required(Intent.model_json_schema())
    msgs = build_messages(text, session, c)
    last_err = ""
    meta: dict[str, Any] = {"retries": 0, "latency": 0.0}
    for _ in range(2):
        try:
            obj, reply = llm.json_out(msgs, schema, "intent", max_tokens=600)
            meta["latency"] += reply.latency
            meta["raw"] = obj
            return normalize_intent(Intent.model_validate(obj)), meta
        except (LLMError, ValidationError, json.JSONDecodeError) as e:
            last_err = str(e)[:400]
            meta["retries"] += 1
            msgs = msgs + [{"role": "user", "content": f"Your JSON was invalid: {last_err}. Reply with valid JSON only."}]
    raise LLMError(f"could not obtain a valid intent: {last_err}")
