"""JSONL trace: every LLM call, tool call, gate verdict, finish check and latency, one line per event."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, directory: Path | None, run_id: str | None = None):
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.path: Path | None = None
        self.events: list[dict] = []
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{self.run_id}.jsonl"
        self.t0 = time.time()

    def event(self, kind: str, **data: Any) -> dict:
        ev = {"t": round(time.time() - self.t0, 3), "kind": kind, **data}
        self.events.append(ev)
        if self.path is not None:
            with self.path.open("a") as f:
                f.write(json.dumps(ev, default=str, ensure_ascii=False) + "\n")
        return ev

    def count(self, kind: str) -> int:
        return sum(1 for e in self.events if e["kind"] == kind)
