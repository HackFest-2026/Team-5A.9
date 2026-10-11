"""Build Sapience_Hackfest_Deck_v9.pptx from Sapience_Hackfest_Deck_v5.pptx (the source file is never modified).

What changes, and why (everything else is left as it is):
  slide 8   the ERPNext bridge statistic now refers to the bridge built on VACP's kit (202 of 203 checks), not the early prototype
  slide 11  the VACP line says the same
  slide 12  "how context is kept": what VACP provides / the gaps found / what we added (was: "Next, not built yet")
  NEW 13    "What we added to VACP": a table of additions against the repository as committed
  slide 14  workflow note: the steps shown in the app are built from the agent's real events
  slide 15  context persistence: from "planned" to what the ERPNext chat keeps and how it survives a reload
  slide 21  built-and-verified list updated (operations console, workspace CRUD, context memory); not-done list updated
Rules kept: Arial, nothing under 15 pt, honest labels. Run:  python deck/build_v9.py
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_v5 as B  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Sapience_Hackfest_Deck_v5.pptx"
OUT = ROOT / "Sapience_Hackfest_Deck_v9.pptx"
EMU = B.EMU


def by_text(slide, starts: str):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip().startswith(starts):
            return sh
    raise KeyError(starts)


def retext(slide, starts: str, new: str, label: str = "") -> None:
    sh = by_text(slide, starts)
    size = sh.text_frame.paragraphs[0].runs[0].font.size.pt
    bold = bool(sh.text_frame.paragraphs[0].runs[0].font.bold)
    B.set_text(slide, sh.name, new) if sum(1 for s in slide.shapes if s.name == sh.name) == 1 else _set_run(sh, new)
    B.check_fit(label or new[:30], new, size, bold, sh.width / EMU, sh.height / EMU)


def _set_run(sh, new: str) -> None:
    paras = sh.text_frame.paragraphs
    runs = paras[0].runs
    runs[0].text = new
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)


def build() -> Path:
    prs = Presentation_(SRC)
    S = {i + 1: s for i, s in enumerate(prs.slides)}

    # ---- slide 8: the bridge statistic
    retext(S[8], "23 of 23 checks passed", "202 of 203 checks passed", "s8 stat")

    # ---- slide 11: the bridge line
    retext(S[11], "Our own window.__vacp prototype",
           "Built on VACP's kit; 202 of 203 checks against SQL. Joining it to the agent is pending.", "s11 line")

    # ---- slide 12: how context is kept
    for sh in [s for s in S[12].shapes if s.name in ("subtitle", "ctx-note") or s.name.startswith("col")]:
        sh._element.getparent().remove(sh._element)
    k = B.SlideKit(S[12])
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Follow-ups in the in-app chat", size=21.0, bold=True, color=B.TEAL)
    cols = [
        ("In VACP", "Provided by the repository", False, "FFFFFF",
         ["Chat thread saved in the browser; survives a reload",
          "Full thread sent each turn; older results cut short",
          "Live screen state on demand (vacp_state)",
          "Scoped capabilities, state deltas, undo history"]),
        ("Gaps found", "Probes, anecdotal", False, "FFFFFF",
         ["Shortened results lose rows and the action list",
          "Re-read the action list in 6 of 11 runs",
          "Model is not told when the user edits the screen",
          "Unknown filters ignored: wrong-scope risk"]),
        ("Added by us", "ERPNext chat; built and checked", False, B.HILITE,
         ["Page snapshot attached to every message",
          "Memory of the last 5 queries, with scope hash and figures",
          "Notices edits made by hand; asks before dropping filters",
          "Digests of older results; unknown parameters are errors"]),
    ]
    x = 0.7
    for i, (head, tag, dash, fill, items) in enumerate(cols):
        k.card(f"col{i}", x, 1.95, 3.8, 4.3, fill=fill, line=B.TEAL, dash=dash)
        k.text(f"col{i}-h", x + 0.2, 2.07, 3.4, 0.4, head, size=20.25, bold=True, color=B.TEAL if i != 1 else B.NAVY)
        k.text(f"col{i}-g", x + 0.2, 2.5, 3.4, 0.3, tag, size=15.0, color=B.MUTED)
        y = 2.95
        for j, it in enumerate(items):
            k.rect(f"col{i}-m{j}", x + 0.22, y + 0.09, 0.1, 0.1, fill=B.TEAL)
            k.text(f"col{i}-i{j}", x + 0.45, y, 3.2, 0.8, it, size=15.75, color=B.NAVY2)
            y += 0.82
        x += 4.1
    k.text("ctx-note", 0.7, 6.5, 12.0, 0.3, "Probes: about 38 model calls, one run each; simple follow-ups worked in 3 of 3. The 28-conversation study has not run in full.",
           size=15.0, color=B.MUTED)

    # ---- NEW: what we added to VACP
    n = B.new_slide(prs, "What we added to VACP")
    k2 = B.SlideKit(n)
    k2.text("subtitle", 0.7, 1.4, 12.0, 0.45, "Beyond the repository: context, strict queries, safe navigation", size=21.75, bold=True, color=B.TEAL)
    rows = [
        ["Addition", "What it does", "Status"],
        ["Page context hook", "Each message carries a snapshot of the page the user sees; it is never stored in the thread", "Shared chat; unit-tested"],
        ["Result digests", "An app-written summary replaces the 1,200-character cut of older results; no digest, no change", "Unit-tested"],
        ["Conversation memory", "Last 5 queries with parameters and scope hash; spots edits by hand; rebuilt from the thread after a reload", "23 live checks"],
        ["Strict queries", "Unknown parameters are errors; every result echoes the parameters used, a scope hash and its time", "53 checks against SQL"],
        ["Safe navigation", "Back, remove-one-filter, and a confirmation before dropping filters the user set by hand", "In the 23 live checks"],
        ["Bridges for real apps", "ERPNext Desk and Metasfresh WebUI, read-only; each answer is shown on the real screen and compared", "202 of 203 checks (ERPNext)"],
    ]
    B.add_table(n, 0.7, 1.95, [2.6, 6.5, 2.9], [0.42] + [0.68] * 6, rows, size=15.75, header_size=16.5)
    k2.text("note", 0.7, 6.55, 12.0, 0.3, "Against the VACP repository as committed. Gains are not yet measured: the 28-conversation study has run once.", size=15.0, color=B.MUTED)
    # move the new slide to position 13
    lst = prs.slides._sldIdLst
    ids = list(lst)
    el = ids[-1]
    lst.remove(el)
    lst.insert(12, el)

    # ---- workflow slide (now 14): the note
    wf = [s for s in prs.slides if any(sh.name == "wf-note" for sh in s.shapes)][0]
    B.set_text(wf, "wf-note", "Steps in the app come from the agent's real events and vary by question; ERPNext steps 6 to 8 need the joined runtime.")
    B.check_fit("wf-note", "Steps in the app come from the agent's real events and vary by question; ERPNext steps 6 to 8 need the joined runtime.", 15.0, False, 12.0, 0.3)

    # ---- context and state persistence (now 15)
    ps = [s for s in prs.slides if any(sh.name == "text-216" for sh in s.shapes)][0]
    for nm, txt in [("text-216", "Built in the ERPNext chat: what it keeps, and how it survives change"),
                    ("text-226", "Page read at every send"), ("text-227", "Route, filters, page, sort"), ("text-228", "Edits by hand detected"),
                    ("text-229", "What the page shows now"),
                    ("text-235", "Last 5 queries kept"), ("text-236", "Parameters used, scope hash"), ("text-237", "Ranked list, opened record"),
                    ("text-238", "What a follow-up points to"),
                    ("text-245", "Digest of older results"), ("text-246", "Reuse: same scope, 10 min"), ("text-247", "Unknown parameters refused"),
                    ("text-250", "Reload"), ("text-252", "Rebuild from thread"), ("text-254", "Re-read the page"), ("text-256", "Re-query if stale")]:
        sh = B.shape_by_name(ps, nm)
        size = sh.text_frame.paragraphs[0].runs[0].font.size.pt
        bold = bool(sh.text_frame.paragraphs[0].runs[0].font.bold)
        B.set_text(ps, nm, txt)
        B.check_fit(nm, txt, size, bold, sh.width / EMU, sh.height / EMU)

    # ---- built and verified (now 21)
    bs = [s for s in prs.slides if any(sh.name == "card-built" for sh in s.shapes)][0]
    shapes = list(bs.shapes)
    leads = [s for s in shapes if s.name.startswith("lead-")]
    dets = [s for s in shapes if s.name.startswith("det-")]
    bridge_l = next(s for s in leads if s.text_frame.text.startswith("ERPNext bridge"))
    bridge_d = dets[leads.index(bridge_l)]
    bridge_l.text_frame.paragraphs[0].runs[0].text = "ERPNext bridge (VACP kit)"
    bridge_d.text_frame.paragraphs[0].runs[0].text = "202 of 203 SQL checks; context memory: 23 live checks"
    # a fifth block for the operations console, copied from an existing one
    new_l, new_d = copy.deepcopy(bridge_l._element), copy.deepcopy(bridge_d._element)
    bridge_d._element.addnext(new_l)
    new_l.addnext(new_d)
    leads_all = [s for s in bs.shapes if s.name.startswith("lead-")]
    dets_all = [s for s in bs.shapes if s.name.startswith("det-")]
    nl = leads_all[leads.index(bridge_l) + 1]
    nd = dets_all[leads.index(bridge_l) + 1]
    nl.text_frame.paragraphs[0].runs[0].text = "Operations console with assistant"
    nd.text_frame.paragraphs[0].runs[0].text = "Real-steps trail, record workspace; 22 of 22 CRUD checks"
    pitch = 0.74
    for i, (l, d) in enumerate(zip(leads_all, dets_all)):
        l.top = int((2.05 + i * pitch) * EMU)
        d.top = int((2.05 + i * pitch + 0.36) * EMU)
        B.check_fit("built-lead", l.text_frame.text, 17.25, True, l.width / EMU, l.height / EMU)
        B.check_fit("built-det", d.text_frame.text, 15.0, False, d.width / EMU, d.height / EMU)
    B.move(bs, "card-built", h=4.3)
    B.move(bs, "card-todo", h=4.3)
    retext(bs, "Assistant panel in the app", "Run the 28-conversation study", "todo-study")
    retext(bs, "Durable session state", "Sessions that survive a restart", "todo-sessions")
    B.move(bs, "status-line", y=5.95)
    B.move(bs, "status-note", y=6.38, h=0.55)
    note = ("The bridge is built on VACP's kit and injected into the stock Desk; it is read-only. Context memory was checked on the live Desk. "
            "ERPNext invoices stop at 24 Feb 2016.")
    _set_run(by_text(bs, "The bridge is our own"), note)
    B.check_fit("status-note", note, 15.0, False, 12.0, 0.55)

    # ---- renumber footers, fix "slide N" references
    total = len(prs.slides)
    for i, s in enumerate(prs.slides, 1):
        for sh in s.shapes:
            if sh.has_text_frame and re.fullmatch(r"\d{1,2} / \d{2}", sh.text_frame.text.strip()):
                sh.text_frame.paragraphs[0].runs[0].text = f"{i:02d} / {total}"
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        m = re.search(r"slide (\d+)", r.text)
                        if m and int(m.group(1)) >= 13 and i != 13:
                            r.text = r.text.replace(m.group(0), f"slide {int(m.group(1)) + 1}")
    prs.save(str(OUT))
    return OUT


def Presentation_(path):
    from pptx import Presentation
    return Presentation(str(path))


if __name__ == "__main__":
    out = build()
    print("saved", out)
    for w in B.WARN:
        print("WARN", w)
    print(len(B.WARN), "warnings")
