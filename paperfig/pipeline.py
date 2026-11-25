"""build(): blueprint → layout → routes → .drawio → PNG/PDF → lint report."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .blueprint import Figure, has_file, load
from .drawio import emit
from .errors import ExportError, PaperFigError
from .export import export, print_px
from .layout import solve
from .lint import Report, check
from .route import route_all
from .route import detours, label_moves, port_room
from .errors import RouteError
from .styles import Recipe, compose
from .drawio import parse_cells
from .lint import MIN_FONT_PT, _venue_text_range, figure_bbox, largest_text, pt_per_px, smallest_text, text_floor
import copy

CHANNEL = 16.0  # px reserved per detour line on a group side
FIT_MARGIN_PT = 0.3  # the fit aims this far above the floor, so rounding never lands just under it
FIT_MAX_SCALE = 1.6  # beyond this, text crowds out whitespace; the layout must change instead

KB_DIR = Path(__file__).resolve().parent.parent / "kb"


_PAINT = re.compile(rb"\bBT\b|\bDo\b|(?<![\w./])[SsBb]\*?(?![\w.])|\bsh\b")


def _blank_page(page) -> bool:
    """True when a page paints nothing but white fills: no text, images, strokes or shadings; every colour is white."""
    c = page.get_contents()
    data = c.get_data() if c is not None else b""
    if _PAINT.search(data):
        return False
    cols = re.findall(rb"((?:[\d.]+\s+){1,4})(rg|RG|g|G|k|K|sc|scn|SC|SCN)\b", data)
    def white(nums, op):
        v = [float(x) for x in nums.split()]
        return all(abs(x) < 1e-3 for x in v) if op in (b"k", b"K") else all(abs(x - 1) < 1e-3 for x in v)
    if not cols and re.search(rb"(?<![\w.])f\*?(?![\w.])", data):
        return False  # a fill in the default colour, black
    return all(white(n, op) for n, op in cols)


def scale_pdf_to_width(path: Path, width_pt: float) -> None:
    """draw.io writes the page at canvas size; scale it (vector, fonts stay embedded) so the PDF is the print width
    the lint judged — 7 pt in the PDF is then 7 pt in the paper."""
    from pypdf import PdfWriter

    w = PdfWriter(clone_from=str(path))
    while len(w.pages) > 1 and _blank_page(w.pages[-1]):  # the page height rounded short: background spill
        w.remove_page(len(w.pages) - 1)
    if len(w.pages) != 1:
        raise ExportError(f"draw.io wrote {len(w.pages)} pages with content to {path}; a figure is one page — "
                          "check the diagram for a second page or content far outside the drawing")
    for page in w.pages:
        f = width_pt / float(page.mediabox.width)
        if abs(f - 1.0) > 1e-3:
            page.scale_by(f)
    with open(path, "wb") as fh:
        w.write(fh)


SERIF = "Times New Roman"


def with_font(recipe, font: str):
    """figure.font: sans keeps the style's family; serif sets Times New Roman everywhere text is drawn."""
    if font != "serif":
        return recipe
    from .styles import Recipe
    d = copy.deepcopy(recipe.data)
    d["typography"]["family"] = SERIF
    d["typography"].pop("title_family", None)  # everywhere: a display face for titles would break the serif match
    return Recipe(recipe.id + "+serif", d)


def _fmt_pt(x: float) -> str:
    """A print size as text: two decimals near the 7 pt floor so 6.96 never reads as 7.0 (< 7.0)."""
    return f"{x:.2f}" if abs(x - MIN_FONT_PT) < 0.1 else f"{x:.1f}"


def _split_estimate(bp_path: Path, style, mix, small: float):
    """Overview + detail panels below the print floor: what each figure would print at on its own."""
    import tempfile

    from .lint import Finding
    from .split import split
    try:
        with tempfile.TemporaryDirectory() as tmp:
            parts = split(bp_path, Path(tmp) / "parts", style=style)
            sizes = []
            for k, part in enumerate([parts["overview"], *parts["modules"]]):
                r = build(part, style, mix, out_dir=Path(tmp) / f"b{k}", formats=(), suggest_split=False, quick=True)
                sizes.append(r.report.stats.get("smallest_text_pt"))
    except Exception as e:  # noqa: BLE001 — the estimate is advice; never fail the build over it
        return Finding("split-suggested", "warn", [], f"the overview and its detail panels print at {small:.1f} pt; "
                       f"consider an overview figure plus a separate module figure (estimate failed: {e})")
    mods = ", ".join(f"{_fmt_pt(x)} pt" for x in sizes[1:] if x is not None) or "?"
    floor = text_floor(load(bp_path).figure.venue)
    head = (f"the overview and its detail panels print at {_fmt_pt(small)} pt (< {floor} pt); split, the "
            f"overview alone would print at {_fmt_pt(sizes[0] or 0)} pt and the module figure(s) at {mods}")
    if (sizes[0] or 0) < floor:  # splitting moves the panels out, but the overview is the problem
        return Finding("split-suggested", "warn", [], head + " — splitting alone does not fix it: the overview itself "
                       "is too wide for this width; use the double-column width, or fewer top-level units per row")
    return Finding("split-suggested", "warn", [], head + " — `paperfig split BLUEPRINT --out DIR` (or ask the user)")


@dataclass
class BuildResult:
    drawio: Path
    png: Path | None
    pdf: Path | None
    lint_md: Path
    lint_json: Path
    report: Report
    print_width_in: float


def load_formats() -> dict:
    return json.loads((KB_DIR / "formats.json").read_text())["venues"]


def venue_width(fig: Figure) -> float:
    if isinstance(fig.width, (int, float)):
        return float(fig.width)
    kb = load_formats()
    v = kb.get(fig.venue.lower())
    if v is None:
        raise PaperFigError(f"venue '{fig.venue}' is not in kb/formats.json (known: {', '.join(sorted(kb))}); "
                            "give figure.width as a number of inches")
    return v["textwidth_in"] if fig.width == "double" else v["columnwidth_in"]


def solve_and_route(bp, recipe: Recipe, hints: dict | None = None, full: bool = True):
    """Layout, then reserve a routing channel on each group side that detour edges use, then route; then let the
    layout make the room routing asked for. `hints`: scale-free decisions of an earlier call on the same figure
    (moved names, bending lines), filled in place, so a refit does not rediscover them round by round."""
    from .annotations import lane_height, lanes_per_side

    hints = {} if hints is None else hints
    placed = solve(bp, recipe, dict(hints) if hints else None)
    extra: dict = dict(hints)
    edges = {e.id: e for e in bp.edges}
    for eid, gid, side in detours(bp, placed):  # a labelled detour needs room for its name too, not only the line
        lab = 0.0
        if edges[eid].label and side in ("top", "bottom"):
            from .layout import measure
            ty = recipe["typography"]
            lab = measure(edges[eid].label, ty["small_size"], False, ty["family"])[1] + recipe["spacing"]["edge_label_pad"]
        extra[(gid, side)] = extra.get((gid, side), 0.0) + CHANNEL + lab
    if bp.annotations:  # bracket lanes sit outside everything else on the root
        n = lanes_per_side(bp, placed, recipe)
        for side in ("top", "bottom"):
            if n[side]:
                extra[(bp.root.id, side)] = extra.get((bp.root.id, side), 0.0) + n[side] * lane_height(recipe)
    if extra and extra != hints:
        placed = solve(bp, recipe, extra)
    routes = route_all(bp, placed, recipe, full=False)
    for _ in range(3):  # what routing found the layout must make room for (user, round 2: blocks may move/grow):
        need = port_room(bp, placed, routes, recipe)  # sides with more ports than fit two arrowheads apart
        grow = {k: v for k, v in need.items() if v > extra.get(k, 0.0) + 0.5}
        grow.update({k: v for k, v in label_moves(bp, placed, routes, extra).items()  # names a line would run through
                     if extra.get(k) != v})
        grow.update({(k, "bent"): True for k, r in routes.items()  # lines that bend: channels in the gaps they cross
                     if len(r.points) > 2 and (k, "bent") not in extra})
        if not grow:
            break
        trial = {**extra, **grow}
        try:
            p2 = solve(bp, recipe, trial)
            r2 = route_all(bp, p2, recipe, full=False)
        except RouteError:  # a feedback round must never break a figure that already routed: keep the last one
            break
        extra, placed, routes = trial, p2, r2
    if full:  # the drawn routes: every pass, once, on the final layout
        routes = route_all(bp, placed, recipe, full=True)
        # the full passes may end a line on another side than the probe did: a name it now runs through moves too
        mv = {k: v for k, v in label_moves(bp, placed, routes, extra).items() if extra.get(k) != v}
        if mv:
            trial = {**extra, **mv}
            try:
                p2 = solve(bp, recipe, trial)
                extra, placed, routes = trial, p2, route_all(bp, p2, recipe, full=True)
            except RouteError:
                pass
    hints.update({k: v for k, v in extra.items() if isinstance(k, tuple) and len(k) == 2
                  and k[1] in ("label_side", "label_tried", "bent")})
    return placed, routes


def _scaled(recipe: Recipe, f: float) -> Recipe:
    """Grow text and everything drawn with it ("ink": strokes, arrowheads, shapes, images) by f and
    whitespace by sqrt(f), so text gains print size while the figure keeps its proportions."""
    d = copy.deepcopy(recipe.data)
    g = f ** 0.5
    for k in ("size", "title_size", "small_size"):
        d["typography"][k] = round(d["typography"][k] * f, 2)
    for k in ("node_pad_x", "node_pad_y", "min_node_w", "min_node_h", "title_h", "label_gap"):
        d["spacing"][k] = round(d["spacing"][k] * f, 2)
    for k in ("group_pad", "edge_label_pad"):
        d["spacing"][k] = round(d["spacing"][k] * g, 2)
    d["spacing"]["gap"] = {k: round(v * g, 2) for k, v in d["spacing"]["gap"].items()}
    for k in ("stroke_width", "group_stroke_width"):
        d["shape"][k] = round(d["shape"][k] * f, 2)
    for k in ("radius", "group_radius"):
        d["shape"][k] = round(d["shape"][k] * g, 2)
    for e in d["edges"].values():
        e["width"] = round(e["width"] * f, 2)
    for k in ("w", "depth", "h"):
        d["tensor"][k] = round(d["tensor"][k] * f, 2)
    d["image"]["default_long_side"] = round(d["image"]["default_long_side"] * f, 2)
    d["ink_scale"] = round(recipe.data.get("ink_scale", 1.0) * f, 4)
    return Recipe(recipe.id if f == 1 else f"{recipe.id}@ink×{f:.2f}", d)


def fit_typography(bp, recipe: Recipe, width_in: float, quick: bool = False):
    """Scale text (and text-bound sizes) until the smallest text prints >= MIN_FONT_PT (+FIT_MARGIN_PT) at width_in —
    no further than a venue's stated maximum allows for the largest text, and down when that maximum is exceeded
    (Nature 5-7 pt); the venue's own minimum is the floor.
    Gaps and group padding grow only by sqrt(f) (_scaled), so text gains on the layout each step and this
    converges; if it cannot reach the target within FIT_MAX_SCALE the
    lint's min-font error reports it (never silently). A right-column legend widens the figure; when that costs
    the font floor, the legend goes back below and the better of the two fits is kept."""
    res = _fit(bp, recipe, width_in, quick)
    if not res[1]["reached"] and not recipe.data.get("legend_no_column"):
        alt = _fit(bp, _with(recipe, legend_no_column=True), width_in, quick)
        if (alt[1]["smallest_pt"] or 0) > (res[1]["smallest_pt"] or 0) + 1e-6:
            return alt
    return res


def _with(recipe: Recipe, **kw) -> Recipe:
    import copy as _copy

    d = _copy.deepcopy(recipe.data)
    d.update(kw)
    return Recipe(recipe.id, d)


def _fit(bp, recipe: Recipe, width_in: float, quick: bool = False):
    from .order import auto_order
    if not getattr(bp, "order_notes", None) and not getattr(bp, "_ordered", False):
        bp.order_notes = auto_order(bp, recipe, solve)  # once per figure: the order is scale-free
        bp._ordered = True
    total, cur = 1.0, recipe
    venue = getattr(bp.figure, "venue", "")
    floor, ceil = text_floor(venue), (_venue_text_range(venue) or {}).get("max")
    goal = max(floor, MIN_FONT_PT)  # aim as legible as any venue; a stated minimum (Nature 5 pt) is only the floor
    info = {"reached": False, "scale": 1.0, "smallest_pt": None}
    last = (cur, None, None)
    hints: dict = {}
    for _ in range(6):
        placed, routes = solve_and_route(bp, cur, hints, full=False)  # sizing only: quick routes
        last = (cur, placed, routes)
        cells = parse_cells(emit(bp, placed, routes, cur))
        ppx = pt_per_px(figure_bbox(cells, cur), width_in)
        sm = smallest_text(cells, cur, ppx)
        lg = largest_text(cells, cur, ppx) if ceil else None
        info["smallest_pt"] = sm[0] if sm else None
        high = lg is not None and lg[0] > ceil + 0.05  # a venue's stated maximum (Nature: 7 pt)
        if sm is None or (sm[0] >= goal and not high):
            info["reached"] = True
            break
        if not high:  # grow toward the legibility goal; stop where the largest text meets a venue maximum
            f = min(FIT_MAX_SCALE / total, (goal + FIT_MARGIN_PT) / sm[0] * 1.02)
            if lg is not None:
                f = min(f, max(ceil / lg[0], floor / sm[0] * 1.02))  # the floor outranks the maximum
        else:  # shrink until the largest text fits, never below the floor
            f = max(ceil / lg[0], floor / sm[0] * 1.005)
        if abs(f - 1.0) <= 1e-3:  # cannot move further: within the venue's range is good enough
            info["reached"] = sm[0] >= floor and not high
            break
        total *= f
        cur = _scaled(recipe, total)
    info["scale"] = round(total, 3)
    if last[0] is not cur:  # the loop ended on a scale it has not laid out yet
        placed, routes = solve_and_route(bp, cur, hints, full=not quick)
    elif not quick:  # the layout stands; route it in full
        placed = last[1]
        routes = route_all(bp, placed, cur, full=True)
    else:
        placed, routes = last[1], last[2]
    return cur, info, placed, routes


def build(blueprint_path, style: str | None = None, mix: dict | None = None, out_dir=None,
          formats=("png", "pdf"), name: str | None = None, dpi: int = 300, facts_path=None, plan_path=None,
          suggest_split: bool = True, quick: bool = False) -> BuildResult:
    bp_path = Path(blueprint_path).resolve()
    bp = load(bp_path)
    from .facts import check_facts, load_facts

    if facts_path is None:  # beside it: facts.json (a run), or <name>.facts.json for <name>.blueprint.json (examples/)
        stem = bp_path.name[:-len(".blueprint.json")] if bp_path.name.endswith(".blueprint.json") else None
        for cand in (bp_path.parent / "facts.json", *([bp_path.parent / f"{stem}.facts.json"] if stem else [])):
            if cand.is_file():
                facts_path = cand
                break
    facts = load_facts(facts_path) if facts_path else None
    if plan_path is None and (bp_path.parent / "figure_plan.json").is_file():
        plan_path = bp_path.parent / "figure_plan.json"
    from .plan import apply_plan, load_plan

    plan = load_plan(plan_path) if plan_path else None
    if bp.figure.tone_legend and plan:  # what each colour means, from the plan, into the legend
        bp.tone_meanings = dict(plan.get("color_semantics") or {})
    width_in = venue_width(bp.figure)
    # quick: lines placed but not repaired — for builds that only measure print size (split parts)
    recipe, fit, placed, routes = fit_typography(bp, with_font(compose(style or bp.figure.style or "soft-pastel", mix),
                                                              bp.figure.font), width_in, quick)
    xml = emit(bp, placed, routes, recipe)
    if name is None:
        name = bp_path.parent.name if bp_path.stem == "blueprint" else bp_path.stem
    out = Path(out_dir).resolve() if out_dir else bp_path.parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    drawio = out / f"{name}.drawio"
    drawio.write_text(xml, encoding="utf-8")
    shutil.copyfile(bp_path, out / f"{name}.blueprint.json")
    png = pdf = None
    if "png" in formats:
        png = export(drawio, "png", out / f"{name}.png", width_px=print_px(width_in, dpi))
        from PIL import Image  # record the print resolution: without it Word / PowerPoint place the PNG oversized
        with Image.open(png) as im:
            im.load()
            im.save(png, dpi=(dpi, dpi))
    if "pdf" in formats:
        pdf = export(drawio, "pdf", out / f"{name}.pdf")
        scale_pdf_to_width(pdf, width_in * 72.0)
    if "svg" in formats:
        export(drawio, "svg", out / f"{name}.svg")
    rep = check(drawio, bp, recipe, png, width_in)
    if pdf is not None:
        from .lint import check_pdf_fonts
        check_pdf_fonts(pdf, rep)
    from .grammar import check_grammar

    rep.findings.extend(check_grammar(bp, drawio, recipe, plan))
    from .consistency import check_run_dir

    rep.findings.extend(check_run_dir(bp, bp_path.parent))  # the blueprint against the analyses, when present
    if facts is not None:
        ff = apply_plan(check_facts(bp, facts, getattr(bp, "annotation_members", {}),
                                    drawn_as=(plan or {}).get("drawn_as")), plan)
        rep.findings.extend(ff)
        bad = sum(1 for x in ff if x.severity == "error")
        skipped = sum(1 for x in ff if x.code in ("fact-waived", "fact-omitted"))
        rep.stats["facts_covered"] = f"{len(facts) - bad - skipped}/{len(facts)}"
        if plan is not None:
            rep.stats["facts_omitted_by_plan"] = sum(1 for x in ff if x.code == "fact-omitted")
    else:
        rep.add("facts-absent", "warn", [], "no facts.json: the blueprint was not checked against the paper (faithfulness gate skipped)")
    for n in bp.leaves():  # tell the user when an image had to be cropped to its (aspect-clamped) box
        if n.visual == "image" and has_file(n.asset):
            from PIL import Image, ImageOps

            with Image.open(n.asset.path) as im:
                w, h = ImageOps.exif_transpose(im).size
            b = placed[n.id].box
            if abs((w / h) - (b.w / b.h)) / (b.w / b.h) > 0.01:
                rep.add("image-cropped", "info", [n.id], f"image {w}x{h} was centre-cropped to the box aspect {b.w / b.h:.2f} (never stretched)")
            fig_w = float(str(rep.stats.get("figure_px", "0x0")).split("x")[0] or 0)
            if fig_w:  # never draw a raster past its own pixels: the visible part must cover the box at print dpi
                need = b.w / fig_w * width_in * dpi
                have = min(w, h * b.w / b.h)  # the width that survives the centre crop
                if have < 0.95 * need:
                    rep.add("asset-resolution", "warn", [n.id], f"image is {have:.0f} px wide where it prints "
                            f"{need:.0f} px wide at {dpi} dpi — it will look soft; use a larger file or a smaller box")
    small = rep.stats.get("smallest_text_pt")
    from .rules import apply_deviations  # tier-2 findings the plan deviates from, with its reason (paperfig/rules.py)
    rep.findings = apply_deviations(rep.findings, plan)
    if suggest_split and small is not None and small < text_floor(bp.figure.venue) and any(g.detail_of for g in bp.groups()):
        rep.findings.append(_split_estimate(bp_path, style, mix, small))
    rep.stats["style"] = recipe.id
    rep.stats["text_scale"] = fit["scale"]
    md, js = out / f"{name}.lint.md", out / f"{name}.lint.json"
    md.write_text(rep.to_markdown(), encoding="utf-8")
    js.write_text(rep.to_json(), encoding="utf-8")
    return BuildResult(drawio, png, pdf, md, js, rep, width_in)
