"""build(): blueprint → layout → routes → .drawio → PNG/PDF → lint report."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .blueprint import Figure, load
from .drawio import emit
from .errors import PaperFigError
from .export import export, print_px
from .layout import solve
from .lint import Report, check
from .route import route_all
from .styles import compose

KB_DIR = Path(__file__).resolve().parent.parent / "kb"


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


def build(blueprint_path, style: str = "soft-pastel", mix: dict | None = None, out_dir=None,
          formats=("png", "pdf"), name: str | None = None, dpi: int = 300) -> BuildResult:
    bp_path = Path(blueprint_path).resolve()
    bp = load(bp_path)
    recipe = compose(style, mix)
    placed = solve(bp, recipe)
    routes = route_all(bp, placed, recipe)
    xml = emit(bp, placed, routes, recipe)
    if name is None:
        name = bp_path.parent.name if bp_path.stem == "blueprint" else bp_path.stem
    out = Path(out_dir).resolve() if out_dir else bp_path.parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    drawio = out / f"{name}.drawio"
    drawio.write_text(xml, encoding="utf-8")
    shutil.copyfile(bp_path, out / f"{name}.blueprint.json")
    width_in = venue_width(bp.figure)
    png = pdf = None
    if "png" in formats:
        png = export(drawio, "png", out / f"{name}.png", width_px=print_px(width_in, dpi))
    if "pdf" in formats:
        pdf = export(drawio, "pdf", out / f"{name}.pdf")
    rep = check(drawio, bp, recipe, png, width_in)
    rep.stats["style"] = recipe.id
    md, js = out / f"{name}.lint.md", out / f"{name}.lint.json"
    md.write_text(rep.to_markdown(), encoding="utf-8")
    js.write_text(rep.to_json(), encoding="utf-8")
    return BuildResult(drawio, png, pdf, md, js, rep, width_in)
