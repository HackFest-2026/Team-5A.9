"""A chart the user can save, proposed from an answered analysis question.

The agent never writes to the workspace itself. It only proposes a definition (the same request it just ran, plus a chart
type and a title). The browser shows a card; the user presses Save, and the console's guarded write API stores it.
"""
from __future__ import annotations

import re

CHART_WORDS = re.compile(r"\b(chart|graph|plot|visuali[sz]e|pie|bar|line)\b", re.I)


def wants_chart(question: str) -> bool:
    return bool(CHART_WORDS.search(question or ""))


def _chart_type(question: str, group_by: str) -> str:
    q = (question or "").lower()
    if group_by == "none":
        return "number"
    if "pie" in q or "share" in q or "split" in q:
        return "pie" if group_by != "month" else "bar"
    if group_by == "month" or re.search(r"\btrend|over time|monthly", q):
        return "line" if group_by == "month" else "bar"
    if "horizontal" in q or "ranking" in q or "top" in q:
        return "hbar"
    return "bar"


def propose_chart(question: str, request: dict | None) -> dict | None:
    """`request` is the analyze request the answer was computed from (measure, dates, comparison, grouping)."""
    if not request or not request.get("measure_id"):
        return None
    group_by = request.get("group_by") or "none"
    if group_by == "month" and request.get("compare_start"):
        return None   # the API cannot chart two periods month by month; the answer stays text only
    title = re.sub(r"[?.!]+$", "", (question or "").strip())
    title = (title[:1].upper() + title[1:])[:80] or "Chart"
    return {
        "title": title,
        "measure_id": request["measure_id"],
        "group_by": group_by,
        "date_basis": request.get("date_basis"),
        "start": request.get("start"),
        "end": request.get("end"),
        "compare_start": request.get("compare_start"),
        "compare_end": request.get("compare_end"),
        "chart_type": _chart_type(question, group_by),
        "top_n": int(request.get("top_n") or 10),
        "sort": None,
    }
