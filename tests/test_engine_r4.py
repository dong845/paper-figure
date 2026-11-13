"""Round 4 engine fixes: per-cell token shades (GAT's unequal α), conditional bar, text tone, glyph accent switch."""
import base64
import copy
import json

from conftest import PROV, leaf
from paperfig import color
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.markup import to_html


def _build(tmp_path, nodes, style="soft-pastel"):
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
         "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", style, out_dir=tmp_path / "o", formats=("png",))
    return res, parse_cells(res.drawio.read_text())


def test_token_values_shade_cells(tmp_path):
    res, cells = _build(tmp_path, [leaf("a", "α<sub>ij</sub>", visual="tokens", tokens=4, values=[0.1, 0.9, 0.4, 0.2]),
                                   leaf("b", "Sum")])
    L = [color.lab(cells[f"pfdeco-a-tok{k}"].style["fillColor"])[0] for k in range(4)]
    assert L[1] < L[2] < L[3] < L[0], L  # higher value = darker cell


def test_conditional_bar_is_a_math_bar():
    assert "p(z∣x)" in to_html("p(z|x)") and "p<sub>η</sub>(z∣x)" in to_html("p<sub>η</sub>(z|x)")
    assert "a | b" in to_html("a | b")  # a plain separator outside parentheses stays


def test_text_node_honours_tone(tmp_path):
    res, cells = _build(tmp_path, [leaf("a", "Encoder"), leaf("t", "masked attention", visual="text", tone="teal")])
    from paperfig.styles import load_recipe
    assert cells["pf-t"].style["fontColor"].lower() == load_recipe("soft-pastel")["palette"]["tones"]["teal"]["font"].lower()


def test_glyph_accent_switch(tmp_path):
    res, cells = _build(tmp_path, [leaf("g", "node i", visual="glyph", glyph="graph", accent=False), leaf("b", "Layer")])
    svg = base64.b64decode(cells["pf-g"].style["image"].split(",", 1)[1]).decode()
    from paperfig.styles import load_recipe
    pal = load_recipe("soft-pastel")["palette"]
    assert pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"].lower() not in svg.lower()


def test_legend_without_free_spot_goes_to_a_right_column_not_a_bottom_band():
    """The user rejected the bottom-band legend; when the figure has no empty spot, a right-hand column comes first
    (it also keeps the figure wide)."""
    from paperfig.blueprint import load
    from paperfig.geometry import Box
    from paperfig.legend import build
    from paperfig.styles import load_recipe
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double", "legend": "auto"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [
             leaf("a", "A", role="proposed", full_name="A"), leaf("b", "B", badges=["frozen"])]},
         "edges": [{"src": "a", "dst": "b", "kind": "skip", "provenance": copy.deepcopy(PROV)}]}
    fig = Box(0, 0, 400, 200)
    lg = build(load(d), load_recipe("soft-pastel"), fig, obstacles=[fig])  # every spot taken
    assert lg is not None and lg.box.x >= fig.right and lg.box.y <= fig.y + 1, lg.box
    assert len({round(it.text.y) for it in lg.items}) == len(lg.items)  # one item per row: a column


def test_edge_label_with_script_gets_room(tmp_path):
    """GAT/LDM: a subscript in an edge label (W_V) touched its own line — the knockout must cover the script."""
    nodes = [leaf("a", "A"), leaf("b", "B")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "loose"}, "children": nodes},
         "edges": [{"src": "a", "dst": "b", "label": "W<sub>V</sub>", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    st = next(c.style for c in parse_cells(res.drawio.read_text()).values() if c.edge and "W" in (c.value or ""))
    assert float(st.get("spacingBottom", 0)) >= 2 and float(st.get("spacingTop", 0)) >= 1, st


def test_legend_labels_can_be_renamed():
    """GAT/ControlNet: 'control / conditioning' and 'proposed (ours)' were fixed texts (F34, F81)."""
    from paperfig.blueprint import load
    from paperfig.legend import _wanted
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double",
                                         "legend_labels": {"proposed": "ours", "control": "attention mask"}},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf("a", "A", role="proposed", full_name="A"), leaf("b", "B")]},
         "edges": [{"src": "a", "dst": "b", "kind": "control", "provenance": copy.deepcopy(PROV)}]}
    labels = {k: lab for _, k, lab in _wanted(load(d))}
    assert labels["proposed"] == "ours" and labels["control"] == "attention mask"


def test_inner_bracket_sits_between_rows(tmp_path):
    """Brackets could only sit in the outer lanes (F39/F80); `placement: inner` names an inner row in place."""
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "loose"}, "children": [
             leaf("a", "Encoder", cell=[0, 0]), leaf("b", "Decoder", cell=[0, 1]),
             leaf("c", "Copy A", role="proposed", full_name="Copy A", cell=[1, 0]), leaf("e", "Copy B", role="proposed", full_name="Copy B", cell=[1, 1])]},
         "edges": [{"src": "a", "dst": "b", "provenance": copy.deepcopy(PROV)}, {"src": "c", "dst": "e", "provenance": copy.deepcopy(PROV)}],
         "annotations": [{"id": "ctrl", "kind": "bracket", "covers": ["c", "e"], "label": "trainable copy", "side": "top", "placement": "inner"}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    cells = parse_cells(res.drawio.read_text())
    lab = cells["pfdeco-ann-ctrl-label"].box
    assert cells["pf-a"].box.bottom <= lab.y and lab.bottom <= cells["pf-c"].box.y, (lab, cells["pf-a"].box, cells["pf-c"].box)
    assert not [f for f in res.report.findings if f.code == "bracket-spans-uncovered"]  # the row above is not "inside"
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]


def test_inner_bracket_without_room_fails_loudly(tmp_path):
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "tight"}, "children": [
             leaf("a", "Encoder", cell=[0, 0]), leaf("b", "Decoder", cell=[0, 1]),
             leaf("c", "Copy A", cell=[1, 0]), leaf("e", "Copy B", cell=[1, 1])]},
         "edges": [{"src": "a", "dst": "b", "provenance": copy.deepcopy(PROV)}, {"src": "c", "dst": "e", "provenance": copy.deepcopy(PROV)}],
         "annotations": [{"id": "ctrl", "kind": "bracket", "covers": ["c", "e"], "label": "a long bracket label here", "side": "top", "placement": "inner"}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    assert any(f.severity == "error" and "ctrl" in f.ids for f in res.report.findings), [f.code for f in res.report.findings]
