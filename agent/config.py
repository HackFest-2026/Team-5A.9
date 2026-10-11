"""Endpoints, model settings and budgets. Everything can be overridden by environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = ROOT / "data" / "wwi-package-v2-2026-10-08"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Config:
    # backend
    backend: str = field(default_factory=lambda: _env("AGENT_BACKEND", "wwi"))  # "wwi" | "erpnext"
    wwi_url: str = field(default_factory=lambda: _env("WWI_URL", "http://127.0.0.1:8017"))
    wwi_package: Path = field(default_factory=lambda: Path(_env("WWI_PACKAGE", str(DEFAULT_PACKAGE))))
    # model that emits tool calls (Qwen2.5-14B on vLLM by default)
    llm_url: str = field(default_factory=lambda: _env("LLM_URL", "http://127.0.0.1:8011/v1"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen2.5-14b"))
    llm_key: str = field(default_factory=lambda: _env("LLM_KEY", "EMPTY"))
    # "tools" = native tool calling (vLLM tool parser); "json" = JSON-schema constrained output (llama.cpp / R1)
    llm_call_style: str = field(default_factory=lambda: _env("LLM_CALL_STYLE", "tools"))
    # embeddings for documentation retrieval
    embed_url: str = field(default_factory=lambda: _env("EMBED_URL", "http://127.0.0.1:8012/v1"))
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "bge-m3"))
    # behaviour
    plan_mode: str = field(default_factory=lambda: _env("AGENT_PLAN_MODE", "llm"))  # "llm" | "slots"
    gates: bool = field(default_factory=lambda: _env("AGENT_GATES", "on") != "off")
    llm_answer: bool = field(default_factory=lambda: _env("AGENT_LLM_ANSWER", "on") != "off")
    step_budget: int = 8
    max_repairs: int = 3
    temperature: float = 0.0
    llm_timeout: float = 180.0
    max_tokens: int = 1200
    trace_dir: Path = field(default_factory=lambda: Path(_env("AGENT_TRACE_DIR", str(ROOT / "traces"))))
    reference_date: str = "2016-05-31"
    data_min: str = "2013-01-01"
    data_max: str = "2016-06-21"
