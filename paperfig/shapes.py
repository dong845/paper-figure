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

# op kind -> (glyph, legend name); glyphs verified to render in draw.io
OPS = {
    "add": ("⊕", "element-wise addition"),
    "mul": ("⊙", "element-wise multiplication"),
    "matmul": ("⊗", "matrix multiplication"),
    "concat": ("Ⓒ", "concatenation"),
    "reshape": ("Ⓡ", "reshape"),
    "gelu": ("⊘", "GELU activation"),
}


def transform(style: dict) -> str:
    if style.get("flipH") == "1":
        return "flipH"
    d = style.get("direction")
    return d if d in ("south", "north") else "none"


def to_constraint(style: dict, fx: float, fy: float) -> tuple[float, float]:
    t = transform(style)
    if t == "flipH":
        return 1 - fx, fy
    if t == "south":  # actual = (1 - ey, ex)
        return fy, 1 - fx
    if t == "north":  # actual = (ey, 1 - ex)
        return 1 - fy, fx
    return fx, fy


def from_constraint(style: dict, ex: float, ey: float) -> tuple[float, float]:
    t = transform(style)
    if t == "flipH":
        return 1 - ex, ey
    if t == "south":
        return 1 - ey, ex
    if t == "north":
        return ey, 1 - ex
    return ex, ey


def op_glyph(node) -> str:
    kind = getattr(node, "op", None)
    return OPS[kind][0] if kind else node.label
