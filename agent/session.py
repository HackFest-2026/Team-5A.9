"""Conversation state: carried UI state, the registry of IDs the agent may legitimately use, and the
record of calls made in the current turn."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .slots import State

FILTER_KIND = {
    "customer_id": "customer", "stock_item_id": "stock_item", "supplier_id": "supplier",
    "stock_group_id": "stock_group", "customer_category_id": "customer_category",
    "buying_group_id": "buying_group", "state_province_id": "state_province",
    "salesperson_id": "salesperson", "order_id": "order", "order_line_id": "order_line",
    "purchase_order_id": "purchase_order", "purchase_line_id": "purchase_line",
}
DIM_KIND = {
    "customer": "customer", "stock_item": "stock_item", "supplier": "supplier", "stock_group": "stock_group",
    "customer_category": "customer_category", "buying_group": "buying_group",
    "state_province": "state_province", "salesperson": "salesperson",
}
COLUMN_KIND = {
    "CustomerID": "customer", "OrderID": "order", "OrderLineID": "order_line", "StockItemID": "stock_item",
    "SupplierID": "supplier", "PurchaseOrderID": "purchase_order", "PurchaseOrderLineID": "purchase_line",
    "SalespersonPersonID": "salesperson", "StockGroupID": "stock_group", "BackorderOrderID": "order",
}


class Registry:
    """IDs that came from somewhere real: a resolve() result, a result row, or a number the user typed."""

    def __init__(self) -> None:
        self.known: dict[str, set[Any]] = {}
        self.user_ints: set[int] = set()
        self.source: dict[tuple[str, Any], str] = {}

    def add(self, kind: str, value: Any, source: str) -> None:
        if value is None:
            return
        self.known.setdefault(kind, set()).add(value)
        self.source.setdefault((kind, value), source)

    def add_user_text(self, text: str) -> None:
        for m in re.finditer(r"(?<![\d.,])\d{1,7}(?![\d.,]\d)", text):
            self.user_ints.add(int(m.group()))

    def has(self, kind: str, value: Any) -> bool:
        return value in self.known.get(kind, set()) or (isinstance(value, int) and value in self.user_ints)

    def harvest(self, obj: Any, source: str) -> None:
        """Collect IDs from a tool result by column name."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                kind = COLUMN_KIND.get(k)
                if kind and isinstance(v, int):
                    self.add(kind, v, source)
                else:
                    self.harvest(v, source)
        elif isinstance(obj, list):
            for x in obj:
                self.harvest(x, source)


@dataclass
class Call:
    """One executed tool call, kept for the finish gate, the answer and the evaluation."""
    name: str
    args: dict
    ok: bool
    data: dict
    error: str | None = None
    applied: dict | None = None
    deep_link: str | None = None
    latency: float = 0.0


@dataclass
class Session:
    state: State = field(default_factory=State)
    registry: Registry = field(default_factory=Registry)
    mentioned: list[dict] = field(default_factory=list)  # [{"text","type","id","name"}]
    last_rows: list[dict] = field(default_factory=list)   # rows of the last grouped analyze
    last_group_by: str = "none"
    last_entity: tuple[str, int] | None = None            # ("stock_item", 193) from the last related/records
    last_related: dict | None = None                      # full response of the last related() call
    pending_text: str | None = None                       # the request we asked a clarifying question about
    turns: int = 0

    def remember_entity(self, text: str, typ: str, ident: Any, name: str | None) -> None:
        self.mentioned = [m for m in self.mentioned if not (m["type"] == typ and m["id"] == ident)]
        self.mentioned.append({"text": text, "type": typ, "id": ident, "name": name})
        self.mentioned = self.mentioned[-8:]

    def mentioned_text(self) -> str:
        if not self.mentioned:
            return "none"
        return "; ".join(f"{m['name'] or m['text']} ({m['type']} {m['id']})" for m in self.mentioned)

    def last_rows_text(self, n: int = 5) -> str:
        if not self.last_rows:
            return "none"
        rows = [r for r in self.last_rows if not r.get("is_other")][:n]
        body = "; ".join(f"{i+1}. {r.get('label')} (key {r.get('key')})" for i, r in enumerate(rows))
        return f"grouped by {self.last_group_by}: {body}"


def jdump(x: Any, limit: int | None = None) -> str:
    s = json.dumps(x, ensure_ascii=False, separators=(",", ":"), default=str)
    return s if limit is None or len(s) <= limit else s[: limit - 3] + "..."
