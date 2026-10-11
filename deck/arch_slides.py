"""Architecture slides for the v5 deck. Each function draws on a SlideKit `k` (see build_v5.py).

overview  - three rows after the Beyond Browsing figure: API-based, VACP, unified (proposed)
api       - Approach 1 in detail: pipeline plus the LedgerAgent, Tool and Mingbird concepts
vacp      - Approach 2 in detail: Task / VACP / Application bands after the VACP figure
Solid = built and verified; dashed = proposed or pending."""
from __future__ import annotations

NAVY, NAVY2, TEAL, MUTED, LIGHT, HILITE, RULE = "102A43", "17324A", "006D77", "4D6270", "F1F6F6", "EAF2F1", "CDD7D9"


def node(k, name, x, y, w, h, title, sub=None, *, fill="FFFFFF", line=TEAL, dash=False, tsize=18.0, ssize=15.0,
         align="l", pad=0.14, sub_lines=1):
    """A card with a bold title and an optional muted sub line."""
    k.card(name, x, y, w, h, fill=fill, line=line, dash=dash)
    ty = y + 0.1 if sub else y + (h - tsize * 1.29 / 72) / 2
    k.text(f"{name}-t", x + pad, ty, w - 2 * pad, tsize * 1.29 / 72 + 0.02, title, size=tsize, bold=True, color=NAVY, align=align)
    if sub:
        k.text(f"{name}-s", x + pad, ty + tsize * 1.29 / 72 + 0.04, w - 2 * pad, ssize * 1.29 / 72 * sub_lines + 0.02, sub,
               size=ssize, color=MUTED, align=align)


def overview(k):
    """One layered view: user, agent core with gates, tool channels and knowledge, then the systems they touch."""
    # user strip
    node(k, "user", 0.7, 1.35, 12.0, 0.55, "User: asks in plain language; gets the answer, its figures and a link to the page", None,
         fill=LIGHT, line=RULE, tsize=17.25)
    k.arrow("u-a", 6.7, 1.9, 6.7, 2.15, both=True)
    # agent core band
    k.card("core", 0.7, 2.15, 12.0, 1.6, fill=HILITE, line=TEAL)
    k.text("core-l", 0.9, 2.28, 1.4, 0.7, ["Agent", "core"], size=18.0, bold=True, color=NAVY)
    steps = [("Understand", "LLM reads slots"), ("Resolve", "names to ids"), ("Execute", "gated calls"),
             ("Finish gate", "code checks"), ("Answer", "sources cited")]
    x = 2.4
    for i, (tt, ss) in enumerate(steps):
        node(k, f"core-s{i}", x, 2.27, 1.8, 0.92, tt, ss, tsize=17.25, pad=0.1)
        if i < len(steps) - 1:
            k.arrow(f"core-a{i}", x + 1.8, 2.73, x + 2.1, 2.73)
        x += 2.1
    k.text("gates", 2.4, 3.28, 9.9, 0.4, "Gates: schema \u00b7 grounding \u00b7 read-before-write \u00b7 loop check \u00b7 budget of 8 calls",
           size=15.75, color=NAVY2)
    # tools, knowledge, session
    k.arrow("c-api", 3.0, 3.75, 3.0, 4.0, both=True)
    k.arrow("c-know", 6.9, 3.75, 6.9, 4.0, both=True)
    k.arrow("c-vacp", 10.7, 3.75, 10.7, 4.0, both=True, dash=True)
    node(k, "api-tools", 0.7, 4.0, 4.4, 1.17, "API tools (6)", "lookup, resolve, analyze, records, related, open_page",
         ssize=15.0, sub_lines=2)
    node(k, "contract", 5.3, 4.0, 3.2, 1.17, "Contract and pages", "Measures, periods, page catalogue", ssize=15.0, sub_lines=2)
    node(k, "vacp-act", 8.7, 4.0, 4.0, 1.17, "VACP actions", "getState, execute: filters, navigate, open record",
         ssize=15.0, sub_lines=2, dash=True)
    # systems
    k.arrow("s-api", 2.9, 5.17, 2.9, 5.42, both=True)
    k.arrow("s-vacp", 10.7, 5.17, 10.7, 5.42, both=True, dash=True)
    node(k, "sys-api", 0.7, 5.42, 4.4, 0.92, "WWI v2 app API", "Read-only; data to 21 June 2016", ssize=15.0)
    node(k, "session", 5.3, 5.42, 3.2, 0.92, "Session and trace", "State kept across turns", ssize=15.0)
    node(k, "sys-erp", 8.7, 5.42, 4.0, 0.92, "ERPNext 15 Desk", "Through window.__vacp", ssize=15.0, dash=True)
    k.arrow("sess-a", 6.9, 5.42, 6.9, 5.17, both=True)
    k.text("ov-note", 0.7, 6.55, 12.0, 0.3, "Solid: built and tested. Dashed: the VACP bridge is verified on its own; joining it to the agent is pending.",
           size=15.0, color=MUTED)


def api(k):
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Typed tools, a state ledger and a code-checked finish", size=21.0, bold=True, color=TEAL)
    steps = [("Understand", "LLM reads slots"), ("Resolve", "names to ids"), ("Execute", "gated tool calls"),
             ("Finish gate", "code checks"), ("Answer", "figures traced")]
    x = 0.7
    for i, (t, s) in enumerate(steps):
        node(k, f"step{i}", x, 1.95, 2.2, 1.0, t, s, fill=HILITE if i in (2, 3) else "FFFFFF", tsize=17.25)
        if i < len(steps) - 1:
            k.arrow(f"stepa{i}", x + 2.2, 2.45, x + 2.45, 2.45)
        x += 2.45
    k.text("concepts", 0.7, 3.15, 12.0, 0.35, "Concepts the agent is built on", size=17.25, color=MUTED)
    cards = [
        ("LedgerAgent", "4,5", "State ledger: every result gets an id, every figure traces to one, read before any change."),
        ("The Tool Illusion", "6,7", "Six small typed tools, not raw tables: lookup, resolve, analyze, records, related, open_page."),
        ("Mingbird", "8", "Harness: one dispatcher, repeated-call check, step budget and explicit finish conditions."),
    ]
    x = 0.7
    for i, (t, c, body) in enumerate(cards):
        k.card(f"c{i}", x, 3.55, 3.85, 1.95, fill="FFFFFF", line=TEAL)
        k.text(f"c{i}-t", x + 0.18, 3.67, 3.5, 0.4, [[(t, 18.75, True, NAVY), (c, 15.0, True, TEAL, True)]], check=False)
        k.text(f"c{i}-b", x + 0.18, 4.15, 3.5, 1.3, body, size=15.75, color=NAVY2)
        x += 4.075
    k.rect("rule", 0.7, 5.68, 12.0, 0.016, fill=RULE)
    k.text("data", 0.7, 5.8, 5.6, 0.7, ["Data: WWI read-only API.", "Built and measured on 31 dev chains."], size=15.75, color=NAVY2)
    k.text("model", 6.7, 5.8, 6.0, 0.7, "Hosted model configured: Nemotron-3 Nano 30B on OpenRouter, not run live yet. Results used DeepSeek-R1-32B.",
           size=15.0, color=MUTED)


def vacp(k):
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Declared in-app actions where no endpoint exists", size=21.0, bold=True, color=TEAL)
    # Task band
    k.card("band-task", 0.7, 1.95, 12.0, 0.8, fill=LIGHT, line=RULE)
    k.text("task-l", 0.9, 2.08, 1.4, 0.35, "Task", size=18.75, bold=True, color=NAVY)
    k.text("task-b", 2.4, 2.1, 10.1, 0.5, "Agent loop: choose one declared action, run it, read the new state, repeat.", size=15.75, color=NAVY2)
    k.arrow("a-task", 6.65, 2.75, 6.65, 2.95, both=True)
    # VACP band
    k.card("band-vacp", 0.7, 2.95, 12.0, 2.2, fill=HILITE, line=TEAL)
    k.text("vacp-l", 0.9, 3.03, 1.4, 0.35, "VACP", size=18.75, bold=True, color=TEAL)
    k.card("transport", 2.4, 3.03, 10.1, 0.38, fill="FFFFFF", line=TEAL, dash=True, line_w=12700)
    k.text("transport-t", 2.55, 3.07, 9.8, 0.3, "Transport: getCapabilities, getState, execute (window.__vacp)", size=15.75, color=NAVY2)
    caps = [("Observation", "Read view state; query exact totals"), ("Configuration", "Set period; set and clear filters"),
            ("Interaction", "Navigate; open a record")]
    x = 0.9
    for i, (t, s) in enumerate(caps):
        node(k, f"cap{i}", x, 3.55, 3.7, 0.95, t, s, tsize=17.25)
        x += 3.95
    k.text("state", 0.9, 4.65, 11.6, 0.35, "Application state: route, period, filters and records, exactly as the user sees them.", size=15.75, color=MUTED)
    k.arrow("a-app", 6.65, 5.15, 6.65, 5.35, both=True)
    # Application band
    k.card("band-app", 0.7, 5.35, 12.0, 0.85, fill="FFFFFF", line=TEAL, dash=True)
    k.text("app-l", 0.9, 5.48, 2.2, 0.35, "Application", size=18.75, bold=True, color=NAVY)
    k.text("app-b", 3.2, 5.5, 9.3, 0.5, "ERPNext Desk: lists, filters and records, stock app, no rebuild.", size=15.75, color=NAVY2)
    k.text("vacp-note", 0.7, 6.45, 12.0, 0.3, "Our own window.__vacp prototype, 23 of 23 checks against SQL; joining it to the agent is pending.",
           size=15.0, color=MUTED)


def workflow(k):
    """Example workflow as a horizontal timeline (numbered nodes on a line, labels alternating above and below).
    Solid nodes: built and checked. Dashed nodes: need the joined runtime (proposed)."""
    k.text("subtitle", 0.7, 1.4, 12.0, 0.45, "Example: “Compare total orders in April and May 2016.”", size=21.75, bold=True, color=TEAL)
    steps = [
        ("01", "Ask", "Compare orders", False),
        ("02", "Resolve scope", "Two periods", False),
        ("03", "Get the facts", "Run comparison", False),
        ("04", "Verify", "Check figures", False),
        ("05", "Explain", "+96 orders", False),
        ("06", "Follow up", "May orders", True),
        ("07", "Open view", "Matching page", True),
        ("08", "Confirm", "Match answer", True),
    ]
    y0 = 3.85
    xs = [1.9 + i * 1.357 for i in range(len(steps))]
    split = 4  # nodes after this index are dashed
    k.rect("tl-solid", 0.9, y0, xs[split] - 0.9, 0.0, line=TEAL, line_w=28575)
    k.rect("tl-dash", xs[split], y0, 12.4 - xs[split], 0.0, line=TEAL, line_w=28575, dash=True)
    for i, (num, title, desc, pending) in enumerate(steps):
        x = xs[i]
        hi = i == 4
        halo, dot = 0.52, 0.22  # every node the same size
        k.oval(f"halo{i}", x, y0, halo, fill=HILITE, line=None)
        k.oval(f"dot{i}", x, y0, dot, fill=TEAL, line=TEAL, line_w=22225)  # every node the same colour
        w = 2.5
        above = i % 2 == 0
        tsize = 18.75 if hi else 17.25
        block_h = 0.3 + 0.34 + 0.34
        top = (y0 - 0.5 - block_h) if above else (y0 + 0.5)
        k.text(f"n{i}", x - w / 2, top, w, 0.3, num, size=15.0, bold=True, color=TEAL, align="ctr", check=False)
        k.text(f"t{i}", x - w / 2, top + 0.3, w, 0.34, title, size=tsize, bold=True, color=(TEAL if hi else NAVY), align="ctr")
        k.text(f"d{i}", x - w / 2, top + 0.66, w, 0.36, desc, size=17.25, color=NAVY2, align="ctr")
    k.card("data-strip", 0.7, 5.75, 12.0, 0.55, fill=HILITE, line=TEAL)
    k.text("data-text", 0.9, 5.84, 11.6, 0.4,
           "Verified data: April 1,951 \u00b7 May 2,047 \u00b7 96 more orders \u00b7 4.92% \u00b7 April\u2019s 1,951 read back from the ERPNext page",
           size=15.75, color=NAVY2)
    k.text("wf-note", 0.7, 6.55, 12.0, 0.3, "The line turns dashed after step 5: those steps need the joined runtime, which remains proposed.",
           size=15.0, color=MUTED)


def vacp_context(k):
    """How the in-app VACP chat keeps context across follow-ups: today, gaps found by probes, planned (not built)."""
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Follow-ups in the in-app chat", size=21.0, bold=True, color=TEAL)
    cols = [
        ("Today", "Built in the VACP chat", False, "FFFFFF",
         ["One chat thread for the whole Desk, kept across page changes",
          "Whole thread sent each turn; older results shortened",
          "Live screen state read on demand (vacp_state)",
          "Thread saved in the browser; survives a reload",
          "Current page attached to each message (our hook)"]),
        ("Gaps found", "Probes, anecdotal", False, "FFFFFF",
         ["Shortened results lose rows and the action list",
          "Re-read the action list in 6 of 11 runs",
          "Model is not told when the user edits the screen",
          "Unknown filters ignored: wrong-scope risk",
          "Simple follow-ups worked in 3 of 3 probes"]),
        ("Next", "Not built yet", True, HILITE,
         [
          "Context block and digests of older results",
          "Unknown parameters become errors",
          "Back and remove-one-filter actions",
          "Test on 28 multi-turn conversations"]),
    ]
    x = 0.7
    for i, (head, tag, dash, fill, items) in enumerate(cols):
        k.card(f"col{i}", x, 1.95, 3.8, 4.3, fill=fill, line=TEAL, dash=dash)
        k.text(f"col{i}-h", x + 0.2, 2.07, 3.4, 0.4, head, size=20.25, bold=True, color=TEAL if i != 1 else NAVY)
        k.text(f"col{i}-g", x + 0.2, 2.5, 3.4, 0.3, tag, size=15.0, color=MUTED)
        y = 3.0
        for j, it in enumerate(items):
            k.rect(f"col{i}-m{j}", x + 0.22, y + 0.09, 0.1, 0.1, fill=TEAL)
            k.text(f"col{i}-i{j}", x + 0.45, y, 3.2, 0.56, it, size=15.75, color=NAVY2)
            y += 0.66
        x += 4.1
    k.text("ctx-note", 0.7, 6.5, 12.0, 0.3, "Probes: about 38 model calls, one run each. The page hook is our own design, not a VACP feature.", size=15.0, color=MUTED)
