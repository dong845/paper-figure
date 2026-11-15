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
    "loss:end": "loss (one-sided)",
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
        k = e.kind + (":end" if getattr(e, "heads", "auto") == "end" and e.kind == "loss" else "")
        if k != "data" and k not in kinds:
            kinds.append(k)
    out += [("edge", k, EDGE_LABELS.get(k) or EDGE_LABELS[k.split(":")[0]]) for k in kinds]
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
    meanings = getattr(bp, "tone_meanings", None) or {}
    if getattr(bp.figure, "tone_legend", False) and meanings:
        used = []
        for el in bp.index.values():
            t = getattr(el, "tone", None)
            if t and t in meanings and t not in used:
                used.append(t)
        out += [("tone", t, str(meanings[t])) for t in used]
    out += [("note", f"note{i}", t) for i, t in enumerate(bp.figure.legend_notes)]
    names = getattr(bp.figure, "legend_labels", None) or {}
    return [(kind, key, names.get(key, label)) for kind, key, label in out]


CELL = 4.0  # px grid for finding empty space
WIDE_ASPECT = 2.3  # KB overview median w/h: a narrower figure takes a right column (widens it); a wider one a band
MARGIN = 10.0  # clearance between a legend placed inside the figure and anything else


def _free_spot(area: Box, w: float, h: float, obstacles: list) -> tuple[float, float] | None:
    """Top-left corner of a free w x h window in a CORNER of ``area`` (flush with one side and with the top or the
    bottom, no obstacle within MARGIN), bottom-right first; None if no corner is free. A key is read last and
    looked up often: every published method figure studied (2026-11-15: ALBEF, MGCA, ImageBind, BLIP-2, …) keeps it
    at the outer edge or a corner — a free hole between rows reads as content and splits the figure."""
    W, H = w + 2 * MARGIN, h + 2 * MARGIN
    cols, rows = int(area.w // CELL) + 1, int(area.h // CELL) + 1
    cw, ch = int(-(-W // CELL)), int(-(-H // CELL))
    if cw > cols or ch > rows:
        return None
    occ = [[0] * cols for _ in range(rows)]
    for b in obstacles:
        x0, y0 = max(0, int((b.x - area.x) // CELL)), max(0, int((b.y - area.y) // CELL))
        x1, y1 = min(cols - 1, int((b.right - area.x) // CELL)), min(rows - 1, int((b.bottom - area.y) // CELL))
        for r in range(y0, y1 + 1):
            row = occ[r]
            for c in range(x0, x1 + 1):
                row[c] = 1
    sat = [[0] * (cols + 1) for _ in range(rows + 1)]
    for r in range(rows):
        acc = 0
        for c in range(cols):
            acc += occ[r][c]
            sat[r + 1][c + 1] = sat[r][c + 1] + acc
    corners = [(area.right, area.bottom), (area.x, area.bottom), (area.right, area.y), (area.x, area.y)]
    best = None
    for r in range(rows - ch + 1):
        for c in range(cols - cw + 1):
            if sat[r + ch][c + cw] - sat[r][c + cw] - sat[r + ch][c] + sat[r][c]:
                continue
            if not ((c == 0 or c + cw >= cols - 1) and (r == 0 or r + ch >= rows - 1)):
                continue  # not in a corner: a hole between content
            x, y = area.x + c * CELL, area.y + r * CELL
            cx, cy = x + W / 2, y + H / 2
            d = min((abs(cx - kx) + abs(cy - ky)) * (1.0 + 0.15 * i) for i, (kx, ky) in enumerate(corners))
            if best is None or d < best[0]:
                best = (d, x + MARGIN, y + MARGIN)
    return None if best is None else (best[1], best[2])


def build(bp: Blueprint, recipe: Recipe, figure_box: Box, obstacles: list | None = None) -> Legend | None:
    if bp.figure.legend == "none":
        return None
    wanted = _wanted(bp)
    if not wanted:
        return None
    ty = recipe["typography"]
    ink = recipe.data.get("ink_scale", 1.0)
    sizes = []
    for kind, key, label in wanted:
        sw = {"edge": SAMPLE_W, "badge": BADGE_W, "swatch": SWATCH_W, "tone": SWATCH_W, "op": BADGE_W, "note": 0.0}[kind] * ink
        tw, th = measure(label, ty["small_size"], False, ty["family"])
        sizes.append((sw, tw, th))
    h = max(max(th for _, _, th in sizes), BADGE_W * ink)
    widths = [sw + (INNER_GAP * ink if sw else 0.0) + tw for sw, tw, _ in sizes]
    limit = max(figure_box.w, max(widths))

    def row_w(idx):
        return sum(widths[k] for k in idx) + ITEM_GAP * ink * (len(idx) - 1)

    n = len(widths)
    row_gap = 6.0 * ink

    def split(nr):
        base, extra = divmod(n, nr)
        cand, start = [], 0
        for r_i in range(nr):
            size = base + (1 if r_i < extra else 0)
            cand.append(list(range(start, start + size)))
            start += size
        return cand

    where = getattr(bp.figure, "legend_at", "auto") or "auto"
    inside = None
    if obstacles is not None and where in ("auto", "corner"):  # first choice: an empty area of the figure itself, so the figure does not grow
        for nr in range(1, n + 1):
            cand = split(nr)
            cw = max(row_w(r) for r in cand)
            chh = nr * h + (nr - 1) * row_gap
            spot = _free_spot(figure_box, cw, chh, obstacles)
            if spot is not None:
                inside = (cand, spot)
                break
    col_h = n * h + (n - 1) * row_gap
    if inside is not None:
        rows, (x_left, y0) = inside
        centred = False
    elif where == "right" or (where == "auto" and obstacles is not None and col_h <= figure_box.h + 1e-6
                              and figure_box.w < WIDE_ASPECT * figure_box.h and not recipe.data.get("legend_no_column")):
        # no empty spot: a column on the right (the bottom band was rejected as the template look, and a column
        # keeps an overview wide); the band below stays the last resort for a legend taller than the figure
        rows = [[k] for k in range(n)]
        x_left, y0 = figure_box.right + recipe["spacing"]["gap"]["normal"], figure_box.y
        centred = False
    else:
        rows = [list(range(n))]
        for nr in range(1, n + 1):  # fewest rows that fit, items split as evenly as possible (no orphan row)
            cand = split(nr)
            if all(row_w(r) <= limit + 1e-6 for r in cand):
                rows = cand
                break
        nrows = len(rows)
        band_h = nrows * h + (nrows - 1) * row_gap
        y0 = (figure_box.y - recipe["spacing"]["gap"]["normal"] - band_h if where == "top"
              else figure_box.bottom + recipe["spacing"]["gap"]["normal"])
        centred = True
    items = []
    total = 0.0
    for r_i, row in enumerate(rows):
        row_w = sum(widths[k] for k in row) + ITEM_GAP * ink * (len(row) - 1)
        total = max(total, row_w)
        x = figure_box.cx - row_w / 2 if centred else x_left
        y = y0 + r_i * (h + row_gap)
        for k in row:
            (kind, key, label), (sw, tw, th) = wanted[k], sizes[k]
            sh = {"edge": 2.0, "badge": BADGE_W, "swatch": SWATCH_H, "tone": SWATCH_H, "op": BADGE_W, "note": 0.0}[kind] * ink
            tx = x + sw + (INNER_GAP * ink if sw else 0.0)
            items.append(LegendItem(kind, key, label, Box(x, y + (h - sh) / 2, sw, sh), Box(tx, y + (h - th) / 2, tw, th)))
            x += widths[k] + ITEM_GAP * ink
    x0 = figure_box.cx - total / 2 if centred else x_left
    h = len(rows) * h + (len(rows) - 1) * row_gap
    return Legend(Box(x0, y0, total, h), items)
