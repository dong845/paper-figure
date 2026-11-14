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


def _grammar(tmp_path, d, plan):
    from paperfig.blueprint import load
    from paperfig.grammar import check_grammar
    from paperfig.styles import load_recipe
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    return check_grammar(load(tmp_path / "b.json"), r.drawio, load_recipe("soft-pastel"), plan)


def _fig(kids, edges):
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
            "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}


def test_a_routine_loss_is_named_unless_it_is_a_contribution(tmp_path):
    """User 2026-11-14: a conventional loss need not be drawn; draw it when it is new or part of the contribution."""
    d = _fig([leaf("net", "Net", role="proposed", full_name="Net"), leaf("mse", "MSE", role="loss")],
             [{"src": "net", "dst": "mse", "kind": "loss", "heads": "end"}])
    found = _grammar(tmp_path / "a", d, {"contributions": [{"ids": ["net"], "what": "the network"}]})
    assert any(f.code == "loss-conventional" and "mse" in f.ids for f in found)
    found = _grammar(tmp_path / "b", d, {"contributions": [{"ids": ["net", "mse"], "what": "a new loss"}]})
    assert not any(f.code == "loss-conventional" for f in found)


def test_symbols_on_every_arrow_are_counted(tmp_path):
    """User on VS-Net: intermediate variables (m, u, x) on the arrows added clutter."""
    kids = [leaf(f"b{i}", f"Block {i}") for i in range(5)]
    edges = [{"src": f"b{i}", "dst": f"b{i+1}", "label": f"$m^{i}$"} for i in range(4)]
    found = _grammar(tmp_path, _fig(kids, edges), {})
    assert any(f.code == "symbol-heavy" for f in found)


def test_mri_glyphs_draw_and_must_be_marked_illustrative(tmp_path):
    """VS-Net blind run: input, mask and coil maps were placeholder boxes; procedural stand-ins now exist."""
    from paperfig.glyphs import glyph_svg
    for name, v in (("mr-image", "clean"), ("mr-image", "aliased"), ("sampling-mask", None), ("coil-maps", None)):
        s = glyph_svg(name, 56, 56, "#ccc", "#333", "#f00", variant=v)
        assert s.startswith("<svg") and "</svg>" in s
    d = _fig([leaf("x", "input", visual="glyph", glyph="mr-image", variant="aliased"), leaf("n", "Net")],
             [{"src": "x", "dst": "n"}])
    found = _grammar(tmp_path, d, {})
    assert any(f.code == "schematic-unmarked" for f in found)


def test_graph_neighbourhood_variants_draw():
    """User 2026-11-14: GraphSAGE's own figure (sample, aggregate on a toy graph) explains more than a pipeline."""
    from paperfig.glyphs import VARIANTS, glyph_svg
    for v in ("neighbourhood", "khop", "aggregate"):
        assert v in VARIANTS["graph"]
        s = glyph_svg("graph", 110, 100, "#ccc", "#333", "#e67e22", variant=v)
        assert s.count("<circle") >= 7
    assert "marker-end" in glyph_svg("graph", 110, 100, "#ccc", "#333", "#e67e22", variant="aggregate")


def test_new_data_glyphs_draw(tmp_path):
    """ISTA-Net / GraphSAINT blind runs: natural images, an induced subgraph, a GCN unrolled over it."""
    from paperfig.glyphs import VARIANTS, glyph_svg
    assert {"subgraph", "layers"} <= set(VARIANTS["graph"]) and "degraded" in VARIANTS["natural-image"]
    for name, v in (("natural-image", "clean"), ("natural-image", "degraded"), ("graph", "subgraph"), ("graph", "layers")):
        s = glyph_svg(name, 110, 90, "#ccc", "#333", "#e67e22", variant=v)
        assert s.startswith("<svg") and "</svg>" in s


def test_zero_valued_tokens_are_empty_and_undirected_links_have_no_heads(tmp_path):
    """ISTA-Net: sparse coefficients drew as faint tinted cells; GraphSAINT: a toy graph's links had to carry heads."""
    kids = [leaf("c", "coefficients", visual="tokens", tokens=4, values=[0.9, 0, 0.4, 0]), leaf("u", "u"), leaf("v", "v")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": kids},
         "edges": [{"src": "c", "dst": "u", "provenance": copy.deepcopy(PROV)},
                   {"src": "u", "dst": "v", "heads": "none", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    assert c["pfdeco-c-tok1"].style["fillColor"].lower() == "#ffffff" and c["pfdeco-c-tok0"].style["fillColor"].lower() != "#ffffff"
    link = next(v for v in c.values() if v.edge and v.source == "pf-u")
    assert link.style.get("endArrow") == "none" and link.style.get("startArrow", "none") == "none"
    assert not [f for f in r.report.findings if f.code == "edge-head-run"]
