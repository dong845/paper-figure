"""TWM run: a one-sided penalty (thresholded entropy loss on the policy) could only be drawn as a loss that
"compares both ends". Edge heads "end" draws one arrowhead at the target and the legend says so."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells


def _build(tmp_path, heads):
    kids = [leaf("pi", "Policy"), leaf("h", "Entropy loss", role="loss"), leaf("v", "Critic"), leaf("lv", "Value loss", role="loss")]
    e1 = {"src": "h", "dst": "pi", "kind": "loss", "provenance": copy.deepcopy(PROV)}
    if heads:
        e1["heads"] = heads
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [e1, {"src": "v", "dst": "lv", "kind": "loss", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    return parse_cells(r.drawio.read_text()), r


def test_a_one_sided_loss_has_one_head_and_its_own_legend_entry(tmp_path):
    c, r = _build(tmp_path, "end")
    one = next(v for v in c.values() if v.edge and v.source == "pf-h")
    both = next(v for v in c.values() if v.edge and v.source == "pf-v")
    assert one.style.get("startArrow", "none") == "none" and one.style.get("endArrow", "none") != "none"
    assert both.style.get("startArrow", "none") != "none"
    texts = " ".join(v.value for k, v in c.items() if k.startswith("pfdeco-legend"))
    assert "loss (one-sided)" in texts and "loss (compares both ends)" in texts, texts
    assert not [f for f in r.report.findings if f.severity == "error"], r.report.findings


def test_without_heads_a_loss_still_compares_both_ends(tmp_path):
    c, _ = _build(tmp_path, None)
    e = next(v for v in c.values() if v.edge and v.source == "pf-h")
    assert e.style.get("startArrow", "none") != "none"
    texts = " ".join(v.value for k, v in c.items() if k.startswith("pfdeco-legend"))
    assert "one-sided" not in texts


def _row(tmp_path, label):
    tmp_path.mkdir(parents=True, exist_ok=True)
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": [leaf("s", "Sampler"), leaf("o", "Frames")]},
         "edges": [{"src": "s", "dst": "o", "label": label, "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    return P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())


def test_a_label_that_holds_a_gap_open_is_named(tmp_path):
    """TWM run: one edge label made the figure 1091 px wide instead of 709 and the lint named only a canvas column."""
    r = _row(tmp_path / "long", "N sequences of length l sampled with balanced weights")
    assert any(f.code == "gap-by-label" for f in r.report.findings), [f.code for f in r.report.findings]
    r = _row(tmp_path / "short", "x")
    assert not any(f.code == "gap-by-label" for f in r.report.findings)


def test_a_tone_legend_names_each_colour_the_figure_uses(tmp_path):
    """VS-Net blind run: the critic's one high issue — orange vs green meant something, and only the plan said what."""
    kids = [leaf("db", "Denoiser", tone="orange"), leaf("dc", "Data consistency", tone="green"), leaf("x", "Output")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double", "tone_legend": True},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [{"src": "db", "dst": "dc", "provenance": copy.deepcopy(PROV)}, {"src": "dc", "dst": "x", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    plan = tmp_path / "figure_plan.json"
    plan.write_text(json.dumps({"color_semantics": {"orange": "learned block", "green": "closed-form step", "blue": "unused"}}))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=(), plan_path=plan)
    c = parse_cells(r.drawio.read_text())
    texts = " ".join(v.value for k, v in c.items() if k.startswith("pfdeco-legend"))
    assert "learned block" in texts and "closed-form step" in texts and "unused" not in texts, texts
    assert sum(1 for k in c if k.startswith("pfdeco-legend") and k.endswith("-tone")) == 2


def test_outline_highlight_reaches_proposed_panels(tmp_path):
    """SimCSE blind run: highlight "outline" changed only boxes; two proposed panels still filled the figure orange."""
    panel = {"id": "pa", "title": "(a) Ours", "role": "proposed", "full_name": "Ours", "provenance": copy.deepcopy(PROV),
             "layout": {"type": "row"}, "children": [leaf("e", "Encoder")]}
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double", "highlight": "outline"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": [leaf("x", "Input"), panel]},
         "edges": [{"src": "x", "dst": "e", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    assert c["pf-pa"].style["fillColor"].lower() == "#ffffff"
