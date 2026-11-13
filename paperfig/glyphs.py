"""Glyph visuals (round 3; the user's design guide §9.1): small deterministic SVG symbols for representations the
box vocabulary cannot show — a graph neighbourhood, a database, a prototype, a schematic heatmap, a segmentation
mask, k-space with its sampling pattern. Drawn in the node's tone; nothing random, so a rebuild is identical.
Heatmap, mask and k-space look like data: they are schematic and must be marked `illustrative` (lint)."""
from __future__ import annotations

import base64
import math

from . import color

GLYPHS = ("graph", "database", "prototype", "heatmap", "mask", "kspace", "documents", "pointcloud", "waveform",
          "spectrogram", "trajectory", "molecule", "plot")
SCHEMATIC = ("heatmap", "mask", "kspace", "pointcloud", "waveform", "spectrogram", "trajectory", "molecule", "plot")
# ^ look like data: always marked illustrative (lint schematic-unmarked); a real sample goes in an image node
VARIANTS = {"pointcloud": ("chair", "airplane", "blob", "scene"), "plot": ("decay", "rise", "bell", "schedule")}
DEFAULT_SIZE = {"graph": (60, 52), "database": (40, 50), "prototype": (34, 34), "heatmap": (56, 56), "mask": (56, 56),
                "kspace": (56, 56), "documents": (44, 52), "pointcloud": (64, 56), "waveform": (84, 32),
                "spectrogram": (76, 44), "trajectory": (64, 52), "molecule": (64, 52), "plot": (64, 46)}


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


# ------------------------------------------------------------------ procedural data thumbnails (round 7)
def _rng(seed: int):
    import random
    return random.Random(seed)  # fixed seed: a rebuild draws the same picture


_SHAPES = {  # point-cloud primitives: boxes (cx, cy, cz, sx, sy, sz) in a unit cube, sampled on their surfaces
    "chair": [(0, 0.05, 0, .9, .12, .9), (0, .55, -.42, .9, .9, .12), (-.38, -.45, -.38, .1, .9, .1),
              (.38, -.45, -.38, .1, .9, .1), (-.38, -.45, .38, .1, .9, .1), (.38, -.45, .38, .1, .9, .1)],
    "airplane": [(0, 0, 0, 2.0, .2, .2), (.1, 0, 0, .42, .04, 2.0), (-.85, .22, 0, .22, .45, .04),
                 (-.88, .04, 0, .2, .03, .75), (.95, -.02, 0, .15, .14, .14)],
    "scene": [(0, -.6, 0, 2.0, .04, 1.6), (-.5, -.3, -.2, .5, .6, .5), (.45, -.15, .3, .4, .9, .4)],
}


def _cloud(variant: str, n: int = 220):
    r = _rng(7)
    pts = []
    if variant == "blob":
        for _ in range(n):
            import math as m
            u, v = r.uniform(-1, 1), r.uniform(0, 2 * m.pi)
            rad = 0.8 + 0.12 * m.sin(3 * v) * (1 - u * u)
            pts.append((rad * m.sqrt(1 - u * u) * m.cos(v), rad * u * 0.85, rad * m.sqrt(1 - u * u) * m.sin(v)))
        return pts
    boxes = _SHAPES[variant]
    areas = [2 * (sx * sy + sy * sz + sx * sz) for *_, sx, sy, sz in boxes]
    tot = sum(areas)
    for (cx, cy, cz, sx, sy, sz), a in zip(boxes, areas):
        for _ in range(max(4, round(n * a / tot))):
            face = r.randrange(3)
            p = [r.uniform(-.5, .5) * sx, r.uniform(-.5, .5) * sy, r.uniform(-.5, .5) * sz]
            p[face] = (.5 if r.random() < .5 else -.5) * (sx, sy, sz)[face]
            pts.append((cx + p[0], cy + p[1], cz + p[2]))
    return pts


_VIEW = {"chair": (35, 22), "airplane": (30, 48), "blob": (30, 20), "scene": (35, 30)}  # yaw, pitch (deg) per shape


def _pointcloud(w, h, fill, stroke, variant):
    """Surface samples of a simple shape seen from above-front, shaded by depth (near = dark)."""
    import math as m
    pts = _cloud(variant, n=420)
    ya, pa = (m.radians(a) for a in _VIEW.get(variant, (30, 25)))
    proj = []
    for x, y, z in pts:
        x1, z1 = x * m.cos(ya) - z * m.sin(ya), x * m.sin(ya) + z * m.cos(ya)  # turn about the vertical axis
        y2, z2 = y * m.cos(pa) - z1 * m.sin(pa), y * m.sin(pa) + z1 * m.cos(pa)  # tilt towards the viewer
        proj.append((x1, -y2, z2))
    xs, ys = [p[0] for p in proj], [p[1] for p in proj]
    sx, sy = (w - 6) / max(1e-6, max(xs) - min(xs)), (h - 6) / max(1e-6, max(ys) - min(ys))
    k = min(sx, sy)
    ox, oy = (w - k * (max(xs) - min(xs))) / 2 - k * min(xs), (h - k * (max(ys) - min(ys))) / 2 - k * min(ys)
    dmin, dmax = min(p[2] for p in proj), max(p[2] for p in proj)
    dark = _mix(stroke, "#000000", 0.25)
    rad = max(0.6, min(w, h) / 60)
    out = []
    for x, y, d in sorted(proj, key=lambda p: -p[2]):  # far first
        t = (d - dmin) / max(1e-6, dmax - dmin)
        out.append(f'<circle cx="{ox + k * x:.1f}" cy="{oy + k * y:.1f}" r="{rad:.2f}" fill="{_mix(dark, fill, 0.1 + 0.7 * t)}"/>')
    return "".join(out)


def _waveform(w, h, stroke, sw):
    """Speech-like bursts: a carrier under a syllable envelope, around a faint zero line."""
    import math as m
    n = 180
    pts = []
    for i in range(n):
        t = i / (n - 1)
        env = sum(a * m.exp(-((t - c) / s) ** 2) for a, c, s in ((1, .2, .07), (.75, .47, .09), (.9, .76, .06)))
        y = env * (0.6 * m.sin(2 * m.pi * 23 * t) + 0.4 * m.sin(2 * m.pi * 41 * t + 1.3))
        pts.append((t * w, h / 2 - y * (h / 2 - 2)))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (f'<line x1="0" y1="{h / 2:.1f}" x2="{w:.1f}" y2="{h / 2:.1f}" stroke="{_mix(stroke, "#ffffff", .6)}" '
            f'stroke-width="{sw * .6:.2f}"/><polyline points="{line}" fill="none" stroke="{stroke}" '
            f'stroke-width="{sw * .8:.2f}" stroke-linejoin="round"/>')


def _spectrogram(w, h, stroke, cols=56, rows=30):
    """Time × frequency energy: harmonic stripes whose strength follows the same syllables as the waveform."""
    import math as m
    hi = _mix(stroke, "#000000", 0.5)
    cw, ch = w / cols, h / rows
    out = []
    for i in range(cols):
        t = i / (cols - 1)
        env = sum(a * m.exp(-((t - c) / s) ** 2) for a, c, s in ((1, .2, .08), (.75, .47, .1), (.9, .76, .07)))
        f0 = 4.6 + 1.4 * m.sin(2 * m.pi * t)
        for j in range(rows):
            f = rows - 1 - j  # low frequencies at the bottom
            harm = sum(m.exp(-((f - k * f0) / 0.45) ** 2) * (0.88 ** k) for k in range(1, 7))
            v = min(1.0, 0.04 + 1.25 * env * harm) ** 0.8
            out.append(f'<rect x="{i * cw:.2f}" y="{j * ch:.2f}" width="{cw + .2:.2f}" height="{ch + .2:.2f}" '
                       f'fill="{_mix("#ffffff", hi, v)}"/>')
    return "".join(out)


def _trajectory(w, h, fill, stroke, accent, sw):
    """A 2-D path over a faint grid: start dot, step markers, goal star."""
    import math as m
    grid = "".join(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h:.1f}" stroke="{_mix(stroke, "#ffffff", .8)}" '
                   f'stroke-width="{sw * .5:.2f}"/>' for x in (w / 4, w / 2, 3 * w / 4))
    grid += "".join(f'<line x1="0" y1="{y:.1f}" x2="{w:.1f}" y2="{y:.1f}" stroke="{_mix(stroke, "#ffffff", .8)}" '
                    f'stroke-width="{sw * .5:.2f}"/>' for y in (h / 3, 2 * h / 3))
    pts = [(w * (0.1 + 0.8 * t), h * (0.82 - 0.55 * t - 0.18 * m.sin(m.pi * 2.2 * t))) for t in (i / 9 for i in range(10))]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    r = max(1.6, min(w, h) / 26)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * .7:.2f}" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="{sw * .6:.2f}"/>' for x, y in pts[1:-1])
    gx, gy = pts[-1]
    star = " ".join(f"{gx + (r * 2.2 if k % 2 == 0 else r) * m.cos(m.pi / 2 + k * m.pi / 5):.1f},"
                    f"{gy - (r * 2.2 if k % 2 == 0 else r) * m.sin(m.pi / 2 + k * m.pi / 5):.1f}" for k in range(10))
    sx, sy = pts[0]
    return (grid + f'<polyline points="{path}" fill="none" stroke="{stroke}" stroke-width="{sw:.2f}"/>' + dots +
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{r * 1.3:.2f}" fill="{stroke}"/>'
            f'<polygon points="{star}" fill="{accent}" stroke="{stroke}" stroke-width="{sw * .6:.2f}"/>')


CPK = {"C": "#909090", "O": "#e0423a", "N": "#3b5bdb", "H": "#ffffff"}  # conventional element colours


def _molecule(w, h, sw):
    """Ball-and-stick of a small aromatic molecule (a ring with substituents), element colours by convention."""
    import math as m
    ring = [(m.cos(m.pi / 6 + k * m.pi / 3), m.sin(m.pi / 6 + k * m.pi / 3)) for k in range(6)]
    atoms = [("C", x, y) for x, y in ring]
    atoms += [("O", ring[0][0] * 1.9, ring[0][1] * 1.9), ("N", ring[3][0] * 1.9, ring[3][1] * 1.9),
              ("C", ring[1][0] * 1.9, ring[1][1] * 1.9), ("O", ring[1][0] * 2.6 + .5, ring[1][1] * 2.6),
              ("H", ring[2][0] * 1.75, ring[2][1] * 1.75), ("H", ring[4][0] * 1.75, ring[4][1] * 1.75),
              ("H", ring[5][0] * 1.75, ring[5][1] * 1.75)]
    bonds = [(k, (k + 1) % 6) for k in range(6)] + [(0, 6), (3, 7), (1, 8), (8, 9), (2, 10), (4, 11), (5, 12)]
    xs, ys = [a[1] for a in atoms], [a[2] for a in atoms]
    span_x, span_y = max(xs) - min(xs) + 0.7, max(ys) - min(ys) + 0.7  # + an atom's diameter: nothing clipped
    k = min((w - 2 * sw) / span_x, (h - 2 * sw) / span_y)
    ox, oy = (w - k * span_x) / 2 + k * 0.35 - k * min(xs), (h - k * span_y) / 2 + k * 0.35 - k * min(ys)
    P = [(ox + k * x, oy + k * y) for _, x, y in atoms]
    out = [f'<line x1="{P[a][0]:.1f}" y1="{P[a][1]:.1f}" x2="{P[b][0]:.1f}" y2="{P[b][1]:.1f}" stroke="#4b5563" '
           f'stroke-width="{sw * 1.4:.2f}"/>' for a, b in bonds]
    for (el, _, _), (x, y) in zip(atoms, P):
        rr = k * (0.22 if el == "H" else 0.32)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}" fill="{CPK[el]}" stroke="#374151" stroke-width="{sw * .6:.2f}"/>')
    return "".join(out)


def _plot(w, h, stroke, accent, sw, variant):
    """Bare axes and one curve: a loss decaying, a score rising, a bell-shaped density, a cosine noise schedule."""
    import math as m
    x0, y0, x1, y1 = 4.0, h - 4.0, w - 2.0, 2.0
    f = {"decay": lambda t: 0.08 + 0.9 * m.exp(-4.5 * t), "rise": lambda t: 0.1 + 0.85 * (1 - m.exp(-4 * t)),
         "bell": lambda t: 0.06 + 0.9 * m.exp(-((t - .5) / .17) ** 2),
         "schedule": lambda t: 0.04 + 0.92 * m.cos((t + 0.008) / 1.008 * m.pi / 2) ** 2}[variant]
    pts = " ".join(f"{x0 + (x1 - x0) * t:.1f},{y0 - (y0 - y1) * f(t):.1f}" for t in (i / 59 for i in range(60)))
    axes = (f'<polyline points="{x0:.1f},{y1:.1f} {x0:.1f},{y0:.1f} {x1:.1f},{y0:.1f}" fill="none" stroke="#4b5563" '
            f'stroke-width="{sw * .8:.2f}"/>')
    return axes + f'<polyline points="{pts}" fill="none" stroke="{_mix(accent, stroke, .3)}" stroke-width="{sw * 1.3:.2f}"/>'


def glyph_svg(name: str, w: float, h: float, fill: str, stroke: str, accent: str, *, nodes: int = 5,
              pattern: str = "cartesian", tones: list[str] | None = None, ink: float = 1.0,
              variant: str | None = None) -> str:
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
    elif name == "pointcloud":
        body = _pointcloud(w, h, fill, stroke, variant or "chair")
    elif name == "waveform":
        body = _waveform(w, h, stroke, sw)
    elif name == "spectrogram":
        body = _spectrogram(w, h, stroke)
    elif name == "trajectory":
        body = _trajectory(w, h, fill, stroke, accent, sw)
    elif name == "molecule":
        body = _molecule(w, h, sw)
    elif name == "plot":
        body = _plot(w, h, stroke, accent, sw, variant or "decay")
    elif name == "kspace":
        body = _kspace(w, h, pattern, 0.9 * ink)
    else:
        raise ValueError(f"unknown glyph '{name}' (one of {', '.join(GLYPHS)})")
    return _svg(w, h, body)


def glyph_data_uri(svg: str) -> str:
    return "data:image/svg+xml," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
