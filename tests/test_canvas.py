"""Round 7 A: canvas layout — children placed by spans on an N-column grid of equal columns (default 12), so a span
is a share of the width (a hero block over 8 columns, satellites over 2), while routing, fit and lint stay automatic."""
import copy
import json

import pytest

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.drawio import parse_cells
from paperfig.errors import BlueprintError


def _bp(children, edges=(), cols=None, gap="normal"):
    lay = {"type": "canvas", "gap": gap}
    if cols:
        lay["cols"] = cols
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": lay, "children": children},
            "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}


def _build(tmp_path, d):
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    return res, parse_cells(res.drawio.read_text())


def test_spans_are_shares_of_the_width(tmp_path):
    kids = [leaf("hero", "Diffusion backbone", cell=[0, 0], span=[2, 8]),
            leaf("s1", "Text", cell=[0, 9], span=[1, 3]), leaf("s2", "Image", cell=[1, 9], span=[1, 3])]
    res, c = _build(tmp_path, _bp(kids, [{"src": "s1", "dst": "hero"}, {"src": "s2", "dst": "hero"}]))
    hero, s1, s2 = c["pf-hero"].box, c["pf-s1"].box, c["pf-s2"].box
    assert hero.w >= 2 * s1.w  # 8 of 12 columns against 3 of 12
    assert s1.x > hero.right and abs(s1.cx - s2.cx) < 0.5  # same column span: one axis
    assert hero.h > s1.h  # spans two rows
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]


def test_columns_are_equal_and_text_still_fits(tmp_path):
    """Equal columns: the pitch is the same everywhere, set by the widest text per column it must hold."""
    kids = [leaf("a", "A", cell=[0, 0]), leaf("b", "A much longer module name", cell=[0, 1]),
            leaf("d", "D", cell=[0, 3])]
    res, c = _build(tmp_path, _bp(kids, cols=4))
    a, b, d = c["pf-a"].box, c["pf-b"].box, c["pf-d"].box
    assert abs((d.cx - b.cx) - 2 * (b.cx - a.cx)) < 1.0  # column 2 is empty, yet as wide as the others
    assert not [f for f in res.report.findings if f.code == "text-overflow"]


def test_canvas_rejects_overlap_and_out_of_range():
    with pytest.raises(BlueprintError, match="overlap"):
        load(_bp([leaf("a", "A", cell=[0, 0], span=[1, 6]), leaf("b", "B", cell=[0, 4], span=[1, 4])]))
    with pytest.raises(BlueprintError, match="cols"):
        load(_bp([leaf("a", "A", cell=[0, 10], span=[1, 4])]))


def test_labelled_edge_between_spans_gets_room(tmp_path):
    kids = [leaf("a", "Encoder", cell=[0, 0], span=[1, 4]), leaf("b", "Decoder", cell=[0, 4], span=[1, 4])]
    res, c = _build(tmp_path, _bp(kids, [{"src": "a", "dst": "b", "label": "latent z (64×64×4)"}], cols=8))
    assert not [f for f in res.report.findings if "label" in f.code and f.severity != "info"], \
        [(f.code, f.message) for f in res.report.findings if "label" in f.code]


def test_the_child_that_sets_the_pitch_is_named(tmp_path):
    kids = [leaf("a", "Encoder", cell=[0, 0], span=[1, 6]), leaf("b", "A rather long single-column name", cell=[0, 7])]
    res, _ = _build(tmp_path, _bp(kids, [{"src": "a", "dst": "b"}]))
    f = next(f for f in res.report.findings if f.code == "canvas-pitch")
    assert f.ids == ["root", "b"] and "more columns" in f.message


def test_gutters_are_narrow_unless_an_arrow_crosses(tmp_path):
    """Twelve columns mean eleven gutters: only a boundary an edge crosses needs the full gap."""
    kids = [leaf("a", "Encoder", cell=[0, 0], span=[1, 4]), leaf("b", "Decoder", cell=[0, 4], span=[1, 4]),
            leaf("c", "Head", cell=[0, 8], span=[1, 4])]
    res, c = _build(tmp_path, _bp(kids, [{"src": "a", "dst": "b"}]))
    a, b, h = c["pf-a"].box, c["pf-b"].box, c["pf-c"].box
    linked, unlinked = b.x - a.right, h.x - b.right
    assert linked >= 20 and unlinked < 0.6 * linked, (linked, unlinked)
