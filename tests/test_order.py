"""Sibling order chosen to cross fewer lines (user 2026-11-14: needless bends and crossings; blocks may move)."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells


def _two_columns(tmp_path, order=None):
    """heads (a, b) feed losses listed the other way round (lb, la): drawn as given, the lines cross."""
    heads = {"id": "heads", "frame": "none", "layout": dict({"type": "column", "gap": "normal"}, **({"order": order} if order else {})),
             "children": [leaf("a", "Head A"), leaf("b", "Head B")]}
    losses = {"id": "losses", "frame": "none", "layout": dict({"type": "column", "gap": "normal"}, **({"order": order} if order else {})),
              "children": [leaf("lb", "Loss B", role="loss"), leaf("la", "Loss A", role="loss")]}
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "loose"}, "children": [heads, losses]},
         "edges": [{"src": "a", "dst": "la", "provenance": copy.deepcopy(PROV)},
                   {"src": "b", "dst": "lb", "provenance": copy.deepcopy(PROV)}]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    return parse_cells(r.drawio.read_text()), r


def test_crossing_siblings_are_reordered_and_the_change_is_reported(tmp_path):
    c, r = _two_columns(tmp_path)
    same_side = (c["pf-a"].box.y < c["pf-b"].box.y) == (c["pf-la"].box.y < c["pf-lb"].box.y)
    assert same_side  # either column turned round: each head now level with its own loss
    assert r.report.stats.get("edge_crossings", 0) == 0
    assert any(f.code == "auto-order" for f in r.report.findings)


def test_a_fixed_order_is_kept(tmp_path):
    c, r = _two_columns(tmp_path, order="fixed")
    assert c["pf-a"].box.y < c["pf-b"].box.y and c["pf-lb"].box.y < c["pf-la"].box.y
    assert not any(f.code == "auto-order" for f in r.report.findings)
