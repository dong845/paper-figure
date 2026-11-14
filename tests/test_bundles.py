"""Round 8: opt-in edge bundles — a fan-out drawn as one trunk that branches (the bus convention), only where the
geometry allows; otherwise the normal routes stay and a note says why."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells


def _fan(tmp_path, cells, bundle="heads"):
    kids = [leaf("x", "Encoder", cell=cells["x"])] + [leaf(t, f"Head {t.upper()}", cell=cells[t]) for t in "abc"]
    edges = [dict({"src": "x", "dst": t, "provenance": copy.deepcopy(PROV)}, **({"bundle": bundle} if bundle else {}))
             for t in "abc"]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids}, "edges": edges}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    from paperfig.lint import _polyline
    polys = [_polyline(v, c) for k, v in c.items() if v.edge and v.source == "pf-x"]
    return res, polys


RIGHT = {"x": [1, 0], "a": [0, 1], "b": [1, 1], "c": [2, 1]}


def test_bundle_shares_one_port_and_trunk(tmp_path):
    res, polys = _fan(tmp_path, RIGHT)
    assert len(polys) == 3
    starts = {(round(p[0][0], 1), round(p[0][1], 1)) for p in polys}
    assert len(starts) == 1  # one exit port
    branch_x = {round(p[1][0], 1) for p in polys if len(p) > 2}
    assert len(branch_x) == 1  # one trunk, then the branches
    bad = [f for f in res.report.findings if f.severity in ("error", "warn") and f.code.startswith("edge")]
    assert not bad, [(f.code, f.message) for f in bad]


def test_unbundled_fan_is_unchanged(tmp_path):
    _, polys = _fan(tmp_path, RIGHT, bundle=None)
    assert len({(round(p[0][0], 1), round(p[0][1], 1)) for p in polys}) > 1


def test_bundle_that_cannot_fit_keeps_normal_routes_and_says_why(tmp_path):
    cells = {"x": [1, 1], "a": [0, 0], "b": [1, 2], "c": [2, 1]}  # targets on three sides
    res, polys = _fan(tmp_path, cells)
    assert any(f.code == "bundle-skipped" and "heads" in f.message for f in res.report.findings)


def test_fan_in_bundle_merges_before_the_target(tmp_path):
    kids = [leaf(t, f"Head {t.upper()}", cell=[i, 0]) for i, t in enumerate("abc")] + [leaf("m", "Merge", cell=[1, 1])]
    edges = [{"src": t, "dst": "m", "bundle": "merge", "provenance": copy.deepcopy(PROV)} for t in "abc"]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids}, "edges": edges}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    from paperfig.lint import _polyline
    polys = [_polyline(v, c) for v in c.values() if v.edge and v.target == "pf-m"]
    assert len({(round(p[-1][0], 1), round(p[-1][1], 1)) for p in polys}) == 1  # one entry port
    assert not [f for f in res.report.findings if f.severity in ("error", "warn") and f.code.startswith("edge")]
