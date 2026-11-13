"""Corpus check — the repo's fixed acceptance inputs (CLAUDE.md `Acceptance`).

Builds every `bench/corpus/<paper>/blueprint.json` (with its facts, plan and recorded style) through the real
pipeline and draw.io export, and writes one summary per paper: lint counts and codes, the facts gate, PDF pages,
PNG blank margins, drawing size and smallest printed text. Run it on the baseline and on the change and diff:

    PYTHONPATH=<code tree> python3 bench/corpus_check.py --out OUT_DIR [--only paper,paper]
    python3 bench/corpus_check.py --diff BASE.json NEW.json

The images in `assets/` are neutral grey stand-ins at the delivered images' pixel sizes (layout is identical; no
third-party pixels in the repo). Each build runs from its own paper directory, so relative asset paths resolve
the same way on old and new code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "corpus"


def summarise(paper_dir: Path, out: Path) -> dict:
    from paperfig import pipeline as P

    cfg = json.loads((paper_dir / "corpus.json").read_text())
    style = cfg["style"]
    if style.endswith(".json"):
        style = str(paper_dir / style)
    cwd = os.getcwd()
    os.chdir(paper_dir)
    try:
        res = P.build(paper_dir / "blueprint.json", style, cfg.get("mix"), out_dir=out, formats=("png", "pdf"),
                      name=paper_dir.name)
    finally:
        os.chdir(cwd)
    fs = res.report.findings
    rec = {"counts": {s: sum(1 for f in fs if f.severity == s) for s in ("error", "warn", "info")},
           "errors": sorted(f.code for f in fs if f.severity == "error"),
           "warns": sorted(f.code for f in fs if f.severity == "warn"),
           "facts": {}, "stats": {k: res.report.stats.get(k) for k in
                                  ("figure_px", "png_px", "smallest_text_pt", "png_margins_px", "style")}}
    for f in fs:
        if f.code.startswith("fact"):
            rec["facts"][f.code] = rec["facts"].get(f.code, 0) + 1
    try:
        from pypdf import PdfReader
        rec["pdf_pages"] = len(PdfReader(str(res.pdf)).pages) if res.pdf else None
    except Exception as e:  # noqa: BLE001
        rec["pdf_pages"] = f"unreadable: {e}"
    from PIL import Image, ImageOps
    with Image.open(res.png) as im:
        g = im.convert("L")
        W, H = g.size
        bb = ImageOps.invert(g.point(lambda v: 255 if v >= 245 else v)).getbbox()
    rec["png_margins_measured"] = [bb[0], bb[1], W - bb[2], H - bb[3]] if bb else None
    rec["png"] = str(res.png)
    return rec


def run(out_dir: Path, only=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for d in sorted(p for p in CORPUS.iterdir() if (p / "corpus.json").is_file()):
        if only and d.name not in only:
            continue
        try:
            result[d.name] = summarise(d, out_dir / d.name)
        except Exception as e:  # noqa: BLE001 — a crash is a result, recorded loudly
            result[d.name] = {"crash": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
        print(d.name, json.dumps({k: v for k, v in result[d.name].items() if k not in ("trace", "png")})[:300])
    (out_dir / "summary.json").write_text(json.dumps(result, indent=1))
    return result


def diff(base: dict, new: dict) -> list[str]:
    """What got worse (or merely changed) from base to new; empty = not worse."""
    out = []
    for p in sorted(set(base) | set(new)):
        a, b = base.get(p, {}), new.get(p, {})
        if "crash" in b:
            out.append(f"WORSE {p}: crashes — {b['crash']}")
            continue
        if "crash" in a:
            out.append(f"better {p}: no longer crashes")
            continue
        new_err = sorted(set(b["errors"]) - set(a["errors"]))
        if new_err:
            out.append(f"WORSE {p}: new lint errors {new_err}")
        if b["counts"]["error"] < a["counts"]["error"]:
            out.append(f"better {p}: lint errors {a['counts']['error']} -> {b['counts']['error']}")
        if b["facts"] != a["facts"]:
            out.append(f"CHANGED {p}: facts {a['facts']} -> {b['facts']}")
        if b.get("pdf_pages") != 1:
            out.append(f"WORSE {p}: pdf pages {b.get('pdf_pages')}")
        ma, mb = max(a.get("png_margins_measured") or [0]), max(b.get("png_margins_measured") or [0])
        if mb > max(48, ma + 6):
            out.append(f"WORSE {p}: widest blank margin {ma} -> {mb} px")
        pa, pb = a["stats"].get("smallest_text_pt") or 0, b["stats"].get("smallest_text_pt") or 0
        if pb + 0.05 < pa:
            out.append(f"WORSE {p}: smallest text {pa} -> {pb} pt")
        if set(b["warns"]) != set(a["warns"]):
            out.append(f"changed {p}: warns +{sorted(set(b['warns']) - set(a['warns']))} "
                       f"-{sorted(set(a['warns']) - set(b['warns']))}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--only")
    ap.add_argument("--diff", nargs=2)
    a = ap.parse_args()
    if a.diff:
        lines = diff(*(json.loads(Path(x).read_text()) for x in a.diff))
        print("\n".join(lines) or "not worse: no differences")
        sys.exit(1 if any(x.startswith("WORSE") for x in lines) else 0)
    run(Path(a.out), set(a.only.split(",")) if a.only else None)
