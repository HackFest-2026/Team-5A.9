"""Intent/slot models, calendar arithmetic and conversation state. All date maths and context carrying
is done here in code; the LLM only names the period ("May 2016") and what changed since the last turn."""
from __future__ import annotations

import calendar
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

from .contract import CHANGE_SORTS, DIM_FILTER, FILTER_RESOLVE_TYPE, SORTS, Contract

ACTIONS = ("analyze", "records", "related", "navigate", "clarify", "refuse")
RESOLVE_TYPES = (
    "customer", "stock_item", "supplier", "customer_category", "buying_group",
    "stock_group", "state_province", "sales_territory", "salesperson",
)
RECORD_VIEWS = ("orders", "order_lines", "items", "holdings", "purchase_orders", "purchase_lines", "customers", "suppliers")
RELATED_TYPES = ("customer", "order", "stock_item", "supplier", "purchase_order", "salesperson")
PAGES = ("overview", "fulfilment", "supply", "analysis")
PLAYBOOKS = ("explain_change", "unpicked_triage", "supplier_exposure", "customer_review", "segment_comparison",
             "order_trace", "money_summary", "no_supply_branch")
GEO_ORDER = ("sales_territory", "state_province_id", "customer_id")  # broad -> narrow


# ------------------------------------------------------------------------------ calendar
def add_months(d: date, k: int) -> date:
    m = d.month - 1 + k
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


class PeriodSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["unchanged", "month", "quarter", "year", "month_range", "this_month", "last_month", "last_n_months", "all_time"]
    year: Optional[int] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    quarter: Optional[int] = Field(default=None, ge=1, le=4)
    end_year: Optional[int] = None
    end_month: Optional[int] = Field(default=None, ge=1, le=12)
    n: Optional[int] = Field(default=None, ge=1, le=60)


def resolve_period(p: PeriodSpec, ref: date, data_max: date) -> tuple[Optional[str], Optional[str]]:
    """PeriodSpec -> (start, end) with end exclusive, clamped to the data. (None, None) means all time."""
    k = p.kind
    if k == "all_time":
        return None, None
    if k == "unchanged":
        raise ValueError("an unchanged period has no dates")
    if k in ("this_month", "last_month"):
        first = date(ref.year, ref.month, 1)
        s = first if k == "this_month" else add_months(first, -1)
        e = add_months(s, 1)
    elif k == "last_n_months":
        n = p.n or 1
        e = add_months(date(ref.year, ref.month, 1), 1)
        s = add_months(e, -n)
    elif k == "month":
        y = p.year or ref.year
        if p.month is None:
            raise ValueError("month period needs month")
        s = date(y, p.month, 1)
        e = add_months(s, 1)
    elif k == "quarter":
        y = p.year or ref.year
        if p.quarter is None:
            raise ValueError("quarter period needs quarter")
        s = date(y, 3 * (p.quarter - 1) + 1, 1)
        e = add_months(s, 3)
    elif k == "year":
        y = p.year or ref.year
        s, e = date(y, 1, 1), date(y + 1, 1, 1)
    elif k == "month_range":
        if p.month is None:
            raise ValueError("month_range needs month")
        y = p.year or ref.year
        s = date(y, p.month, 1)
        ey = p.end_year or y
        em = p.end_month or p.month
        e = add_months(date(ey, em, 1), 1)
    else:  # pragma: no cover
        raise ValueError(f"unknown period kind {k}")
    if e > data_max:
        e = data_max  # the data ends 2016-06-21 and end dates are exclusive
    return s.isoformat(), e.isoformat()


def shift_period(start: str, end: str, mode: str) -> tuple[str, str]:
    """Baseline period for 'previous_period' / 'same_period_last_year'."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if mode == "same_period_last_year":
        return add_months(s, -12).isoformat(), add_months(e, -12).isoformat()
    whole_months = s.day == 1 and e.day == 1
    if whole_months:
        n = (e.year - s.year) * 12 + e.month - s.month
        return add_months(s, -n).isoformat(), s.isoformat()
    span = e - s
    return (s - span).isoformat(), s.isoformat()


# ------------------------------------------------------------------------------ intent model
def build_intent_model(c: Contract):
    id_filters = tuple(c.id_filters)
    measure_ids = tuple(c.measures)
    non_mapped = tuple(c.glossary_terms("ambiguous") + c.glossary_terms("unsupported")) or ("",)
    NameRef = create_model(
        "NameRef", __config__=ConfigDict(extra="forbid"),
        text=(str, ...), type=(Literal[RESOLVE_TYPES], ...),  # type: ignore[valid-type]
    )
    IdRef = create_model(
        "IdRef", __config__=ConfigDict(extra="forbid"),
        filter=(Literal[id_filters], ...), value=(int, ...),  # type: ignore[valid-type]
    )
    clearable = tuple(id_filters) + ("sales_territory", "status", "period", "compare", "group_by", "sort")
    Intent = create_model(
        "Intent",
        __config__=ConfigDict(extra="forbid"),
        action=(Literal[ACTIONS], ...),  # type: ignore[valid-type]
        measure_id=(Literal[("unchanged",) + measure_ids], "unchanged"),  # type: ignore[valid-type]
        group_by=(Literal[("unchanged",) + tuple(c.dimensions)], "unchanged"),  # type: ignore[valid-type]
        period=(Optional[PeriodSpec], None),
        compare=(Literal["unchanged", "none", "previous_period", "same_period_last_year", "explicit"], "unchanged"),
        compare_period=(Optional[PeriodSpec], None),
        date_basis=(Optional[Literal[tuple(sorted({b for m in c.measures.values() for b in m["date_bases"]}))]], None),  # type: ignore[valid-type]
        names=(list[NameRef], Field(default_factory=list)),  # type: ignore[valid-type]
        ids=(list[IdRef], Field(default_factory=list)),  # type: ignore[valid-type]
        territory=(Optional[Literal[tuple(c.territories) or ("",)]], None),  # type: ignore[valid-type]
        status=(Optional[Literal[tuple(c.status_values)]], None),  # type: ignore[valid-type]
        clear=(list[Literal[clearable]], Field(default_factory=list)),  # type: ignore[valid-type]
        sort=(Literal[("unchanged",) + tuple(SORTS)], "unchanged"),  # type: ignore[valid-type]
        top_n=(Optional[int], Field(default=None, ge=1, le=50)),
        use_row=(Optional[int], Field(default=None, ge=1, le=50)),
        records_view=(Optional[Literal[RECORD_VIEWS]], None),  # type: ignore[valid-type]
        related_type=(Optional[Literal[RELATED_TYPES]], None),  # type: ignore[valid-type]
        page=(Optional[Literal[PAGES]], None),  # type: ignore[valid-type]
        scenario_id=(Optional[Literal[tuple(c.scenarios)]], None),  # type: ignore[valid-type]
        glossary_term=(Optional[Literal[non_mapped]], None),  # type: ignore[valid-type]
        playbook=(Optional[Literal[PLAYBOOKS]], None),  # type: ignore[valid-type]
    )
    return Intent, NameRef, IdRef


_MONTHS = {m: i for i, names in enumerate(
    ["jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august",
     "sep sept september", "oct october", "nov november", "dec december"], 1) for m in names.split()}
_MONTH_RE = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b(?:[ ,-]+(20\d\d))?", re.I)


def fallback_periods(text: str) -> tuple[Optional[PeriodSpec], Optional[PeriodSpec]]:
    """Safety net used only when the model returned no period: read calendar words straight from the text.
    Two months -> current = the later one, baseline = the earlier one ("May vs April", "April-to-May change")."""
    t = text.lower()
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", t)]
    default_year = years[-1] if years else 2016
    q = re.search(r"\bq([1-4])\b(?:[ ,-]+(20\d\d))?", t)
    if q:
        return PeriodSpec(kind="quarter", year=int(q.group(2) or default_year), quarter=int(q.group(1))), None
    found: list[tuple[int, int]] = []
    for m in _MONTH_RE.finditer(text):
        if m.group(1).lower() == "may" and not re.search(r"\bmay\b\s*(20\d\d|\b(vs|versus|and|to|compared|orders|sales|units)\b)|\b(in|for|of|from|to|and|vs|versus|than)\s+may\b", t):
            continue  # the verb "may"
        ym = (int(m.group(2) or default_year), _MONTHS[m.group(1).lower()])
        if ym not in found:
            found.append(ym)
    if len(found) >= 2 and not re.search(r"\bto\b.*\bto\b", t):
        found.sort()
        (y0, m0), (y1, m1) = found[-2], found[-1]
        if re.search(r"\b(vs|versus|compar|against|than|change|between|from)\b|-to-", t):
            return (PeriodSpec(kind="month", year=y1, month=m1), PeriodSpec(kind="month", year=y0, month=m0))
        return PeriodSpec(kind="month_range", year=found[0][0], month=found[0][1], end_year=found[-1][0], end_month=found[-1][1]), None
    if len(found) == 1 and not re.search(r"\b(vs|versus|compar|against|than|instead of|swap|replace)\b", t):
        return PeriodSpec(kind="month", year=found[0][0], month=found[0][1]), None
    return None, None


def normalize_intent(intent: Any) -> Any:
    """Turn the model's explicit "unchanged" markers into None so merge_state sees only real changes."""
    for f in ("measure_id", "group_by", "compare", "sort"):
        if getattr(intent, f) == "unchanged":
            setattr(intent, f, None)
    if intent.period is not None and intent.period.kind == "unchanged":
        intent.period = None
    if intent.compare_period is not None and intent.compare_period.kind == "unchanged":
        intent.compare_period = None
    return intent


# ------------------------------------------------------------------------------ state
@dataclass
class State:
    """What the app view currently shows (the carried context between turns)."""
    measure_id: Optional[str] = None
    group_by: str = "none"
    start: Optional[str] = None
    end: Optional[str] = None
    compare_start: Optional[str] = None
    compare_end: Optional[str] = None
    compare_mode: Optional[str] = None  # previous_period | same_period_last_year | explicit
    filters: dict[str, Any] = field(default_factory=dict)
    sort: Optional[str] = None
    top_n: Optional[int] = None
    date_basis: Optional[str] = None
    scenario_id: str = "base"

    def copy(self) -> "State":
        return deepcopy(self)

    def to_request(self) -> dict:
        r: dict[str, Any] = {"measure_id": self.measure_id, "group_by": self.group_by, "filters": dict(self.filters),
                             "scenario_id": self.scenario_id}
        for k in ("date_basis", "start", "end", "compare_start", "compare_end", "sort", "top_n"):
            v = getattr(self, k)
            if v is not None:
                r[k] = v
        if self.group_by == "month" and self.sort is None:
            r["sort"] = "label_asc"  # a trend reads chronologically
        return r

    def describe(self) -> dict:
        d = {k: v for k, v in self.to_request().items() if v not in (None, {}, "none")}
        return d


def canonical(req: dict, c: Contract) -> dict:
    """Fill API defaults so two requests that mean the same compare equal."""
    out: dict[str, Any] = {}
    mid = req.get("measure_id")
    out["measure_id"] = mid
    m = c.measures.get(mid or "", {})
    out["date_basis"] = req.get("date_basis") or m.get("default_date_basis")
    for k in ("start", "end", "compare_start", "compare_end"):
        out[k] = req.get(k) or None
    out["group_by"] = req.get("group_by") or "none"
    flt = {}
    for k, v in (req.get("filters") or {}).items():
        if v is None or (k == "status" and v == "all"):
            continue
        flt[k] = v
    out["filters"] = flt
    has_cmp = bool(out["compare_start"])
    out["sort"] = req.get("sort") or ("abs_change_desc" if has_cmp else "value_desc")
    out["top_n"] = req.get("top_n") or 10
    out["scenario_id"] = req.get("scenario_id") or "base"
    return out


def diff_requests(expected: dict, applied: dict, c: Contract) -> list[str]:
    """Field-by-field differences between two canonical requests (empty = same)."""
    a, b = canonical(expected, c), canonical(applied, c)
    diffs = []
    for k in ("measure_id", "date_basis", "start", "end", "compare_start", "compare_end", "group_by", "sort", "top_n", "scenario_id"):
        if a[k] != b[k]:
            diffs.append(f"{k}: user asked for {a[k]!r} but call has {b[k]!r}")
    for k in sorted(set(a["filters"]) | set(b["filters"])):
        if a["filters"].get(k) != b["filters"].get(k):
            diffs.append(f"filters.{k}: user asked for {a['filters'].get(k)!r} but call has {b['filters'].get(k)!r}")
    return diffs


# ------------------------------------------------------------------------------ merge
def _narrow_geo(filters: dict, newly_set: str) -> None:
    """A narrower geography replaces a broader one (state replaces territory, customer replaces both)."""
    order = list(GEO_ORDER)
    if newly_set in order:
        for broader in order[: order.index(newly_set)]:
            filters.pop(broader, None)


def merge_state(
    prev: State,
    intent: Any,
    resolved: dict[str, Any],
    row_ref: tuple[str, Any] | None,
    c: Contract,
    ref_date: date,
    data_max: date,
) -> State:
    """Apply the user's delta to the previous state. `resolved` maps filter name -> id/value (from resolve());
    `row_ref` = (filter_name, value) when the user pointed at a row of the previous result."""
    s = prev.copy()
    action = intent.action
    for item in intent.clear:
        if item == "period":
            s.start = s.end = None
            s.compare_start = s.compare_end = s.compare_mode = None
        elif item == "compare":
            s.compare_start = s.compare_end = s.compare_mode = None
        elif item == "group_by":
            s.group_by = "none"
        elif item == "sort":
            s.sort = None
        else:
            s.filters.pop(item, None)
    if intent.scenario_id and intent.scenario_id != s.scenario_id:
        # a scenario switch resets entity selections and query scope
        s = State(scenario_id=intent.scenario_id, measure_id=s.measure_id, group_by=s.group_by)
    old_basis = s.date_basis
    if intent.measure_id:
        s.measure_id = intent.measure_id
        s.date_basis = intent.date_basis or c.default_date_basis(intent.measure_id)
        if s.date_basis == "none":
            s.start = s.end = s.compare_start = s.compare_end = s.compare_mode = None
        if old_basis == "none" and s.date_basis != "none":
            pass  # nothing carried from an undated view
    elif intent.date_basis:
        s.date_basis = intent.date_basis
    if intent.group_by:
        s.group_by = intent.group_by
    # period
    period_changed = False
    if intent.period is not None:
        s.start, s.end = resolve_period(intent.period, ref_date, data_max)
        period_changed = True
        if s.start is None:
            s.compare_start = s.compare_end = s.compare_mode = None
    cmp_mode = intent.compare
    if cmp_mode == "none":
        s.compare_start = s.compare_end = s.compare_mode = None
    elif cmp_mode in ("previous_period", "same_period_last_year"):
        if s.start and s.end:
            s.compare_start, s.compare_end = shift_period(s.start, s.end, cmp_mode)
            s.compare_mode = cmp_mode
    elif cmp_mode == "explicit" or (cmp_mode is None and intent.compare_period is not None):
        if intent.compare_period is not None:
            s.compare_start, s.compare_end = resolve_period(intent.compare_period, ref_date, data_max)
            s.compare_mode = "explicit"
    elif period_changed and s.compare_mode in ("previous_period", "same_period_last_year") and s.start:
        s.compare_start, s.compare_end = shift_period(s.start, s.end, s.compare_mode)  # keep the relative comparison
    elif period_changed and s.compare_mode == "explicit":
        s.compare_start = s.compare_end = s.compare_mode = None  # stale explicit baseline
    # filters
    for k, v in list(resolved.items()):
        s.filters[k] = v
        _narrow_geo(s.filters, k)
    for ref in intent.ids:
        s.filters[ref.filter] = ref.value
        _narrow_geo(s.filters, ref.filter)
    if intent.territory:
        s.filters["sales_territory"] = intent.territory
    if row_ref is not None:
        s.filters[row_ref[0]] = row_ref[1]
        _narrow_geo(s.filters, row_ref[0])
    if intent.status:
        s.filters["status"] = intent.status
    # a breakdown by the very thing you have just narrowed to one value is meaningless: show the total instead
    gb_filter = DIM_FILTER.get(s.group_by)
    if gb_filter and gb_filter in s.filters and not intent.group_by:
        s.group_by = "none"
        if not intent.top_n:
            s.top_n = None
    if intent.sort:
        s.sort = intent.sort
    if intent.top_n:
        s.top_n = intent.top_n
    if action == "records":
        s.compare_start = s.compare_end = s.compare_mode = None  # records are for the current period only
    if s.sort in CHANGE_SORTS and not s.compare_start:
        s.sort = None
    return s


def drill_filter(group_by: str) -> str | None:
    return DIM_FILTER.get(group_by)


def resolve_type_for(filter_name: str) -> str | None:
    return FILTER_RESOLVE_TYPE.get(filter_name)
