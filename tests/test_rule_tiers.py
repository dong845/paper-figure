"""Rule tiers (user, 2026-11-24): invariants (faithful, legible, printable) never bend; design defaults are priors a
plan may depart from with a reason and evidence; taste is judged, not ruled. A user's example figure sets the bar."""
import json
import pathlib
import re

import pytest

import test_layout_round as L
from paperfig import artifacts, lint
from paperfig.rules import INVARIANTS, PLAN_RULES, apply_deviations, deviation_problems

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _emitted():
    codes, errors = set(lint.CHECKS), set()
    for f in ("lint", "grammar", "plan", "facts", "pipeline", "consistency"):
        s = (ROOT / "paperfig" / f"{f}.py").read_text(encoding="utf-8")
        codes |= set(re.findall(r'(?:rep\.add|Finding)\(\s*"([a-z-]+)"', s))
        errors |= set(re.findall(r'(?:rep\.add|Finding)\(\s*"([a-z-]+)",\s*"error"', s))
    return codes, errors


def test_invariants_are_real_codes_and_every_hard_error_is_an_invariant():
    codes, errors = _emitted()
    assert INVARIANTS <= codes, sorted(INVARIANTS - codes)
    assert errors <= INVARIANTS, sorted(errors - INVARIANTS)  # a code that always blocks must be a correctness rule


def test_a_deviation_needs_a_default_a_reason_and_real_evidence():
    ok = {"rule": "ink-heavy", "why": "the method's state lives in tinted panels the reader must tell apart",
          "evidence": {"kind": "card", "ref": "clip-2021-fig1"}}
    assert deviation_problems({"deviations": [ok]}, known_cards={"clip-2021-fig1"}) == []
    for bad, msg in [
        (dict(ok, rule="overlap"), "invariant"),
        (dict(ok, rule="plan:nonsense"), "unknown plan rule"),
        (dict(ok, why="denser"), "say why"),
        (dict(ok, evidence={"kind": "vibes", "ref": "x"}), "evidence.kind"),
        (dict(ok, evidence={"kind": "card", "ref": "no-such-card"}), "not in the knowledge base"),
        (dict(ok, evidence={"kind": "user-draft", "ref": "user-draft"}), "missing"),
        (dict(ok, evidence={"kind": "user", "ref": "dense"}), "quote what the user asked"),
    ]:
        assert any(msg in p for p in deviation_problems({"deviations": [bad]}, known_cards={"clip-2021-fig1"})), msg


def test_deviated_findings_are_reported_not_fixed_and_invariants_never_bend():
    F = lint.Finding
    plan = {"deviations": [{"rule": "palette-busy", "why": "each tool panel keeps its own colour as in the target",
                            "evidence": {"kind": "user", "ref": "like VERA figure 2"}},
                           {"rule": "overlap", "why": "never honoured even if a plan lists it here",
                            "evidence": {"kind": "user", "ref": "please allow overlaps"}}]}
    out = apply_deviations([F("palette-busy", "warn", [], "9 colours"), F("overlap", "error", ["a"], "a hides b")], plan)
    assert out[0].severity == "info" and out[0].message.startswith("deviated (each tool panel")
    assert out[1].severity == "error"


def test_a_design_check_yields_to_a_recorded_deviation(tmp_path):
    probs = L._check(tmp_path, "single", L._layout(partition="single", units=[]))
    assert any("stream" in p.lower() for p in probs)  # the default: stages / streams get their own units
    bpp = L.write(tmp_path, "bp-dev.json", L._two_streams())
    an = L._streams_analysis(tmp_path, False)
    p = L.brief_v2(layout=L._layout(partition="single", units=[]), drawn_as=L.DRAWN, structure=L.STRUCT,
                   contributions=[{"name": "Aggregator", "solves": "x y", "shown_by": "a b", "ids": ["agg"]}],
                   mechanism=[{"explains": "how it aggregates", "ids": ["agg"]}], infer_kept=["img_a"],
                   key_representations=[], core=["img_a", "agg"],
                   supervision={"ids": ["l_cap_a"], "how": "a pair matrix per objective"},
                   deviations=[{"rule": "plan:stages-partition",
                                "why": "the user wants one dense panel like their own draft, streams told apart by colour",
                                "evidence": {"kind": "user", "ref": "draw both streams in one panel"}}])
    probs = artifacts.validate("figure-plan", L.write(tmp_path, "p-dev.json", p), blueprint=bpp, analysis=an)
    assert not any("separates" in x or "no unit draws the stream" in x for x in probs), probs
    assert set(PLAN_RULES) >= {"plan:stages-partition", "plan:losses-per-stream", "plan:supervision"}


def test_the_users_target_figure_sets_the_density_bar(monkeypatch, tmp_path):
    """VERA-like richness is not flagged when the user showed a figure that rich."""
    from paperfig import grammar
    from paperfig import pipeline as P
    r = P.build(ROOT / "examples" / "restormer.blueprint.json", "soft-pastel", out_dir=tmp_path / "a", formats=("png",))
    assert any(f.code == "ink-heavy" for f in r.report.findings)  # 45% inked: above the KB's p75
    monkeypatch.setattr(grammar, "target_measure", lambda bp: {"ink_ratio": 0.6, "palette": [], "aspect": 1.0})
    r = P.build(ROOT / "examples" / "restormer.blueprint.json", "soft-pastel", out_dir=tmp_path / "b", formats=("png",))
    assert not any(f.code in ("ink-heavy", "aspect-tall") for f in r.report.findings)
