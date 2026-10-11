"""Loads the app Contract once and turns it into (a) pydantic models for tool parameters,
(b) semantic validation rules, and (c) compact prompt text. Nothing here calls an LLM."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SORTS = ["value_desc", "value_asc", "label_asc", "label_desc", "change_desc", "change_asc", "abs_change_desc"]
CHANGE_SORTS = {"change_desc", "change_asc", "abs_change_desc"}
# filter name -> entity type used by resolve()
FILTER_RESOLVE_TYPE = {
    "customer_id": "customer",
    "stock_item_id": "stock_item",
    "supplier_id": "supplier",
    "stock_group_id": "stock_group",
    "customer_category_id": "customer_category",
    "buying_group_id": "buying_group",
    "state_province_id": "state_province",
    "salesperson_id": "salesperson",
    "sales_territory": "sales_territory",
}
RESOLVE_TYPE_FILTER = {v: k for k, v in FILTER_RESOLVE_TYPE.items()}
# group_by value -> filter that drills into one of its rows
DIM_FILTER = {
    "customer": "customer_id",
    "stock_item": "stock_item_id",
    "supplier": "supplier_id",
    "stock_group": "stock_group_id",
    "customer_category": "customer_category_id",
    "buying_group": "buying_group_id",
    "state_province": "state_province_id",
    "salesperson": "salesperson_id",
    "sales_territory": "sales_territory",
}


class ContractError(RuntimeError):
    pass


def _d(s: str) -> date:
    return date.fromisoformat(s)


class Contract:
    def __init__(self, raw: dict, data_min: str = "2013-01-01", data_max: str = "2016-06-21"):
        self.raw = raw
        self.data_min, self.data_max = data_min, data_max
        am = raw.get("analysis_measures", {}).get("items", [])
        self.measures: dict[str, dict] = {
            m["id"]: m for m in am if m.get("date_bases") and "analyze" in (m.get("operations") or ["analyze"])
        }
        if not self.measures:
            raise ContractError("contract has no usable analysis measures")
        self.dimensions: list[str] = [x["id"] for x in raw["dimensions"]["items"]]
        self.dim_additive: dict[str, bool | None] = {x["id"]: x.get("additive") for x in raw["dimensions"]["items"]}
        self.filter_defs: dict[str, dict] = {x["id"]: x for x in raw["filters"]["items"]}
        terr = self.filter_defs.get("sales_territory", {}).get("valid_enums") or []
        self.territories: list[str] = list(terr)
        self.id_filters: list[str] = sorted(
            {f for m in self.measures.values() for f in m["filters"]} - {"sales_territory"}
        )
        self.status_values: list[str] = sorted({s for m in self.measures.values() for s in m["status_values"]})
        self.glossary: list[dict] = raw.get("glossary", {}).get("items", [])
        self.reference_date: str = raw.get("glossary", {}).get("reference_date") or "2016-05-31"
        self.playbooks: dict[str, dict] = {p["id"]: p for p in raw.get("playbooks", {}).get("items", [])}
        self.views: dict[str, dict] = {v["id"]: v for v in raw.get("views", {}).get("items", [])}
        self.entities: dict[str, dict] = {e["id"]: e for e in raw.get("graph", {}).get("entities", [])}
        self.scenarios: list[str] = list(raw.get("contract_version", {}).get("supported_scenario_ids", ["base"]))
        self.AnalyzeArgs, self.Filters = self._build_models()

    # ------------------------------------------------------------------ models
    def _build_models(self):
        measure_ids = tuple(self.measures)
        terr = tuple(self.territories) or ("",)
        fields: dict[str, Any] = {f: (Optional[int], None) for f in self.id_filters}
        fields["sales_territory"] = (Optional[Literal[terr]], None)  # type: ignore[valid-type]
        fields["status"] = (Literal[tuple(self.status_values)], "all")  # type: ignore[valid-type]
        Filters = create_model("Filters", __config__=ConfigDict(extra="forbid"), **fields)
        date_t = Optional[str]
        AnalyzeArgs = create_model(
            "AnalyzeArgs",
            __config__=ConfigDict(extra="forbid"),
            measure_id=(Literal[measure_ids], ...),  # type: ignore[valid-type]
            date_basis=(Optional[Literal[tuple(sorted({b for m in self.measures.values() for b in m["date_bases"]}))]], None),  # type: ignore[valid-type]
            start=(date_t, None),
            end=(date_t, None),
            compare_start=(date_t, None),
            compare_end=(date_t, None),
            group_by=(Literal[tuple(self.dimensions)], "none"),  # type: ignore[valid-type]
            filters=(Filters, Field(default_factory=Filters)),
            sort=(Optional[Literal[tuple(SORTS)]], None),  # type: ignore[valid-type]
            top_n=(Optional[int], Field(default=None, ge=1, le=50)),
            scenario_id=(Literal[tuple(self.scenarios)], "base"),  # type: ignore[valid-type]
        )
        return AnalyzeArgs, Filters

    # -------------------------------------------------------------- validation
    def default_date_basis(self, measure_id: str) -> str | None:
        return self.measures[measure_id]["default_date_basis"]

    def validate_analyze(self, args: dict) -> tuple[dict | None, list[str]]:
        """Return (normalised args, []) or (None, [repair hints]). Never raises on bad input."""
        if not isinstance(args, dict):
            return None, ["analyze arguments must be a JSON object"]
        errs: list[str] = []
        try:
            model = self.AnalyzeArgs.model_validate(args)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                typ = err["type"]
                if typ == "extra_forbidden":
                    errs.append(f"unknown field '{loc}'. Allowed top-level fields: measure_id, date_basis, start, end, "
                                f"compare_start, compare_end, group_by, filters, sort, top_n, scenario_id")
                elif typ == "literal_error":
                    errs.append(f"{loc}: {err['msg']}")
                elif typ == "missing":
                    errs.append(f"{loc} is required")
                else:
                    errs.append(f"{loc}: {err['msg']}")
            return None, errs
        out = model.model_dump(exclude_none=True)
        flt = {k: v for k, v in out.get("filters", {}).items() if v is not None and not (k == "status" and v == "all")}
        out["filters"] = flt
        m = self.measures[out["measure_id"]]
        # date basis
        basis = out.get("date_basis") or m["default_date_basis"]
        if basis not in m["date_bases"]:
            errs.append(f"date_basis '{basis}' is not valid for {m['id']}; use one of {m['date_bases']}")
        out["date_basis"] = basis
        # periods
        for k in ("start", "end", "compare_start", "compare_end"):
            if k in out and not DATE_RE.match(out[k]):
                errs.append(f"{k} must be an ISO date YYYY-MM-DD, got '{out[k]}'")
        if not errs:
            s, e = out.get("start"), out.get("end")
            cs, ce = out.get("compare_start"), out.get("compare_end")
            if (s is None) != (e is None):
                errs.append("give both start and end, or neither (end is exclusive: 'May 2016' is 2016-05-01 to 2016-06-01)")
            if (cs is None) != (ce is None):
                errs.append("give both compare_start and compare_end, or neither")
            if cs and not s:
                errs.append("a comparison needs the current period too: set start and end")
            for a, b, label in ((s, e, "period"), (cs, ce, "compare period")):
                if a and b:
                    try:
                        da, db = _d(a), _d(b)
                    except ValueError:
                        errs.append(f"{label}: invalid calendar date in {a}..{b}")
                        continue
                    if da >= db:
                        errs.append(f"{label}: start must be before end (end is exclusive), got {a}..{b}")
                    if da < _d(self.data_min) or db > _d(self.data_max):
                        errs.append(f"{label} {a}..{b} is outside the data range {self.data_min}..{self.data_max}")
            if basis == "none" and (s or cs):
                errs.append(f"{m['id']} with date_basis 'none' is undated; remove start/end or choose purchase_order_date / expected_delivery_date")
        # dimension
        allowed_dims = [x["id"] for x in m["dimensions"]]
        if out["group_by"] not in allowed_dims:
            why = next((v for k, v in m["not_allowed"].items() if k == out["group_by"]), None) or m.get("caveat") or ""
            errs.append(f"{m['id']} cannot be broken down by '{out['group_by']}' ({why}). Allowed group_by: {allowed_dims}")
        if out["group_by"] == "month" and basis == "none":
            errs.append("group_by month needs a dated date_basis")
        # filters
        for k, v in flt.items():
            if k == "status":
                if v not in m["status_values"]:
                    errs.append(f"status '{v}' is not valid for {m['id']}; use one of {m['status_values']}")
            elif k not in m["filters"]:
                why = m["not_allowed"].get(k) or "not applicable to this measure"
                errs.append(f"filter '{k}' cannot be used with {m['id']}: {why}")
        # sort
        sort = out.get("sort")
        has_cmp = bool(out.get("compare_start"))
        if sort in CHANGE_SORTS and not has_cmp:
            errs.append(f"sort '{sort}' needs a comparison period (compare_start/compare_end); use value_desc otherwise")
        return (None, errs) if errs else (out, [])

    # ---------------------------------------------------------------- glossary
    def glossary_find(self, text: str, limit: int = 3) -> list[dict]:
        toks = set(re.findall(r"[a-z0-9]+", text.lower()))
        scored = []
        for it in self.glossary:
            names = [it["term"]] + list(it.get("synonyms") or [])
            best = 0.0
            for n in names:
                nt = set(re.findall(r"[a-z0-9]+", n.lower()))
                if not nt:
                    continue
                if n.lower() in text.lower():
                    best = max(best, 1.0 + len(nt) * 0.01)
                else:
                    best = max(best, len(nt & toks) / len(nt) * 0.8)
            if best > 0.45:
                scored.append((best, it))
        scored.sort(key=lambda x: -x[0])
        return [it for _, it in scored[:limit]]

    def glossary_terms(self, status: str) -> list[str]:
        return [g["term"] for g in self.glossary if g["status"] == status]

    # ------------------------------------------------------------- prompt text
    def prompt_summary(self) -> str:
        sig: dict[tuple, list[str]] = {}
        for mid, m in self.measures.items():
            key = (
                tuple(x["id"] for x in m["dimensions"]),
                tuple(m["filters"]),
                tuple(m["date_bases"]),
                tuple(m["status_values"]),
            )
            sig.setdefault(key, []).append(mid)
        lines = ["MEASURES (measure_id = meaning [unit]; default date_basis):"]
        for mid, m in self.measures.items():
            cav = f" CAVEAT: {m['caveat']}" if m.get("caveat") else ""
            lines.append(f"- {mid} = {m['name']} [{m['unit']}]; date_basis {m['default_date_basis']}.{cav}")
        lines.append("CAPABILITIES:")
        for (dims, flts, bases, stat), ids in sig.items():
            lines.append(f"- {'/'.join(ids)}: group_by {list(dims)}; filters {list(flts)}; date_basis {list(bases)}; status {list(stat)}")
        lines.append(f"sales_territory values: {self.territories}")
        lines.append(f"Periods are [start,end): 'May 2016' = start 2016-05-01, end 2016-06-01. Data covers {self.data_min}..{self.data_max}. "
                     f"'This month' = May 2016 (archive end {self.reference_date}).")
        return "\n".join(lines)

    def glossary_prompt(self) -> str:
        lines = ["GLOSSARY (business word -> meaning):"]
        for g in self.glossary:
            syn = ", ".join((g.get("synonyms") or [])[:4])
            if g["status"] == "mapped":
                mp = g.get("maps_to") or {}
                tgt = mp.get("measure_id") or mp.get("filter") or mp
                lines.append(f"- {g['term']} ({syn}) -> {tgt}")
            elif g["status"] == "ambiguous":
                lines.append(f"- {g['term']} ({syn}) -> AMBIGUOUS: ask the user")
            else:
                lines.append(f"- {g['term']} ({syn}) -> UNSUPPORTED: refuse honestly")
        return "\n".join(lines)
