"""Blind runs 2026-11-14 on SimCSE, GraphSAGE and VS-Net: engine bugs they hit."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import name_shown
from paperfig.drawio import parse_cells


def test_a_tex_name_is_found_in_its_drawn_label():
    """VS-Net: validate passed "Stage $n_{it}$", the build's lint failed it (drawn as \\(n_{it}\\))."""
    assert name_shown(r"Stage \(n_{it}\)", "Stage $n_{it}$")
    assert not name_shown("Stage 1", "Stage $n_{it}$")


def test_placeholder_labels_take_markup(tmp_path):
    """VS-Net: a placeholder printed 'input<br>m0' literally."""
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [
             leaf("img", "input<br>scan", visual="placeholder", asset={"spec": "an MR slice", "status": "placeholder"}),
             leaf("n", "Net")]},
         "edges": [{"src": "img", "dst": "n", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    v = parse_cells(r.drawio.read_text())["pf-img"].value
    assert "&lt;br" not in v and "<br" in v, v


def test_a_loss_drawn_as_a_contributed_group_is_not_loss_heavy(tmp_path):
    """SimCSE: the contrastive objective drawn as a grid (a group listed in contributions) kept loss-heavy alive."""
    cells = [leaf(f"c{i}", f"s{i}", role="loss") for i in range(3)]
    grid = {"id": "obj", "frame": "none", "layout": {"type": "row", "gap": "none"}, "children": cells}
    kids = [leaf(f"h{i}", f"h{i}") for i in range(3)] + [grid]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [{"src": f"h{i}", "dst": f"c{j}", "kind": "loss", "provenance": copy.deepcopy(PROV)}
                   for i in range(3) for j in range(2)]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    plan = tmp_path / "figure_plan.json"
    plan.write_text(json.dumps({"contributions": [{"ids": ["obj"], "what": "the contrastive objective"}]}))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=(), plan_path=plan)
    from paperfig.grammar import check_grammar
    from paperfig.blueprint import load
    from paperfig.styles import load_recipe
    found = check_grammar(load(tmp_path / "b.json"), r.drawio, load_recipe("soft-pastel"), json.loads(plan.read_text()))
    assert not [f for f in found if f.code == "loss-heavy"], [f.message for f in found if f.code == "loss-heavy"]


def test_sketch_names_a_marked_up_label_the_way_the_check_reads_it(tmp_path):
    """GraphSAGE: sketch named AGGREGATE<sub>k</sub> 'AGGREGATE k' and then failed its own name check."""
    from paperfig.sketch import make_sketches
    sk = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
          "root": {"id": "root", "layout": {"type": "row"}, "children": [
              {"id": "a", "label": "Sampler"}, {"id": "g", "label": "AGGREGATE<sub>k</sub>", "role": "proposed"}]},
          "edges": [{"src": "a", "dst": "g"}]}
    (tmp_path / "c1.json").write_text(json.dumps(sk))
    res = make_sketches([tmp_path / "c1.json"], tmp_path / "out")
    assert res["concepts"][0]["concept"] == "c1"
