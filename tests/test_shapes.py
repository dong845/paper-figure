import itertools
import xml.etree.ElementTree as ET

import pytest

from paperfig import shapes
from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.layout import solve
from paperfig.route import route_all
from paperfig.styles import load_recipe
from paperfig import measure
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def fig(children, edges=(), layout=None):
    return load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                 "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
                 "edges": [dict(e, provenance=PROV) for e in edges]})


def build(bp):
    p = solve(bp, R)
    r = route_all(bp, p, R)
    return p, r, emit(bp, p, r, R)


@pytest.mark.parametrize("st", [{}, {"flipH": "1"}, {"direction": "south"}, {"direction": "north"}])
def test_constraint_transforms_inverse(st):
    for fx, fy in itertools.product((0, 0.25, 0.5, 1), (0, 0.4, 1)):
        ex, ey = shapes.to_constraint(st, fx, fy)
        assert shapes.from_constraint(st, ex, ey) == pytest.approx((fx, fy))


def test_measured_transforms():
    # measured with draw.io 30.3.14 (9-point grids): direction=south maps (ex,ey)=(0,0) to the right-top corner
    assert shapes.from_constraint({"direction": "south"}, 0, 0) == (1, 0)
    assert shapes.from_constraint({"direction": "north"}, 0, 0) == (0, 1)
    assert shapes.from_constraint({"flipH": "1"}, 0, 0.5) == (1, 0.5)


def test_trapezoid_style_direction():
    bp = fig([leaf("e", "Image<br>Encoder", visual="trapezoid", taper="in"), leaf("d", "LLM", visual="trapezoid", taper="out")])
    _, _, xml = build(bp)
    c = parse_cells(xml)
    assert c["pf-e"].style["shape"] == "trapezoid" and c["pf-e"].style["direction"] == "south"
    assert c["pf-d"].style["direction"] == "north"


def test_trapezoid_text_fits_narrow_end():
    bp = fig([leaf("e", "Image<br>Encoder", visual="trapezoid", taper="in")])
    p = solve(bp, R)
    tw, th = measure.measure("Image<br>Encoder", R["typography"]["size"])
    b = p["e"].box
    assert b.w >= tw and b.h * (1 - 2 * shapes.TRAPEZOID_SIZE) >= th


def test_stack_sheets_inside_footprint():
    bp = fig([leaf("s", "F<sub>1</sub>", visual="stack", sheets=4)])
    p, _, xml = build(bp)
    cells = parse_cells(xml)
    sheets = [c for k, c in cells.items() if k.startswith("pfdeco-s-sheet")]
    assert len(sheets) == 4
    for sh in sheets:
        assert p["s"].box.contains(sh.box, eps=0.01)


def test_slab_rotated_label_fits():
    bp = fig([leaf("k", "3×3 Dconv", visual="slab")])
    p, _, xml = build(bp)
    c = parse_cells(xml)["pf-k"]
    assert c.style["horizontal"] == "0"
    tw, th = measure.measure("3×3 Dconv", R["typography"]["small_size"])
    assert p["k"].box.h >= tw and p["k"].box.w >= th and p["k"].box.h > p["k"].box.w


def test_op_kind_glyph_and_legend():
    bp = fig([leaf("a", "A"), leaf("m", "", visual="op", op="matmul", role="op"), leaf("c", "", visual="op", op="concat", role="op")],
             [{"src": "a", "dst": "m"}, {"src": "m", "dst": "c"}])
    _, _, xml = build(bp)
    cells = parse_cells(xml)
    assert cells["pf-m"].value == "⊗" and cells["pf-c"].value == "Ⓒ"
    legend = " ".join(c.value for k, c in cells.items() if k.startswith("pfdeco-legend"))
    assert "matrix multiplication" in legend and "concatenation" in legend


def test_op_kind_requires_op_visual():
    from paperfig.errors import BlueprintError
    with pytest.raises(BlueprintError, match="op"):
        fig([leaf("m", "", visual="box", op="add")])


@pytest.mark.parametrize("visual,extra", [("trapezoid", {"taper": "in"}), ("trapezoid", {"taper": "out"}), ("tensor", {})])
def test_rotated_shape_ports_roundtrip_through_lint(visual, extra):
    from paperfig.lint import _polyline
    ch = [leaf("up", "Up", cell=[0, 1]), leaf("l", "Left", cell=[1, 0]), dict(leaf("x", "X", visual=visual, cell=[1, 1]), **extra),
          leaf("r", "Right", cell=[1, 2]), leaf("dn", "Down", cell=[2, 1])]
    edges = [{"src": "l", "dst": "x"}, {"src": "x", "dst": "r"}, {"src": "up", "dst": "x"}, {"src": "x", "dst": "dn"}]
    bp = fig(ch, edges, {"type": "grid"})
    p, r, xml = build(bp)
    cells = parse_cells(xml)
    for e in bp.edges:
        poly = _polyline(cells[f"pf-{e.id}"], cells)
        assert poly[0] == pytest.approx(r[e.id].points[0], abs=0.05)
        assert poly[-1] == pytest.approx(r[e.id].points[-1], abs=0.05)


def test_badge_inside_tapered_trapezoid():
    bp = fig([leaf("e", "Image<br>Encoder", visual="trapezoid", taper="in", badges=["frozen"])])
    p, _, xml = build(bp)
    b = parse_cells(xml)["pfdeco-e-badge0"].box
    e = p["e"].box
    from paperfig.shapes import trapezoid_top
    assert b.cx > e.cx and b.y >= trapezoid_top(e, "in", b.right)  # top-right, inside the slanted outline


def test_op_glyph_larger_than_body_text():
    bp = fig([leaf("m", "", visual="op", op="matmul", role="op")])
    _, _, xml = build(bp)
    st = parse_cells(xml)["pf-m"].style
    assert float(st["fontSize"]) >= 1.3 * R["typography"]["size"]
