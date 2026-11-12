"""Operators drawn as their glyph (no big circle); ring sizes measured from draw.io renders."""
import pytest

from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.shapes import OPS, OP_RING_EM
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def build(ops):
    ch = [leaf("a", "A")] + [leaf(f"o{k}", "", visual="op", op=o, role="op") for k, o in enumerate(ops)]
    edges = [{"src": "a", "dst": "o0"}] + [{"src": f"o{k}", "dst": f"o{k+1}"} for k in range(len(ops) - 1)]
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "children": ch}, "edges": [dict(e, provenance=PROV) for e in edges]})
    from paperfig.pipeline import solve_and_route
    p, r = solve_and_route(bp, R)
    return bp, p, r, parse_cells(emit(bp, p, r, R))


def test_circled_glyphs_have_no_drawn_circle_and_ring_fills_box():
    bp, p, r, cells = build(["add", "matmul", "mul", "reshape", "concat"])
    for k, op in enumerate(["add", "matmul", "mul", "reshape", "concat"]):
        st = cells[f"pf-o{k}"].style
        assert st["strokeColor"] == "none"
        ring = float(st["fontSize"]) * OP_RING_EM[OPS[op][0]]
        assert ring == pytest.approx(p[f"o{k}"].box.w, rel=0.03)


def test_rings_equal_size_across_glyphs():
    bp, p, r, cells = build(["add", "reshape", "gelu"])
    ws = [p[f"o{k}"].box.w for k in range(3)]
    assert max(ws) - min(ws) < 0.5


def test_gelu_has_thin_ring():
    bp, p, r, cells = build(["gelu"])
    st = cells["pf-o0"].style
    assert st["strokeColor"] != "none" and float(st["strokeWidth"]) <= 1.5 * R.data.get("ink_scale", 1.0)


def test_op_ring_smaller_than_old_circle():
    bp, p, r, cells = build(["add"])
    assert p["o0"].box.w <= 1.25 * R["typography"]["size"]


def test_lint_does_not_flag_op_glyph_overflow(tmp_path):
    from paperfig.lint import check
    from paperfig.drawio import emit
    from paperfig.pipeline import solve_and_route
    bp, p, r, cells = build(["add", "reshape", "gelu"])
    f = tmp_path / "f.drawio"
    f.write_text(emit(bp, p, r, R))
    assert not any(x.code == "text-overflow" for x in check(f, bp, R, None, 6.875).findings)


def test_no_jog_on_restormer_bench_after_repair():
    """Regression: a residual edge re-sided by the repair pass left its former side-mate shifted by 1.8px."""
    import os
    from paperfig.pipeline import fit_typography
    from paperfig.styles import compose
    if not os.path.isfile(os.path.expanduser("~/.cache/paper-figure/bench/restormer/assets/degraded-crop.png")):
        pytest.skip("bench assets not cached")
    bp = load("bench/phase0/restormer/blueprint.json")
    rc, info, p, r = fit_typography(bp, compose("soft-pastel"), 6.875)
    for e in bp.edges:
        pts = r[e.id].points
        inner = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])][1:-1]
        assert not inner or min(inner) >= 8, (e.id, e.src, e.dst, pts)
