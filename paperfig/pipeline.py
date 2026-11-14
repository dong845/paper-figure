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
from .route import detours
from .styles import Recipe, compose
from .drawio import parse_cells
from .lint import MIN_FONT_PT, figure_bbox, pt_per_px, smallest_text
import copy

CHANNEL = 16.0  # px reserved per detour line on a group side
FIT_TARGET_PT = MIN_FONT_PT + 0.3
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
                r = build(part, style, mix, out_dir=Path(tmp) / f"b{k}", formats=(), suggest_split=False)
                sizes.append(r.report.stats.get("smallest_text_pt"))
    except Exception as e:  # noqa: BLE001 — the estimate is advice; never fail the build over it
        return Finding("split-suggested", "warn", [], f"the overview and its detail panels print at {small:.1f} pt; "
                       f"consider an overview figure plus a separate module figure (estimate failed: {e})")
    mods = ", ".join(f"{_fmt_pt(x)} pt" for x in sizes[1:] if x is not None) or "?"
    head = (f"the overview and its detail panels print at {_fmt_pt(small)} pt (< {MIN_FONT_PT} pt); split, the "
            f"overview alone would print at {_fmt_pt(sizes[0] or 0)} pt and the module figure(s) at {mods}")
    if (sizes[0] or 0) < MIN_FONT_PT:  # splitting moves the panels out, but the overview is the problem
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


def solve_and_route(bp, recipe: Recipe):
    """Layout, then reserve a routing channel on each group side that detour edges use, then route."""
    from .annotations import lane_height, lanes_per_side

    placed = solve(bp, recipe)
    extra: dict = {}
    for _, gid, side in detours(bp, placed):
        extra[(gid, side)] = extra.get((gid, side), 0.0) + CHANNEL
    if bp.annotations:  # bracket lanes sit outside everything else on the root
        n = lanes_per_side(bp, placed, recipe)
        for side in ("top", "bottom"):
            if n[side]:
                extra[(bp.root.id, side)] = extra.get((bp.root.id, side), 0.0) + n[side] * lane_height(recipe)
    if extra:
        placed = solve(bp, recipe, extra)
    return placed, route_all(bp, placed, recipe)


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


def fit_typography(bp, recipe: Recipe, width_in: float):
    """Scale text (and text-bound sizes) until the smallest text prints >= FIT_TARGET_PT at width_in.
    Gaps stay fixed, so this converges; if it cannot reach the target within FIT_MAX_SCALE the
    lint's min-font error reports it (never silently). A right-column legend widens the figure; when that costs
    the font floor, the legend goes back below and the better of the two fits is kept."""
    res = _fit(bp, recipe, width_in)
    if not res[1]["reached"] and not recipe.data.get("legend_no_column"):
        alt = _fit(bp, _with(recipe, legend_no_column=True), width_in)
        if (alt[1]["smallest_pt"] or 0) > (res[1]["smallest_pt"] or 0) + 1e-6:
            return alt
    return res


def _with(recipe: Recipe, **kw) -> Recipe:
    import copy as _copy

    d = _copy.deepcopy(recipe.data)
    d.update(kw)
    return Recipe(recipe.id, d)


def _fit(bp, recipe: Recipe, width_in: float):
    total, cur = 1.0, recipe
    info = {"reached": False, "scale": 1.0, "smallest_pt": None}
    last = (cur, None, None)
    for _ in range(6):
        placed, routes = solve_and_route(bp, cur)
        last = (cur, placed, routes)
        cells = parse_cells(emit(bp, placed, routes, cur))
        sm = smallest_text(cells, cur, pt_per_px(figure_bbox(cells, cur), width_in))
        info["smallest_pt"] = sm[0] if sm else None
        if sm is None or sm[0] >= MIN_FONT_PT:
            info["reached"] = True
            break
        f = min(FIT_MAX_SCALE / total, FIT_TARGET_PT / sm[0] * 1.02)
        if f <= 1.0 + 1e-3:
            break
        total *= f
        cur = _scaled(recipe, total)
    info["scale"] = round(total, 3)
    if last[0] is not cur:  # the loop ended on a scale it has not laid out yet
        placed, routes = solve_and_route(bp, cur)
    else:
        placed, routes = last[1], last[2]
    return cur, info, placed, routes


def build(blueprint_path, style: str | None = None, mix: dict | None = None, out_dir=None,
          formats=("png", "pdf"), name: str | None = None, dpi: int = 300, facts_path=None, plan_path=None,
          suggest_split: bool = True) -> BuildResult:
    bp_path = Path(blueprint_path).resolve()
    bp = load(bp_path)
    from .facts import check_facts, load_facts

    if facts_path is None and (bp_path.parent / "facts.json").is_file():
        facts_path = bp_path.parent / "facts.json"
    facts = load_facts(facts_path) if facts_path else None
    if plan_path is None and (bp_path.parent / "figure_plan.json").is_file():
        plan_path = bp_path.parent / "figure_plan.json"
    from .plan import apply_plan, load_plan

    plan = load_plan(plan_path) if plan_path else None
    width_in = venue_width(bp.figure)
    recipe, fit, placed, routes = fit_typography(bp, with_font(compose(style or bp.figure.style or "soft-pastel", mix),
                                                              bp.figure.font), width_in)
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
    if "pdf" in formats:
        pdf = export(drawio, "pdf", out / f"{name}.pdf")
        scale_pdf_to_width(pdf, width_in * 72.0)
    if "svg" in formats:
        export(drawio, "svg", out / f"{name}.svg")
    rep = check(drawio, bp, recipe, png, width_in)
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
    if suggest_split and small is not None and small < MIN_FONT_PT and any(g.detail_of for g in bp.groups()):
        rep.findings.append(_split_estimate(bp_path, style, mix, small))
    rep.stats["style"] = recipe.id
    rep.stats["text_scale"] = fit["scale"]
    md, js = out / f"{name}.lint.md", out / f"{name}.lint.json"
    md.write_text(rep.to_markdown(), encoding="utf-8")
    js.write_text(rep.to_json(), encoding="utf-8")
    return BuildResult(drawio, png, pdf, md, js, rep, width_in)
