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
SAMPLE_W, BADGE_W, SWATCH_W, SWATCH_H = 30.0, 14.0, 18.0, 12.0
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
        sw = {"edge": SAMPLE_W, "badge": BADGE_W, "swatch": SWATCH_W}[kind] * ink
        tw, th = measure(label, ty["small_size"], False, ty["family"])
        sizes.append((sw, tw, th))
    h = max(max(th for _, _, th in sizes), BADGE_W * ink)
    total = sum(sw + INNER_GAP * ink + tw for sw, tw, _ in sizes) + ITEM_GAP * ink * (len(sizes) - 1)
    x0 = figure_box.cx - total / 2
    y0 = figure_box.bottom + recipe["spacing"]["gap"]["normal"]
    items, x = [], x0
    for (kind, key, label), (sw, tw, th) in zip(wanted, sizes):
        sh = {"edge": 2.0, "badge": BADGE_W, "swatch": SWATCH_H}[kind] * ink
        sample = Box(x, y0 + (h - sh) / 2, sw, sh)
        text = Box(x + sw + INNER_GAP * ink, y0 + (h - th) / 2, tw, th)
        items.append(LegendItem(kind, key, label, sample, text))
        x += sw + INNER_GAP * ink + tw + ITEM_GAP * ink
    return Legend(Box(x0, y0, total, h), items)
