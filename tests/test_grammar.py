"""Round 3: visual-grammar lint from the user's design guide (one meaning per colour, recurring symbols, a
grayscale-safe highlight, at most two zoom-ins)."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.grammar import gray_highlight


def test_gray_highlight_flagged():
    # light orange vs light blue: different hues, nearly the same grey
    msg = gray_highlight([{"fillColor": "#fde3cf", "strokeWidth": "1.2"}], [{"fillColor": "#dce8f7", "strokeWidth": "1.2"}])
    assert msg and "grayscale" in msg


def test_gray_highlight_cue_accepted():
    prop, reused = {"fillColor": "#fde3cf", "strokeWidth": "1.2"}, {"fillColor": "#dce8f7", "strokeWidth": "1.2"}
    assert gray_highlight([dict(prop, strokeWidth="2.4")], [reused]) is None  # heavier outline
    assert gray_highlight([dict(prop, fontStyle="1")], [dict(reused, fontStyle="0")]) is None  # bold name
    assert gray_highlight([{"fillColor": "#f4a261"}], [{"fillColor": "#f1f3f5"}]) is None  # lightness differs


def _build(tmp_path, nodes, plan):
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
         "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    (tmp_path / "figure_plan.json").write_text(json.dumps(plan))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    return {f.code: f for f in res.report.findings}


def test_key_rep_consistency(tmp_path):
    nodes = [leaf("p1", "Proto", tone="purple"), leaf("m", "Model", role="proposed", full_name="Model"),
             leaf("p2", "Proto", tone="teal")]
    codes = _build(tmp_path, nodes, {"key_representations": [{"name": "prototype", "ids": ["p1", "p2"]}]})
    assert "key-rep-inconsistent" in codes and "p2" in codes["key-rep-inconsistent"].ids
    nodes[2]["tone"] = "purple"
    assert "key-rep-inconsistent" not in _build(tmp_path, nodes, {"key_representations": [{"name": "prototype", "ids": ["p1", "p2"]}]})


def test_tone_semantics(tmp_path):
    nodes = [leaf("a", "Encoder", role="reused", tone="blue"), leaf("m", "Fusion", role="proposed", full_name="Fusion", tone="blue"),
             leaf("c", "Head", role="reused", tone="green")]
    codes = _build(tmp_path, nodes, {"color_semantics": {"blue": "network blocks"}})
    assert "tone-undeclared" in codes and "green" in codes["tone-undeclared"].message
    assert "tone-two-meanings" in codes and "blue" in codes["tone-two-meanings"].message


def test_gray_highlight_bold_markup_is_a_cue():
    """BLIP-2: 'Q-Former' is bold through <b> markup in the label, not through fontStyle."""
    prop, reused = {"fillColor": "#fde3cf", "strokeWidth": "1.2"}, {"fillColor": "#dce8f7", "strokeWidth": "1.2"}
    assert gray_highlight([prop], [reused], prop_values=["<b>Q-Former</b><br>Querying Transformer"],
                          reused_values=["Image<br>Encoder"]) is None
