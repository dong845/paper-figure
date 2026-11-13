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


def test_tone_semantics_uses_declared_tone_not_fill(tmp_path):
    """GAT/PointNet round 3: editorial-minimal paints blue, green, purple, … all #ffffff, so mapping fills back to
    tone names reported declared blue features as 'yellow' (F87/F93)."""
    nodes = [leaf("a", "Features", role="reused", tone="blue"), leaf("m", "Attention", role="proposed", full_name="Attention"),
             leaf("c", "Head", role="reused", tone="blue")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
         "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    from paperfig.styles import load_recipe
    proposed = load_recipe("editorial-minimal")["palette"]["roles"]["proposed"]["tone"]
    (tmp_path / "figure_plan.json").write_text(json.dumps({"color_semantics": {"blue": "features", proposed: "proposed"}}))
    res = P.build(tmp_path / "blueprint.json", "editorial-minimal", out_dir=tmp_path / "o", formats=("png",))
    assert not [f for f in res.report.findings if f.code in ("tone-undeclared", "tone-two-meanings")], \
        [f.message for f in res.report.findings if f.code.startswith("tone-")]


def test_style_tones_carry_colour():
    """User 2026-11-13: '颜色感觉不少都是白色或者单一颜色'. Measured: the styles' tone fills had chroma 6-9 at
    L* 94-97 (editorial-minimal: pure white), while the chromatic colours of 59 top-venue overview figures in the KB
    have median chroma 24 at L* 76. Chromatic tones must be visibly tinted; the proposed accent must be the strongest."""
    from paperfig import color
    from paperfig.styles import load_recipe
    for name in ("soft-pastel", "depth-cv", "editorial-minimal"):
        pal = load_recipe(name)["palette"]
        lab = {k: color.lab(v["fill"]) for k, v in pal["tones"].items() if isinstance(v, dict) and k not in ("gray", "grey")}
        chroma = {k: (a * a + b * b) ** 0.5 for k, (L, a, b) in lab.items()}
        assert all(chroma[k] >= 10 for k in chroma), (name, {k: round(v, 1) for k, v in chroma.items()})
        assert all(lab[k][0] <= 92 for k in lab), (name, {k: round(v[0], 1) for k, v in lab.items()})
        acc = pal["roles"]["proposed"]["tone"]
        assert chroma[acc] >= max(c for k, c in chroma.items() if k != acc) - 1e-6, (name, acc)


def test_washed_figure_and_tall_overview_flagged(tmp_path):
    nodes = [leaf("a", "Encoder"), leaf("b", "Fusion", role="proposed", full_name="Fusion"), leaf("c", "Decoder")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column", "gap": "normal"}, "children": nodes},
         "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    tall = [f for f in res.report.findings if f.code == "aspect-tall"]
    assert tall and "median" in tall[0].message and "KB cards" in tall[0].message  # a column of boxes is a tower
    d["root"]["layout"]["type"] = "row"
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o2", formats=("png",))
    assert not [f for f in res.report.findings if f.code == "aspect-tall"]
    from paperfig.grammar import washed_out
    assert washed_out(["#f3f4f6", "#e8f0fe", "#fff4ea"]) and not washed_out(["#f3f4f6", "#cfe0fb", "#fbd5b3"])


def test_group_area_is_lighter_than_its_elements():
    """After the palette retune, a proposed container filled with the full accent became a heavy orange block and
    its orange children lost contrast: an area is a lighter tint of the tone its elements carry."""
    from types import SimpleNamespace
    from paperfig import color
    from paperfig.styles import colors_for, load_recipe
    for name in ("soft-pastel", "depth-cv", "editorial-minimal"):
        r = load_recipe(name)
        g = SimpleNamespace(is_group=True, role="proposed", tone=None, frame="box", detail_of=None)
        leaf_ = SimpleNamespace(is_group=False, role="proposed", tone=None)
        gl, ll = color.lab(colors_for(r, g)[0])[0], color.lab(colors_for(r, leaf_)[0])[0]
        assert gl >= ll + 5, (name, gl, ll)
