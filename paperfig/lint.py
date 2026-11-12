"""Mechanical lint (spec §4 ⑥, layer 1). Reads the emitted .drawio and the exported
PNG — the real artifacts — and reports findings. Thresholds without a published
source are marked provisional and must be calibrated in phase 1 (spec §6.1)."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import color
from .blueprint import Blueprint, name_shown, plain_text
from .drawio import Cell, parse_cells
from .geometry import Box, segment_crosses_interior
from .measure import measure
from .styles import Recipe

MIN_FONT_PT = 7.0  # \scriptsize of the 10pt templates (NeurIPS/ICML/ICLR/CVPR kits); heuristic, see kb/formats.json
EXPORT_BORDER = 12
GAP_CV_MAX = 0.25  # provisional
DENSITY_RANGE = (0.15, 0.60)  # provisional
TONE_DE_MIN = 10.0  # provisional
LABEL_SPACING = 2.0  # drawio default label spacing


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
            x = tb.x + float(cell.style[f"{key}X"]) * tb.w + float(cell.style.get(f"{key}Dx", 0))
            y = tb.y + float(cell.style[f"{key}Y"]) * tb.h + float(cell.style.get(f"{key}Dy", 0))
        else:
            x, y = tb.cx, tb.cy
        pts.append((x, y))
    if pts[0] is None or pts[1] is None:
        return []
    return [pts[0]] + list(cell.points) + [pts[1]]


def _midpoint(poly):
    lens = [math.dist(a, b) for a, b in zip(poly, poly[1:])]
    half, acc = sum(lens) / 2, 0.0
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
        if c.style.get("verticalLabelPosition") == "bottom" or "ASSET NEEDED" in c.value:
            continue
        tw, th = measure(c.value, size, _bold(c), fam)
        if tw > c.box.w - 2 * LABEL_SPACING + 0.5 or th > c.box.h - 2 * LABEL_SPACING + 0.5:
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
            if fb.intersects(legend.box, eps=0.5) and not (bp.index[el_id] is bp.root):
                rep.add("overlap", "error", [el_id, "legend"], "legend overlaps the figure")

    # ---------------- edges
    title_band = {}
    for g in bp.groups():
        c = cells.get(f"pf-{g.id}")
        if c is not None and c.box is not None and g.title:
            _, th = measure(c.value, _font(c, recipe), _bold(c), fam)
            title_band[g.id] = Box(c.box.x, c.box.y, c.box.w, max(recipe["spacing"]["title_h"], th + 8))
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
        if c.value and plain_text(c.value):
            mx, my = _midpoint(poly)
            tw, th = measure(c.value, _font(c, recipe), _bold(c), fam)
            lb = Box(mx - tw / 2, my - th / 2, tw, th)
            for el_id, fb in foot.items():
                el = bp.index[el_id]
                if el.is_group:
                    continue
                if lb.intersects(fb, eps=0.5):
                    rep.add("edge-label-overlap", "warn", [e.id, el_id], f"edge label overlaps '{el_id}'")
    # crossings / collinear overlaps between different edges
    crossings = 0
    items = list(polys.items())
    for i, (ea, pa) in enumerate(items):
        for eb, pb in items[i + 1:]:
            for a, b in zip(pa, pa[1:]):
                for c2, d in zip(pb, pb[1:]):
                    ha, hb = abs(a[1] - b[1]) < 0.5, abs(c2[1] - d[1]) < 0.5
                    if ha and hb and abs(a[1] - c2[1]) < 0.5:
                        ov = min(max(a[0], b[0]), max(c2[0], d[0])) - max(min(a[0], b[0]), min(c2[0], d[0]))
                        if ov > 1:
                            rep.add("edge-overlap", "warn", [ea, eb], f"edges run on top of each other for {ov:.0f}px")
                    elif not ha and not hb and abs(a[0] - c2[0]) < 0.5:
                        ov = min(max(a[1], b[1]), max(c2[1], d[1])) - max(min(a[1], b[1]), min(c2[1], d[1]))
                        if ov > 1:
                            rep.add("edge-overlap", "warn", [ea, eb], f"edges run on top of each other for {ov:.0f}px")
                    elif ha != hb:
                        h1, h2, v1, v2 = (a, b, c2, d) if ha else (c2, d, a, b)
                        if min(h1[0], h2[0]) + 0.5 < v1[0] < max(h1[0], h2[0]) - 0.5 and min(v1[1], v2[1]) + 0.5 < h1[1] < max(v1[1], v2[1]) - 0.5:
                            crossings += 1
    rep.stats["edge_crossings"] = crossings
    if crossings:
        rep.add("edge-crossings", "info", [], f"{crossings} edge crossing(s)")

    # ---------------- print size
    vboxes = [c.box for c in cells.values() if c.vertex and c.box is not None and c.parent in ("1",)]
    for c in cells.values():
        if c.vertex and c.box is not None:
            lb = _label_box(c, recipe)
            if lb:
                vboxes.append(lb)
    bbox = vboxes[0]
    for b in vboxes[1:]:
        bbox = bbox.union(b)
    fig_w = bbox.w + 2 * EXPORT_BORDER
    pt_per_px = print_width_in * 72.0 / fig_w
    rep.stats["figure_px"] = f"{bbox.w:.0f}x{bbox.h:.0f}"
    rep.stats["print_width_in"] = print_width_in
    rep.stats["print_height_in"] = round((bbox.h + 2 * EXPORT_BORDER) * pt_per_px / 72.0, 2)
    smallest = None
    for cid, c in cells.items():
        if not plain_text(c.value):
            continue
        pt = _font(c, recipe) * pt_per_px
        if smallest is None or pt < smallest[0]:
            smallest = (pt, cid)
    if smallest:
        rep.stats["smallest_text_pt"] = round(smallest[0], 2)
        if smallest[0] < MIN_FONT_PT:
            rep.add("min-font", "error", [smallest[1]],
                    f"smallest text prints at {smallest[0]:.1f}pt at {print_width_in}in width (< {MIN_FONT_PT}pt = template \\scriptsize; heuristic)")

    # ---------------- spacing and density
    for g in bp.groups():
        if g.layout.type not in ("row", "column") or len(g.children) < 3:
            continue
        fb = [foot[c.id] for c in g.children if c.id in foot]
        if g.layout.type == "row":
            fb.sort(key=lambda b: b.x)
            gaps = [b.x - a.right for a, b in zip(fb, fb[1:])]
        else:
            fb.sort(key=lambda b: b.y)
            gaps = [b.y - a.bottom for a, b in zip(fb, fb[1:])]
        labelled = {e for e in bp.edges if e.label}
        if not gaps or labelled:
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
    for i, (s1, id1) in enumerate(sl):
        for s2, id2 in sl[i + 1:]:
            for kind in ("protan", "deutan", "tritan", "gray"):
                d = color.de2000(color.simulate(s1, kind), color.simulate(s2, kind))
                if d < TONE_DE_MIN and color.de2000(s1, s2) >= TONE_DE_MIN:
                    rep.add("tone-confusable", "warn", [id1, id2], f"{s1} vs {s2} differ by only ΔE00={d:.1f} under {kind} simulation", True)
                    break
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
    pend = [cid[3:] for cid, c in cells.items() if cid.startswith("pf-") and "ASSET NEEDED" in c.value]
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
            expect = (bbox.w + 2 * EXPORT_BORDER) / (bbox.h + 2 * EXPORT_BORDER)
            got = pw / ph
            if abs(got - expect) / expect > 0.03:
                rep.add("png-mismatch", "error", [], f"PNG aspect {got:.3f} differs from diagram {expect:.3f}")
            rep.stats["png_px"] = f"{pw}x{ph}"
    return rep
