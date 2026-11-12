"""Emit draw.io (mxGraph) XML from a solved layout and routes, and parse it back.

Design for editability: groups are real drawio containers (children move with
them), edges stay attached to their terminals (exit/entry constraints) and carry
explicit waypoints, labels are plain html with <b>/<i>/<sub>/<sup>/<br> only.
"""
from __future__ import annotations

import base64
import dataclasses
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .blueprint import Blueprint
from .errors import PaperFigError
from .geometry import Box
from .layout import Placed, is_pending_asset, placeholder_text
from .legend import BADGE_W, build as build_legend
from .markup import to_html
from .route import Route
from .shapes import OPS, to_constraint
from .styles import Recipe, colors_for, edge_style, edge_style_for_kind, group_style, node_style, to_style_string

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
BADGE_ICONS = {"frozen": ("snowflake", "#2563eb"), "trainable": ("flame", "#ea580c")}
TOKEN_SIZE, TOKEN_GAP = 14.0, 3.0


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


def _n(v: float) -> str:
    s = "%.2f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


def icon_data_uri(name: str, color: str) -> str:
    p = ICON_DIR / f"{name}.svg"
    if not p.is_file():
        avail = ", ".join(sorted(x.stem for x in ICON_DIR.glob("*.svg")))
        raise PaperFigError(f"unknown icon '{name}' (available: {avail})")
    svg = p.read_text(encoding="utf-8").replace("currentColor", color)
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
        c = ET.SubElement(self.root, "mxCell", id=cid, value=value, style=style, vertex="1", parent=parent_id)
        ET.SubElement(c, "mxGeometry", {"x": _n(box.x - origin[0]), "y": _n(box.y - origin[1]),
                                        "width": _n(box.w), "height": _n(box.h), "as": "geometry"})
        return c

    def edge_cell(self, cid, value, style, parent_id, source=None, target=None, points=(), sp=None, tp=None, label_x=None):
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
            st = to_style_string(group_style(self.r, el))
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

    def leaf(self, n, parent_el, parent_id, origin):
        pl = self.p[n.id]
        cid = f"pf-{n.id}"
        g = self._details().get(n.id)
        if g is not None:  # highlight the source node with the panel's tint, behind the node
            fill, stroke, _ = colors_for(self.r, g)
            hst = {"rounded": "1", "absoluteArcSize": "1", "arcSize": _n(2 * self.r["shape"]["radius"] + 6), "fillColor": fill,
                   "strokeColor": stroke, "strokeWidth": "1", "dashed": "1", "dashPattern": "3 3"}
            self.vertex(f"pfdeco-callout-{g.id}-halo", "", to_style_string(hst), self._halo_box(n.id), parent_id, origin)
        if is_pending_asset(n):
            st = node_style(self.r, dataclasses.replace(n, visual="placeholder"), parent_el)
            self.vertex(cid, to_html(placeholder_text(n)), to_style_string(st), pl.box, parent_id, origin)
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
            st["image"] = icon_data_uri(n.icon, colors_for(self.r, n, parent_el)[1])
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
                self.vertex(f"pfdeco-{n.id}-tok{k}", "", to_style_string(tst), b, cid, (pl.box.x, pl.box.y))
        else:
            self.vertex(cid, to_html(n.label), to_style_string(st), pl.box, parent_id, origin)
        self.badges(n, cid, pl)

    def badges(self, n, cid, pl):
        bw = BADGE_W * self.r.data.get("ink_scale", 1.0)
        clear = 4.0 + self.r["shape"]["stroke_width"]
        for k, b in enumerate(n.badges):
            icon, color = BADGE_ICONS[b]
            st = {"shape": "image", "image": icon_data_uri(icon, color), "imageAspect": "0", "editable": "1"}
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
            if e.label:  # knock-out behind the label = the fill of the panel the edge runs in
                both = [g for g in self.bp.ancestors(e.src) if g in self.bp.ancestors(e.dst)]
                for gid in both:
                    g = self.bp.index[gid]
                    if g.frame != "none":
                        f = group_style(self.r, g).get("fillColor", "none")
                        if f and f != "none":
                            st["labelBackgroundColor"] = f
                        break
            for key, eid, pt in (("exit", e.src, rt.points[0]), ("entry", e.dst, rt.points[-1])):
                b = self.p[eid].box
                fx = (pt[0] - b.x) / b.w if b.w else 0.5
                fy = (pt[1] - b.y) / b.h if b.h else 0.5
                dy = 0.0
                if fy > 1.0 + 1e-9:  # bottom port below a below-label: anchor at bottom + offset
                    dy, fy = pt[1] - b.bottom, 1.0
                el = self.bp.index[eid]
                if not el.is_group:  # rotated/flipped shapes: drawio transforms constraints (measured)
                    fx, fy = to_constraint(node_style(self.r, el, None), fx, fy)
                st[f"{key}X"] = "%.4f" % min(1.0, max(0.0, fx))
                fy = min(1.0, max(0.0, fy))
                st[f"{key}Y"] = "%.4f" % fy
                if dy:
                    st[f"{key}Dy"] = _n(dy)
                st[f"{key}Perimeter"] = "0"
            self.edge_cell(f"pf-{e.id}", to_html(e.label or ""), to_style_string(st), "1", f"pf-{e.src}", f"pf-{e.dst}",
                           rt.points[1:-1], label_x=label_position(rt.points) if e.label else None)

    def legend(self):
        fig = self.p[self.bp.root.id].box
        pts = [pt for rt in self.routes.values() for pt in rt.points]
        if pts:  # edges may detour outside the root box: keep the legend clear of them
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            fig = fig.union(Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        lg = build_legend(self.bp, self.r, fig)
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
                y = it.sample.cy - o[1]
                self.edge_cell(f"pfdeco-legend-{i}-line", "", to_style_string(st), gid,
                               sp=(it.sample.x - o[0], y), tp=(it.sample.right - o[0], y))
            elif it.kind == "op":
                ost = {"shape": "ellipse", "perimeter": "ellipsePerimeter", "aspect": "fixed", "html": "1", "fillColor": "#ffffff",
                       "strokeColor": "#6b7280", "fontFamily": ty["family"], "fontSize": _n(ty["small_size"]), "fontColor": ty["color"]}
                self.vertex(f"pfdeco-legend-{i}-op", OPS[it.key][0], to_style_string(ost), it.sample, gid, o)
            elif it.kind == "note":
                pass  # text only
            elif it.kind == "badge":
                icon, color = BADGE_ICONS[it.key]
                st = {"shape": "image", "image": icon_data_uri(icon, color), "imageAspect": "0"}
                self.vertex(f"pfdeco-legend-{i}-icon", "", to_style_string(st), it.sample, gid, o)
            else:
                t = pal["tones"][pal["roles"]["proposed"]["tone"]]
                st = {"rounded": "1", "absoluteArcSize": "1", "arcSize": "6", "fillColor": t["fill"], "strokeColor": t["stroke"],
                      "strokeWidth": _n(self.r["shape"]["group_stroke_width"])}
                self.vertex(f"pfdeco-legend-{i}-swatch", "", to_style_string(st), it.sample, gid, o)
            tst = {"html": "1", "whiteSpace": "nowrap", "strokeColor": "none", "fillColor": "none", "align": "left",
                   "verticalAlign": "middle", "spacing": "0", "fontFamily": ty["family"], "fontSize": _n(ty["small_size"]),
                   "fontColor": ty["color"]}
            self.vertex(f"pfdeco-legend-{i}-text", to_html(it.label), to_style_string(tst), it.text, gid, o)

    def annotations(self):
        from .annotations import place as place_brackets

        ty = self.r["typography"]
        ink = self.r.data.get("ink_scale", 1.0)
        for aid, g in place_brackets(self.bp, self.p, self.r).items():
            a = next(x for x in self.bp.annotations if x.id == aid)
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
        self.annotations()
        self.legend()
        ET.indent(self.mxfile)
        return ET.tostring(self.mxfile, encoding="unicode")


def emit(bp: Blueprint, placed: dict[str, Placed], routes: dict[str, Route], recipe: Recipe) -> str:
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
        if g is not None and c.get("edge") == "1":
            lx = float(g.get("x", 0) or 0)
            for m in g.findall("mxPoint"):
                if m.get("as") == "sourcePoint":
                    sp = (float(m.get("x")), float(m.get("y")))
                elif m.get("as") == "targetPoint":
                    tp = (float(m.get("x")), float(m.get("y")))
            arr = g.find("Array")
            if arr is not None:
                pts = [(float(m.get("x")), float(m.get("y"))) for m in arr.findall("mxPoint")]
        cells[c.get("id")] = Cell(c.get("id"), c.get("parent"), c.get("value") or "", parse_style(c.get("style")),
                                  c.get("vertex") == "1", c.get("edge") == "1", c.get("source"), c.get("target"), None, pts, rel, lx, sp, tp)

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
