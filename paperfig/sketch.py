"""Low-fidelity concept sketches (the user's design guide, stage 2 "Visual storyboarding"): render 2–3 candidate
compositions as skeletons — top-level units only, no provenance needed — side by side, so the composition is chosen
by looking before the real blueprint is written. Sketches are never delivered and never judged by the facts gate."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .errors import PaperFigError

SKETCH_PROV = [{"source": "user", "ref": "concept sketch (not delivered)"}]


def _fill(d: dict) -> dict:
    d = copy.deepcopy(d)
    d.setdefault("schema_version", 1)
    fig = d.setdefault("figure", {})
    fig.setdefault("type", "overview")
    fig.setdefault("venue", "cvpr")
    fig.setdefault("width", "double")
    fig.setdefault("legend", "none")

    def walk(n):
        n.setdefault("provenance", copy.deepcopy(SKETCH_PROV))
        if n.get("children") and "label" in n:  # a skeleton's group may say label: it is the group's title
            n.setdefault("title", n.pop("label"))
        if n.get("role") == "proposed" and not (n.get("full_name") or n.get("abbrev")):  # a skeleton is rough: its
            from .blueprint import plain_text  # the very text the proposed-name check reads (markup dropped, not spaced:
            n["full_name"] = plain_text(str(n.get("label") or n.get("title") or n["id"])).strip()  # 'AGGREGATE<sub>k'
            # '</sub>' -> 'AGGREGATEk' — a space there made sketch reject its own name, GraphSAGE blind run)
        for c in n.get("children", []):
            walk(c)
    walk(d["root"])
    for e in d.get("edges", []):
        e.setdefault("provenance", copy.deepcopy(SKETCH_PROV))
    return d


def make_sketches(paths: list, out_dir, style: str = "soft-pastel", mix: dict | None = None) -> dict:
    """Render each skeleton blueprint and a labelled side-by-side sheet; returns {"sheet", "concepts": [...]}."""
    from . import pipeline
    from .contact import compose as contact_sheet

    if len(paths) < 1:
        raise PaperFigError("sketch needs at least one concept skeleton")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, panels = [], []
    for p in paths:
        p = Path(p)
        try:
            d = _fill(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            raise PaperFigError(f"sketch {p}: {e}") from e
        src = out / f"{p.stem}.blueprint.json"
        src.write_text(json.dumps(d), encoding="utf-8")
        b = pipeline.build(src, style, mix, out / p.stem, formats=("png",), name=p.stem)  # mix: e.g. compact
        # spacing at a narrow venue width, so the concepts are judged at the size they will print (TWM run)
        w, h = (int(x) for x in str(b.report.stats.get("figure_px", "0x0")).split("x"))
        ar = round(w / h, 2) if h else None
        rows.append({"concept": p.stem, "png": str(b.png), "aspect": ar,
                     "smallest_pt": b.report.stats.get("smallest_text_pt")})
        panels.append((f"{p.stem} · w/h {ar}", b.png))
    sheet = out / "sketches.png"
    contact_sheet(panels, sheet)
    (out / "sketches.json").write_text(json.dumps({"sheet": str(sheet), "concepts": rows}, indent=1), encoding="utf-8")
    return {"sheet": sheet, "concepts": rows}
