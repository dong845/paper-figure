"""Round 8 blind runs (Swin, DreamerV3): small fixes for what the runners hit."""
import copy
import json

import pytest

from conftest import MINI, PROV, leaf
from paperfig import pipeline as P


def test_glued_children_are_not_uneven_gaps(tmp_path):
    kids = [leaf(f"c{i}", f"x{i}", visual="chip") for i in range(5)]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column"}, "children": [
             {"id": "g", "layout": {"type": "column", "gap": "none"}, "frame": "none", "children": kids,
              "provenance": copy.deepcopy(PROV)}, leaf("n", "Next")]},
         "edges": [{"src": "g", "dst": "n", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert not [f for f in r.report.findings if f.code == "gap-uneven" and "g" in f.ids]


def test_nbsp_is_a_space_not_text():
    from paperfig.markup import to_html
    assert "&nbsp;" not in to_html("Swin&nbsp;Transformer") and " " in to_html("Swin&nbsp;Transformer")


def test_unknown_entities_are_rejected():
    from paperfig.blueprint import load
    from paperfig.errors import BlueprintError
    d = copy.deepcopy(MINI)
    d["root"]["children"][1]["label"] = "Enc&thinsp;oder"
    with pytest.raises(BlueprintError, match="entity"):
        load(d)


def test_sketch_accepts_a_proposed_role_without_a_name(tmp_path):
    from paperfig.sketch import _fill
    from paperfig.blueprint import load
    sk = {"root": {"id": "root", "layout": {"type": "row"},
                   "children": [{"id": "a", "label": "Encoder"}, {"id": "b", "label": "Our block", "role": "proposed"}]},
          "edges": [{"src": "a", "dst": "b"}]}
    load(_fill(sk))


def test_split_message_does_not_round_below_the_floor_up_to_it():
    from paperfig.pipeline import _fmt_pt
    assert _fmt_pt(6.96) == "6.96" and _fmt_pt(6.5) == "6.5"


def test_math_labels_get_room_to_stay_on_one_line(tmp_path):
    """Swin run: pure-TeX labels in no-wrap containers ('$\\frac{H}{4}\\times\\frac{W}{4}\\times C$' under a tensor,
    '$h_t \\in \\mathbb{R}^{d \\times n}$' on an arrow) were broken by MathJax at every operator. Each gets an inline
    block as wide as its measured text; lint reads the label as before."""
    from paperfig.drawio import parse_cells
    from paperfig.measure import measure
    lab = "$\\frac{H}{4}\\times\\frac{W}{4}\\times C$"
    kids = [leaf("a", "Stem"), leaf("t", lab, visual="tensor"), leaf("b", "Stage 1")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": kids},
         "edges": [{"src": "a", "dst": "t", "provenance": copy.deepcopy(PROV)},
                   {"src": "t", "dst": "b", "label": "$h_t \\in \\mathbb{R}^{d \\times n}$", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    cells = parse_cells(r.drawio.read_text())
    import re as _re
    for c in (cells["pf-t"], next(v for v in cells.values() if v.edge and v.source == "pf-t")):
        m = _re.search(r"min-width:(\d+)px", c.value)
        assert m and int(m.group(1)) > 20  # an explicit width for MathJax to lay the formula out in
    assert not [f for f in r.report.findings if f.code in ("text-overflow", "overlap") and f.severity != "info"]


def test_a_fact_drawn_on_the_edge_into_its_target_group_is_covered():
    """DreamerV3 run: reward drawn on the arrow env → p1 (p1 inside 'agent'): fact reward → agent was missing,
    because the search started at p1 — already inside the goal — and only looked onward."""
    from paperfig.blueprint import load
    from paperfig.facts import check_facts
    d = copy.deepcopy(MINI)
    d["edges"].append({"id": "e_x", "src": "inp", "dst": "gf", "label": "x", "provenance": copy.deepcopy(PROV)})
    bp = load(d)
    f = [{"id": "x->csfm", "from": "x", "to": "csfm", "quote": "q", "ref": "Sec. 3"}]
    out = check_facts(bp, f, None, [{"ids": ["x"], "on_edge": "e_x", "how": "label on the arrow into gf"}])
    assert out[0].code == "fact-covered", out[0].message


def test_a_proposed_group_may_be_named_by_its_bracket():
    """Swin run: the name had to sit in the frame title, so outside edges crossed it; a bracket label that covers
    the group names it just as well (and keeps the frame top free)."""
    from paperfig.blueprint import load
    from paperfig.errors import BlueprintError
    d = copy.deepcopy(MINI)
    g = d["root"]["children"][2]
    g.pop("title")
    g["frame"] = "none"
    with pytest.raises(BlueprintError, match="bracket"):
        load(copy.deepcopy(d))
    d["annotations"] = [{"id": "nm", "kind": "bracket", "covers": ["csfm"], "label": "Cross-Scale Fusion Module (CSFM)"}]
    load(d)


def test_bracket_named_group_builds_without_name_errors(tmp_path):
    d = copy.deepcopy(MINI)
    g = d["root"]["children"][2]
    g.pop("title")
    g["frame"] = "dashed"
    d["annotations"] = [{"id": "nm", "kind": "bracket", "covers": ["csfm"], "label": "Cross-Scale Fusion Module (CSFM)"}]
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert not [f for f in r.report.findings if "name" in f.code and f.severity != "info"], \
        [(f.code, f.message) for f in r.report.findings if "name" in f.code]


def test_copies_use_the_shortest_path_between_them():
    """DreamerV3 run: an encoder drawn once per time step (drawn_as into [enc1, enc2]) and a sequence model per step;
    the gate took the first copy pair with any path — around the env loop — and called the fact reversed."""
    from paperfig.blueprint import load
    from paperfig.facts import check_facts
    ids = ["enc1", "seq1", "enc2", "seq2", "env"]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf(i, i) for i in ids]},
         "edges": [{"src": a, "dst": b, "provenance": copy.deepcopy(PROV)} for a, b in
                   (("enc1", "seq1"), ("seq1", "enc2"), ("enc2", "seq2"), ("seq2", "env"), ("env", "enc1"))]}
    bp = load(d)
    plan = [{"ids": ["encoder"], "into": ["enc2", "enc1"], "how": "one per step"},
            {"ids": ["seq_model"], "into": ["seq1", "seq2"], "how": "one per step"}]
    f = [{"id": "e->s", "from": "encoder", "to": "seq_model", "quote": "q", "ref": "Sec. 3"}]
    out = check_facts(bp, f, None, plan)
    assert out[0].code == "fact-covered", out[0].message


def _losses(tmp_path, n_loss, contribution_ids=()):
    kids = [leaf("x", "Input"), leaf("m", "Model"), leaf("y", "Output")] + \
           [leaf(f"l{i}", f"Loss {i}", role="loss") for i in range(n_loss)]
    edges = [{"src": "x", "dst": "m"}, {"src": "m", "dst": "y"}] + \
            [{"src": "y", "dst": f"l{i}", "kind": "loss"} for i in range(n_loss)]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": kids},
         "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    if contribution_ids:
        (tmp_path / "figure_plan.json").write_text(json.dumps({"contributions": [
            {"name": "our loss", "solves": "s", "shown_by": "b", "ids": list(contribution_ids)}]}))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    return [f for f in r.report.findings if f.code == "loss-heavy"]


def test_an_overview_full_of_losses_is_flagged(tmp_path):
    """STORM / DreamerV3 reruns: 5 and 3 loss boxes, 9 and 8 loss arrows, where the authors' overviews show the
    prediction outputs and no loss box at all (corpus overviews: at most 1 loss box, 3 loss arrows)."""
    assert not _losses(tmp_path / "a", 1)
    hit = _losses(tmp_path / "b", 3)
    assert hit and hit[0].severity == "warn" and "prediction" in hit[0].message
    assert not _losses(tmp_path / "c", 3, contribution_ids=["l0", "l1", "l2"])  # the losses are the contribution
    # a contribution that merely feeds a loss (the model, the output) does not excuse the loss boxes
    assert _losses(tmp_path / "d", 3, contribution_ids=["y", "m"])


def test_caption_free_is_read_where_the_critic_puts_it(tmp_path):
    """DreamerV3 run: the critic wrote reader.levels.caption_free; run round wanted reader.caption_free."""
    from paperfig import run
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    (d / "figure_plan.json").write_text(json.dumps({"brief_version": 2}))
    lint = {"ok": True, "counts": {"error": 0, "warn": 0, "info": 0}, "stats": {}, "findings": []}
    (d / "build" / "r1").mkdir()
    (d / "build" / "r1" / "fig.lint.json").write_text(json.dumps(lint))
    reader = {"takeaway_from_png": "t", "top_level_units": 3, "levels": {"glance": "g", "contribution": "c", "mechanism": "m",
                                                   "caption_free": True}}
    (d / "critic" / "r1.json").write_text(json.dumps({"viewed_png": True, "scores": {}, "issues": [], "io_audit": [],
                                                      "reader": reader}))
    run.record_round(d, 1, d / "build/r1/fig.lint.json", d / "critic" / "r1.json", "first")


def test_sketch_group_label_is_its_title():
    from paperfig.blueprint import load
    from paperfig.sketch import _fill
    sk = {"root": {"id": "root", "layout": {"type": "row"}, "children": [
        {"id": "g", "label": "World model", "layout": {"type": "row"}, "children": [{"id": "a", "label": "Enc"}]},
        {"id": "b", "label": "Actor"}]}, "edges": [{"src": "g", "dst": "b"}]}
    bp = load(_fill(sk))
    assert bp.index["g"].title == "World model"


def test_neutral_tones_are_not_reported_unused(tmp_path):
    d = copy.deepcopy(MINI)
    d["root"]["children"][0]["tone"] = "gray"
    d["root"]["children"][1]["tone"] = "purple"
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    (tmp_path / "figure_plan.json").write_text(json.dumps({"color_semantics": {"gray": "inputs", "green": "decoder",
                                                                                "orange": "ours"}}))
    r = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    f = next(f for f in r.report.findings if f.code == "tone-undeclared")
    assert "purple" in f.message and "never drawn: gray" not in f.message
