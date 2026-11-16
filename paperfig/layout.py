"""Container layout (spec §4 ⑤): measured leaves, row/column/grid groups,
uniform gaps from the style recipe. Output is absolute boxes per element.

Uniform spacing is produced by construction (one gap value per group, only
widened where an edge label must fit), which is the main defence against the
"too tight / too loose" problem.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .blueprint import GRIDLIKE, has_file, Blueprint, Group, Node
from .errors import LayoutError
from .geometry import Box
from .measure import measure
from .styles import Recipe, _is_bold

TOKEN_SIZE, TOKEN_GAP = 14.0, 3.0
ICON_SIZE = 28.0
BUBBLE_TAIL = 9.0  # the speech bubble's pointer below the text
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
    label_side: str = "below"  # "top"/"right"/"left": the name moved off the bottom a line leaves (user, round 2)
    _gap: float = 0.0  # label gap, for axis_off of a name above
    label_dx: float | None = None  # name below starting this far right of the shape (pair-matrix: after the row names)
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
        if self.label_h and self.label_side == "top":
            return self.label_h + self._gap + self.shape_h / 2
        if self.label_h and self.label_side != "below":
            return max(self.shape_h, self.label_h) / 2
        return self.shape_h / 2

    def foot(self, label_gap: float) -> tuple[float, float]:
        if self.label_h and self.label_side == "top":  # name above the shape: same footprint as below
            return max(self.shape_w, self.label_w), self.shape_h + label_gap + self.label_h
        if self.label_h and self.label_side != "below":
            return self.shape_w + label_gap + self.label_w, max(self.shape_h, self.label_h)
        if self.label_h:
            w = max(self.shape_w, self.label_w) if self.label_dx is None else max(self.shape_w, self.label_dx + self.label_w)
            return w, self.shape_h + label_gap + self.label_h
        return self.shape_w, self.shape_h


def placeholder_text(node: Node) -> str:
    """A placeholder looks like an image frame with a short label; its long spec goes to the report, never the figure."""
    # the label is blueprint markup like any other (validated on load): <br>, <sub>, $..$ render; escaping it printed
    # "input<br>m⁰" literally (VS-Net blind run)
    return node.label or "image"


def is_pending_asset(node: Node) -> bool:
    return node.visual == "placeholder" or (node.visual == "image" and node.asset is not None and not has_file(node.asset))


def _image_aspect(node: Node) -> float:
    if node.asset and node.asset.path and has_file(node.asset):
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


RESIZABLE = ("box", "trapezoid", "textcard", "slab")  # visuals that may grow to hold their ports (not glyphs, images)


class _Solver:
    def __init__(self, bp: Blueprint, recipe: Recipe, extra_pad: dict | None = None):
        self.bp, self.r = bp, recipe
        self.extra = extra_pad or {}
        self.ink = recipe.data.get("ink_scale", 1.0)
        self.grid_gap: dict[tuple[str, str, int], float] = {}  # (group, "row"|"col", index) -> min gap
        self.row_axis: dict[str, list] = {}
        self.free_pos: dict[str, tuple[float, float]] = {}
        self.ty, self.sp = recipe["typography"], dict(recipe["spacing"])
        self.sp["gap"] = dict(self.sp["gap"], none=0.0)  # gap "none": glued (chips such as [d | x])
        self.m: dict[str, _M] = {}
        self.out: dict[str, Placed] = {}
        self.pair_gap: dict[tuple[str, int], float] = {}
        self._canvas_links()
        self._edge_label_gaps()
        self._arrow_gaps()

    # ---------- measuring ----------
    def _canvas_links(self):
        """Column boundaries of a canvas that an edge crosses between two side-by-side children (full gap there)."""
        self.canvas_links = set()
        for e in self.bp.edges:
            a_chain = [e.src] + self.bp.ancestors(e.src)
            b_chain = [e.dst] + self.bp.ancestors(e.dst)
            lca = next((g for g in a_chain[1:] if g in b_chain[1:]), None)
            if lca is None or self.bp.index[lca].layout.type != "canvas":
                continue
            A = self.bp.index[a_chain[a_chain.index(lca) - 1]]
            B = self.bp.index[b_chain[b_chain.index(lca) - 1]]
            if A.cell is None or B.cell is None:
                continue
            if A.cell[1] > B.cell[1]:
                A, B = B, A
            lo, hi = A.cell[1] + A.span[1] - 1, B.cell[1]
            for i in range(lo, hi):  # every boundary between them carries the arrow
                self.canvas_links.add((lca, i))

    SHAFT_HEADS = 1.5  # an arrow keeps at least this many arrowhead lengths of visible line between its heads
    PARALLEL = 1.5  # = route.PARALLEL: lines closer than this many arrowheads read as one
    HEAD_DRAWN = 1.4  # = route.HEAD_DRAWN: draw.io draws a block head this many endSizes long

    def _gap_between(self, e):
        """Which gap an edge between two neighbouring siblings crosses: ("pair", key) in a row/column,
        ("grid", key) in a grid/canvas, or None (not neighbours)."""
        a_chain = [e.src] + self.bp.ancestors(e.src)
        b_chain = [e.dst] + self.bp.ancestors(e.dst)
        lca = next((g for g in a_chain[1:] if g in b_chain[1:]), None)
        if lca is None:
            return None
        g = self.bp.index[lca]
        ca, cb = a_chain[a_chain.index(lca) - 1], b_chain[b_chain.index(lca) - 1]
        if ca == cb:
            return None
        if g.layout.type in GRIDLIKE:
            A, B = self.bp.index[ca], self.bp.index[cb]
            if A.cell is None or B.cell is None:
                return None
            top, bot = (A, B) if A.cell[0] <= B.cell[0] else (B, A)
            if top.cell[0] + top.span[0] == bot.cell[0]:
                return "grid", (lca, "row", top.cell[0] + top.span[0] - 1)
            L, R = (A, B) if A.cell[1] <= B.cell[1] else (B, A)
            if L.cell[1] + L.span[1] == R.cell[1]:
                return "grid", (lca, "col", L.cell[1] + L.span[1] - 1)
            return None
        ids = [c.id for c in g.children]
        i, j = ids.index(ca), ids.index(cb)
        return ("pair", (lca, min(i, j))) if abs(i - j) == 1 else None

    def _dash_period(self, kind) -> float:
        """Line needed to recognise a dash pattern as drawn (draw.io scales it by the stroke width): the pattern up
        to its last mark — dash, gap, dot for a dash-dot — so its trailing gap is not paid for. 0 for a solid kind, and
        for a kind drawn in another colour than data lines: there the pattern is not the only cue."""
        edges = self.r.data.get("edges", {})
        st = edges.get(kind, {})
        solid = edges.get("data", {})
        if str(st.get("color", "")).lower() != str(solid.get("color", "")).lower():
            return 0.0  # its colour already tells it from a data line (LDM: blue z~p(z)); widening cost text size
        try:
            marks = [float(x) for x in str(st.get("dash") or "").split()]
        except ValueError:
            return 0.0
        return sum(marks[:-1]) * float(st.get("width", 1.0)) if len(marks) >= 2 else 0.0

    def _arrow_gaps(self):
        """A gap an arrow crosses holds its heads and a visible shaft: a loss arrow (two heads) gets room for both
        (DreamerV3 run: double-headed arrows in a gap sized for one head, the heads met)."""
        from .styles import arrow_size
        head = arrow_size(self.r)  # the arrowhead size edges are drawn with
        edges_r = self.r.data.get("edges", {})
        per_gap: dict = {}  # (table, key) -> [need of each arrow crossing that gap]
        for e in self.bp.edges:
            st = edges_r.get(e.kind, {})
            hh = getattr(e, "heads", "auto")
            heads = ((st.get("start", "none") not in ("none", None) and hh == "auto")
                     + (st.get("end", "none") not in ("none", None) and hh != "none"))
            if not heads:
                continue
            where = self._gap_between(e)
            if where is None:
                continue
            # a dashed line shorter than one pattern reads as solid (TWM run: dash-dot infer_only edges drew solid)
            need = heads * self.HEAD_DRAWN * head + max(self.SHAFT_HEADS * head, self._dash_period(e.kind))
            per_gap.setdefault(where, []).append((need, bool(self.extra.get((e.id, "bent")))))
        for (kind, k), items in per_gap.items():
            # every further line that BENDS in the gap (routing reported it: solve_and_route) gets its own channel,
            # PARALLEL heads from the next, so those lines neither cross nor run side by side (user, round 2: lines
            # meeting read as one thick line); lines straight across need none — widening for them cost text size
            bent = sum(1 for _, b in items if b)
            need = max(n for n, _ in items) + max(0, bent - 1) * self.PARALLEL * head
            table = self.grid_gap if kind == "grid" else self.pair_gap
            table[k] = max(table.get(k, 0.0), need)

    def _label_gap(self, table, k, need, e):
        """A gap an edge label needs; the widest one per gap is remembered (grammar 'gap-by-label': TWM run — one
        label on sampler -> o1 made the figure 1091 px wide instead of 709, and nothing said which)."""
        if need > table.get(k, 0.0):
            table[k] = need
            by = getattr(self.bp, "label_gaps", None)
            if by is None:
                by = self.bp.label_gaps = {}
            by[k] = (need, e.id)

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
            lw, lh = measure(e.label, self.ty["small_size"], False, self.ty["family"])
            # keep the line and arrowhead visible on both sides of the label — a whole dash pattern for a dashed kind,
            # or the line reads as solid (TWM run: labelled infer_only edges drew solid beside a dash-dot one)
            side = max(6.0 * self.ink, self._dash_period(e.kind))
            lw += 2 * side  # (a label that cannot leave its arrowhead a shaft goes beside the line: route._place_labels)
            if g.layout.type in GRIDLIKE:
                A, B = self.bp.index[ca], self.bp.index[cb]
                if A.cell[1] > B.cell[1] or (A.cell[1] == B.cell[1] and A.cell[0] > B.cell[0]):
                    A, B = B, A
                a_end_r, a_end_c = A.cell[0] + A.span[0] - 1, A.cell[1] + A.span[1] - 1
                top, bot = (A, B) if A.cell[0] <= B.cell[0] else (B, A)
                t_end = top.cell[0] + top.span[0] - 1
                if t_end + 1 == bot.cell[0]:  # stacked neighbours (touching row spans): label on the vertical leg
                    k = (lca, "row", t_end)
                    self._label_gap(self.grid_gap, k, lh + 2 * side + 2 * self.sp["edge_label_pad"], e)
                elif a_end_c + 1 == B.cell[1] and A.cell[0] <= B.cell[0] + B.span[0] - 1 and B.cell[0] <= a_end_r:
                    k = (lca, "col", a_end_c)  # side by side (touching column spans that share a row)
                    self._label_gap(self.grid_gap, k, lw + 2 * self.sp["edge_label_pad"], e)
                continue
            if abs(i - j) != 1:
                continue
            need = (lw if g.layout.type == "row" else lh + 2 * side) + 2 * self.sp["edge_label_pad"]
            k = (lca, min(i, j))
            self._label_gap(self.pair_gap, k, need, e)

    def leaf(self, n: Node) -> _M:
        ty, sp = self.ty, self.sp
        bold = _is_bold(self.r, n)
        v = n.visual
        label_w = label_h = 0.0
        has_below = v in ("tensor", "tokens", "image", "icon", "stack", "glyph") and bool(n.label)
        size = tuple(n.size) if n.size else None  # final drawing units (not scaled by the text fit)
        if v == "chip":  # as small as its text: glued pieces of one input ([d | x])
            tw, th = measure(n.label, ty["size"], bold, ty["family"])
            w, h = tw + 2 * 5 * self.ink, max(th + 2 * sp["node_pad_y"], sp["min_node_h"] * 0.75)
        elif v == "box":
            tw, th = measure(n.label, ty["size"], bold, ty["family"])
            padx = sp["node_pad_x"]
            if n.badges:  # badges sit inside the top-right corner: keep the centred text clear of them
                padx = max(padx, BADGE_SIZE * self.ink + BADGE_CLEAR + 2)
            w, h = max(sp["min_node_w"], tw + 2 * padx), max(sp["min_node_h"], th + 2 * sp["node_pad_y"])
        elif v == "placeholder":
            tw, th = measure(placeholder_text(n), ty["small_size"], False, ty["family"])
            L = self.r["image"]["default_long_side"]
            w, h = size if size else (L, 0.75 * L)
            w, h = max(w, tw + 2 * sp["node_pad_x"]), max(h, th + 2 * sp["node_pad_y"])
        elif v == "text":
            tw, th = measure(n.label, ty["small_size"], bold and n.role != "annotation", ty["family"])
            w, h = tw + 6, th + 4
        elif v == "textcard":  # an example message / prompt / tool call, left-aligned in a card
            fam = "Courier New" if n.card_style == "code" else ty["family"]
            tw, th = measure(n.label, ty["small_size"], False, fam)
            padx, pady = sp["node_pad_x"], sp["node_pad_y"]
            w, h = tw + 2 * padx + 2, th + 2 * pady
            if "$" in (n.label or "").replace("\\$", ""):  # a math card wraps (styles): room so no line breaks —
                import re  # only the MathJax part's width is an estimate; the text font's metrics are exact
                mw = sum(measure(f"${m}$", ty["small_size"], False, fam)[0]
                         for m in re.findall(r"(?<!\\)\$(.+?)(?<!\\)\$", n.label))
                w += 0.08 * mw + 2 * self.ink  # MATH_WIDTH is already generous: no slack wrapped nothing (Reflexion)
            if n.card_style == "bubble":
                h += BUBBLE_TAIL * self.ink
            elif n.card_style == "quote":  # a dashed border reads heavier: room under the role line (v4 run)
                h += 0.6 * pady
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
            if size:
                hw, hh = size
                w, h = (hw, hw / a) if hw / a <= hh else (hh * a, hh)
            else:
                L = self.r["image"]["default_long_side"]
                w, h = (L, L / a) if a >= 1 else (L * a, L)
        elif v == "icon":
            w = h = ICON_SIZE * self.ink
        elif v == "glyph":
            from .glyphs import DEFAULT_SIZE
            w, h = size if size else tuple(x * self.ink for x in DEFAULT_SIZE.get(n.glyph, (48, 48)))
            if n.glyph == "pair-matrix" and getattr(n, "axes", None):  # named rows / columns at the label size
                from .glyphs import GRIDDED, pair_matrix_min_size
                mw, mh = pair_matrix_min_size(tuple(n.grid or GRIDDED["pair-matrix"]), ty["small_size"])
                w, h = max(w, mw), max(h, mh)
        else:  # pragma: no cover - schema forbids
            raise LayoutError(f"'{n.id}': unknown visual {v}")
        if size and v in ("tensor", "stack"):  # exact: feature maps taper with resolution
            w, h = max(size[0], 6 * self.ink), max(size[1], 6 * self.ink)
        elif size and v not in ("image", "placeholder", "glyph"):  # text must still fit: a size only enlarges
            w, h = max(w, size[0]), max(h, size[1])
            if v == "op":
                w = h = max(w, h)
        if v in RESIZABLE:  # routing asked for a longer side: its ports sit two arrowheads apart (solve_and_route)
            w = max(w, self.extra.get((n.id, "min_w"), 0.0))
            h = max(h, self.extra.get((n.id, "min_h"), 0.0))
        if has_below:
            label_w, label_h = measure(n.label, ty["small_size"], False, ty["family"])
        side = self.extra.get((n.id, "label_side"), "below") if has_below else "below"
        dx = None
        if has_below and v == "glyph" and n.glyph == "pair-matrix":  # the name under the cells, clear of the row
            from .glyphs import GRIDDED, pair_matrix_header  # names where the image-side line enters from below
            hw = pair_matrix_header(w, h, tuple(n.grid or GRIDDED["pair-matrix"]), getattr(n, "axes", None),
                                    ty["small_size"])
            dx = hw + max(0.0, (w - hw - label_w) / 2)
        return _M(w, h, label_w, label_h, label_side=side, _gap=sp["label_gap"], label_dx=dx)

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
            self._fill_spans(g, cols, rows, gap)
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

    FILL = ("box", "trapezoid", "textcard")  # canvas: these stretch to their span; data-shaped visuals keep their size

    def _fill_spans(self, g: Group, cols: list, rows: list, gap: float):
        """A canvas span is the block's share of the figure: box-like children and framed groups fill it. In a grid,
        a box spanning several rows (columns) covers them — a tower facing a column of loss boxes, an embedding
        feeding the rows it spans — so each line to a row is one short straight run; single-track spans keep
        their size."""
        canvas = g.layout.type == "canvas"
        for c in g.children:
            if c.place == "free":
                continue
            m = self.m[c.id]
            if c.is_group and c.frame == "none":
                continue
            if not c.is_group and (c.visual not in self.FILL or m.label_h):
                continue
            sw = self._span(g, "col", cols, c.cell[1], c.span[1], gap)
            sh = self._span(g, "row", rows, c.cell[0], c.span[0], gap)
            dw = max(0.0, sw - m.shape_w) if canvas or c.span[1] > 1 else 0.0
            dh = max(0.0, sh - m.shape_h) if c.span[0] > 1 else 0.0
            m.shape_w += dw
            m.shape_h += dh
            if c.is_group:
                m.inner_w += dw

    CANVAS_GUTTER = 0.4  # canvas columns: a boundary no edge crosses gets this share of the gap

    def _tgap(self, g: Group, axis: str, i: int, gap: float) -> float:
        base = gap
        if axis == "col" and g.layout.type == "canvas" and (g.id, i) not in self.canvas_links:
            base = gap * self.CANVAS_GUTTER
        return max(base, self.grid_gap.get((g.id, axis, i), 0.0))

    def _span(self, g: Group, axis: str, tracks: list, start: int, n: int, gap: float) -> float:
        return sum(tracks[start : start + n]) + sum(self._tgap(g, axis, i, gap) for i in range(start, start + n - 1))

    def _grid_tracks(self, g: Group, gap: float):
        nr = max(c.cell[0] + c.span[0] for c in g.children)
        nc = max(c.cell[1] + c.span[1] for c in g.children)
        if g.layout.type == "canvas":
            nc = max(nc, g.layout.cols)
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
        if g.layout.type == "canvas":  # equal columns: the narrowest pitch at which every child's span holds it
            unit, by = 0.0, None
            for c in tracked:
                fw, _ = self.foot(c.id)
                inner = sum(self._tgap(g, "col", i, gap) for i in range(c.cell[1], c.cell[1] + c.span[1] - 1))
                if (fw - inner) / c.span[1] > unit:
                    unit, by = (fw - inner) / c.span[1], c.id
            cols = [unit] * nc
            pitch = getattr(self.bp, "canvas_pitch", None)
            if pitch is None:
                pitch = self.bp.canvas_pitch = {}
            pitch[g.id] = (unit, by, nc)  # the child that sets every column's width (reported by the grammar lint)
        for c in tracked:  # spans: distribute any deficit evenly
            fw, fh = self.foot(c.id)
            if c.span[1] > 1 and g.layout.type != "canvas":
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
            fw, fh = self.foot(el.id)
            lb = None
            if m.label_h and m.label_side == "top":  # name above the shape
                gap = self.sp["label_gap"]
                lb = Box(x + (fw - m.label_w) / 2, y, m.label_w, m.label_h)
                box = Box(x + (fw - m.shape_w) / 2, y + m.label_h + gap, m.shape_w, m.shape_h)
            elif m.label_h and m.label_side != "below":  # name beside the shape, centred on it
                gap = self.sp["label_gap"]
                sx = x if m.label_side == "right" else x + m.label_w + gap
                box = Box(sx, y + (fh - m.shape_h) / 2, m.shape_w, m.shape_h)
                lx = box.right + gap if m.label_side == "right" else x
                lb = Box(lx, box.cy - m.label_h / 2, m.label_w, m.label_h)
            else:
                if m.label_h and m.label_dx is not None:  # shape at the footprint's left, name after its row names
                    box = Box(x, y, m.shape_w, m.shape_h)
                    lb = Box(x + m.label_dx, box.bottom + self.sp["label_gap"], m.label_w, m.label_h)
                else:
                    box = Box(x + (fw - m.shape_w) / 2, y, m.shape_w, m.shape_h)
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
    _apply_align(bp, s.out)
    _apply_pins(bp, s.out)
    return s.out


def _apply_pins(bp: Blueprint, out: dict):
    """pin [dx, dy]: the author's hand move (absorbed from draw.io) — the element and everything in it shift after
    layout and alignment; routing runs afterwards, and lint judges the result like any other."""
    for el in bp.index.values():
        pin = getattr(el, "pin", None)
        if not pin or el.id == bp.root.id:
            continue
        moved = _shift(out[el.id], float(pin[0]), float(pin[1])).footprint
        pid = bp.parent.get(el.id)
        if pid is not None:
            par = bp.index[pid]
            if pid != bp.root.id and par.frame != "none" and not out[pid].box.contains(moved, eps=0.5):
                raise LayoutError(f"the pin of '{el.id}' (a hand move absorbed from draw.io) puts it outside '{pid}' — "
                                  f"move '{pid}' itself, or keep '{el.id}' inside its frame")
            for sib in par.children:
                if sib.id != el.id and moved.intersects(out[sib.id].footprint, eps=0.5):
                    raise LayoutError(f"the pin of '{el.id}' (a hand move absorbed from draw.io) puts it on '{sib.id}' — "
                                      "move it to free space in draw.io and absorb again, or remove the pin")
        for x in _subtree(bp, el.id):
            out[x] = _shift(out[x], float(pin[0]), float(pin[1]))


def _subtree(bp: Blueprint, eid: str) -> list[str]:
    out, stack = [], [eid]
    while stack:
        x = stack.pop()
        out.append(x)
        el = bp.index[x]
        if el.is_group:
            stack.extend(c.id for c in el.children)
    return out


def _shift(p: Placed, dx: float, dy: float) -> Placed:
    mv = lambda b: None if b is None else Box(b.x + dx, b.y + dy, b.w, b.h)
    return Placed(p.elem, mv(p.box), mv(p.label_box), mv(p.title_box), mv(p.title_text),
                  None if p.axis_y is None else p.axis_y + dy)


def _apply_align(bp: Blueprint, out: dict):
    """align_x / align_y: after layout, shift an element and everything in it so its alignment point (a group's
    axis_of child, else its own centre) lines up with another node — the way to line up nodes that sit in
    different frames. A shift that would leave the parent or hit a sibling stops the build with the reason."""
    def point(eid):
        el = bp.index[eid]
        ref = el.axis_of if el.is_group and getattr(el, "axis_of", None) else eid
        return out[ref].box.cx, out[ref].axis[1]

    aligned = [el for el in bp.index.values() if getattr(el, "align_x", None) or getattr(el, "align_y", None)]
    ids_aligned = {el.id for el in aligned}

    def deps(el):  # what must already sit in its final place: the targets, and any aligned frame around a target
        out_ = set()
        for t in (getattr(el, "align_x", None), getattr(el, "align_y", None)):
            if t:
                out_ |= ({t} | set(bp.ancestors(t))) & ids_aligned
        return out_ - {el.id}
    order, done, visiting = [], set(), set()

    def visit(el):  # targets first (GraphSAGE blind run: a chained align resolved against the old position)
        if el.id in done:
            return
        if el.id in visiting:
            raise LayoutError(f"align of '{el.id}' is part of a cycle (each waits for the other) — align both to one node")
        visiting.add(el.id)
        for d in sorted(deps(el)):
            visit(bp.index[d])
        visiting.discard(el.id)
        done.add(el.id)
        order.append(el)
    for el in aligned:
        visit(el)
    for el in order:
        ax, ay = getattr(el, "align_x", None), getattr(el, "align_y", None)
        px, py = point(el.id)
        dx = (point(ax)[0] - px) if ax else 0.0
        dy = (point(ay)[1] - py) if ay else 0.0
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            continue
        ids = _subtree(bp, el.id)
        moved = _shift(out[el.id], dx, dy).footprint
        pid = bp.parent.get(el.id)
        if pid is not None:
            par = bp.index[pid]
            if not out[pid].box.contains(moved, eps=1.5):  # a pixel of rounding is not "outside"
                raise LayoutError(f"align of '{el.id}' to '{ax or ay}' would move it outside '{pid}' by "
                                  f"{max(abs(dx), abs(dy)):.0f}px — give '{pid}' room (wider siblings, a free cell) or drop the align")
            for sib in par.children:
                if sib.id != el.id and moved.intersects(out[sib.id].footprint, eps=0.5):
                    raise LayoutError(f"align of '{el.id}' to '{ax or ay}' would overlap '{sib.id}' — reorder, add a gap "
                                      "or drop the align")
        for x in ids:
            out[x] = _shift(out[x], dx, dy)



def _check_free(bp: Blueprint, out: dict, recipe: Recipe):
    """A free-placed child must not collide with its siblings (keep a small gap)."""
    gap = recipe["spacing"]["gap"]["tight"] / 2
    for g in bp.groups():
        if g.layout.type not in GRIDLIKE:
            continue
        for c in g.children:
            if c.place != "free":
                continue
            fb = out[c.id].footprint.inflate(gap)
            for o in g.children:
                if o.id != c.id and fb.intersects(out[o.id].footprint):
                    raise LayoutError(f"free-placed '{c.id}' overlaps '{o.id}' in grid '{g.id}': move it to another cell")
