import json

import pytest

from paperfig import artifacts, plan as P
from paperfig.blueprint import load
from paperfig.facts import check_facts

FACTS = [{"id": "f_in", "from": "inp", "to": "enc", "quote": "q", "ref": "Sec. 3"},
         {"id": "f_skip", "from": "enc", "to": "out", "quote": "q", "ref": "Sec. 3"},
         {"id": "f_gone", "from": "enc", "to": "aux_head", "quote": "q", "ref": "Sec. 3"}]


def plan(**kw):
    p = {"takeaway": "An encoder-decoder with a fusion module restores the input image.",
         "concepts": [{"id": "c1", "name": "U-shape with feature maps", "adapts": "uformer-2022-fig2", "takes": "U layout"},
                      {"id": "c2", "name": "linear pipeline", "adapts": "promptir-2023-fig3", "takes": "detail panel"}],
         "chosen": "c1", "why": "the paper's encoder-decoder is symmetric",
         "core": ["inp", "enc", "csfm", "dec", "out"], "highlight": "CSFM named and expanded",
         "data_visuals": [{"what": "input image", "visual": "image", "source": "placeholder", "path": None, "licence": None, "for": "inp"}],
         "omitted": [{"fact": "f_gone", "reason": "auxiliary head used only for an ablation", "where": "text"}]}
    p.update(kw)
    return p


def write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def test_plan_concept_needs_reference(tmp_path):
    facts = write(tmp_path, "facts.json", {"facts": FACTS})
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", plan()), facts=facts) == []
    bad = plan(concepts=[{"id": "c1", "name": "x", "adapts": "no-such-card", "takes": "layout"},
                         {"id": "c2", "name": "z", "adapts": "uformer-2022-fig2", "takes": "layout"}])
    assert any("no-such-card" in p for p in artifacts.validate("figure-plan", write(tmp_path, "b.json", bad), facts=facts))
    assert any("chosen" in p for p in artifacts.validate("figure-plan", write(tmp_path, "c.json", plan(chosen="c9")), facts=facts))
    assert any("f_nope" in p for p in artifacts.validate(
        "figure-plan", write(tmp_path, "d.json", plan(omitted=[{"fact": "f_nope", "reason": "not needed here", "where": "text"}])), facts=facts))


def test_plan_concept_may_cite_a_selected_reference(tmp_path):
    refs = write(tmp_path, "refs.json", {"selected": [{"title": "Some Paper", "arxiv_id": "2401.00001", "url": "https://arxiv.org/abs/2401.00001"}]})
    p = plan(concepts=[{"id": "c1", "name": "x", "adapts": "2401.00001", "takes": "layout"},
                       {"id": "c2", "name": "z", "adapts": "uformer-2022-fig2", "takes": "layout"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", p), refs=refs) == []


def test_omitted_fact_is_info(mini_bp):
    bp = load(mini_bp)
    ff = P.apply_plan(check_facts(bp, FACTS), plan())
    gone = [f for f in ff if "f_gone" in f.ids]
    assert gone and gone[0].code == "fact-omitted" and gone[0].severity == "info" and "ablation" in gone[0].message


def test_unplanned_missing_fact_is_error(mini_bp):
    bp = load(mini_bp)
    ff = P.apply_plan(check_facts(bp, FACTS), plan(omitted=[]))
    assert any(f.code in ("fact-missing", "fact-unknown-id") and f.severity == "error" and "f_gone" in f.ids for f in ff)


def test_run_check_requires_plan(tmp_path):
    from paperfig import run
    from test_run import _complete_run

    d = _complete_run(tmp_path)
    assert any("figure_plan.json" in p for p in run.check(d))
