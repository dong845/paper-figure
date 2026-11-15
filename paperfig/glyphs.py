"""Glyph visuals (round 3; the user's design guide §9.1): small deterministic SVG symbols for representations the
box vocabulary cannot show — a graph neighbourhood, a database, a prototype, a schematic heatmap, a segmentation
mask, k-space with its sampling pattern. Drawn in the node's tone; nothing random, so a rebuild is identical.
Heatmap, mask and k-space look like data: they are schematic and must be marked `illustrative` (lint)."""
from __future__ import annotations

import base64
import math

from . import color

GLYPHS = ("graph", "database", "prototype", "heatmap", "mask", "kspace", "documents", "pointcloud", "waveform",
          "spectrogram", "trajectory", "molecule", "plot", "onehot", "vector", "patches", "mr-image", "sampling-mask",
          "coil-maps", "natural-image", "ellipsis", "pair-matrix")
SCHEMATIC = ("heatmap", "mask", "kspace", "pointcloud", "waveform", "spectrogram", "trajectory", "molecule", "plot",
             "mr-image", "sampling-mask", "coil-maps", "natural-image")
# ^ look like data: always marked illustrative (lint schematic-unmarked); a real sample goes in an image node
VARIANTS = {"pointcloud": ("chair", "airplane", "blob", "scene"), "plot": ("decay", "rise", "bell", "schedule"),
            "patches": ("regular", "shifted"), "mr-image": ("clean", "aliased"),
            "graph": ("star", "neighbourhood", "khop", "aggregate", "subgraph", "layers"),
            "natural-image": ("clean", "degraded"), "pair-matrix": ("one-to-one", "many-to-one", "many-to-many")}
GRIDDED = {"onehot": (4, 5), "patches": (8, 8), "pair-matrix": (5, 5)}  # glyphs whose `grid` [rows, cols] means something (defaults)
DEFAULT_SIZE = {"graph": (60, 52), "database": (40, 50), "prototype": (34, 34), "heatmap": (56, 56), "mask": (56, 56),
                "kspace": (56, 56), "documents": (44, 52), "pointcloud": (64, 56), "waveform": (84, 32),
                "spectrogram": (76, 44), "trajectory": (64, 52), "molecule": (64, 52), "plot": (64, 46),
                "onehot": (50, 40), "vector": (16, 50), "patches": (56, 56), "mr-image": (56, 56),
                "sampling-mask": (56, 56), "coil-maps": (64, 60), "natural-image": (64, 48), "ellipsis": (26, 10),
                "pair-matrix": (60, 60)}


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


TWO_HOP = (  # a toy neighbourhood: centre, one-hop ring (indices 1-5), two-hop leaves; positions in [-1, 1]
    (0.0, 0.0), (0.42, -0.30), (-0.44, -0.22), (-0.30, 0.40), (0.36, 0.38), (0.02, -0.52),
    (0.86, -0.58), (0.80, 0.02), (-0.88, -0.60), (-0.84, 0.30), (-0.52, 0.86), (0.66, 0.84), (0.10, -0.94))
TWO_HOP_EDGES = ((0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 6), (1, 7), (2, 8), (3, 9), (3, 10), (4, 11), (5, 12),
                 (1, 5), (3, 4))
SAMPLED = {1, 3, 4, 6, 10, 11}  # the uniform sample a GraphSAGE-like method keeps (one and two hops)


def _graph_neighbourhood(w, h, fill, stroke, accent, sw, variant):
    """A node's two-hop neighbourhood, for figures that explain on the graph itself (user 2026-11-14: GraphSAGE's own
    figure — sample, then aggregate — explains more than a pipeline). 'khop': hop rings, the sampled neighbours and
    edges in the accent's tint, the rest faint. 'aggregate': only the sampled part, arrows carrying messages toward
    the centre (two hops -> one hop -> centre)."""
    s = min(w, h) / 2 - 4
    cx, cy = w / 2, h / 2
    P = [(cx + x * s, cy + y * s) for x, y in TWO_HOP]
    tint = _mix(accent, "#ffffff", 0.45)
    nr = max(2.6, min(w, h) / 15)
    out = []
    if variant == "khop":
        for rr in (0.62, 1.0):
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr * s:.1f}" fill="none" stroke="{stroke}" '
                       f'stroke-width="{0.7 * sw:.2f}" stroke-dasharray="1.6 2.2" opacity="0.7"/>')
    keep = lambda a, b: a in SAMPLED | {0} and b in SAMPLED | {0} and (0 in (a, b) or (a in SAMPLED and b in SAMPLED))
    if variant == "aggregate":
        out.append(f'<defs><marker id="pfah" viewBox="0 0 6 6" refX="5.4" refY="3" markerWidth="{3.2 * sw:.1f}" '
                   f'markerHeight="{3.2 * sw:.1f}" orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6 z" fill="{accent}"/>'
                   '</marker></defs>')
        for a, b in TWO_HOP_EDGES:
            if not keep(a, b) or (1 <= a <= 5 and 1 <= b <= 5):  # messages go toward the centre, not across a ring
                continue
            src, dst = (b, a) if a == 0 or (a in range(1, 6) and b >= 6) else (a, b)  # messages flow inward
            (x1, y1), (x2, y2) = P[src], P[dst]
            d = math.hypot(x2 - x1, y2 - y1) or 1
            ux, uy = (x2 - x1) / d, (y2 - y1) / d
            out.append(f'<line x1="{x1 + ux * nr:.1f}" y1="{y1 + uy * nr:.1f}" x2="{x2 - ux * (nr + 1.5):.1f}" '
                       f'y2="{y2 - uy * (nr + 1.5):.1f}" stroke="{accent}" stroke-width="{1.3 * sw:.2f}" marker-end="url(#pfah)"/>')
        nodes = [i for i in range(len(P)) if i == 0 or i in SAMPLED]
    else:
        for a, b in TWO_HOP_EDGES:
            on = variant == "khop" and keep(a, b)
            out.append(f'<line x1="{P[a][0]:.1f}" y1="{P[a][1]:.1f}" x2="{P[b][0]:.1f}" y2="{P[b][1]:.1f}" '
                       f'stroke="{accent if on else stroke}" stroke-width="{(1.6 if on else 0.8) * sw:.2f}" '
                       f'opacity="{1 if on or variant != "khop" else 0.45}"/>')
        nodes = list(range(len(P)))
    for i in nodes:
        x, y = P[i]
        f = accent if i == 0 else (tint if (variant in ("khop", "aggregate") and i in SAMPLED) else "#ffffff")
        faint = variant == "khop" and i != 0 and i not in SAMPLED  # opaque, so no line shows through it
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{nr:.1f}" fill="{f}" stroke="{stroke}" stroke-width="{sw:.2f}" '
                   f'stroke-opacity="{0.45 if faint else 1}"/>')
    return "".join(out)


TOY = ((-0.86, 0.0), (-0.52, -0.62), (-0.48, 0.62), (-0.08, -0.05), (0.18, -0.70), (0.30, 0.60), (0.62, -0.20),
       (0.90, 0.35), (0.92, -0.72), (0.62, 0.92))
TOY_EDGES = ((0, 1), (0, 2), (1, 3), (2, 3), (0, 3), (3, 5), (3, 4), (4, 6), (5, 7), (6, 7), (6, 8), (7, 9), (5, 9),
             (4, 8))
TOY_SUB = (0, 1, 2, 3, 5, 7)  # the induced subgraph a sampler keeps (GraphSAINT blind run: no hop rings, no centre)


def _graph_subgraph(w, h, fill, stroke, accent, sw):
    """A toy graph with an induced subgraph picked out: its nodes and edges bold in the accent, the rest faint."""
    s = min(w / 2, h / 2) - 4
    cx, cy = w / 2, h / 2
    P = [(cx + x * (w / 2 - 6), cy + y * (h / 2 - 6)) for x, y in TOY]
    nr = max(2.6, min(w, h) / 13)
    tint = _mix(accent, "#ffffff", 0.45)
    out = []
    for a, b in TOY_EDGES:
        on = a in TOY_SUB and b in TOY_SUB
        out.append(f'<line x1="{P[a][0]:.1f}" y1="{P[a][1]:.1f}" x2="{P[b][0]:.1f}" y2="{P[b][1]:.1f}" '
                   f'stroke="{accent if on else stroke}" stroke-width="{(1.7 if on else 0.8) * sw:.2f}" '
                   f'stroke-opacity="{1 if on else 0.4}"/>')
    for i, (x, y) in enumerate(P):
        on = i in TOY_SUB
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{nr:.1f}" fill="{tint if on else "#ffffff"}" stroke="{stroke}" '
                   f'stroke-width="{sw:.2f}" stroke-opacity="{1 if on else 0.4}"/>')
    return "".join(out)


def _graph_layers(w, h, fill, stroke, accent, sw, rows=3):
    """A GCN unrolled over a (sub)graph: the subgraph's nodes in each layer, edges from a node's neighbours (and
    itself) in the layer below — every node is embedded, not one centre (GraphSAINT blind run)."""
    nodes = TOY_SUB
    adj = {v: {v} | {b for a, b in TOY_EDGES if a == v and b in nodes} | {a for a, b in TOY_EDGES if b == v and a in nodes}
           for v in nodes}
    n = len(nodes)
    nr = max(2.2, min(w / (4.2 * n), h / (5.0 * rows)))
    xs = [nr + 2 + i * (w - 2 * nr - 4) / (n - 1) for i in range(n)]
    ys = [h - nr - 2 - r * (h - 2 * nr - 4) / (rows - 1) for r in range(rows)]
    tint = _mix(accent, "#ffffff", 0.45)
    out = []
    for r in range(rows - 1):
        for j, v in enumerate(nodes):
            for i, u in enumerate(nodes):
                if u in adj[v]:
                    out.append(f'<line x1="{xs[i]:.1f}" y1="{ys[r] - nr:.1f}" x2="{xs[j]:.1f}" y2="{ys[r + 1] + nr:.1f}" '
                               f'stroke="{stroke}" stroke-width="{0.7 * sw:.2f}" stroke-opacity="0.75"/>')
    for r in range(rows):
        for j in range(n):
            out.append(f'<circle cx="{xs[j]:.1f}" cy="{ys[r]:.1f}" r="{nr:.1f}" fill="{tint}" stroke="{stroke}" '
                       f'stroke-width="{sw:.2f}"/>')
    return "".join(out)


def _natural_image(w, h, variant):
    """A licence-free natural-image stand-in (sky, sun, two ridges, a lake) for imaging methods on natural pictures;
    'degraded' is a measured/undersampled version: blurred and blocky (ISTA-Net blind run: the MR phantom stood in for
    natural images and the critic read it as MRI)."""
    body = (f'<defs><linearGradient id="pfsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fb2e0"/>'
            f'<stop offset="1" stop-color="#e8f1f8"/></linearGradient></defs>'
            f'<rect width="{w:.1f}" height="{h:.1f}" fill="url(#pfsky)"/>'
            f'<circle cx="{w * .74:.1f}" cy="{h * .26:.1f}" r="{min(w, h) * .1:.1f}" fill="#f6d36b"/>'
            f'<path d="M0 {h * .62:.1f} L{w * .22:.1f} {h * .36:.1f} L{w * .42:.1f} {h * .58:.1f} L{w * .62:.1f} '
            f'{h * .40:.1f} L{w:.1f} {h * .66:.1f} L{w:.1f} {h:.1f} L0 {h:.1f} Z" fill="#6f8f6a"/>'
            f'<path d="M0 {h * .74:.1f} Q{w * .35:.1f} {h * .60:.1f} {w * .7:.1f} {h * .72:.1f} T{w:.1f} {h * .70:.1f} '
            f'L{w:.1f} {h:.1f} L0 {h:.1f} Z" fill="#3f6a4a"/>'
            f'<ellipse cx="{w * .5:.1f}" cy="{h * .88:.1f}" rx="{w * .3:.1f}" ry="{h * .06:.1f}" fill="#5f8fbf"/>')
    if variant == "degraded":  # a measured / undersampled reconstruction: blurred, a little noisy, lower contrast
        return (f'<defs><filter id="pfdeg" x="0" y="0" width="100%" height="100%"><feGaussianBlur stdDeviation="{0.035 * w:.2f}"/></filter>'
                f'<filter id="pfnoise" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" '
                f'baseFrequency="{3.2 / max(w, 1):.3f}" numOctaves="2" seed="7"/><feColorMatrix type="saturate" values="0"/>'
                f'</filter><clipPath id="pfdclip"><rect width="{w:.1f}" height="{h:.1f}"/></clipPath></defs>'
                f'<g clip-path="url(#pfdclip)"><g filter="url(#pfdeg)">{body}</g>'
                f'<rect width="{w:.1f}" height="{h:.1f}" filter="url(#pfnoise)" opacity="0.22"/>'
                f'<rect width="{w:.1f}" height="{h:.1f}" fill="#ffffff" opacity="0.12"/></g>')
    return body


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


# ---------------------------------------------- MRI data (user 2026-11-14: VS-Net's input, mask and coil maps were
# placeholder boxes; the fastMRI knees cannot be redistributed — draw licence-free stand-ins instead)
SHEPP_LOGAN = (  # modified Shepp-Logan phantom: centre x, y, half-axes a, b, angle (deg), resulting grey (display)
    (0.0, 0.0, 0.69, 0.92, 0, 0.93), (0.0, -0.0184, 0.6624, 0.874, 0, 0.36),
    (0.22, 0.0, 0.11, 0.31, -18, 0.12), (-0.22, 0.0, 0.16, 0.41, 18, 0.12),
    (0.0, 0.35, 0.21, 0.25, 0, 0.55), (0.0, 0.1, 0.046, 0.046, 0, 0.55), (0.0, -0.1, 0.046, 0.046, 0, 0.55),
    (-0.08, -0.605, 0.046, 0.023, 0, 0.55), (0.0, -0.606, 0.023, 0.023, 0, 0.55), (0.06, -0.605, 0.023, 0.046, 0, 0.55))


def _phantom(w, h):
    s = min(w, h) / 2
    cx, cy = w / 2, h / 2
    out = []
    for x, y, a, b, ang, g in SHEPP_LOGAN:
        v = int(round(255 * g))
        out.append(f'<ellipse cx="{cx + x * s:.2f}" cy="{cy - y * s:.2f}" rx="{a * s:.2f}" ry="{b * s:.2f}" '
                   f'transform="rotate({-ang} {cx + x * s:.2f} {cy - y * s:.2f})" fill="rgb({v},{v},{v})"/>')
    return "".join(out)


def _mr_image(w, h, variant):
    """A licence-free MR stand-in: the modified Shepp-Logan phantom (the standard test image of MR reconstruction).
    'aliased' is the undersampled input: faint copies shifted along the phase-encode axis (fold-over) and a blur."""
    img = _phantom(w, h)
    if variant == "aliased":
        ghosts = "".join(f'<g opacity="0.33" transform="translate(0 {dy:.2f})">{img}</g>' for dy in (-h / 3, h / 3))
        return (f'<defs><filter id="pfblur"><feGaussianBlur stdDeviation="{0.012 * w:.2f}"/></filter>'
                f'<clipPath id="pfclip"><rect width="{w:.1f}" height="{h:.1f}"/></clipPath></defs>'
                f'<rect width="{w:.1f}" height="{h:.1f}" fill="#000"/>'
                f'<g clip-path="url(#pfclip)" filter="url(#pfblur)">{ghosts}{img}</g>')
    return f'<rect width="{w:.1f}" height="{h:.1f}" fill="#000"/>' + img


def _sampling_mask(w, h, pattern, sw):
    """The undersampling mask itself (not k-space): white sampled lines on black — Cartesian columns with a fully
    sampled centre, radial spokes, or variable-density random columns."""
    lines = []
    if pattern == "radial":
        cx, cy = w / 2, h / 2
        for k in range(10):
            a = math.pi * k / 10
            dx, dy = math.cos(a) * w, math.sin(a) * h
            lines.append((cx - dx, cy - dy, cx + dx, cy + dy, sw))
    else:
        cols = ([0.06, 0.17, 0.29, 0.38, 0.44, 0.47, 0.5, 0.53, 0.56, 0.62, 0.73, 0.9] if pattern == "random"
                else sorted({*(i / 16 for i in range(1, 16, 4)), 0.44, 0.47, 0.5, 0.53, 0.56}))
        lines = [(w * c, 0, w * c, h, max(sw, w / 40)) for c in cols]
    ln = "".join(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#ffffff" stroke-width="{s:.2f}"/>'
                 for x1, y1, x2, y2, s in lines)
    return (f'<defs><clipPath id="pfmclip"><rect width="{w:.1f}" height="{h:.1f}"/></clipPath></defs>'
            f'<rect width="{w:.1f}" height="{h:.1f}" fill="#000"/><g clip-path="url(#pfmclip)">{ln}</g>')


def _coil_maps(w, h, n=4):
    """Coil sensitivity maps: a stack of smooth maps, each bright near its own coil (top, right, bottom, left)."""
    off = min(w, h) * 0.08
    mw, mh = w - off * (n - 1), h - off * (n - 1)
    spots = [(0.5, 0.05), (0.95, 0.5), (0.5, 0.95), (0.05, 0.5)]
    defs, body = [], []
    for k in range(n):
        fx, fy = spots[k % len(spots)]
        defs.append(f'<radialGradient id="pfcoil{k}" cx="{fx}" cy="{fy}" r="0.85"><stop offset="0" stop-color="#f2f2f2"/>'
                    f'<stop offset="0.55" stop-color="#6b6b6b"/><stop offset="1" stop-color="#0d0d0d"/></radialGradient>')
    for k in reversed(range(n)):  # back maps first; the front one bottom-left
        x, y = off * (n - 1 - k), off * k
        body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{mw:.1f}" height="{mh:.1f}" fill="url(#pfcoil{k})" '
                    f'stroke="#ffffff" stroke-width="0.6"/>')
    return "<defs>" + "".join(defs) + "</defs>" + "".join(body)


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


# ------------------------------------------------------------------ structure glyphs (round 8)
def _onehot(w, h, fill, stroke, sw, grid, seed: str):
    """A categorical latent: rows of classes, exactly one class on per row (where, fixed by the node id)."""
    import zlib
    r, c = grid
    cw, ch = w / c, h / r
    on = _mix(stroke, "#000000", 0.55)
    k = zlib.crc32(seed.encode())
    out = []
    for i in range(r):
        hot = (k >> (3 * i)) % c
        for j in range(c):
            out.append(f'<rect data-row="{i}" data-on="{1 if j == hot else 0}" x="{j * cw + sw / 2:.2f}" '
                       f'y="{i * ch + sw / 2:.2f}" width="{cw - sw:.2f}" height="{ch - sw:.2f}" '
                       f'fill="{on if j == hot else "#ffffff"}" stroke="{stroke}" stroke-width="{sw * 0.6:.2f}"/>')
    return "".join(out)


def _vector(w, h, fill, stroke, sw, n):
    """A vector: a column of cells between square brackets (an embedding, a state, proprioception)."""
    b = max(2.5, w * 0.22)  # bracket arm
    cx0, cx1 = b + sw, w - b - sw
    ch = (h - 2 * sw) / n
    out = [f'<rect x="{cx0:.2f}" y="{sw + i * ch + sw / 2:.2f}" width="{cx1 - cx0:.2f}" height="{ch - sw:.2f}" '
           f'fill="{_mix(fill, "#ffffff", 0.15 * (i % 2))}" stroke="{stroke}" stroke-width="{sw * 0.6:.2f}"/>' for i in range(n)]
    for x0, x1 in ((b, sw / 2), (w - b, w - sw / 2)):
        out.append(f'<path d="M{x0:.2f},{sw / 2:.2f} H{x1:.2f} V{h - sw / 2:.2f} H{x0:.2f}" fill="none" '
                   f'stroke="#374151" stroke-width="{sw:.2f}"/>')
    return "".join(out)


def _patches(w, h, fill, stroke, sw, grid, shifted: bool):
    """An image cut into patches (thin lines) and attention windows (heavy lines); `shifted` moves the window
    partition by half a window, so windows straddle the regular ones."""
    r, c = grid
    pw, ph = w / c, h / r
    out = [f'<rect x="0" y="0" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>']
    out += [f'<line x1="{j * pw:.2f}" y1="0" x2="{j * pw:.2f}" y2="{h:.1f}" stroke="#ffffff" stroke-width="{sw * 0.7:.2f}"/>'
            for j in range(1, c)]
    out += [f'<line x1="0" y1="{i * ph:.2f}" x2="{w:.1f}" y2="{i * ph:.2f}" stroke="#ffffff" stroke-width="{sw * 0.7:.2f}"/>'
            for i in range(1, r)]
    wr, wc = max(1, r // 2), max(1, c // 2)  # 2 × 2 windows
    off_r, off_c = (wr // 2, wc // 2) if shifted else (0, 0)
    dark = _mix(stroke, "#000000", 0.3)
    for j in range(off_c, c + 1, wc):
        if 0 < j < c or not shifted:
            out.append(f'<line x1="{j * pw:.2f}" y1="0" x2="{j * pw:.2f}" y2="{h:.1f}" stroke="{dark}" stroke-width="{sw * 1.6:.2f}"/>')
    for i in range(off_r, r + 1, wr):
        if 0 < i < r or not shifted:
            out.append(f'<line x1="0" y1="{i * ph:.2f}" x2="{w:.1f}" y2="{i * ph:.2f}" stroke="{dark}" stroke-width="{sw * 1.6:.2f}"/>')
    out.append(f'<rect x="{sw:.2f}" y="{sw:.2f}" width="{w - 2 * sw:.2f}" height="{h - 2 * sw:.2f}" fill="none" '
               f'stroke="{dark}" stroke-width="{sw * 1.6:.2f}"/>')
    return "".join(out)


def _axis_label(x, y, sym, idx, font_px, family, axis):
    """z_1 / t_1 in a header cell: the symbol at the label size, its index as a subscript (70 %)."""
    return (f'<text data-axis="{axis}" x="{x:.2f}" y="{y:.2f}" font-size="{font_px:.2f}" font-family="{family}" '
            f'font-style="italic" text-anchor="middle" dominant-baseline="central" fill="#1f2937">{sym}'
            f'<tspan font-size="{font_px * 0.7:.2f}" font-style="normal" dy="{font_px * 0.28:.2f}">{idx}</tspan></text>')


def pair_matrix_min_size(grid, font_px: float) -> tuple[float, float]:
    """The smallest box that holds named rows / columns at ``font_px`` (header = 2 label widths, cell >= 1.7 em)."""
    r, c = grid
    hw, cell = 2.1 * font_px, 1.75 * font_px
    return hw + c * cell, hw + r * cell


def pair_matrix_header(w, h, grid, axes=None, font_px=None) -> float:
    """Width of the row-name column (= height of the column-name strip) of a pair-matrix drawn at w × h."""
    r, c = grid
    hw = min(w, h) / (max(r, c) + 1) * 0.8
    if axes and font_px:  # named rows / columns (z_1 … , t_1 …): the header holds the label at the label size
        hw = max(hw, 2.1 * font_px)
    return hw


def check_positives(positives, grid) -> list[str]:
    """Problems with explicit positive cells: 1-based [row, col] pairs inside the grid."""
    r, c = grid
    bad = [p for p in positives if len(p) != 2 or not (1 <= p[0] <= r and 1 <= p[1] <= c)]
    return [f"positives {bad} outside the {r} × {c} grid (cells are 1-based [row, col])"] if bad else []


def _pair_matrix(w, h, row_fill, row_stroke, col_fill, col_stroke, pos, sw, grid, variant, seed: str,
                 axes=None, font_px=None, family="Helvetica", positives=None):
    """CLIP's picture of a contrastive objective: rows (e.g. images) against columns (e.g. texts), the positive pairs
    filled. one-to-one = the diagonal; many-to-one = every row one positive, rows sharing a column (a class
    sentence); many-to-many = rows sharing sets of columns (concepts). Header strips carry the two sides' tones."""
    import zlib
    r, c = grid
    hw = pair_matrix_header(w, h, grid, axes, font_px)
    cw, ch = (w - hw) / c, (h - hw) / r
    k = zlib.crc32(seed.encode()) or 1
    on = set()
    if positives is not None:  # the blueprint names the cells: the same picture wherever the node sits
        probs = check_positives(positives, grid)
        if probs:
            raise ValueError(probs[0])
        on = {(int(a) - 1, int(b) - 1) for a, b in positives}
    elif variant == "many-to-one":
        cols = [i % c for i in range(r)]  # every column used once at least, then deterministically shuffled
        for i in range(r - 1, 0, -1):
            k = (k * 1103515245 + 12345) & 0x7FFFFFFF
            j = k % (i + 1)
            cols[i], cols[j] = cols[j], cols[i]
        on = {(i, cols[i]) for i in range(r)}
    elif variant == "many-to-many":
        for i in range(r):
            k = (k * 1103515245 + 12345) & 0x7FFFFFFF
            n = 1 + (k >> 8) % min(3, c)
            start = (k >> 4) % c
            on |= {(i, (start + t * (1 + (k >> 12) % 2)) % c) for t in range(n)}
        if all(sum(1 for (a, _) in on if a == i) < 2 for i in range(r)):
            on.add((0, (min(j for (a, j) in on if a == 0) + 1) % c))
    else:
        on = {(i, i) for i in range(min(r, c))}
    out = []
    for i in range(r):  # row headers
        out.append(f'<rect x="{sw / 2:.2f}" y="{hw + i * ch + sw / 2:.2f}" width="{hw - sw:.2f}" height="{ch - sw:.2f}" '
                   f'fill="{row_fill}" stroke="{row_stroke}" stroke-width="{sw * 0.6:.2f}"/>')
    for j in range(c):  # column headers
        out.append(f'<rect x="{hw + j * cw + sw / 2:.2f}" y="{sw / 2:.2f}" width="{cw - sw:.2f}" height="{hw - sw:.2f}" '
                   f'fill="{col_fill}" stroke="{col_stroke}" stroke-width="{sw * 0.6:.2f}"/>')
    if axes and font_px:
        for i in range(r):
            out.append(_axis_label(hw / 2, hw + (i + 0.5) * ch, axes[0], i + 1, font_px, family, "row"))
        for j in range(c):
            out.append(_axis_label(hw + (j + 0.5) * cw, hw / 2, axes[1], j + 1, font_px, family, "col"))
    grid_line = "#c7ccd4"
    for i in range(r):
        for j in range(c):
            p = (i, j) in on
            out.append(f'<rect data-r="{i}" data-c="{j}" data-pos="{1 if p else 0}" x="{hw + j * cw:.2f}" '
                       f'y="{hw + i * ch:.2f}" width="{cw:.2f}" height="{ch:.2f}" fill="{pos if p else "#ffffff"}" '
                       f'stroke="{grid_line}" stroke-width="{sw * 0.5:.2f}"/>')
    return "".join(out)


def glyph_svg(name: str, w: float, h: float, fill: str, stroke: str, accent: str, *, nodes: int = 5,
              pattern: str = "cartesian", tones: list[str] | None = None, ink: float = 1.0,
              variant: str | None = None, grid: tuple | None = None, seed: str = "",
              col: tuple[str, str] | None = None, axes=None, font_px: float | None = None,
              family: str = "Helvetica", positives=None) -> str:
    sw = 1.2 * ink
    if name == "pair-matrix":  # col = the column side's (fill, stroke); positives in the accent
        cf, cs = col or (_mix(fill, "#ffffff", 0.3), stroke)
        return _svg(w, h, _pair_matrix(w, h, fill, stroke, cf, cs, accent, sw, tuple(grid or GRIDDED["pair-matrix"]),
                                       variant or "one-to-one", seed, axes=axes, font_px=font_px, family=family,
                                       positives=positives))
    if name == "graph" and variant == "subgraph":
        body = _graph_subgraph(w, h, fill, stroke, accent, sw)
    elif name == "graph" and variant == "layers":
        body = _graph_layers(w, h, fill, stroke, accent, sw)
    elif name == "graph" and variant in ("neighbourhood", "khop", "aggregate"):
        body = _graph_neighbourhood(w, h, fill, stroke, accent, sw, variant)
    elif name == "graph":
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
    elif name == "onehot":
        body = _onehot(w, h, fill, stroke, sw, tuple(grid or GRIDDED["onehot"]), seed)
    elif name == "vector":
        body = _vector(w, h, fill, stroke, sw, max(3, min(8, nodes)))
    elif name == "patches":
        body = _patches(w, h, fill, stroke, sw, tuple(grid or GRIDDED["patches"]), variant == "shifted")
    elif name == "kspace":
        body = _kspace(w, h, pattern, 0.9 * ink)
    elif name == "ellipsis":  # "and so on" between unrolled stages: three dots, no box (a text '⋯' printed tiny)
        r = min(h / 2, w / 9)
        body = "".join(f'<circle cx="{w * f:.1f}" cy="{h / 2:.1f}" r="{r:.1f}" fill="{stroke}"/>' for f in (0.2, 0.5, 0.8))
    elif name == "natural-image":
        body = _natural_image(w, h, variant or "clean")
    elif name == "mr-image":
        body = _mr_image(w, h, variant or "clean")
    elif name == "sampling-mask":
        body = _sampling_mask(w, h, pattern, 0.9 * ink)
    elif name == "coil-maps":
        body = _coil_maps(w, h)
    else:
        raise ValueError(f"unknown glyph '{name}' (one of {', '.join(GLYPHS)})")
    return _svg(w, h, body)


def glyph_data_uri(svg: str) -> str:
    return "data:image/svg+xml," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
