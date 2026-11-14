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


def test_dataset_image_needs_licence_and_source(tmp_path):
    ok = {"what": "CT slice", "visual": "image", "source": "dataset", "path": "assets/ct.png",
          "licence": "CC BY-SA 4.0", "url": "https://example.org/dataset", "for": "inp"}
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", plan(data_visuals=[ok]))) == []
    for drop in ("licence", "url", "path"):
        bad = dict(ok, **{drop: None})
        probs = artifacts.validate("figure-plan", write(tmp_path, f"b_{drop}.json", plan(data_visuals=[bad])))
        assert any(drop in p for p in probs), (drop, probs)
    repo = {"what": "demo image", "visual": "image", "source": "repo", "path": None, "licence": None, "for": "inp"}
    assert any("path" in p for p in artifacts.validate("figure-plan", write(tmp_path, "r.json", plan(data_visuals=[repo]))))


# ---- round-2 fix pass: facts at the granularity the figure draws (F57, F31, F48)
def _mini_edges(bp, src, dst):
    return next(e.id for e in bp.edges if e.src == src and e.dst == dst)


def test_drawn_as_edge_label_covers_internal_facts(mini_bp):
    bp = load(mini_bp)
    eid = _mini_edges(bp, "inp", "enc")
    facts = [{"id": "f1", "from": "inp", "to": "embed", "quote": "q", "ref": "s"},
             {"id": "f2", "from": "embed", "to": "norm", "quote": "q", "ref": "s"},
             {"id": "f3", "from": "norm", "to": "enc", "quote": "q", "ref": "s"},
             {"id": "f4", "from": "norm", "to": "out", "quote": "q", "ref": "s"}]
    bare = check_facts(bp, facts)
    assert all(f.code == "fact-unknown-id" for f in bare)
    drawn = [{"ids": ["embed", "norm"], "on_edge": eid, "how": "label E on the input arrow"}]
    ff = P.apply_plan(check_facts(bp, facts, drawn_as=drawn), plan(omitted=[], drawn_as=drawn))
    assert sorted(f.ids[0] for f in ff if f.code == "fact-covered") == ["f1", "f2", "f3", "f4"], [f.message for f in ff]


def test_drawn_as_replicas_any_copy_counts(mini_bp):
    bp = load(mini_bp)
    facts = [{"id": "f1", "from": "head", "to": "out", "quote": "q", "ref": "s"},
             {"id": "f2", "from": "inp", "to": "head", "quote": "q", "ref": "s"}]
    drawn = [{"ids": ["head"], "into": ["msa", "dec"], "how": "one copy per timestep"}]
    ff = check_facts(bp, facts, drawn_as=drawn)
    assert [f.code for f in ff] == ["fact-covered", "fact-covered"], [f.message for f in ff]


def test_plan_that_omits_every_fact_is_error(mini_bp):
    bp = load(mini_bp)
    gone = [{"fact": f["id"], "reason": "not drawn here", "where": "text"} for f in FACTS]
    facts = [dict(f, to="nowhere") for f in FACTS]
    ff = P.apply_plan(check_facts(bp, facts), plan(omitted=gone))
    assert any(f.code == "facts-all-omitted" and f.severity == "error" for f in ff), [f.code for f in ff]
    two_gone = [FACTS[0], dict(FACTS[1], to="aux2"), FACTS[2]]  # 2 of 3 not drawn, both planned out
    half = P.apply_plan(check_facts(bp, two_gone), plan(omitted=[{"fact": "f_gone", "reason": "ablation only", "where": "text"},
                                                                 {"fact": "f_skip", "reason": "too fine", "where": "text"}]))
    assert any(f.code == "fact-omitted-majority" and f.severity == "warn" for f in half), [f.code for f in half]


def test_member_with_its_own_inbound_edge_is_reached_through_its_container(mini_bp):
    d = mini_bp  # msa's only other inbound edge comes from an isolated side input
    d["root"]["children"].append({"id": "side", "label": "Side", "provenance": d["edges"][0]["provenance"]})
    d["edges"].append({"src": "side", "dst": "msa", "provenance": d["edges"][0]["provenance"]})
    bp = load(d)
    ff = check_facts(bp, [{"id": "f", "from": "enc", "to": "msa", "quote": "q", "ref": "s"}])
    assert ff[0].code == "fact-covered", ff[0].message


def test_validator_checks_drawn_as(tmp_path, mini_bp):
    facts = write(tmp_path, "facts.json", {"facts": FACTS + [{"id": "f_e", "from": "inp", "to": "embed", "quote": "q", "ref": "s"}]})
    bpp = write(tmp_path, "bp.json", mini_bp)
    eid = _mini_edges(load(mini_bp), "inp", "enc")
    good = plan(drawn_as=[{"ids": ["embed"], "on_edge": eid, "how": "label E"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "g.json", good), facts=facts, blueprint=bpp) == []
    for bad, needle in ((plan(drawn_as=[{"ids": ["embed"], "on_edge": "e99", "how": "label"}]), "e99"),
                        (plan(drawn_as=[{"ids": ["embed"], "into": "nope", "how": "label"}]), "nope"),
                        (plan(drawn_as=[{"ids": ["enc"], "into": "dec", "how": "label"}]), "enc"),
                        (plan(drawn_as=[{"ids": ["typo"], "into": "dec", "how": "label"}]), "typo")):
        probs = artifacts.validate("figure-plan", write(tmp_path, "b.json", bad), facts=facts, blueprint=bpp)
        assert any(needle in p for p in probs), (needle, probs)


# ---- round 3: the design Brief (user's guide) — three reading levels, train/infer, grammar
def _bp_with_panel(mini_bp):
    d = mini_bp
    d["root"]["layout"] = {"type": "row"}
    d["root"]["children"].append({"id": "zoom", "title": "(b) CSFM", "detail_of": "csfm", "place": "free",
                                  "layout": {"type": "row"}, "provenance": d["edges"][0]["provenance"],
                                  "children": [{"id": "z1", "label": "Attention", "provenance": d["edges"][0]["provenance"]}]})
    return d


def brief_v2(**kw):
    b = plan(brief_version=2, problem="Fixed-scale fusion loses fine detail in restoration.",
             io={"inputs": ["degraded image"], "outputs": ["restored image"]},
             contributions=[{"name": "Cross-Scale Fusion Module", "solves": "fixed-scale fusion",
                             "shown_by": "orange panel, named, expanded in (b)", "ids": ["csfm"]}],
             mechanism=[{"explains": "how attention mixes scales", "ids": ["z1"], "panel": "zoom"}],
             train_only=[], infer_kept=["inp", "enc", "csfm", "dec", "out"],
             key_representations=[{"name": "multi-scale feature", "ids": ["msa", "gf"], "visual": "box", "tone": "orange"}],
             color_semantics={"orange": "proposed module", "blue": "reused encoder", "green": "reused decoder"},
             annotate=["H/2, H/4 scales"], export={"width": "double", "formats": ["pdf", "png"]})
    b.update(kw)
    return b


def test_brief_v2_validates(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    facts = write(tmp_path, "facts.json", {"facts": FACTS})
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", brief_v2()), facts=facts, blueprint=bpp) == []
    probs = artifacts.validate("figure-plan", write(tmp_path, "q.json", plan(brief_version=2)), facts=facts)
    assert any("problem" in p for p in probs) and any("mechanism" in p for p in probs), probs  # v2 needs the brief


def test_brief_v2_limits(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    c = {"name": "x", "solves": "y y", "shown_by": "z z", "ids": ["csfm"]}
    for bad, needle in ((brief_v2(contributions=[c] * 4), "contributions"),
                        (brief_v2(mechanism=[{"explains": "a b", "ids": ["z1"], "panel": "csfm"}]), "detail_of"),
                        (brief_v2(mechanism=[{"explains": "a b", "ids": ["nope"]}]), "nope"),
                        (brief_v2(train_only=["ghost"]), "ghost"),
                        (brief_v2(mechanism=[]), "mechanism")):
        probs = artifacts.validate("figure-plan", write(tmp_path, "b.json", bad), blueprint=bpp)
        assert any(needle in p for p in probs), (needle, probs)


def test_mechanism_equations_must_exist_in_the_analysis(tmp_path, mini_bp):
    an = write(tmp_path, "analysis.json", {"equations": [{"id": "eq1", "text": "y = f(x)", "relates": ["csfm"],
                                                          "provenance": {"ref": "Eq. 1", "quote": "q"}}]})
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    ok = brief_v2(mechanism=[{"explains": "how scales mix", "ids": ["z1"], "panel": "zoom", "equations": ["eq1"]}])
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", ok), blueprint=bpp, analysis=an) == []
    bad = brief_v2(mechanism=[{"explains": "how scales mix", "ids": ["z1"], "panel": "zoom", "equations": ["eq9"]}])
    assert any("eq9" in p for p in artifacts.validate("figure-plan", write(tmp_path, "q.json", bad), blueprint=bpp, analysis=an))


# ---- round 4: references are optional; run cards count as references
def test_concept_may_adapt_none(tmp_path):
    """User 2026-11-13: if no reference fits after analysis, design from the material and the venue's conventions."""
    p = plan(concepts=[{"id": "c1", "name": "own layout", "adapts": "none", "takes": "CVPR overview conventions: left-to-right, full width"},
                       {"id": "c2", "name": "z", "adapts": "uformer-2022-fig2", "takes": "layout"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", p)) == []
    bad = plan(concepts=[{"id": "c1", "name": "own", "adapts": "none", "takes": "x"}, plan()["concepts"][1]])
    assert any("takes" in q for q in artifacts.validate("figure-plan", write(tmp_path, "b.json", bad)))


def test_concept_may_cite_run_card(tmp_path):
    refs_dir = tmp_path / "refs"
    (refs_dir / "cards").mkdir(parents=True)
    (refs_dir / "refs.json").write_text(json.dumps({"selected": []}))
    (refs_dir / "cards" / "vq-diffusion-2021-fig1.json").write_text(json.dumps({"id": "vq-diffusion-2021-fig1"}))
    p = plan(concepts=[{"id": "c1", "name": "x", "adapts": "vq-diffusion-2021-fig1", "takes": "layout"},
                       {"id": "c2", "name": "z", "adapts": "uformer-2022-fig2", "takes": "layout"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", p), refs=refs_dir / "refs.json") == []


# ---- round 4 T5: validator rules the runners tripped over
def test_brief_accepts_brackets_drawn_as_and_analysis_components(tmp_path, mini_bp):
    d = _bp_with_panel(mini_bp)
    d["annotations"] = [{"id": "stage2", "kind": "bracket", "covers": ["enc", "csfm"], "label": "Stage 2", "side": "top"}]
    bpp = write(tmp_path, "bp.json", d)
    eid = _mini_edges(load(mini_bp), "inp", "enc")
    an = write(tmp_path, "analysis.json", {"components": [{"id": "fwd_process"}, {"id": "head"}], "equations": []})
    facts = write(tmp_path, "facts.json", {"facts": FACTS})
    p = brief_v2(contributions=[{"name": "two-stage training", "solves": "y y", "shown_by": "bracket", "ids": ["stage2"]}],
                 drawn_as=[{"ids": ["fwd_process"], "on_edge": eid, "how": "label on the arrow"},
                           {"ids": ["head"], "into": "dec", "how": "merged"}],
                 train_only=["fwd_process"],
                 data_visuals=[{"what": "photo", "visual": "image", "source": "public-sample", "path": "a.png",
                                "licence": "CC0", "url": "https://example.org/x", "for": "inp"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "p.json", p), blueprint=bpp, analysis=an, facts=facts) == []


def test_drawn_as_accepts_code_only_components(tmp_path):
    """Blind DreamerV3 run: a part named only by the code analysis ('enc') could not be mapped in drawn_as."""
    import json as _j
    from paperfig import artifacts
    from paperfig.artifacts import validate
    plan_p = tmp_path / "figure_plan.json"
    import inspect
    from test_plan import plan as mkplan
    pl = mkplan(omitted=[], drawn_as=[{"ids": ["enc_code"], "into": "enc", "how": "the code's encoder is the Encoder box"}])
    plan_p.write_text(_j.dumps(pl))
    draft = tmp_path / "analysis.draft.json"
    draft.write_text(_j.dumps({"components": [{"id": "enc"}]}))
    code = tmp_path / "analysis.code.json"
    code.write_text(_j.dumps({"components": [{"id": "enc_code"}]}))
    facts = tmp_path / "facts.json"
    facts.write_text(_j.dumps({"facts": []}))
    only_draft = [p for p in validate("figure-plan", plan_p, analysis=draft, facts=facts) if "enc_code" in p]
    both = [p for p in validate("figure-plan", plan_p, analysis=[draft, code], facts=facts) if "enc_code" in p]
    assert only_draft and not both


def test_two_analyses_never_crash_validation(tmp_path):
    """STORM / DreamerV3 runs: run check passed [draft, code] and the plan's mechanism check (and validate facts
    --analysis A --analysis B) crashed with 'argument should be a str … not list'."""
    import json as _j
    from paperfig.artifacts import validate
    draft = tmp_path / "analysis.draft.json"
    draft.write_text(_j.dumps({"components": [{"id": "enc"}], "equations": [{"id": "eq_enc", "tex": "x"}],
                               "data_flow": []}))
    code = tmp_path / "analysis.code.json"
    code.write_text(_j.dumps({"components": [{"id": "enc_code"}], "data_flow": []}))
    from test_plan import plan as mkplan
    pl = mkplan(omitted=[], drawn_as=[])
    pl["mechanism"] = [{"what": "x", "equations": ["eq_enc"]}]
    (tmp_path / "figure_plan.json").write_text(_j.dumps(pl))
    facts = tmp_path / "facts.json"
    facts.write_text(_j.dumps({"facts": []}))
    validate("figure-plan", tmp_path / "figure_plan.json", analysis=[draft, code], facts=facts)  # no TypeError
    validate("facts", facts, analysis=[draft, code])
