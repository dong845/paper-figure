"""Text measurement in drawio units (1 unit = 1 px at 100% zoom).

drawio renders html labels in a browser; we approximate with the same font
files via Pillow. Per-character fallback mirrors browser font fallback:
East-Asian wide/fullwidth glyphs are 1em; glyphs missing from the primary
font are measured with a broad-coverage fallback font; with no font at all
we estimate 0.6em per character (never crash).
"""
from __future__ import annotations

import os
import sys
import unicodedata
from functools import lru_cache

from .markup import parse

LINE_HEIGHT = 1.2  # drawio html labels
SCRIPT_SCALE = 0.75
_FONT_CACHE: dict = {}

_FAMILY_FILES = {
    "helvetica": [
        ("/System/Library/Fonts/Helvetica.ttc", 0, 1),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0, 1),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", None, None),
        ("/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf", None, None),
        ("C:/Windows/Fonts/arial.ttf", None, None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None, None),
    ],
}
_BOLD_SIBLINGS = {
    "LiberationSans-Regular.ttf": "LiberationSans-Bold.ttf",
    "arial.ttf": "arialbd.ttf",
    "DejaVuSans.ttf": "DejaVuSans-Bold.ttf",
}
_FALLBACK_FILES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
]


def _candidates(family: str, bold: bool) -> list[tuple[str, int]]:
    out = []
    for path, ireg, ibold in _FAMILY_FILES.get(family.lower(), _FAMILY_FILES["helvetica"]):
        if path.endswith(".ttc"):
            out.append((path, ibold if bold else ireg))
        elif bold:
            sib = _BOLD_SIBLINGS.get(os.path.basename(path))
            if sib:
                out.append((os.path.join(os.path.dirname(path), sib), 0))
        else:
            out.append((path, 0))
    return out


def _fallback_candidates() -> list[tuple[str, int]]:
    return [(p, 0) for p in _FALLBACK_FILES]


def _open(cands, size_key: float):
    from PIL import ImageFont

    for path, idx in cands:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=100, index=idx), path, idx
            except OSError:
                continue
    return None


@lru_cache(maxsize=None)
def _cmap(path: str, idx: int) -> frozenset | None:
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        return None
    try:
        font = TTCollection(path).fonts[idx] if path.endswith(".ttc") else TTFont(path, lazy=True)
        return frozenset(font.getBestCmap() or {})
    except Exception:
        return None


def _font(kind: str, family: str = "helvetica", bold: bool = False):
    key = (kind, family.lower(), bold)
    if key not in _FONT_CACHE:
        cands = _candidates(family, bold) if kind == "primary" else _fallback_candidates()
        _FONT_CACHE[key] = _open(cands, 100)
    return _FONT_CACHE[key]


def _in_primary(ch: str, opened) -> bool:
    _, path, idx = opened
    cmap = _cmap(path, idx)
    if cmap is not None:
        return ord(ch) in cmap
    return ord(ch) < 0x0530  # Latin, Greek, Cyrillic: covered by any text font


def _char_width_em(ch: str, bold: bool, family: str) -> float:
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    prim = _font("primary", family, bold)
    if prim is not None and _in_primary(ch, prim):
        return prim[0].getlength(ch) / 100.0
    fb = _font("fallback")
    if fb is not None:
        return fb[0].getlength(ch) / 100.0
    if prim is not None:
        return prim[0].getlength(ch) / 100.0
    return 0.6


def _run_width(text: str, size: float, bold: bool, family: str) -> float:
    prim = _font("primary", family, bold)
    total, chunk = 0.0, []

    def flush():
        if chunk:
            nonlocal total
            total += prim[0].getlength("".join(chunk)) / 100.0 * size  # kerning-aware for runs
            chunk.clear()

    for ch in text:
        simple = prim is not None and unicodedata.east_asian_width(ch) not in ("W", "F") and _in_primary(ch, prim)
        if simple:
            chunk.append(ch)
        else:
            flush()
            total += _char_width_em(ch, bold, family) * size
    flush()
    return total


def measure(label: str, size: float, bold: bool = False, family: str = "Helvetica") -> tuple[float, float]:
    """(width, height) of a markup label at font size `size` (drawio fontSize)."""
    lines = parse(label)
    width = 0.0
    for line in lines:
        w = 0.0
        for run in line:
            s = size * (SCRIPT_SCALE if run.script else 1.0)
            w += _run_width(run.text, s, bold or run.bold, family)
        width = max(width, w)
    return width, len(lines) * size * LINE_HEIGHT
