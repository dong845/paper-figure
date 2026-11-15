"""Regression tests for the round-2 whole-branch review (Important 1-6)."""
import copy
import json

import pytest

from paperfig.blueprint import load
from paperfig.facts import check_facts, load_facts
from conftest import leaf, PROV

BENCH = "examples"


def fig(children, edges, layout=None, **kw):
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
         "edges": [dict(e, provenance=PROV) for e in edges]}
    d.update(kw)
    return d


def F(a, b, **kw):
    d = {"id": f"{a}->{b}", "from": a, "to": b, "quote": "q", "ref": "r"}
    d.update(kw)
    return d


def errors(fs):
    return [f for f in fs if f.severity == "error"]


# ---- 1. one fact must not be satisfied by a sibling branch ---------------------
def _restormer_without(edge_pairs):
    d = json.load(open(f"{BENCH}/restormer.blueprint.json"))
    d["edges"] = [e for e in d["edges"] if (e["src"], e["dst"]) not in edge_pairs]
    bp = load(d, base_dir=BENCH)
    facts = load_facts(f"{BENCH}/restormer.facts.json")
    return check_facts(bp, facts, bp.annotation_members)


def test_bench_facts_pass_intact():
    assert errors(_restormer_without(set())) == []


@pytest.mark.parametrize("dropped", [{("m_r2", "m_av")}, {("m_p1", "m_d1"), ("m_d1", "m_r1"), ("m_r1", "m_qk")},
                                     {("g_d1", "g_mul")}, {("g_gelu", "g_mul")}])
def test_bench_facts_catch_a_missing_branch(dropped):
    assert errors(_restormer_without(dropped)), dropped


def test_via_must_be_on_the_path():
    bp = load(fig([leaf("a", "A"), leaf("b", "B"), leaf("c", "C"), leaf("d", "D")],
                  [{"src": "a", "dst": "b"}, {"src": "b", "dst": "d"}, {"src": "a", "dst": "c"}]))
    assert errors(check_facts(bp, [F("a", "d", via=["b"])])) == []
    assert errors(check_facts(bp, [F("a", "d", via=["c"])]))


def test_direct_requires_an_edge():
    bp = load(fig([leaf("a", "A"), leaf("b", "B"), leaf("c", "C")], [{"src": "a", "dst": "b"}, {"src": "b", "dst": "c"}]))
    assert errors(check_facts(bp, [F("a", "c")])) == []
    assert errors(check_facts(bp, [F("a", "c", direct=True)]))


def test_covering_path_reported():
    bp = load(fig([leaf("a", "A"), leaf("b", "B"), leaf("c", "C")], [{"src": "a", "dst": "b"}, {"src": "b", "dst": "c"}]))
    fs = check_facts(bp, [F("a", "c")])
    info = [f for f in fs if f.code == "fact-covered"]
    assert info and "a → b → c" in info[0].message


# ---- 2. only data-flow edges ---------------------------------------------------
def test_gradient_and_loss_edges_not_followed():
    bp = load(fig([leaf("txt", "T"), leaf("loss", "L", role="loss"), leaf("enc", "E")],
                  [{"src": "txt", "dst": "loss", "kind": "loss"}, {"src": "loss", "dst": "enc", "kind": "grad"}]))
    assert errors(check_facts(bp, [F("txt", "enc")]))
    assert errors(check_facts(bp, [F("txt", "enc", kinds=["loss", "grad"])])) == []


# ---- 3. a container is not a hub ----------------------------------------------
def test_container_not_a_hub():
    g = {"id": "C", "title": "C", "layout": {"type": "row"}, "children": [leaf("c1", "c1"), leaf("c2", "c2")]}
    bp = load(fig([leaf("x", "x"), leaf("y", "y"), g, leaf("z", "z")],
                  [{"src": "x", "dst": "C"}, {"src": "y", "dst": "c2"}, {"src": "c2", "dst": "z"}]))
    assert errors(check_facts(bp, [F("x", "z")]))      # c2 is fed by y, not by x
    assert errors(check_facts(bp, [F("x", "c1")])) == []  # entering C still reaches its children


# ---- 4. brackets clear a framed root's title -----------------------------------
def test_top_bracket_below_framed_root_title():
    from paperfig.annotations import place
    from paperfig.pipeline import solve_and_route
    from paperfig.styles import load_recipe
    R = load_recipe("soft-pastel")
    d = fig([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b"}],
            annotations=[{"id": "st", "kind": "bracket", "covers": ["a", "b"], "label": "Stage", "side": "top"}])
    d["root"].update(title="A Framed Root Title", frame="box")
    bp = load(d)
    p, r = solve_and_route(bp, R)
    g = place(bp, p, R)["st"]
    assert g.band.y >= p["root"].title_box.bottom - 1e-6
    assert g.band.bottom <= min(p["a"].box.y, p["b"].box.y) + 1e-6


# ---- 5. detail_of a group -----------------------------------------------------
def test_detail_of_group_draws_halo():
    from paperfig.drawio import emit, parse_cells
    from paperfig.pipeline import solve_and_route
    from paperfig.styles import load_recipe
    R = load_recipe("soft-pastel")
    src = {"id": "blk", "title": "Block", "cell": [0, 0], "layout": {"type": "row"}, "children": [leaf("m", "M"), leaf("n", "N")]}
    pan = {"id": "pan", "title": "(a)", "detail_of": "blk", "cell": [1, 0], "layout": {"type": "row"}, "provenance": PROV,
           "children": [leaf("x", "inner")]}
    bp = load(fig([src, pan], [{"src": "m", "dst": "n"}], {"type": "grid"}))
    p, r = solve_and_route(bp, R)
    cells = parse_cells(emit(bp, p, r, R))
    halo = cells["pfdeco-callout-pan-halo"]
    assert halo.box.contains(p["blk"].box)


# ---- 6. bracket span claims an uncovered node ----------------------------------
def test_bracket_spans_uncovered_warns(tmp_path):
    from paperfig.drawio import emit
    from paperfig.lint import check
    from paperfig.pipeline import solve_and_route
    from paperfig.styles import load_recipe
    R = load_recipe("soft-pastel")
    ch = [leaf("q", "Queries", cell=[0, 1]), leaf("a", "A", cell=[1, 0]), leaf("b", "B", cell=[1, 1]), leaf("c", "C", cell=[1, 2])]
    d = fig(ch, [{"src": "a", "dst": "b"}, {"src": "b", "dst": "c"}, {"src": "q", "dst": "b"}], {"type": "grid"},
            annotations=[{"id": "st", "kind": "bracket", "covers": ["a", "b", "c"], "label": "Stage 2", "side": "top"}])
    bp = load(d)
    p, r = solve_and_route(bp, R)
    f = tmp_path / "f.drawio"
    f.write_text(emit(bp, p, r, R))
    rep = check(f, bp, R, None, 6.875)
    assert any(x.code == "bracket-spans-uncovered" and "q" in x.ids for x in rep.findings)
