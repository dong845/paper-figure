"""Overview depth, balanced space and colour inside a module (user, 2026-11-28): name a proposed module in the
overview and open it in an inset or a figure of its own — one zoom level; no large blank region; a module whose
parts are all one strong colour has no hierarchy."""
import copy
import json
import shutil
from pathlib import Path

from paperfig import artifacts, pipeline as P
from paperfig.blueprint import load
from paperfig.geometry import Box
from paperfig.lint import largest_hole

from test_plan import FACTS, _bp_with_panel, brief_v2, write

CORPUS = Path(__file__).resolve().parents[1] / "bench/corpus"
PROV = {"ref": "Sec. 3", "quote": "a quote of twelve letters"}


def _analysis(tmp_path, inner=4):
    comps = [{"id": "csfm", "name": "Cross-Scale Fusion Module", "role": "proposed", "what": "fuses", "parent": None,
              "inner_parts": inner, "provenance": PROV},
             {"id": "msa", "name": "Multi-Scale Attention", "role": "proposed", "what": "x", "parent": "csfm",
              "provenance": PROV}]
    return write(tmp_path, "an.json", {"components": comps, "equations": []})


def _depth_probs(tmp_path, bp, depth, inner=4):
    p = brief_v2() if depth is None else brief_v2(depth=depth)
    return artifacts.validate("figure-plan", write(tmp_path, "p.json", p), blueprint=write(tmp_path, "bp.json", bp),
                              analysis=_analysis(tmp_path, inner), facts=write(tmp_path, "f.json", {"facts": FACTS}))


def test_every_outer_proposed_module_needs_a_depth(tmp_path, mini_bp):
    probs = _depth_probs(tmp_path, _bp_with_panel(mini_bp), None)
    assert any("'csfm'" in p and "has no depth" in p for p in probs), probs
    assert not any("'msa'" in p and "has no depth" in p for p in probs)  # a part inside a proposed module is not asked


def test_inset_needs_its_panel_and_box_needs_none(tmp_path, mini_bp):
    bp = _bp_with_panel(mini_bp)  # 'zoom' is detail_of csfm, csfm drawn as an open group
    inset = [{"id": "csfm", "as": "inset", "why": "the mechanism the reader needs", "panel": "zoom"}]
    probs = _depth_probs(tmp_path, bp, inset)
    assert any("open group" in p for p in probs), probs  # opened in place AND zoomed: drawn twice
    boxed = copy.deepcopy(bp)
    boxed["root"]["children"][2] = {"id": "csfm", "label": "<b>CSFM</b><br><small>fuses scales</small>", "role": "proposed",
                                    "full_name": "Cross-Scale Fusion Module", "abbrev": "CSFM",
                                    "provenance": [{"source": "draft", "ref": "Sec. 3"}]}
    boxed["root"]["children"][-1]["children"] += [{"id": "msa", "label": "Multi-Scale Attention", "role": "proposed",
                                                   "provenance": [{"source": "draft", "ref": "Sec. 3"}]},
                                                  {"id": "gf", "label": "Gated Fusion", "role": "proposed",
                                                   "provenance": [{"source": "draft", "ref": "Sec. 3"}]}]
    ok = _depth_probs(tmp_path, boxed, inset)
    assert not any(p.startswith("depth") for p in ok), ok
    no_panel = copy.deepcopy(bp)
    no_panel["root"]["children"] = [c for c in no_panel["root"]["children"] if c["id"] != "zoom"]
    probs = _depth_probs(tmp_path, no_panel, [{"id": "csfm", "as": "inset", "why": "the mechanism the reader needs"}])
    assert any("no group has detail_of 'csfm'" in p for p in probs), probs
    probs = _depth_probs(tmp_path, bp, [{"id": "csfm", "as": "box", "why": "named only, details in the text"}])
    assert any("zooms into it" in p for p in probs) and any("open group" in p for p in probs), probs


def test_inline_module_with_many_parts_is_a_design_default(tmp_path, mini_bp):
    bp = copy.deepcopy(mini_bp)
    probs = _depth_probs(tmp_path, bp, [{"id": "csfm", "as": "inline", "why": "two parts on the main line"}], inner=6)
    assert any("plan:" not in p and "describes 6 parts" in p for p in probs), probs
    dev = {"rule": "plan:depth-inline", "why": "the author's own figure draws all six parts in place",
           "evidence": {"kind": "user-draft", "ref": "user-draft"}}
    p = brief_v2(depth=[{"id": "csfm", "as": "inline", "why": "two parts on the main line"}], deviations=[dev])
    probs = artifacts.validate("figure-plan", write(tmp_path, "p.json", p), blueprint=write(tmp_path, "bp.json", bp),
                               analysis=_analysis(tmp_path, 6), facts=write(tmp_path, "f.json", {"facts": FACTS}))
    assert not any("describes 6 parts" in x for x in probs)


def test_split_moves_only_the_own_figure_modules(tmp_path):
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(CORPUS / "restormer" / f, tmp_path / f)
    (tmp_path / "figure_plan.json").write_text(json.dumps({"depth": [
        {"id": "mdta", "as": "inset", "why": "the 2-minute mechanism", "panel": "mp"},
        {"id": "gdfn", "as": "own-figure", "why": "its own subsection", "panel": "gp", "section": "Sec. 3.2"}]}))
    from paperfig.split import split
    res = split(tmp_path / "blueprint.json", tmp_path / "parts")
    assert [Path(m).parent.name for m in res["modules"]] == ["module-gp"]
    ov = json.dumps(json.loads(Path(res["overview"]).read_text()))
    assert '"detail_of": "mdta"' in ov and '"detail_of": "gdfn"' not in ov and "(Fig. 2)" in ov


def test_a_zoom_inside_a_zoom_is_reported(tmp_path):
    """Restormer's corpus figure: the MDTA panel zooms into a box inside the 'Transformer Block' explainer panel,
    which no line ties to the overview — two zoom levels."""
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(CORPUS / "restormer" / f, tmp_path / f)
    r = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    found = [f for f in r.report.findings if f.code == "zoom-nested"]
    assert found and "tbx" in found[0].ids, [f.code for f in r.report.findings]
    (tmp_path / "pn").mkdir()
    for f in ("blueprint.json", "facts.json"):  # PointNet opens its panel straight from the overview: no finding
        shutil.copy(CORPUS / "pointnet" / f, tmp_path / "pn" / f)
    d = json.loads((tmp_path / "pn/blueprint.json").read_text())
    for a in d["root"]["children"]:
        if a.get("asset", {}).get("path"):
            a["asset"]["path"] = str(CORPUS / "pointnet" / a["asset"]["path"])
    (tmp_path / "pn/blueprint.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "pn/blueprint.json", "soft-pastel", out_dir=tmp_path / "o2", formats=())
    assert not [f for f in r.report.findings if f.code == "zoom-nested"]


def test_largest_hole_finds_the_blank_quadrant():
    fig = Box(0, 0, 400, 200)
    boxes = [Box(0, 0, 400, 90), Box(0, 100, 180, 100)]  # the bottom-right 220x100 is empty
    h = largest_hole(boxes, [], fig)
    assert 200 <= h.w <= 225 and 95 <= h.h <= 115 and h.x >= 175
    h2 = largest_hole(boxes, [[(300, 120), (300, 190)]], fig)  # a line through the region splits it
    assert h2.area < h.area * 0.7


def test_flat_module_and_hole_findings_on_built_figures(tmp_path):
    flat = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": [
                {"id": "mod", "title": "Module", "role": "proposed", "full_name": "Module", "layout": {"type": "row"},
                 "provenance": [{"source": "draft", "ref": "Sec. 3"}],
                 "children": [{"id": f"p{i}", "label": n, "role": "reused", "tone": "orange",
                               "provenance": [{"source": "draft", "ref": "Sec. 3"}]}
                              for i, n in enumerate(["LN", "MSA", "LN", "MLP"])]}]},
            "edges": [{"src": f"p{i}", "dst": f"p{i + 1}", "provenance": [{"source": "draft", "ref": "Sec. 3"}]}
                      for i in range(3)]}
    p = write(tmp_path, "flat.json", flat)
    r = P.build(p, "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert any(f.code == "module-flat" for f in r.report.findings), [f.code for f in r.report.findings]
    flat["root"]["children"][0]["children"][0]["tone"] = "gray"  # a routine part made light: the module has a hierarchy
    r = P.build(write(tmp_path, "flat2.json", flat), "soft-pastel", out_dir=tmp_path / "o2", formats=())
    assert not any(f.code == "module-flat" for f in r.report.findings)
    assert "hole" in r.report.stats


def test_build_makes_the_own_figure_modules_beside_the_overview(tmp_path):
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(CORPUS / "restormer" / f, tmp_path / f)
    (tmp_path / "figure_plan.json").write_text(json.dumps({"depth": [
        {"id": "mdta", "as": "inset", "why": "the 2-minute mechanism", "panel": "mp"},
        {"id": "gdfn", "as": "own-figure", "why": "its own subsection", "panel": "gp", "section": "Sec. 3.2",
         "figure": 4}]}))
    r = P.build_figures(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",), name="fig")
    assert (tmp_path / "o/fig.png").is_file() and (tmp_path / "o/fig-gp.png").is_file()
    assert r.report.stats["module_figures"] == ["fig-gp"]
    assert (tmp_path / "o/fig.blueprint.json").read_text() == (tmp_path / "blueprint.json").read_text()
    ov = (tmp_path / "o/parts/overview/blueprint.json").read_text()
    assert "(Fig. 4)" in ov and '"detail_of": "gdfn"' not in ov
    assert not [f for f in r.report.findings if f.severity == "error"], [f.message for f in r.report.findings if f.severity == "error"]


def test_split_without_own_figure_depth_still_splits_every_panel(tmp_path):
    """The split-size estimate (and a hand split) of a plan whose modules are all insets takes every panel."""
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(CORPUS / "restormer" / f, tmp_path / f)
    (tmp_path / "figure_plan.json").write_text(json.dumps({"depth": [
        {"id": "mdta", "as": "inset", "why": "the 2-minute mechanism", "panel": "mp"}]}))
    from paperfig.split import split
    assert len(split(tmp_path / "blueprint.json", tmp_path / "parts")["modules"]) == 2
