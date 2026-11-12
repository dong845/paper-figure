"""CLI: python -m paperfig build|lint|contact ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import PaperFigError


def parse_mix(items) -> dict:
    mix = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--mix expects section=style, got {it!r}")
        k, v = it.split("=", 1)
        mix[k.strip()] = v.strip()
    return mix


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="paperfig")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="blueprint -> .drawio + PNG/PDF + lint report")
    b.add_argument("blueprint")
    b.add_argument("--style", default="soft-pastel")
    b.add_argument("--mix", action="append", help="section=style, e.g. effects=depth-cv (repeatable)")
    b.add_argument("--out")
    b.add_argument("--name")
    b.add_argument("--formats", default="png,pdf")
    l = sub.add_parser("lint", help="lint an existing .drawio against its blueprint")
    l.add_argument("drawio")
    l.add_argument("--blueprint", required=True)
    l.add_argument("--style", default="soft-pastel")
    l.add_argument("--png")
    c = sub.add_parser("contact", help="labelled contact sheet")
    c.add_argument("--panel", action="append", required=True, help="Label=path.png (repeatable)")
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            from .pipeline import build

            res = build(a.blueprint, a.style, parse_mix(a.mix), a.out, tuple(x for x in a.formats.split(",") if x), a.name)
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
