import pytest

from paperfig.blueprint import load
from paperfig.drawio import parse_cells
from paperfig.errors import BlueprintError
from paperfig.geometry import Box, segment_hits_box
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def fig(children, edges=(), annotations=(), layout=None):
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "icml", "width": "double"},
            "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges], "annotations": list(annotations)}


def chain():
    return fig([leaf("img", "Image"), leaf("enc", "Encoder"), leaf("qf", "Q-Former"), leaf("fc", "FC"), leaf("llm", "LLM")],
               [{"src": "img", "dst": "enc"}, {"src": "enc", "dst": "qf"}, {"src": "qf", "dst": "fc"}, {"src": "fc", "dst": "llm"},
                {"src": "img", "dst": "llm", "kind": "skip"}],
               [{"id": "st1", "kind": "bracket", "covers": ["enc", "qf"], "label": "Stage 1", "side": "top"},
                {"id": "st2", "kind": "bracket", "covers": ["enc", "qf", "fc", "llm"], "label": "Stage 2", "side": "top"}])


def compile_(d):
    from paperfig.pipeline import solve_and_route
    from paperfig.drawio import emit
    bp = load(d)
    p, r = solve_and_route(bp, R)
    return bp, p, r, parse_cells(emit(bp, p, r, R))


def test_bracket_unknown_id_rejected():
    d = chain()
    d["annotations"][0]["covers"].append("ghost")
    with pytest.raises(BlueprintError, match="ghost"):
        load(d)


def test_bracket_spans_covered_nodes():
    bp, p, r, cells = compile_(chain())
    line = cells["pfdeco-ann-st1-line"]
    xs = [x for x, _ in line.points] + [line.sp[0], line.tp[0]] if hasattr(line, "sp") else [x for x, _ in line.points]
    assert min(xs) <= p["enc"].footprint.x + 1e-6 and max(xs) >= p["qf"].footprint.right - 1e-6


def test_brackets_overlap_in_separate_lanes():
    bp, p, r, cells = compile_(chain())
    y1 = min(y for _, y in cells["pfdeco-ann-st1-line"].points)
    y2 = min(y for _, y in cells["pfdeco-ann-st2-line"].points)
    assert abs(y1 - y2) >= 14
    l1, l2 = cells["pfdeco-ann-st1-label"].box, cells["pfdeco-ann-st2-label"].box
    assert not l1.intersects(l2)
    for nid in ("img", "enc", "qf", "fc", "llm"):
        assert not l1.intersects(p[nid].footprint) and not l2.intersects(p[nid].footprint)


def test_routes_avoid_brackets():
    bp, p, r, cells = compile_(chain())
    skip = next(e for e in bp.edges if e.kind == "skip")
    for aid in ("st1", "st2"):
        lab = cells[f"pfdeco-ann-{aid}-label"].box
        for a, b in zip(r[skip.id].points, r[skip.id].points[1:]):
            assert not segment_hits_box(a, b, lab)


def test_fact_scope_can_be_a_bracket():
    from paperfig.facts import check_facts
    bp = load(chain())
    F = lambda a, b, s: {"id": "f", "from": a, "to": b, "scope": s, "quote": "q", "ref": "r"}
    assert [x for x in check_facts(bp, [F("enc", "llm", "st2")], bp.annotation_members) if x.severity != "info"] == []
    assert [x.code for x in check_facts(bp, [F("enc", "llm", "st1")], bp.annotation_members) if x.severity == "error"] == ["fact-out-of-scope"]


def test_lint_checks_bracket_coverage(tmp_path):
    import re
    from paperfig.lint import check
    from paperfig.drawio import emit
    from paperfig.pipeline import solve_and_route
    bp = load(chain())
    p, r = solve_and_route(bp, R)
    xml = emit(bp, p, r, R)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    assert not any(x.code == "bracket-coverage" for x in check(f, bp, R, None, 6.75).findings)
    # shrink bracket st2 so it no longer reaches llm
    xml2 = re.sub(r'(<mxCell id="pfdeco-ann-st2-line".*?<mxPoint x=")([\d.]+)(" y="[\d.]+" as="targetPoint")',
                  lambda m: m.group(1) + "10" + m.group(3), xml, count=1, flags=re.S)
    f.write_text(xml2)
    assert any(x.code == "bracket-coverage" for x in check(f, bp, R, None, 6.75).findings)


def test_lint_flags_edge_through_bracket_label(tmp_path):
    import re
    from paperfig.lint import check
    from paperfig.drawio import emit
    from paperfig.pipeline import solve_and_route
    bp = load(chain())
    p, r = solve_and_route(bp, R)
    xml = emit(bp, p, r, R)
    cells = parse_cells(xml)
    lab = cells["pfdeco-ann-st2-label"].box
    skip = next(e for e in bp.edges if e.kind == "skip")
    # drag the skip edge's waypoints through the middle of the bracket label
    y = lab.cy
    xml = re.sub(rf'(<mxCell id="pf-{skip.id}".*?<Array as="points">)(.*?)(</Array>)',
                 lambda m: m.group(1) + re.sub(r'y="[\d.\-]+"', f'y="{y}"', m.group(2)) + m.group(3), xml, count=1, flags=re.S)
    f = tmp_path / "f.drawio"
    f.write_text(xml)
    assert any(x.code == "edge-through-annotation" for x in check(f, bp, R, None, 6.75).findings)
