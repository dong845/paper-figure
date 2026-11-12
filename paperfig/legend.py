"""Auto legend (on-canvas row under the figure) for non-default visual codes."""
from __future__ import annotations

from dataclasses import dataclass

from .blueprint import Blueprint
from .geometry import Box
from .measure import measure
from .styles import Recipe

EDGE_LABELS = {
    "skip": "skip connection",
    "loss": "loss (compares both ends)",
    "train_only": "training only",
    "infer_only": "inference only",
    "grad": "gradient",
    "control": "control / conditioning",
}
BADGE_LABELS = {"frozen": "frozen", "trainable": "trainable"}
SAMPLE_W, BADGE_W, SWATCH_W, SWATCH_H = 30.0, 14.0, 28.0, 13.0  # swatch reads as a module box, not a token
INNER_GAP, ITEM_GAP = 6.0, 20.0


@dataclass
class LegendItem:
    kind: str  # "edge" | "badge" | "swatch"
    key: str
    label: str
    sample: Box
    text: Box


@dataclass
class Legend:
    box: Box
    items: list[LegendItem]


def _wanted(bp: Blueprint) -> list[tuple[str, str, str]]:
    out = []
    if any(el.role == "proposed" for el in bp.index.values()):
        out.append(("swatch", "proposed", "proposed (ours)"))
    kinds = []
    for e in bp.edges:
        if e.kind != "data" and e.kind not in kinds:
            kinds.append(e.kind)
    out += [("edge", k, EDGE_LABELS[k]) for k in kinds]
    badges = []
    for n in bp.leaves():
        for b in n.badges:
            if b not in badges:
                badges.append(b)
    out += [("badge", b, BADGE_LABELS[b]) for b in badges]
    from .shapes import OPS
    ops = []
    for n in bp.leaves():
        if n.op and n.op not in ops:
            ops.append(n.op)
    out += [("op", k, OPS[k][1]) for k in ops]
    return out


def build(bp: Blueprint, recipe: Recipe, figure_box: Box) -> Legend | None:
    if bp.figure.legend == "none":
        return None
    wanted = _wanted(bp)
    if not wanted:
        return None
    ty = recipe["typography"]
    ink = recipe.data.get("ink_scale", 1.0)
    sizes = []
    for kind, key, label in wanted:
        sw = {"edge": SAMPLE_W, "badge": BADGE_W, "swatch": SWATCH_W, "op": BADGE_W}[kind] * ink
        tw, th = measure(label, ty["small_size"], False, ty["family"])
        sizes.append((sw, tw, th))
    h = max(max(th for _, _, th in sizes), BADGE_W * ink)
    widths = [sw + INNER_GAP * ink + tw for sw, tw, _ in sizes]
    limit = max(figure_box.w, max(widths))
    rows, cur, cur_w = [], [], 0.0  # wrap items into rows no wider than the figure
    for k, w in enumerate(widths):
        add = w if not cur else w + ITEM_GAP * ink
        if cur and cur_w + add > limit:
            rows.append(cur)
            cur, cur_w = [], 0.0
            add = w
        cur.append(k)
        cur_w += add
    if cur:
        rows.append(cur)
    row_gap = 6.0 * ink
    y0 = figure_box.bottom + recipe["spacing"]["gap"]["normal"]
    items = []
    total = 0.0
    for r_i, row in enumerate(rows):
        row_w = sum(widths[k] for k in row) + ITEM_GAP * ink * (len(row) - 1)
        total = max(total, row_w)
        x = figure_box.cx - row_w / 2
        y = y0 + r_i * (h + row_gap)
        for k in row:
            (kind, key, label), (sw, tw, th) = wanted[k], sizes[k]
            sh = {"edge": 2.0, "badge": BADGE_W, "swatch": SWATCH_H, "op": BADGE_W}[kind] * ink
            items.append(LegendItem(kind, key, label, Box(x, y + (h - sh) / 2, sw, sh), Box(x + sw + INNER_GAP * ink, y + (h - th) / 2, tw, th)))
            x += widths[k] + ITEM_GAP * ink
    x0 = figure_box.cx - total / 2
    h = len(rows) * h + (len(rows) - 1) * row_gap
    return Legend(Box(x0, y0, total, h), items)
