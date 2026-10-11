"""Independent oracle for the WWI v2 evaluation corpus.

Reads ONLY the raw Parquet files (data/raw) and the labelled synthetic
fixture (data/synthetic/no_incoming_v1). It deliberately does not import or
read the package engine (scripts/engine.py, analysis_v2.py, serve_v2.py) or
data/wwi.duckdb. Every SQL statement here is written from docs/V2_SPEC.md.

Library use:
    from oracle_v2 import Oracle
    o = Oracle()                       # package root auto-detected
    o.analyze({"measure_id": "M01", "start": "2016-05-01", "end": "2016-06-01"})
    o.resolve("litware", ["supplier"])
    o.item_summary(80)

CLI:
    python -I scripts/oracle_v2.py --selftest
    python -I scripts/oracle_v2.py --analyze '{"measure_id":"M02","group_by":"stock_item","top_n":5}'
    python -I scripts/oracle_v2.py --resolve hudson --types salesperson
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import duckdb

ORACLE_VERSION = "oracle_v2 1.0.1"
DATASET_VERSION = "wwi-data-v1-2026-10-08"
MIN_DATE = dt.date(2013, 1, 1)
MAX_DATE = dt.date(2016, 6, 21)
CURRENCY_LABEL = "sample amount (currency not stated in source)"

TERRITORIES = ["Far West", "Great Lakes", "Mideast", "New England", "Plains",
               "Rocky Mountain", "Southeast", "Southwest", "External"]

ORDER_MEASURES = {"M01", "M02", "M03", "M13"}
INVOICE_MEASURES = {"M10", "M11"}
PURCHASE_MEASURES = {"M05"}

MEASURES = {
    "M01": {"name": "Orders created", "unit": "orders", "grain": "order",
            "definition": "COUNT(DISTINCT OrderID) over order lines in scope"},
    "M02": {"name": "Stored unpicked units", "unit": "item units", "grain": "order line",
            "definition": "SUM(GREATEST(Quantity - PickedQuantity, 0)) over order lines"},
    "M03": {"name": "Orders with unpicked quantities", "unit": "orders", "grain": "order",
            "definition": "COUNT(DISTINCT OrderID) over lines with Quantity - PickedQuantity > 0"},
    "M13": {"name": "Ordered units", "unit": "item units", "grain": "order line",
            "definition": "SUM(Quantity) over order lines"},
    "M05": {"name": "Related incoming units", "unit": "item units", "grain": "purchase line",
            "definition": "SUM((OrderedOuters - ReceivedOuters) * QuantityPerOuter) over open purchase lines"},
    "M10": {"name": "Invoiced sales excluding tax", "unit": CURRENCY_LABEL, "grain": "invoice line",
            "definition": "SUM(ExtendedPrice - TaxAmount)"},
    "M11": {"name": "Recorded gross line profit", "unit": CURRENCY_LABEL, "grain": "invoice line",
            "definition": "SUM(LineProfit) (recorded line profit, not net profit)"},
}
MONEY = INVOICE_MEASURES

CUSTOMER_DIMS = {"customer", "customer_category", "buying_group", "state_province",
                 "sales_territory", "salesperson"}
ALL_DIMS = {"none", "month", "stock_item", "supplier", "stock_group"} | CUSTOMER_DIMS

CUSTOMER_FILTERS = {"customer_id", "customer_category_id", "buying_group_id",
                    "state_province_id", "sales_territory", "salesperson_id",
                    "order_id", "order_line_id"}
ITEM_FILTERS = {"stock_item_id", "supplier_id", "stock_group_id"}
PURCHASE_FILTERS = {"purchase_order_id", "purchase_line_id"}
ALL_FILTERS = CUSTOMER_FILTERS | ITEM_FILTERS | PURCHASE_FILTERS | {"status"}

SORTS = {"value_desc", "value_asc", "label_asc", "label_desc",
         "change_desc", "change_asc", "abs_change_desc"}
ORDER_STATUS = {"all", "quantity-not-yet-picked", "picking-incomplete", "picking-complete"}


class Reject(Exception):
    """Invalid request -> the engine must answer HTTP 422 {completed:false}."""


def _pkg_root() -> Path:
    return Path(__file__).resolve().parent.parent


def money_str(v) -> str:
    return f"{Decimal(v if v is not None else 0).quantize(Decimal('0.01')):.2f}"


class Oracle:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else _pkg_root()
        self.raw = self.root / "data" / "raw"
        self.syn = self.root / "data" / "synthetic" / "no_incoming_v1"
        self.con = duckdb.connect()
        self._load()

    # ------------------------------------------------------------------ load
    def _p(self, name: str) -> str:
        return str(self.raw / f"{name}.parquet").replace("'", "''")

    def _s(self, name: str) -> str:
        return str(self.syn / f"{name}.parquet").replace("'", "''")

    def _load(self):
        c = self.con
        for tbl in ["Sales.Orders", "Sales.OrderLines", "Sales.Customers", "Sales.CustomerCategories",
                    "Sales.BuyingGroups", "Sales.Invoices", "Sales.InvoiceLines", "Warehouse.StockItems",
                    "Warehouse.StockItemHoldings", "Warehouse.StockItemStockGroups", "Warehouse.StockGroups",
                    "Purchasing.PurchaseOrders", "Purchasing.PurchaseOrderLines", "Purchasing.Suppliers",
                    "Application.People", "Application.Cities", "Application.StateProvinces"]:
            c.execute(f"CREATE VIEW \"{tbl.replace('.', '_')}\" AS SELECT * FROM read_parquet('{self._p(tbl)}')")
        # synthetic fixture rows (additive branch)
        c.execute(f"""CREATE VIEW syn_orders AS SELECT OrderID, CustomerID, SalespersonPersonID, OrderDate,
                      PickingCompletedWhen, BackorderOrderID FROM read_parquet('{self._s('Sales_Orders')}')""")
        c.execute(f"""CREATE VIEW syn_lines AS SELECT OrderLineID, OrderID, StockItemID, Quantity, PickedQuantity
                      FROM read_parquet('{self._s('Sales_OrderLines')}')""")
        c.execute(f"""CREATE VIEW syn_items AS SELECT StockItemID, StockItemName, SupplierID, QuantityPerOuter
                      FROM read_parquet('{self._s('Warehouse_StockItems')}')""")
        c.execute(f"""CREATE VIEW syn_holdings AS SELECT StockItemID, QuantityOnHand, ReorderLevel, TargetStockLevel,
                      BinLocation FROM read_parquet('{self._s('Warehouse_StockItemHoldings')}')""")
        # customer geography (current stored attributes)
        c.execute("""CREATE TABLE cust AS
            SELECT cu.CustomerID, cu.CustomerName, cu.CustomerCategoryID, cc.CustomerCategoryName,
                   cu.BuyingGroupID, bg.BuyingGroupName, sp.StateProvinceID, sp.StateProvinceName,
                   sp.SalesTerritory
            FROM Sales_Customers cu
            JOIN Sales_CustomerCategories cc USING (CustomerCategoryID)
            LEFT JOIN Sales_BuyingGroups bg USING (BuyingGroupID)
            JOIN Application_Cities ci ON ci.CityID = cu.DeliveryCityID
            JOIN Application_StateProvinces sp ON sp.StateProvinceID = ci.StateProvinceID""")
        # Scenario scope follows v1 (scenario.json "fixture business records only"): the fixture scenario
        # contains ONLY the synthetic records; it is not an overlay on base data.
        for scen, src_items, src_orders, src_lines in [
                ("base", "Warehouse_StockItems", "Sales_Orders", "Sales_OrderLines"),
                ("no_incoming_v1", "syn_items", "syn_orders", "syn_lines")]:
            c.execute(f"""CREATE TABLE items_{scen} AS
                SELECT StockItemID, StockItemName, SupplierID, QuantityPerOuter FROM {src_items}""")
            c.execute(f"""CREATE TABLE ol_{scen} AS
                WITH o AS (SELECT OrderID, CustomerID, SalespersonPersonID, OrderDate, PickingCompletedWhen
                           FROM {src_orders}),
                     l AS (SELECT OrderLineID, OrderID, StockItemID, Quantity, PickedQuantity
                           FROM {src_lines})
                SELECT l.OrderLineID, l.OrderID, l.StockItemID, l.Quantity, l.PickedQuantity,
                       o.OrderDate AS d, o.CustomerID, o.SalespersonPersonID AS SalespersonID,
                       o.PickingCompletedWhen AS OrderPickingCompletedWhen,
                       it.SupplierID AS ItemSupplierID
                FROM l JOIN o USING (OrderID) JOIN items_{scen} it USING (StockItemID)""")
        c.execute("""CREATE TABLE il AS
            SELECT il.InvoiceLineID, il.InvoiceID, il.StockItemID, il.ExtendedPrice, il.TaxAmount, il.LineProfit,
                   i.InvoiceDate AS d, i.CustomerID, i.SalespersonPersonID AS SalespersonID, i.OrderID,
                   it.SupplierID AS ItemSupplierID
            FROM Sales_InvoiceLines il JOIN Sales_Invoices i USING (InvoiceID)
            JOIN Warehouse_StockItems it USING (StockItemID)""")
        c.execute("""CREATE TABLE pl AS
            SELECT l.PurchaseOrderLineID, l.PurchaseOrderID, l.StockItemID, l.OrderedOuters, l.ReceivedOuters,
                   it.QuantityPerOuter, (l.OrderedOuters - l.ReceivedOuters) * it.QuantityPerOuter AS open_units,
                   p.SupplierID AS POSupplierID, p.OrderDate AS po_date, p.ExpectedDeliveryDate AS exp_date
            FROM Purchasing_PurchaseOrderLines l JOIN Purchasing_PurchaseOrders p USING (PurchaseOrderID)
            JOIN Warehouse_StockItems it USING (StockItemID)
            WHERE NOT p.IsOrderFinalized AND NOT l.IsOrderLineFinalized AND l.OrderedOuters > l.ReceivedOuters""")

    def q(self, sql, params=None):
        return self.con.execute(sql, params or []).fetchall()

    # -------------------------------------------------------------- validate
    def _validate(self, req: dict) -> dict:
        known = {"measure_id", "date_basis", "start", "end", "compare_start", "compare_end",
                 "group_by", "filters", "sort", "top_n", "scenario_id", "dataset_version"}
        extra = set(req) - known
        if extra:
            raise Reject(f"unknown fields {sorted(extra)}")
        m = req.get("measure_id")
        if m not in MEASURES:
            raise Reject(f"unknown measure_id {m!r}")
        scen = req.get("scenario_id", "base") or "base"
        if scen not in ("base", "no_incoming_v1"):
            raise Reject(f"unknown scenario {scen}")
        if m in INVOICE_MEASURES and scen != "base":
            raise Reject("the synthetic fixture has no invoices; money measures are base-only")
        if m in ORDER_MEASURES:
            allowed_db, default_db = {"order_date"}, "order_date"
        elif m in INVOICE_MEASURES:
            allowed_db, default_db = {"invoice_date"}, "invoice_date"
        else:
            allowed_db, default_db = {"none", "purchase_order_date", "expected_delivery_date"}, "none"
        db = req.get("date_basis") or default_db
        if db not in allowed_db:
            raise Reject(f"date_basis {db} invalid for {m}")

        def pdate(x, name):
            if x is None:
                return None
            try:
                return dt.date.fromisoformat(x)
            except Exception:
                raise Reject(f"bad date {name}={x!r}")

        start, end = pdate(req.get("start"), "start"), pdate(req.get("end"), "end")
        cs, ce = pdate(req.get("compare_start"), "compare_start"), pdate(req.get("compare_end"), "compare_end")
        for a, b, nm in [(start, end, "period"), (cs, ce, "compare period")]:
            if (a is None) != (b is None):
                raise Reject(f"{nm} needs both start and end")
            if a is not None:
                if not (MIN_DATE <= a < b <= MAX_DATE):
                    raise Reject(f"{nm} outside 2013-01-01..2016-06-21 or start>=end")
        if cs is not None and start is None:
            raise Reject("compare period requires a current period")
        if db == "none" and (start is not None or cs is not None):
            raise Reject("M05 with date_basis none takes no period")
        g = req.get("group_by") or "none"
        if g not in ALL_DIMS:
            raise Reject(f"unknown group_by {g}")
        if m in PURCHASE_MEASURES and g in CUSTOMER_DIMS:
            raise Reject("customer-side dimensions are invalid for M05 (purchasing is not allocated to customers)")
        if g == "month" and db == "none":
            raise Reject("month needs a dated basis")
        filters = dict(req.get("filters") or {})
        filters = {k: v for k, v in filters.items() if v is not None}
        for k, v in filters.items():
            if k not in ALL_FILTERS:
                raise Reject(f"unknown filter {k}")
            if k == "sales_territory":
                if v not in TERRITORIES:
                    raise Reject(f"unknown sales_territory {v!r}")
            elif k == "status":
                pass
            elif not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
                raise Reject(f"filter {k} must be a positive integer")
        if m in PURCHASE_MEASURES:
            bad = set(filters) & CUSTOMER_FILTERS
            if bad:
                raise Reject(f"filters {sorted(bad)} invalid for M05")
            if filters.get("status", "all") not in ("all", "incoming"):
                raise Reject("status for M05 must be all|incoming")
        else:
            bad = set(filters) & PURCHASE_FILTERS
            if bad:
                raise Reject(f"filters {sorted(bad)} valid only for M05")
            if m in ORDER_MEASURES and filters.get("status", "all") not in ORDER_STATUS:
                raise Reject("bad status for order measure")
            if m in INVOICE_MEASURES and filters.get("status", "all") != "all":
                raise Reject("status invalid for invoice measures unless 'all'")
        compare = cs is not None
        sort = req.get("sort") or ("abs_change_desc" if compare else "value_desc")
        if sort not in SORTS:
            raise Reject(f"bad sort {sort}")
        if not compare and sort in ("change_desc", "change_asc", "abs_change_desc"):
            raise Reject("change sorts need a compare period")
        top_n = req.get("top_n", 10)
        if top_n is None:
            top_n = 10
        if not (isinstance(top_n, int) and 1 <= top_n <= 50):
            raise Reject("top_n must be 1..50")
        if scen != "base" and m in (INVOICE_MEASURES | PURCHASE_MEASURES):
            pass  # fixture adds no invoices/purchasing; base rows apply
        applied = {"measure_id": m, "date_basis": db,
                   "start": req.get("start"), "end": req.get("end"),
                   "group_by": g, "filters": dict(sorted(filters.items())), "sort": sort, "top_n": top_n,
                   "scenario_id": scen}
        if compare:
            applied["compare_start"] = req.get("compare_start")
            applied["compare_end"] = req.get("compare_end")
        return applied

    # ------------------------------------------------------------- building
    def _base(self, a: dict):
        """Return (from_sql, where_list, params, date_col, value_expr) for the measure family."""
        m, scen, f = a["measure_id"], a["scenario_id"], a["filters"]
        where, params = [], []
        if m in ORDER_MEASURES:
            frm = f"ol_{scen} x"
            date_col = "x.d"
            st = f.get("status", "all")
            if st == "quantity-not-yet-picked":
                where.append("x.Quantity - x.PickedQuantity > 0")
            elif st == "picking-incomplete":
                where.append("x.OrderPickingCompletedWhen IS NULL")
            elif st == "picking-complete":
                where.append("x.OrderPickingCompletedWhen IS NOT NULL")
            if "order_line_id" in f:
                where.append("x.OrderLineID = ?"); params.append(f["order_line_id"])
        elif m in INVOICE_MEASURES:
            frm = "il x"
            date_col = "x.d"
            if "order_line_id" in f:
                # spec lists order_line_id as valid for invoice measures; invoice lines have no order-line key.
                # Choice: lines of the invoice for that line's order AND the same stock item.
                where.append(f"""EXISTS (SELECT 1 FROM ol_base z WHERE z.OrderLineID = ?
                                 AND z.OrderID = x.OrderID AND z.StockItemID = x.StockItemID)""")
                params.append(f["order_line_id"])
        else:
            frm = "pl x"
            if scen != "base":
                where.append("FALSE")  # v1: purchasing exists only in base; the fixture has no incoming supply
            date_col = {"none": None, "purchase_order_date": "x.po_date",
                        "expected_delivery_date": "x.exp_date"}[a["date_basis"]]
            if "purchase_order_id" in f:
                where.append("x.PurchaseOrderID = ?"); params.append(f["purchase_order_id"])
            if "purchase_line_id" in f:
                where.append("x.PurchaseOrderLineID = ?"); params.append(f["purchase_line_id"])
        # customer-side filters
        cust_map = {"customer_id": "CustomerID", "customer_category_id": "CustomerCategoryID",
                    "buying_group_id": "BuyingGroupID", "state_province_id": "StateProvinceID",
                    "sales_territory": "SalesTerritory"}
        for k, col in cust_map.items():
            if k in f:
                if k == "customer_id":
                    where.append("x.CustomerID = ?")
                else:
                    where.append(f"x.CustomerID IN (SELECT CustomerID FROM cust WHERE {col} = ?)")
                params.append(f[k])
        if "salesperson_id" in f:
            where.append("x.SalespersonID = ?"); params.append(f["salesperson_id"])
        if "order_id" in f:
            where.append("x.OrderID = ?"); params.append(f["order_id"])
        if "stock_item_id" in f:
            where.append("x.StockItemID = ?"); params.append(f["stock_item_id"])
        if "supplier_id" in f:
            where.append(("x.POSupplierID" if m in PURCHASE_MEASURES else "x.ItemSupplierID") + " = ?")
            params.append(f["supplier_id"])
        if "stock_group_id" in f:
            where.append("EXISTS (SELECT 1 FROM Warehouse_StockItemStockGroups sg "
                         "WHERE sg.StockItemID = x.StockItemID AND sg.StockGroupID = ?)")
            params.append(f["stock_group_id"])
        value = {"M01": "COUNT(DISTINCT x.OrderID)",
                 "M02": "COALESCE(SUM(GREATEST(x.Quantity - x.PickedQuantity, 0)), 0)",
                 "M03": "COUNT(DISTINCT CASE WHEN x.Quantity - x.PickedQuantity > 0 THEN x.OrderID END)",
                 "M13": "COALESCE(SUM(x.Quantity), 0)",
                 "M05": "COALESCE(SUM(x.open_units), 0)",
                 "M10": "COALESCE(SUM(x.ExtendedPrice - x.TaxAmount), 0)",
                 "M11": "COALESCE(SUM(x.LineProfit), 0)"}[m]
        return frm, where, params, date_col, value

    def _dim(self, a: dict):
        """Return (join_sql, key_expr, label_expr, additive)."""
        g, m = a["group_by"], a["measure_id"]
        items = f"items_{a['scenario_id']}" if m in ORDER_MEASURES else "Warehouse_StockItems"
        counts = m in ("M01", "M03")
        if g == "month":
            return "", "strftime(DATECOL, '%Y-%m')", "strftime(DATECOL, '%Y-%m')", True
        if g == "customer":
            return "JOIN cust c ON c.CustomerID = x.CustomerID", "c.CustomerID", "c.CustomerName", True
        if g == "customer_category":
            return ("JOIN cust c ON c.CustomerID = x.CustomerID", "c.CustomerCategoryID",
                    "c.CustomerCategoryName", True)
        if g == "buying_group":
            return ("JOIN cust c ON c.CustomerID = x.CustomerID", "c.BuyingGroupID",
                    "COALESCE(c.BuyingGroupName, 'No buying group')", True)
        if g == "state_province":
            return "JOIN cust c ON c.CustomerID = x.CustomerID", "c.StateProvinceID", "c.StateProvinceName", True
        if g == "sales_territory":
            return "JOIN cust c ON c.CustomerID = x.CustomerID", "c.SalesTerritory", "c.SalesTerritory", True
        if g == "salesperson":
            return ("JOIN Application_People pp ON pp.PersonID = x.SalespersonID", "pp.PersonID",
                    "pp.FullName", True)
        if g == "stock_item":
            return (f"JOIN {items} si ON si.StockItemID = x.StockItemID", "si.StockItemID", "si.StockItemName",
                    not counts)
        if g == "supplier":
            col = "x.POSupplierID" if m in PURCHASE_MEASURES else "x.ItemSupplierID"
            return (f"JOIN Purchasing_Suppliers su ON su.SupplierID = {col}", "su.SupplierID", "su.SupplierName",
                    not counts)
        if g == "stock_group":
            return ("JOIN Warehouse_StockItemStockGroups sig ON sig.StockItemID = x.StockItemID "
                    "JOIN Warehouse_StockGroups sgn ON sgn.StockGroupID = sig.StockGroupID",
                    "sgn.StockGroupID", "sgn.StockGroupName", False)
        raise Reject(g)

    def _agg(self, a, start, end):
        frm, where, params, date_col, value = self._base(a)
        where = list(where)
        params = list(params)
        if start is not None:
            where.append(f"{date_col} >= ? AND {date_col} < ?")
            params += [dt.date.fromisoformat(start), dt.date.fromisoformat(end)]
        wsql = ("WHERE " + " AND ".join(where)) if where else ""
        total = self.q(f"SELECT {value} FROM {frm} {wsql}", params)[0][0]
        rows = None
        additive = None
        if a["group_by"] != "none":
            join, key, label, additive = self._dim(a)
            key = key.replace("DATECOL", date_col or "NULL")
            label = label.replace("DATECOL", date_col or "NULL")
            rows = self.q(f"SELECT {key} AS k, {label} AS lbl, {value} AS v FROM {frm} {join} {wsql} "
                          f"GROUP BY 1, 2", params)
        return total, rows, additive

    # -------------------------------------------------------------- analyze
    def analyze(self, req: dict) -> dict:
        try:
            a = self._validate(req)
        except Reject as e:
            return {"completed": False, "http_status": 422, "error": str(e)}
        m = a["measure_id"]
        money = m in MONEY
        conv = (lambda v: Decimal(v)) if money else (lambda v: int(v))
        out_v = money_str if money else (lambda v: v)
        compare = "compare_start" in a
        g = a["group_by"]
        additive = None
        if g != "none":
            additive = self._dim(a)[3]
        res = {"completed": True, "applied": a,
               "measure": {"id": m, **MEASURES[m]},
               "dimension": {"id": g, "additive": additive},
               "deep_link": deep_link(a)}
        if money:
            res["caveat"] = ("Currency is not stated in the source; amounts are sample amounts. "
                             + ("M11 is recorded line profit, not net profit." if m == "M11" else ""))
        if not compare:
            total, rows, _ = self._agg(a, a["start"], a["end"])
            total = conv(total)
            res["total"] = out_v(total)
            if g != "none":
                rs = [{"key": k, "label": l, "value": conv(v)} for k, l, v in rows]
                rs = _sort(rs, a["sort"], "value")
                top, rest = rs[:a["top_n"]], rs[a["top_n"]:]
                if additive and rest:
                    top.append({"key": None, "label": "All others",
                                "value": sum((r["value"] for r in rest), conv(0)),
                                "groups": len(rest)})
                for r in top:
                    r["share"] = (None if not additive or total == 0
                                  else round(float(Decimal(r["value"]) / Decimal(total)), 6))
                    r["value"] = out_v(r["value"])
                res["rows"] = top
                res["group_count"] = len(rs)
            return res
        bt, brows, _ = self._agg(a, a["compare_start"], a["compare_end"])
        ct, crows, _ = self._agg(a, a["start"], a["end"])
        bt, ct = conv(bt), conv(ct)
        change = ct - bt
        res["total_baseline"] = out_v(bt)
        res["total_current"] = out_v(ct)
        res["change"] = out_v(change)
        res["pct_change"] = None if bt == 0 else round(float(Decimal(change) * 100 / Decimal(bt)), 2)
        if g != "none":
            merged = {}
            for k, l, v in brows:
                merged.setdefault(k, {"key": k, "label": l, "baseline": conv(0), "current": conv(0)})
                merged[k]["baseline"] = conv(v)
            for k, l, v in crows:
                merged.setdefault(k, {"key": k, "label": l, "baseline": conv(0), "current": conv(0)})
                merged[k]["current"] = conv(v)
            rs = list(merged.values())
            for r in rs:
                r["change"] = r["current"] - r["baseline"]
            rs = _sort(rs, a["sort"], "current")
            top, rest = rs[:a["top_n"]], rs[a["top_n"]:]
            if additive and rest:
                o = {"key": None, "label": "All others", "groups": len(rest)}
                for fld in ("baseline", "current", "change"):
                    o[fld] = sum((r[fld] for r in rest), conv(0))
                top.append(o)
            for r in top:
                r["share_of_change"] = (None if not additive or change == 0
                                        else round(float(Decimal(r["change"]) / Decimal(change)), 6))
                for fld in ("baseline", "current", "change"):
                    r[fld] = out_v(r[fld])
            res["rows"] = top
            res["group_count"] = len(rs)
        return res

    # --------------------------------------------------------------- lookups
    def name(self, etype: str, eid):
        sql = {"customer": "SELECT CustomerName FROM Sales_Customers WHERE CustomerID=?",
               "stock_item": "SELECT StockItemName FROM items_no_incoming_v1 WHERE StockItemID=?",
               "supplier": "SELECT SupplierName FROM Purchasing_Suppliers WHERE SupplierID=?",
               "customer_category": "SELECT CustomerCategoryName FROM Sales_CustomerCategories WHERE CustomerCategoryID=?",
               "buying_group": "SELECT BuyingGroupName FROM Sales_BuyingGroups WHERE BuyingGroupID=?",
               "stock_group": "SELECT StockGroupName FROM Warehouse_StockGroups WHERE StockGroupID=?",
               "state_province": "SELECT StateProvinceName FROM Application_StateProvinces WHERE StateProvinceID=?",
               "salesperson": "SELECT FullName FROM Application_People WHERE PersonID=? AND IsSalesperson",
               "order": "SELECT CAST(OrderID AS VARCHAR) FROM ol_no_incoming_v1 WHERE OrderID=? LIMIT 1",
               "purchase_order": "SELECT CAST(PurchaseOrderID AS VARCHAR) FROM Purchasing_PurchaseOrders WHERE PurchaseOrderID=?",
               }.get(etype)
        if etype == "sales_territory":
            return eid if eid in TERRITORIES else None
        if sql is None:
            raise ValueError(etype)
        r = self.q(sql, [eid])
        return r[0][0] if r else None

    def exists(self, etype, eid) -> bool:
        return self.name(etype, eid) is not None

    def _catalog(self):
        if hasattr(self, "_cat"):
            return self._cat
        cat = []
        for t, sql in [("customer", "SELECT CustomerID, CustomerName FROM Sales_Customers"),
                       ("stock_item", "SELECT StockItemID, StockItemName FROM Warehouse_StockItems"),
                       ("supplier", "SELECT SupplierID, SupplierName FROM Purchasing_Suppliers"),
                       ("customer_category", "SELECT CustomerCategoryID, CustomerCategoryName FROM Sales_CustomerCategories"),
                       ("buying_group", "SELECT BuyingGroupID, BuyingGroupName FROM Sales_BuyingGroups"),
                       ("stock_group", "SELECT StockGroupID, StockGroupName FROM Warehouse_StockGroups"),
                       ("state_province", "SELECT StateProvinceID, StateProvinceName FROM Application_StateProvinces"),
                       ("salesperson", "SELECT PersonID, FullName FROM Application_People WHERE IsSalesperson")]:
            for i, n in self.q(sql):
                aliases = []
                if t == "supplier":
                    aliases.append(re.sub(r",? *(Inc\.|Ltd\.|Corporation)$", "", n))
                if t == "state_province":
                    code = self.q("SELECT StateProvinceCode FROM Application_StateProvinces WHERE StateProvinceID=?", [i])[0][0]
                    aliases.append(code)
                cat.append((t, i, n, [x for x in aliases if x and x != n]))
        for tname in TERRITORIES:
            cat.append(("sales_territory", tname, tname, []))
        self._cat = cat
        return cat

    def resolve(self, text: str, types=None, limit=5) -> dict:
        """Reference resolver: exact > alias > prefix > token > fuzzy (casefolded)."""
        tx = " ".join(text.casefold().split())
        rank = {"exact": 0, "alias": 1, "prefix": 2, "token": 3, "fuzzy": 4}
        toks = set(re.findall(r"[a-z0-9]+", tx))
        found = []
        for t, i, n, aliases in self._catalog():
            if types and t not in types:
                continue
            nf = n.casefold()
            ntoks = set(re.findall(r"[a-z0-9]+", nf))
            kind = None
            if nf == tx:
                kind = "exact"
            elif any(a.casefold() == tx for a in aliases):
                kind = "alias"
            elif nf.startswith(tx):
                kind = "prefix"
            elif toks and toks <= ntoks:
                kind = "token"
            elif difflib.SequenceMatcher(None, tx, nf).ratio() >= 0.88:
                kind = "fuzzy"
            if kind:
                found.append({"type": t, "id": i, "name": n, "match": kind})
        found.sort(key=lambda r: (rank[r["match"]], r["type"], str(r["id"])))
        status = "none"
        if found:
            best = rank[found[0]["match"]]
            tied = [r for r in found if rank[r["match"]] == best]
            if len(found) == 1 or (best <= 1 and len(tied) == 1):
                status = "unique"
            else:
                status = "ambiguous"
        return {"status": status, "candidate_count": len(found), "candidates": found[:limit]}

    def item_summary(self, item_id: int, scenario="base") -> dict:
        r = self.q(f"""SELECT it.StockItemID, it.StockItemName, it.SupplierID, su.SupplierName, it.QuantityPerOuter
                       FROM items_{scenario} it JOIN Purchasing_Suppliers su USING (SupplierID)
                       WHERE it.StockItemID = ?""", [item_id])
        if not r:
            return None
        _, nm, sid, sname, qpo = r[0]
        hold_sql = "SELECT QuantityOnHand, ReorderLevel, TargetStockLevel FROM Warehouse_StockItemHoldings WHERE StockItemID=?"
        if scenario == "no_incoming_v1":
            hold_sql = ("SELECT QuantityOnHand, ReorderLevel, TargetStockLevel FROM (SELECT StockItemID, QuantityOnHand, "
                        "ReorderLevel, TargetStockLevel FROM Warehouse_StockItemHoldings UNION ALL SELECT StockItemID, "
                        "QuantityOnHand, ReorderLevel, TargetStockLevel FROM syn_holdings) WHERE StockItemID=?")
        h = self.q(hold_sql, [item_id])
        unpicked = self.analyze({"measure_id": "M02", "filters": {"stock_item_id": item_id}, "scenario_id": scenario})
        unpicked_orders = self.analyze({"measure_id": "M03", "filters": {"stock_item_id": item_id}, "scenario_id": scenario})
        po = self.q("""SELECT PurchaseOrderID, PurchaseOrderLineID, POSupplierID, OrderedOuters, ReceivedOuters,
                              QuantityPerOuter, open_units, po_date, exp_date
                       FROM pl WHERE StockItemID=? ORDER BY PurchaseOrderID, PurchaseOrderLineID""", [item_id])
        return {"stock_item_id": item_id, "name": nm, "nominated_supplier_id": sid, "nominated_supplier_name": sname,
                "quantity_per_outer": qpo,
                "holdings": ({"quantity_on_hand": h[0][0], "reorder_level": h[0][1], "target_stock_level": h[0][2]}
                             if h else None),
                "unpicked_units_all_history": unpicked["total"],
                "orders_with_unpicked_all_history": unpicked_orders["total"],
                "incoming_units": sum(p[6] for p in po),
                "incoming_lines": [{"purchase_order_id": p[0], "purchase_line_id": p[1], "po_supplier_id": p[2],
                                    "ordered_outers": p[3], "received_outers": p[4], "quantity_per_outer": p[5],
                                    "remaining_units": p[6], "po_order_date": str(p[7]),
                                    "expected_delivery_date": str(p[8])} for p in po]}

    def supplier_items(self, supplier_id: int) -> list:
        return [r[0] for r in self.q("SELECT StockItemID FROM Warehouse_StockItems WHERE SupplierID=? ORDER BY 1",
                                     [supplier_id])]

    def orders(self, filters: dict, start=None, end=None, scenario="base") -> list:
        a = self._validate({"measure_id": "M01", "start": start, "end": end, "filters": filters,
                            "scenario_id": scenario})
        frm, where, params, date_col, _ = self._base(a)
        if start:
            where.append(f"{date_col} >= ? AND {date_col} < ?")
            params += [dt.date.fromisoformat(start), dt.date.fromisoformat(end)]
        wsql = ("WHERE " + " AND ".join(where)) if where else ""
        return [r[0] for r in self.q(f"SELECT DISTINCT x.OrderID FROM {frm} {wsql} ORDER BY 1", params)]

    def order_detail(self, order_id: int, scenario="base") -> dict:
        r = self.q(f"""SELECT OrderLineID, StockItemID, Quantity, PickedQuantity, d, CustomerID, SalespersonID,
                              OrderPickingCompletedWhen FROM ol_{scenario} WHERE OrderID=? ORDER BY OrderLineID""",
                   [order_id])
        if not r:
            return None
        bo = self.q("SELECT BackorderOrderID FROM Sales_Orders WHERE OrderID=?", [order_id])
        return {"order_id": order_id, "order_date": str(r[0][4]), "customer_id": r[0][5],
                "salesperson_id": r[0][6], "picking_completed": r[0][7] is not None,
                "backorder_order_id": bo[0][0] if bo else None,
                "lines": [{"order_line_id": x[0], "stock_item_id": x[1], "quantity": x[2], "picked": x[3],
                           "unpicked": max(x[2] - x[3], 0)} for x in r]}

    def customer_info(self, cid: int) -> dict:
        r = self.q("SELECT * FROM cust WHERE CustomerID=?", [cid])
        cols = [d[0] for d in self.con.description]
        return dict(zip(cols, r[0])) if r else None

    def salesperson_ids(self):
        return [r[0] for r in self.q("SELECT PersonID FROM Application_People WHERE IsSalesperson ORDER BY 1")]


def _sort(rows, sort, value_field):
    def keyval(r):
        k = r["key"]
        return (1, "") if k is None else (0, k)
    rows = sorted(rows, key=keyval)  # stable tie-break: key ascending
    if sort == "value_desc":
        rows.sort(key=lambda r: r[value_field], reverse=True)
    elif sort == "value_asc":
        rows.sort(key=lambda r: r[value_field])
    elif sort == "label_asc":
        rows.sort(key=lambda r: str(r["label"]))
    elif sort == "label_desc":
        rows.sort(key=lambda r: str(r["label"]), reverse=True)
    elif sort == "change_desc":
        rows.sort(key=lambda r: r["change"], reverse=True)
    elif sort == "change_asc":
        rows.sort(key=lambda r: r["change"])
    elif sort == "abs_change_desc":
        rows.sort(key=lambda r: abs(r["change"]), reverse=True)
    return rows


def deep_link(a: dict) -> str:
    parts = [("measure_id", a["measure_id"])]
    if a["measure_id"] in PURCHASE_MEASURES:
        parts.append(("date_basis", a["date_basis"]))
    if a.get("group_by", "none") != "none":
        parts.append(("group_by", a["group_by"]))
    for k in ("start", "end", "compare_start", "compare_end"):
        if a.get(k):
            parts.append((k, a[k]))
    if a.get("group_by", "none") != "none":
        parts.append(("sort", a["sort"]))
        parts.append(("top_n", str(a["top_n"])))
    for k, v in sorted((a.get("filters") or {}).items()):
        parts.append((k, str(v)))
    if a.get("scenario_id", "base") != "base":
        parts.append(("scenario_id", a["scenario_id"]))
    return "#/analysis?" + "&".join(f"{k}={quote(str(v), safe='-')}" for k, v in parts)


# ------------------------------------------------------------------ selftest
def selftest(o: Oracle) -> list:
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    may = {"start": "2016-05-01", "end": "2016-06-01"}
    apr = {"start": "2016-04-01", "end": "2016-05-01"}
    check("M01 May 2016 = 2047", o.analyze({"measure_id": "M01", **may})["total"] == 2047)
    check("M02 May 2016 = 17710", o.analyze({"measure_id": "M02", **may})["total"] == 17710)
    check("M03 May 2016 = 161", o.analyze({"measure_id": "M03", **may})["total"] == 161)
    check("M01 April 2016 = 1951", o.analyze({"measure_id": "M01", **apr})["total"] == 1951)
    check("M02 all history = 360276", o.analyze({"measure_id": "M02"})["total"] == 360276)
    check("M03 all history = 3085", o.analyze({"measure_id": "M03"})["total"] == 3085)
    check("M01 all history = 73595", o.analyze({"measure_id": "M01"})["total"] == 73595)
    check("M05 item 80 = 21972",
          o.analyze({"measure_id": "M05", "filters": {"stock_item_id": 80}})["total"] == 21972)
    check("M10+tax = ExtendedPrice total 198043439.45 (all history)",
          Decimal(o.analyze({"measure_id": "M10"})["total"]) + Decimal("25782098.25") == Decimal("198043439.45"))
    check("M11 all history = 85729180.90", o.analyze({"measure_id": "M11"})["total"] == "85729180.90")
    # fixture
    s = o.item_summary(1227, "no_incoming_v1")
    check("fixture item 1227: unpicked 120, holdings 20, incoming 0",
          s["unpicked_units_all_history"] == 120 and s["holdings"]["quantity_on_hand"] == 20
          and s["incoming_units"] == 0 and not s["incoming_lines"])
    check("fixture absent from base", o.item_summary(1227, "base") is None)
    check("fixture scenario holds only fixture records (v1 scope): M02 = 120",
          o.analyze({"measure_id": "M02", "scenario_id": "no_incoming_v1"})["total"] == 120)
    # additive breakdowns sum to total (with All others row)
    combos = [("M01", "sales_territory", may), ("M01", "customer_category", may), ("M01", "buying_group", {}),
              ("M01", "salesperson", may), ("M01", "customer", may), ("M02", "stock_item", may),
              ("M02", "supplier", {}), ("M03", "state_province", may), ("M13", "month", {}),
              ("M10", "sales_territory", may), ("M11", "customer_category", may), ("M10", "stock_item", may),
              ("M05", "stock_item", {}), ("M05", "supplier", {})]
    for m, g, per in combos:
        for tn in (3, 50):
            r = o.analyze({"measure_id": m, "group_by": g, "top_n": tn, **per})
            if m in MONEY:
                ssum = sum(Decimal(x["value"]) for x in r["rows"])
                ok = ssum == Decimal(r["total"])
                shares = sum(x["share"] for x in r["rows"])
            else:
                ssum = sum(x["value"] for x in r["rows"])
                ok = ssum == r["total"]
                shares = sum(x["share"] for x in r["rows"])
            check(f"additive {m} by {g} top_n={tn} rows sum to total", ok and abs(shares - 1) < 1e-4,
                  f"{ssum} vs {r['total']}")
    # compare: row changes sum to total change
    for m, g in [("M01", "sales_territory"), ("M01", "salesperson"), ("M01", "customer_category"),
                 ("M02", "stock_item"), ("M10", "sales_territory"), ("M11", "month"), ("M01", "customer")]:
        for tn in (3, 50):
            r = o.analyze({"measure_id": m, "group_by": g, "top_n": tn, **may,
                           "compare_start": apr["start"], "compare_end": apr["end"]})
            if m in MONEY:
                ok = sum(Decimal(x["change"]) for x in r["rows"]) == Decimal(r["change"])
            else:
                ok = sum(x["change"] for x in r["rows"]) == r["change"]
            sc = [x["share_of_change"] for x in r["rows"]]
            ok2 = all(v is None for v in sc) if r["change"] in (0, "0.00") else abs(sum(sc) - 1) < 1e-4
            check(f"compare {m} by {g} top_n={tn} changes sum to total change", ok and ok2)
    r = o.analyze({"measure_id": "M01", **may, "compare_start": apr["start"], "compare_end": apr["end"]})
    check("compare M01 May vs April change = +96", r["change"] == 96 and r["pct_change"] == 4.92)
    # overlapping
    r = o.analyze({"measure_id": "M01", "group_by": "stock_group", **may, "top_n": 50})
    check("overlapping stock_group: share null, rows over-count total",
          all(x["share"] is None for x in r["rows"]) and sum(x["value"] for x in r["rows"]) > r["total"]
          and not any(x["label"] == "All others" for x in r["rows"]))
    r = o.analyze({"measure_id": "M01", "group_by": "stock_item", **may, "top_n": 5})
    check("M01 by stock_item is overlapping (no All others, share null)",
          r["dimension"]["additive"] is False and len(r["rows"]) == 5 and r["rows"][0]["share"] is None)
    # rejections
    for bad in [{"measure_id": "M05", "group_by": "customer_category"},
                {"measure_id": "M05", "filters": {"customer_id": 1}},
                {"measure_id": "M10", "filters": {"status": "picking-complete"}},
                {"measure_id": "M01", "filters": {"purchase_order_id": 2073}},
                {"measure_id": "M01", "date_basis": "invoice_date"},
                {"measure_id": "M05", "group_by": "month"},
                {"measure_id": "M01", "start": "2016-05-01", "end": "2016-07-01"},
                {"measure_id": "M01", "filters": {"sales_territory": "Narnia"}},
                {"measure_id": "M01", "sort": "change_desc"}]:
        check(f"reject {json.dumps(bad)}", o.analyze(bad).get("completed") is False)
    # row-level Python cross-check (pyarrow + plain loops, no SQL) of key chain figures
    import pyarrow.parquet as pq

    def rows(t, cols):
        return pq.read_table(o.raw / f"{t}.parquet", columns=cols).to_pylist()
    city_state = {r["CityID"]: r["StateProvinceID"] for r in rows("Application.Cities", ["CityID", "StateProvinceID"])}
    state_terr = {r["StateProvinceID"]: r["SalesTerritory"]
                  for r in rows("Application.StateProvinces", ["StateProvinceID", "SalesTerritory"])}
    cust_terr = {r["CustomerID"]: state_terr[city_state[r["DeliveryCityID"]]]
                 for r in rows("Sales.Customers", ["CustomerID", "DeliveryCityID"])}
    gl = {"apr": 0, "may": 0}
    for r in rows("Sales.Orders", ["OrderID", "CustomerID", "OrderDate"]):
        if cust_terr[r["CustomerID"]] == "Great Lakes":
            if dt.date(2016, 4, 1) <= r["OrderDate"] < dt.date(2016, 5, 1):
                gl["apr"] += 1
            elif dt.date(2016, 5, 1) <= r["OrderDate"] < dt.date(2016, 6, 1):
                gl["may"] += 1
    sql_gl = [x for x in o.analyze({"measure_id": "M01", **may, "compare_start": apr["start"],
                                    "compare_end": apr["end"], "group_by": "sales_territory"})["rows"]
              if x["key"] == "Great Lakes"][0]
    check("python cross-check: Great Lakes M01 Apr->May matches SQL (+65)",
          (gl["apr"], gl["may"]) == (sql_gl["baseline"], sql_gl["current"]) and sql_gl["change"] == 65,
          f"{gl} vs {sql_gl}")
    inv_may = {r["InvoiceID"] for r in rows("Sales.Invoices", ["InvoiceID", "InvoiceDate"])
               if dt.date(2016, 5, 1) <= r["InvoiceDate"] < dt.date(2016, 6, 1)}
    m10 = sum((r["ExtendedPrice"] - r["TaxAmount"] for r in
               rows("Sales.InvoiceLines", ["InvoiceID", "ExtendedPrice", "TaxAmount"]) if r["InvoiceID"] in inv_may),
              Decimal(0))
    check("python cross-check: M10 May 2016 matches SQL",
          money_str(m10) == o.analyze({"measure_id": "M10", **may})["total"])
    # resolver
    check("resolve 'Litware' -> supplier 7",
          o.resolve("Litware", ["supplier"])["candidates"][0]["id"] == 7
          and o.resolve("Litware", ["supplier"])["status"] == "unique")
    hr = o.resolve("Hudson", ["salesperson"])
    check("resolve 'Hudson' salesperson ambiguous (3, 13)",
          hr["status"] == "ambiguous" and sorted(c["id"] for c in hr["candidates"]) == [3, 13])
    tr = o.resolve("Tailspin Toys", ["customer"])
    check("resolve 'Tailspin Toys' customer ambiguous (>100 stores)",
          tr["status"] == "ambiguous" and tr["candidate_count"] > 100)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--analyze", help="JSON analyze request")
    ap.add_argument("--resolve", help="text to resolve")
    ap.add_argument("--types", help="comma-separated resolve types")
    ap.add_argument("--item", type=int, help="item summary")
    ap.add_argument("--scenario", default="base")
    ap.add_argument("--root", help="package root (default: parent of scripts/)")
    args = ap.parse_args(argv)
    o = Oracle(args.root)
    if args.selftest:
        res = selftest(o)
        for name, ok, detail in res:
            print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
        nfail = sum(1 for _, ok, _ in res if not ok)
        print(f"{ORACLE_VERSION}: {len(res) - nfail}/{len(res)} checks passed")
        return 1 if nfail else 0
    if args.analyze:
        print(json.dumps(o.analyze(json.loads(args.analyze)), indent=2, default=str))
    if args.resolve:
        print(json.dumps(o.resolve(args.resolve, args.types.split(",") if args.types else None), indent=2,
                         default=str))
    if args.item:
        print(json.dumps(o.item_summary(args.item, args.scenario), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
