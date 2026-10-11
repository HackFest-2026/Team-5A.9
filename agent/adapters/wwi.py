"""Adapter for our WWI v2 app API (POST /api/analyze, /api/resolve, /api/related, /api/records)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from .base import BackendError

DETAIL_ROUTES = {
    "customer": "#/customer/{id}",
    "order": "#/order/{id}",
    "order_line": "#/order-line/{id}",
    "stock_item": "#/item/{id}",
    "item": "#/item/{id}",
    "supplier": "#/supplier/{id}",
    "purchase_order": "#/purchase/{id}",
    "purchase": "#/purchase/{id}",
    "purchase_line": "#/purchase-line/{id}",
}


class WWIBackend:
    name = "wwi"

    def __init__(self, base_url: str, package: Path | None = None, timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        self.package = Path(package) if package else None
        self.http = httpx.Client(timeout=timeout)
        self._contract: dict | None = None

    # -- transport -----------------------------------------------------------------
    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self.http.post(self.base + path, json=body)
        except httpx.HTTPError as e:
            raise BackendError(f"cannot reach {self.base}{path}: {e}") from e
        try:
            data = r.json()
        except json.JSONDecodeError as e:
            raise BackendError(f"{path} returned non-JSON (HTTP {r.status_code})") from e
        if not isinstance(data, dict):
            raise BackendError(f"{path} returned {type(data).__name__}, expected object")
        if r.status_code >= 400 and "completed" not in data:
            data = {"completed": False, "error": data.get("error") or data.get("detail") or f"HTTP {r.status_code}"}
        if r.status_code >= 400:
            data["completed"] = False
        return data

    def _get(self, path: str) -> dict:
        try:
            r = self.http.get(self.base + path)
            return r.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            raise BackendError(f"GET {path} failed: {e}") from e

    # -- Backend interface ---------------------------------------------------------
    def contract(self) -> dict:
        if self._contract is None:
            self._contract = self._get("/api/contract")
        return self._contract

    def analyze(self, req: dict) -> dict:
        return self._post("/api/analyze", req)

    def resolve(self, text: str, types: list[str] | None, limit: int = 5) -> dict:
        body: dict = {"text": text, "limit": limit}
        if types:
            body["types"] = types
        return self._post("/api/resolve", body)

    def related(self, entity_type: str, entity_id: int, scenario_id: str = "base") -> dict:
        return self._post("/api/related", {"entity_type": entity_type, "entity_id": entity_id, "scenario_id": scenario_id})

    def records(self, req: dict) -> dict:
        return self._post("/api/records", req)

    def pages(self) -> list[dict]:
        if self.package is None:
            raise BackendError("no package path configured for the page catalogue")
        path = self.package / "catalog" / "retrieval" / "pages.json"
        return json.loads(path.read_text())["items"]

    def route_for(self, kind: str, entity_id: int | str | None = None) -> str | None:
        tpl = DETAIL_ROUTES.get(kind)
        if tpl is None or entity_id is None:
            return None
        return tpl.format(id=entity_id)
