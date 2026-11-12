"""Engine fixes from the round-2 critics (faithfulness judged against the paper text)."""
import math
import xml.etree.ElementTree as ET

import pytest

from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.styles import load_recipe, node_style
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def fig(children, edges=(), layout=None, **f):
    fd = {"type": "overview", "venue": "cvpr", "width": "double"}
    fd.update(f)
    return {"schema_version": 1, "figure": fd, "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges]}


def compile_(d, recipe=R):
    from paperfig.pipeline import solve_and_route
    bp = load(d)
    p, r = solve_and_route(bp, recipe)
    return bp, p, r, emit(bp, p, r, recipe)


def test_trapezoid_top_port_on_slanted_outline():
    from paperfig.shapes import TRAPEZOID_SIZE
    ch = [leaf("pr", "prompt text", visual="text", role="annotation", cell=[0, 0]),
          leaf("llm", "LLM", visual="trapezoid", taper="out", cell=[1, 0])]
    bp, p, r, xml = compile_(fig(ch, [{"src": "pr", "dst": "llm"}], {"type": "grid"}))
    x, y = r["e0"].points[-1]
    b = p["llm"].box
    # taper 'out' widens to the right: the top edge falls from (x0, y0+cut) to (x1, y0)
    cut = TRAPEZOID_SIZE * b.h
    expect = b.y + cut * (1 - (x - b.x) / b.w)
    assert y == pytest.approx(expect, abs=0.6)


def test_short_slab_label_horizontal():
    bp, p, r, xml = compile_(fig([leaf("fc", "FC", visual="slab")]))
    st = parse_cells(xml)["pf-fc"].style
    assert st.get("horizontal") != "0"


def test_zoom_lines_drawn_above_containers():
    tb = {"id": "tb", "title": "Block", "layout": {"type": "row"}, "children": [leaf("m", "MDTA"), leaf("g", "GDFN")], "cell": [0, 0]}
    pan = {"id": "pan", "title": "(a)", "detail_of": "m", "cell": [1, 0], "layout": {"type": "row"}, "provenance": PROV,
           "children": [leaf("x", "inner")]}
    bp, p, r, xml = compile_(fig([tb, pan], [{"src": "m", "dst": "g"}], {"type": "grid"}))
    order = [c.get("id") for c in ET.fromstring(xml).iter("mxCell")]
    assert order.index("pfdeco-callout-pan-zoom0") > order.index("pf-tb")
    cells = parse_cells(xml)
    z = cells["pfdeco-callout-pan-zoom0"]
    assert p["m"].box.inflate(8).contains_point(*z.sp)  # leg starts at the source module, not at the container


def test_op_glyphs_unambiguous():
    from paperfig.shapes import OPS
    assert OPS["gelu"][0] == "φ" and OPS["reshape"][0] == "R" and OPS["concat"][0] == "C"


def test_edge_label_background_matches_panel_fill():
    pan = {"id": "pan", "title": "(a)", "tone": "yellow", "layout": {"type": "row"}, "provenance": PROV,
           "children": [leaf("a", "A"), leaf("b", "B")]}
    bp, p, r, xml = compile_(fig([pan], [{"src": "a", "dst": "b", "label": "Q"}]))
    cells = parse_cells(xml)
    e = next(c for k, c in cells.items() if c.edge and c.source == "pf-a")
    assert e.style["labelBackgroundColor"] == cells["pf-pan"].style["fillColor"]


def test_depth_style_flat_inside_detail_panels():
    rc = load_recipe("depth-cv")
    d = fig([leaf("m", "MDTA"), {"id": "pan", "title": "(a)", "detail_of": "m", "layout": {"type": "row"}, "provenance": PROV,
                                 "children": [leaf("x", "inner")]}])
    bp = load(d)
    assert node_style(rc, bp.index["x"], bp.index["pan"])["shadow"] == "0"
    assert "gradientColor" not in node_style(rc, bp.index["x"], bp.index["pan"])
    assert node_style(rc, bp.index["m"], bp.root)["shadow"] == "1"


def test_legend_rows_balanced_and_notes():
    from paperfig.legend import build as build_legend
    from paperfig.layout import solve
    ops = ["add", "mul", "matmul", "concat", "reshape", "gelu"]
    ch = [leaf("a", "A")] + [leaf(f"o{k}", "", visual="op", op=o, role="op") for k, o in enumerate(ops)]
    edges = [{"src": "a", "dst": "o0", "kind": "skip"}] + [{"src": f"o{k}", "dst": f"o{k+1}"} for k in range(len(ops) - 1)]
    d = fig(ch, edges, legend_notes=["Norm = LayerNorm", "Dconv = depth-wise conv"])
    bp = load(d)
    p = solve(bp, R)
    lg = build_legend(bp, R, p["root"].box)
    rows = {}
    for it in lg.items:
        rows.setdefault(round(it.text.y), []).append(it)
    counts = sorted(len(v) for v in rows.values())
    assert counts[-1] - counts[0] <= 1  # balanced: no orphan row
    assert any(it.kind == "note" and "LayerNorm" in it.label for it in lg.items)


def test_badges_top_right_inside_trapezoid_outline():
    from paperfig.shapes import TRAPEZOID_SIZE
    for taper in ("in", "out"):
        bp, p, r, xml = compile_(fig([leaf("e", "Encoder", visual="trapezoid", taper=taper, badges=["frozen"])]))
        b = parse_cells(xml)["pfdeco-e-badge0"].box
        e = p["e"].box
        assert b.cx > e.cx  # top-right, consistently
        top_at = e.y + (TRAPEZOID_SIZE * e.h * ((b.right - e.x) / e.w) if taper == "in" else TRAPEZOID_SIZE * e.h * (1 - (b.x - e.x) / e.w))
        assert b.y >= top_at  # inside the slanted outline


def _callout_case(title="Transformer Block", align=None):
    tb = {"id": "tb", "title": title, "layout": {"type": "row"}, "children": [leaf("m", "MDTA module"), leaf("g", "GDFN module")], "cell": [1, 0]}
    if align:
        tb["title_align"] = align
    pan = {"id": "pan", "title": "(b) panel", "detail_of": "g", "cell": [0, 0], "layout": {"type": "row"}, "provenance": PROV,
           "children": [leaf("x", "wide inner content one"), leaf("y", "wide inner content two")]}
    return fig([pan, tb], [{"src": "m", "dst": "g"}], {"type": "grid"})


def test_lint_flags_zoom_line_through_title(tmp_path):
    import re
    from paperfig.lint import check
    bp, p, r, xml = compile_(_callout_case())
    cells = parse_cells(xml)
    # force a leg straight through the middle of the title band
    tb = p["tb"].title_box
    xml = re.sub(r'(<mxCell id="pfdeco-callout-pan-zoom0".*?<mxPoint x=")[\d.\-]+(" y=")[\d.\-]+(" as="sourcePoint")',
                 lambda m: m.group(1) + f"{tb.cx}" + m.group(2) + f"{tb.bottom + 2}" + m.group(3), xml, count=1, flags=re.S)
    xml = re.sub(r'(<mxCell id="pfdeco-callout-pan-zoom0".*?<mxPoint x=")[\d.\-]+(" y=")[\d.\-]+(" as="targetPoint")',
                 lambda m: m.group(1) + f"{tb.cx}" + m.group(2) + f"{tb.y - 20}" + m.group(3), xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    assert any(x.code == "callout-crosses-title" for x in check(f, bp, R, None, 6.875).findings)


def test_zoom_legs_avoid_title_text():
    from paperfig.lint import check
    from paperfig.geometry import segment_crosses_interior
    from paperfig.measure import measure
    bp, p, r, xml = compile_(_callout_case(align="left"))
    cells = parse_cells(xml)
    tw, th = measure("Transformer Block", R["typography"]["title_size"], True)
    tbx = p["tb"].box
    title_text = Box(tbx.x, tbx.y, R["spacing"]["group_pad"] + tw + 4, p["tb"].title_box.h)
    for k in (0, 1):
        z = cells[f"pfdeco-callout-pan-zoom{k}"]
        assert not segment_crosses_interior(z.sp, z.tp, title_text, eps=0.5)


from paperfig.geometry import Box  # noqa: E402


@pytest.mark.parametrize("visual,extra", [("trapezoid", {"taper": "in"}), ("trapezoid", {"taper": "out"}), ("box", {})])
def test_badge_clear_of_label_text(visual, extra):
    from paperfig.measure import measure
    n = dict(leaf("e", "Image<br>Encoder", visual=visual, badges=["frozen"]), **extra)
    bp, p, r, xml = compile_(fig([n]))
    b = parse_cells(xml)["pfdeco-e-badge0"].box
    tw, th = measure("Image<br>Encoder", R["typography"]["size"])
    e = p["e"].box
    text = Box(e.cx - tw / 2, e.cy - th / 2, tw, th)
    assert not b.intersects(text)


def test_lint_flags_badge_over_text(tmp_path):
    import re
    from paperfig.lint import check
    bp, p, r, xml = compile_(fig([leaf("e", "Image Encoder", badges=["frozen"])]))
    e = p["e"].box
    xml = re.sub(r'(<mxCell id="pfdeco-e-badge0".*?<mxGeometry x=")[\d.\-]+(" y=")[\d.\-]+',
                 lambda m: m.group(1) + f"{e.w / 2 - 7}" + m.group(2) + f"{e.h / 2 - 7}", xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    assert any(x.code == "badge-overlaps-text" for x in check(f, bp, R, None, 6.875).findings)
