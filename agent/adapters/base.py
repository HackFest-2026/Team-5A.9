"""Backend interface. The agent core only talks to this; adapters translate to a concrete app API."""
from __future__ import annotations

from typing import Protocol


class BackendError(RuntimeError):
    """The backend could not be reached or returned something that is not a JSON object."""


class Backend(Protocol):
    name: str

    def contract(self) -> dict:
        """All Contract documents (measures, dimensions, glossary, graph, playbooks, views, ...)."""

    def analyze(self, req: dict) -> dict:
        """Run an analysis request. A refused request returns {'completed': False, 'error': str}."""

    def resolve(self, text: str, types: list[str] | None, limit: int = 5) -> dict:
        """Name -> candidates: {'status': unique|ambiguous|none, 'candidates': [...]}"""

    def related(self, entity_type: str, entity_id: int, scenario_id: str = "base") -> dict:
        """One-hop context for an entity."""

    def records(self, req: dict) -> dict:
        """Paged source rows."""

    def pages(self) -> list[dict]:
        """Page/component catalogue used by documentation retrieval."""

    def route_for(self, kind: str, entity_id: int | str | None = None) -> str | None:
        """Hash route of an entity detail page (e.g. '#/customer/950'), or None if it has no page."""
