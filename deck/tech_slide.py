"""Technology stack slide (inserted after the system architecture)."""
from __future__ import annotations


def build(prs, h) -> int:
    h.prs = prs
    s = h.new_slide(prs, "Technology stack")
    k = h.SlideKit(s)
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "What each layer of the system is built with", size=21.0, bold=True, color=h.TEAL)
    rows = [
        ["Layer", "Technology", "Role"],
        ["Language model", "DeepSeek-R1-Distill 32B (Q4_K_M) on llama.cpp", "Reads slots, writes answers; JSON-schema output"],
        ["Agent", "Python 3, httpx, pydantic, pytest", "Slots, gates, finish gate, ledger, HTTP service"],
        ["Data and API", "Python, DuckDB, pydantic, SQLite", "WWI v2 API, 8 measures, workspace store"],
        ["ERP application", "ERPNext 15 (Frappe), MariaDB 10.6, Redis, Docker", "Real app loaded with WWI data"],
        ["In-app interface", "TypeScript (pnpm monorepo), window.__vacp, JavaScript", "Declared state and actions; assistant panel"],
        ["Testing", "Playwright (headless Chromium), independent oracle", "Browser checks; frozen tasks, held-out set"],
    ]
    h.add_table(s, 0.7, 1.9, [2.2, 4.9, 4.9], [0.42] + [0.7] * 6, rows, size=15.75, header_size=16.5)
    k.text("note", 0.7, 6.58, 12.0, 0.3, "Hosted Nemotron-3 Nano 30B (OpenRouter) is configured in the workspace build but has not been run live.",
           size=15.0, color=h.MUTED)
    return len(prs.slides) - 1
