"""Brackets: labelled spans over a set of elements (e.g. overlapping training stages). They are drawn
outside the content in lanes (overlapping brackets get separate lanes, narrowest innermost), reserve
their space in the layout, and are obstacles for edge routing."""
from __future__ import annotations

from dataclasses import dataclass

from .blueprint import Blueprint
from .geometry import Box
from .measure import measure
from .styles import Recipe

TICK, LANE_GAP, LABEL_PAD = 7.0, 6.0, 3.0


@dataclass
class BracketGeom:
    aid: str
    side: str
    x0: float
    x1: float
    y: float  # y of the bracket's long line
    tick_end: float  # y where the ticks end (towards the content)
    label: Box

    @property
    def band(self) -> Box:
        top = min(self.label.y, self.y, self.tick_end)
        bot = max(self.label.bottom, self.y, self.tick_end)
        x0 = min(self.x0, self.label.x)
        x1 = max(self.x1, self.label.right)
        return Box(x0, top, x1 - x0, bot - top)


def _span(bp: Blueprint, placed, a) -> tuple[float, float]:
    boxes = [placed[c].footprint for c in a.covers]
    return min(b.x for b in boxes), max(b.right for b in boxes)


def lane_height(recipe: Recipe) -> float:
    ink = recipe.data.get("ink_scale", 1.0)
    _, th = measure("Ag", recipe["typography"]["small_size"])
    return th + LABEL_PAD + TICK * ink + LANE_GAP * ink


def assign_lanes(bp: Blueprint, placed, recipe: Recipe) -> dict[str, tuple[str, int]]:
    """{annotation id: (side, lane)}; lane 0 is closest to the content."""
    out = {}
    for side in ("top", "bottom"):
        items = []
        for a in bp.annotations:
            if a.side != side:
                continue
            x0, x1 = _span(bp, placed, a)
            lw, _ = measure(a.label, recipe["typography"]["small_size"], True)
            cx = (x0 + x1) / 2
            items.append((x1 - x0, min(x0, cx - lw / 2) - 8, max(x1, cx + lw / 2) + 8, a.id))
        lanes: list[list[tuple[float, float]]] = []
        for _, lo, hi, aid in sorted(items):
            k = 0
            while k < len(lanes) and any(not (hi <= l0 or lo >= l1) for l0, l1 in lanes[k]):
                k += 1
            if k == len(lanes):
                lanes.append([])
            lanes[k].append((lo, hi))
            out[aid] = (side, k)
    return out


def lanes_per_side(bp: Blueprint, placed, recipe: Recipe) -> dict[str, int]:
    n = {"top": 0, "bottom": 0}
    for side, k in assign_lanes(bp, placed, recipe).values():
        n[side] = max(n[side], k + 1)
    return n


def place(bp: Blueprint, placed, recipe: Recipe, routes=None) -> dict[str, BracketGeom]:
    if not bp.annotations:
        return {}
    lanes = assign_lanes(bp, placed, recipe)
    root = placed[bp.root.id].box
    lh = lane_height(recipe)
    ink = recipe.data.get("ink_scale", 1.0)
    covered = [placed[c].footprint for a in bp.annotations for c in a.covers]
    content_top = min([b.y for b in covered])
    content_bot = max([b.bottom for b in covered])
    n = lanes_per_side(bp, placed, recipe)
    out = {}
    for a in bp.annotations:
        side, k = lanes[a.id]
        x0, x1 = _span(bp, placed, a)
        lw, lh_text = measure(a.label, recipe["typography"]["small_size"], True)
        cx = (x0 + x1) / 2
        if side == "top":
            lane_top = root.y + (n["top"] - 1 - k) * lh  # outermost lane at the very top
            y = lane_top + lh_text + LABEL_PAD
            label = Box(cx - lw / 2, lane_top, lw, lh_text)
            tick_end = y + TICK * ink
        else:
            lane_top = root.bottom - (n["bottom"] - k) * lh
            y = lane_top + LANE_GAP * ink
            tick_end = y - TICK * ink
            label = Box(cx - lw / 2, y + LABEL_PAD, lw, lh_text)
        out[a.id] = BracketGeom(a.id, side, x0, x1, y, tick_end, label)
    return out
