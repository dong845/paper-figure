"""Round 5 engine limits: edge tone, glued chips, outline highlight, vertical taper, outgoing stub."""
import copy

from conftest import PROV, leaf
from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.pipeline import solve_and_route
from paperfig.styles import load_recipe

R = load_recipe("soft-pastel")


def _compile(kids, edges=(), layout=None, **fig):
    d = {"schema_version": 1, "figure": dict({"type": "overview", "venue": "cvpr", "width": "double"}, **fig),
         "root": {"id": "root", "layout": layout or {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}
    bp = load(d)
    placed, routes = solve_and_route(bp, R)
    return bp, placed, parse_cells(emit(bp, placed, routes, R))


def test_edge_tone_colours_one_path():
    _, _, c = _compile([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b", "tone": "purple"}])
    e = next(x for x in c.values() if x.edge and x.source == "pf-a")
    assert e.style["strokeColor"].lower() == R["palette"]["tones"]["purple"]["stroke"].lower()


def test_chips_glue_with_gap_none():
    _, p, _ = _compile([leaf("d", "d", visual="chip"), leaf("x", "x", visual="chip")], layout={"type": "row", "gap": "none"})
    assert abs(p["x"].box.x - p["d"].box.right) < 0.5  # glued
    assert p["d"].box.w < R["spacing"]["min_node_w"]  # a chip is as small as its text


def test_outline_highlight():
    _, _, c = _compile([leaf("a", "Ours", role="proposed", full_name="Ours"), leaf("b", "Base")], highlight="outline")
    st = c["pf-a"].style
    assert st["fillColor"].lower() in ("#ffffff", "none")
    assert float(st["strokeWidth"]) >= 2 * float(c["pf-b"].style["strokeWidth"]) - 1e-6


def test_vertical_taper():
    _, _, c = _compile([leaf("e", "Encoder", visual="trapezoid", taper="down")], layout={"type": "column"})
    assert c["pf-e"].style.get("direction") in ("east", "west")


def test_stub_arrow_out_of_a_node():
    _, p, c = _compile([leaf("a", "Panel end", stub={"side": "right", "label": "out"})])
    s = next(x for x in c.values() if x.id.startswith("pfdeco-stub-a"))
    xs = [pt[0] for pt in (s.sp, s.tp)]
    assert min(xs) >= p["a"].box.right - 0.5 and max(xs) > p["a"].box.right + 10


def test_stub_into_a_neighbour_is_an_error(tmp_path):
    from paperfig.grammar import check_grammar
    bp, p, _ = _compile([leaf("a", "Panel end", stub={"side": "right"}), leaf("b", "Next")], layout={"type": "row", "gap": "tight"})
    placed, routes = solve_and_route(bp, R)
    f = tmp_path / "x.drawio"
    f.write_text(emit(bp, placed, routes, R))
    assert any(x.code == "stub-overlap" and x.severity == "error" for x in check_grammar(bp, f, R, None))


def test_edge_economy_flags_detours_and_duplicates(tmp_path):
    from paperfig.grammar import check_grammar, detour_ratio
    assert detour_ratio([(0, 0), (100, 0)]) == 1.0
    assert detour_ratio([(0, 0), (0, -80), (100, -80), (100, 0)]) > 2.5  # up, over, down: a wrap-around
    bp, _, _ = _compile([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b"}, {"src": "a", "dst": "b", "kind": "skip"}])
    placed, routes = solve_and_route(bp, R)
    f = tmp_path / "x.drawio"
    f.write_text(emit(bp, placed, routes, R))
    assert any(x.code == "edges-parallel" for x in check_grammar(bp, f, R, None))
