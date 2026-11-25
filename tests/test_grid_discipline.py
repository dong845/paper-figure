"""Grid discipline (user, 2026-11-24: "A, B, C, D are all different sizes ... a layout is about neat alignment"):
the engine, not the agent's taste, makes parallel panels one size with shared edges and lets a panel fill the room its
parent gives it."""
import copy

from conftest import PROV, leaf
from paperfig import blueprint as B
from paperfig.layout import solve
from paperfig.lint import near_aligned
from paperfig.styles import load_recipe


def _panel(id, n, layout="column", words="step"):
    return {"id": id, "title": f"Panel {id}", "layout": {"type": layout}, "provenance": copy.deepcopy(PROV),
            "children": [leaf(f"{id}{i}", f"{words} {i}" * (1 + i % 2)) for i in range(n)]}


def _bp(root):
    return B.load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                   "root": root, "edges": []})


def _boxes(p, ids):
    return [p[i].box for i in ids]


def test_panels_side_by_side_share_height_top_and_width():
    bp = _bp({"id": "root", "layout": {"type": "row"},
              "children": [_panel("a", 2), _panel("b", 4), _panel("c", 3)]})
    p = solve(bp, load_recipe("soft-pastel"))
    a, b, c = _boxes(p, "abc")
    assert {round(x.y, 1) for x in (a, b, c)} == {round(a.y, 1)}
    assert {round(x.h, 1) for x in (a, b, c)} == {round(b.h, 1)}  # the fullest panel sets the height
    assert {round(x.w, 1) for x in (a, b, c)} == {round(max(a.w, b.w, c.w), 1)}
    # the shorter panels loosen their stack (at most three extra gaps per step), never into an unbounded spread
    gap = load_recipe("soft-pastel")["spacing"]["gap"]["normal"]
    assert p["a1"].box.y - p["a0"].box.bottom <= 4 * gap + 0.5


def test_very_different_panels_keep_their_widths_but_still_align():
    bp = _bp({"id": "root", "layout": {"type": "row"},
              "children": [_panel("a", 2), _panel("w", 3, layout="row", words="a much longer step label")]})
    p = solve(bp, load_recipe("soft-pastel"))
    a, w = _boxes(p, "aw")
    assert w.w > 1.6 * a.w and round(a.h, 1) == round(w.h, 1) and round(a.y, 1) == round(w.y, 1)


def test_stacked_panels_share_left_and_right_edges():
    bp = _bp({"id": "root", "layout": {"type": "column"},
              "children": [_panel("a", 2, layout="row"), _panel("b", 5, layout="row", words="wider")]})
    p = solve(bp, load_recipe("soft-pastel"))
    a, b = _boxes(p, "ab")
    assert round(a.x, 1) == round(b.x, 1) and round(a.right, 1) == round(b.right, 1)


def test_near_miss_edges_are_reported_exact_ones_are_not():
    from paperfig.geometry import Box

    class C:
        def __init__(self, box):
            self.box = box

    g = _bp({"id": "root", "layout": {"type": "row"}, "children": [_panel("a", 1), _panel("b", 1)]}).root
    assert near_aligned(g, {"pf-a": C(Box(0, 0, 100, 80)), "pf-b": C(Box(120, 0, 100, 80))}) == []
    found = near_aligned(g, {"pf-a": C(Box(0, 0, 100, 80)), "pf-b": C(Box(120, 3, 100, 80))})
    assert found and found[0][0] == ["a", "b"] and "top" in found[0][1]


def test_the_users_figure_is_the_shape_to_match(monkeypatch, tmp_path):
    import pathlib

    from paperfig import grammar
    from paperfig import pipeline as P
    ex = pathlib.Path(__file__).resolve().parents[1] / "examples" / "restormer.blueprint.json"
    monkeypatch.setattr(grammar, "target_measure", lambda bp: {"ink_ratio": 0.9, "palette": [], "aspect": 0.5})
    r = P.build(ex, "soft-pastel", out_dir=tmp_path, formats=("png",))
    assert any(f.code == "aspect-off-target" for f in r.report.findings)


def test_full_width_overviews_may_print_down_to_5_5_pt():
    from types import SimpleNamespace as NS

    from paperfig.lint import hard_floor
    assert hard_floor(NS(type="overview"), 6.875) == 5.5
    assert hard_floor(NS(type="overview"), 3.25) == 6.0  # a column figure keeps 6 pt
    assert hard_floor(NS(type="module-detail"), 6.875) == 6.0
