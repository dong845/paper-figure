import json

import pytest

from paperfig.blueprint import load
from paperfig.facts import check_facts, load_facts
from conftest import leaf, PROV


def fig(children, edges, layout=None):
    return load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                 "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
                 "edges": [dict(e, provenance=PROV) for e in edges]})


def F(fr, to, **kw):
    d = {"id": f"{fr}->{to}", "from": fr, "to": to, "quote": "q", "ref": "Sec. 3"}
    d.update(kw)
    return d


def codes(findings, sev=None):
    return {f.code for f in findings if sev is None or f.severity == sev}


BP = None


@pytest.fixture
def chain():
    return fig([leaf("img", "Image"), leaf("enc", "Encoder"),
                {"id": "s1", "title": "Stage 1", "children": [leaf("qf", "Q-Former"), leaf("ln", "Norm")]},
                leaf("llm", "LLM"), leaf("txt", "Text")],
               [{"src": "img", "dst": "enc"}, {"src": "enc", "dst": "qf"}, {"src": "qf", "dst": "llm"}])


def test_direct_edge_covers_fact(chain):
    assert [x for x in check_facts(chain, [F("img", "enc")]) if x.severity != "info"] == []


def test_multi_hop_path_covers_fact(chain):
    assert [x for x in check_facts(chain, [F("img", "llm")]) if x.severity != "info"] == []


def test_edge_into_group_reaches_its_children():
    bp = fig([leaf("a", "A"), {"id": "g", "title": "G", "children": [leaf("b", "B")]}], [{"src": "a", "dst": "g"}])
    assert [x for x in check_facts(bp, [F("a", "b")]) if x.severity != "info"] == []


def test_missing_path_is_error(chain):
    f = check_facts(chain, [F("txt", "qf", quote="the text transformer ... queries")])
    assert codes(f, "error") == {"fact-missing"}
    assert "txt" in f[0].message and "qf" in f[0].message and "the text transformer" in f[0].message


def test_fact_unknown_id_is_error(chain):
    assert codes(check_facts(chain, [F("fc", "llm")]), "error") == {"fact-unknown-id"}


def test_fact_path_must_stay_in_scope(chain):
    # img -> enc -> qf exists but img and enc are outside stage s1
    assert codes(check_facts(chain, [F("img", "qf", scope="s1")]), "error") == {"fact-out-of-scope"}


def test_unknown_scope_is_error(chain):
    assert codes(check_facts(chain, [F("img", "enc", scope="nope")]), "error") == {"fact-unknown-id"}


def test_waived_fact_is_a_warning(chain):  # round 4 review: a waiver is never silent
    f = check_facts(chain, [F("txt", "qf", waive="text input shown in the detail figure")])
    assert codes(f) == {"fact-waived"} and f[0].severity == "warn"


def test_load_facts_validates(tmp_path):
    p = tmp_path / "facts.json"
    p.write_text(json.dumps({"facts": [{"from": "a"}]}))
    from paperfig.errors import BlueprintError
    with pytest.raises(BlueprintError, match="facts"):
        load_facts(p)


def test_build_includes_fact_findings(mini_bp, tmp_path):
    from paperfig import pipeline as P
    from paperfig.errors import ExportError
    from paperfig.export import find_drawio
    try:
        find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    d = tmp_path / "fig"
    d.mkdir()
    (d / "blueprint.json").write_text(json.dumps(mini_bp))
    (d / "facts.json").write_text(json.dumps({"facts": [F("inp", "out"), F("out", "inp")]}))
    res = P.build(d / "blueprint.json", "soft-pastel", out_dir=tmp_path / "out")
    assert any(x.code == "fact-missing" for x in res.report.findings)
    assert res.report.stats["facts_covered"] == "1/2"
    assert not res.report.ok


def two_panels(extra_edges=()):
    """Panel (a) teaches, panel (b) extends; one cross-panel arrow b → a and one back a → b (the CaseLIP v3 / v5
    blueprints: a fact inside (b) was credited through panel (a), which (b) never draws)."""
    return fig([{"id": "pa", "title": "(a)", "children": [leaf("enc_a", "Encoder"), leaf("z_a", "z")]},
                {"id": "pb", "title": "(b)", "children": [leaf("q_b", "Query"), leaf("enc_b", "Encoder"),
                                                           leaf("loss_b", "Loss")]}],
               [{"src": "q_b", "dst": "enc_b"}, {"src": "enc_b", "dst": "enc_a"}, {"src": "enc_a", "dst": "z_a"},
                {"src": "z_a", "dst": "loss_b"}, *extra_edges])


def test_a_declared_stop_in_the_other_panel_is_allowed():
    assert codes(check_facts(two_panels(), [F("q_b", "loss_b", via=["enc_a"])])) == {"fact-covered"}


def test_fact_between_panels_may_cross():
    assert codes(check_facts(two_panels(), [F("q_b", "z_a")])) == {"fact-covered"}


def test_a_component_drawn_in_both_panels_is_checked_in_the_panel_that_holds_both_ends():
    bp = two_panels([{"src": "enc_b", "dst": "loss_b"}])
    f = check_facts(bp, [F("encoder", "loss_b")], drawn_as=[{"ids": ["encoder"], "into": ["enc_a", "enc_b"]}])
    assert codes(f) == {"fact-covered"} and "enc_a" not in f[0].message


def test_a_copy_outside_the_panel_may_carry_the_fact():
    """TWM / VS-Net runs: one copy of the target sits in the source's panel, but the drawn flow reaches another copy
    outside every panel — the path's own ends decide, not the copies it did not use."""
    bp = fig([{"id": "pa", "title": "(a)", "children": [leaf("s", "Sampler"), leaf("e_in", "Encoder")]},
              {"id": "pb", "title": "(b)", "children": [leaf("x", "x")]}, leaf("o1", "o1"), leaf("e1", "Encoder")],
             [{"src": "s", "dst": "o1"}, {"src": "o1", "dst": "e1"}])
    f = check_facts(bp, [F("s", "enc")], drawn_as=[{"ids": ["enc"], "into": ["e_in", "e1"]}])
    assert codes(f) == {"fact-covered"}


def test_via_stops_chain_through_the_copy_the_previous_step_reached():
    """CaseLIP v5: each step of a `via` fact picked its own copy, so q → enc_b and enc_a → z_a were joined into one
    'path' with no arrow between enc_b and enc_a. A step starts where the previous one ended."""
    bp = fig([{"id": "pa", "title": "(a)", "children": [leaf("enc_a", "Encoder"), leaf("z_a", "z")]},
              {"id": "pb", "title": "(b)", "children": [leaf("q", "Query"), leaf("enc_b", "Encoder")]}],
             [{"src": "q", "dst": "enc_b"}, {"src": "enc_a", "dst": "z_a"}])
    da = [{"ids": ["enc"], "into": ["enc_a", "enc_b"]}]
    assert codes(check_facts(bp, [F("q", "z_a", via=["enc"])], drawn_as=da), "error") == {"fact-missing"}
    bp2 = fig([{"id": "pa", "title": "(a)", "children": [leaf("enc_a", "Encoder"), leaf("z_a", "z")]},
               {"id": "pb", "title": "(b)", "children": [leaf("q", "Query"), leaf("enc_b", "Encoder"), leaf("z_b", "z")]}],
              [{"src": "q", "dst": "enc_b"}, {"src": "enc_a", "dst": "z_a"}, {"src": "enc_b", "dst": "z_b"}])
    f = check_facts(bp2, [F("q", "zz", via=["enc"])], drawn_as=da + [{"ids": ["zz"], "into": ["z_a", "z_b"]}])
    assert codes(f) == {"fact-covered"} and f[0].message.endswith("q → enc_b → z_b")
