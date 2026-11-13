"""Style samples (spec §4, style selection): one blueprint built in several styles and shown side by side.
A sample whose lint report has errors is never shown — it is listed with the reason instead."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import pipeline
from .errors import PaperFigError


@dataclass
class Sample:
    style: str
    label: str
    png: Path
    lint_md: Path
    warnings: int


@dataclass
class SamplesResult:
    sheet: Path | None
    shown: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # [(style, reason)]


def _label(style: str, mix: dict | None) -> str:
    from .styles import load_recipe

    try:
        name = load_recipe(style).data.get("name") or style
    except PaperFigError:
        name = style
    return name + (" + " + ", ".join(f"{k}={v}" for k, v in sorted(mix.items())) if mix else "")


def make_samples(bp_path, styles, mix: dict | None = None, out_dir=None, facts_path=None) -> SamplesResult:
    styles = list(dict.fromkeys(s.strip() for s in styles if s and s.strip()))
    if not styles:
        raise PaperFigError("samples need at least one style")
    bp_path = Path(bp_path)
    out = Path(out_dir) if out_dir else bp_path.parent / "samples"
    out.mkdir(parents=True, exist_ok=True)
    res = SamplesResult(None)
    for st in styles:
        slug = Path(st).stem if st.endswith(".json") else st  # a run's own style file: name the folder by its stem
        try:
            b = pipeline.build(bp_path, st, mix, out / slug, formats=("png",), name=f"sample-{slug}", facts_path=facts_path)
        except Exception as e:  # one style failing never aborts the sheet (it is listed with the reason)
            res.skipped.append((st, f"{type(e).__name__}: {e}"))
            continue
        errs = [f for f in b.report.findings if f.severity == "error"]
        if errs:
            more = f" (+{len(errs) - 5} more)" if len(errs) > 5 else ""
            res.skipped.append((st, "lint errors: " + "; ".join(f"{f.code}: {f.message}" for f in errs[:5]) + more))
            continue
        res.shown.append(Sample(st, _label(st, mix), b.png, b.lint_md, sum(1 for f in b.report.findings if f.severity == "warn")))
    record = {"blueprint": str(bp_path), "mix": mix or {},
              "shown": [{"style": s.style, "label": s.label, "png": str(s.png), "lint": str(s.lint_md), "warnings": s.warnings}
                        for s in res.shown],
              "skipped": [{"style": s, "reason": r} for s, r in res.skipped]}
    if res.shown:
        from .contact import compose

        res.sheet = Path(compose([(s.label, s.png) for s in res.shown], out / "samples.png"))
        record["sheet"] = str(res.sheet)
    (out / "samples.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    if not res.shown:
        raise PaperFigError("no sample passed the mechanical checks — " + "; ".join(f"{s}: {r}" for s, r in res.skipped))
    return res
