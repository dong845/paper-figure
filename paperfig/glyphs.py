"""Glyph visuals (round 3; the user's design guide §9.1): small deterministic SVG symbols for representations the
box vocabulary cannot show — a graph neighbourhood, a database, a prototype, a schematic heatmap, a segmentation
mask, k-space with its sampling pattern. Drawn in the node's tone; nothing random, so a rebuild is identical.
Heatmap, mask and k-space look like data: they are schematic and must be marked `illustrative` (lint)."""
from __future__ import annotations

import base64
import math

from . import color

GLYPHS = ("graph", "database", "prototype", "heatmap", "mask", "kspace", "documents")
SCHEMATIC = ("heatmap", "mask", "kspace")  # could be mistaken for a result
DEFAULT_SIZE = {"graph": (60, 52), "database": (40, 50), "prototype": (34, 34), "heatmap": (56, 56), "mask": (56, 56),
                "kspace": (56, 56), "documents": (44, 52)}


def _mix(a: str, b: str, t: float) -> str:
    ra, rb = color.hex_rgb(a), color.hex_rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def _svg(w: float, h: float, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.1f}" height="{h:.1f}" viewBox="0 0 {w:.1f} {h:.1f}">'
            f"{body}</svg>")


def _graph(w, h, fill, stroke, accent, n, sw):
    cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 7
    pts = [(cx, cy)] + [(cx + r * math.cos(2 * math.pi * k / (n - 1) - math.pi / 2),
                         cy + r * math.sin(2 * math.pi * k / (n - 1) - math.pi / 2)) for k in range(n - 1)]
    edges = [(0, k) for k in range(1, n)] + [(k, k + 1) for k in range(1, n - 1, 2)]
    lines = "".join(f'<line x1="{pts[a][0]:.1f}" y1="{pts[a][1]:.1f}" x2="{pts[b][0]:.1f}" y2="{pts[b][1]:.1f}" '
                    f'stroke="{stroke}" stroke-width="{sw:.2f}"/>' for a, b in edges)
    nr = max(3.0, min(w, h) / 11)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{nr:.1f}" fill="{accent if i == 0 else fill}" '
                      f'stroke="{stroke}" stroke-width="{sw:.2f}"/>' for i, (x, y) in enumerate(pts))
    return lines + circles


def _database(w, h, fill, stroke, sw):
    rx, ry = w / 2 - sw, max(3.0, h / 8)
    top, bot = ry + sw, h - ry - sw
    body = (f'<path d="M{sw:.1f},{top:.1f} L{sw:.1f},{bot:.1f} A{rx:.1f},{ry:.1f} 0 0 0 {w - sw:.1f},{bot:.1f} '
            f'L{w - sw:.1f},{top:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.2f}"/>')
    bands = "".join(f'<path d="M{sw:.1f},{y:.1f} A{rx:.1f},{ry:.1f} 0 0 0 {w - sw:.1f},{y:.1f}" fill="none" '
                    f'stroke="{stroke}" stroke-width="{sw:.2f}"/>' for y in (top + (bot - top) / 3, top + 2 * (bot - top) / 3))
    cap = f'<ellipse cx="{w / 2:.1f}" cy="{top:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.2f}"/>'
    return body + bands + cap


def _prototype(w, h, fill, stroke, accent, sw):
    cx, cy = w / 2, h / 2
    pts = f"{cx:.1f},{sw:.1f} {w - sw:.1f},{cy:.1f} {cx:.1f},{h - sw:.1f} {sw:.1f},{cy:.1f}"
    return (f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.2f}"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{min(w, h) / 8:.1f}" fill="{accent}"/>')


def _documents(w, h, fill, stroke, sw):
    """Stacked text pages (memory of reflections, logs, a corpus): two sheets behind, a front page with a folded
    corner and text lines — reads as written text, not as a feature map or a database."""
    off = max(3.0, min(w, h) / 9)
    pw, ph = w - 2 * off - sw, h - 2 * off - sw
    fold = min(pw, ph) / 4
    out = []
    for k in (2, 1):  # back sheets up-right
        x, y = sw / 2 + k * off, sw / 2 + (2 - k) * off
        out.append(f'<path d="M{x:.1f},{y:.1f} h{pw:.1f} v{ph:.1f} h{-pw:.1f} Z" fill="{_mix(fill, "#ffffff", 0.35 * k)}" '
                   f'stroke="{stroke}" stroke-width="{sw:.2f}"/>')
    x, y = sw / 2, sw / 2 + 2 * off
    out.append(f'<path d="M{x:.1f},{y:.1f} h{pw - fold:.1f} l{fold:.1f},{fold:.1f} v{ph - fold:.1f} h{-pw:.1f} Z" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.2f}"/>')
    out.append(f'<path d="M{x + pw - fold:.1f},{y:.1f} v{fold:.1f} h{fold:.1f}" fill="none" stroke="{stroke}" '
               f'stroke-width="{sw:.2f}"/>')
    lx0, lx1 = x + pw * 0.18, x + pw * 0.82
    for j, f in enumerate((0.42, 0.58, 0.74, 0.88)):
        x1 = lx1 if j < 3 else x + pw * 0.55  # the last line is short, like the end of a paragraph
        out.append(f'<line x1="{lx0:.1f}" y1="{y + ph * f:.1f}" x2="{x1:.1f}" y2="{y + ph * f:.1f}" stroke="{stroke}" '
                   f'stroke-width="{sw:.2f}" stroke-linecap="round"/>')
    return "".join(out)


def _heatmap(w, h, fill, stroke, k=8):
    """A smooth blob on a k×k grid: a schematic response map, light (low) to the tone's dark (high)."""
    cw, ch = w / k, h / k
    hi = _mix(stroke, "#000000", 0.3)  # the peak reads clearly even with a pastel tone
    out = []
    for i in range(k):
        for j in range(k):
            v = math.exp(-(((i - 2.6) / 2.2) ** 2 + ((j - 4.8) / 2.6) ** 2)) * 0.85 + \
                math.exp(-(((i - 6.0) / 1.4) ** 2 + ((j - 1.8) / 1.6) ** 2)) * 0.45
            out.append(f'<rect x="{j * cw:.2f}" y="{i * ch:.2f}" width="{cw + 0.2:.2f}" height="{ch + 0.2:.2f}" '
                       f'fill="{_mix("#ffffff", hi, min(1.0, v))}"/>')
    return "".join(out)


MASK_COLORS = ("#E69F00", "#56B4E9", "#009E73")  # Okabe-Ito: label maps are conventionally saturated, colour-blind safe


def _mask(w, h, tones=None):
    """A schematic label map: dark background, three organ-like regions in distinct (style-independent) colours."""
    a, b, c = MASK_COLORS
    return (f'<rect width="{w:.1f}" height="{h:.1f}" fill="#1f2933"/>'
            f'<ellipse cx="{w * .38:.1f}" cy="{h * .45:.1f}" rx="{w * .22:.1f}" ry="{h * .17:.1f}" fill="{a}"/>'
            f'<ellipse cx="{w * .68:.1f}" cy="{h * .40:.1f}" rx="{w * .12:.1f}" ry="{h * .20:.1f}" fill="{b}"/>'
            f'<ellipse cx="{w * .52:.1f}" cy="{h * .74:.1f}" rx="{w * .16:.1f}" ry="{h * .09:.1f}" fill="{c}"/>')


def _kspace(w, h, pattern, sw):
    """Schematic k-space: dark field, bright low-frequency centre, the sampling pattern in white lines."""
    cx, cy = w / 2, h / 2
    glow = "".join(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{min(w, h) * f:.1f}" fill="#ffffff" fill-opacity="{o}"/>'
                   for f, o in ((0.30, 0.10), (0.18, 0.22), (0.09, 0.55)))
    lines = []
    if pattern == "radial":
        for k in range(8):
            a = math.pi * k / 8
            dx, dy = math.cos(a) * w / 2, math.sin(a) * h / 2
            lines.append((cx - dx, cy - dy, cx + dx, cy + dy))
    elif pattern == "random":
        rows = [0.08, 0.21, 0.30, 0.42, 0.46, 0.50, 0.54, 0.58, 0.71, 0.88]  # fixed: dense centre, sparse edge
        lines = [(0, h * r, w, h * r) for r in rows]
    else:  # cartesian: every 4th phase-encode line plus a fully sampled centre
        rows = sorted({*(i / 16 for i in range(1, 16, 4)), 0.44, 0.47, 0.5, 0.53, 0.56})
        lines = [(0, h * r, w, h * r) for r in rows]
    ln = "".join(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#ffffff" stroke-width="{sw:.2f}" '
                 f'stroke-opacity="0.9"/>' for x1, y1, x2, y2 in lines)
    return f'<rect width="{w:.1f}" height="{h:.1f}" fill="#0b0f14"/>' + glow + ln


def glyph_svg(name: str, w: float, h: float, fill: str, stroke: str, accent: str, *, nodes: int = 5,
              pattern: str = "cartesian", tones: list[str] | None = None, ink: float = 1.0) -> str:
    sw = 1.2 * ink
    if name == "graph":
        body = _graph(w, h, fill, stroke, accent, max(3, min(8, nodes)), sw)
    elif name == "database":
        body = _database(w, h, fill, stroke, sw)
    elif name == "prototype":
        body = _prototype(w, h, fill, stroke, accent, sw)
    elif name == "heatmap":
        body = _heatmap(w, h, fill, stroke)
    elif name == "mask":
        body = _mask(w, h, list(tones or []))
    elif name == "documents":
        body = _documents(w, h, fill, stroke, sw)
    elif name == "kspace":
        body = _kspace(w, h, pattern, 0.9 * ink)
    else:
        raise ValueError(f"unknown glyph '{name}' (one of {', '.join(GLYPHS)})")
    return _svg(w, h, body)


def glyph_data_uri(svg: str) -> str:
    return "data:image/svg+xml," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
