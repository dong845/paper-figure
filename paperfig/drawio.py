"""Emit draw.io (mxGraph) XML from a solved layout and routes, and parse it back.

Design for editability: groups are real drawio containers (children move with
them), edges stay attached to their terminals (exit/entry constraints) and carry
explicit waypoints, labels are plain html with <b>/<i>/<sub>/<sup>/<br> only.
"""
from __future__ import annotations

import base64
import re
import dataclasses
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .blueprint import Blueprint
from .errors import PaperFigError
from .geometry import Box
from .layout import TOKEN_GAP, TOKEN_SIZE, Placed, is_pending_asset, placeholder_text
from .legend import BADGE_W, build as build_legend
from .markup import to_html
from .route import Route
from .shapes import OPS, to_constraint
from .styles import Recipe, colors_for, edge_style, edge_style_for_kind, group_style, node_style, to_style_string

BADGE_ICONS = {"frozen": ("snowflake", "#2563eb"), "trainable": ("flame", "#ea580c")}


def label_position(pts) -> float:
    """drawio relative label position (-1..1) that puts the label in the middle of the longest segment,
    so labels on elbow routes sit on a straight run instead of the corner."""
    lens = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    total = sum(lens)
    if total <= 0:
        return 0.0
    k = max(range(len(lens)), key=lambda i: lens[i])
    d = sum(lens[:k]) + lens[k] / 2
    return 2 * d / total - 1


def _point_at(pts, frac: float) -> tuple[float, float]:
    """The point `frac` (0..1) of the way along a polyline, by length (as draw.io places an edge label)."""
    lens = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(pts, pts[1:])]
    want, acc = sum(lens) * frac, 0.0
    for (a, b), L in zip(zip(pts, pts[1:]), lens):
        if acc + L >= want and L > 0:
            u = (want - acc) / L
            return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
        acc += L
    return pts[-1]


def _n(v: float) -> str:
    s = "%.2f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


def icon_data_uri(name: str, color: str, stroke_px: float | None = None, size_px: float | None = None) -> str:
    """A Lucide icon in `color`; with `stroke_px` and `size_px` its lines draw `stroke_px` wide at that size — the
    figure's own line weight (Lucide's 2-per-24 drew 2.3 px at 28 px, heavier than the 1.4 px boxes)."""
    from .icons import resolve  # shipped, cached, or fetched from Lucide on first use
    svg = resolve(name).read_text(encoding="utf-8").replace("currentColor", color)
    if stroke_px and size_px and size_px > 0:
        m = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)', svg)
        units = float(m.group(1)) if m else 24.0
        sw = min(3.0, max(1.0, stroke_px * units / size_px))  # keep icons legible, never hairline or blobs
        svg = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{sw:.2f}"', svg)
    return "data:image/svg+xml," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def image_data_uri(path: str, display: tuple[float, float]) -> str:
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        fmt = (im.format or "PNG").upper()
        im = ImageOps.exif_transpose(im)
        want = display[0] / display[1] if display[1] else 1.0
        have = im.width / im.height if im.height else 1.0
        if abs(have - want) / want > 0.01:  # the box was clamped: crop, never stretch (imageAspect=0 fills the box)
            if have > want:
                nw = max(1, round(im.height * want))
                x0 = (im.width - nw) // 2
                im = im.crop((x0, 0, x0 + nw, im.height))
            else:
                nh = max(1, round(im.width / want))
                y0 = (im.height - nh) // 2
                im = im.crop((0, y0, im.width, y0 + nh))
        target = max(512, int(4 * max(display)))
        if max(im.size) > target:
            im.thumbnail((target, target), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt in ("JPEG", "JPG") and im.mode in ("RGB", "L"):
            im.save(buf, "JPEG", quality=92)
            mime = "image/jpeg"
        else:
            if im.mode not in ("RGB", "RGBA", "L", "LA"):
                im = im.convert("RGBA")
            im.save(buf, "PNG", optimize=True)
            mime = "image/png"
    # drawio style values cannot contain ';' so the ';base64' marker is omitted (drawio convention)
    return f"data:{mime}," + base64.b64encode(buf.getvalue()).decode("ascii")


MATH_BOX = '<div style="display:inline-block;min-width:{w}px">'


BIG_PANEL = 0.45  # a framed panel covering this share of the figure gets a near-white fill


def math_unbreakable(value: str, style: str) -> str:
    """A label that holds TeX in a shrink-to-fit (no-wrap) container: MathJax's automatic line breaking sees almost
    no width and breaks the formula at every operator — 'x / × y / + z' under a glyph, 'h_t / ∈ R^{d×n}' on an
    arrow (Swin run). An inline block as wide as the measured label gives it room to stay on one line."""
    if not value or "\\(" not in value or "whiteSpace=wrap" in style or value.startswith(MATH_BOX[:20]):
        return value
    from .measure import drawn_size
    m = re.search(r"(?:^|;)fontSize=([\d.]+)", style)
    fam = re.search(r"(?:^|;)fontFamily=([^;]+)", style)
    # a margin, not just the measure (measure.MATH_MARGIN): text mixed with TeX rendered wider than measured and
    # MathJax still broke inside the formula ('N ×' / '2N' in a SimCSE legend note); the block sets a minimum width
    w, _ = drawn_size(value, float(m.group(1)) if m else 10.5, "fontStyle=1" in style, fam.group(1) if fam else "Helvetica")
    return MATH_BOX.format(w=f"{w:.0f}") + value + "</div>"


def fit_dash(pattern: str, length: float, periods: float = 2.5) -> str:
    """Shrink a dash pattern so at least ``periods`` repeats fit on a line of ``length`` px (draw.io draws a
    dashed line shorter than one period as solid, so short dashed edges and legend samples read as data edges)."""
    parts = [float(x) for x in str(pattern).split()]
    period = sum(parts)
    if not parts or period <= 0 or length >= periods * period:
        return pattern
    f = max(length / (periods * period), 0.15)
    return " ".join(f"{max(0.5, int(x * f * 100) / 100):g}" for x in parts)


def _col_tone(recipe, tone):
    """pair-matrix glyph: the column side's (fill, stroke) from a tone name, or None for the glyph's default."""
    if not tone:
        return None
    from .styles import _tone
    t = _tone(recipe, tone)
    return t["fill"], t["stroke"]


class _Writer:
    def __init__(self, bp: Blueprint, placed: dict[str, Placed], routes: dict[str, Route], recipe: Recipe):
        self.bp, self.p, self.routes, self.r = bp, placed, routes, recipe
        self.mxfile = ET.Element("mxfile", host="paperfig", type="device")
        diag = ET.SubElement(self.mxfile, "diagram", id="paperfig", name=bp.figure.title or "figure")
        model = ET.SubElement(diag, "mxGraphModel", grid="0", gridSize="10", guides="1", tooltips="1", connect="1",
                              arrows="1", fold="1", page="0", pageScale="1", math="0", shadow="0", background="#ffffff")
        self.root = ET.SubElement(model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")

    def vertex(self, cid, value, style, box: Box, parent_id: str, origin=(0.0, 0.0)):
        style = self._side_label(cid, style)
        value = math_unbreakable(value, style)
        c = ET.SubElement(self.root, "mxCell", id=cid, value=value, style=style, vertex="1", parent=parent_id)
        ET.SubElement(c, "mxGeometry", {"x": _n(box.x - origin[0]), "y": _n(box.y - origin[1]),
                                        "width": _n(box.w), "height": _n(box.h), "as": "geometry"})
        return c

    def _label_panel_fill(self, rt) -> str | None:
        """Fill of the innermost framed, filled panel under an edge label's centre (as drawn: a big panel is
        lightened), so its knock-out matches the panel instead of cutting a white box into it. None: the page."""
        t = rt.label_t if rt.label_t is not None else (label_position(rt.points) + 1) / 2
        x, y = _point_at(rt.points, t)
        if rt.label_off:
            x, y = x + rt.label_off[0], y + rt.label_off[1]
        best = None
        for g in self.bp.groups():
            pl = self.p.get(g.id)
            b = pl.box if pl is not None else None
            if g.frame == "none" or b is None or not (b.x <= x <= b.x + b.w and b.y <= y <= b.y + b.h):
                continue
            f = self._group_style(g).get("fillColor", "none")
            if f and f != "none" and (best is None or b.w * b.h < best[0]):
                best = (b.w * b.h, f)
        return best[1] if best else None

    def _group_style(self, g) -> dict:
        """The group's style as drawn: a tint over most of the figure encodes nothing and reads as heavy (SimCSE critic;
        GAT corpus: ink 0.95 against a reference p75 of 0.39), so a big panel keeps its coloured border and its fill
        goes near white. Every reader of a panel's fill (edge-label knock-outs) goes through here."""
        gst = group_style(self.r, g)
        pl = self.p.get(g.id)
        fig = self._figure_area()
        if (pl is not None and gst.get("fillColor", "none") not in ("none", "#ffffff") and fig
                and pl.box.w * pl.box.h >= BIG_PANEL * fig):
            from .styles import mix
            gst["fillColor"] = mix(gst["fillColor"], "#ffffff", 0.8)
        return gst

    def _figure_area(self) -> float:
        if not hasattr(self, "_fig_area"):
            boxes = [pl.box for pl in self.p.values() if pl.box is not None]
            if not boxes:
                self._fig_area = 0.0
            else:
                x0, y0 = min(b.x for b in boxes), min(b.y for b in boxes)
                x1, y1 = max(b.right for b in boxes), max(b.bottom for b in boxes)
                self._fig_area = max(0.0, (x1 - x0) * (y1 - y0))
        return self._fig_area

    def _side_label(self, cid, style: str) -> str:
        """A name the layout put beside its shape (layout label_side): draw.io draws it there, not below."""
        nid = cid[3:] if cid.startswith("pf-") else None
        pl = self.p.get(nid) if nid else None
        if pl is None or pl.label_box is None or "verticalLabelPosition=bottom" not in style:
            return style
        lb, b = pl.label_box, pl.box
        if lb.y >= b.bottom - 0.5:  # below, as drawn by default — centred on the shape unless the layout moved it
            d = lb.cx - b.cx
            if abs(d) < 0.5:
                return style
            st = parse_style(style)  # draw.io centres the name in the shape's width less the spacings
            st.update({"spacingLeft" if d > 0 else "spacingRight": _n(2 * abs(d)), "pflabeldx": _n(d)})
            return to_style_string(st)
        st = parse_style(style)
        if lb.bottom <= b.y + 0.5:  # above the shape
            st.update({"verticalLabelPosition": "top", "verticalAlign": "bottom", "spacingBottom": _n(b.y - lb.bottom),
                       "spacingTop": "0"})
            return to_style_string(st)
        right = lb.x >= b.right - 0.5
        st.update({"labelPosition": "right" if right else "left", "verticalLabelPosition": "middle",
                   "align": "left" if right else "right", "verticalAlign": "middle",
                   "spacingLeft" if right else "spacingRight": _n((lb.x - b.right) if right else (b.x - lb.right)),
                   "spacing": "0"})
        return to_style_string(st)

    def edge_cell(self, cid, value, style, parent_id, source=None, target=None, points=(), sp=None, tp=None, label_x=None,
                  label_off=None):
        value = math_unbreakable(value, style)
        attrs = {"id": cid, "value": value, "style": style, "edge": "1", "parent": parent_id}
        if source:
            attrs["source"] = source
        if target:
            attrs["target"] = target
        c = ET.SubElement(self.root, "mxCell", attrs)
        attrs_g = {"relative": "1", "as": "geometry"}
        if label_x is not None:
            attrs_g["x"] = "%.4f" % label_x  # drawio: label position along the edge, -1..1 (0 = middle)
        g = ET.SubElement(c, "mxGeometry", attrs_g)
        if sp:
            ET.SubElement(g, "mxPoint", {"x": _n(sp[0]), "y": _n(sp[1]), "as": "sourcePoint"})
        if tp:
            ET.SubElement(g, "mxPoint", {"x": _n(tp[0]), "y": _n(tp[1]), "as": "targetPoint"})
        if label_off and (abs(label_off[0]) > 1e-6 or abs(label_off[1]) > 1e-6):
            ET.SubElement(g, "mxPoint", {"x": _n(label_off[0]), "y": _n(label_off[1]), "as": "offset"})
        if points:
            arr = ET.SubElement(g, "Array", {"as": "points"})
            for x, y in points:
                ET.SubElement(arr, "mxPoint", {"x": _n(x), "y": _n(y)})
        return c

    # -------------------------------------------------------------- elements
    def element(self, el, parent_el, parent_id: str, origin):
        pl = self.p[el.id]
        cid = f"pf-{el.id}"
        if el.is_group:
            if parent_el is None and el.frame == "none":
                for c in el.children:
                    self.element(c, el, "1", (0.0, 0.0))
                return
            st = to_style_string(self._group_style(el))
            g = self._details().get(el.id)
            if g is not None:  # a container can be the source of a detail panel too
                self._halo(g, el.id, parent_id, origin)
            self.vertex(cid, to_html(el.title or ""), st, pl.box, parent_id, origin)
            for c in el.children:
                self.element(c, el, cid, (pl.box.x, pl.box.y))
            return
        self.leaf(el, parent_el, parent_id, origin)

    def _details(self):
        return {g.detail_of: g for g in self.bp.groups() if g.detail_of}

    def _halo_box(self, nid):
        return self.p[nid].box.inflate(5.0 * self.r.data.get("ink_scale", 1.0))

    def _callout_obstacles(self, g):
        from .styles import title_text_box

        inside = {g.id} | {x for x in self.bp.index if g.id in self.bp.ancestors(x)}
        boxes = []
        for el in self.bp.index.values():
            if el.id in inside or el.id == g.detail_of:
                continue
            pl = self.p[el.id]
            if el.is_group:
                t = title_text_box(self.r, el, pl)
                if t is not None:
                    boxes.append(t)
            else:
                boxes.append(pl.footprint)
        return boxes

    def _halo(self, g, src_id, parent_id, origin):
        fill, stroke, _ = colors_for(self.r, g)
        hst = {"rounded": "1", "absoluteArcSize": "1", "arcSize": _n(2 * self.r["shape"]["radius"] + 6), "fillColor": fill,
               "strokeColor": stroke, "strokeWidth": _n(self.r["shape"]["stroke_width"]), "dashed": "1", "dashPattern": "3 3"}
        self.vertex(f"pfdeco-callout-{g.id}-halo", "", to_style_string(hst), self._halo_box(src_id), parent_id, origin)

    def callouts_behind(self):
        """Zoom legs from a highlighted source node to its detail panel (drawn above containers). The wide
        cone to the panel corners is used unless it crosses a title or a node; then a steeper cone."""
        from .geometry import segment_crosses_interior

        for src, g in self._details().items():
            h, pb = self._halo_box(src), self.p[g.id].box
            fill, stroke, _ = colors_for(self.r, g)
            dx, dy = pb.cx - h.cx, pb.cy - h.cy
            vertical = abs(dy) >= abs(dx)
            if vertical:
                (ya, yb) = (h.bottom, pb.y) if dy > 0 else (h.y, pb.bottom)
                wide = [((h.x, ya), (pb.x, yb)), ((h.right, ya), (pb.right, yb))]
                d = abs(yb - ya)
                steep = [((h.x, ya), (max(pb.x, h.x - d), yb)), ((h.right, ya), (min(pb.right, h.right + d), yb))]
                straight = [((h.x, ya), (max(pb.x, min(pb.right, h.x)), yb)), ((h.right, ya), (min(pb.right, max(pb.x, h.right)), yb))]
            else:
                (xa, xb) = (h.right, pb.x) if dx > 0 else (h.x, pb.right)
                wide = [((xa, h.y), (xb, pb.y)), ((xa, h.bottom), (xb, pb.bottom))]
                d = abs(xb - xa)
                steep = [((xa, h.y), (xb, max(pb.y, h.y - d))), ((xa, h.bottom), (xb, min(pb.bottom, h.bottom + d)))]
                straight = [((xa, h.y), (xb, max(pb.y, min(pb.bottom, h.y)))), ((xa, h.bottom), (xb, min(pb.bottom, max(pb.y, h.bottom))))]
            obs = self._callout_obstacles(g)

            def hits(pairs):
                return sum(1 for a, b in pairs for o in obs if segment_crosses_interior(a, b, o, eps=0.5))

            pairs = min((wide, steep, straight), key=hits)  # first (widest) cone among the least-crossing ones
            st = {"html": "1", "edgeStyle": "none", "endArrow": "none", "startArrow": "none", "dashed": "1", "dashPattern": "3 3",
                  "strokeColor": stroke, "strokeWidth": _n(1.0 * self.r.data.get("ink_scale", 1.0)), "opacity": "70"}
            for k, (a, b) in enumerate(pairs):
                self.edge_cell(f"pfdeco-callout-{g.id}-zoom{k}", "", to_style_string(st), "1", sp=a, tp=b)
                self._deco_segments = getattr(self, "_deco_segments", []) + [(a, b)]

    def leaf(self, n, parent_el, parent_id, origin):
        pl = self.p[n.id]
        cid = f"pf-{n.id}"
        g = self._details().get(n.id)
        if g is not None:  # highlight the source node with the panel's tint, behind the node
            self._halo(g, n.id, parent_id, origin)
        if is_pending_asset(n):
            st = node_style(self.r, dataclasses.replace(n, visual="placeholder"), parent_el)
            self.vertex(cid, "" if pl.label_box is not None else to_html(placeholder_text(n)), to_style_string(st), pl.box,
                        parent_id, origin)
            if pl.label_box is not None:
                ty = self.r["typography"]
                tst = {"html": "1", "whiteSpace": "nowrap", "strokeColor": "none", "fillColor": "none", "fontFamily": ty["family"],
                       "fontSize": _n(ty["small_size"]), "fontColor": ty["color"], "align": "center", "verticalAlign": "middle"}
                self.vertex(f"pfdeco-{n.id}-label", to_html(n.label), to_style_string(tst), pl.label_box, parent_id, origin)
            self.badges(n, cid, pl)
            return
        st = node_style(self.r, n, parent_el)
        if n.visual == "image":
            st["image"] = image_data_uri(n.asset.path, (pl.box.w, pl.box.h))
        elif n.visual == "icon":
            st["image"] = icon_data_uri(n.icon, colors_for(self.r, n, parent_el)[1], self.r["shape"]["stroke_width"],
                                        min(pl.box.w, pl.box.h))
        elif n.visual == "glyph":
            from .glyphs import glyph_data_uri, glyph_svg
            fill, stroke, _ = colors_for(self.r, n, parent_el)
            pal = self.r["palette"]
            accent = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"] if n.accent else stroke
            if n.glyph == "pair-matrix":  # positives are their own code (CLIP blue), never the contribution's accent
                accent = pal["tones"].get("blue", {}).get("stroke", "#3b6fc4")
                if not n.tone and "gray" in pal["tones"]:  # the headers are the paired items, not the node's role: a
                    g = pal["tones"]["gray"]  # loss matrix with no tone drew them loss-red (CaseLIP v8 sketches)
                    fill, stroke = g["fill"], g["stroke"]
            tones = [t["stroke"] for k, t in pal["tones"].items() if isinstance(t, dict) and k not in ("gray", "grey")][:3]
            st["image"] = glyph_data_uri(glyph_svg(n.glyph, pl.box.w, pl.box.h, fill, stroke, accent, nodes=n.nodes,
                                                   pattern=n.pattern, tones=tones, ink=self.r.data.get("ink_scale", 1.0),
                                                   variant=getattr(n, "variant", None),
                                                   grid=getattr(n, "grid", None), seed=n.id,
                                                   col=_col_tone(self.r, getattr(n, "col_tone", None)),
                                                   axes=getattr(n, "axes", None), font_px=self.r["typography"]["small_size"],
                                                   family=self.r["typography"]["family"],
                                                   positives=getattr(n, "positives", None)))
            if n.glyph == "pair-matrix" and getattr(n, "axes", None):  # text inside the image: lint holds it to the floor
                st["pfglyphfont"] = f'{self.r["typography"]["small_size"]:.2f}'
        if n.visual == "stack":
            from .shapes import STACK_OFFSET
            fill, stroke, font = colors_for(self.r, n, parent_el)
            gst = node_style(self.r, n, parent_el)
            gst.update({"container": "1", "collapsible": "0", "fillColor": "none", "strokeColor": "none", "shadow": "0"})
            gst.pop("gradientColor", None)
            self.vertex(cid, to_html(n.label), to_style_string(gst), pl.box, parent_id, origin)
            off = STACK_OFFSET * self.r.data.get("ink_scale", 1.0)
            sw, sh = pl.box.w - (n.sheets - 1) * off, pl.box.h - (n.sheets - 1) * off
            sst = {"rounded": "1", "absoluteArcSize": "1", "arcSize": "4", "fillColor": fill, "strokeColor": stroke,
                   "strokeWidth": f"{self.r['shape']['stroke_width']:.2f}"}
            if self.r["effects"]["shadow"]:
                sst["shadow"] = "1"
            for k in range(n.sheets):  # back sheet top-right, front sheet bottom-left
                b = Box(pl.box.x + (n.sheets - 1 - k) * off, pl.box.y + k * off, sw, sh)
                self.vertex(f"pfdeco-{n.id}-sheet{k}", "", to_style_string(sst), b, cid, (pl.box.x, pl.box.y))
            self.badges(n, cid, pl)
            return
        if n.visual == "op":
            from .shapes import op_glyph
            self.vertex(cid, to_html(op_glyph(n)), to_style_string(st), pl.box, parent_id, origin)
            self.badges(n, cid, pl)
            return
        if n.visual == "tokens":
            fill, stroke, font = colors_for(self.r, n, parent_el)
            gst = {"html": "1", "whiteSpace": "nowrap", "container": "1", "collapsible": "0", "fillColor": "none", "strokeColor": "none",
                   "verticalLabelPosition": "bottom", "verticalAlign": "top", "fontFamily": self.r["typography"]["family"],
                   "fontSize": _n(self.r["typography"]["small_size"]), "fontColor": font}
            self.vertex(cid, to_html(n.label), to_style_string(gst), pl.box, parent_id, origin)
            tst = {"rounded": "1", "absoluteArcSize": "1", "arcSize": "6", "fillColor": fill, "strokeColor": stroke,
                   "strokeWidth": _n(self.r["shape"]["stroke_width"])}
            if self.r["effects"]["shadow"]:
                tst["shadow"] = "1"
            ink = self.r.data.get("ink_scale", 1.0)
            ts, tg = TOKEN_SIZE * ink, TOKEN_GAP * ink
            for k in range(n.tokens):
                b = Box(pl.box.x + k * (ts + tg), pl.box.y, ts, ts)
                cst = tst
                if n.values is not None:  # the value is the cell's shade: unequal weights are seen, not told
                    from .styles import mix
                    v = float(n.values[k])  # exactly 0 is an empty cell: sparsity reads (ISTA-Net blind run)
                    cst = dict(tst, fillColor="#ffffff" if v == 0 else mix("#ffffff", mix(stroke, "#000000", 0.25), 0.08 + 0.82 * v))
                self.vertex(f"pfdeco-{n.id}-tok{k}", "", to_style_string(cst), b, cid, (pl.box.x, pl.box.y))
        else:
            self.vertex(cid, to_html(n.label), to_style_string(st), pl.box, parent_id, origin)
        self.badges(n, cid, pl)

    def badges(self, n, cid, pl):
        bw = BADGE_W * self.r.data.get("ink_scale", 1.0)
        clear = 4.0 + self.r["shape"]["stroke_width"]
        for k, b in enumerate(n.badges):
            icon, color = BADGE_ICONS[b]
            st = {"shape": "image", "image": icon_data_uri(icon, color, self.r["shape"]["stroke_width"], bw),
                  "imageAspect": "0", "editable": "1"}
            x = pl.box.right - clear - bw - k * (bw + 2)  # inside the corner, clear of the stroke
            y = pl.box.y + clear
            if n.visual == "trapezoid":  # top-right, below the slanted outline
                from .shapes import trapezoid_top
                x -= 2
                worst = max(trapezoid_top(pl.box, n.taper, x), trapezoid_top(pl.box, n.taper, x + bw))
                y = worst + clear
            self.vertex(f"pfdeco-{n.id}-badge{k}", "", to_style_string(st), Box(x, y, bw, bw), cid, (pl.box.x, pl.box.y))

    # -------------------------------------------------------------- edges
    def edges(self):
        for e in self.bp.edges:
            rt = self.routes[e.id]
            st = edge_style(self.r, e)
            rt0 = self.routes.get(e.id)
            if st.get("dashPattern") and rt0 is not None and len(rt0.points) > 1:
                length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(rt0.points, rt0.points[1:]))
                st["dashPattern"] = fit_dash(st["dashPattern"], length)
            if e.label and rt0 is not None and len(rt0.points) > 1:
                f = self._label_panel_fill(rt0)
                if f:
                    st["labelBackgroundColor"] = f
            for key, eid, pt in (("exit", e.src, rt.points[0]), ("entry", e.dst, rt.points[-1])):
                b = self.p[eid].box
                fx = (pt[0] - b.x) / b.w if b.w else 0.5
                fy = (pt[1] - b.y) / b.h if b.h else 0.5
                # a point outside the box (below a below-label; a bundle branch leaving the shared trunk): anchor on
                # the nearest box edge plus an absolute offset
                cfx, cfy = min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))
                dx, dy = pt[0] - (b.x + cfx * b.w), pt[1] - (b.y + cfy * b.h)
                el = self.bp.index[eid]
                if not el.is_group:  # rotated/flipped shapes: drawio transforms constraints (measured)
                    cfx, cfy = to_constraint(node_style(self.r, el, None), cfx, cfy)
                st[f"{key}X"] = "%.4f" % min(1.0, max(0.0, cfx))
                st[f"{key}Y"] = "%.4f" % min(1.0, max(0.0, cfy))
                if abs(dx) > 1e-6:
                    st[f"{key}Dx"] = _n(dx)
                if abs(dy) > 1e-6:
                    st[f"{key}Dy"] = _n(dy)
                st[f"{key}Perimeter"] = "0"
            if getattr(rt, "free_end", False):  # a bundle branch that ends on the shared trunk: the trunk's one head
                st["endArrow"] = "none"
            if e.label and ("<sub>" in e.label or "<sup>" in e.label):  # the knockout must cover sub/superscripts
                ink = self.r.data.get("ink_scale", 1.0)
                st.update({"spacingTop": _n(2 * ink), "spacingBottom": _n(3 * ink)})
            value = to_html(e.label or "")
            if value and not any(abs(t) > 1e-6 for t in (getattr(rt, "label_off", None) or (0.0, 0.0))):
                # on the line: a no-break space each side widens the knock-out, so the line stops short of the first
                # and last glyph (blind runs: 'k < K', '{x_i}' touched their line; draw.io's spacing*/labelPadding do
                # not widen an html label's background — measured on the PNG)
                value = "&nbsp;" + value + "&nbsp;"
            self.edge_cell(f"pf-{e.id}", value, to_style_string(st), "1", f"pf-{e.src}", f"pf-{e.dst}",
                           rt.points[1:-1], label_x=(None if not e.label else
                                                     2 * rt.label_t - 1 if getattr(rt, "label_t", None) is not None
                                                     else label_position(rt.points)),
                           label_off=getattr(rt, "label_off", None))

    def _legend_obstacles(self) -> list:
        """Everything a legend placed inside the figure must keep clear of."""
        obs = []
        for el in self.bp.index.values():
            pl = self.p[el.id]
            if el.id == self.bp.root.id:
                if pl.title_box is not None:
                    obs.append(pl.title_box)
                continue
            if el.is_group:
                if el.frame != "none":
                    obs.append(pl.box)
                elif pl.title_box is not None:
                    obs.append(pl.title_box)
            else:
                obs.append(pl.footprint)
        for rt in self.routes.values():
            for a, b in zip(rt.points, rt.points[1:]):
                obs.append(Box(min(a[0], b[0]) - 4, min(a[1], b[1]) - 4, abs(a[0] - b[0]) + 8, abs(a[1] - b[1]) + 8))
                if rt is not None and getattr(rt, "label_box", None) is not None:
                    obs.append(rt.label_box)
        for a, b in getattr(self, "_deco_segments", []):
            obs.append(Box(min(a[0], b[0]) - 3, min(a[1], b[1]) - 3, abs(a[0] - b[0]) + 6, abs(a[1] - b[1]) + 6))
        obs.extend(getattr(self, "_ann_bands", []))  # brackets: line, ticks and label
        obs.extend(getattr(self, "_stub_boxes", []))  # stub arrows and their labels
        return obs

    def legend(self):
        fig = self.p[self.bp.root.id].box
        pts = [pt for rt in self.routes.values() for pt in rt.points]
        if pts:  # edges may detour outside the root box: keep the legend clear of them
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            fig = fig.union(Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        lg = build_legend(self.bp, self.r, fig, self._legend_obstacles())
        if lg is None:
            return
        gid = "pfdeco-legend"
        gst = {"html": "1", "container": "1", "collapsible": "0", "fillColor": "none", "strokeColor": "none"}
        self.vertex(gid, "", to_style_string(gst), lg.box, "1")
        o = (lg.box.x, lg.box.y)
        ty = self.r["typography"]
        pal = self.r["palette"]
        for i, it in enumerate(lg.items):
            if it.kind == "edge":
                st = edge_style_for_kind(self.r, it.key)
                if st.get("dashPattern"):
                    st["dashPattern"] = fit_dash(st["dashPattern"], it.sample.w)
                y = it.sample.cy - o[1]
                self.edge_cell(f"pfdeco-legend-{i}-line", "", to_style_string(st), gid,
                               sp=(it.sample.x - o[0], y), tp=(it.sample.right - o[0], y))
            elif it.kind == "op":
                from .shapes import op_glyph_style
                ost = {"html": "1", "fontFamily": ty["family"]}
                ost.update(op_glyph_style(OPS[it.key][0], it.sample.w, "#374151", self.r.data.get("ink_scale", 1.0)))
                self.vertex(f"pfdeco-legend-{i}-op", OPS[it.key][0], to_style_string(ost), it.sample, gid, o)
            elif it.kind == "note":
                pass  # text only
            elif it.kind == "tone":  # a declared colour meaning: the tone's own fill and outline
                from .styles import _tone
                tc = _tone(self.r, it.key)
                st = {"rounded": "1", "absoluteArcSize": "1", "arcSize": "6", "fillColor": tc["fill"], "strokeColor": tc["stroke"],
                      "strokeWidth": _n(self.r["shape"]["stroke_width"])}
                self.vertex(f"pfdeco-legend-{i}-tone", "", to_style_string(st), it.sample, gid, o)
            elif it.kind == "cell":  # a pair-matrix cell: filled = positive pair (the glyph's blue), empty = negative
                pos = pal["tones"].get("blue", {}).get("stroke", "#3b6fc4")
                st = {"fillColor": pos if it.key == "pos" else "#ffffff", "strokeColor": "#c7ccd4",
                      "strokeWidth": _n(0.6 * self.r.data.get("ink_scale", 1.0))}
                self.vertex(f"pfdeco-legend-{i}-cell", "", to_style_string(st), it.sample, gid, o)
            elif it.kind == "badge":
                icon, color = BADGE_ICONS[it.key]
                st = {"shape": "image", "image": icon_data_uri(icon, color, self.r["shape"]["stroke_width"],
                                                           min(it.sample.w, it.sample.h)), "imageAspect": "0"}
                self.vertex(f"pfdeco-legend-{i}-icon", "", to_style_string(st), it.sample, gid, o)
            else:
                fill, stroke = self._proposed_colors()
                st = {"rounded": "1", "absoluteArcSize": "1", "arcSize": "6", "fillColor": fill, "strokeColor": stroke,
                      "strokeWidth": _n(self.r["shape"]["group_stroke_width"])}
                self.vertex(f"pfdeco-legend-{i}-swatch", "", to_style_string(st), it.sample, gid, o)
            tst = {"html": "1", "whiteSpace": "nowrap", "strokeColor": "none", "fillColor": "none", "align": "left",
                   "verticalAlign": "middle", "spacing": "0", "fontFamily": ty["family"], "fontSize": _n(ty["small_size"]),
                   "fontColor": ty["color"]}
            self.vertex(f"pfdeco-legend-{i}-text", to_html(it.label), to_style_string(tst), it.text, gid, o)

    def _proposed_colors(self) -> tuple[str, str]:
        """The swatch shows what the proposed boxes are drawn in: the commonest (fill, stroke) of proposed leaves that
        stand for a module (an explicit tone, or not nested inside a proposed group), else a proposed group's own
        tone, else the recipe's proposed tone."""
        from collections import Counter

        from .styles import _tone, colors_for
        pal = self.r["palette"]
        seen: Counter = Counter()
        for el in self.bp.index.values():
            if el.role != "proposed" or el.is_group:
                continue
            par = self.bp.index.get(self.bp.parent.get(el.id))
            if el.tone or getattr(par, "role", None) != "proposed":
                seen[colors_for(self.r, el, par)[:2]] += 1
        if not seen:
            for el in self.bp.index.values():
                if el.is_group and el.role == "proposed" and el.tone:
                    t = _tone(self.r, el.tone)
                    seen[(t["fill"], t["stroke"])] += 1
        if seen:
            fill, stroke = seen.most_common(1)[0][0]
        else:
            t = pal["tones"][pal["roles"]["proposed"]["tone"]]
            fill, stroke = t["fill"], t["stroke"]
        if self.r.data.get("highlight") in ("outline", "ring"):  # the swatch shows what is drawn: a heavy outline
            fill = "#ffffff"  # (ring: the fills mean modality, so the swatch is the ring alone)
            if self.r.data.get("highlight") == "ring":
                stroke = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"]
        return fill, stroke

    def stubs(self):
        """A node's `stub`: a short outgoing arrow with no drawn target (a panel's output, "to the decoder")."""
        from .layout import stub_geometry
        ink = self.r.data.get("ink_scale", 1.0)
        for n in self.bp.leaves():
            st_ = getattr(n, "stub", None)
            if not st_:
                continue
            side = st_["side"]
            a, z, box = stub_geometry(n, self.p[n.id].box, self.r)
            st = edge_style_for_kind(self.r, "data")
            self.edge_cell(f"pfdeco-stub-{n.id}", "", to_style_string(st), "1", sp=a, tp=z)
            self._stub_boxes = getattr(self, "_stub_boxes", []) + [  # the legend keeps clear (placed after stubs)
                Box(min(a[0], z[0]) - 6 * ink, min(a[1], z[1]) - 6 * ink, abs(a[0] - z[0]) + 12 * ink,
                    abs(a[1] - z[1]) + 12 * ink)]
            if box is not None:  # its own text cell past the tip: an edge label centred on a short arrow covers it
                ty = self.r["typography"]
                tst = {"html": "1", "whiteSpace": "nowrap", "strokeColor": "none", "fillColor": "none", "spacing": "0",
                       "align": "right" if side == "left" else "left", "verticalAlign": "middle",
                       "fontFamily": ty["family"], "fontSize": _n(ty["small_size"]), "fontColor": ty["color"]}
                self.vertex(f"pfdeco-stub-{n.id}-label", to_html(st_["label"]), to_style_string(tst), box, "1")
                self._stub_boxes.append(box.inflate(2))

    def annotations(self):
        from .annotations import place as place_brackets

        ty = self.r["typography"]
        ink = self.r.data.get("ink_scale", 1.0)
        for aid, g in place_brackets(self.bp, self.p, self.r).items():
            a = next(x for x in self.bp.annotations if x.id == aid)
            self._ann_bands = getattr(self, "_ann_bands", []) + [g.band.inflate(3)]
            st = {"html": "1", "edgeStyle": "none", "rounded": "0", "endArrow": "none", "startArrow": "none",
                  "strokeColor": "#6b7280", "strokeWidth": _n(1.2 * ink)}
            self.edge_cell(f"pfdeco-ann-{aid}-line", "", to_style_string(st), "1", points=[(g.x0, g.y), (g.x1, g.y)],
                           sp=(g.x0, g.tick_end), tp=(g.x1, g.tick_end))
            tst = {"html": "1", "whiteSpace": "nowrap", "strokeColor": "none", "fillColor": "none", "align": "center",
                   "verticalAlign": "middle", "spacing": "0", "fontFamily": ty["family"], "fontSize": _n(ty["small_size"]),
                   "fontStyle": "1", "fontColor": "#374151"}
            self.vertex(f"pfdeco-ann-{aid}-label", to_html(a.label), to_style_string(tst), g.label, "1")

    def build(self) -> str:
        self.element(self.bp.root, None, "1", (0.0, 0.0))
        self.callouts_behind()  # above containers (their fills used to hide the legs), below edges
        self.edges()
        self.stubs()
        self.annotations()
        self.legend()
        if any("\\(" in (c.get("value") or "") for c in self.root.iter("mxCell")):  # TeX labels: MathJax on
            self.mxfile.find("diagram/mxGraphModel").set("math", "1")
        ET.indent(self.mxfile)
        return ET.tostring(self.mxfile, encoding="unicode")



def emit(bp: Blueprint, placed: dict[str, Placed], routes: dict[str, Route], recipe: Recipe) -> str:
    if getattr(bp.figure, "highlight", "fill") != "fill":  # figure-level choice the style rules read
        recipe = type(recipe)(recipe.id, dict(recipe.data, highlight=bp.figure.highlight))
    return _Writer(bp, placed, routes, recipe).build()


# ------------------------------------------------------------------ parsing
@dataclass
class Cell:
    id: str
    parent: str | None
    value: str
    style: dict
    vertex: bool
    edge: bool
    source: str | None = None
    target: str | None = None
    box: Box | None = None  # absolute, vertices only
    points: list = field(default_factory=list)  # waypoints (absolute for layer-1 edges)
    rel: Box | None = None
    label_x: float = 0.0  # edges: relative label position along the path
    sp: tuple | None = None  # free edge end points (no terminal)
    tp: tuple | None = None
    label_off: tuple = (0.0, 0.0)  # edges: absolute label offset from that point (a label beside its line)


def parse_style(s: str) -> dict:
    out = {}
    for tok in (s or "").split(";"):
        if not tok:
            continue
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
        else:
            out[tok] = None
    return out


def parse_cells(xml: str) -> dict[str, Cell]:
    root = ET.fromstring(xml)
    for d in root.iter("diagram"):
        if d.find("mxGraphModel") is None and (d.text or "").strip():
            raise PaperFigError("compressed .drawio diagrams are not supported: in draw.io use File > Properties > "
                                "uncheck 'Compressed', then save again")
    cells: dict[str, Cell] = {}
    for c in root.iter("mxCell"):
        g = c.find("mxGeometry")
        rel = None
        pts = []
        if g is not None and c.get("vertex") == "1":
            rel = Box(float(g.get("x", 0)), float(g.get("y", 0)), float(g.get("width", 0)), float(g.get("height", 0)))
        lx = 0.0
        sp = tp = None
        off = (0.0, 0.0)
        if g is not None and c.get("edge") == "1":
            lx = float(g.get("x", 0) or 0)
            for m in g.findall("mxPoint"):
                if m.get("as") == "sourcePoint":
                    sp = (float(m.get("x")), float(m.get("y")))
                elif m.get("as") == "targetPoint":
                    tp = (float(m.get("x")), float(m.get("y")))
                elif m.get("as") == "offset":
                    off = (float(m.get("x", 0) or 0), float(m.get("y", 0) or 0))
            arr = g.find("Array")
            if arr is not None:
                pts = [(float(m.get("x")), float(m.get("y"))) for m in arr.findall("mxPoint")]
        cells[c.get("id")] = Cell(c.get("id"), c.get("parent"), c.get("value") or "", parse_style(c.get("style")),
                                  c.get("vertex") == "1", c.get("edge") == "1", c.get("source"), c.get("target"), None, pts, rel, lx, sp, tp)
        cells[c.get("id")].label_off = off

    def absolute(cid: str) -> Box | None:
        cell = cells.get(cid)
        if cell is None or cell.rel is None:
            return None
        if cell.box is None:
            par = absolute(cell.parent) if cell.parent not in (None, "0", "1") else None
            cell.box = cell.rel.translate(par.x, par.y) if par else cell.rel
        return cell.box

    for cid in cells:
        absolute(cid)
    return cells
