"""Order of siblings, chosen to cross fewer lines (user 2026-11-14: avoid needless bends and crossings; blocks may
move). Measured on STORM: the six orders of its head/loss columns route with 2-13 crossings and 34-47 bends; a
straight centre-to-centre estimate after layout alone ranks them the same way (4/10/14) at ~0.01 s per order.

Only containers whose children are all leaves are reordered (panels keep their reading order), only into orders that
keep every connected pair of siblings in its original order (the flow direction stays), and the author's order
stays unless the estimate is strictly better. `layout.order: "fixed"` opts a container out.
"""
from __future__ import annotations

import itertools

MAX_CHILDREN = 6  # 720 orders at most per container


def _cross(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def estimate(bp, placed) -> tuple[int, float]:
    """(crossings, length) of straight lines between the edges' end centres."""
    segs = [((placed[e.src].box.cx, placed[e.src].box.cy), (placed[e.dst].box.cx, placed[e.dst].box.cy))
            for e in bp.edges if e.src in placed and e.dst in placed]
    n = sum(_cross(*segs[i], *segs[j]) for i in range(len(segs)) for j in range(i + 1, len(segs)))
    return n, sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in segs)


def _orders(bp, g):
    ids = [c.id for c in g.children]

    def top(x):
        return next((c for c in [x] + bp.ancestors(x) if c in ids), None)
    keep = set()
    for e in bp.edges:
        a, b = top(e.src), top(e.dst)
        if a and b and a != b:
            keep.add((a, b) if ids.index(a) < ids.index(b) else (b, a))
    return [p for p in itertools.permutations(ids) if all(p.index(a) < p.index(b) for a, b in keep)]


def candidates(bp) -> list:
    return [g for g in bp.groups() if g.layout.type in ("row", "column") and getattr(g.layout, "order", "auto") != "fixed"
            and 2 <= len(g.children) <= MAX_CHILDREN and all(not c.is_group for c in g.children)]


def auto_order(bp, recipe, solve) -> list[str]:
    """Reorder in place; returns notes (one per container changed). Coordinate descent over the containers, two
    passes: never worse than the author's order by the estimate."""
    groups = [g for g in candidates(bp) if len(_orders(bp, g)) > 1]
    if not groups:
        return []
    original = {g.id: [c.id for c in g.children] for g in groups}
    best = estimate(bp, solve(bp, recipe))
    for _ in range(2):
        changed = False
        for g in groups:
            cur = [c.id for c in g.children]
            for p in _orders(bp, g):
                if list(p) == cur:
                    continue
                g.children = [bp.index[x] for x in p]
                try:
                    score = estimate(bp, solve(bp, recipe))
                except Exception:  # noqa: BLE001 — an order the layout cannot place is simply not taken
                    score = None
                if score is not None and (score[0], round(score[1])) < (best[0], round(best[1])) and score[0] < best[0]:
                    best, cur, changed = score, list(p), True
                g.children = [bp.index[x] for x in cur]
        if not changed:
            break
    # containers whose children are linked (heads -> their losses): one at a time each move breaks the pairing and
    # looks worse, so they are also tried together (STORM: the best head/loss order needs both columns turned)
    for i, g1 in enumerate(groups):
        k1 = {c.id for c in g1.children}
        for g2 in groups[i + 1:]:
            k2 = {c.id for c in g2.children}
            if not any((e.src in k1 and e.dst in k2) or (e.src in k2 and e.dst in k1) for e in bp.edges):
                continue
            o1, o2 = _orders(bp, g1), _orders(bp, g2)
            if len(o1) * len(o2) > 720:
                continue
            cur = ([c.id for c in g1.children], [c.id for c in g2.children])
            for p1 in o1:
                for p2 in o2:
                    if (list(p1), list(p2)) == cur:
                        continue
                    g1.children, g2.children = [bp.index[x] for x in p1], [bp.index[x] for x in p2]
                    try:
                        score = estimate(bp, solve(bp, recipe))
                    except Exception:  # noqa: BLE001
                        score = None
                    if score is not None and score[0] < best[0]:
                        best, cur = score, (list(p1), list(p2))
                    g1.children, g2.children = [bp.index[x] for x in cur[0]], [bp.index[x] for x in cur[1]]
    return [f"'{g.id}' reordered {original[g.id]} -> {[c.id for c in g.children]} (fewer line crossings; "
            "layout order \"fixed\" keeps yours)" for g in groups if [c.id for c in g.children] != original[g.id]]
