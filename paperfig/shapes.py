"""Shape vocabulary shared by layout, emitter and lint.

Constraint transforms were measured with draw.io 30.3.14 by exporting 9-point exit grids:
  flipH=1          actual = (1 - ex, ey)
  direction=south  actual = (1 - ey, ex)
  direction=north  actual = (ey, 1 - ex)
The emitter converts the router's actual port fractions with `to_constraint`; the lint converts back
with `from_constraint`, so both read the same geometry draw.io draws.
"""
from __future__ import annotations

TRAPEZOID_SIZE = 0.2  # drawio trapezoid 'size': each end shrinks by this fraction of the height
STACK_OFFSET = 5.0  # px between stacked sheets (scaled by ink)

# op kind -> (glyph, legend name); operators are drawn as their glyph, not inside a big circle
OPS = {
    "add": ("⊕", "element-wise addition"),
    "mul": ("⊙", "element-wise multiplication"),
    "matmul": ("⊗", "matrix multiplication"),
    "concat": ("Ⓒ", "concatenation"),
    "reshape": ("Ⓡ", "reshape"),
    "gelu": ("φ", "GELU activation"),  # ⊘ reads as division; φ gets a thin drawn ring of the same size
}
# Ring diameter of circled glyphs as a fraction of the font size, and how far the ring sits below the
# text centre — measured 2026-11-12 from draw.io 30.3.14 renders (Helvetica + system fallback, 40px glyphs).
OP_RING_EM = {"⊕": 0.575, "⊗": 0.588, "⊙": 0.575, "Ⓡ": 0.975, "Ⓒ": 0.975}
OP_RING_DY = {"⊕": 0.07, "⊗": 0.07, "⊙": 0.07}
OP_RING_SCALE = 1.15  # every operator ring has diameter = 1.15 x the body font size


def op_ring(body_size: float) -> float:
    return body_size * OP_RING_SCALE


def op_glyph_style(glyph: str, ring: float, color: str, ink: float = 1.0) -> dict:
    """drawio style keys that make the glyph's ring exactly `ring` px wide and centred in a ring x ring box."""
    st = {"shape": "ellipse", "perimeter": "ellipsePerimeter", "aspect": "fixed", "fillColor": "#ffffff",
          "fontColor": color, "fontStyle": "0", "spacing": "0", "pfop": "1"}
    if glyph in OP_RING_EM:
        fs = ring / OP_RING_EM[glyph]
        st.update({"strokeColor": "none", "fontSize": "%.2f" % fs})
        dy = OP_RING_DY.get(glyph, 0.0) * fs
        if dy:
            st["spacingBottom"] = "%.2f" % (2 * dy)  # lift the glyph so its ring is centred on the node
    else:
        st.update({"strokeColor": color, "strokeWidth": "%.2f" % min(1.1 * ink, 1.5 * ink), "fontSize": "%.2f" % (ring * 0.8)})
    return st


def transform(style: dict) -> str:
    if style.get("flipH") == "1":
        return "flipH"
    d = style.get("direction")
    return d if d in ("south", "north", "west") else "none"


def to_constraint(style: dict, fx: float, fy: float) -> tuple[float, float]:
    t = transform(style)
    if t == "flipH":
        return 1 - fx, fy
    if t == "south":  # actual = (1 - ey, ex)
        return fy, 1 - fx
    if t == "north":  # actual = (ey, 1 - ex)
        return 1 - fy, fx
    if t == "west":  # turned half way round: actual = (1 - ex, 1 - ey) (a taper-"down" trapezoid's ports landed
        return 1 - fx, 1 - fy  # on its far side, the line drawn straight through it — TWM run)
    return fx, fy


def from_constraint(style: dict, ex: float, ey: float) -> tuple[float, float]:
    t = transform(style)
    if t == "flipH":
        return 1 - ex, ey
    if t == "south":
        return 1 - ey, ex
    if t == "north":
        return ey, 1 - ex
    if t == "west":
        return 1 - ex, 1 - ey
    return ex, ey


def op_glyph(node) -> str:
    kind = getattr(node, "op", None)
    return OPS[kind][0] if kind else node.label


def slab_rotated(node) -> bool:
    """Slab labels are rotated 90°, except very short ones (e.g. 'FC') which read better upright."""
    from .blueprint import plain_text
    return len(plain_text(node.label)) > 3


def trapezoid_top(box, taper: str, x: float) -> float:
    """y of the slanted top outline at x (taper 'in' narrows to the right, 'out' widens to the right); 'up' and
    'down' slant the left and right sides instead, so their top is flat."""
    if taper in ("up", "down"):
        return box.y
    cut = TRAPEZOID_SIZE * box.h
    t = min(1.0, max(0.0, (x - box.x) / box.w)) if box.w else 0.5
    return box.y + (cut * t if taper == "in" else cut * (1 - t))


def trapezoid_side_x(box, taper: str, side: str, y: float) -> float:
    """x of the slanted left/right outline at y for an 'up' (narrow top) or 'down' (narrow bottom) taper."""
    cut = TRAPEZOID_SIZE * box.w
    t = min(1.0, max(0.0, (y - box.y) / box.h)) if box.h else 0.5
    inset = cut * ((1 - t) if taper == "up" else t)
    return box.x + inset if side == "left" else box.right - inset


def trapezoid_bottom(box, taper: str, x: float) -> float:
    return box.bottom - (trapezoid_top(box, taper, x) - box.y)
