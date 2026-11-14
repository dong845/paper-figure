"""User 2026-11-14: in the DreamerV3 rerun spacing was so tight that arrowheads met (double-headed loss arrows in a
gap sized for one head); in STORM lines crossed and ran close to blocks. Layout and routing leave room for the
arrows themselves."""
import copy
import json
import math

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.lint import _polyline


def _row(tmp_path, kind, gap="tight", mix=None):
    kids = [leaf("a", "Critic v"), leaf("b", "Critic loss", role="loss")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": gap}, "children": kids},
         "edges": [{"src": "a", "dst": "b", "kind": kind, "provenance": copy.deepcopy(PROV)}]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", mix, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    e = next(v for v in c.values() if v.edge)
    p = _polyline(e, c)
    return sum(math.dist(x, y) for x, y in zip(p, p[1:])), float(e.style.get("endSize", 6)), r


def test_a_double_headed_arrow_gets_room_for_both_heads_and_a_shaft(tmp_path):
    L, head, _ = _row(tmp_path / "loss", "loss", gap="tight", mix={"spacing": "compact"})
    assert L >= 2 * head + 1.5 * head - 0.5, (L, head)


def test_a_single_headed_arrow_keeps_a_visible_shaft(tmp_path):
    L, head, _ = _row(tmp_path / "data", "data", gap="tight", mix={"spacing": "compact"})
    assert L >= head + 1.5 * head - 0.5, (L, head)


def _fan_in(tmp_path, n=3):
    """Inputs stacked on the left of one small box: all arrive on its left side, more than it has room for."""
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": [
             {"id": "ins", "layout": {"type": "column", "gap": "normal"}, "frame": "none",
              "children": [leaf(f"i{k}", f"Input {k}") for k in range(n)]},
             leaf("s", "State")]},
         "edges": [{"src": f"i{k}", "dst": "s", "dst_side": "left", "kind": "data", "provenance": copy.deepcopy(PROV)} for k in range(n)]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    polys = {k: _polyline(v, c) for k, v in c.items() if v.edge}
    return polys, c, r


import pytest


@pytest.mark.parametrize("n", [3, 4])
def test_inputs_on_one_side_neither_touch_heads_nor_cross(tmp_path, n):
    polys, c, r = _fan_in(tmp_path, n)
    head = float(next(iter(c[k] for k in polys)).style.get("endSize", 6))
    ps = list(polys.values())
    for i, pa in enumerate(ps):
        for pb in ps[i + 1:]:
            tips = math.dist(pa[-1], pb[-1])
            assert tips < 0.5 or tips >= 1.2 * head, (pa, pb)  # one shared head, or clearly apart — never touching
            if tips < 0.5:  # merged: the shared segment holds the head and a visible shaft
                assert pa[-2] == pb[-2] and math.dist(pa[-2], pa[-1]) >= 2.5 * head, (pa, pb)
    assert not [i for i in r.report.findings if i.code in ("edge-overlap", "edge-crossings")], r.report.findings


def test_a_line_does_not_skim_past_another_arrows_tip():
    """Passing within one arrowhead of where another line ends costs as a crossing (STORM: s_t->actor slid 3 px
    under the critic, past the tip of the loss arrow ending there)."""
    from paperfig import route as R
    R._TIP = 7.6
    routed = R._Routed()
    routed.add([(100.0, 200.0), (100.0, 150.0)], "loss")  # ends (tip) at y=150, coming from below
    assert routed.penalty((50.0, 147.0), (150.0, 147.0)) >= R.CROSS  # 3 px beyond the tip
    assert routed.penalty((50.0, 140.0), (150.0, 140.0)) < R.CROSS  # clear of it


@pytest.mark.parametrize("taper", ["down", "up"])
def test_lines_attach_to_the_slanted_sides_of_vertical_tapers(tmp_path, taper):
    """TWM run: with taper "down" draw.io turned the port constraints half way round, so Enc->Dec ran straight through
    both trapezoids (measured on the PNG); with "up" the arrows stopped short of the slanted sides."""
    from paperfig.shapes import trapezoid_side_x
    kids = [leaf("enc", "Enc", visual="trapezoid", taper=taper), leaf("dec", "Dec", visual="trapezoid", taper=taper)]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "single"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [{"src": "enc", "dst": "dec", "kind": "data", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    e = next(v for v in c.values() if v.edge)
    p = _polyline(e, c)
    a, b = c["pf-enc"].box, c["pf-dec"].box
    assert abs(p[0][0] - trapezoid_side_x(a, taper, "right", p[0][1])) < 1.0, (p, a)
    assert abs(p[-1][0] - trapezoid_side_x(b, taper, "left", p[-1][1])) < 1.0, (p, b)
    assert p[0][0] < p[-1][0]  # left to right, not through the shapes


def test_a_labelled_dashed_edge_shows_its_pattern_beside_the_label(tmp_path):
    """TWM run: labelled infer_only (dash-dot) edges drew solid — the line beside the label was shorter than one
    dash pattern. Where the pattern is the only cue (same colour as data lines), each side keeps a recognisable one."""
    from paperfig.geometry import Box
    from paperfig.lint import measure
    from paperfig.styles import load_recipe
    kids = [leaf("env", "Env"), leaf("enc", "Encoder")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "tight"}, "children": kids},
         "edges": [{"src": "env", "dst": "enc", "kind": "infer_only", "label": "$o_t$", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    e = next(v for v in c.values() if v.edge)
    p = _polyline(e, c)
    L = sum(math.dist(x, y) for x, y in zip(p, p[1:]))
    marks = [float(x) for x in e.style["dashPattern"].split()]
    period = sum(marks[:-1]) * float(e.style["strokeWidth"])  # dash, gap, dot: the pattern up to its last mark
    label_w = measure(e.value, float(e.style["fontSize"]))[0]
    assert (L - label_w) / 2 >= period - 0.5, (L, label_w, period)
