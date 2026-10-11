"""Build Sapience_Hackfest_Deck_v5.pptx from the v4 deck (the v4 file is never modified).

Edits existing slides in place, adds new slides in the deck's own style, and takes every number from the
evidence files in evidence/. Run:  python deck/build_v5.py
Rules: Arial, nothing under 15 pt, honest labels (development set, single run, held-out not run)."""
from __future__ import annotations

import copy
import glob
import io
import json
import sys
from pathlib import Path

from lxml import etree
from PIL import ImageFont
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.util import Emu, Pt

sys.path.insert(0, str(Path(__file__).parent))
import arch_slides  # noqa: E402
import survey_slides  # noqa: E402
import tech_slide  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Sapience_Hackfest_Deck_v4 (1).pptx"
OUT = ROOT / "Sapience_Hackfest_Deck_v5.pptx"
EV = ROOT / "evidence"
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
EMU = 914400

NAVY, NAVY2, TEAL, MUTED, LIGHT, HILITE, RULE, MINT = "102A43", "17324A", "006D77", "4D6270", "F1F6F6", "EAF2F1", "CDD7D9", "8AE1D5"
MIN_PT = 15.0
WARN: list[str] = []

# ---------------------------------------------------------------- text measurement (Arial ~ Liberation Sans)
_FONT_DIRS = glob.glob("/usr/share/fonts/truetype/liberation*")


def _font(bold: bool, size: float) -> ImageFont.FreeTypeFont:
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    for d in _FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), int(size * 10))
    raise FileNotFoundError(name)


def lines_needed(text: str, size: float, bold: bool, width_in: float) -> int:
    f = _font(bold, size)
    limit = width_in * 72 * 10
    total = 0
    for para in text.split("\n"):
        words, cur, n = para.split(" "), "", 1
        for w in words:
            t = (cur + " " + w).strip()
            if f.getlength(t) <= limit or not cur:
                cur = t
            else:
                n += 1
                cur = w
        total += n
    return total


def check_fit(label: str, text: str, size: float, bold: bool, w_in: float, h_in: float) -> None:
    if size < MIN_PT:
        WARN.append(f"{label}: font {size} pt is under {MIN_PT}")
    n = lines_needed(text, size, bold, w_in)
    need = n * size * 1.29 / 72
    if need > h_in + 0.02:
        WARN.append(f"{label}: needs {need:.2f} in ({n} lines) but box is {h_in:.2f} in :: {text[:50]!r}")


# ---------------------------------------------------------------- xml helpers
def _sp_xml(sid: int, name: str, x: float, y: float, w: float, h: float, fill: str | None, line: str | None,
            paras_xml: str = "", line_w: int = 15240, anchor: str = "t", dash: bool = False, geom: str = "rect") -> str:
    fill_x = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    dash_x = '<a:prstDash val="dash"/>' if dash else ""
    ln_x = (f'<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill>{dash_x}</a:ln>' if line
            else '<a:ln w="0"><a:noFill/></a:ln>')
    body = ""
    if paras_xml:
        body = (f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="{anchor}"><a:noAutofit/></a:bodyPr>'
                f"<a:lstStyle/>{paras_xml}</p:txBody>")
    return (f'<p:sp xmlns:a="{NS["a"]}" xmlns:p="{NS["p"]}"><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{int(x*EMU)}" y="{int(y*EMU)}"/><a:ext cx="{int(w*EMU)}" cy="{int(h*EMU)}"/></a:xfrm>'
            f'<a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom>{fill_x}{ln_x}</p:spPr>{body}</p:sp>')


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run(text: str, size: float, bold: bool, color: str, sup: bool = False) -> str:
    base = ' baseline="30000"' if sup else ""
    return (f'<a:r><a:rPr lang="en-US" sz="{int(round(size*100))}" b="{1 if bold else 0}"{base}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/></a:rPr><a:t>{_esc(text)}</a:t></a:r>')


def _para(runs: list[tuple], align: str = "l", space_after: int = 0) -> str:
    sa = f'<a:spcAft><a:spcPts val="{space_after}"/></a:spcAft>' if space_after else ""
    rx = "".join(_run(*r) for r in runs)
    return f'<a:p><a:pPr algn="{align}"><a:lnSpc><a:spcPct val="112000"/></a:lnSpc>{sa}<a:buNone/></a:pPr>{rx}</a:p>'


class SlideKit:
    def __init__(self, slide):
        self.s = slide
        self.tree = slide.shapes._spTree

    def next_id(self) -> int:
        ids = [int(e.get("id")) for e in self.tree.iter() if e.tag.endswith("}cNvPr") and e.get("id", "").isdigit()]
        return max(ids + [1]) + 1

    def add(self, xml: str) -> None:
        self.tree.append(etree.fromstring(xml))

    def rect(self, name, x, y, w, h, fill=None, line=None, line_w=15240, dash=False):
        self.add(_sp_xml(self.next_id(), name, x, y, w, h, fill, line, "", line_w, dash=dash))

    def oval(self, name, cx, cy, d, fill=None, line=TEAL, line_w=19050):
        """A circle of diameter d centred on (cx, cy)."""
        self.add(_sp_xml(self.next_id(), name, cx - d / 2, cy - d / 2, d, d, fill, line, "", line_w, geom="ellipse"))

    def arrow(self, name, x1, y1, x2, y2, color=TEAL, dash=False, both=False, w=19050):
        """Straight connector with a triangle head at (x2, y2), and at (x1, y1) too when both=True."""
        x, y = min(x1, x2), min(y1, y2)
        flip = (' flipH="1"' if x2 < x1 else "") + (' flipV="1"' if y2 < y1 else "")
        d = '<a:prstDash val="dash"/>' if dash else ""
        head = '<a:headEnd type="triangle" w="med" len="med"/>' if both else ""
        self.add(
            f'<p:cxnSp xmlns:a="{NS["a"]}" xmlns:p="{NS["p"]}"><p:nvCxnSpPr><p:cNvPr id="{self.next_id()}" name="{name}"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
            f'<p:spPr><a:xfrm{flip}><a:off x="{int(x*EMU)}" y="{int(y*EMU)}"/><a:ext cx="{int(abs(x2-x1)*EMU)}" cy="{int(abs(y2-y1)*EMU)}"/></a:xfrm>'
            f'<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom><a:ln w="{w}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>{d}'
            f'{head}<a:tailEnd type="triangle" w="med" len="med"/></a:ln></p:spPr></p:cxnSp>')

    def card(self, name, x, y, w, h, fill="FFFFFF", line=TEAL, dash=False, line_w=19050):
        self.rect(name, x, y, w, h, fill=fill, line=line, line_w=line_w, dash=dash)

    def text(self, name, x, y, w, h, paras, size=18.0, bold=False, color=NAVY2, align="l", anchor="t", check=True, space_after=0):
        """paras: str | list of (str | list of (text, size, bold, color[, sup]) runs)."""
        if isinstance(paras, str):
            paras = [paras]
        px, plain = [], []
        for p in paras:
            if isinstance(p, str):
                runs = [(p, size, bold, color)]
            else:
                runs = p
            px.append(_para(runs, align, space_after))
            plain.append("".join(r[0] for r in runs if len(r) < 5 or not r[4]))
        self.add(_sp_xml(self.next_id(), name, x, y, w, h, None, None, "".join(px), anchor=anchor))
        if check:
            for p, pl in zip(paras, plain):
                runs = [(p, size, bold, color)] if isinstance(p, str) else p
                sz = max(r[1] for r in runs)
                bd = any(r[2] for r in runs)
                check_fit(name, pl, sz, bd, w, h if len(paras) == 1 else h)
            if len(paras) > 1:
                total = sum(lines_needed(pl, max((r[1] for r in ([(p, size, bold, color)] if isinstance(p, str) else p))), True, w)
                            * size * 1.29 / 72 for p, pl in zip(paras, plain))
                if total > h + 0.02:
                    WARN.append(f"{name}: multi-paragraph text needs ~{total:.2f} in, box is {h:.2f} in")

    def cite(self, x, y, text):
        self.text(f"citation-{text}", x, y, 0.9, 0.3, text, size=15.0, bold=True, color=TEAL, check=False)


# ---------------------------------------------------------------- deck helpers
def shape_by_name(slide, name):
    for sh in slide.shapes:
        if sh.name == name:
            return sh
    raise KeyError(name)


def set_text(slide, name, new, size=None):
    """Replace the text of an existing text shape, keeping its first run's formatting."""
    sh = shape_by_name(slide, name)
    paras = sh.text_frame.paragraphs
    first = paras[0]
    runs = first.runs
    runs[0].text = new
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    if size:
        runs[0].font.size = Pt(size)
    return sh


def move(slide, name, x=None, y=None, w=None, h=None):
    sh = shape_by_name(slide, name)
    if x is not None:
        sh.left = int(x * EMU)
    if y is not None:
        sh.top = int(y * EMU)
    if w is not None:
        sh.width = int(w * EMU)
    if h is not None:
        sh.height = int(h * EMU)
    return sh


CHROME = ["shape-103", "shape-104", "slide-5-title", "shape-105", "brand-5", "page-5"]


def rebuild_architecture(slide) -> None:
    """Clear the body of the original architecture slide and draw the three-row overview (arch_slides.overview)."""
    keep = {"shape-108", "shape-109", "slide-6-title", "shape-110", "brand-6", "page-6", "Picture 76"}
    tree = slide.shapes._spTree
    for el in list(tree):
        nm = el.find(".//{%s}cNvPr" % NS["p"])
        if el.tag.split("}")[1] in ("sp", "cxnSp", "pic", "grpSp", "graphicFrame") and (nm is None or nm.get("name") not in keep):
            tree.remove(el)
    arch_slides.overview(SlideKit(slide))


def rebuild_workflow(slide) -> None:
    """Clear the body of the original 'Example workflow' slide and draw the timeline (arch_slides.workflow)."""
    keep = {"shape-180", "shape-181", "slide-7-title", "shape-182", "brand-7", "page-7", "Picture 38"}
    tree = slide.shapes._spTree
    for el in list(tree):
        nm = el.find(".//{%s}cNvPr" % NS["p"])
        if el.tag.split("}")[1] in ("sp", "cxnSp", "pic", "grpSp", "graphicFrame") and (nm is None or nm.get("name") not in keep):
            tree.remove(el)
    arch_slides.workflow(SlideKit(slide))


def set_cell(cell, text: str) -> None:
    paras = cell.text_frame.paragraphs
    runs = paras[0].runs
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    for extra in paras[1:]:
        extra._p.getparent().remove(extra._p)


def edit_objectives(slide) -> None:
    """More professional wording for the objectives slide. The numeric targets stay as in v4."""
    set_text(slide, "text-106", "Proposed targets and acceptance criteria for the final evaluation")
    check_fit("obj subtitle", "Proposed targets and acceptance criteria for the final evaluation", 21.75, True, 12.0, 0.5)
    rows = [
        ("Reliable multi-step task completion", "Frozen, held-out tasks meet every required outcome: operation, scope, destination and values."),
        ("Faithful numerical answers", "Each reported figure matches its source value, unit, scope and stated caveat."),
        ("Context continuity and correct destination", "Follow-ups, reloads and navigation keep scope and reach the intended view."),
        ("No false completion", "Invalid, unsupported or failed requests are never reported as completed."),
    ]
    tbl = shape_by_name(slide, "Table 7").table
    for i, (obj, crit) in enumerate(rows, 1):
        set_cell(tbl.cell(i, 1), obj)
        set_cell(tbl.cell(i, 2), crit)
        check_fit(f"obj r{i}c1", obj, 17.25, False, 3.9 - 0.29, 0.8)
        check_fit(f"obj r{i}c2", crit, 17.25, False, 6.54 - 0.29, 0.8)


def new_slide(prs, title: str):
    """A blank slide with the deck's header band, rule, title, footer, brand, page number and KLE logo."""
    layout = [l for l in prs.slide_layouts if l.name == "Blank"][0]
    src = prs.slides[4]  # objectives slide carries the standard chrome
    s = prs.slides.add_slide(layout)
    for el in list(s.shapes._spTree):
        if el.tag.endswith("}sp") or el.tag.endswith("}pic"):
            s.shapes._spTree.remove(el)
    for nm in CHROME:
        s.shapes._spTree.append(copy.deepcopy(shape_by_name(src, nm)._element))
    logo = [sh for sh in src.shapes if sh.shape_type == 13][0]
    pic = s.shapes.add_picture(io.BytesIO(logo.image.blob), logo.left, logo.top, logo.width, logo.height)
    pic.name = "KLE logo"
    set_text(s, "slide-5-title", title)
    check_fit("title", title, 31.5, True, 9.0, 0.6)
    return s


def style_table(tbl_shape, col_w: list[float], row_h: list[float], rows: list[list], size=15.75, header_size=17.25,
                bold_first_col=True, aligns=None):
    """Fill a python-pptx table to look like the deck's tables (teal header, alternating light rows)."""
    tbl = tbl_shape.table
    tblPr = tbl._tbl.tblPr
    for a in ("firstRow", "bandRow"):
        if a in tblPr.attrib:
            del tblPr.attrib[a]
    for ch in list(tblPr):
        tblPr.remove(ch)
    for i, w in enumerate(col_w):
        tbl.columns[i].width = int(w * EMU)
    for i, h in enumerate(row_h):
        tbl.rows[i].height = int(h * EMU)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = int(0.146 * EMU)
            cell.margin_top, cell.margin_bottom = int(0.07 * EMU), int(0.06 * EMU)
            tf = cell.text_frame
            tf.word_wrap = True
            head = r == 0
            sz = header_size if head else size
            bold = head or (bold_first_col and c == 0)
            color = "FFFFFF" if head else NAVY2
            lines = val if isinstance(val, list) else [val]
            for k, ln in enumerate(lines):
                p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                for rr in list(p.runs):
                    rr._r.getparent().remove(rr._r)
                run = p.add_run()
                run.text = ln
                run.font.size = Pt(sz)
                run.font.bold = bold
                run.font.name = "Arial"
                run.font.color.rgb = RGBColor.from_string(color)
                p.line_spacing = 1.08
            fill = TEAL if head else (LIGHT if r % 2 == 1 else "FFFFFF")
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(fill)
            cell.vertical_anchor = 3  # middle
            cw = col_w[c] - 0.29
            for ln in lines:
                n = lines_needed(ln, sz, bold, cw)
                need = n * sz * 1.17 * 1.08 / 72 + 0.13
                if need > row_h[r] + 0.02 or n > (2 if not head else 1) + 1:
                    WARN.append(f"table cell r{r}c{c}: {n} lines need {need:.2f} in, row is {row_h[r]:.2f} :: {ln[:40]!r}")


def add_table(slide, x, y, col_w, row_h, rows, **kw):
    gf = slide.shapes.add_table(len(rows), len(col_w), int(x * EMU), int(y * EMU), int(sum(col_w) * EMU), int(sum(row_h) * EMU))
    style_table(gf, col_w, row_h, rows, **kw)
    return gf


def style_chart(chart, size=15.0):
    chart.font.size = Pt(size)
    chart.font.name = "Arial"
    chart.font.color.rgb = RGBColor.from_string(NAVY2)
    chart.has_title = False


def bar_chart(slide, x, y, w, h, cats, series: dict[str, list[float]], colors: list[str], point_colors: dict | None = None,
              fmt='0.0"%"', legend=False, vmax=None, gap=60):
    cd = CategoryChartData()
    cd.categories = cats
    for k, v in series.items():
        cd.add_series(k, v)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, int(x * EMU), int(y * EMU), int(w * EMU), int(h * EMU), cd)
    ch = gf.chart
    style_chart(ch)
    ch.has_legend = legend
    if legend:
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(15)
        from pptx.enum.chart import XL_LEGEND_POSITION
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    plot = ch.plots[0]
    plot.gap_width = gap
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(15)
    dl.font.bold = True
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, s in enumerate(plot.series):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = RGBColor.from_string(colors[i % len(colors)])
        s.invert_if_negative = False
    if point_colors:
        s0 = plot.series[0]
        for idx, col in point_colors.items():
            pt = s0.points[idx]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = RGBColor.from_string(col)
    va = ch.value_axis
    va.visible = False
    va.has_major_gridlines = False
    va.minimum_scale = 0
    if vmax:
        va.maximum_scale = vmax
    ca = ch.category_axis
    ca.reverse_order = True
    ca.tick_labels.font.size = Pt(15)
    ca.format.line.color.rgb = RGBColor.from_string(RULE)
    ca.has_major_gridlines = False
    return gf


# ---------------------------------------------------------------- evidence
def load(name):
    p = EV / name
    return json.loads(p.read_text()) if p.exists() else None


def steps_of(run):
    return [s for ch in run["chains"][0] for s in ch["steps"]]


def count(run, key):
    st = steps_of(run)
    return sum(1 for s in st if s[key]), len(st)


def kpis(run):
    c = run["summary"]["chains"]
    st = steps_of(run)
    n = len(st)
    return {
        "chains": c["n"], "chains_ok": sum(ch["success"] for ch in run["chains"][0]), "steps": n,
        "chain_pct": c["chain_success_pct"], "step_pct": c["step_pass_pct"], "step_ok": sum(s["pass"] for s in st),
        "dest_pct": c["destination_acc_pct"], "dest_ok": sum(s["dest_ok"] and s["op_ok"] for s in st),
        "state_pct": c["ui_state_acc_pct"], "state_ok": sum(s["state_ok"] for s in st),
        "ana_pct": c["analytic_acc_pct"], "ana_ok": sum(s["analytic_ok"] for s in st),
        "faith_pct": c["faithfulness_pct"], "halluc_n": sum(1 for s in st if s["halluc"]), "halluc_pct": c["hallucinated_action_rate_pct"],
        "lat": c["latency_mean_s"], "p95": c["latency_p95_s"], "steps_per_chain": c["avg_steps_per_chain"],
        "calls_per_step": c["avg_tool_calls_per_step"],
    }


def pct1(x):
    return f"{x:.1f}%"


# ---------------------------------------------------------------- main build
def build() -> Path:
    best = load("dev_chains_slots_r1.json")        # R1 extracts slots, code builds the calls
    r1emit = load("dev_chains_full_r1.json")        # R1 emits the calls
    retr = load("retrieval.json")["results"][0]
    ctl_s, ctl_l = load("ctl_slots_r1.json"), load("ctl_llm_r1.json")
    cur = ctl_s or best  # the current system, with R1-written answers (same code as the shipped agent)
    held = load("heldout_slots_r1.json")
    K = {"best": kpis(best), "r1": kpis(r1emit), "cur": kpis(cur)}
    H = kpis(held) if held else None
    prs = Presentation(str(SRC))
    S = {i + 1: s for i, s in enumerate(prs.slides)}  # original numbering

    # ---- slide 4 (proposed solution): honest status line
    set_text(S[4], "text-102", "Proposed integrated behavior. The API agent and the ERPNext bridge are built and verified separately.")
    check_fit("s4 note", "Proposed integrated behavior. The API agent and the ERPNext bridge are built and verified separately.", 15, False, 12.0, 0.3)

    # ---- slide 6 (architecture): model line and status line
    rebuild_architecture(S[6])
    edit_objectives(S[5])

    # ---- slide 7 (workflow): the same total read back from the live ERPNext page
    rebuild_workflow(S[7])

    # ---- slide 9 (why better): point to the first evidence

    # ---- slide 10 (dataset): ERPNext facts and the 24 Feb 2016 cut-off
    set_text(S[10], "text-279", "24 Feb 2016")
    set_text(S[10], "text-280", "ERPNext invoice cut-off")
    check_fit("s10 tile", "ERPNext invoice cut-off", 17.25, False, 2.9, 0.4)
    set_text(S[10], "text-297", "ERPNext 15 with WWI loaded")
    move(S[10], "text-297", x=6.4, w=3.7)
    move(S[10], "citation-298", x=10.1)
    set_text(S[10], "text-300", "73,596 orders, 64,500 invoices; 8 of 8 checks pass")
    move(S[10], "text-300", x=6.4, w=6.3)
    check_fit("s10 erp title", "ERPNext 15 with WWI loaded", 18.75, True, 3.7, 0.3)
    check_fit("s10 erp line", "73,596 orders, 64,500 invoices; 8 of 8 checks pass", 15, False, 6.3, 0.3)

    # ======================================================= NEW 1: where API-only agents fall short
    n_gap = new_slide(prs, "Where API-only agents fall short")
    k = SlideKit(n_gap)
    k.text("subtitle", 0.7, 1.45, 12.0, 0.5, "Half of the sampled tasks had no endpoint to call", size=21.75, bold=True, color=TEAL)
    k.text("cap-left", 0.7, 2.1, 5.9, 0.35, [[("API-only agent, 100 sampled WebArena tasks", 17.25, False, MUTED), ("2", 15.0, True, TEAL, True)]], check=False)
    bar_chart(n_gap, 0.55, 2.5, 6.4, 2.9, ["Correct", "No endpoint exists", "API-usage error", "Task misunderstood"],
              {"Share of tasks": [33, 50, 11, 6]}, [RULE], point_colors={1: TEAL, 0: NAVY2, 2: MUTED, 3: MUTED}, fmt='0"%"', vmax=65)
    k.text("big-50", 7.4, 2.05, 2.0, 0.85, "50%", size=48.0, bold=True, color=TEAL, check=False)
    k.text("big-50-label", 9.35, 2.1, 3.4, 0.8, "unsolvable: the needed endpoint does not exist", size=17.25, color=NAVY2)
    k.text("cap-right", 7.4, 3.2, 5.3, 0.35, [[("Success rate by agent type, WebArena", 17.25, False, MUTED), ("2", 15.0, True, TEAL, True)]], check=False)
    bar_chart(n_gap, 7.25, 3.55, 5.5, 1.85, ["Browsing only", "API only", "API + browsing"],
              {"Success": [14.8, 29.2, 38.9]}, [RULE], point_colors={0: MUTED, 1: NAVY2, 2: TEAL}, fmt='0.0"%"', vmax=52, gap=45)
    k.rect("rule", 0.7, 5.62, 12.0, 0.016, fill=RULE)
    k.text("hypothesis", 0.7, 5.8, 12.0, 0.4, "We built the API agent first, then added VACP for the half with no endpoint.", size=18.75, bold=True, color=NAVY2)
    k.text("gap-note", 0.7, 6.6, 12.0, 0.3, "Published results (refs 2, 14, 15). That VACP closes the gap is our hypothesis, not yet measured.", size=15.0, color=MUTED)

    # ======================================================= NEW 2: KPI scorecard
    b = K["cur"]
    n_kpi = new_slide(prs, "KPI results")
    k = SlideKit(n_kpi)
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Current system: 31 development chains and 15 held-out chains", size=21.0, bold=True, color=TEAL)
    h = H
    hx = (lambda f: f(h)) if h else (lambda f: "Not run")
    rows = [
        ["KPI from the brief", "Dev, 31 chains", "Held-out, 15" if h else "Held-out", "Basis"],
        ["Intent-to-destination", pct1(b['dest_pct']), hx(lambda x: pct1(x['dest_pct'])), "Right page and operation"],
        ["UI-state correctness", pct1(b['state_pct']), hx(lambda x: pct1(x['state_pct'])), "Filters, dates, sort match"],
        ["Multi-step task success", pct1(b['chain_pct']), hx(lambda x: pct1(x['chain_pct'])), f"Every step right; {b['chains_ok']} of {b['chains']} dev"],
        ["Steps and latency", f"{b['lat']:.1f} s per step", hx(lambda x: f"{x['lat']:.1f} s per step"), f"About {b['steps_per_chain']:.1f} steps per chain"],
        ["Analytical correctness", pct1(b['ana_pct']), hx(lambda x: pct1(x['ana_pct'])), "Totals and rows match oracle"],
        ["Faithfulness", f"{b['faith_pct']:.0f}%", hx(lambda x: f"{x['faith_pct']:.0f}%"), "Numbers traced to a result"],
        ["Retrieval, 293 pages", f"MRR {retr['MRR_gold']:.3f}", "Not run", f"hit@1 {pct1(retr['hit@1_gold_pct'])}, hit@5 {pct1(retr['hit@5_gold_pct'])}"],
        ["Action hallucination", pct1(b['halluc_pct']), hx(lambda x: pct1(x['halluc_pct'])), "Share of steps; target 0"],
        ["Error and recovery rate", "Pending", "Pending", "Not reported separately"],
    ]
    add_table(n_kpi, 0.7, 1.88, [3.3, 2.5, 2.4, 3.8], [0.42] + [0.46] * 9, rows, size=15.75, header_size=16.5)
    k.text("kpi-note", 0.7, 6.55, 12.0, 0.3, "One run each. Dev chains were used to tune; the held-out chains were run once and not tuned on.", size=15.0, color=MUTED)

    # ======================================================= NEW 3: what drove the result
    n_var = new_slide(prs, "What drove the result")
    k = SlideKit(n_var)
    k.text("subtitle", 0.7, 1.4, 12.0, 0.4, "Three runs on the same development chains", size=21.0, bold=True, color=TEAL)
    names = ["R1-32B emits calls", "R1-32B slots, older code", "R1-32B slots, current code"]
    ks = [K["r1"], K["best"], K["cur"]]
    bar_chart(n_var, 0.55, 1.9, 7.2, 3.0, names,
              {"Chain success": [x["chain_pct"] for x in ks], "Step pass": [x["step_pct"] for x in ks]}, [NAVY2, TEAL], legend=False, vmax=100, gap=50)
    k.rect("leg-chain", 0.95, 5.02, 0.16, 0.16, fill=NAVY2)
    k.text("leg-chain-t", 1.2, 4.95, 2.0, 0.3, "Chain success", size=15.0, color=NAVY2)
    k.rect("leg-step", 3.35, 5.02, 0.16, 0.16, fill=TEAL)
    k.text("leg-step-t", 3.6, 4.95, 2.0, 0.3, "Step pass", size=15.0, color=NAVY2)
    add_table(n_var, 7.95, 1.95, [2.1, 1.3, 1.4], [0.4, 0.68, 0.68, 0.68],
              [["Run", "Halluc.", "Latency"]] + [[["R1-32B", "emits calls"], pct1(ks[0]["halluc_pct"]), f"{ks[0]['lat']:.0f} s"],
                                                 [["R1-32B slots,", "older code"], pct1(ks[1]["halluc_pct"]), f"{ks[1]['lat']:.0f} s"],
                                                 [["R1-32B slots,", "current code"], pct1(ks[2]["halluc_pct"]), f"{ks[2]['lat']:.0f} s"]],
              size=15.75, header_size=15.75)
    if ctl_l:
        ctl_line = f"Same-code rerun, R1-32B emits the calls: {pct1(kpis(ctl_l)['chain_pct'])} of chains."
    else:
        ctl_line = "A same-code rerun of the model-emits variant is pending."
    k.rect("caveat-card", 0.7, 5.4, 12.0, 1.1, fill=HILITE, line=TEAL)
    k.text("caveat", 0.9, 5.5, 11.6, 0.95,
           ["Not a controlled comparison: the first two runs used earlier code, and prompts and guards were tuned on these chains.",
            ctl_line], size=15.75, color=NAVY2, space_after=3)
    k.text("var-note", 0.7, 6.6, 12.0, 0.3, "Development set, one run each. Row 2 latency excludes the written answer.", size=15.0, color=MUTED)

    # ======================================================= NEW 4: built and verified
    n_st = new_slide(prs, "Built and verified so far")
    k = SlideKit(n_st)
    k.rect("card-built", 0.7, 1.5, 7.5, 3.95, fill="FFFFFF", line=TEAL)
    k.text("built-h", 0.95, 1.62, 7.0, 0.4, "Verified individually", size=20.25, bold=True, color=TEAL)
    items = [
        ("API agent", "16 tests pass; live demo: +96 orders (4.92%), Great Lakes +65"),
        ("ERPNext 15 with WWI data", "73,596 orders, 64,500 invoices, 2,074 POs; 8 of 8 checks pass"),
        ("ERPNext bridge (window.__vacp)", "23 of 23 checks against SQL on the stock Desk"),
        ("Sapience workspace build", "WWI API, ERP-style UI, model transport; 65 tests pass"),
    ]
    y = 2.05
    for lead, det in items:
        k.text(f"lead-{lead[:6]}", 0.95, y, 7.0, 0.32, lead, size=17.25, bold=True, color=NAVY2)
        k.text(f"det-{lead[:6]}", 0.95, y + 0.36, 7.0, 0.32, det, size=15.0, color=MUTED)
        y += 0.85
    k.rect("card-todo", 8.5, 1.5, 4.2, 3.95, fill=HILITE, line=TEAL)
    k.text("todo-h", 8.75, 1.62, 3.8, 0.4, "Not done yet", size=20.25, bold=True, color=NAVY2)
    todo = ["Close the held-out gap", "Joined API + bridge agent", "Live hosted-model loop", "Durable session state", "Assistant panel in the app", "WebArena runs, baselines"]
    y = 2.15
    for t in todo:
        k.text(f"todo-{t[:6]}", 8.75, y, 3.8, 0.32, t, size=16.5, color=NAVY2)
        y += 0.55
    k.text("status-line", 0.7, 5.7, 12.0, 0.4, "Both channels are built and verified individually; joining them is the last step.", size=18.75, bold=True, color=NAVY2)
    k.text("status-note", 0.7, 6.18, 12.0, 0.65,
           "The bridge is our own window.__vacp, tested in headless Chromium on the Sales Order and Sales Invoice lists, not VACP's kit. ERPNext invoices stop at 24 Feb 2016.",
           size=15.0, color=MUTED)

    # ======================================================= NEW 5: references (continued)
    n_ref = new_slide(prs, "Research references (continued)")
    k = SlideKit(n_ref)
    refs = [
        ("13", ["WebArena Verified: Reliable", "Evaluation for Web Agents"], "El hattami et al.  /  NeurIPS 2025 workshop"),
        ("14", ["WALT: Web Agents that Learn Tools"], "Prabhu et al.  /  2025"),
        ("15", ["Web Agents Should Adopt the", "Plan-Then-Execute Paradigm"], "Piet et al.  /  2026"),
        ("16", ["Callability Is Not Operability:", "Controlled Interface Interventions", "for LLM Agents"], "Wang  /  2026"),
    ]
    pos = [(0.7, 1.7), (7.1, 1.7), (0.7, 3.75), (7.1, 3.75)]
    for (num, title_lines, meta), (px, py) in zip(refs, pos):
        k.text(f"ref-num-{num}", px, py, 0.6, 0.4, num, size=18.0, bold=True, color=TEAL)
        k.text(f"ref-title-{num}", px + 0.7, py, 5.1, 1.0, title_lines, size=17.25, bold=True, color=NAVY2)
        k.text(f"ref-meta-{num}", px + 0.7, py + 0.12 + 0.31 * len(title_lines), 5.1, 0.3, meta, size=15.75, color=MUTED)
        link = {"13": "https://openreview.net/forum?id=94tlGxmqkN", "14": "https://arxiv.org/abs/2510.01524",
                "15": "https://arxiv.org/abs/2605.14290", "16": "https://arxiv.org/abs/2608.23628"}[num]
        for para in shape_by_name(n_ref, f"ref-title-{num}").text_frame.paragraphs:  # same linked-title style as slide 16
            for run in para.runs:
                run.hyperlink.address = link
                run.font.underline = True
    k.text("ref-note", 0.7, 6.55, 12.0, 0.3, "Added in v5. Authors and venues checked on arXiv and OpenReview, 11 October 2026.", size=15.0, color=MUTED)

    n_api = new_slide(prs, "Approach 1: API-based agent")
    arch_slides.api(SlideKit(n_api))
    n_vacp = new_slide(prs, "Approach 2: VACP, in-app actions")
    arch_slides.vacp(SlideKit(n_vacp))
    n_ctx = new_slide(prs, "VACP: how context is kept")
    arch_slides.vacp_context(SlideKit(n_ctx))

    # ======================================================= NEW: innovations accomplished
    n_inn = new_slide(prs, "Innovations accomplished")
    k = SlideKit(n_inn)
    cur = K["cur"]
    inn = [
        ("Code builds the calls", "The model reads the request into fields; our code makes the tool calls.",
         f"{pct1(cur['step_pct'])} of dev steps fully correct"),
        ("Checks before every call", "Invented ids and invalid combinations are rejected before anything runs.",
         "16 unit tests pass"),
        ("Answers checked in code", "Every number in an answer is traced back to a tool result.",
         f"{cur['faith_pct']:.0f}% of dev answers traced"),
        ("Finds the right page", "Searches 293 pages; a page that does not exist cannot be opened.",
         f"Right page in top 5: {pct1(retr['hit@5_gold_pct'])}"),
        ("Works inside ERPNext", "A small bridge reads and sets the real page, with no rebuild.",
         "23 of 23 checks passed"),
        ("Scored against an answer key", "Each step is compared with independently computed values.",
         f"{cur['chains']} chains, {cur['steps']} steps"),
    ]
    for i, (t, body, tag) in enumerate(inn):
        x = 0.7 + (i % 2) * 6.1
        y = 1.45 + (i // 2) * 1.6
        k.card(f"inn{i}", x, y, 5.9, 1.5, fill="FFFFFF", line=TEAL)
        k.text(f"inn{i}-n", x + 0.18, y + 0.12, 0.5, 0.3, f"{i + 1:02d}", size=17.25, bold=True, color=TEAL, check=False)
        k.text(f"inn{i}-t", x + 0.75, y + 0.12, 4.95, 0.34, t, size=18.0, bold=True, color=NAVY)
        k.text(f"inn{i}-b", x + 0.75, y + 0.5, 4.95, 0.56, body, size=15.75, color=NAVY2)
        k.text(f"inn{i}-g", x + 0.75, y + 1.15, 4.95, 0.3, tag, size=15.0, bold=True, color=TEAL)
    k.text("inn-note", 0.7, 6.55, 12.0, 0.3, "Adapted from the cited research. Results: 31 dev chains and 15 held-out chains, one run each.",
           size=15.0, color=MUTED)

    import types
    helpers = types.SimpleNamespace(new_slide=new_slide, SlideKit=SlideKit, add_table=add_table, bar_chart=bar_chart,
                                    NAVY=NAVY, NAVY2=NAVY2, TEAL=TEAL, MUTED=MUTED, HILITE=HILITE, LIGHT=LIGHT)
    survey_idx = survey_slides.build(prs, helpers)
    tech_idx = tech_slide.build(prs, helpers)

    # ---------------------------------------------------------------- order and page numbers
    lst = prs.slides._sldIdLst
    ids = list(lst)  # 0..12 original, 13 gap, 14 kpi, 15 variants, 16 status, 17 refs2
    order = [0, 1, 2] + survey_idx + [13, 3, 4, 21, 5, tech_idx, 18, 19, 20, 6, 7, 8, 9, 10, 14, 15, 16, 11, 17, 12]
    for el in ids:
        lst.remove(el)
    for i in order:
        lst.append(ids[i])
    total = len(order)
    run_no = order.index(15) + 1  # slide that compares the runs
    note9 = f"Research-informed design hypotheses. No baseline comparison yet; first development-set evidence on slide {run_no}."
    set_text(S[9], "text-265", note9)
    check_fit("s9 note", note9, 15, False, 12.0, 0.3)
    for n, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.name.startswith("page-") and sh.has_text_frame:
                runs = sh.text_frame.paragraphs[0].runs
                runs[0].text = f"{n:02d} / {total}"
    prs.save(str(OUT))
    return OUT


if __name__ == "__main__":
    out = build()
    print("saved", out)
    for w in WARN:
        print("WARN", w)
    print(len(WARN), "warnings")
