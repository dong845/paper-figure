"""Orthogonal, obstacle-avoiding edge router (spec §4 ⑤ 走线).

Routes are computed here — not left to drawio's runtime router — so that the
mechanical lint can check the exact polylines that get drawn. Each edge is an
A* search over a sparse grid built from obstacle borders, port lines and the
mid-lines of the gaps between them. Cost = length + bends + crossings +
collinear overlap with previously routed edges.
"""
from __future__ import annotations

import heapq
from bisect import bisect_left
from dataclasses import dataclass

from .blueprint import Blueprint
from .errors import RouteError
from .geometry import Box
from .measure import measure
from .layout import Placed
from .styles import Recipe

DIRS = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}
OPP = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}
BEND, CROSS, OVERLAP, NEAR = 24.0, 60.0, 400.0, 30.0
GEOM_EPS = 1e-6  # boundary tolerance: stubs computed along different float paths land "on" obstacle edges
MARGINS = (14.0, 10.0, 7.0, 4.0, 2.0)  # clearance between routed lines and boxes
KIND_ORDER = {"data": 0, "skip": 1, "train_only": 2, "infer_only": 2, "grad": 3, "control": 3, "loss": 4}
PORT_INSET = 6.0  # keep ports away from rounded corners
_TIP = 6.0  # arrowhead size of the figure being routed (route_all sets it from the recipe)
HUG_W = 1.0  # cost per px of line running within one arrowhead of a box it does not connect
_NEAR: dict = {}  # edge id -> boxes it does not connect (route_all sets it per figure)
_HEADS: dict = {}  # edge id -> (arrowhead at the source, arrowhead at the target)
_LABELS: dict = {}  # edge id -> box of its label as placed so far (other lines keep out of it)
_LABEL_SIZE: dict = {}  # edge id -> measured label (w, h)
HEAD_DRAWN = 1.4  # draw.io draws a block arrowhead this many endSizes long (measured: 10 px for endSize 7.2)
END_RUN = HEAD_DRAWN + 1.5  # endSizes of straight line an arrow end keeps in its own direction: the drawn head plus
# a visible shaft of 1.5 endSizes
PARALLEL = 1.5  # two lines closer than this many arrowheads read as one thick line


def _port_sep() -> float:
    """Ports on one side sit two arrowheads apart: their heads never touch and their lines stay apart."""
    return max(PORT_SEP, 2.0 * _TIP)


def _label_box(eid, pts):
    """Where the drawing puts an edge's label: the middle of its longest segment (drawio.label_position)."""
    if eid not in _LABEL_SIZE or len(pts) < 2:
        return None
    k = max(range(len(pts) - 1), key=lambda i: abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1]))
    (x1, y1), (x2, y2) = pts[k], pts[k + 1]
    w, h = _LABEL_SIZE[eid]
    return Box((x1 + x2) / 2 - w / 2 - 2, (y1 + y2) / 2 - h / 2 - 2, w + 4, h + 4)


def _place_label(eid, pts):
    b = _label_box(eid, pts)
    if b is not None:
        _LABELS[eid] = b


@dataclass
class Route:
    edge_id: str
    points: list[tuple[float, float]]
    src_side: str
    dst_side: str
    label_t: float | None = None  # where its label sits, as a fraction of the path length (_place_labels)
    free_end: bool = False  # a bundle branch ending on the shared trunk: drawn without a head (one head per trunk)
    label_off: tuple | None = None  # label offset from its point on the line (beside the line, not on it)

    @property
    def segments(self):
        return list(zip(self.points, self.points[1:]))


def _simplify(pts):
    out = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-6 and abs(out[-1][1] - p[1]) < 1e-6:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 1e-6 and abs(b[0] - c[0]) < 1e-6) or (abs(a[1] - b[1]) < 1e-6 and abs(b[1] - c[1]) < 1e-6):
            out.pop(i)
        else:
            i += 1
    return out


class _Routed:
    """Index of already-routed segments for crossing/overlap penalties."""

    def __init__(self):
        self.h: list[tuple[float, float, float, str, float, float]] = []  # y, x1, x2, edge, reach below/above x1/x2
        self.v: list[tuple[float, float, float, str, float, float]] = []  # x, y1, y2, edge, reach

    def add(self, pts, eid):
        n = len(pts) - 1
        for k, ((x1, y1), (x2, y2)) in enumerate(zip(pts, pts[1:])):
            # a line ending at a box carries an arrowhead (or a port) there: passing within one head of that end
            # touches it, so it costs as a crossing (STORM: s_t->actor slid 3 px under the critic, past the tip
            # of the loss arrow ending there, and was cheaper than a clean crossing)
            lo_end, hi_end = (k == 0), (k == n - 1)
            if abs(y1 - y2) < 1e-9:
                ra = _TIP if (lo_end if x1 <= x2 else hi_end) else 0.0
                rb = _TIP if (hi_end if x1 <= x2 else lo_end) else 0.0
                self.h.append((y1, min(x1, x2), max(x1, x2), eid, ra, rb))
            else:
                ra = _TIP if (lo_end if y1 <= y2 else hi_end) else 0.0
                rb = _TIP if (hi_end if y1 <= y2 else lo_end) else 0.0
                self.v.append((x1, min(y1, y2), max(y1, y2), eid, ra, rb))

    def _sorted(self):
        """h sorted by y and v by x (rebuilt after adds): a query bisects to the segments near it."""
        if getattr(self, "_n", None) != (len(self.h), len(self.v)):
            self._hs = sorted(self.h)
            self._vs = sorted(self.v)
            self._hk = [t[0] for t in self._hs]
            self._vk = [t[0] for t in self._vs]
            self._n = (len(self.h), len(self.v))
        return self._hs, self._hk, self._vs, self._vk

    def penalty(self, p, q) -> float:
        (x1, y1), (x2, y2) = p, q
        cost = 0.0
        near = max(5.0, PARALLEL * _TIP)  # parallel lines this close read as one thick line: cost per px of run
        hs, hk, vs, vk = self._sorted()
        if abs(y1 - y2) < 1e-9:
            lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
            for k in range(bisect_left(vk, lo + 0.5), bisect_left(vk, hi - 0.5)):  # verticals strictly inside
                (x, a, b, _, ra, rb) = vs[k]
                if lo + 0.5 < x < hi - 0.5 and a + 0.5 - ra < y1 < b - 0.5 + rb:
                    cost += CROSS
            for k in range(bisect_left(hk, y1 - near), bisect_left(hk, y1 + near)):  # horizontals within reach
                (y, a, b, _, _ra, _rb) = hs[k]
                ov = min(hi, b) - max(lo, a)
                if ov > 0.5:
                    d = abs(y - y1)
                    if d < 0.5:
                        cost += OVERLAP + 4 * ov
                    elif d < near:
                        cost += NEAR + 2.0 * ov
        else:
            lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
            for k in range(bisect_left(hk, lo + 0.5), bisect_left(hk, hi - 0.5)):
                (y, a, b, _, ra, rb) = hs[k]
                if lo + 0.5 < y < hi - 0.5 and a + 0.5 - ra < x1 < b - 0.5 + rb:
                    cost += CROSS
            for k in range(bisect_left(vk, x1 - near), bisect_left(vk, x1 + near)):
                (x, a, b, _, _ra, _rb) = vs[k]
                ov = min(hi, b) - max(lo, a)
                if ov > 0.5:
                    d = abs(x - x1)
                    if d < 0.5:
                        cost += OVERLAP + 4 * ov
                    elif d < near:
                        cost += NEAR + 2.0 * ov
        return cost


def _lines(vals, lo_pad):
    """Sorted candidate coordinates (exact values, deduplicated within 1e-6) plus gap mid-lines and an outer ring."""
    vals = sorted(vals)
    uniq = []
    for v in vals:
        if not uniq or v - uniq[-1] > 1e-6:
            uniq.append(v)
    mids = [(a + b) / 2 for a, b in zip(uniq, uniq[1:]) if b - a > 4]
    allv = sorted(uniq + mids)
    return [allv[0] - lo_pad] + allv + [allv[-1] + lo_pad]


def _index_of(lines, v):
    k = bisect_left(lines, v - 1e-6)
    if k < len(lines) and abs(lines[k] - v) <= 1e-6:
        return k
    raise AssertionError(f"coordinate {v} missing from candidate lines")


def find_path(edge_id, start, start_dir, goal, goal_dir, obstacles: list[Box], routed, extra_x=(), extra_y=()):
    """Orthogonal path from `start` (leaving towards start_dir) to `goal` (arriving while moving in goal_dir)."""
    return find_path_cost(edge_id, start, start_dir, goal, goal_dir, obstacles, routed, extra_x, extra_y)[0]


def _border_penalty(p, q, borders) -> float:
    if not borders:
        return 0.0
    vert = abs(p[0] - q[0]) < 1e-9
    coord = p[0] if vert else p[1]
    a0, a1 = sorted((p[1], q[1]) if vert else (p[0], q[0]))
    cost = 0.0
    for o, c, lo, hi in borders:
        if (o == "v") != vert:
            continue
        if abs(coord - c) < BORDER_CLEAR and min(a1, hi) - max(a0, lo) > 2:
            cost += BORDER_PENALTY + 0.5 * (min(a1, hi) - max(a0, lo))
    return cost


def find_path_cost(edge_id, start, start_dir, goal, goal_dir, obstacles: list[Box], routed, extra_x=(), extra_y=(), borders=(),
                   near=()):
    """`near`: boxes the line does not connect; running within one arrowhead of them costs per px, so among equal
    routes the search takes the one in the middle of a gap, not the one skimming a box."""
    routed = routed if isinstance(routed, _Routed) else _Routed()
    for b in obstacles:
        if b.contains_point(*start, eps=GEOM_EPS) or b.contains_point(*goal, eps=GEOM_EPS):
            raise RouteError(edge_id, "an endpoint lies inside an obstacle (elements too close)")
    xs = _lines([start[0], goal[0], *extra_x] + [b.x for b in obstacles] + [b.right for b in obstacles], 40)
    ys = _lines([start[1], goal[1], *extra_y] + [b.y for b in obstacles] + [b.bottom for b in obstacles], 40)
    s = (_index_of(xs, start[0]), _index_of(ys, start[1]))
    g = (_index_of(xs, goal[0]), _index_of(ys, goal[1]))
    D = 0.01

    obs_t = [(b.x + GEOM_EPS, b.y + GEOM_EPS, b.right - GEOM_EPS, b.bottom - GEOM_EPS) for b in obstacles]
    CELL = 48.0  # obstacles bucketed on a coarse grid: a point is tested against its bucket only
    buckets: dict = {}
    for t in obs_t:
        for cx in range(int(t[0] // CELL), int(t[2] // CELL) + 1):
            for cy in range(int(t[1] // CELL), int(t[3] // CELL) + 1):
                buckets.setdefault((cx, cy), []).append(t)
    empty: list = []

    def inside_any(x, y):  # = any(b.contains_point(x, y, eps=GEOM_EPS)), on plain tuples (the search's hot loop)
        for x0, y0, x1, y1 in buckets.get((int(x // CELL), int(y // CELL)), empty):
            if x0 < x < x1 and y0 < y < y1:
                return True
        return False
    near_t = _hug_prep(near) if near else None

    def blocked_pt(x, y):
        # interior of the union of obstacles: also catches seams between touching obstacles
        if inside_any(x, y):
            return True
        return all(inside_any(x + sx * D, y + sy * D) for sx in (-1, 1) for sy in (-1, 1))

    seg_cache: dict = {}
    pen_cache: dict = {}

    def seg_ok(i1, j1, i2, j2):
        k = (i1, j1, i2, j2) if (i1, j1) <= (i2, j2) else (i2, j2, i1, j1)
        if k not in seg_cache:
            mx, my = (xs[i1] + xs[i2]) / 2, (ys[j1] + ys[j2]) / 2
            if j1 == j2:  # horizontal: blocked if obstacle material on both sides of the line
                seam = inside_any(mx, my - D) and inside_any(mx, my + D)
            else:
                seam = inside_any(mx - D, my) and inside_any(mx + D, my)
            seg_cache[k] = not (inside_any(mx, my) or seam or blocked_pt(xs[i2], ys[j2]))
        return seg_cache[k]

    def h(i, j):
        return abs(xs[i] - goal[0]) + abs(ys[j] - goal[1])

    start_state = (s[0], s[1], start_dir)
    dist = {start_state: 0.0}
    prev: dict = {}
    pq = [(h(*s), 0.0, start_state)]
    end_state = None
    while pq:
        f, cst, st = heapq.heappop(pq)
        if cst > dist.get(st, float("inf")) + 1e-9:
            continue
        i, j, d = st
        if (i, j) == g:
            if d == goal_dir:
                end_state = st
                break
            if d != OPP[goal_dir]:
                fin = (i, j, goal_dir)
                nc = cst + BEND
                if nc < dist.get(fin, float("inf")):
                    dist[fin] = nc
                    prev[fin] = st
                    heapq.heappush(pq, (nc, nc, fin))
            continue
        for nd, (dx, dy) in DIRS.items():
            if nd == OPP[d]:
                continue
            ni, nj = i + dx, j + dy
            if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                continue
            if not seg_ok(i, j, ni, nj):
                continue
            p, q = (xs[i], ys[j]), (xs[ni], ys[nj])
            sk = (i, j, ni, nj) if (i, j) <= (ni, nj) else (ni, nj, i, j)
            pen = pen_cache.get(sk)
            if pen is None:  # the same grid segment is reached from several directions: score it once
                pen = routed.penalty(p, q) + _border_penalty(p, q, borders) + (HUG_W * _hug_seg(p, q, near_t) if near_t else 0.0)
                pen_cache[sk] = pen
            nc = cst + abs(q[0] - p[0]) + abs(q[1] - p[1]) + (BEND if nd != d else 0.0) + pen
            ns = (ni, nj, nd)
            if nc < dist.get(ns, float("inf")) - 1e-9:
                dist[ns] = nc
                prev[ns] = st
                heapq.heappush(pq, (nc + h(ni, nj), nc, ns))
    if end_state is None:
        raise RouteError(edge_id, "no obstacle-free orthogonal path")
    pts, st = [], end_state
    while True:
        pts.append((xs[st[0]], ys[st[1]]))
        if st == start_state:
            break
        st = prev[st]
    return _simplify(list(reversed(pts))), dist[end_state]


# ---------------------------------------------------------------- ports
def _sides_auto(a: Box, b: Box) -> tuple[str, str]:
    h_sep = b.x >= a.right or a.x >= b.right
    v_sep = b.y >= a.bottom or a.y >= b.bottom
    if h_sep and v_sep:  # diagonal neighbours: one elbow, vertical leg attached to the upper box
        right = b.x >= a.right
        if b.y >= a.bottom:  # dst lower: leave the upper src downwards
            return "bottom", ("left" if right else "right")
        return ("right" if right else "left"), "bottom"  # dst upper: enter it from below
    if b.x >= a.right:
        return "right", "left"
    if a.x >= b.right:
        return "left", "right"
    if b.y >= a.bottom:
        return "bottom", "top"
    if a.y >= b.bottom:
        return "top", "bottom"
    dx, dy = b.cx - a.cx, b.cy - a.cy
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def _side_span(pl: Placed, side: str, inset: float = PORT_INSET) -> tuple[float, float, float]:
    """(fixed coordinate, span lo, span hi) of a side; bottom uses the footprint (below-label).
    Ports stay `inset` away from the corners so they never sit on a rounded corner."""
    b = pl.box
    inset_h = min(inset, b.h / 4)
    inset_w = min(inset, b.w / 4)
    if side == "left":
        return b.x, b.y + inset_h, b.bottom - inset_h
    if side == "right":
        return b.right, b.y + inset_h, b.bottom - inset_h
    if side == "top":
        above = pl.label_box is not None and pl.label_box.bottom <= b.y + 0.5
        return (pl.footprint.y if above else b.y), b.x + inset_w, b.right - inset_w
    below = pl.label_box is not None and pl.label_box.y >= b.bottom - 0.5  # a name beside the shape is not in the way
    return (pl.footprint.bottom if below else b.bottom), b.x + inset_w, b.right - inset_w


def _under_label(pl: Placed, side: str, v: float) -> bool:
    """A bottom port at coordinate v would sit under the element's below-shape name (the line grows out of the
    text — user, round 2)."""
    lb = pl.label_box
    if side != "bottom" or lb is None or lb.y < pl.box.bottom - 0.5:
        return False
    g = 0.5 * _TIP
    return lb.x - g < v < lb.right + g


def _attach_bottom(pl: Placed, side: str, pt):
    """A bottom port beside a below-shape name leaves the shape itself (not the footprint under the name)."""
    if side == "bottom" and pl.label_box is not None and pl.label_box.y >= pl.box.bottom - 0.5 \
            and not _under_label(pl, side, pt[0]):
        return (pt[0], pl.box.bottom)
    return pt


def _on_shape(pl: Placed, side: str, pt: tuple[float, float]) -> tuple[float, float]:
    """Move a side port onto the drawn outline (op nodes are circles, trapezoids have slanted edges)."""
    vis = getattr(pl.elem, "visual", None)
    if vis == "trapezoid":
        from .shapes import TRAPEZOID_SIZE, trapezoid_bottom, trapezoid_top
        b, taper = pl.box, pl.elem.taper
        if taper in ("up", "down"):  # slanted left/right sides, flat top and bottom
            if side in ("left", "right"):
                from .shapes import trapezoid_side_x
                return (trapezoid_side_x(b, taper, side, pt[1]), pt[1])
            narrow = (side == "top") == (taper == "up")
            if narrow:  # the short end: keep the port within its width
                cut = TRAPEZOID_SIZE * b.w
                return (min(b.right - cut - 2, max(b.x + cut + 2, pt[0])), pt[1])
            return pt
        if side == "top":
            return (pt[0], trapezoid_top(b, taper, pt[0]))
        if side == "bottom":
            return (pt[0], trapezoid_bottom(b, taper, pt[0]))
        narrow = (side == "right") == (taper == "in")
        if narrow:  # the short end: keep the port within its height
            cut = TRAPEZOID_SIZE * b.h
            return (pt[0], min(b.bottom - cut - 2, max(b.y + cut + 2, pt[1])))
        return pt
    if vis != "op":
        return pt
    cx, cy, r = pl.box.cx, pl.box.cy, pl.box.w / 2
    if side in ("left", "right"):
        dy = max(-0.92 * r, min(0.92 * r, pt[1] - cy))
        dx = (r * r - dy * dy) ** 0.5
        return (cx - dx if side == "left" else cx + dx, cy + dy)
    dx = max(-0.92 * r, min(0.92 * r, pt[0] - cx))
    dy = (r * r - dx * dx) ** 0.5
    return (cx + dx, cy - dy if side == "top" else cy + dy)


def _port_point(pl: Placed, side: str, t: float) -> tuple[float, float]:
    fixed, lo, hi = _side_span(pl, side)
    v = lo + (hi - lo) * t if hi > lo else (lo + hi) / 2
    return (fixed, v) if side in ("left", "right") else (v, fixed)


PORT_SEP = 10.0


def _walls(b: Box, t: float) -> list[Box]:
    """Thin obstacles along a container's frame: lines inside it keep clear of the border."""
    return [Box(b.x - t, b.y - t, b.w + 2 * t, 2 * t), Box(b.x - t, b.bottom - t, b.w + 2 * t, 2 * t),
            Box(b.x - t, b.y - t, 2 * t, b.h + 2 * t), Box(b.right - t, b.y - t, 2 * t, b.h + 2 * t)]


def detours(bp: Blueprint, placed: dict[str, Placed]) -> list[tuple[str, str, str]]:
    """(edge id, lowest common ancestor group, side) for edges that go around obstacles via one side."""
    out = []
    sides = _all_sides(bp, placed)
    for e in bp.edges:
        ss, ds = sides[e.id]
        if ss == ds:
            a = bp.ancestors(e.src)
            b = set(bp.ancestors(e.dst))
            lca = next((g for g in a if g in b), bp.root.id)
            out.append((e.id, lca, ss))
    return out


def _blockers(bp: Blueprint, placed: dict[str, Placed], e) -> list[Box]:
    """Boxes an edge must not pass through (endpoints and their ancestors excluded)."""
    ends = {e.src, e.dst}
    anc = set(bp.ancestors(e.src)) | set(bp.ancestors(e.dst))
    out = []
    for el in bp.index.values():
        if el.id in ends or el.id in anc:
            continue
        if el.is_group and (el.frame == "none" or any(el.id in bp.ancestors(x) for x in ends)):
            continue
        if not el.is_group and any(g in bp.ancestors(el.id) for g in ends):
            continue  # children of an endpoint container are inside it
        out.append(placed[el.id].footprint)
    return out


def _choose_sides(bp, placed, e, used: dict | None = None) -> tuple[str, str]:
    """Sides for an edge. Blocked straight corridors detour via a common side; that side is chosen
    to avoid (1) sides other edges already attach to (would force crossings), (2) bottom ports under
    below-labels, then (3) the shorter detour."""
    used = used or {}
    a, b = placed[e.src].footprint, placed[e.dst].footprint
    sa, sb = _sides_auto(a, b)

    def busy(side):
        return used.get((e.src, side), 0) + used.get((e.dst, side), 0)
    if e.src_side != "auto" or e.dst_side != "auto":
        return (e.src_side if e.src_side != "auto" else sa, e.dst_side if e.dst_side != "auto" else sb)
    blockers = _blockers(bp, placed, e)
    if sa in ("left", "right"):
        lo, hi = max(a.y, b.y), min(a.bottom, b.bottom)
        x0, x1 = (a.right, b.x) if sa == "right" else (b.right, a.x)
        if hi - lo < 1 or x1 <= x0:
            return sa, sb
        corridor = Box(x0, lo, x1 - x0, hi - lo)
        hits = [k for k in blockers if k.intersects(corridor, eps=0.5)]
        if not hits:
            return sa, sb
        down = max(k.bottom for k in hits) - max(a.bottom, b.bottom) + 1e4 * busy("bottom")
        up = min(a.y, b.y) - min(k.y for k in hits) + 1e4 * busy("top")
        if placed[e.src].label_box is not None or placed[e.dst].label_box is not None:
            down += 1e6  # a bottom port would start/end under the label below the shape
        return ("bottom", "bottom") if down <= up else ("top", "top")
    lo, hi = max(a.x, b.x), min(a.right, b.right)
    y0, y1 = (a.bottom, b.y) if sa == "bottom" else (b.bottom, a.y)
    if hi - lo < 1 or y1 <= y0:
        return sa, sb
    corridor = Box(lo, y0, hi - lo, y1 - y0)
    hits = [k for k in blockers if k.intersects(corridor, eps=0.5)]
    if not hits:
        return sa, sb
    right = max(k.right for k in hits) - max(a.right, b.right) + 1e4 * busy("right")
    left = min(a.x, b.x) - min(k.x for k in hits) + 1e4 * busy("left")
    return ("right", "right") if right <= left else ("left", "left")


def _assign_ports(bp, placed, sides, recipe=None) -> dict[tuple[str, str], tuple[float, float]]:
    """Per (element, side): each edge wants the coordinate that makes it straight towards the
    other endpoint; edges are placed in priority order (data first) at the nearest coordinate
    keeping PORT_SEP from ports already on that side. Falls back to even spreading."""
    buckets: dict[tuple[str, str], list] = {}
    for e in bp.edges:
        ss, ds = sides[e.id]
        buckets.setdefault((e.src, ss), []).append((e, "src", e.dst))
        buckets.setdefault((e.dst, ds), []).append((e, "dst", e.src))
    coord: dict[tuple[str, str], float] = {}
    rad = 0.0
    if recipe is not None:
        rad = max(recipe["shape"]["radius"], recipe["shape"]["group_radius"])
    inset = max(PORT_INSET, rad + 4)
    spans = {k: _side_span(placed[k[0]], k[1], inset) for k in buckets}
    straight: dict[str, float] = {}  # facing sides that overlap: one shared coordinate makes the edge straight
    for e in bp.edges:
        ss, ds = sides[e.id]
        if OPP[ss] != ds or e.src == e.dst:
            continue
        _, alo, ahi = spans[(e.src, ss)]
        _, blo, bhi = spans[(e.dst, ds)]
        lo, hi = max(alo, blo), min(ahi, bhi)
        if hi < lo:
            continue
        i = 1 if ss in ("left", "right") else 0
        ac, bc = placed[e.src].axis[i], placed[e.dst].axis[i]
        if (ahi - alo) > (bhi - blo):  # aim at the centre of the smaller side
            ac, bc = bc, ac
        straight[e.id] = ac if lo <= ac <= hi else bc if lo <= bc <= hi else (lo + hi) / 2
    for (elem, side), lst in buckets.items():
        fixed, lo, hi = spans[(elem, side)]
        horiz = side in ("left", "right")
        own = placed[elem].axis[1] if horiz else placed[elem].axis[0]

        def pref(item, horiz=horiz, lo=lo, hi=hi, own=own, side=side):
            e = item[0]
            ss, ds = sides[e.id]
            if OPP[ss] != ds:  # same-side detour (e.g. bottom->bottom): attach near the middle
                c = own
            elif e.id in straight:
                c = straight[e.id]
            else:
                ax = placed[item[2]].axis
                c = ax[1] if horiz else ax[0]
            return min(hi, max(lo, c))

        order = sorted(lst, key=lambda it: (KIND_ORDER.get(it[0].kind, 5), abs(pref(it) - (lo + hi) / 2)))
        want_sep = _port_sep()
        sep = want_sep if (hi - lo) >= want_sep * (len(lst) - 1) else (hi - lo) / max(1, len(lst))
        taken: list[float] = []
        ok = True
        for it in order:
            want = pref(it)
            pl_e = placed[elem]
            cands = sorted({min(hi, max(lo, want + k * sep * s)) for k in range(0, 2 * len(lst) + 2) for s in (-1, 1)}
                           | ({min(hi, max(lo, pl_e.label_box.x - 0.5 * _TIP - 1)), min(hi, max(lo, pl_e.label_box.right + 0.5 * _TIP + 1))}
                              if side == "bottom" and pl_e.label_box is not None else set()),
                           key=lambda v: (_under_label(pl_e, side, v), abs(v - want), v))
            pick = next((v for v in cands if all(abs(v - t) >= sep - 1e-6 for t in taken)), None)
            if pick is None:
                ok = False
                break
            taken.append(pick)
            coord[(it[0].id, it[1])] = pick
        if ok and len(lst) > 1:  # the ports keep the far ends' order, or neighbouring lines cross right at the side
            vals = sorted(coord[(it[0].id, it[1])] for it in lst)
            far = sorted(lst, key=lambda it: (placed[it[2]].axis[1] if horiz else placed[it[2]].axis[0],
                                              coord[(it[0].id, it[1])]))
            for it, v in zip(far, vals):
                coord[(it[0].id, it[1])] = v
        if not ok:  # evenly spaced, ordered by the opposite endpoint: at the wanted spacing around the wanted
            srt = sorted(lst, key=lambda it: placed[it[2]].box.cy if horiz else placed[it[2]].box.cx)  # centre if
            n = len(lst)                                                                      # the side has room
            if n > 1 and (hi - lo) >= want_sep * (n - 1) - 1e-6:
                mid = sum(pref(it) for it in lst) / n
                first = min(hi - want_sep * (n - 1), max(lo, mid - want_sep * (n - 1) / 2))
                vals = [first + k * want_sep for k in range(n)]
            else:
                vals = [lo + (hi - lo) * (k + 1) / (n + 1) for k in range(n)] if n > 1 else [(lo + hi) / 2]
                if n > 1:
                    vals = [lo + (hi - lo) * k / (n - 1) for k in range(n)]  # the whole side: as far apart as it allows
            for it, v in zip(srt, vals):
                coord[(it[0].id, it[1])] = v
    ports = {}
    for e in bp.edges:
        ss, ds = sides[e.id]
        for end, elem, side in (("src", e.src, ss), ("dst", e.dst, ds)):
            fixed, _, _ = spans[(elem, side)]
            v = coord[(e.id, end)]
            ports[(e.id, end)] = (fixed, v) if side in ("left", "right") else (v, fixed)
        # both ports alone on facing sides: share one coordinate inside the overlap so the line is straight
        if len(buckets[(e.src, ss)]) == 1 and len(buckets[(e.dst, ds)]) == 1 and OPP[ss] == ds:
            _, alo, ahi = spans[(e.src, ss)]
            _, blo, bhi = spans[(e.dst, ds)]
            lo, hi = max(alo, blo), min(ahi, bhi)
            if hi >= lo:
                axa, axb = placed[e.src].axis, placed[e.dst].axis
                ac, bc = (axa[1], axb[1]) if ss in ("left", "right") else (axa[0], axb[0])
                if (ahi - alo) > (bhi - blo):  # aim at the centre of the smaller side
                    ac, bc = bc, ac
                v = ac if lo <= ac <= hi else bc if lo <= bc <= hi else (lo + hi) / 2
                under = [pl_ for pl_, sd in ((placed[e.src], ss), (placed[e.dst], ds)) if _under_label(pl_, sd, v)]
                if under:  # straight, but beside the name below the shape, not through it
                    lb = under[0].label_box
                    alts = [x for x in (lb.x - 0.5 * _TIP - 1, lb.right + 0.5 * _TIP + 1) if lo <= x <= hi
                            and not any(_under_label(pl_, sd, x) for pl_, sd in ((placed[e.src], ss), (placed[e.dst], ds)))]
                    if alts:
                        v = min(alts, key=lambda x: abs(x - v))
                pa, pb = ports[(e.id, "src")], ports[(e.id, "dst")]
                if ss in ("left", "right"):
                    ports[(e.id, "src")], ports[(e.id, "dst")] = (pa[0], v), (pb[0], v)
                else:
                    ports[(e.id, "src")], ports[(e.id, "dst")] = (v, pa[1]), (v, pb[1])
    for e in bp.edges:  # op nodes are circles: put their ports on the outline
        ss, ds = sides[e.id]
        ports[(e.id, "src")] = _on_shape(placed[e.src], ss, _attach_bottom(placed[e.src], ss, ports[(e.id, "src")]))
        ports[(e.id, "dst")] = _on_shape(placed[e.dst], ds, _attach_bottom(placed[e.dst], ds, ports[(e.id, "dst")]))
    return ports


def _l_alternative(ss, ds):
    """The other single-elbow route between diagonal neighbours (vertical-first <-> horizontal-first)."""
    vert = ("top", "bottom")
    if ss in vert and ds not in vert:  # vertical leg first, enters dst from the side
        return ("right" if ds == "left" else "left"), ("top" if ss == "bottom" else "bottom")
    if ss not in vert and ds in vert:
        return ("bottom" if ds == "top" else "top"), ("left" if ss == "right" else "right")
    return None


def _all_sides(bp, placed) -> dict[str, tuple[str, str]]:
    first = {e.id: _choose_sides(bp, placed, e) for e in bp.edges}
    sides = {}
    used_all: dict = {}
    for e in bp.edges:
        os_, od = first[e.id]
        used_all.setdefault((e.src, os_), []).append(e.id)
        used_all.setdefault((e.dst, od), []).append(e.id)
    for e in bp.edges:
        ss, ds = first[e.id]
        alt = _l_alternative(ss, ds) if (e.src_side == "auto" and e.dst_side == "auto") else None
        if alt is not None:  # L-elbow: avoid entering/leaving through a side another edge already uses
            busy = lambda s1, s2: len([x for x in used_all.get((e.src, s1), []) if x != e.id]) + \
                len([x for x in used_all.get((e.dst, s2), []) if x != e.id])
            if busy(ss, ds) > busy(*alt):
                first[e.id] = alt
                ss, ds = alt
        if ss == ds and e.src_side == "auto" and e.dst_side == "auto":  # detour: re-choose knowing the others
            used: dict = {}
            for o in bp.edges:
                if o.id == e.id:
                    continue
                os_, od = first[o.id]
                used[(o.src, os_)] = used.get((o.src, os_), 0) + 1
                used[(o.dst, od)] = used.get((o.dst, od), 0) + 1
            sides[e.id] = _choose_sides(bp, placed, e, used)
        else:
            sides[e.id] = (ss, ds)
    for e in bp.edges:  # never attach on the side an element's name was moved to (it would run through the text)
        ss, ds = sides[e.id]
        ss = _off_name(placed, e.src, ss, placed[e.dst].box) if e.src_side == "auto" else ss
        ds = _off_name(placed, e.dst, ds, placed[e.src].box) if e.dst_side == "auto" else ds
        sides[e.id] = (ss, ds)
    return sides


def name_side(pl: Placed) -> str | None:
    """Which side of its shape an element's outside name is on (None: no outside name)."""
    lb, b = pl.label_box, pl.box
    if lb is None:
        return None
    if lb.y >= b.bottom - 0.5:
        return "bottom"
    if lb.bottom <= b.y + 0.5:
        return "top"
    return "right" if lb.x >= b.right - 0.5 else "left"


def _off_name(placed, elem, side, other: Box) -> str:
    ns = name_side(placed[elem])
    if ns is None or ns == "bottom" or side != ns:  # a name below is handled port by port (_under_label)
        return side
    b = placed[elem].box
    if side in ("left", "right"):
        return "top" if other.cy < b.cy else "bottom"
    return "right" if other.cx > b.cx else "left"


def route_all(bp: Blueprint, placed: dict[str, Placed], recipe: Recipe, full: bool = True) -> dict[str, Route]:
    """Route every edge. full=False skips the repair, untangle and straighten passes (85% of a build's time, STORM):
    the fit and the layout feedback only need where lines go and which sides they use; the drawn figure is routed
    in full once, on the final layout (pipeline)."""
    from .annotations import place as place_brackets

    global _EXTRA, _BORDERS
    _EXTRA = [g.band for g in place_brackets(bp, placed, recipe).values()]
    _BORDERS = []
    for g in bp.groups():
        if g.frame != "none" and g is not bp.root:
            b = placed[g.id].box
            _BORDERS += [("v", b.x, b.y, b.bottom), ("v", b.right, b.y, b.bottom), ("h", b.y, b.x, b.right), ("h", b.bottom, b.x, b.right)]
    global _TIP, _NEAR, _HEADS, _LABELS, _LABEL_SIZE
    from .styles import arrow_size
    _TIP = arrow_size(recipe)  # the arrowhead size edges are drawn with
    _NEAR = {e.id: _near_boxes(bp, placed, e) for e in bp.edges}
    _HEADS = {e.id: (_has_head(recipe, e, "src"), _has_head(recipe, e, "dst")) for e in bp.edges}
    _LABELS = {}
    _LABEL_SIZE = {e.id: measure(e.label, recipe["typography"]["small_size"]) for e in bp.edges if e.label}
    sides = _all_sides(bp, placed)
    ports = _assign_ports(bp, placed, sides, recipe)

    order = sorted(bp.edges, key=lambda e: (KIND_ORDER.get(e.kind, 5), not e.label, -(abs(placed[e.src].box.cx - placed[e.dst].box.cx) + abs(placed[e.src].box.cy - placed[e.dst].box.cy))))
    routed = _Routed()
    out: dict[str, Route] = {}
    for e in order:
        ss, ds = sides[e.id]
        try:
            pts, _ = _route_edge(bp, placed, e, ss, ds, ports[(e.id, "src")], ports[(e.id, "dst")], routed)
        except RouteError:  # the chosen sides are walled in: any other pair of sides, at free ports
            pts = None
            for s1 in DIRS:
                for s2 in DIRS:
                    q0 = _free_port(placed[e.src], s1, [])
                    q1 = _free_port(placed[e.dst], s2, [])
                    if q0 is None or q1 is None:
                        continue
                    try:
                        cand, sc = _route_edge(bp, placed, e, s1, s2, q0, q1, routed)
                    except RouteError:
                        continue
                    if pts is None or sc < pts[1]:
                        pts, ss, ds = (cand, sc), s1, s2
            if pts is None:
                raise
            pts = pts[0]
        routed.add(pts, e.id)
        out[e.id] = Route(e.id, pts, ss, ds)
        _place_label(e.id, pts)
    if full:
        _repair(bp, placed, out, order)
        _untangle(bp, placed, out)
        _straighten(bp, placed, out, order)
    _bundle(bp, placed, out)
    _place_labels(bp, placed, out)
    return out


def _place_labels(bp, placed, out: dict) -> None:
    """Each edge label goes where nothing strikes it: no framed group's border, no other line, no element, no
    other label; nearest the middle of the longest straight run otherwise (user, round 2: lines through text —
    STORM's a_t sat on the actor-critic frame). Sets Route.label_t."""
    from .geometry import segment_crosses_interior
    others_boxes = [placed[n.id].footprint for n in bp.leaves()]
    titles = [placed[g.id].title_text or placed[g.id].title_box for g in bp.groups()
              if g is not bp.root and g.title and (placed[g.id].title_text or placed[g.id].title_box)]
    borders = []
    for o, c, lo, hi in _BORDERS:
        borders.append(((c, lo), (c, hi)) if o == "v" else ((lo, c), (hi, c)))
    taken: list = []
    eby = {e.id: e for e in bp.edges}
    for k in sorted(out, key=lambda k: k):
        e = eby.get(k)
        if e is None or not e.label or k not in _LABEL_SIZE:
            continue
        pts = out[k].points
        w, h = _LABEL_SIZE[k]
        hs, ht = _HEADS.get(k, (False, False))
        clear0 = END_RUN * _TIP if hs else _TIP  # line kept between the label and each end (a head needs a shaft)
        clear1 = END_RUN * _TIP if ht else _TIP
        lens = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        total = sum(lens) or 1.0
        best = None
        for i, L in enumerate(lens):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            along = (w if abs(y1 - y2) < 1e-6 else h) + 6.0  # the label's extent along this segment (+ draw.io's
            # placement slack: measured 3.5 px off-centre on GAT's e_ij)
            fr = [0.5, 0.35, 0.65, 0.2, 0.8]
            if L > 0:  # snug against either end's clearance
                start = sum(lens[:i])
                for c in (clear0 + along / 2, total - clear1 - along / 2):
                    if start < c < start + L:
                        fr.append((c - start) / L)
            horiz_seg = abs(y1 - y2) < 1e-6
            g = 0.6 * _TIP + 1  # beside the line: clear of the line and of an arrowhead's flanks
            offsets = [(0.0, 0.0)] + ([(0.0, -(h / 2 + g)), (0.0, h / 2 + g)] if horiz_seg
                                      else [(w / 2 + g, 0.0), (-(w / 2 + g), 0.0)])
            for f in fr:
                for dx, dy in offsets:
                    cx, cy = x1 + (x2 - x1) * f + dx, y1 + (y2 - y1) * f + dy
                    box = Box(cx - w / 2 - 2, cy - h / 2 - 2, w + 4, h + 4)
                    bad = 0.0
                    bad += 1000.0 * sum(1 for a, b in borders if segment_crosses_interior(a, b, box, eps=0.5))
                    bad += 1000.0 * sum(1 for k2, r in out.items() if (k2 != k or dx or dy)
                                        and any(segment_crosses_interior(a, b, box, eps=0.5) for a, b in zip(r.points, r.points[1:])))
                    bad += 500.0 * sum(1 for fb in others_boxes + titles + taken if box.intersects(fb, eps=0.5))
                    if dx or dy:  # beside the line: the whole line shows, heads and shafts; on it is the default
                        bad += 60.0 + 4 * max(0.0, along - L)
                    else:  # on the line (it knocks the line out): each end keeps its line, a head its shaft
                        d0 = sum(lens[:i]) + L * f - along / 2  # path length before / after the label
                        d1 = total - (sum(lens[:i]) + L * f) - along / 2
                        short = max(0.0, clear0 - d0) + max(0.0, clear1 - d1) + max(0.0, along - L)
                        bad += 0 if short <= 0 else 200.0 + 4 * short
                    bad += abs(f - 0.5) * 20 + (max(lens) - L) * 0.05  # middle of the longest run, all else equal
                    if best is None or bad < best[0]:
                        best = (bad, (sum(lens[:i]) + L * f) / total, box, (dx, dy))
        if best is not None:
            out[k].label_t = best[1]
            out[k].label_off = best[3]
            taken.append(best[2])


def port_room(bp: Blueprint, placed: dict[str, Placed], routes: dict, recipe: Recipe) -> dict:
    """{(element id, "min_w"|"min_h"): px} for resizable elements whose side holds more ports than fit two
    arrowheads apart (user 2026-11-14: rather than lines meeting at a crowded side, make the block bigger).
    solve_and_route feeds it back into the layout."""
    from .layout import RESIZABLE
    rad = max(recipe["shape"]["radius"], recipe["shape"]["group_radius"])
    inset = max(PORT_INSET, rad + 4)
    count: dict = {}
    eby = {e.id: e for e in bp.edges}
    for k, r in routes.items():
        e = eby.get(k)
        if e is None:
            continue
        for elem, side in ((e.src, r.src_side), (e.dst, r.dst_side)):
            count[(elem, side)] = count.get((elem, side), 0) + 1
    need: dict = {}
    for (elem, side), n in count.items():
        el = bp.index[elem]
        if n < 2 or el.is_group or getattr(el, "visual", None) not in RESIZABLE:
            continue
        b = placed[elem].box
        length = (n - 1) * _port_sep() + 2 * inset
        if getattr(el, "visual", None) == "trapezoid":  # the slanted ends lose part of their length
            from .shapes import TRAPEZOID_SIZE
            length /= (1 - 2 * TRAPEZOID_SIZE)
        key, have = ((elem, "min_h"), b.h) if side in ("left", "right") else ((elem, "min_w"), b.w)
        if length > have + 0.5:
            need[key] = max(need.get(key, 0.0), length)
    return need


def label_moves(bp: Blueprint, placed: dict[str, Placed], routes: dict, current: dict) -> dict:
    """{(element id, "label_side"): "top"|"right"|"left"|"below"} for elements whose outside name sits where a line
    leaves or enters (the line would grow out of the text — user, round 2). The name moves to a side no line uses,
    above first (no extra width; beside widened wav2vec2 707 -> 951 px); with every side in use it stays."""
    eby = {e.id: e for e in bp.edges}
    used: dict = {}
    for k, r in routes.items():
        e = eby.get(k)
        if e is None:
            continue
        for elem, side, pt in ((e.src, r.src_side, r.points[0]), (e.dst, r.dst_side, r.points[-1])):
            used.setdefault((elem, side), []).append(pt)
    out = {}
    for n in bp.leaves():
        pl = placed.get(n.id)
        if pl is None or pl.label_box is None:
            continue
        lb, b = pl.label_box, pl.box
        side = ("bottom" if lb.y >= b.bottom - 0.5 else "top" if lb.bottom <= b.y + 0.5
                else "right" if lb.x >= b.right - 0.5 else "left")
        pts = used.get((n.id, side), [])
        g = 2.0
        if side in ("bottom", "top"):
            hit = any(lb.x - g < x < lb.right + g for x, _ in pts)
        else:
            hit = any(lb.y - g < y < lb.bottom + g for _, y in pts)
        if not hit:
            continue
        tried = current.get((n.id, "label_tried"), ())
        free = next((sd for sd in ("top", "right", "left", "bottom") if sd != side and sd not in tried
                     and (n.id, sd) not in used), None)
        if free:
            out[(n.id, "label_side")] = "below" if free == "bottom" else free
            out[(n.id, "label_tried")] = tuple(tried) + (side,)
    return out


def _has_head(recipe, e, end) -> bool:
    if end == "src" and getattr(e, "heads", "auto") == "end":
        return False
    st = recipe.data.get("edges", {}).get(e.kind, {})
    return st.get("start" if end == "src" else "end", "none") not in ("none", None)


OPP = {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}


def _bundle(bp: Blueprint, placed: dict, out: dict) -> set:
    """Edges with the same `bundle` that share a source (fan-out) or a target (fan-in): one port on the shared
    element, one trunk to a branch line 30% of the way across the gap, one branch per other end. Only where every
    other end lies on one side and no branch crosses another element; otherwise the routes stay and
    bp.bundle_notes says why."""
    groups: dict = {}
    for e in bp.edges:
        if getattr(e, "bundle", None):
            groups.setdefault(e.bundle, []).append(e)
    notes, done = [], set()
    for name, es in groups.items():
        if len(es) < 2:
            continue
        if len({e.src for e in es}) == 1:
            hub, ends, fan_in = es[0].src, {e.id: e.dst for e in es}, False
        elif len({e.dst for e in es}) == 1:
            hub, ends, fan_in = es[0].dst, {e.id: e.src for e in es}, True
        else:
            notes.append(f"bundle '{name}': its edges share neither a source nor a target — drawn as separate arrows")
            continue
        s = placed[hub].box
        ts = {k: placed[v].box for k, v in ends.items()}
        side = next((sd for sd, ok in (("right", all(t.x > s.right for t in ts.values())),
                                       ("left", all(t.right < s.x for t in ts.values())),
                                       ("bottom", all(t.y > s.bottom for t in ts.values())),
                                       ("top", all(t.bottom < s.y for t in ts.values()))) if ok), None)
        if side is None:
            notes.append(f"bundle '{name}' at '{hub}': the other ends lie on different sides — drawn as separate arrows")
            continue
        hub_side, end_side = side, OPP[side]  # the hub's port faces the far ends; theirs face it (fan-out and fan-in)
        pinned = [e.id for e in es if (e.src_side not in ("auto", hub_side if not fan_in else end_side))
                  or (e.dst_side not in ("auto", end_side if not fan_in else hub_side))]
        if pinned:  # an author's side choice wins over the bus
            notes.append(f"bundle '{name}' at '{hub}': {', '.join(pinned)} pin a side the bus cannot use — drawn as "
                         "separate arrows (drop the pin, or the bundle)")
            continue
        horiz = side in ("left", "right")
        mine = {e.id for e in es}
        taken: dict = {}  # ports other edges already use: a branch on top of one reads as one thick line
        eby_all = {x.id: x for x in bp.edges}
        for k2, r2 in out.items():
            x = eby_all.get(k2)
            if x is None or k2 in mine:
                continue
            for el, sd, pt in ((x.src, r2.src_side, r2.points[0]), (x.dst, r2.dst_side, r2.points[-1])):
                taken.setdefault((el, sd), []).append(pt[1] if sd in ("left", "right") else pt[0])

        def port(el, sd):
            pt = _port_point(placed[el], sd, 0.5)
            c = pt[1] if sd in ("left", "right") else pt[0]
            if any(abs(c - t) < _port_sep() for t in taken.get((el, sd), [])):
                alt = _free_port(placed[el], sd, taken.get((el, sd), []))
                if alt is not None:
                    return alt
            return pt
        p0 = port(hub, side)
        p1s = {e.id: port(ends[e.id], OPP[side]) for e in es}
        near = (min(t.x for t in ts.values()) if side == "right" else max(t.right for t in ts.values()) if side == "left"
                else min(t.y for t in ts.values()) if side == "bottom" else max(t.bottom for t in ts.values()))
        start = p0[0] if horiz else p0[1]
        # branch near the shared element on a fan-out (straight runs into the arrowheads), near the far ends on a
        # fan-in (the merged trunk carries the single arrowhead into the target)
        b = start + (0.7 if fan_in else 0.3) * (near - start)
        new = {}
        for e in es:
            p1 = p1s[e.id]
            pts = [p0, (b, p0[1]), (b, p1[1]), p1] if horiz else [p0, (p0[0], b), (p1[0], b), p1]
            new[e.id] = _simplify(list(reversed(pts)) if fan_in else pts)
        titles = [placed[g.id].title_text or placed[g.id].title_box for g in bp.groups()
                  if g is not bp.root and g.title and (placed[g.id].title_text or placed[g.id].title_box)]

        def hits(pts, own):  # every element but the shared one and this branch's own end — other targets count,
            others = [placed[n.id].footprint for n in bp.leaves() if n.id not in (hub, own)] + titles  # titles too
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                seg = Box(min(x1, x2) - 0.5, min(y1, y2) - 0.5, abs(x2 - x1) + 1, abs(y2 - y1) + 1)
                if any(seg.intersects(o, eps=0.5) for o in others):
                    return True
            return False
        if any(hits(new[e.id], ends[e.id]) for e in es):
            notes.append(f"bundle '{name}' at '{hub}': a branch would cross another element — drawn as separate arrows")
            continue
        # every piece of line is drawn once (drawn twice it renders as one thick line — user, round 2): the trunk
        # (shared port -> branch line) by one edge, the branch line on each side of the trunk by the farthest
        # branch there; nearer branches start (fan-out) or end without a head (fan-in) where they meet that line
        ax = 1 if horiz else 0  # the coordinate along the branch line
        far_c = {e.id: p1s[e.id][ax] for e in es}
        sgn = {k: (v > p0[ax] + 0.5) - (v < p0[ax] - 0.5) for k, v in far_c.items()}
        straight = [e.id for e in es if sgn[e.id] == 0]
        by_dir = {d: sorted((e.id for e in es if sgn[e.id] == d), key=lambda k: -abs(far_c[k] - p0[ax])) for d in (-1, 1)}
        primary = straight[0] if straight else max(by_dir.values(), key=len)[0]
        bus_owner = {d: ids[0] for d, ids in by_dir.items() if ids}

        def at(c):  # the point on the branch line at coordinate c
            return (b, c) if horiz else (c, b)
        for e in es:
            p1 = p1s[e.id]
            if e.id == primary:
                pts, free = new[e.id], False
            elif e.id == bus_owner.get(sgn[e.id]):  # draws its side of the branch line, from the junction
                pts = _simplify([at(p0[ax]), at(p1[ax]), p1])
                pts, free = (list(reversed(pts)), True) if fan_in else (pts, False)
            else:  # only its own branch, from the branch line
                pts = [at(p1[ax]), p1]
                pts, free = (list(reversed(pts)), True) if fan_in else (pts, False)
            out[e.id] = Route(e.id, pts, OPP[side] if fan_in else side, side if fan_in else OPP[side], free_end=free)
            done.add(e.id)
    bp.bundle_notes = notes
    return done


_EXTRA: list[Box] = []  # annotation bands for the figure currently being routed


def _obstacles(bp, placed, e, m) -> list[Box]:
    anc = set(bp.ancestors(e.src)) | set(bp.ancestors(e.dst))
    both = set(bp.ancestors(e.src)) & set(bp.ancestors(e.dst))
    obstacles = []
    for el in bp.index.values():
        pl = placed[el.id]
        if el.is_group:
            if el.id in (e.src, e.dst):
                obstacles.append(pl.box.inflate(m))
            elif el.id in anc:
                if pl.title_box is not None:  # only the title text: edges may enter the group beside it
                    tt = getattr(pl, "title_text", None)
                    obstacles.append((tt or pl.title_box).inflate(m / 2))
                if el.id in both and el.frame != "none":
                    obstacles.extend(_walls(pl.box, m / 2 + 2))
            elif el.frame != "none":
                obstacles.append(pl.box.inflate(m))
        else:
            # shape and below-label are separate obstacles: a label wider than its shape must not
            # swallow the shape's side ports
            obstacles.append(pl.box.inflate(m))
            if pl.label_box is not None:
                obstacles.append(pl.label_box.inflate(min(m, 4.0)))
    obstacles.extend(b.inflate(min(m, 6.0)) for b in _EXTRA)
    if _WITH_LABELS:  # other edges' labels: a line through a label strikes the text out
        obstacles.extend(b for k, b in _LABELS.items() if k != e.id)
    return obstacles


_WITH_LABELS = True


def _hug_prep(boxes):
    """(box, box inflated by one arrowhead) as plain tuples, once per search."""
    t = _TIP
    return [(b.x, b.y, b.right, b.bottom, b.x - t, b.y - t, b.right + t, b.bottom + t) for b in boxes]


def _hug_seg(p, q, prepped) -> float:
    (x1, y1), (x2, y2) = p, q
    tot = 0.0
    if abs(y1 - y2) < 1e-9:
        lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
        for bx, by, br, bb, ox, oy, orr, ob in prepped:
            if oy < y1 < ob and not (by - 0.5 < y1 < bb + 0.5):
                ov = min(hi, orr) - max(lo, ox)
                if ov > 0:
                    tot += ov
    else:
        lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
        for bx, by, br, bb, ox, oy, orr, ob in prepped:
            if ox < x1 < orr and not (bx - 0.5 < x1 < br + 0.5):
                ov = min(hi, ob) - max(lo, oy)
                if ov > 0:
                    tot += ov
    return tot


def _hug_len(pts, boxes) -> float:
    """Length of line running within one arrowhead of boxes it does not connect (reads as touching them)."""
    prepped = _hug_prep(boxes)
    return sum(_hug_seg(a, b, prepped) for a, b in zip(pts, pts[1:]))


def _near_boxes(bp, placed, e) -> list[Box]:
    return [b for n in bp.leaves() if n.id not in (e.src, e.dst)
            for b in (placed[n.id].box, placed[n.id].label_box) if b is not None]


def _route_edge(bp, placed, e, ss, ds, p0, p1, routed, margins=MARGINS):
    """Best route; raises RouteError if none works. Preferred in this order, each tried only when the one before
    finds nothing: every arrow end keeps END_RUN arrowheads of straight line in its own direction and other edges'
    labels are obstacles; then labels kept but short ends; then neither (user 2026-11-14: a connection must show a
    straight run before its head, and no line may run through text)."""
    global _WITH_LABELS
    hs, ht = _HEADS.get(e.id, (False, False))
    run = END_RUN * _TIP
    modes = [(run if hs else 0.0, run if ht else 0.0, True), (0.0, 0.0, True), (0.0, 0.0, False)]
    if not (hs or ht):
        modes = modes[1:]
    last_err = None
    try:
        for ls, lt, labels in modes:
            _WITH_LABELS = labels
            try:
                return _route_edge_once(bp, placed, e, ss, ds, p0, p1, routed, margins, ls, lt)
            except RouteError as err:
                last_err = err
    finally:
        _WITH_LABELS = True
    raise last_err


def _route_edge_once(bp, placed, e, ss, ds, p0, p1, routed, margins, ls, lt):
    last_err = None
    best = None  # (score, pts, cost): every clearance is tried; a big clearance must not force an absurd detour
    near = _near_boxes(bp, placed, e)
    for m in margins:
        obstacles = _obstacles(bp, placed, e, m)
        S = _stub(placed[e.src], ss, p0, max(m, ls))
        T = _stub(placed[e.dst], ds, p1, max(m, lt))
        dx, dy = DIRS[ss]
        if OPP[ss] == ds and (ls or lt) and (T[0] - S[0]) * dx + (T[1] - S[1]) * dy < 0:
            # facing ends too close for both runs: one straight line serves both if the ports line up
            if abs(p0[0] - p1[0]) < 1e-6 or abs(p0[1] - p1[1]) < 1e-6:
                L = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
                if L >= max(ls, lt) + (HEAD_DRAWN * _TIP if ls and lt else 0.0) - 0.5:  # = layout._arrow_gaps
                    return [p0, p1], L
            last_err = RouteError(e.id, "no room for straight arrow ends")
            continue
        if (ls or lt) and not (_run_clear(p0, S, obstacles) and _run_clear(T, p1, obstacles)):
            last_err = RouteError(e.id, "a straight arrow end would cross something")
            continue
        bx, by = _border_lines(bp)
        try:
            mid, cost = find_path_cost(e.id, S, ss, T, OPP[ds], obstacles, routed, extra_x=(p0[0], p1[0], *bx),
                                       extra_y=(p0[1], p1[1], *by), borders=_BORDERS, near=near)
        except RouteError as err:
            last_err = err
            continue
        pts = _simplify([p0] + mid + [p1])
        # mild preference for more clearance (the cost already charges a line skimming a box it does not connect)
        score = cost + 4.0 * (margins[0] - m)
        if best is None or score < best[0] - 1e-9:
            best = (score, pts, cost)
        if cost <= abs(T[0] - S[0]) + abs(T[1] - S[1]) + 2 * BEND + 1e-6:
            break  # already a Manhattan-length route with <= 2 bends: smaller clearances cannot beat it
    if best is None:
        raise last_err or RouteError(e.id)
    return best[1], best[0]


def _run_clear(a, b, obstacles) -> bool:
    """The straight end run a-b (port to stub point) crosses no obstacle but the one it starts or ends in."""
    seg = Box(min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]), abs(b[1] - a[1]))
    for o in obstacles:
        if o.contains_point(*a, eps=GEOM_EPS) or o.contains_point(*b, eps=GEOM_EPS):
            continue
        if seg.intersects(o, eps=GEOM_EPS):
            return False
    return True


def _stub(pl: Placed, side: str, p, m: float):
    fixed = _side_span(pl, side)[0]
    dx, dy = DIRS[side]
    return (fixed + dx * m, p[1]) if side in ("left", "right") else (p[0], fixed + dy * m)


_BORDERS: list = []  # (orient, coord, lo, hi) of framed container borders for the current figure
BORDER_CLEAR, BORDER_PENALTY = 8.0, 60.0


def _border_lines(bp):
    xs, ys = [], []
    for o, c, lo, hi in _BORDERS:
        (xs if o == "v" else ys).extend((c - BORDER_CLEAR - 2, c + BORDER_CLEAR + 2))
    return xs, ys


def _crossings(pts, others) -> int:
    n = 0
    for (a, b) in zip(pts, pts[1:]):
        ha = abs(a[1] - b[1]) < 1e-6
        for o in others:
            for (c, d) in zip(o, o[1:]):
                hc = abs(c[1] - d[1]) < 1e-6
                if ha == hc:
                    continue
                h, v = ((a, b), (c, d)) if ha else ((c, d), (a, b))
                if min(h[0][0], h[1][0]) + 0.5 < v[0][0] < max(h[0][0], h[1][0]) - 0.5 and \
                        min(v[0][1], v[1][1]) + 0.5 < h[0][1] < max(v[0][1], v[1][1]) - 0.5:
                    n += 1
    return n


def _overlap_len(p, q) -> float:
    """Total length over which two polylines run collinearly on top of each other."""
    tot = 0.0
    for a, b in zip(p, p[1:]):
        for c, d in zip(q, q[1:]):
            if abs(a[1] - b[1]) < 0.5 and abs(c[1] - d[1]) < 0.5 and abs(a[1] - c[1]) < 0.5:
                tot += max(0.0, min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])))
            elif abs(a[0] - b[0]) < 0.5 and abs(c[0] - d[0]) < 0.5 and abs(a[0] - c[0]) < 0.5:
                tot += max(0.0, min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])))
    return tot


def _edge_badness(pts) -> float:
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    direct = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
    return 50.0 * max(0, len(pts) - 2 - 2) + 0.1 * (length - direct)


def global_badness(routes: dict) -> float:
    """Whole-figure routing cost used to accept or reject repairs: overlaps are worst, then crossings."""
    items = [r.points if hasattr(r, "points") else r for r in routes.values()]
    total = sum(_edge_badness(p) for p in items)
    for k, r in routes.items():  # skimming a box it does not connect, as in _route_edge (STORM: the repair pass
        if k in _NEAR:           # moved s_t->actor back to 3 px under the critic, since nothing here counted it)
            total += HUG_W * _hug_len(r.points if hasattr(r, "points") else r, _NEAR[k])
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if _overlap_len(a, b) > 1.0:
                total += 2000.0
            total += 1000.0 * _crossings(a, [b])
            total += 3.0 * _parallel_len(a, b)  # side by side, closer than PARALLEL heads: one thick line
    total += 1000.0 * _label_hits(routes)
    total += 1000.0 * sum(_short_runs(k, r.points if hasattr(r, "points") else r) for k, r in routes.items())  # = a crossing: "确保" (user)
    return total


def _short_runs(eid, pts) -> int:
    """Arrow ends of this edge whose last straight run is shorter than END_RUN endSizes (only a head shows —
    user, round 2): the repair pass weighs them, so it does not trade a straight end for a shorter route
    (DreamerV3: critic v2 -> actor loss moved to facing sides 22 px apart and kept 3 px of line)."""
    if len(pts) < 2:
        return 0
    hs, ht = _HEADS.get(eid, (False, False))
    need = END_RUN * _TIP - 0.5
    n = 0
    if hs and abs(pts[1][0] - pts[0][0]) + abs(pts[1][1] - pts[0][1]) < need:
        n += 1
    if ht and abs(pts[-1][0] - pts[-2][0]) + abs(pts[-1][1] - pts[-2][1]) < need:
        n += 1
    return n


def _parallel_len(p, q) -> float:
    """Length over which two polylines run side by side closer than PARALLEL arrowheads (not on top: that is
    _overlap_len)."""
    near, tot = PARALLEL * _TIP, 0.0
    for a, b in zip(p, p[1:]):
        for c, d in zip(q, q[1:]):
            if abs(a[1] - b[1]) < 0.5 and abs(c[1] - d[1]) < 0.5 and 0.5 <= abs(a[1] - c[1]) < near:
                tot += max(0.0, min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])))
            elif abs(a[0] - b[0]) < 0.5 and abs(c[0] - d[0]) < 0.5 and 0.5 <= abs(a[0] - c[0]) < near:
                tot += max(0.0, min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])))
    return tot


def _label_hits(routes: dict) -> int:
    """Lines running through another edge's label (labels follow their routes)."""
    from .geometry import segment_crosses_interior
    pts = {k: (r.points if hasattr(r, "points") else r) for k, r in routes.items()}
    boxes = {k: _label_box(k, p) for k, p in pts.items()}
    n = 0
    for k, b in boxes.items():
        if b is None:
            continue
        for k2, p in pts.items():
            if k2 != k and any(segment_crosses_interior(a, c, b, eps=1.0) for a, c in zip(p, p[1:])):
                n += 1
    return n


def _repair(bp, placed, out: dict[str, Route], order):
    """Re-route edges that cross or overlap others, bend more than 3 times or detour wildly, trying every
    pair of sides (auto-sided edges only). Low-priority edges (loss, control, skip) are moved first, and a
    candidate is kept only if the whole figure's routing badness drops."""
    eby = {e.id: e for e in bp.edges}
    for e in reversed(order):
        if e.src_side != "auto" or e.dst_side != "auto":
            continue
        cur = out[e.id]
        others = [r.points for k, r in out.items() if k != e.id]
        length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(cur.points, cur.points[1:]))
        direct = abs(cur.points[-1][0] - cur.points[0][0]) + abs(cur.points[-1][1] - cur.points[0][1])
        clean = (_crossings(cur.points, others) == 0 and all(_overlap_len(cur.points, o) <= 1.0 for o in others)
                 and all(_parallel_len(cur.points, o) <= 2 * _TIP for o in others)
                 and len(cur.points) - 2 <= 3 and length <= 1.8 * direct + 60
                 and _short_runs(e.id, cur.points) == 0
                 and _label_hits({e.id: cur.points, **{k: r.points for k, r in out.items() if k != e.id}}) == 0)
        if clean:
            continue
        routed = _Routed()
        for k, r in out.items():
            if k != e.id:
                routed.add(r.points, k)
        taken: dict[tuple[str, str], list[float]] = {}
        for k, r in out.items():
            if k == e.id:
                continue
            ed = eby[k]
            for elem, side, pt in ((ed.src, r.src_side, r.points[0]), (ed.dst, r.dst_side, r.points[-1])):
                taken.setdefault((elem, side), []).append(pt[1] if side in ("left", "right") else pt[0])
        best_score, best = global_badness(out), cur
        a_c, b_c = placed[e.src].box, placed[e.dst].box
        vx, vy = b_c.cx - a_c.cx, b_c.cy - a_c.cy

        def plausible(sd):  # sides facing the other end first: the first clean one found is kept
            (dxs, dys), (dxd, dyd) = DIRS[sd[0]], DIRS[sd[1]]
            return -((dxs * vx + dys * vy) - (dxd * vx + dyd * vy))
        found_clean = False
        for ss, ds in sorted(((a, b) for a in DIRS for b in DIRS), key=plausible):
            if found_clean:
                break
            if True:
                p0 = _free_port(placed[e.src], ss, taken.get((e.src, ss), []))
                p1 = _free_port(placed[e.dst], ds, taken.get((e.dst, ds), []))
                if p0 is None or p1 is None:
                    continue
                try:
                    pts, _ = _route_edge(bp, placed, e, ss, ds, p0, p1, routed, margins=(10.0, 6.0, 3.0))
                except RouteError:
                    continue
                trial = dict(out)
                trial[e.id] = Route(e.id, pts, ss, ds)
                score = global_badness(trial)
                if score < best_score - 1e-6:
                    best_score, best = score, trial[e.id]
                    rest = [r.points for k, r in out.items() if k != e.id]
                    found_clean = (_crossings(pts, rest) == 0 and all(_overlap_len(pts, o) <= 1.0 for o in rest)
                                   and all(_parallel_len(pts, o) <= 2 * _TIP for o in rest)
                                   and _label_hits(trial) == 0)
        out[e.id] = best
        _place_label(e.id, best.points)


def _untangle(bp, placed, out: dict) -> None:
    """Two lines on one side of an element that cross each other swap their ports there (STORM: z_t and h_t both
    came down into s_t's left side, the outer one on the upper port, and crossed right before the block). A swap
    is kept only if the whole figure's routing gets better."""
    eby = {e.id: e for e in bp.edges}
    ends: dict = {}
    for k, r in out.items():
        e = eby.get(k)
        if e is None or getattr(r, "free_end", False):
            continue
        ends.setdefault((e.src, r.src_side), []).append((k, 0))
        ends.setdefault((e.dst, r.dst_side), []).append((k, -1))
    for (elem, side), lst in ends.items():
        for i, (ka, ia) in enumerate(lst):
            for kb, ib in lst[i + 1:]:
                if ka == kb or _crossings(out[ka].points, [out[kb].points]) == 0:
                    continue
                pa, pb = out[ka].points[ia], out[kb].points[ib]
                routed = _Routed()
                for k, r in out.items():
                    if k not in (ka, kb):
                        routed.add(r.points, k)
                trial = dict(out)
                ok = True
                for k, idx, newp in ((ka, ia, pb), (kb, ib, pa)):
                    e, r = eby[k], out[k]
                    p0 = newp if idx == 0 else r.points[0]
                    p1 = newp if idx == -1 else r.points[-1]
                    try:
                        pts, _ = _route_edge(bp, placed, e, r.src_side, r.dst_side, p0, p1, routed)
                    except RouteError:
                        ok = False
                        break
                    routed.add(pts, k)
                    trial[k] = Route(k, pts, r.src_side, r.dst_side)
                if ok and global_badness(trial) < global_badness(out) - 1e-6:
                    out[ka], out[kb] = trial[ka], trial[kb]
                    _place_label(ka, trial[ka].points)
                    _place_label(kb, trial[kb].points)


JOG_MIN = 8.0


def _straighten(bp, placed, out: dict[str, Route], order):
    """Remove small kinks left behind when the repair pass moved an edge off a shared side: align one
    end with the other if that side has room and the figure's routing does not get worse."""
    eby = {e.id: e for e in bp.edges}
    for e in order:
        rt = out[e.id]
        pts = rt.points
        segl = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        if len(pts) < 4 or min(segl[1:-1]) >= JOG_MIN or OPP[rt.src_side] != rt.dst_side:
            continue
        horiz = rt.src_side in ("left", "right")
        taken: dict[tuple[str, str], list[float]] = {}
        for k, r in out.items():
            if k == e.id:
                continue
            ed = eby[k]
            for elem, side, pt in ((ed.src, r.src_side, r.points[0]), (ed.dst, r.dst_side, r.points[-1])):
                taken.setdefault((elem, side), []).append(pt[1] if side in ("left", "right") else pt[0])
        routed = _Routed()
        for k, r in out.items():
            if k != e.id:
                routed.add(r.points, k)
        p0, p1 = pts[0], pts[-1]
        base = global_badness(out)
        for elem, side, coord, keep in ((e.dst, rt.dst_side, p0[1] if horiz else p0[0], "src"),
                                        (e.src, rt.src_side, p1[1] if horiz else p1[0], "dst")):
            fixed, lo, hi = _side_span(placed[elem], side)
            if not lo - 1e-6 <= coord <= hi + 1e-6 or any(abs(coord - t) < _port_sep() for t in taken.get((elem, side), [])):
                continue
            if _under_label(placed[elem], side, coord):
                continue
            new = _on_shape(placed[elem], side, (fixed, coord) if horiz else _attach_bottom(placed[elem], side, (coord, fixed)))
            a, b = (p0, new) if keep == "src" else (new, p1)
            try:
                cand, _ = _route_edge(bp, placed, e, rt.src_side, rt.dst_side, a, b, routed, margins=(10.0, 6.0, 3.0))
            except RouteError:
                continue
            trial = dict(out)
            trial[e.id] = Route(e.id, cand, rt.src_side, rt.dst_side)
            if len(cand) < len(pts) and global_badness(trial) <= base + 1e-6:
                out[e.id] = trial[e.id]
                break


def _free_port(pl: Placed, side: str, taken: list[float]):
    fixed, lo, hi = _side_span(pl, side, PORT_INSET + 6)
    own = pl.axis[1] if side in ("left", "right") else pl.axis[0]
    for k in range(0, 12):
        for sgn in (1, -1):
            v = min(hi, max(lo, own + sgn * k * _port_sep()))
            if all(abs(v - t) >= _port_sep() for t in taken) and not _under_label(pl, side, v):
                return _on_shape(pl, side, (fixed, v) if side in ("left", "right") else _attach_bottom(pl, side, (v, fixed)))
    for k in range(0, 12):  # every free spot is under the name: take one anyway (label_moves moves the name)
        for sgn in (1, -1):
            v = min(hi, max(lo, own + sgn * k * _port_sep()))
            if all(abs(v - t) >= _port_sep() for t in taken):
                return _on_shape(pl, side, (fixed, v) if side in ("left", "right") else (v, fixed))
    return None
