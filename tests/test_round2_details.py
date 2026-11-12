import json
import math

import pytest

from paperfig.blueprint import load
from paperfig.errors import BlueprintError, PaperFigError
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def fig(children, edges=(), layout=None, **f):
    fd = {"type": "overview", "venue": "cvpr", "width": "double"}
    fd.update(f)
    return {"schema_version": 1, "figure": fd, "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges]}


def route(d):
    from paperfig.pipeline import solve_and_route
    bp = load(d)
    p, r = solve_and_route(bp, R)
    return bp, p, r


def test_op_ports_on_circle():
    col = {"id": "col", "frame": "none", "layout": {"type": "column"}, "children": [leaf("a", "A"), leaf("b", "B")]}
    bp, p, r = route(fig([col, leaf("m", "", visual="op", op="add", role="op"), leaf("z", "Z")],
                         [{"src": "a", "dst": "m"}, {"src": "b", "dst": "m"}, {"src": "m", "dst": "z"}]))
    c = p["m"].box
    rad = c.w / 2
    for e in bp.edges:
        pt = r[e.id].points[-1] if e.dst == "m" else r[e.id].points[0]
        assert math.dist(pt, (c.cx, c.cy)) == pytest.approx(rad, abs=0.6), (e.id, pt)


def test_route_keeps_off_frame_borders():
    g1 = {"id": "g1", "title": "Stage 1", "frame": "dashed", "layout": {"type": "row"}, "children": [leaf("a", "A"), leaf("q", "Q-Former")]}
    g2 = {"id": "g2", "title": "Stage 2", "frame": "dashed", "layout": {"type": "row"}, "children": [leaf("p", "prompt text here"), leaf("l", "LLM")]}
    bp, p, r = route(fig([g1, g2], [{"src": "a", "dst": "q"}, {"src": "q", "dst": "l"}, {"src": "p", "dst": "l"}],
                         {"type": "column", "align": "end"}))
    e = next(x for x in bp.edges if x.src == "q")
    borders = []
    for gid in ("g1", "g2"):
        b = p[gid].box
        borders += [("v", b.x, b.y, b.bottom), ("v", b.right, b.y, b.bottom), ("h", b.y, b.x, b.right), ("h", b.bottom, b.x, b.right)]
    for s, t in zip(r[e.id].points, r[e.id].points[1:]):
        vert = abs(s[0] - t[0]) < 1e-6
        for kind, c, lo, hi in borders:
            if (kind == "v") == vert:
                coord = s[0] if vert else s[1]
                a0, a1 = sorted((s[1], t[1]) if vert else (s[0], t[0]))
                if min(a1, hi) - max(a0, lo) > 4:
                    assert abs(coord - c) >= 8 - 1e-6, (s, t, kind, c)


def test_lint_flags_hugging(tmp_path):
    import re
    from paperfig.drawio import emit
    from paperfig.lint import check
    bp, p, r = route(fig([leaf("a", "A"), leaf("k", "Blocker"), leaf("c", "C")], [{"src": "a", "dst": "c"}]))
    xml = emit(bp, p, r, R)
    kb = p["k"].box
    y = kb.y - 2  # run 2px above the blocker's top edge
    xml = re.sub(r'(<mxCell id="pf-e0".*?<Array as="points">)(.*?)(</Array>)',
                 lambda m: m.group(1) + re.sub(r'y="[\d.\-]+"', f'y="{y}"', m.group(2)) + m.group(3), xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    rep = check(f, bp, R, None, 6.875)
    hug = [x for x in rep.findings if x.code == "edge-hugs-border"]
    assert hug and hug[0].provisional


def test_frozen_and_trainable_rejected():
    with pytest.raises(BlueprintError, match="frozen.*trainable|trainable.*frozen"):
        load(fig([leaf("a", "A", badges=["frozen", "trainable"])]))


def test_compressed_drawio_clear_error():
    from paperfig.drawio import parse_cells
    xml = '<mxfile><diagram id="x" name="p">7ZbBbqMwEIafhqPXJjNVqHVF</diagram></mxfile>'
    with pytest.raises(PaperFigError, match="compressed"):
        parse_cells(xml)


def test_edge_jog_marked_provisional(tmp_path):
    import re
    from paperfig.drawio import emit
    from paperfig.lint import check
    bp, p, r = route(fig([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b"}]))
    xml = emit(bp, p, r, R)
    a = p["a"].box
    y = a.cy
    mid = a.right + 14
    pts = f'<Array as="points"><mxPoint x="{mid}" y="{y}" /><mxPoint x="{mid}" y="{y + 3}" /></Array>'
    xml = re.sub(r'(<mxCell id="pf-e0".*?entryY=)[\d.]+', lambda m: m.group(1) + "%.4f" % (0.5 + 3 / a.h), xml, count=1, flags=re.S)
    xml = re.sub(r'(<mxCell id="pf-e0".*?<mxGeometry relative="1" as="geometry")\s*/>', r'\1>' + pts + '</mxGeometry>', xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    jog = [x for x in check(f, bp, R, None, 6.875).findings if x.code == "edge-jog"]
    assert jog and jog[0].provisional


def test_blueprint_style_used_as_default(tmp_path):
    from paperfig.__main__ import main
    from paperfig import pipeline as P
    seen = {}

    def fake(bp, style, *a, **k):
        seen["style"] = style
        raise PaperFigError("stop")
    d = tmp_path / "fig"
    d.mkdir()
    (d / "blueprint.json").write_text(json.dumps(fig([leaf("a", "A")], style="depth-cv")))
    import paperfig.pipeline
    orig = paperfig.pipeline.build
    paperfig.pipeline.build = fake
    try:
        main(["build", str(d / "blueprint.json")])
    finally:
        paperfig.pipeline.build = orig
    assert seen["style"] == "depth-cv"


def test_unknown_format_rejected(tmp_path):
    from paperfig.__main__ import main
    assert main(["build", "x.json", "--formats", "png,svgz"]) == 2


def test_fit_returns_layout_for_reuse():
    from paperfig.pipeline import fit_typography
    from paperfig.styles import compose
    bp = load(fig([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b"}]))
    recipe, info, placed, routes = fit_typography(bp, compose("soft-pastel"), 6.875)
    assert "a" in placed and set(routes) == {e.id for e in bp.edges}


def test_legend_wraps_to_figure_width():
    from paperfig.legend import build as build_legend
    from paperfig.layout import solve
    ops = ["add", "mul", "matmul", "concat", "reshape", "gelu"]
    ch = [leaf("a", "A")] + [leaf(f"o{k}", "", visual="op", op=o, role="op") for k, o in enumerate(ops)]
    edges = [{"src": "a", "dst": "o0", "kind": "skip"}] + [{"src": f"o{k}", "dst": f"o{k+1}"} for k in range(len(ops) - 1)]
    bp = load(fig(ch, edges, badges=None) if False else fig(ch, edges))
    p = solve(bp, R)
    lg = build_legend(bp, R, p["root"].box)
    assert lg.box.w <= p["root"].box.w + 1e-6
    assert len({round(it.text.y) for it in lg.items}) >= 2  # wrapped onto several rows


def test_edge_label_gap_leaves_room_for_arrow():
    from paperfig.layout import solve
    from paperfig import measure as M
    bp = load(fig([leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1])], [{"src": "a", "dst": "b", "label": "Q"}],
                  {"type": "grid", "gap": "tight"}))
    p = solve(bp, R)
    lw, _ = M.measure("Q", R["typography"]["small_size"])
    assert p["b"].box.x - p["a"].box.right >= lw + 2 * R["spacing"]["edge_label_pad"] + 2 * 6 - 1e-6


def test_l_elbow_avoids_busy_entry_side():
    ch = [leaf("g", "", visual="op", op="gelu", role="op", cell=[0, 1]), leaf("d", "Dconv", cell=[1, 0]),
          leaf("m", "", visual="op", op="mul", role="op", cell=[1, 2])]
    bp, p, r = route(fig(ch, [{"src": "d", "dst": "m"}, {"src": "g", "dst": "m"}], {"type": "grid"}))
    e = next(x for x in bp.edges if x.src == "g")
    assert r[e.id].dst_side == "top", r[e.id]
