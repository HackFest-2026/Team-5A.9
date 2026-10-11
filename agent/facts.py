"""Code-computed facts. Differences, percentages, shares and rankings are derived here from tool results,
never by the LLM. The same facts feed the answer prompt, the faithfulness check and the template answer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .contract import Contract
from .session import Call

NUM_RE = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")


def dec(x: Any) -> Decimal | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        return Decimal(str(x).replace(",", "").rstrip("%"))
    except (InvalidOperation, ValueError):
        return None


def fmt_num(x: Any) -> str:
    """Counts with thousands separators; decimals keep their scale (money has 2 places)."""
    d = dec(x)
    if d is None:
        return str(x)
    if d == d.to_integral_value() and "." not in str(x):
        return f"{int(d):,}"
    s = f"{d:,}"
    return s


def signed(x: Any) -> str:
    d = dec(x)
    if d is None:
        return str(x)
    return ("+" if d > 0 else "") + fmt_num(x)


@dataclass
class Facts:
    lines: list[str] = field(default_factory=list)
    numbers: set[Decimal] = field(default_factory=set)
    small_int_cap: int = 0

    def num(self, *xs: Any) -> None:
        for x in xs:
            d = dec(x)
            if d is not None:
                self.numbers.add(d)


def _walk(o: Any, out: set[Decimal]) -> None:
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("query_wall_seconds",):
                continue
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)
    elif isinstance(o, bool) or o is None:
        return
    elif isinstance(o, (int, float, Decimal)):
        out.add(Decimal(str(o)))
    elif isinstance(o, str):
        d = dec(o) if re.fullmatch(r"[-+]?\d+(\.\d+)?", o.strip()) else None
        if d is not None:
            out.add(d)
        for m in NUM_RE.finditer(DATE_RE.sub(" ", o)):
            dd = dec(m.group())
            if dd is not None:
                out.add(dd)
        for m in DATE_RE.finditer(o):
            for part in m.group().split("-"):
                out.add(Decimal(int(part)))
            out.add(Decimal(m.group().replace("-", "")[:4]))


def pct(a: Any, b: Any) -> Decimal | None:
    da, db = dec(a), dec(b)
    if da is None or db is None or db == 0:
        return None
    return da / db * 100


def _add_pct(f: Facts, p: Decimal | None) -> None:
    if p is None:
        return
    for q in ("1", "0.1", "0.01"):
        f.numbers.add(p.quantize(Decimal(q)))
        f.numbers.add(abs(p).quantize(Decimal(q)))


def describe_filters(filters: dict) -> str:
    parts = []
    for k, v in filters.items():
        if k == "status" and v == "all":
            continue
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def derive(calls: list[Call], c: Contract) -> Facts:
    f = Facts()
    for call in calls:
        if not call.ok:
            continue
        _walk(call.data, f.numbers)
        if call.name == "analyze":
            _analyze_facts(call, f, c)
        elif call.name == "related":
            f.lines.append(f"Context for {call.args.get('entity_type')} {call.args.get('entity_id')}: see data.")
    f.small_int_cap = 12
    return f


def _analyze_facts(call: Call, f: Facts, c: Contract) -> None:
    d = call.data
    ap = d.get("applied", {})
    m = d.get("measure", {})
    unit = m.get("unit", "")
    dim = d.get("dimension", {})
    additive = dim.get("additive")
    flt = {k: v for k, v in (ap.get("filters") or {}).items() if v not in (None, "all")}
    head = f"{m.get('name')} [{unit}]"
    if ap.get("start"):
        head += f", {ap['start']} to {ap['end']} (end exclusive)"
    else:
        head += ", all history"
    if ap.get("compare_start"):
        head += f", compared with {ap['compare_start']} to {ap['compare_end']}"
    if flt:
        head += f", filters {describe_filters(flt)}"
    if ap.get("group_by", "none") != "none":
        head += f", by {ap['group_by']}"
    f.lines.append("ANALYSIS: " + head)
    if "total_current" in d:
        ch = d["change"]
        line = f"Current {fmt_num(d['total_current'])} vs baseline {fmt_num(d['total_baseline'])}: change {signed(ch)}"
        if d.get("pct_change") is not None:
            line += f" ({signed(d['pct_change'])}%)"
            f.num(d["pct_change"], abs(dec(d["pct_change"]) or 0))
        else:
            line += " (no % change: baseline is 0)"
        f.lines.append(line)
    elif "total" in d:
        f.lines.append(f"Total {fmt_num(d['total'])}")
    for i, row in enumerate(d.get("rows") or [], 1):
        label = row.get("label")
        if "current" in row:
            chg = dec(row["change"])
            word = "up" if chg and chg > 0 else "down" if chg and chg < 0 else "no change"
            seg = f"{i}. {label}: {word}; current {fmt_num(row['current'])}, baseline {fmt_num(row['baseline'])}, change {signed(row['change'])}"
            p = pct(row["change"], row["baseline"])
            if p is not None:
                seg += f" ({signed(p.quantize(Decimal('0.01')))}%)"
                _add_pct(f, p)
            sc = row.get("share_of_change")
            if sc is not None and additive:
                sp = Decimal(str(sc)) * 100
                seg += f", {sp.quantize(Decimal('0.1'))}% of the total change"
                _add_pct(f, sp)
        else:
            seg = f"{i}. {label}: {fmt_num(row.get('value'))}"
            sh = row.get("share")
            if sh is not None and additive:
                sp = Decimal(str(sh)) * 100
                seg += f" ({sp.quantize(Decimal('0.1'))}% of total)"
                _add_pct(f, sp)
        f.lines.append(seg)
        f.numbers.add(Decimal(i))
    if additive is False:
        f.lines.append("NOTE: groups overlap; rows do not add up to the total.")
