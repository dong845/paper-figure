"""Visual grammar (round 3, the user's figure-design guide §4 and §6.3): one meaning per colour, a recurring
representation keeps one symbol, the contribution's highlight survives a grayscale print, and at most two zoom-ins.
Reads the drawn cells, so it judges what was rendered, not what the blueprint meant."""
from __future__ import annotations

from . import color
from .drawio import parse_cells
from .lint import Finding

NEUTRAL = {"gray", "grey", "white", "neutral"}
GRAY_DL_MIN = 12.0  # L* difference a grayscale reader still sees as "a different box"


def _sig(cell) -> tuple:
    st = cell.style
    return (st.get("shape", "rect"), (st.get("fillColor") or "").lower(), (st.get("strokeColor") or "").lower())


def _l_gray(hex_: str) -> float | None:
    if not (isinstance(hex_, str) and hex_.startswith("#")):
        return None
    return color.lab(color.simulate(hex_, "gray"))[0]


def _num(v, default=1.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def gray_highlight(proposed: list[dict], reused: list[dict], prop_values=None, reused_values=None) -> str | None:
    """A message when the proposed parts differ from the reused ones only by hue: in grayscale their fills are
    within GRAY_DL_MIN in L* and neither a heavier outline nor a bold name sets them apart."""
    pl = [x for x in (_l_gray(s.get("fillColor")) for s in proposed) if x is not None]
    rl = [x for x in (_l_gray(s.get("fillColor")) for s in reused) if x is not None]
    if not pl or not rl:
        return None
    dl = min(abs(a - b) for a in pl for b in rl)
    if dl >= GRAY_DL_MIN:
        return None
    pw = min(_num(s.get("strokeWidth")) for s in proposed)
    rw = max(_num(s.get("strokeWidth")) for s in reused)
    bold = lambda s, v: bool(int(_num(s.get("fontStyle"), 0)) & 1) or "<b>" in (v or "")
    pv = list(prop_values or [""] * len(proposed))
    rv = list(reused_values or [""] * len(reused))
    if pw >= rw + 0.5 or (all(bold(s, v) for s, v in zip(proposed, pv)) and not any(bold(s, v) for s, v in zip(reused, rv))):
        return None
    return (f"in grayscale the proposed parts and the reused ones differ by only ΔL*={dl:.1f} (< {GRAY_DL_MIN:.0f}) "
            "and nothing but hue sets them apart — use a darker/lighter fill, a heavier outline or a bold name")


def check_grammar(bp, drawio_path, recipe, plan: dict | None) -> list[Finding]:
    plan = plan or {}
    cells = parse_cells(drawio_path.read_text(encoding="utf-8"))
    drawn = {el.id: cells.get(f"pf-{el.id}") for el in bp.index.values() if el is not bp.root}
    drawn = {k: c for k, c in drawn.items() if c is not None}
    out: list[Finding] = []

    for k in plan.get("key_representations", []) or []:
        sigs = {i: _sig(drawn[i]) for i in k.get("ids", []) if i in drawn}
        if len(set(sigs.values())) > 1:
            first = next(iter(sigs.values()))
            odd = [i for i, s in sigs.items() if s != first]
            out.append(Finding("key-rep-inconsistent", "warn", odd,
                               f"'{k.get('name')}' is drawn in {len(set(sigs.values()))} different ways — a recurring "
                               "representation keeps one shape and colour everywhere so the reader can follow it"))

    sem = plan.get("color_semantics")
    if isinstance(sem, dict):
        roles = recipe["palette"].get("roles", {})
        used: dict[str, set] = {}
        for i, c in drawn.items():
            el = bp.index[i]
            if el.is_group and el.frame == "none":
                continue
            # the tone the author chose (or the role's), not a reverse lookup of the fill: styles may paint several
            # tones with one fill (editorial-minimal: white), which made the lookup name the wrong tone
            t = getattr(el, "tone", None) or (roles.get(el.role) or {}).get("tone")
            if t and t not in NEUTRAL:
                used.setdefault(t, set()).add(el.role or "")
        undeclared = sorted(t for t in used if t not in sem)
        if undeclared:
            out.append(Finding("tone-undeclared", "warn", [], f"tones without a declared meaning: {', '.join(undeclared)} — "
                               "add them to the plan's color_semantics or drop them (one meaning per colour)"))
        for t, roles in sorted(used.items()):
            if "proposed" in roles and roles - {"proposed", ""}:
                out.append(Finding("tone-two-meanings", "warn", [], f"tone '{t}' marks both the proposed parts and "
                                   f"{', '.join(sorted(roles - {'proposed', ''}))} parts — the highlight colour must mean one thing"))

    prop = [c for i, c in drawn.items() if bp.index[i].role == "proposed" and not bp.index[i].is_group]
    reused = [c for i, c in drawn.items() if bp.index[i].role == "reused" and not bp.index[i].is_group]
    msg = gray_highlight([c.style for c in prop], [c.style for c in reused],
                         [c.value for c in prop], [c.value for c in reused])
    if msg:
        out.append(Finding("gray-highlight", "warn", [], msg))

    from .glyphs import SCHEMATIC
    for el in bp.leaves():
        if el.visual == "glyph" and el.glyph in SCHEMATIC and not el.illustrative:
            out.append(Finding("schematic-unmarked", "warn", [el.id], f"the {el.glyph} glyph '{el.id}' looks like data — set "
                               "\"illustrative\": true and say \"schematic\" in the caption, so nobody reads it as a result"))

    panels = [el.id for el in bp.index.values() if el.is_group and el.detail_of]
    if len(panels) > 2:
        out.append(Finding("zoom-ins-many", "warn", panels, f"{len(panels)} zoom-in panels — expand only the one or two "
                           "mechanisms a reader most needs; the rest belongs in the text or another figure"))
    return out
