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


def test_waived_fact_is_info(chain):
    f = check_facts(chain, [F("txt", "qf", waive="text input shown in the detail figure")])
    assert codes(f) == {"fact-waived"} and f[0].severity == "info"


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
