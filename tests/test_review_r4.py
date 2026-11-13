"""Round 4 whole-skill review: one test per finding that code can decide (numbers = the review's findings)."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from conftest import MINI, PROV, leaf
from paperfig import artifacts, kb, run
from paperfig.errors import PaperFigError

ROOT = Path(__file__).resolve().parents[1]


def _w(p, obj):
    p.write_text(json.dumps(obj))
    return p


# 1 — samples with a style file path
def test_samples_accept_a_style_file(tmp_path):
    from paperfig.samples import make_samples
    from paperfig.styles import STYLES_DIR
    style = shutil.copy(STYLES_DIR / "soft-pastel.json", tmp_path / "style.json")
    bp = _w(tmp_path / "blueprint.json", copy.deepcopy(MINI))
    res = make_samples(bp, [str(style), "editorial-minimal"], None, tmp_path / "samples", None)
    assert {s.style for s in res.shown} == {str(style), "editorial-minimal"}, res.skipped
    assert (tmp_path / "samples" / "samples.json").is_file()


# 2 — run check validates the plan with the analysis
def test_run_check_validates_plan_with_analysis(tmp_path):
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    bp = copy.deepcopy(MINI)
    _w(d / "blueprint.json", bp)
    from paperfig.blueprint import load
    eid = next(e.id for e in load(bp).edges if e.src == "inp")
    an = json.loads((d / "analysis.draft.json").read_text())
    an["components"].append({"id": "norm", "name": "Norm", "abbrev": None, "role": "reused", "what": "norm",
                             "provenance": an["components"][0]["provenance"]})
    _w(d / "analysis.draft.json", an)
    from test_plan import plan
    _w(d / "figure_plan.json", plan(omitted=[], drawn_as=[{"ids": ["norm"], "on_edge": eid, "how": "label on the arrow"}]))
    assert not [p for p in run.check(d) if "drawn_as" in p], run.check(d)


# 3 — a user revision round is recorded without a critic
def test_user_revision_round_without_critic(tmp_path):
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    lint = {"ok": True, "counts": {"error": 0, "warn": 0, "info": 0}, "stats": {}, "findings": []}
    for n in (1, 2, 3):
        (d / "build" / f"r{n}").mkdir()
        _w(d / "build" / f"r{n}" / "fig.lint.json", lint)
    _w(d / "critic" / "r1.json", {"viewed_png": True, "scores": {}, "issues": [], "io_audit": []})
    run.record_round(d, 1, d / "build/r1/fig.lint.json", d / "critic" / "r1.json", "first")
    run.record_round(d, 2, d / "build/r2/fig.lint.json", None, "applied r1", critic_of=1)
    run.record_round(d, 3, d / "build/r3/fig.lint.json", None, "user: make the decoder blue", by_user=True)
    rec = json.loads((d / "run.json").read_text())
    assert rec["rounds"][-1]["by_user"] is True and rec["rounds"][-1]["n"] == 3
    with pytest.raises(PaperFigError, match="note"):
        run.record_round(d, 4, d / "build/r3/fig.lint.json", None, "", by_user=True)


# 4 — reused cards are copied into the run; run cards reach the brief whatever their domain
def test_reused_card_copied_and_run_cards_in_brief(tmp_path):
    out = tmp_path / "cards"
    p = kb.copy_card("hgt-2020-fig2", out)
    assert p.is_file() and json.loads(p.read_text())["id"] == "hgt-2020-fig2"
    brief = kb.query("diffusion", "cvpr", run_cards=out)
    assert "hgt-2020-fig2" in [c["id"] for c in brief["cards"]]  # a graph-learning card, still in the brief


# 5 — the derived accent never takes the reused tone
def test_derived_accent_differs_from_reused(tmp_path):
    from paperfig.styles import derive_style, load_recipe
    cards = tmp_path / "c"
    cards.mkdir()
    _w(cards / "a.json", {"id": "a", "measured": {"palette": [{"hex": "#3b6fd6", "share": 0.3, "neutral": False},
                                                             {"hex": "#e07b39", "share": 0.05, "neutral": False}]}})
    r = load_recipe(str(derive_style("soft-pastel", cards, tmp_path / "s.json")))
    roles = r["palette"]["roles"]
    assert roles["proposed"]["tone"] != roles["reused"]["tone"] and roles["proposed"]["tone"] not in ("gray", "grey")


# 6 — a loss/control fact without kinds is caught at validation
def test_fact_without_kinds_for_loss_flow_is_flagged(tmp_path):
    from test_artifacts import TEXT, draft
    an = draft(data_flow=[{"from": "inp", "to": "embed", "label": None, "kind": "loss",
                           "provenance": {"ref": "Sec. 3", "quote": "Restormer first applies a convolution"}}])
    a = _w(tmp_path / "a.json", an)
    f = _w(tmp_path / "f.json", {"facts": [{"id": "f1", "from": "inp", "to": "embed", "quote": "first applies a convolution", "ref": "Sec. 3"}]})
    t = tmp_path / "m.txt"
    t.write_text(TEXT)
    assert any("kinds" in p for p in artifacts.validate("facts", f, text=t, analysis=a))


# 7 — waived facts count as left out and are warned
def test_waived_facts_are_not_silent(mini_bp):
    from paperfig.blueprint import load
    from paperfig.facts import check_facts
    from paperfig.plan import apply_plan
    facts = [{"id": "f1", "from": "inp", "to": "nowhere", "quote": "q", "ref": "s", "waive": "too fine"}]
    ff = apply_plan(check_facts(load(mini_bp), facts), {"omitted": []})
    assert any(f.code == "fact-waived" and f.severity == "warn" for f in ff)
    assert any(f.code == "facts-all-omitted" for f in ff)


# 8 — a proposed component drawn as reused or misnamed; an unstated data edge
def test_blueprint_checked_against_analysis(tmp_path):
    from paperfig.consistency import check_against_analysis
    from paperfig.blueprint import load
    bp = copy.deepcopy(MINI)
    bp["root"]["children"][2]["role"] = "reused"  # csfm demoted
    an = {"components": [{"id": "csfm", "name": "Cross-Scale Fusion Module", "abbrev": "CSFM", "role": "proposed"},
                         {"id": "inp"}, {"id": "enc"}, {"id": "dec"}, {"id": "out"}, {"id": "msa"}, {"id": "gf"}],
          "data_flow": [{"from": "inp", "to": "enc"}, {"from": "enc", "to": "csfm"}, {"from": "csfm", "to": "dec"},
                        {"from": "dec", "to": "out"}, {"from": "msa", "to": "gf"}]}
    codes = {f.code: f for f in check_against_analysis(load(bp), an, None)}
    assert "proposed-mismatch" in codes and codes["proposed-mismatch"].severity == "error"
    from paperfig.consistency import _tokens
    assert _tokens("Max Pooling Layer") <= _tokens("max pooling") and _tokens("feature alignment network") <= _tokens("align features joint alignment")
    assert "edge-unstated" in codes and "enc" in codes["edge-unstated"].ids  # the enc->dec skip is in no data_flow


# 9 — code-only facts are checked against the repo
def test_code_only_facts_checked_against_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.py").write_text("x = self.encoder(img)\ny = self.decoder(x)\n")
    good = {"facts": [{"id": "f1", "from": "enc", "to": "dec", "quote": "y = self.decoder(x)", "ref": "model.py:2"}]}
    assert artifacts.validate("facts", _w(tmp_path / "g.json", good), repo=repo) == []
    bad = {"facts": [{"id": "f1", "from": "enc", "to": "dec", "quote": "y = self.attention(x)", "ref": "model.py:2"}]}
    assert artifacts.validate("facts", _w(tmp_path / "b.json", bad), repo=repo)


# 10 — doctor and dependencies know pypdf
def test_pypdf_is_a_declared_dependency():
    assert "pypdf" in (ROOT / "pyproject.toml").read_text()
    assert "pypdf" in (ROOT / "paperfig" / "doctor.py").read_text()


# 14 — svg is delivered when built
def test_deliver_includes_svg():
    assert "fig.svg" in run.DELIVER_OPTIONAL


# 15 — an unknown venue fails at validation, not at build
def test_unknown_venue_rejected_at_load():
    from paperfig.blueprint import load
    from paperfig.errors import BlueprintError
    bp = copy.deepcopy(MINI)
    bp["figure"]["venue"] = "CVPR 2026"
    with pytest.raises(BlueprintError, match="venue"):
        load(bp)
    bp["figure"]["width"] = 6.5  # inches given: any venue name is fine
    load(bp)


# 12 — a worked v2 Brief ships and stays valid
def test_example_brief_validates():
    ex = ROOT / "references" / "examples" / "restormer.figure_plan.json"
    probs = artifacts.validate("figure-plan", ex, facts=ROOT / "bench/phase0/restormer/facts.json",
                               blueprint=ROOT / "bench/phase0/restormer/blueprint.json")
    assert probs == [], probs
