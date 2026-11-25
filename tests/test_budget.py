"""Where the width comes from, and where the details come from (user, 2026-11-25: make the skill produce full,
well-sized figures on its own — the agent gets the instrument used by hand, and the text it needs)."""
import copy
import json

from conftest import PROV, leaf
from paperfig import artifacts
from paperfig import blueprint as B
from paperfig.budget import budget, hint
from paperfig.extract import extract_draft, method_section
from paperfig.styles import load_recipe


def _panel(id, kids, layout="column"):
    return {"id": id, "title": f"P {id}", "layout": {"type": layout}, "provenance": copy.deepcopy(PROV), "children": kids}


def test_budget_names_the_panel_its_peers_are_stretched_to_and_its_widest_part():
    wide = {"id": "pair", "frame": "none", "layout": {"type": "row"},
            "children": [leaf("p1", "<b>a fairly long name</b>"), leaf("p2", "<b>another long name</b>")]}
    bp = B.load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                 "root": {"id": "root", "layout": {"type": "row"},
                          "children": [_panel("a", [leaf("a1", "<b>a fairly long name and then some</b>"), leaf("a2", "y")]), _panel("b", [wide, leaf("b2", "z")])]},
                 "edges": []})
    b = budget(bp, load_recipe("soft-pastel"), 6.875)
    s = b["setters"][0]
    assert s["panel"] == "b" and s["peers"] == ["a"] and s["widest"][0][0] == "pair"
    assert "'b'" in hint(b) and b["width_for_floor"] > b["width_for_goal"]


def test_method_text_carries_the_implementation_details(tmp_path):
    md = tmp_path / "p.md"
    md.write_text("# 1 Introduction\nWhy.\n\n# 2 Method\nThe encoder reads the image.\n\n# 3 Experiments\n"
                  "Datasets are listed.\n\n## 3.1 Implementation Details\nWe use three rounds and a tolerance of 0.25.\n\n"
                  "## 3.2 Results\nNumbers.\n")
    text = method_section(extract_draft(md))
    assert "encoder reads" in text and "three rounds" in text and "Numbers." not in text


def test_component_details_are_quoted_from_the_text(tmp_path):
    src = tmp_path / "m.txt"
    src.write_text("The memory stores every view with its location and viewing parameters for later recall.")
    a = {"paper": {"title": None, "task": "the memory keeps views for recall"}, "assets": [], "unclear": [],
         "components": [{"id": "mem", "name": "Memory", "role": "proposed", "what": "stores views",
                         "details": [{"text": "location · params", "quote": "with its location and viewing parameters"},
                                     {"text": "made up", "quote": "a sentence the paper never wrote at all"}],
                         "provenance": {"ref": "Sec. 3", "quote": "The memory stores every view"}}],
         "data_flow": [], "stages": [], "losses": [], "train_vs_infer": [], "contributions": []}
    p = tmp_path / "a.json"
    p.write_text(json.dumps(a))
    probs = artifacts.validate("draft-analysis", p, text=src)
    assert any("details[1]" in x for x in probs) and not any("details[0]" in x for x in probs), probs
