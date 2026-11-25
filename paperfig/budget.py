"""Width budget (user, 2026-11-25: the agent needs the instrument used to compose VERA by hand).

The smallest text prints at  width_in * 72 * size / figure_width,  so a figure's text size is set by how many text
sizes wide it is — and that width is set by one chain of elements: the band that is widest, inside it the panel
its peers were stretched to (grid discipline makes peers one width), inside that panel its widest element (often a
title or a one-line formula, not the longest label in the figure). Shrinking anything else changes nothing.
"""
from __future__ import annotations

from .layout import _Solver, solve


def _alone(bp, recipe, el) -> float:
    """An element's width laid out on its own, before any peer or parent stretches it."""
    s = _Solver(bp, recipe)
    if el.is_group:
        return s.group(el).shape_w
    return s.leaf(el).foot(s.sp["label_gap"])[0]


def _natural(bp, recipe, g) -> tuple[float, dict]:
    """A group's natural width, and each child's (each on its own: inside the group they are already stretched)."""
    return _alone(bp, recipe, g), {c.id: _alone(bp, recipe, c) for c in g.children}


def _title_w(recipe, g) -> float:
    from .measure import measure
    from .styles import is_bold_title, title_family, title_lead
    if not g.title:
        return 0.0
    ty = recipe["typography"]
    return measure(g.title, ty["title_size"], is_bold_title(recipe, g), title_family(recipe))[0] + title_lead(recipe, g)


def budget(bp, recipe, width_in: float) -> dict:
    from .lint import MIN_FONT_PT, hard_floor
    placed = solve(bp, recipe)
    xs = [p.box for p in placed.values()]
    W = max(b.right for b in xs) - min(b.x for b in xs)
    ty = recipe["typography"]
    smallest = min(ty["size"], ty["small_size"])
    scale = 72.0 * width_in / W
    floor = hard_floor(bp.figure, width_in)
    nat = {}
    for g in bp.groups():
        if g is not bp.root:
            nat[g.id] = _natural(bp, recipe, g)
    bands = sorted(((nat[c.id][0] if c.is_group else placed[c.id].box.w, c.id) for c in bp.root.children), reverse=True)
    setters = []
    for g in bp.groups():
        if g is bp.root or g.frame == "none":
            continue
        w_nat, kids = nat[g.id]
        w = placed[g.id].box.w
        par = bp.index[bp.parent[g.id]]
        peers = [c for c in par.children if c is not g and c.is_group and c.frame != "none" and c.id in placed]
        stretched = [c.id for c in peers if placed[c.id].box.w > nat[c.id][0] + 0.5 and abs(placed[c.id].box.w - w) < 1]
        if stretched and w <= w_nat + 0.5:
            parts = sorted(((cw, cid) for cid, cw in kids.items()), reverse=True)[:2]
            tw = _title_w(recipe, g)
            if tw and (not parts or tw >= parts[0][0]):
                parts.insert(0, (tw, "title"))
            setters.append({"panel": g.id, "natural": round(w_nat), "peers": stretched,
                            "widest": [(cid, round(cw)) for cw, cid in parts[:2]]})
    return {"width": round(W), "sizes_wide": round(W / ty["size"]), "body_pt": round(ty["size"] * scale, 2),
            "smallest_pt": round(smallest * scale, 2), "floor_pt": floor, "goal_pt": MIN_FONT_PT,
            "width_for_floor": round(72.0 * width_in * smallest / floor), "width_for_goal": round(72.0 * width_in * smallest / MIN_FONT_PT),
            "bands": [(bid, round(bw)) for bw, bid in bands[:3]], "setters": setters}


def describe(b: dict) -> str:
    lines = [f"{b['width']} units wide = {b['sizes_wide']} text sizes: body prints {b['body_pt']} pt, smallest "
             f"{b['smallest_pt']} pt (floor {b['floor_pt']}, goal {b['goal_pt']}): fits the floor at <= "
             f"{b['width_for_floor']} units, the goal at <= {b['width_for_goal']}"]
    if b["bands"]:
        lines.append("widest at the top level: " + ", ".join(f"{i} ({w})" for i, w in b["bands"]))
    for s in b["setters"]:
        what = ", ".join(f"{i} ({w})" for i, w in s["widest"])
        lines.append(f"'{s['panel']}' sets the width of {', '.join(s['peers'])} (natural {s['natural']}): its widest — "
                     f"{what}. Break that title / line, stack its side-by-side parts, or move a long formula out")
    return "\n".join(lines)


def hint(b: dict) -> str:
    """One sentence for lint min-font: where to cut, not just how much."""
    if b["setters"]:
        s = max(b["setters"], key=lambda x: x["natural"])
        what = ", ".join(f"{i} ({w})" for i, w in s["widest"])
        return (f"the width comes from panel '{s['panel']}' ({s['natural']} wide; its peers {', '.join(s['peers'])} "
                f"are stretched to it) — narrow its widest part: {what}")
    if b["bands"]:
        return f"the width comes from '{b['bands'][0][0]}' ({b['bands'][0][1]} wide)"
    return ""
