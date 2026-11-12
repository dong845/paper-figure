"""Container layout (spec §4 ⑤): measured leaves, row/column/grid groups,
uniform gaps from the style recipe. Output is absolute boxes per element.

Uniform spacing is produced by construction (one gap value per group, only
widened where an edge label must fit), which is the main defence against the
"too tight / too loose" problem.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from .blueprint import Blueprint, Group, Node
from .errors import LayoutError
from .geometry import Box
from .measure import measure
from .styles import Recipe, _is_bold

TOKEN_SIZE, TOKEN_GAP = 14.0, 3.0
ICON_SIZE = 28.0
BADGE_SIZE, BADGE_CLEAR = 14.0, 4.0
ASPECT_MIN, ASPECT_MAX = 0.25, 4.0
EQUAL_RATIO = 1.6  # siblings whose sizes differ by less than this get the same size (tidy rows)


@dataclass
class Placed:
    elem: object
    box: Box
    label_box: Box | None = None
    title_box: Box | None = None
    title_text: Box | None = None  # where the title text sits inside title_box (the only part edges must avoid)

    axis_y: float | None = None  # groups: centre line of the content area (below the title band)

    @property
    def footprint(self) -> Box:
        return self.box.union(self.label_box)

    @property
    def axis(self) -> tuple[float, float]:
        """Visual centre line used for alignment and straight edges."""
        return self.box.cx, (self.axis_y if self.axis_y is not None else self.box.cy)


@dataclass
class _M:  # measured sizes
    shape_w: float
    shape_h: float
    label_w: float = 0.0
    label_h: float = 0.0
    # groups only
    inner_w: float = 0.0
    content_w: float = 0.0
    content_h: float = 0.0
    top: float = 0.0
    pad: float = 0.0
    band: float = 0.0
    gaps: list = field(default_factory=list)
    cols: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    row_above: float = 0.0
    left_extra: float = 0.0
    axis_override: float | None = None

    def axis_off(self) -> float:
        """Distance from the footprint top to the element's visual centre line."""
        if self.axis_override is not None:
            return self.axis_override
        if self.content_h or self.inner_w:  # group
            return self.top + self.content_h / 2
        return self.shape_h / 2

    def foot(self, label_gap: float) -> tuple[float, float]:
        if self.label_h:
            return max(self.shape_w, self.label_w), self.shape_h + label_gap + self.label_h
        return self.shape_w, self.shape_h


def placeholder_text(node: Node) -> str:
    """A placeholder looks like an image frame with a short label; its long spec goes to the report, never the figure."""
    return html.escape(node.label or "image", quote=False)


def is_pending_asset(node: Node) -> bool:
    return node.visual == "placeholder" or (node.visual == "image" and node.asset is not None and node.asset.status in ("requested", "placeholder"))


def _image_aspect(node: Node) -> float:
    if node.asset and node.asset.path and node.asset.status in ("provided", "from-code"):
        from PIL import Image, ImageOps

        try:
            with Image.open(node.asset.path) as im:
                w, h = ImageOps.exif_transpose(im).size  # displayed orientation (phone photos)
        except Exception as e:  # unreadable image is a hard error, not a silent square
            raise LayoutError(f"'{node.id}': cannot read image {node.asset.path}: {e}")
        a = w / h if h else 1.0
    elif node.size:
        a = node.size[0] / node.size[1]
    else:
        a = 1.0
    return min(ASPECT_MAX, max(ASPECT_MIN, a))


class _Solver:
    def __init__(self, bp: Blueprint, recipe: Recipe, extra_pad: dict | None = None):
        self.bp, self.r = bp, recipe
        self.extra = extra_pad or {}
        self.ink = recipe.data.get("ink_scale", 1.0)
        self.grid_gap: dict[tuple[str, str, int], float] = {}  # (group, "row"|"col", index) -> min gap
        self.row_axis: dict[str, list] = {}
        self.free_pos: dict[str, tuple[float, float]] = {}
        self.ty, self.sp = recipe["typography"], recipe["spacing"]
        self.m: dict[str, _M] = {}
        self.out: dict[str, Placed] = {}
        self.pair_gap: dict[tuple[str, int], float] = {}
        self._edge_label_gaps()

    # ---------- measuring ----------
    def _edge_label_gaps(self):
        for e in self.bp.edges:
            if not e.label:
                continue
            a_chain = [e.src] + self.bp.ancestors(e.src)
            b_chain = [e.dst] + self.bp.ancestors(e.dst)
            lca = next((g for g in a_chain[1:] if g in b_chain[1:]), None)
            if lca is None:
                continue
            g = self.bp.index[lca]
            ca = a_chain[a_chain.index(lca) - 1]
            cb = b_chain[b_chain.index(lca) - 1]
            ids = [c.id for c in g.children]
            i, j = ids.index(ca), ids.index(cb)
            lw, lh = measure(e.label, self.ty["small_size"])
            lw += 2 * 6.0 * self.ink  # keep the line and arrowhead visible on both sides of the label
            if g.layout.type == "grid":
                A, B = self.bp.index[ca], self.bp.index[cb]
                if abs(A.cell[0] - B.cell[0]) == 1:  # vertical or diagonal neighbours: label sits on the vertical leg
                    k = (lca, "row", min(A.cell[0], B.cell[0]))
                    self.grid_gap[k] = max(self.grid_gap.get(k, 0.0), lh + 2 * 6.0 * self.ink + 2 * self.sp["edge_label_pad"])
                elif A.cell[0] == B.cell[0] and abs(A.cell[1] - B.cell[1]) == 1:
                    k = (lca, "col", min(A.cell[1], B.cell[1]))
                    self.grid_gap[k] = max(self.grid_gap.get(k, 0.0), lw + 2 * self.sp["edge_label_pad"])
                continue
            if abs(i - j) != 1:
                continue
            need = (lw if g.layout.type == "row" else lh + 2 * 6.0 * self.ink) + 2 * self.sp["edge_label_pad"]
            k = (lca, min(i, j))
            self.pair_gap[k] = max(self.pair_gap.get(k, 0.0), need)

    def leaf(self, n: Node) -> _M:
        ty, sp = self.ty, self.sp
        bold = _is_bold(self.r, n)
        v = n.visual
        label_w = label_h = 0.0
        has_below = v in ("tensor", "tokens", "image", "icon", "stack") and bool(n.label)
        if v == "box":
            tw, th = measure(n.label, ty["size"], bold, ty["family"])
            padx = sp["node_pad_x"]
            if n.badges:  # badges sit inside the top-right corner: keep the centred text clear of them
                padx = max(padx, BADGE_SIZE * self.ink + BADGE_CLEAR + 2)
            w, h = max(sp["min_node_w"], tw + 2 * padx), max(sp["min_node_h"], th + 2 * sp["node_pad_y"])
        elif v == "placeholder":
            tw, th = measure(placeholder_text(n), ty["small_size"], False, ty["family"])
            L = self.r["image"]["default_long_side"]
            w, h = (n.size[0], n.size[1]) if n.size else (L, 0.75 * L)
            w, h = max(w, tw + 2 * sp["node_pad_x"]), max(h, th + 2 * sp["node_pad_y"])
        elif v == "text":
            tw, th = measure(n.label, ty["small_size"], bold and n.role != "annotation", ty["family"])
            w, h = tw + 6, th + 4
        elif v == "op":
            if n.op:  # typed operator: the box is exactly its glyph ring
                from .shapes import op_ring
                w = h = op_ring(ty["size"])
            else:
                tw, th = measure(n.label, ty["size"], bold, ty["family"])
                w = h = max(26.0 * self.ink, max(tw, th) + 10 * self.ink)
        elif v == "trapezoid":
            from .shapes import TRAPEZOID_SIZE
            tw, th = measure(n.label, ty["size"], bold, ty["family"])
            usable = 1 - 2 * TRAPEZOID_SIZE  # the narrow end of the taper
            padx = sp["node_pad_x"]
            if n.badges:  # top-right badge: keep the centred text clear of it
                padx = max(padx, BADGE_SIZE * self.ink + BADGE_CLEAR + 4)
            w = max(sp["min_node_w"], tw + 2 * padx)
            h = max(sp["min_node_h"] * 1.5, (th + 2 * sp["node_pad_y"]) / usable)
        elif v == "slab":
            from .shapes import slab_rotated
            tw, th = measure(n.label, ty["small_size"], False, ty["family"])
            if slab_rotated(n):  # label rotated 90 degrees
                w = th + 2 * 3 * self.ink
                h = max(sp["min_node_h"], tw + 2 * sp["node_pad_y"])
            else:
                w = tw + 2 * 5 * self.ink
                h = sp["min_node_h"]
        elif v == "stack":
            from .shapes import STACK_OFFSET
            t = self.r["tensor"]
            off = STACK_OFFSET * self.ink
            sheet_w, sheet_h = t["h"] * 0.42, t["h"]
            w, h = sheet_w + (n.sheets - 1) * off, sheet_h + (n.sheets - 1) * off
        elif v == "tensor":
            t = self.r["tensor"]
            w, h = t["w"] + t["depth"], t["h"] + t["depth"]
        elif v == "tokens":
            k = n.tokens or 1
            ts, tg = TOKEN_SIZE * self.ink, TOKEN_GAP * self.ink
            w, h = k * ts + (k - 1) * tg, ts
        elif v == "image":
            a = _image_aspect(n)
            if n.size:
                hw, hh = n.size
                w, h = (hw, hw / a) if hw / a <= hh else (hh * a, hh)
            else:
                L = self.r["image"]["default_long_side"]
                w, h = (L, L / a) if a >= 1 else (L * a, L)
        elif v == "icon":
            w = h = ICON_SIZE * self.ink
        else:  # pragma: no cover - schema forbids
            raise LayoutError(f"'{n.id}': unknown visual {v}")
        if n.size and v not in ("image", "placeholder"):
            w, h = max(w, n.size[0]), max(h, n.size[1])
            if v == "op":
                w = h = max(w, h)
        if has_below:
            label_w, label_h = measure(n.label, ty["small_size"], False, ty["family"])
        return _M(w, h, label_w, label_h)

    def foot(self, eid: str) -> tuple[float, float]:
        return self.m[eid].foot(self.sp["label_gap"])

    def group(self, g: Group) -> _M:
        for c in g.children:
            self.m[c.id] = self.group(c) if c.is_group else self.leaf(c)
        lay = g.layout
        if lay.equalize:
            self._equalize(g)
        gap = self.sp["gap"][lay.gap]
        n = len(g.children)
        gaps = [max(gap, self.pair_gap.get((g.id, i), 0.0)) for i in range(n - 1)]
        cols: list[float] = []
        rows: list[float] = []
        above = below = 0.0
        if lay.type == "row":
            W = sum(self.foot(c.id)[0] for c in g.children) + sum(gaps)
            if lay.align == "center":
                above = max(self.m[c.id].axis_off() for c in g.children)
                below = max(self.foot(c.id)[1] - self.m[c.id].axis_off() for c in g.children)
                H = above + below
            else:
                H = max(self.foot(c.id)[1] for c in g.children)
        elif lay.type == "column":
            W = max(self.foot(c.id)[0] for c in g.children)
            H = sum(self.foot(c.id)[1] for c in g.children) + sum(gaps)
        else:
            cols, rows = self._grid_tracks(g, gap)
            W = sum(cols) + sum(self._tgap(g, "col", i, gap) for i in range(len(cols) - 1))
            H = sum(rows) + sum(self._tgap(g, "row", i, gap) for i in range(len(rows) - 1))
            placed_free: list[Box] = []
            for c in g.children:  # free children: anchored at their cell origin, extend the grid if needed
                if c.place == "free":
                    fw, fh = self.foot(c.id)
                    x0 = self._span(g, "col", cols, 0, c.cell[1], gap) + (self._tgap(g, "col", c.cell[1] - 1, gap) if c.cell[1] else 0)
                    y0 = self._span(g, "row", rows, 0, c.cell[0], gap) + (self._tgap(g, "row", c.cell[0] - 1, gap) if c.cell[0] else 0)
                    moved = True
                    while moved:  # stack below earlier free panels instead of colliding with them
                        moved = False
                        for b in placed_free:
                            if Box(x0, y0, fw, fh).intersects(b.inflate(gap / 2)):
                                y0 = b.bottom + gap
                                moved = True
                    placed_free.append(Box(x0, y0, fw, fh))
                    self.free_pos[c.id] = (x0, y0)
                    W, H = max(W, x0 + fw), max(H, y0 + fh)
        pad = self.sp["group_pad"] if g.frame != "none" else 0.0
        ex = {k: self.extra.get((g.id, k), 0.0) for k in ("top", "bottom", "left", "right")}
        band = top = 0.0
        title_w = 0.0
        if g.title:
            title_w, th = measure(g.title, self.ty["title_size"], _is_bold(self.r, g), self.ty["family"])
            band = max(self.sp["title_h"], th + 8)
            top = band + pad * 0.5
        else:
            top = pad
        top += ex["top"]
        inner_w = max(W, title_w + 8)
        m = _M(inner_w + 2 * pad + ex["left"] + ex["right"], top + H + pad + ex["bottom"], inner_w=inner_w, content_w=W,
               content_h=H, top=top, pad=pad, band=band, gaps=gaps, cols=cols, rows=rows)
        m.left_extra = ex["left"]
        m.row_above = above
        if g.axis_of:  # dry-run placement to find the descendant's centre relative to the group top
            self.m[g.id] = m
            saved = self.out
            self.out = {}
            self.place(g, 0.0, 0.0)
            m.axis_override = self.out[g.axis_of].box.cy
            self.out = saved
        return m

    def _equalize(self, g: Group):
        boxes = [c for c in g.children if not c.is_group and c.visual == "box"]
        if len(boxes) < 2:
            return
        t = g.layout.type

        def same(attr, force):
            vals = [getattr(self.m[c.id], attr) for c in boxes]
            if force or max(vals) <= EQUAL_RATIO * min(vals):
                for c in boxes:
                    setattr(self.m[c.id], attr, max(vals))

        if t == "row":
            same("shape_h", True)
            same("shape_w", False)
        elif t == "column":
            same("shape_w", True)
            same("shape_h", False)
        else:
            for key, attr, idx in (("row", "shape_h", 0), ("col", "shape_w", 1)):
                buckets: dict[int, list] = {}
                for c in boxes:
                    if c.span[idx] == 1:
                        buckets.setdefault(c.cell[idx], []).append(c)
                for members in buckets.values():
                    mx = max(getattr(self.m[c.id], attr) for c in members)
                    for c in members:
                        setattr(self.m[c.id], attr, mx)

    def _tgap(self, g: Group, axis: str, i: int, gap: float) -> float:
        return max(gap, self.grid_gap.get((g.id, axis, i), 0.0))

    def _span(self, g: Group, axis: str, tracks: list, start: int, n: int, gap: float) -> float:
        return sum(tracks[start : start + n]) + sum(self._tgap(g, axis, i, gap) for i in range(start, start + n - 1))

    def _grid_tracks(self, g: Group, gap: float):
        nr = max(c.cell[0] + c.span[0] for c in g.children)
        nc = max(c.cell[1] + c.span[1] for c in g.children)
        cols, rows = [0.0] * nc, [0.0] * nr
        above = [0.0] * nr
        below = [0.0] * nr
        tracked = [c for c in g.children if c.place != "free"]
        for c in tracked:
            fw, fh = self.foot(c.id)
            if c.span[1] == 1:
                cols[c.cell[1]] = max(cols[c.cell[1]], fw)
            if c.span[0] == 1:
                rows[c.cell[0]] = max(rows[c.cell[0]], fh)
                ax = self.m[c.id].axis_off()
                above[c.cell[0]] = max(above[c.cell[0]], ax)
                below[c.cell[0]] = max(below[c.cell[0]], fh - ax)
        if g.layout.align == "center":  # rows align on shape centres, so captions hang below
            rows = [max(r, a + b) for r, a, b in zip(rows, above, below)]
            self.row_axis[g.id] = above
        for c in tracked:  # spans: distribute any deficit evenly
            fw, fh = self.foot(c.id)
            if c.span[1] > 1:
                idx = range(c.cell[1], c.cell[1] + c.span[1])
                have = self._span(g, "col", cols, c.cell[1], c.span[1], gap)
                for i in idx:
                    cols[i] += max(0.0, fw - have) / c.span[1]
            if c.span[0] > 1:
                idx = range(c.cell[0], c.cell[0] + c.span[0])
                have = self._span(g, "row", rows, c.cell[0], c.span[0], gap)
                for i in idx:
                    rows[i] += max(0.0, fh - have) / c.span[0]
        return cols, rows

    # ---------- positioning ----------
    def place(self, el, x: float, y: float):
        m = self.m[el.id]
        if not el.is_group:
            fw, _ = self.foot(el.id)
            box = Box(x + (fw - m.shape_w) / 2, y, m.shape_w, m.shape_h)
            lb = None
            if m.label_h:
                lb = Box(x + (fw - m.label_w) / 2, box.bottom + self.sp["label_gap"], m.label_w, m.label_h)
            self.out[el.id] = Placed(el, box, lb)
            return
        box = Box(x, y, m.shape_w, m.shape_h)
        tb = Box(x, y, m.shape_w, m.band) if el.title else None
        self.out[el.id] = Placed(el, box, None, tb, axis_y=y + m.axis_off())
        if tb is not None:
            from .styles import title_text_box

            self.out[el.id].title_text = title_text_box(self.r, el, self.out[el.id])
        ox = x + m.pad + m.left_extra + (m.inner_w - m.content_w) / 2
        oy = y + m.top
        f = {"start": 0.0, "center": 0.5, "end": 1.0}[el.layout.align]
        t = el.layout.type
        if t == "row":
            cur = ox
            for i, c in enumerate(el.children):
                fw, fh = self.foot(c.id)
                if el.layout.align == "center":
                    cy = oy + m.row_above - self.m[c.id].axis_off()
                else:
                    cy = oy + (m.content_h - fh) * f
                self.place(c, cur, cy)
                cur += fw + (m.gaps[i] if i < len(m.gaps) else 0)
        elif t == "column":
            cur = oy
            for i, c in enumerate(el.children):
                fw, fh = self.foot(c.id)
                self.place(c, ox + (m.content_w - fw) * f, cur)
                cur += fh + (m.gaps[i] if i < len(m.gaps) else 0)
        else:
            gap = self.sp["gap"][el.layout.gap]
            xs = [ox + self._span(el, "col", m.cols, 0, i, gap) + (self._tgap(el, "col", i - 1, gap) if i else 0) for i in range(len(m.cols))]
            ys = [oy + self._span(el, "row", m.rows, 0, i, gap) + (self._tgap(el, "row", i - 1, gap) if i else 0) for i in range(len(m.rows))]
            for c in el.children:
                fw, fh = self.foot(c.id)
                r0, c0 = c.cell
                if c.place == "free":
                    fx, fy = self.free_pos[c.id]
                    self.place(c, ox + fx, oy + fy)
                    continue
                cw = self._span(el, "col", m.cols, c0, c.span[1], gap)
                rh = self._span(el, "row", m.rows, r0, c.span[0], gap)
                axes = self.row_axis.get(el.id)
                if axes is not None and c.span[0] == 1:
                    y = ys[r0] + axes[r0] - self.m[c.id].axis_off()
                else:
                    y = ys[r0] + (rh - fh) * f
                self.place(c, xs[c0] + (cw - fw) * f, y)


def solve(bp: Blueprint, recipe: Recipe, extra_pad: dict | None = None) -> dict[str, Placed]:
    """extra_pad: {(group_id, side): px} reserved routing channels (see pipeline.solve_and_route)."""
    s = _Solver(bp, recipe, extra_pad)
    s.m[bp.root.id] = s.group(bp.root)
    s.place(bp.root, 0.0, 0.0)
    _check_free(bp, s.out, recipe)
    return s.out


def _check_free(bp: Blueprint, out: dict, recipe: Recipe):
    """A free-placed child must not collide with its siblings (keep a small gap)."""
    gap = recipe["spacing"]["gap"]["tight"] / 2
    for g in bp.groups():
        if g.layout.type != "grid":
            continue
        for c in g.children:
            if c.place != "free":
                continue
            fb = out[c.id].footprint.inflate(gap)
            for o in g.children:
                if o.id != c.id and fb.intersects(out[o.id].footprint):
                    raise LayoutError(f"free-placed '{c.id}' overlaps '{o.id}' in grid '{g.id}': move it to another cell")
