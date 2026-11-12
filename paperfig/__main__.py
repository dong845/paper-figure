"""CLI: python -m paperfig build|lint|extract|codemap|refs|contact ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import PaperFigError


def _figure_style(path):
    import json

    try:
        return json.loads(open(path, encoding="utf-8").read()).get("figure", {}).get("style")
    except (OSError, ValueError, AttributeError):
        return None  # the build itself will report the unreadable blueprint


def parse_mix(items) -> dict:
    mix = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--mix expects section=style, got {it!r}")
        k, v = it.split("=", 1)
        mix[k.strip()] = v.strip()
    return mix


def _years(text):
    if not text:
        return None
    import re

    m = re.fullmatch(r"\s*(\d{4})\s*(?:-\s*(\d{4}))?\s*", text)
    if not m:
        raise PaperFigError(f"--years expects YYYY or YYYY-YYYY, got {text!r}")
    return int(m.group(1)), int(m.group(2) or m.group(1))


def _refs(a) -> int:
    import json

    from . import refs

    if a.refs_cmd == "search":
        venues = [v for v in (a.venues or "").split(",") if v.strip()]
        res = refs.search(a.query, years=_years(a.years), venues=venues or None, limit=a.limit,
                          exclude_arxiv=a.exclude_arxiv, exclude_titles=a.exclude_title)
        for n in res.notes:
            print(f"note: {n}", file=sys.stderr)
        for c in res:
            print(f"{c.year or '----'}  {(c.venue or '?')[:12]:12}  {str(c.citations if c.citations is not None else '-'):>6}  "
                  f"{c.arxiv_id or '-':12}  {c.title}")
        if a.out:
            Path(a.out).write_text(json.dumps({"query": a.query, "notes": res.notes, "candidates": [c.to_dict() for c in res]},
                                              indent=1, ensure_ascii=False), encoding="utf-8")
        if not res:
            print("no candidates", file=sys.stderr)
        return 0
    if a.refs_cmd == "fetch":
        print(refs.fetch(a.arxiv_id))
        return 0
    if a.refs_cmd == "crop":
        nums = None
        if a.figures:
            try:
                nums = {int(x) for x in a.figures.split(",") if x.strip()}
            except ValueError:
                raise PaperFigError(f"--figures expects numbers like 1,3, got {a.figures!r}") from None
        crops = refs.crop_figures(a.pdf, a.out, numbers=nums, dpi=a.dpi)
        bad = 0
        for c in crops:
            if c.problem:
                bad += 1
                print(f"fig{c.number}: PROBLEM — {c.problem}")
            else:
                print(f"fig{c.number}: page {c.page}, {c.layout}, {c.span} -> {c.png}")
        return 1 if bad else 0
    raise PaperFigError(f"unknown refs command {a.refs_cmd!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="paperfig")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="blueprint -> .drawio + PNG/PDF + lint report")
    b.add_argument("blueprint")
    b.add_argument("--style", default=None, help="style recipe (default: figure.style in the blueprint, else soft-pastel)")
    b.add_argument("--mix", action="append", help="section=style, e.g. effects=depth-cv (repeatable)")
    b.add_argument("--out")
    b.add_argument("--name")
    b.add_argument("--formats", default="png,pdf")
    b.add_argument("--facts", help="facts.json (default: facts.json next to the blueprint)")
    l = sub.add_parser("lint", help="lint an existing .drawio against its blueprint")
    l.add_argument("drawio")
    l.add_argument("--blueprint", required=True)
    l.add_argument("--style", default="soft-pastel")
    l.add_argument("--png")
    x = sub.add_parser("extract", help="draft (.tex dir/file, .pdf, .md, .docx) -> plain text")
    x.add_argument("draft")
    x.add_argument("--blind", action="store_true", help="drop figures and captions (benchmark protocol)")
    x.add_argument("--method-only", action="store_true")
    x.add_argument("--out", required=True)
    cm = sub.add_parser("codemap", help="repository -> classes / forward() map (JSON)")
    cm.add_argument("repo")
    cm.add_argument("--out", required=True)
    rf = sub.add_parser("refs", help="reference papers: search / fetch / crop figures")
    rsub = rf.add_subparsers(dest="refs_cmd", required=True)
    rs = rsub.add_parser("search", help="Semantic Scholar (arXiv fallback) -> candidate papers")
    rs.add_argument("query")
    rs.add_argument("--years", help="YYYY or YYYY-YYYY")
    rs.add_argument("--venues", help="comma list, e.g. CVPR,ICCV,ECCV")
    rs.add_argument("--limit", type=int, default=20)
    rs.add_argument("--exclude-arxiv", action="append", default=[])
    rs.add_argument("--exclude-title", action="append", default=[])
    rs.add_argument("--out", help="write candidates JSON here")
    rfe = rsub.add_parser("fetch", help="download an arXiv PDF into the cache")
    rfe.add_argument("arxiv_id")
    rc = rsub.add_parser("crop", help="crop figures from a PDF by their captions")
    rc.add_argument("pdf")
    rc.add_argument("--out", required=True)
    rc.add_argument("--figures", help="comma list of figure numbers (default: all)")
    rc.add_argument("--dpi", type=int, default=200)
    c = sub.add_parser("contact", help="labelled contact sheet")
    c.add_argument("--panel", action="append", required=True, help="Label=path.png (repeatable)")
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            from . import pipeline

            fmts = tuple(x for x in a.formats.split(",") if x)
            bad = [x for x in fmts if x not in ("png", "pdf", "svg")]
            if bad:
                raise PaperFigError(f"unknown format(s): {', '.join(bad)} (use png, pdf, svg)")
            build = pipeline.build

            res = build(a.blueprint, a.style or _figure_style(a.blueprint), parse_mix(a.mix), a.out, fmts, a.name,
                        facts_path=a.facts)
            print(res.report.to_markdown())
            print(f"\ndrawio: {res.drawio}\npng:    {res.png}\npdf:    {res.pdf}\nlint:   {res.lint_md}")
            return 0 if res.report.ok else 1
        if a.cmd == "lint":
            from .blueprint import load
            from .lint import check
            from .pipeline import venue_width
            from .styles import compose

            bp = load(a.blueprint)
            rep = check(a.drawio, bp, compose(a.style), a.png, venue_width(bp.figure))
            print(rep.to_markdown())
            return 0 if rep.ok else 1
        if a.cmd == "extract":
            from .extract import extract_draft, method_section

            d = extract_draft(a.draft, blind=a.blind)
            text = method_section(d) if a.method_only else d.text
            Path(a.out).write_text(text, encoding="utf-8")
            for w in d.warnings:
                print(f"warning: {w}", file=sys.stderr)
            print(f"{a.out}: {len(text.split())} words, {len(d.sections)} sections ({d.source_kind}{', blind' if a.blind else ''})")
            return 0
        if a.cmd == "codemap":
            import json

            from .codemap import code_map

            m = code_map(a.repo)
            Path(a.out).write_text(json.dumps(m, indent=1), encoding="utf-8")
            print(f"{a.out}: {len(m['files'])} python files, {sum(len(f['classes']) for f in m['files'])} classes, {len(m['errors'])} parse errors")
            return 0
        if a.cmd == "refs":
            return _refs(a)
        if a.cmd == "contact":
            from .contact import compose as sheet

            panels = []
            for p in a.panel:
                if "=" not in p:
                    raise SystemExit(f"--panel expects Label=path, got {p!r}")
                k, v = p.split("=", 1)
                panels.append((k, Path(v)))
            print(sheet(panels, a.out))
            return 0
    except PaperFigError as e:
        print(f"paperfig: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # never let a crash look like a lint failure (exit 1)
        import traceback

        traceback.print_exc()
        print(f"paperfig: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
