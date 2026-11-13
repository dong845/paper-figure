"""Round-6 validation run (Reflexion, an agent loop): fixes for what the runner hit."""
import copy

from conftest import MINI, PROV, leaf
from paperfig.blueprint import load
from paperfig.facts import check_facts
from paperfig.plan import apply_plan


def _loop():
    """actor -> evaluator -> reflect -> memory -> actor: a drawn loop."""
    ids = ["actor", "evaluator", "reflect", "memory"]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf(i, i.title()) for i in ids]},
            "edges": [{"src": a, "dst": b, "provenance": copy.deepcopy(PROV)}
                      for a, b in zip(ids, ids[1:] + ids[:1])]}


def _fact(a, b, **kw):
    return {"id": f"{a}-{b}", "from": a, "to": b, "quote": "q", "ref": "Sec. 3", **kw}


def _codes(ff):
    return {f.ids[0]: f.code for f in ff if f.ids}


def test_a_loop_does_not_cover_the_reverse_of_a_drawn_arrow():
    """In a loop everything reaches everything; a fact whose reverse is a drawn arrow is not drawn."""
    bp = load(_loop())
    got = _codes(check_facts(bp, [_fact("memory", "reflect"), _fact("evaluator", "actor"),
                                  _fact("actor", "reflect"), _fact("memory", "actor")]))
    assert got["memory-reflect"] == "fact-reversed" and got["evaluator-actor"] == "fact-reversed"
    assert got["actor-reflect"] == "fact-covered" and got["memory-actor"] == "fact-covered"


def test_plan_can_omit_a_reversed_fact():
    bp = load(_loop())
    ff = apply_plan(check_facts(bp, [_fact("memory", "reflect"), _fact("memory", "actor")]),
                    {"omitted": [{"fact": "memory-reflect", "where": "caption", "reason": "detail"}]})
    assert _codes(ff)["memory-reflect"] == "fact-omitted"


def test_plan_omitting_a_drawn_fact_is_flagged():
    bp = load(_loop())
    ff = apply_plan(check_facts(bp, [_fact("memory", "actor"), _fact("actor", "evaluator")]),
                    {"omitted": [{"fact": "memory-actor", "where": "caption", "reason": "detail"}]})
    hit = [f for f in ff if f.code == "fact-omitted-drawn"]
    assert hit and hit[0].severity == "warn" and hit[0].ids == ["memory-actor"]


def test_an_edge_from_a_group_leaves_from_its_exit_members():
    """Symmetric to entering a container: csfm -> dec carries what leaves gf (gf has no edge of its own out)."""
    bp = load(copy.deepcopy(MINI))
    got = _codes(check_facts(bp, [_fact("gf", "dec"), _fact("msa", "dec")]))
    assert got == {"gf-dec": "fact-covered", "msa-dec": "fact-covered"}
