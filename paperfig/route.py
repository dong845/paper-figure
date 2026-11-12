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
from .layout import Placed
from .styles import Recipe

DIRS = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}
OPP = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}
BEND, CROSS, OVERLAP, NEAR = 24.0, 60.0, 400.0, 30.0
MARGINS = (14.0, 10.0, 7.0, 4.0, 2.0)  # clearance between routed lines and boxes
KIND_ORDER = {"data": 0, "skip": 1, "train_only": 2, "infer_only": 2, "grad": 3, "control": 3, "loss": 4}
PORT_INSET = 6.0  # keep ports away from rounded corners


@dataclass
class Route:
    edge_id: str
    points: list[tuple[float, float]]
    src_side: str
    dst_side: str

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
        self.h: list[tuple[float, float, float, str]] = []  # y, x1, x2, edge
        self.v: list[tuple[float, float, float, str]] = []  # x, y1, y2, edge

    def add(self, pts, eid):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if abs(y1 - y2) < 1e-9:
                self.h.append((y1, min(x1, x2), max(x1, x2), eid))
            else:
                self.v.append((x1, min(y1, y2), max(y1, y2), eid))

    def penalty(self, p, q) -> float:
        (x1, y1), (x2, y2) = p, q
        cost = 0.0
        if abs(y1 - y2) < 1e-9:
            lo, hi = sorted((x1, x2))
            for (x, a, b, _) in self.v:
                if lo + 0.5 < x < hi - 0.5 and a + 0.5 < y1 < b - 0.5:
                    cost += CROSS
            for (y, a, b, _) in self.h:
                ov = min(hi, b) - max(lo, a)
                if ov > 0.5:
                    d = abs(y - y1)
                    if d < 0.5:
                        cost += OVERLAP + 4 * ov
                    elif d < 5:
                        cost += NEAR
        else:
            lo, hi = sorted((y1, y2))
            for (y, a, b, _) in self.h:
                if lo + 0.5 < y < hi - 0.5 and a + 0.5 < x1 < b - 0.5:
                    cost += CROSS
            for (x, a, b, _) in self.v:
                ov = min(hi, b) - max(lo, a)
                if ov > 0.5:
                    d = abs(x - x1)
                    if d < 0.5:
                        cost += OVERLAP + 4 * ov
                    elif d < 5:
                        cost += NEAR
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


def find_path_cost(edge_id, start, start_dir, goal, goal_dir, obstacles: list[Box], routed, extra_x=(), extra_y=()):
    routed = routed if isinstance(routed, _Routed) else _Routed()
    for b in obstacles:
        if b.contains_point(*start) or b.contains_point(*goal):
            raise RouteError(edge_id, "an endpoint lies inside an obstacle (elements too close)")
    xs = _lines([start[0], goal[0], *extra_x] + [b.x for b in obstacles] + [b.right for b in obstacles], 40)
    ys = _lines([start[1], goal[1], *extra_y] + [b.y for b in obstacles] + [b.bottom for b in obstacles], 40)
    s = (_index_of(xs, start[0]), _index_of(ys, start[1]))
    g = (_index_of(xs, goal[0]), _index_of(ys, goal[1]))
    D = 0.01

    def inside_any(x, y):
        return any(b.contains_point(x, y) for b in obstacles)

    def blocked_pt(x, y):
        # interior of the union of obstacles: also catches seams between touching obstacles
        if inside_any(x, y):
            return True
        return all(inside_any(x + sx * D, y + sy * D) for sx in (-1, 1) for sy in (-1, 1))

    seg_cache: dict = {}

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
            nc = cst + abs(q[0] - p[0]) + abs(q[1] - p[1]) + (BEND if nd != d else 0.0) + routed.penalty(p, q)
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
        return b.y, b.x + inset_w, b.right - inset_w
    return pl.footprint.bottom, b.x + inset_w, b.right - inset_w


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
    for e in bp.edges:
        ss, ds = _choose_sides(bp, placed, e)
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


def _choose_sides(bp, placed, e) -> tuple[str, str]:
    a, b = placed[e.src].footprint, placed[e.dst].footprint
    sa, sb = _sides_auto(a, b)
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
        down = max(k.bottom for k in hits) - max(a.bottom, b.bottom)
        up = min(a.y, b.y) - min(k.y for k in hits)
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
    right = max(k.right for k in hits) - max(a.right, b.right)
    left = min(a.x, b.x) - min(k.x for k in hits)
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
    spans = {}
    for (elem, side), lst in buckets.items():
        fixed, lo, hi = _side_span(placed[elem], side, inset)
        spans[(elem, side)] = (fixed, lo, hi)
        horiz = side in ("left", "right")
        own = placed[elem].axis[1] if horiz else placed[elem].axis[0]

        def pref(item, horiz=horiz, lo=lo, hi=hi, own=own, side=side):
            e = item[0]
            ss, ds = sides[e.id]
            if OPP[ss] != ds:  # same-side detour (e.g. bottom->bottom): attach near the middle
                c = own
            else:
                ax = placed[item[2]].axis
                c = ax[1] if horiz else ax[0]
            return min(hi, max(lo, c))

        order = sorted(lst, key=lambda it: (KIND_ORDER.get(it[0].kind, 5), abs(pref(it) - (lo + hi) / 2)))
        sep = PORT_SEP if (hi - lo) >= PORT_SEP * (len(lst) - 1) else (hi - lo) / max(1, len(lst))
        taken: list[float] = []
        ok = True
        for it in order:
            want = pref(it)
            cands = sorted({min(hi, max(lo, want + k * sep * s)) for k in range(0, 2 * len(lst) + 2) for s in (-1, 1)},
                           key=lambda v: (abs(v - want), v))
            pick = next((v for v in cands if all(abs(v - t) >= sep - 1e-6 for t in taken)), None)
            if pick is None:
                ok = False
                break
            taken.append(pick)
            coord[(it[0].id, it[1])] = pick
        if not ok:  # even spread, ordered by the opposite endpoint
            srt = sorted(lst, key=lambda it: placed[it[2]].box.cy if horiz else placed[it[2]].box.cx)
            for k, it in enumerate(srt):
                coord[(it[0].id, it[1])] = lo + (hi - lo) * (k + 1) / (len(lst) + 1)
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
                v = ac if lo <= ac <= hi else bc if lo <= bc <= hi else (lo + hi) / 2
                pa, pb = ports[(e.id, "src")], ports[(e.id, "dst")]
                if ss in ("left", "right"):
                    ports[(e.id, "src")], ports[(e.id, "dst")] = (pa[0], v), (pb[0], v)
                else:
                    ports[(e.id, "src")], ports[(e.id, "dst")] = (v, pa[1]), (v, pb[1])
    return ports


def route_all(bp: Blueprint, placed: dict[str, Placed], recipe: Recipe) -> dict[str, Route]:
    sides = {e.id: _choose_sides(bp, placed, e) for e in bp.edges}
    ports = _assign_ports(bp, placed, sides, recipe)

    order = sorted(bp.edges, key=lambda e: (KIND_ORDER.get(e.kind, 5), -(abs(placed[e.src].box.cx - placed[e.dst].box.cx) + abs(placed[e.src].box.cy - placed[e.dst].box.cy))))
    routed = _Routed()
    out: dict[str, Route] = {}
    for e in order:
        ss, ds = sides[e.id]
        p0, p1 = ports[(e.id, "src")], ports[(e.id, "dst")]
        anc = set(bp.ancestors(e.src)) | set(bp.ancestors(e.dst))
        both = set(bp.ancestors(e.src)) & set(bp.ancestors(e.dst))
        last_err = None
        best = None  # (score, pts): every clearance is tried; a big clearance must not force an absurd detour
        for m in MARGINS:
            obstacles = []
            for el in bp.index.values():
                pl = placed[el.id]
                if el.is_group:
                    if el.id in (e.src, e.dst):
                        obstacles.append(pl.box.inflate(m))
                    elif el.id in anc:
                        if pl.title_box is not None:
                            obstacles.append(pl.title_box.inflate(m / 2))
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
            sdx, sdy = DIRS[ss]
            ddx, ddy = DIRS[ds]
            S = (p0[0] + sdx * m, p0[1] + sdy * m)
            T = (p1[0] + ddx * m, p1[1] + ddy * m)
            try:
                mid, cost = find_path_cost(e.id, S, ss, T, OPP[ds], obstacles, routed, extra_x=(p0[0], p1[0]), extra_y=(p0[1], p1[1]))
            except RouteError as err:
                last_err = err
                continue
            score = cost + 4.0 * (MARGINS[0] - m)  # mild preference for more clearance
            if best is None or score < best[0] - 1e-9:
                best = (score, _simplify([p0] + mid + [p1]))
            if cost <= abs(T[0] - S[0]) + abs(T[1] - S[1]) + 2 * BEND + 1e-6:
                break  # already a Manhattan-length route with <= 2 bends: smaller clearances cannot beat it
        if best is None:
            raise last_err
        routed.add(best[1], e.id)
        out[e.id] = Route(e.id, best[1], ss, ds)
    return out
