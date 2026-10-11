"""Workspace: create / read / update / delete for the console, kept apart from the source data.

The WWI source tables and the answer key are never written. Everything here lives in one small SQLite file
(`workspace/workspace.db`) beside the package:

  * new records   - customer, supplier, stock item, draft order (kind + data)
  * edits         - an "overlay" on a source record (kind + ref_id + the changed fields only)
  * deletes       - soft: the row is flagged and can be restored
  * audit         - every change, with the before and after values

Analytics (`/api/analyze`, `/api/metric`, ...) read only the source, so editing here cannot move a reported figure.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path

MAX_RECORDS = 2000
MAX_LINES = 20

# field: (label, type, required, max/min). Types: text, int, num, date, select:<lookup type>, ref:<entity type>
SCHEMA = {
    "customer": {"label": "Customer", "source": "customers", "key": "CustomerID", "entity": "customer",
                 "fields": {"name": ("Name", "text", True, 100), "category_id": ("Category", "select:customer_category", False, None),
                            "buying_group_id": ("Buying group", "select:buying_group", False, None),
                            "phone": ("Phone", "text", False, 30), "notes": ("Notes", "text", False, 500)},
                 "map": {"name": "CustomerName", "category_id": "CustomerCategoryID", "buying_group_id": "BuyingGroupID"}},
    "supplier": {"label": "Supplier", "source": "suppliers", "key": "SupplierID", "entity": "supplier",
                 "fields": {"name": ("Name", "text", True, 100), "phone": ("Phone", "text", False, 30), "notes": ("Notes", "text", False, 500)},
                 "map": {"name": "SupplierName"}},
    "item": {"label": "Stock item", "source": "items", "key": "StockItemID", "entity": "stock_item",
             "fields": {"name": ("Name", "text", True, 100), "supplier_id": ("Supplier", "ref:supplier", False, None),
                        "quantity_on_hand": ("Quantity on hand", "int", False, 0), "reorder_level": ("Reorder level", "int", False, 0),
                        "target_level": ("Target stock level", "int", False, 0), "notes": ("Notes", "text", False, 500)},
             "map": {"name": "StockItemName", "supplier_id": "SupplierID", "quantity_on_hand": "QuantityOnHand",
                     "reorder_level": "ReorderLevel", "target_level": "TargetStockLevel"}},
    "chart": {"label": "Chart", "source": None, "key": None, "entity": None,
              "fields": {"title": ("Title", "text", True, 80), "measure_id": ("Measure", "text", True, 8), "group_by": ("Break down by", "text", False, 30),
                         "date_basis": ("Date basis", "text", False, 40), "start": ("From", "date", False, None), "end": ("To (exclusive)", "date", False, None),
                         "compare_start": ("Compare from", "date", False, None), "compare_end": ("Compare to", "date", False, None),
                         "chart_type": ("Chart type", "text", True, 10), "top_n": ("Top N", "int", False, 1), "sort": ("Sort", "text", False, 20)},
              "map": {}},
    "order": {"label": "Draft order", "source": None, "key": None, "entity": None,
              "fields": {"customer_id": ("Customer", "ref:customer", True, None), "expected_delivery": ("Expected delivery", "date", False, None),
                         "comments": ("Comments", "text", False, 500)},
              "map": {}},
}
EDITABLE_SOURCE = {k for k, v in SCHEMA.items() if v["source"]}


def schema_public() -> dict:
    out = {}
    for k, v in SCHEMA.items():
        out[k] = {"label": v["label"], "editable_source": k in EDITABLE_SOURCE, "map": v["map"], "source": v["source"], "key": v["key"],
                  "fields": [{"name": n, "label": f[0], "type": f[1], "required": f[2], "limit": f[3]} for n, f in v["fields"].items()]}
    out["order"]["has_lines"] = True
    out["order"]["max_lines"] = MAX_LINES
    return out


class Workspace:
    def __init__(self, package: Path, known_ids):
        self.dir = Path(package) / "workspace"
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / "workspace.db"
        self.lock = threading.Lock()
        self.known_ids = known_ids          # callable(entity_type) -> set of source ids
        self._db().close()

    def _db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.executescript("""
            CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref_id INTEGER,
                data TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_overlay ON records(kind, ref_id) WHERE ref_id IS NOT NULL;
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, action TEXT NOT NULL, kind TEXT, rec_id INTEGER,
                ref_id INTEGER, before TEXT, after TEXT, note TEXT);
            """)   # idempotent: also recreates the file if it was removed
        return c

    # ---------------------------------------------------------------- validation
    def clean(self, kind: str, data: dict, partial: bool) -> dict:
        if kind not in SCHEMA:
            raise ValueError(f"kind must be one of {sorted(SCHEMA)}")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        sch = SCHEMA[kind]["fields"]
        unknown = [k for k in data if k not in sch and not (kind == "order" and k == "lines")]
        if unknown:
            raise ValueError(f"unknown field(s) for {kind}: {', '.join(unknown)}")
        out: dict = {}
        for name, (label, typ, req, lim) in sch.items():
            if name not in data:
                if req and not partial:
                    raise ValueError(f"{label} is required")
                continue
            v = data[name]
            if v in (None, ""):
                if req:
                    raise ValueError(f"{label} is required")
                out[name] = None
                continue
            if typ == "text":
                v = re.sub(r"\s+", " ", str(v)).strip()
                if not v and req:
                    raise ValueError(f"{label} is required")
                if len(v) > lim:
                    raise ValueError(f"{label} must be at most {lim} characters")
            elif typ in ("int", "select:customer_category", "select:buying_group") or typ.startswith("ref:"):
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{label} must be a whole number")
                if f != int(f):
                    raise ValueError(f"{label} must be a whole number")
                v = int(f)
                if typ == "int" and v < (lim or 0):
                    raise ValueError(f"{label} cannot be negative")
                if typ.startswith("ref:"):
                    ent = typ.split(":")[1]
                    if v not in self.known_ids(ent):
                        raise ValueError(f"{label}: no {ent} with ID {v} in the source data")
            elif typ == "date":
                try:
                    v = date.fromisoformat(str(v)).isoformat()
                except ValueError:
                    raise ValueError(f"{label} must be a date like 2016-06-30")
            out[name] = v
        if kind == "chart":
            self._check_chart(out)
        if kind == "order":
            if "lines" in data or not partial:
                lines = data.get("lines") or []
                if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES:
                    raise ValueError(f"A draft order needs 1 to {MAX_LINES} lines")
                items = self.known_ids("stock_item")
                ln = []
                for i, l in enumerate(lines, 1):
                    try:
                        iid, q = int(l.get("item_id")), int(l.get("qty"))
                    except (TypeError, ValueError, AttributeError):
                        raise ValueError(f"Line {i}: choose an item and a whole quantity")
                    if iid not in items:
                        raise ValueError(f"Line {i}: no stock item with ID {iid} in the source data")
                    if not 1 <= q <= 100000:
                        raise ValueError(f"Line {i}: quantity must be between 1 and 100,000")
                    ln.append({"item_id": iid, "qty": q, "item_name": str(l.get("item_name") or "")[:100]})
                out["lines"] = ln
        return out

    # ---------------------------------------------------------------- chart definitions
    CHART_TYPES = {"bar", "hbar", "line", "pie", "number"}
    SORTS = {"value_desc", "value_asc", "label_asc", "label_desc"}

    def _measures(self) -> dict:
        if not hasattr(self, "_mcache"):
            doc = json.loads((self.dir.parent / "catalog" / "analysis_measures.json").read_text())
            self._mcache = {m["id"]: m for m in doc["items"] if m["status"] in ("verified", "published-with-caveat") and "analyze" in m["operations"]}
        return self._mcache

    def _check_chart(self, d: dict) -> None:
        """A chart stores a request for /api/analyze, never data: the figures are computed from the governed API every time it is drawn."""
        m = self._measures().get(d.get("measure_id"))
        if not m:
            raise ValueError("Measure is not published for charts")
        dims = {x["id"]: x for x in m["dimensions"]}
        g = d.get("group_by") or "none"
        if g not in dims:
            raise ValueError(f"{m['name']} cannot be broken down by {g}")
        d["group_by"] = g
        if d.get("date_basis") and d["date_basis"] not in m["date_bases"]:
            raise ValueError(f"Date basis must be one of {', '.join(m['date_bases'])}")
        for a, b, label in (("start", "end", "period"), ("compare_start", "compare_end", "comparison period")):
            x, y = d.get(a), d.get(b)
            if (x is None) != (y is None):
                raise ValueError(f"Give both dates of the {label}")
            if x is not None and not ("2013-01-01" <= x < y <= "2016-06-21"):
                raise ValueError(f"The {label} must lie within 2013-01-01 and 2016-06-21 and end after it starts")
        if d.get("compare_start") and not d.get("start"):
            raise ValueError("A comparison needs the current period too")
        if g == "month" and d.get("compare_start"):
            raise ValueError("A monthly chart cannot compare two periods; use one wider period")
        t = d.get("chart_type")
        if t not in self.CHART_TYPES:
            raise ValueError("Chart type must be bar, hbar, line, pie or number")
        if g == "none" and t != "number":
            d["chart_type"] = t = "number"
        if g != "none" and t == "number":
            raise ValueError("Choose a bar, line or pie chart for a breakdown")
        if t == "line" and g != "month":
            raise ValueError("A line chart needs the breakdown Month")
        if t == "pie" and (not dims[g].get("additive") or d.get("compare_start")):
            raise ValueError("A pie chart needs a breakdown whose parts add up, and no comparison")
        if d.get("top_n") is not None and not 1 <= d["top_n"] <= 50:
            raise ValueError("Top N must be between 1 and 50")
        if d.get("sort") and d["sort"] not in self.SORTS:
            raise ValueError("Unknown sort")

    # ---------------------------------------------------------------- reads
    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["data"] = json.loads(d["data"])
        d["deleted"] = bool(d["deleted"])
        return d

    def list(self, kind: str | None, include_deleted: bool, ref_id: int | None = None) -> list[dict]:
        q, a = "SELECT * FROM records WHERE 1=1", []
        if kind:
            q += " AND kind=?"; a.append(kind)
        if ref_id is not None:
            q += " AND ref_id=?"; a.append(ref_id)
        if not include_deleted:
            q += " AND deleted=0"
        with self._db() as c:
            return [self._row(r) for r in c.execute(q + " ORDER BY updated DESC LIMIT 500", a)]

    def get(self, rid: int) -> dict:
        with self._db() as c:
            r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
        if not r:
            raise LookupError(f"no workspace record {rid}")
        return self._row(r)

    def audit(self, limit: int = 100) -> list[dict]:
        with self._db() as c:
            rows = c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 500),)).fetchall()
        return [{**dict(r), "before": json.loads(r["before"]) if r["before"] else None, "after": json.loads(r["after"]) if r["after"] else None} for r in rows]

    def counts(self) -> dict:
        with self._db() as c:
            rows = c.execute("SELECT kind, ref_id IS NOT NULL AS edit, COUNT(*) n FROM records WHERE deleted=0 GROUP BY 1,2").fetchall()
        return {f"{r['kind']}{'_edits' if r['edit'] else ''}": r["n"] for r in rows}

    # ---------------------------------------------------------------- writes
    def _log(self, c, action, kind, rec_id, ref_id, before, after, note=""):
        c.execute("INSERT INTO audit(ts,action,kind,rec_id,ref_id,before,after,note) VALUES(?,?,?,?,?,?,?,?)",
                  (time.time(), action, kind, rec_id, ref_id, json.dumps(before) if before is not None else None,
                   json.dumps(after) if after is not None else None, note))

    def create(self, kind: str, data: dict) -> dict:
        d = self.clean(kind, data, partial=False)
        now = time.time()
        with self.lock, self._db() as c:
            if c.execute("SELECT COUNT(*) FROM records").fetchone()[0] >= MAX_RECORDS:
                raise ValueError("The workspace is full")
            cur = c.execute("INSERT INTO records(kind,ref_id,data,created,updated) VALUES(?,?,?,?,?)", (kind, None, json.dumps(d), now, now))
            self._log(c, "create", kind, cur.lastrowid, None, None, d)
            return self.get_in(c, cur.lastrowid)

    def edit_source(self, kind: str, ref_id: int, data: dict, source_now: dict) -> dict:
        """Save the fields that differ from the source row (`source_now`, in workspace field names) as an overlay."""
        if kind not in EDITABLE_SOURCE:
            raise ValueError(f"{kind} records cannot be edited")
        if ref_id not in self.known_ids(SCHEMA[kind]["entity"]):
            raise ValueError(f"no {kind} with ID {ref_id} in the source data")
        d = self.clean(kind, data, partial=True)
        mapped = SCHEMA[kind]["map"]
        diff = {k: v for k, v in d.items() if (v != source_now.get(k) if k in mapped else True)}
        now = time.time()
        with self.lock, self._db() as c:
            row = c.execute("SELECT * FROM records WHERE kind=? AND ref_id=?", (kind, ref_id)).fetchone()
            if not diff:
                if row:   # everything was set back to the source: drop the overlay
                    c.execute("DELETE FROM records WHERE id=?", (row["id"],))
                    self._log(c, "revert", kind, row["id"], ref_id, json.loads(row["data"]), None, "back to source values")
                return {"unchanged": True}
            prior = json.loads(row["data"]) if row else {}
            diff = {k: v for k, v in diff.items() if v is not None or k in prior or k in mapped}
            if not diff and not row:
                return {"unchanged": True}
            if row:
                before = prior
                c.execute("UPDATE records SET data=?, deleted=0, version=version+1, updated=? WHERE id=?", (json.dumps(diff), now, row["id"]))
                rid = row["id"]
            else:
                before = None
                rid = c.execute("INSERT INTO records(kind,ref_id,data,created,updated) VALUES(?,?,?,?,?)", (kind, ref_id, json.dumps(diff), now, now)).lastrowid
            self._log(c, "edit", kind, rid, ref_id, before, diff)
            return self.get_in(c, rid)

    def update(self, rid: int, data: dict, version: int | None) -> dict:
        now = time.time()
        with self.lock, self._db() as c:
            r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
            if not r:
                raise LookupError(f"no workspace record {rid}")
            if r["ref_id"] is not None:
                raise ValueError("This is an edit of a source record; save it through the source record's edit form")
            if version is not None and version != r["version"]:
                raise ValueError("This record was changed by someone else. Reload and try again.")
            d = self.clean(r["kind"], data, partial=False)
            before = json.loads(r["data"])
            c.execute("UPDATE records SET data=?, version=version+1, updated=? WHERE id=?", (json.dumps(d), now, rid))
            self._log(c, "update", r["kind"], rid, None, before, d)
            return self.get_in(c, rid)

    def set_deleted(self, rid: int, deleted: bool) -> dict:
        with self.lock, self._db() as c:
            r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
            if not r:
                raise LookupError(f"no workspace record {rid}")
            c.execute("UPDATE records SET deleted=?, version=version+1, updated=? WHERE id=?", (1 if deleted else 0, time.time(), rid))
            self._log(c, "delete" if deleted else "restore", r["kind"], rid, r["ref_id"], json.loads(r["data"]), None)
            return self.get_in(c, rid)

    def get_in(self, c, rid: int) -> dict:
        return self._row(c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone())
