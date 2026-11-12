"""Mechanical lint (spec §4 ⑥, layer 1). Reads the emitted .drawio and the exported
PNG — the real artifacts — and reports findings. Thresholds without a published
source are marked provisional and must be calibrated in phase 1 (spec §6.1)."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import color
from .blueprint import Blueprint, name_shown, plain_text
from .drawio import Cell, parse_cells
from .geometry import Box, segment_crosses_interior
from .measure import SCRIPT_SCALE, measure
from .styles import Recipe

MIN_FONT_PT = 7.0  # \scriptsize of the 10pt templates (NeurIPS/ICML/ICLR/CVPR kits); heuristic, see kb/formats.json
MIN_FONT_HARD_PT = 6.0  # heuristic hard floor: below this is an error, between this and MIN_FONT_PT a warning
EXPORT_BORDER = 12
GAP_CV_MAX = 0.25  # provisional
DENSITY_RANGE = (0.15, 0.60)  # provisional
TONE_DE_MIN = 10.0  # provisional
JOG_MIN = 8.0  # provisional: inner segments shorter than this read as kinks
LABEL_SPACING = 2.0  # drawio default label spacing
CHECKS = frozenset({
    "asset-pending",
    "badge-overlaps-text",
    "bracket-coverage",
    "bracket-spans-uncovered",
    "callout-crosses-node",
    "callout-crosses-title",
    "callout-missing",
    "child-outside-parent",
    "coverage-extra",
    "coverage-missing",
    "density",
    "edge-crossings",
    "edge-diagonal",
    "edge-hugs-border",
    "edge-jog",
    "edge-kind-color-only",
    "edge-label-overlap",
    "edge-overlap",
    "edge-through-annotation",
    "edge-through-legend",
    "edge-through-node",
    "edge-through-title",
    "gap-uneven",
    "gray-confusable",
    "min-font",
    "overlap",
    "png-mismatch",
    "proposed-name-missing",
    "text-contrast",
    "text-overflow",
    "tone-confusable",
})  # every finding id this module can emit (kept in sync by tests/test_kb.py)
SCRIPT_SCALE_RENDER = SCRIPT_SCALE
PNG_SLACK_PX = 30  # drawio export bounds exceed the predicted bbox by up to ~14px (shadows, strokes, edge bounds)
EDGE_BOUNDS_PAD = 11.0  # measured 2026-11-12 (draw.io 30.3.14): export bounds extend ~11px around edge paths


@dataclass
class Finding:
    code: str
    severity: str  # error | warn | info
    ids: list[str]
    message: str
    provisional: bool = False


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def add(self, code, severity, ids, message, provisional=False):
        self.findings.append(Finding(code, severity, list(ids), message, provisional))

    def counts(self) -> dict:
        c = {"error": 0, "warn": 0, "info": 0}
        for f in self.findings:
            c[f.severity] += 1
        return c

    def to_json(self) -> str:
        return json.dumps({"ok": self.ok, "counts": self.counts(), "stats": self.stats,
                           "findings": [asdict(f) for f in self.findings]}, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        c = self.counts()
        lines = [f"# Lint report — {'PASS' if self.ok else 'FAIL'}", "",
                 f"errors: {c['error']} · warnings: {c['warn']} · info: {c['info']}", ""]
        if self.stats:
            lines += ["| stat | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in self.stats.items()] + [""]
        for sev in ("error", "warn", "info"):
            items = [f for f in self.findings if f.severity == sev]
            if items:
                lines.append(f"## {sev}")
                for f in items:
                    prov = " *(provisional threshold)*" if f.provisional else ""
                    ids = f" `{', '.join(f.ids)}`" if f.ids else ""
                    lines.append(f"- **{f.code}**{ids}: {f.message}{prov}")
                lines.append("")
        return "\n".join(lines)


def _bold(cell: Cell) -> bool:
    try:
        return int(cell.style.get("fontStyle", "0")) & 1 == 1
    except ValueError:
        return False


def _font(cell: Cell, recipe: Recipe) -> float:
    try:
        return float(cell.style.get("fontSize", recipe["typography"]["size"]))
    except ValueError:
        return float(recipe["typography"]["size"])


def _label_box(cell: Cell, recipe: Recipe) -> Box | None:
    """Where drawio draws a below-shape label (verticalLabelPosition=bottom)."""
    if cell.style.get("verticalLabelPosition") != "bottom" or not plain_text(cell.value):
        return None
    tw, th = measure(cell.value, _font(cell, recipe), _bold(cell), recipe["typography"]["family"])
    b = cell.box
    return Box(b.cx - tw / 2, b.bottom + LABEL_SPACING, tw, th)


def _polyline(cell: Cell, cells: dict[str, Cell]) -> list[tuple[float, float]]:
    pts = []
    for key, term in (("exit", cell.source), ("entry", cell.target)):
        tb = cells[term].box if term in cells and cells[term].box else None
        if tb is None:
            pts.append(None)
            continue
        if f"{key}X" in cell.style:
            from .shapes import from_constraint
            fx, fy = from_constraint(cells[term].style, float(cell.style[f"{key}X"]), float(cell.style[f"{key}Y"]))
            x = tb.x + fx * tb.w + float(cell.style.get(f"{key}Dx", 0))
            y = tb.y + fy * tb.h + float(cell.style.get(f"{key}Dy", 0))
        else:
            x, y = tb.cx, tb.cy
        pts.append((x, y))
    if pts[0] is None or pts[1] is None:
        return []
    return [pts[0]] + list(cell.points) + [pts[1]]


def _label_point(cell, poly):
    """Where drawio draws the edge label: fraction (x+1)/2 of the path length."""
    return _point_at(poly, (max(-1.0, min(1.0, cell.label_x)) + 1) / 2)


def _point_at(poly, frac):
    lens = [math.dist(a, b) for a, b in zip(poly, poly[1:])]
    half, acc = sum(lens) * frac, 0.0
    for (a, b), L in zip(zip(poly, poly[1:]), lens):
        if acc + L >= half and L > 0:
            t = (half - acc) / L
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        acc += L
    return poly[0]


def _bg_for(cell: Cell, cells: dict[str, Cell]) -> str:
    c = cell
    while c is not None:
        f = c.style.get("fillColor")
        if f and f not in ("none",) and f.startswith("#"):
            return f
        c = cells.get(c.parent) if c.parent not in (None, "0", "1") else None
    return "#ffffff"


HUG_PX = 3.0  # provisional


def _hugging(poly, e, bp, foot):
    """id of a box/frame (not an endpoint) that a segment runs alongside within HUG_PX for >10px."""
    for a, b in zip(poly, poly[1:]):
        vert = abs(a[0] - b[0]) < 0.5
        if not vert and abs(a[1] - b[1]) > 0.5:
            continue
        coord = a[0] if vert else a[1]
        lo, hi = sorted((a[1], b[1]) if vert else (a[0], b[0]))
        for el_id, fb in foot.items():
            el = bp.index[el_id]
            if el_id in (e.src, e.dst) or (el.is_group and el.frame == "none") or el is bp.root:
                continue
            sides = (fb.x, fb.right) if vert else (fb.y, fb.bottom)
            span = (fb.y, fb.bottom) if vert else (fb.x, fb.right)
            if any(abs(coord - sd) < HUG_PX for sd in sides) and min(hi, span[1]) - max(lo, span[0]) > 10:
                return el_id
    return None


def figure_bbox(cells: dict[str, Cell], recipe: Recipe) -> Box:
    """What drawio exports: top-level vertices, below-shape labels and edge polylines."""
    boxes = [c.box for c in cells.values() if c.vertex and c.box is not None and c.parent == "1"]
    for c in cells.values():
        if c.vertex and c.box is not None:
            lb = _label_box(c, recipe)
            if lb:
                boxes.append(lb)
        if c.edge and c.source and c.target:
            poly = _polyline(c, cells)
            if poly:
                xs, ys = [p[0] for p in poly], [p[1] for p in poly]
                boxes.append(Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).inflate(EDGE_BOUNDS_PAD))
    if not boxes:
        return Box(0, 0, 1, 1)
    bb = boxes[0]
    for b in boxes[1:]:
        bb = bb.union(b)
    return bb


def pt_per_px(bbox: Box, print_width_in: float) -> float:
    # drawio's --border is in OUTPUT pixels: the diagram fills (print px - 2*border) of the image width
    return (print_width_in - 2 * EXPORT_BORDER / 300.0) * 72.0 / max(1.0, bbox.w)


def _legend_hits(el, footprint: Box, legend: Box, title_h: float) -> bool:
    """A legend may sit in a frameless group's empty space; only visible things (leaves, framed groups, any title)
    count as an overlap."""
    if el.is_group and el.frame == "none":
        return bool(el.title) and Box(footprint.x, footprint.y, footprint.w, title_h).intersects(legend, eps=0.5)
    return footprint.intersects(legend, eps=0.5)


def smallest_text(cells: dict[str, Cell], recipe: Recipe, scale: float):
    """Smallest printed base text size. Sub/superscript runs are typeset at SCRIPT_SCALE of their label on purpose
    (as in the body text, where a 10 pt line carries 7 pt subscripts), so a label is judged by its base size."""
    smallest = None
    for cid, c in cells.items():
        if not plain_text(c.value):
            continue
        pt = _font(c, recipe) * scale
        if smallest is None or pt < smallest[0]:
            smallest = (pt, cid)
    return smallest


def check(drawio_path, bp: Blueprint, recipe: Recipe, png_path, print_width_in: float) -> Report:
    rep = Report()
    drawio_path = Path(drawio_path)
    xml = drawio_path.read_text(encoding="utf-8")
    cells = parse_cells(xml)
    fam = recipe["typography"]["family"]

    # ---------------- coverage
    want = {f"pf-{el.id}": el for el in bp.index.values() if not (el is bp.root and el.frame == "none")}
    want_edges = {f"pf-{e.id}": e for e in bp.edges}
    for cid, el in want.items():
        if cid not in cells:
            rep.add("coverage-missing", "error", [el.id], "blueprint element is not drawn")
    for cid, e in want_edges.items():
        if cid not in cells:
            rep.add("coverage-missing", "error", [e.id], f"edge {e.src}->{e.dst} is not drawn")
        else:
            c = cells[cid]
            if c.source != f"pf-{e.src}" or c.target != f"pf-{e.dst}":
                rep.add("coverage-missing", "error", [e.id], f"edge drawn between {c.source}->{c.target}, blueprint says {e.src}->{e.dst}")
    for cid, c in cells.items():
        if cid in ("0", "1") or cid.startswith("pfdeco-"):
            continue
        if cid not in want and cid not in want_edges:
            rep.add("coverage-extra", "error", [cid], f"cell not in the blueprint ({plain_text(c.value)!r})")

    # ---------------- names of proposed elements
    for el in bp.index.values():
        if el.role != "proposed":
            continue
        c = cells.get(f"pf-{el.id}")
        if c is None:
            continue
        if not (name_shown(c.value, el.full_name) or name_shown(c.value, el.abbrev)):
            rep.add("proposed-name-missing", "error", [el.id],
                    f"proposed element shows {plain_text(c.value)!r}, must contain {el.full_name or ''} {('/ ' + el.abbrev) if el.abbrev else ''}".strip())

    # ---------------- geometry: footprints
    foot: dict[str, Box] = {}
    for cid, el in want.items():
        c = cells.get(cid)
        if c is None or c.box is None:
            continue
        lb = _label_box(c, recipe)
        foot[el.id] = c.box.union(lb) if (lb and not el.is_group) else c.box
    for cid, c in cells.items():  # deco label cells for pending assets join their owner's footprint
        if cid.startswith("pfdeco-") and cid.endswith("-label") and c.box:
            owner = cid[len("pfdeco-"):-len("-label")]
            if owner in foot:
                foot[owner] = foot[owner].union(c.box)

    # text fit
    for cid, el in want.items():
        c = cells.get(cid)
        if c is None or c.box is None or not plain_text(c.value):
            continue
        size = _font(c, recipe)
        if el.is_group:
            tw, th = measure(c.value, size, _bold(c), fam)
            if tw > c.box.w - 4:
                rep.add("text-overflow", "error", [el.id], f"title is {tw:.0f}px wide, container {c.box.w:.0f}px")
            continue
        if c.style.get("verticalLabelPosition") == "bottom" or c.style.get("pfasset") == "pending" or c.style.get("pfop") == "1":
            continue  # below-labels, placeholders and operator glyphs (sized to their measured ring) are checked elsewhere
        tw, th = measure(c.value, size, _bold(c), fam)
        avail_w, avail_h = c.box.w, c.box.h
        if c.style.get("horizontal") == "0":  # rotated label
            avail_w, avail_h = c.box.h, c.box.w
        if c.style.get("shape") == "trapezoid":
            avail_h = c.box.h * (1 - 2 * float(c.style.get("size", 0.2)))
        if tw > avail_w - 2 * LABEL_SPACING + 0.5 or th > avail_h - 2 * LABEL_SPACING + 0.5:
            rep.add("text-overflow", "error", [el.id], f"label needs {tw:.0f}x{th:.0f}px, box is {c.box.w:.0f}x{c.box.h:.0f}px (drawio would wrap or spill)")

    # overlaps: siblings within each group, and child containment
    for g in bp.groups():
        gbox = foot.get(g.id)
        kids = [c for c in g.children if c.id in foot]
        for i, a in enumerate(kids):
            if gbox is not None and not (g is bp.root and g.frame == "none") and not gbox.contains(foot[a.id], eps=0.5):
                rep.add("child-outside-parent", "error", [a.id, g.id], "element sticks out of its container")
            for b in kids[i + 1:]:
                if foot[a.id].intersects(foot[b.id], eps=0.5):
                    rep.add("overlap", "error", [a.id, b.id], "elements overlap")
    leaves = [n for n in bp.leaves() if n.id in foot]
    for i, a in enumerate(leaves):  # cross-group leaf overlaps (e.g. hand-moved cells)
        for b in leaves[i + 1:]:
            if bp.parent[a.id] != bp.parent[b.id] and foot[a.id].intersects(foot[b.id], eps=0.5):
                rep.add("overlap", "error", [a.id, b.id], "elements overlap")
    legend = cells.get("pfdeco-legend")
    if legend is not None and legend.box is not None:
        for el_id, fb in foot.items():
            if not (bp.index[el_id] is bp.root) and _legend_hits(bp.index[el_id], fb, legend.box, recipe["spacing"]["title_h"]):
                rep.add("overlap", "error", [el_id, "legend"], "legend overlaps the figure")
        for a in bp.annotations:
            lab = cells.get(f"pfdeco-ann-{a.id}-label")
            line = cells.get(f"pfdeco-ann-{a.id}-line")
            hit = lab is not None and lab.box is not None and lab.box.intersects(legend.box, eps=0.5)
            if not hit and line is not None:
                poly = _polyline(line, cells)
                hit = any(Box(min(p[0], q[0]), min(p[1], q[1]), abs(p[0] - q[0]), abs(p[1] - q[1])).intersects(legend.box, eps=0.5)
                          for p, q in zip(poly, poly[1:]))
            if hit:
                rep.add("overlap", "error", [a.id, "legend"], f"legend overlaps the bracket '{plain_text(a.label)}'")

    # ---------------- badges must not sit on their node's label
    for cid, c in cells.items():
        if not (cid.startswith("pfdeco-") and "-badge" in cid) or c.box is None:
            continue
        owner = cells.get(c.parent)
        if owner is None or owner.box is None or not plain_text(owner.value):
            continue
        tw, th = measure(owner.value, _font(owner, recipe), _bold(owner), fam)
        tbox = Box(owner.box.cx - tw / 2, owner.box.cy - th / 2, tw, th)
        if c.box.intersects(tbox, eps=0.5):
            rep.add("badge-overlaps-text", "error", [owner.id[3:] if owner.id.startswith("pf-") else owner.id],
                    "badge icon sits on the node's label")

    # ---------------- detail callouts
    for g in bp.groups():
        if not g.detail_of:
            continue
        inside = {g.id} | {x for x in bp.index if g.id in bp.ancestors(x)}
        for k in (0, 1):
            z = cells.get(f"pfdeco-callout-{g.id}-zoom{k}")
            if z is None or z.sp is None or z.tp is None:
                rep.add("callout-missing", "error", [g.id], "detail panel has no zoom line to its source")
                continue
            for el_id, fb in foot.items():
                el = bp.index[el_id]
                if el.is_group or el_id == g.detail_of or el_id in inside:
                    continue
                if segment_crosses_interior(z.sp, z.tp, fb, eps=1.0):
                    rep.add("callout-crosses-node", "warn", [g.id, el_id], f"zoom line of '{g.id}' passes behind '{el_id}' — move the panel")
                    break
            for og in bp.groups():
                if og.id in inside or not og.title:
                    continue
                oc = cells.get(f"pf-{og.id}")
                if oc is None or oc.box is None:
                    continue
                tw, th = measure(oc.value, _font(oc, recipe), _bold(oc), fam)
                left = oc.style.get("align") == "left"
                tx = oc.box.x + float(oc.style.get("spacingLeft", 0)) if left else oc.box.cx - tw / 2
                tbox = Box(tx, oc.box.y + 4, tw, th)
                if segment_crosses_interior(z.sp, z.tp, tbox, eps=0.5):
                    rep.add("callout-crosses-title", "warn", [g.id, og.id], f"zoom line of '{g.id}' crosses the title of '{og.id}'")
                    break

    # ---------------- annotations (brackets)
    for a in bp.annotations:
        line = cells.get(f"pfdeco-ann-{a.id}-line")
        lab = cells.get(f"pfdeco-ann-{a.id}-label")
        if line is None or line.sp is None or line.tp is None:
            rep.add("bracket-coverage", "error", [a.id], "bracket is not drawn")
            continue
        x0, x1 = min(line.sp[0], line.tp[0]), max(line.sp[0], line.tp[0])
        short = [c for c in a.covers if c in foot and (foot[c].x < x0 - 1 or foot[c].right > x1 + 1)]
        if short:
            rep.add("bracket-coverage", "error", [a.id] + short, f"bracket '{plain_text(a.label)}' does not span {', '.join(short)}")
        if lab is not None and lab.box is not None:
            for el_id, fb in foot.items():
                if not bp.index[el_id].is_group and fb.intersects(lab.box, eps=0.5):
                    rep.add("overlap", "error", [a.id, el_id], "bracket label overlaps an element")
            for og in bp.groups():
                oc = cells.get(f"pf-{og.id}")
                if og.title and oc is not None and oc.box is not None:
                    tw, th = measure(oc.value, _font(oc, recipe), _bold(oc), fam)
                    tx = oc.box.x + float(oc.style.get("spacingLeft", 0)) if oc.style.get("align") == "left" else oc.box.cx - tw / 2
                    if Box(tx, oc.box.y + 4, tw, th).intersects(lab.box, eps=0.5):
                        rep.add("overlap", "error", [a.id, og.id], "bracket label overlaps a container title")
        # an uncovered node inside the span, nearer the bracket than every covered node, reads as a member
        line_y = line.points[0][1] if line.points else line.sp[1]
        covered = set()
        for c in a.covers:
            covered |= {c} | {x for x in bp.index if c in bp.ancestors(x)}
        def dist(fb):
            return (fb.y - line_y) if a.side == "top" else (line_y - fb.bottom)
        cov_d = [dist(foot[c]) for c in covered if c in foot and not bp.index[c].is_group]
        if cov_d:
            near = min(cov_d)
            for n in bp.leaves():
                if n.id in covered or n.id not in foot:
                    continue
                fb = foot[n.id]
                if x0 <= fb.cx <= x1 and dist(fb) < near - 1:
                    rep.add("bracket-spans-uncovered", "warn", [a.id, n.id],
                            f"'{n.id}' sits inside the span of bracket '{plain_text(a.label)}' (closer than its members) but is not covered")

    # ---------------- edges
    title_band = {}
    for g in bp.groups():
        c = cells.get(f"pf-{g.id}")
        if c is not None and c.box is not None and g.title:
            tw, th = measure(c.value, _font(c, recipe), _bold(c), fam)  # only the title text blocks edges, not the band
            align_left = getattr(g, "title_align", "center") == "left"
            tx = c.box.x + recipe["spacing"]["group_pad"] if align_left else c.box.cx - tw / 2
            title_band[g.id] = Box(tx - 3, c.box.y + 1, tw + 6, th + 6)
    polys = {}
    for cid, e in want_edges.items():
        c = cells.get(cid)
        if c is None:
            continue
        poly = _polyline(c, cells)
        if not poly:
            rep.add("coverage-missing", "error", [e.id], "edge terminals missing")
            continue
        polys[e.id] = poly
        if any(abs(a[0] - b[0]) > 0.5 and abs(a[1] - b[1]) > 0.5 for a, b in zip(poly, poly[1:])):
            rep.add("edge-diagonal", "warn", [e.id], "edge has a diagonal segment")
        segl = [math.dist(a, b) for a, b in zip(poly, poly[1:])]
        if len(segl) >= 3 and min(segl[1:-1]) < JOG_MIN:
            rep.add("edge-jog", "warn", [e.id], f"edge has a {min(segl[1:-1]):.1f}px jog (reads as a kink; align the ports)", True)
        hug = _hugging(poly, e, bp, foot)
        if hug:
            rep.add("edge-hugs-border", "warn", [e.id, hug], f"edge runs within {HUG_PX:.0f}px of '{hug}' — looks attached to it", True)
        ends = {e.src, e.dst}
        anc = set(bp.ancestors(e.src)) | set(bp.ancestors(e.dst))
        hit = set()
        for a, b in zip(poly, poly[1:]):
            for el_id, fb in foot.items():
                el = bp.index[el_id]
                if el_id in ends or el_id in anc or el_id in hit:
                    continue
                if el.is_group and (el.frame == "none" or any(el_id in bp.ancestors(x) for x in ends)):
                    continue
                if segment_crosses_interior(a, b, fb, eps=1.0):
                    hit.add(el_id)
                    rep.add("edge-through-node", "error", [e.id, el_id], f"edge {e.src}->{e.dst} passes through '{el_id}'")
            for gid in anc:
                tb = title_band.get(gid)
                if tb is not None and segment_crosses_interior(a, b, tb, eps=1.0) and ("title", gid) not in hit:
                    hit.add(("title", gid))
                    rep.add("edge-through-title", "error", [e.id, gid], f"edge {e.src}->{e.dst} crosses the title of '{gid}'")
        if legend is not None and legend.box is not None:
            if any(segment_crosses_interior(a, b, legend.box.inflate(2), eps=0.0) for a, b in zip(poly, poly[1:])):
                rep.add("edge-through-legend", "error", [e.id], f"edge {e.src}->{e.dst} runs through the legend")
        if c.value and plain_text(c.value):
            mx, my = _label_point(c, poly)
            tw, th = measure(c.value, _font(c, recipe), _bold(c), fam)
            lb = Box(mx - tw / 2, my - th / 2, tw, th)
            for el_id, fb in foot.items():
                el = bp.index[el_id]
                if el.is_group:
                    continue
                if lb.intersects(fb, eps=0.5):
                    rep.add("edge-label-overlap", "warn", [e.id, el_id], f"edge label overlaps '{el_id}'")
    for a in bp.annotations:
        lab = cells.get(f"pfdeco-ann-{a.id}-label")
        if lab is None or lab.box is None:
            continue
        for eid, poly in polys.items():
            if any(segment_crosses_interior(p0, p1, lab.box, eps=0.5) for p0, p1 in zip(poly, poly[1:])):
                rep.add("edge-through-annotation", "error", [eid, a.id], f"edge runs through the bracket label '{plain_text(a.label)}'")
    # crossings / collinear overlaps between different edges
    crossings = 0
    items = list(polys.items())
    eby = {e.id: e for e in bp.edges}

    def overlap_sev(ea, eb):
        a, b = eby[ea], eby[eb]
        shared = {a.src, a.dst} & {b.src, b.dst}
        return "warn" if shared else "error"  # unrelated edges drawn on top of each other read as one
    for i, (ea, pa) in enumerate(items):
        for eb, pb in items[i + 1:]:
            for a, b in zip(pa, pa[1:]):
                for c2, d in zip(pb, pb[1:]):
                    ha, hb = abs(a[1] - b[1]) < 0.5, abs(c2[1] - d[1]) < 0.5
                    if ha and hb and abs(a[1] - c2[1]) < 0.5:
                        ov = min(max(a[0], b[0]), max(c2[0], d[0])) - max(min(a[0], b[0]), min(c2[0], d[0]))
                        if ov > 1:
                            rep.add("edge-overlap", overlap_sev(ea, eb), [ea, eb], f"edges run on top of each other for {ov:.0f}px")
                    elif not ha and not hb and abs(a[0] - c2[0]) < 0.5:
                        ov = min(max(a[1], b[1]), max(c2[1], d[1])) - max(min(a[1], b[1]), min(c2[1], d[1]))
                        if ov > 1:
                            rep.add("edge-overlap", overlap_sev(ea, eb), [ea, eb], f"edges run on top of each other for {ov:.0f}px")
                    elif ha != hb:
                        h1, h2, v1, v2 = (a, b, c2, d) if ha else (c2, d, a, b)
                        if min(h1[0], h2[0]) + 0.5 < v1[0] < max(h1[0], h2[0]) - 0.5 and min(v1[1], v2[1]) + 0.5 < h1[1] < max(v1[1], v2[1]) - 0.5:
                            crossings += 1
    rep.stats["edge_crossings"] = crossings
    if crossings:
        rep.add("edge-crossings", "warn", [], f"{crossings} edge crossing(s) — the router could not avoid them; consider reordering or moving nodes")

    # ---------------- print size
    bbox = figure_bbox(cells, recipe)
    scale = pt_per_px(bbox, print_width_in)
    rep.stats["figure_px"] = f"{bbox.w:.0f}x{bbox.h:.0f}"
    rep.stats["print_width_in"] = print_width_in
    rep.stats["print_height_in"] = round(bbox.h * scale / 72.0 + 2 * EXPORT_BORDER / 300.0, 2)
    smallest = smallest_text(cells, recipe, scale)
    scripts = [_font(c, recipe) * scale * SCRIPT_SCALE for c in cells.values()
               if plain_text(c.value) and re.search(r"<su[bp]>", c.value, re.I)]
    if scripts:  # informational: sub/superscripts print at SCRIPT_SCALE of their label, as in the body text
        rep.stats["smallest_script_pt"] = round(min(scripts), 2)
    if smallest:
        rep.stats["smallest_text_pt"] = round(smallest[0], 2)
        if smallest[0] < MIN_FONT_PT:
            sev = "error" if smallest[0] < MIN_FONT_HARD_PT else "warn"
            rep.add("min-font", sev, [smallest[1]],
                    f"smallest text prints at {smallest[0]:.1f}pt at {print_width_in}in width (< {MIN_FONT_PT}pt = template \\scriptsize; "
                    f"error below {MIN_FONT_HARD_PT}pt; heuristic) — shorten labels or use fewer columns", True)

    # ---------------- spacing and density
    labelled_pairs = set()
    for e in bp.edges:
        if e.label:
            for a in [e.src] + bp.ancestors(e.src):
                for b in [e.dst] + bp.ancestors(e.dst):
                    labelled_pairs.add(frozenset((a, b)))
    for g in bp.groups():
        if g.layout.type not in ("row", "column") or len(g.children) < 3:
            continue
        kids = sorted((c for c in g.children if c.id in foot),
                      key=lambda c: foot[c.id].x if g.layout.type == "row" else foot[c.id].y)
        gaps = []
        for a, b in zip(kids, kids[1:]):
            if frozenset((a.id, b.id)) in labelled_pairs:
                continue  # widened on purpose to fit an edge label
            A, B = foot[a.id], foot[b.id]
            gaps.append(B.x - A.right if g.layout.type == "row" else B.y - A.bottom)
        if len(gaps) < 2:
            continue
        mean = sum(gaps) / len(gaps)
        if mean > 0:
            cv = math.sqrt(sum((x - mean) ** 2 for x in gaps) / len(gaps)) / mean
            if cv > GAP_CV_MAX:
                rep.add("gap-uneven", "warn", [g.id], f"gaps between children vary (CV={cv:.2f}: {', '.join('%.0f' % x for x in gaps)})", True)
    root_box = bbox
    leaf_area = sum(foot[n.id].area for n in bp.leaves() if n.id in foot)
    dens = leaf_area / root_box.area if root_box.area else 0
    rep.stats["density"] = round(dens, 3)
    if not DENSITY_RANGE[0] <= dens <= DENSITY_RANGE[1]:
        rep.add("density", "warn", [], f"leaf area / figure area = {dens:.2f}, outside {DENSITY_RANGE}", True)

    # ---------------- colour
    for cid, c in cells.items():
        if not plain_text(c.value) or "fontColor" not in c.style:
            continue
        fg = c.style["fontColor"]
        bg = c.style.get("labelBackgroundColor") if c.edge else _bg_for(c, cells)
        if not bg or bg == "none" or c.style.get("verticalLabelPosition") == "bottom":
            parent = cells.get(c.parent)
            bg = _bg_for(parent, cells) if parent is not None and parent.id not in ("0", "1") else "#ffffff"
        try:
            cr = color.contrast(fg, bg)
        except ValueError:
            continue
        if cr < 3.0:
            rep.add("text-contrast", "error", [cid], f"text {fg} on {bg}: contrast {cr:.2f} < 3")
        elif cr < 4.5:
            rep.add("text-contrast", "warn", [cid], f"text {fg} on {bg}: contrast {cr:.2f} < 4.5")
    strokes = {}
    for n in bp.leaves():
        c = cells.get(f"pf-{n.id}")
        s = c.style.get("strokeColor") if c else None
        if s and s.startswith("#") and n.visual in ("box", "tensor", "op", "tokens"):
            strokes.setdefault(s, n.id)
    sl = list(strokes.items())
    gray_pairs = []
    for i, (s1, id1) in enumerate(sl):
        for s2, id2 in sl[i + 1:]:
            if color.de2000(s1, s2) < TONE_DE_MIN:
                continue
            bad = [(k, color.de2000(color.simulate(s1, k), color.simulate(s2, k))) for k in ("protan", "deutan", "tritan")]
            bad = [(k, d) for k, d in bad if d < TONE_DE_MIN]
            if bad:
                rep.add("tone-confusable", "warn", [id1, id2],
                        f"{s1} vs {s2} become hard to tell apart for " + ", ".join(f"{k} (ΔE00={d:.1f})" for k, d in bad)
                        + "; make sure labels or shape, not colour alone, carry the distinction", True)
            if color.de2000(color.simulate(s1, "gray"), color.simulate(s2, "gray")) < TONE_DE_MIN:
                gray_pairs.append(f"{id1}/{id2}")
    if gray_pairs:
        rep.add("gray-confusable", "info", [], "in grayscale print these tone pairs look alike: " + ", ".join(gray_pairs), True)
    sigs = {}
    for e in bp.edges:
        c = cells.get(f"pf-{e.id}")
        if c is None:
            continue
        sig = (c.style.get("dashed", "0"), c.style.get("dashPattern", ""), c.style.get("startArrow", "none"), c.style.get("endArrow", ""))
        if sig in sigs and sigs[sig][0] != e.kind:
            rep.add("edge-kind-color-only", "warn", [sigs[sig][1], e.id], f"edge kinds {sigs[sig][0]} and {e.kind} differ only by colour")
        sigs.setdefault(sig, (e.kind, e.id))

    # ---------------- assets
    pend = [cid[3:] for cid, c in cells.items() if cid.startswith("pf-") and c.style.get("pfasset") == "pending"]
    if pend:
        rep.add("asset-pending", "warn", pend, "placeholder assets still need real files (ask the user / run the code)")

    # ---------------- png consistency
    if png_path is None:
        rep.add("png-mismatch", "info", [], "no PNG supplied; export consistency not checked")
    else:
        png_path = Path(png_path)
        if not png_path.is_file():
            rep.add("png-mismatch", "error", [], f"PNG not found: {png_path}")
        else:
            from PIL import Image

            if png_path.stat().st_mtime + 1 < drawio_path.stat().st_mtime:
                rep.add("png-mismatch", "error", [], "PNG is older than the .drawio (stale export)")
            with Image.open(png_path) as im:
                pw, ph = im.size
            got = (pw - 2 * EXPORT_BORDER) / max(1, ph - 2 * EXPORT_BORDER)
            # drawio's bounds run up to ~14px beyond ours (shadows, strokes); allow that per dimension, in px
            lo = bbox.w / (bbox.h + PNG_SLACK_PX)
            hi = (bbox.w + PNG_SLACK_PX) / bbox.h
            expect = min(max(got, lo), hi)
            if abs(got - expect) / expect > 0.03:
                rep.add("png-mismatch", "error", [], f"PNG aspect {got:.3f} differs from diagram {expect:.3f}")
            rep.stats["png_px"] = f"{pw}x{ph}"
    return rep
