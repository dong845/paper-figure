"""Environment check run at the start of every job (SKILL.md: `paperfig doctor`)."""
from __future__ import annotations

import shutil
import sys

POPPLER = "install poppler (macOS: brew install poppler; Debian/Ubuntu: apt install poppler-utils)"


def check() -> list[dict]:
    out = [{"name": "python", "ok": sys.version_info >= (3, 10), "detail": sys.version.split()[0] + " (needs >= 3.10)"}]
    from importlib import metadata

    for mod, pip in (("PIL", "Pillow"), ("jsonschema", "jsonschema")):
        try:
            __import__(mod)
            out.append({"name": pip, "ok": True, "detail": metadata.version(pip)})
        except ImportError:
            out.append({"name": pip, "ok": False, "detail": f"missing — pip install {pip}"})
        except metadata.PackageNotFoundError:
            out.append({"name": pip, "ok": True, "detail": "installed (version unknown)"})
    for tool in ("pdftotext", "pdftoppm", "pdfinfo"):
        p = shutil.which(tool)
        out.append({"name": tool, "ok": bool(p), "detail": p or f"not found — {POPPLER}"})
    from .errors import ExportError
    from .export import find_drawio

    try:
        out.append({"name": "draw.io", "ok": True, "detail": find_drawio()})
    except ExportError as e:
        out.append({"name": "draw.io", "ok": False, "detail": f"{e} — install draw.io desktop from https://www.drawio.com"})
    return out
