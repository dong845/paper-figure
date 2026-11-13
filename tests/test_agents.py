"""Round 5: what agent papers need — a loop layout, text cards, icons."""
import copy
import json

import pytest

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.drawio import parse_cells


def _loop(hub=False, n=4):
    kids = [leaf(f"s{i}", ["Thought", "Action", "Observation", "Reflection", "Plan", "Memory"][i]) for i in range(n)]
    lay = {"type": "cycle", "gap": "loose"}
    if hub:
        kids.append(leaf("llm", "LLM", role="proposed", full_name="LLM"))
        lay["hub"] = "llm"
    edges = [{"src": f"s{i}", "dst": f"s{(i + 1) % n}", "provenance": copy.deepcopy(PROV)} for i in range(n)]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": lay, "children": kids}, "edges": edges}


def test_cycle_places_members_around_a_loop(tmp_path):
    bp = load(_loop())
    cells = {c.id: c.cell for c in bp.root.children}
    assert cells == {"s0": (0, 0), "s1": (0, 1), "s2": (1, 1), "s3": (1, 0)}  # clockwise: top L→R, bottom R→L
    (tmp_path / "blueprint.json").write_text(json.dumps(_loop(hub=True, n=5)))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    c = parse_cells(res.drawio.read_text())
    top = [c[f"pf-s{i}"].box for i in (0, 1, 2)]
    hub = c["pf-llm"].box
    assert all(b.bottom <= hub.y for b in top)  # the hub sits inside the loop, below the top row
    assert min(b.x for b in top) < hub.cx < max(b.right for b in top)
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]


def test_textcards_hold_prompts_code_and_messages(tmp_path):
    kids = [leaf("p", "<b>Thought:</b> I need the population of Paris.<br><b>Action:</b> search[Paris]", visual="textcard"),
            leaf("c", "result = search('Paris')<br>print(result)", visual="textcard", card_style="code"),
            leaf("m", "Could you check the date?", visual="textcard", card_style="bubble", tone="blue")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [{"src": "p", "dst": "c", "provenance": copy.deepcopy(PROV)}, {"src": "c", "dst": "m", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    c = parse_cells(res.drawio.read_text())
    assert c["pf-p"].style.get("align") == "left"
    assert "courier" in c["pf-c"].style.get("fontFamily", "").lower()
    assert c["pf-m"].style.get("shape") == "callout"
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]


def test_sketch_renders_concepts_side_by_side(tmp_path):
    from paperfig.sketch import make_sketches
    a = {"root": {"id": "root", "layout": {"type": "row"}, "children": [{"id": "x", "label": "Input"}, {"id": "m", "label": "Model"}, {"id": "y", "label": "Output"}]},
         "edges": [{"src": "x", "dst": "m"}, {"src": "m", "dst": "y"}]}
    b = {"root": {"id": "root", "layout": {"type": "cycle"}, "children": [{"id": "t", "label": "Thought"}, {"id": "a", "label": "Act"}, {"id": "o", "label": "Observe"}]},
         "edges": [{"src": "t", "dst": "a"}, {"src": "a", "dst": "o"}, {"src": "o", "dst": "t"}]}
    (tmp_path / "c1.json").write_text(json.dumps(a))
    (tmp_path / "c2.json").write_text(json.dumps(b))
    res = make_sketches([tmp_path / "c1.json", tmp_path / "c2.json"], tmp_path / "out")
    assert res["sheet"].is_file() and [r["concept"] for r in res["concepts"]] == ["c1", "c2"]
    assert res["concepts"][0]["aspect"] > res["concepts"][1]["aspect"]  # a row is wider than a loop
