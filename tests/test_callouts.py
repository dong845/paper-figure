import pytest

from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.errors import BlueprintError, LayoutError
from paperfig.layout import solve
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def fig(children, edges=(), layout=None):
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
            "root": {"id": "root", "layout": layout or {"type": "grid"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges]}


def panel(cell, **kw):
    d = {"id": "pan", "title": "(a) Detail", "cell": cell, "place": "free", "layout": {"type": "row"},
         "provenance": PROV, "children": [leaf("p1", "Inner one"), leaf("p2", "Inner two"), leaf("p3", "Inner three")]}
    d.update(kw)
    return d


def test_free_child_does_not_resize_tracks():
    base = fig([leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), leaf("c", "C", cell=[1, 0])])
    with_panel = fig([leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), leaf("c", "C", cell=[1, 0]), panel([1, 1])])
    p0 = solve(load(base), R)
    p1 = solve(load(with_panel), R)
    for k in ("a", "b", "c"):
        assert p1[k].box == p0[k].box
    assert p1["pan"].box.x == pytest.approx(p1["b"].footprint.x)  # anchored at its cell origin
    assert p1["root"].box.contains(p1["pan"].box, eps=1e-6)


def test_free_child_overlap_raises():
    d = fig([leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), leaf("c", "C", cell=[1, 0]), leaf("d", "D", cell=[1, 2]), panel([1, 1])])
    with pytest.raises(LayoutError, match="pan.*d|d.*pan"):
        solve(load(d), R)


def test_detail_of_must_name_an_outside_node():
    d = fig([leaf("a", "A", cell=[0, 0]), panel([1, 0], detail_of="p1")])
    with pytest.raises(BlueprintError, match="detail_of"):
        load(d)


def _compile(d):
    from paperfig.pipeline import solve_and_route
    bp = load(d)
    p, r = solve_and_route(bp, R)
    return bp, p, emit(bp, p, r, R)


def test_detail_panel_tint_matches_source_highlight():
    bp, p, xml = _compile(fig([leaf("a", "MDTA", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), panel([1, 1], detail_of="a")],
                              [{"src": "a", "dst": "b"}]))
    cells = parse_cells(xml)
    halo = cells["pfdeco-callout-pan-halo"]
    assert halo.style["fillColor"] == cells["pf-pan"].style["fillColor"]
    assert halo.box.contains(p["a"].box)


def test_zoom_lines_drawn_behind():
    bp, p, xml = _compile(fig([leaf("a", "MDTA", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), panel([1, 1], detail_of="a")],
                              [{"src": "a", "dst": "b"}]))
    import xml.etree.ElementTree as ET
    order = [c.get("id") for c in ET.fromstring(xml).iter("mxCell")]
    for z in ("pfdeco-callout-pan-zoom0", "pfdeco-callout-pan-zoom1"):
        # drawn above the containers (a container fill must not hide the legs), before any data edge
        assert order.index(z) > order.index("pf-pan")
        assert all(order.index(z) < order.index(k) for k in order if k.startswith("pf-e"))
    halo_i = order.index("pfdeco-callout-pan-halo")
    assert halo_i < order.index("pf-a")


def _crossing_case():
    return fig([leaf("a", "MDTA", cell=[0, 1]), leaf("mid", "In the way", cell=[1, 0]), leaf("b", "B", cell=[0, 2]),
                panel([2, 0], detail_of="a")], [{"src": "a", "dst": "b"}])


def test_engine_picks_zoom_legs_that_avoid_nodes():
    from paperfig.geometry import segment_crosses_interior
    bp, p, xml = _compile(_crossing_case())
    cells = parse_cells(xml)
    for k in (0, 1):
        z = cells[f"pfdeco-callout-pan-zoom{k}"]
        assert not segment_crosses_interior(z.sp, z.tp, p["mid"].footprint, eps=1.0)


def test_lint_warns_when_zoom_line_crosses_node(tmp_path):
    import re
    from paperfig.lint import check
    bp, p, xml = _compile(_crossing_case())
    m = p["mid"].box
    # drag leg 0 through the middle of 'mid'
    xml = re.sub(r'(<mxCell id="pfdeco-callout-pan-zoom0".*?<mxPoint x=")[\d.\-]+(" y=")[\d.\-]+(" as="sourcePoint")',
                 lambda mm: mm.group(1) + f"{m.cx}" + mm.group(2) + f"{m.y - 10}" + mm.group(3), xml, count=1, flags=re.S)
    xml = re.sub(r'(<mxCell id="pfdeco-callout-pan-zoom0".*?<mxPoint x=")[\d.\-]+(" y=")[\d.\-]+(" as="targetPoint")',
                 lambda mm: mm.group(1) + f"{m.cx}" + mm.group(2) + f"{m.bottom + 10}" + mm.group(3), xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    assert any(x.code == "callout-crosses-node" for x in check(f, bp, R, None, 6.875).findings)


def test_free_children_stack_instead_of_colliding():
    p2 = dict(panel([1, 1]), id="pan2", children=[leaf("q1", "Second panel content")], title="(b)")
    p1 = panel([0, 2])
    d = fig([leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), leaf("c", "C", cell=[1, 0]), p1, p2])
    p = solve(load(d), R)
    assert p["pan2"].box.y >= p["pan"].footprint.bottom  # stacked below the earlier free panel
    assert p["root"].box.contains(p["pan2"].box, eps=1e-6)
