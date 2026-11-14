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


def _drawn_twice(polys):
    """Total length drawn by more than one edge (renders as one thick line — user 2026-11-14, round 2)."""
    from paperfig.route import _overlap_len
    return sum(_overlap_len(a, b) for i, a in enumerate(polys) for b in polys[i + 1:])


def test_bundle_draws_one_trunk_and_branches_without_doubling(tmp_path):
    res, polys = _fan(tmp_path, RIGHT)
    assert len(polys) == 3
    port = min(polys, key=lambda p: p[0][0])[0]  # the shared exit port on the encoder
    assert sum(1 for p in polys if abs(p[0][0] - port[0]) < 0.5 and abs(p[0][1] - port[1]) < 0.5) == 1  # one trunk
    xs = {round(x, 1) for p in polys for (x, _), (x2, _) in zip(p, p[1:]) if abs(x - x2) < 0.5}
    assert len(xs) == 1  # every vertical piece lies on the one branch line
    assert _drawn_twice(polys) < 1.0, polys
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
    edges = [v for v in c.values() if v.edge and v.target == "pf-m"]
    polys = [_polyline(v, c) for v in edges]
    m = c["pf-m"].box
    into = [v for v, p in zip(edges, polys) if m.inflate(0.5).contains_point(*p[-1], eps=0.0) or
            abs(p[-1][1] - m.y) < 0.5]
    assert len(into) == 1 and into[0].style.get("endArrow", "none") != "none"  # one trunk, one head into Merge
    assert all(v.style.get("endArrow") == "none" for v in edges if v not in into)  # branches end on the trunk
    assert _drawn_twice(polys) < 1.0, polys
    assert not [f for f in res.report.findings if f.severity in ("error", "warn") and f.code.startswith("edge")]


def test_a_branch_may_not_cross_another_target_of_its_bundle(tmp_path):
    """Blind DreamerV3 run: env → x1, x2, x3 in one row gave a trunk through x1 and x2 and no bundle-skipped."""
    res, polys = _fan(tmp_path, {"x": [0, 0], "a": [0, 1], "b": [0, 2], "c": [0, 3]})
    assert not [f for f in res.report.findings if f.code == "edge-through-node"], \
        [f.message for f in res.report.findings if f.code == "edge-through-node"]
    assert any(f.code == "bundle-skipped" for f in res.report.findings)


def test_a_bundle_respects_pinned_sides_and_titles(tmp_path):
    """STORM run: a bundle with dst_side 'left' was drawn entering from the top through the agent band's title."""
    kids = [leaf("x", "Encoder", cell=[1, 0]),
            {"id": "g", "title": "Agent", "layout": {"type": "column"}, "cell": [1, 1], "provenance": copy.deepcopy(PROV),
             "children": [leaf("a", "Head A"), leaf("b", "Head B")]}]
    edges = [{"src": "x", "dst": t, "bundle": "hb", "dst_side": "top", "provenance": copy.deepcopy(PROV)} for t in "ab"]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids}, "edges": edges}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert any(f.code == "bundle-skipped" for f in res.report.findings)
    assert not [f for f in res.report.findings if f.code == "edge-through-title"]


def test_fan_in_with_consistent_pins_still_bundles(tmp_path):
    kids = [leaf(t, f"Head {t.upper()}", cell=[i, 0]) for i, t in enumerate("abc")] + [leaf("m", "Merge", cell=[1, 1])]
    edges = [{"src": t, "dst": "m", "bundle": "merge", "src_side": "right", "dst_side": "left",
              "provenance": copy.deepcopy(PROV)} for t in "abc"]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids}, "edges": edges}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert not any(f.code == "bundle-skipped" for f in res.report.findings)


def test_a_bundle_branch_does_not_sit_on_another_edge_from_the_same_side(tmp_path):
    """DreamerV3 run (user, round 2): critic v1's bundle branch up to the lambda-return bus and its loss line up to the
    critic loss both left the middle of v1's top — one drawn over the other. A branch takes a free port."""
    from paperfig.lint import _polyline
    from paperfig.route import _overlap_len
    kids = [leaf("lc", "Critic loss", role="loss", cell=[0, 0]), leaf("lam", "Returns", cell=[0, 1]),
            leaf("a", "Reward", cell=[2, 0]), leaf("v", "Critic", cell=[2, 1]), leaf("b", "Value", cell=[2, 2])]
    edges = [{"src": t, "dst": "lam", "bundle": "ret", "provenance": copy.deepcopy(PROV)} for t in ("a", "v", "b")]
    edges.append({"src": "v", "dst": "lc", "kind": "loss", "src_side": "top", "provenance": copy.deepcopy(PROV)})
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids}, "edges": edges}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    polys = {k: _polyline(v, c) for k, v in c.items() if v.edge and k.startswith("pf-")}
    loss = next(p for k, v in c.items() if v.edge and v.target == "pf-lc" for p in [polys[k]])
    branch = next(p for k, v in c.items() if v.edge and v.source == "pf-v" and v.target == "pf-lam" for p in [polys[k]])
    assert _overlap_len(loss, branch) < 1.0, (loss, branch)
    assert not [f for f in res.report.findings if f.code in ("edge-overlap", "edge-parallel")], res.report.findings
