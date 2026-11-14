"""Visual grammar (round 3, the user's figure-design guide §4 and §6.3): one meaning per colour, a recurring
representation keeps one symbol, the contribution's highlight survives a grayscale print, and at most two zoom-ins.
Reads the drawn cells, so it judges what was rendered, not what the blueprint meant."""
from __future__ import annotations

from . import color
from .drawio import parse_cells
from .blueprint import plain_text
from .lint import Finding

NEUTRAL = {"gray", "grey", "white", "neutral"}
GRAY_DL_MIN = 12.0  # L* difference a grayscale reader still sees as "a different box"


LOSS_NODES_MAX, LOSS_EDGES_MAX = 2, 4  # corpus overviews: at most 1 loss box and 3 loss arrows


def _sig(cell) -> tuple:
    st = cell.style
    return (st.get("shape", "rect"), (st.get("fillColor") or "").lower(), (st.get("strokeColor") or "").lower())


def _l_gray(hex_: str) -> float | None:
    if not (isinstance(hex_, str) and hex_.startswith("#")):
        return None
    return color.lab(color.simulate(hex_, "gray"))[0]


def _plain(v) -> str:
    import re
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>|\$|\\[a-zA-Z]+", "", str(v or "")))


def _num(v, default=1.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


SYMBOLS_MAX = 3


def _bare_symbol(label: str) -> bool:
    """A label that is only a variable: TeX alone, or a short token without a word in it ('m^k', '{x_i}', 'h_t')."""
    import re
    t = plain_text(label).strip()
    words = re.findall(r"[A-Za-z]{3,}", re.sub(r"\\[A-Za-z]+|\$[^$]*\$", " ", label))
    return bool(t) and not words


def gray_highlight(proposed: list[dict], reused: list[dict], prop_values=None, reused_values=None) -> str | None:
    """A message when the proposed parts differ from the reused ones only by hue: in grayscale their fills are
    within GRAY_DL_MIN in L* and neither a heavier outline nor a bold name sets them apart."""
    # only filled parts take part: an unfilled glyph strip with its name below (TWM: the balanced sampler) has no
    # grey fill to confuse, and counting it made the bold-name remedy impossible to satisfy
    pv = list(prop_values or [""] * len(proposed))
    rv = list(reused_values or [""] * len(reused))
    pf = [(s, v) for s, v in zip(proposed, pv) if _l_gray(s.get("fillColor")) is not None]
    rf = [(s, v) for s, v in zip(reused, rv) if _l_gray(s.get("fillColor")) is not None]
    if not pf or not rf:
        return None
    proposed, pv = [s for s, _ in pf], [v for _, v in pf]
    reused, rv = [s for s, _ in rf], [v for _, v in rf]
    pl = [_l_gray(s.get("fillColor")) for s in proposed]
    rl = [_l_gray(s.get("fillColor")) for s in reused]
    dl = min(abs(a - b) for a in pl for b in rl)
    if dl >= GRAY_DL_MIN:
        return None
    pw = min(_num(s.get("strokeWidth")) for s in proposed)
    rw = max(_num(s.get("strokeWidth")) for s in reused)
    bold = lambda s, v: bool(int(_num(s.get("fontStyle"), 0)) & 1) or "<b>" in (v or "")
    named = [(s, v) for s, v in zip(proposed, pv) if len(_plain(v)) > 2] or list(zip(proposed, pv))  # a symbol
    if pw >= rw + 0.5 or (all(bold(s, v) for s, v in named) and not any(bold(s, v) for s, v in zip(reused, rv))):  # (E, z) keeps its italics
        return None
    return (f"in grayscale the proposed parts and the reused ones differ by only ΔL*={dl:.1f} (< {GRAY_DL_MIN:.0f}) "
            "and nothing but hue sets them apart — use a darker/lighter fill, a heavier outline or a bold name")


WASHED_L, WASHED_C = 92.0, 12.0  # a fill lighter and greyer than this reads as white in print
FALLBACK_ASPECT = (2.25, 1.68, 59)  # KB overview cards, measured 2026-11-13: median w/h, 25th percentile, n


def washed_out(fills: list[str]) -> bool:
    """True when no fill carries visible colour: every chromatic fill is lighter than L* 92 and greyer than C 12
    (the user: '颜色感觉不少都是白色'; KB overview figures' colours: median chroma 24 at L* 76)."""
    chrom = []
    for f in fills:
        if isinstance(f, str) and f.startswith("#") and len(f) == 7:
            L, a, b = color.lab(f)
            c = (a * a + b * b) ** 0.5
            if c > 2.5:
                chrom.append((L, c))
    return not any(L <= WASHED_L or c >= WASHED_C for L, c in chrom)


def reference_aspect(figure_type: str) -> tuple[float, float, int]:
    """(median, 25th percentile, n) of w/h over the knowledge base's measured cards of this figure type."""
    try:
        from .kb import load_kb
        a = sorted(float(c["measured"]["aspect"]) for c in load_kb().cards.values()
                   if c.get("figure_type") == figure_type and (c.get("measured") or {}).get("aspect"))
    except Exception:  # the KB is advisory here: never let it break a build
        a = []
    if len(a) < 10:
        return FALLBACK_ASPECT
    return a[len(a) // 2], a[len(a) // 4], len(a)


def aspect_floor(width, p25: float) -> float:
    """w/h below which a figure is a tower: a page-wide figure is judged against the references (p25); a single
    column cannot reach that at the font floor, so there only a figure clearly taller than wide is flagged."""
    narrow = width == "single" or (isinstance(width, (int, float)) and float(width) < 4.0)
    return 0.8 if narrow else p25


DETOUR_MAX = 2.2  # route length / straight distance above which an arrow reads as a detour (provisional)


def detour_ratio(points) -> float:
    """Polyline length over the straight distance between its ends (1.0 = straight)."""
    if len(points) < 2:
        return 1.0
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(points, points[1:]))
    (x0, y0), (x1, y1) = points[0], points[-1]
    direct = max(abs(x1 - x0) + abs(y1 - y0), 1.0)
    return length / direct


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
            unused = sorted(k for k in sem if k not in used and k not in NEUTRAL)  # neutral tones are never "used"
            hint = (f"; declared but never drawn: {', '.join(unused)} — keys are the blueprint's tone names, not the "
                    "colours a style paints them in (editorial-minimal draws 'orange' as teal)") if unused else ""
            out.append(Finding("tone-undeclared", "warn", [], f"tones without a declared meaning: {', '.join(undeclared)} — "
                               f"add them to the plan's color_semantics or drop them (one meaning per colour){hint}"))
        for t, roles in sorted(used.items()):
            if "proposed" in roles and roles - {"proposed", ""}:
                out.append(Finding("tone-two-meanings", "warn", [], f"tone '{t}' marks both the proposed parts and "
                                   f"{', '.join(sorted(roles - {'proposed', ''}))} parts — the highlight colour must mean one thing"))

    if getattr(bp.figure, "font", "sans") == "serif" and str(bp.figure.venue).lower() == "nature":
        out.append(Finding("font-family", "warn", [], "Nature asks for sans-serif lettering (Helvetica or Arial), the "
                           "same in every figure (kb typography 'nature-lettering') — use figure.font \"sans\""))
    if bp.figure.type in ("overview", "teaser"):  # an overview shows the data path; its objective is said once
        contrib = {i for c in plan.get("contributions", []) or [] if isinstance(c, dict) for i in c.get("ids", [])}
        # a contribution drawn as a group (SimCSE: the similarity grid is the loss) covers what is inside it
        inside = {x for x in bp.index if any(g in contrib and bp.index[g].is_group for g in bp.ancestors(x))}
        inside |= {g for g in contrib if g in bp.index and bp.index[g].is_group}
        kept = {el.id for el in bp.leaves() if el.role == "loss" and el.id in contrib}  # a loss that IS a contribution
        loss_nodes = [el.id for el in bp.leaves() if el.role == "loss" and el.id not in contrib and el.id not in inside]
        kept |= inside  # edges into a contributed group (a loss drawn as a grid) are that contribution's own
        loss_edges = [e.id for e in bp.edges if e.kind in ("loss", "grad") and e.src not in kept and e.dst not in kept]
        if plan.get("contributions") and loss_nodes:  # a routine loss is said in the caption (user, 2026-11-14)
            out.append(Finding("loss-conventional", "warn", loss_nodes[:6], f"{', '.join(loss_nodes[:6])}: a drawn loss "
                               "that is not one of the plan's contributions — a conventional loss (MSE, L1, cross-entropy, "
                               "a standard KL or contrastive term) goes in the caption; draw a loss only when it is new or "
                               "part of the contribution, and then list it in contributions"))
        if len(loss_nodes) > LOSS_NODES_MAX or len(loss_edges) > LOSS_EDGES_MAX:
            out.append(Finding("loss-heavy", "warn", loss_nodes[:6], f"{len(loss_nodes)} loss boxes and {len(loss_edges)} "
                               "loss arrows in an overview — authors draw the prediction outputs (x̂, r̂ …) and name "
                               "the objective once (one loss box, or the caption); keep a loss box only for a loss that "
                               "is a contribution (list it in the plan's contributions)"))
    sym = [e.id for e in bp.edges if e.label and _bare_symbol(e.label)]
    if len(sym) > SYMBOLS_MAX:  # intermediate variables on every arrow (user on VS-Net: m, u, x add clutter)
        out.append(Finding("symbol-heavy", "info", sym[:8], f"{len(sym)} edges are labelled only with a symbol — keep a "
                           "variable on an arrow only where the caption or text relies on it, or where two flows would "
                           "otherwise be confused"))
    for note in getattr(bp, "order_notes", None) or []:
        out.append(Finding("auto-order", "info", [], note))
    for note in getattr(bp, "bundle_notes", None) or []:
        out.append(Finding("bundle-skipped", "info", [], note))
    gap_n = recipe["spacing"]["gap"].get("normal", 0.0) if recipe is not None else 0.0
    for k, (need, eid) in sorted((getattr(bp, "label_gaps", None) or {}).items(), key=lambda kv: -kv[1][0])[:3]:
        if gap_n and need > 3 * gap_n:
            e = next((x for x in bp.edges if x.id == eid), None)
            out.append(Finding("gap-by-label", "info", [eid], f"the label of edge {eid} ('{plain_text(e.label) if e else ''}') "
                               f"holds the gap it crosses at {need:.0f}px (a normal gap is {gap_n:.0f}px) — if the figure "
                               "is too wide or its text too small, shorten that label, move it to the caption, or put the "
                               "edge where the gap is wide anyway"))
    for gid, (unit, by, nc) in sorted((getattr(bp, "canvas_pitch", None) or {}).items()):
        if by is not None:
            el = bp.index[by]
            out.append(Finding("canvas-pitch", "info", [gid, by], f"canvas '{gid}': all {nc} columns are as wide as "
                               f"'{by}' needs over its {el.span[1]} column(s) ({unit:.0f} px each) — if the figure is too "
                               f"wide or its text too small, give '{by}' more columns"))

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

    fills = [(c.style.get("fillColor") or "").lower() for i, c in drawn.items()
             if not (bp.index[i].is_group and bp.index[i].frame == "none")]
    if washed_out(fills):
        out.append(Finding("palette-washed", "warn", [], "no fill carries visible colour (all near-white) — the figure "
                           "reads as white; give the contribution and each kind of representation its semantic tone "
                           "(top-venue overview figures' colours: median chroma ≈24 at L* ≈76)"))

    ftype = getattr(bp.figure, "type", None)
    if ftype in ("overview", "teaser"):
        from .lint import figure_bbox
        box = figure_bbox(cells, recipe)
        if box.h > 0:
            med, p25, n = reference_aspect(ftype)
            ar = box.w / box.h
            floor = aspect_floor(bp.figure.width, p25)
            if ar < floor:
                out.append(Finding("aspect-tall", "warn", [], f"the figure is {ar:.2f}:1 (w/h) — {ftype} figures in "
                                   f"top venues are wide: median {med:.2f}:1, three in four wider than {p25:.2f}:1 "
                                   f"({n} KB cards). Lay the main line out horizontally (input left, contribution "
                                   "centre, output right), put zoom-ins beside it or in one band, use the full text width"))

    for g in bp.groups():  # an aligned, titled frame: its title sits where the straight link would enter
        tgt = getattr(g, "align_x", None)
        if not tgt or g.frame == "none" or not g.title:
            continue
        inside = {x for x in bp.index if x == g.id or g.id in bp.ancestors(x)}
        near = {tgt} | {x for x in bp.index if tgt in bp.ancestors(x)}
        if any((e.src in near and e.dst in inside) or (e.dst in near and e.src in inside) for e in bp.edges):
            out.append(Finding("align-title-blocks", "warn", [g.id], f"'{g.id}' is aligned under '{tgt}' but its title "
                               "sits where the straight link enters, so the edge detours — make it frame \"none\" and "
                               "name it with an inner bracket (placement \"inner\"), or let the link enter from the side"))

    for cid, c in cells.items():  # a stub arrow and its label must sit in free space
        if not cid.startswith("pfdeco-stub-"):
            continue
        from .geometry import Box
        if cid.endswith("-label"):
            if c.box is None:
                continue
            owner, seg, what = cid[len("pfdeco-stub-"):-len("-label")], c.box, "label"
        elif c.sp is not None and c.tp is not None:
            owner, what = cid[len("pfdeco-stub-"):], "arrow"
            x0, x1 = sorted((c.sp[0], c.tp[0]))
            y0, y1 = sorted((c.sp[1], c.tp[1]))
            seg = Box(x0 - 1, y0 - 1, x1 - x0 + 2, y1 - y0 + 2)
        else:
            continue
        for el in bp.leaves():
            oc = cells.get(f"pf-{el.id}")
            if oc is not None and oc.box is not None and (el.id != owner or what == "label") and \
                    seg.intersects(oc.box, eps=0.5):
                out.append(Finding("stub-overlap", "error", [owner, el.id], f"the stub {what} of '{owner}' runs into "
                                   f"'{el.id}' — leave room on that side (a looser gap) or move the stub"))

    # edge economy: every arrow should earn its place — no wrap-arounds, no duplicate paths
    from .lint import _polyline
    for e in bp.edges:
        c = cells.get(f"pf-{e.id}")
        if c is None:
            continue
        pts = _polyline(c, cells)
        r = detour_ratio(pts)
        span = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])) if len(pts) > 1 else 0
        if r > DETOUR_MAX and span > 80:
            out.append(Finding("edge-detour", "warn", [e.src, e.dst], f"{e.src} → {e.dst} runs {r:.1f}× its straight "
                               "distance — reorder or move the ends so it runs straight, show the loop as one short "
                               "labelled return arrow, or leave it to the caption"))
    pairs = {}
    for e in bp.edges:
        pairs.setdefault(tuple(sorted((e.src, e.dst))), []).append(e)
    for (a, b), es in pairs.items():
        if len(es) > 1:
            out.append(Finding("edges-parallel", "warn", [a, b], f"{len(es)} arrows join {a} and {b} — merge them into "
                               "one (label it with both meanings) unless they are different flows the reader must tell apart"))

    panels = [el.id for el in bp.index.values() if el.is_group and el.detail_of]
    if len(panels) > 2:
        out.append(Finding("zoom-ins-many", "warn", panels, f"{len(panels)} zoom-in panels — expand only the one or two "
                           "mechanisms a reader most needs; the rest belongs in the text or another figure"))
    return out
