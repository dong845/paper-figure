"""Round-4 validation run (Latent Diffusion, single column): fixes for what the runner hit."""
import copy
import json

from conftest import MINI, PROV, leaf
from paperfig import artifacts
from paperfig import pipeline as P


def _bp(tmp_path, layout, width, n=3):
    nodes = [leaf(f"n{i}", f"Stage {i}", **({"cell": [i // 2, i % 2]} if layout == "grid" else {})) for i in range(n)]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": width},
         "root": {"id": "root", "layout": {"type": layout, "gap": "normal"}, "children": nodes},
         "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    return tmp_path / "blueprint.json"


def test_single_column_judged_against_a_column_not_a_page(tmp_path):
    """A single-column overview cannot reach w/h 2.3 at the 7 pt floor; only a tower is flagged there."""
    from paperfig.grammar import aspect_floor
    assert aspect_floor("single", 1.5) < 1.0 < aspect_floor("double", 1.5)
    res = P.build(_bp(tmp_path, "grid", "single", 4), "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    assert "aspect-tall" not in {f.code for f in res.report.findings}  # a 2×2 block in a column is fine


def test_compact_recipe_for_column_width():
    from paperfig.styles import compose, load_recipe
    base, comp = load_recipe("soft-pastel"), compose("soft-pastel", {"spacing": "compact", "typography": "compact"})
    assert comp["spacing"]["min_node_w"] < base["spacing"]["min_node_w"]
    assert comp["spacing"]["gap"]["normal"] < base["spacing"]["gap"]["normal"]
    assert comp["typography"]["small_size"] >= comp["typography"]["size"] - 0.5  # no smaller-than-body text


def test_infer_only_dash_survives_column_width():
    from paperfig.styles import load_recipe
    for rid in ("soft-pastel", "depth-cv"):
        nums = [float(x) for x in load_recipe(rid)["edges"]["infer_only"]["dash"].split()]
        assert min(nums[1::2]) >= 3.5 and max(nums[0::2]) >= 7, (rid, nums)  # gaps a print can show


def test_edge_unstated_resolves_drawn_as():
    from paperfig.blueprint import load
    from paperfig.consistency import check_against_analysis
    bp = load(copy.deepcopy(MINI))
    an = {"components": [{"id": "inp"}, {"id": "embed"}, {"id": "enc"}],
          "data_flow": [{"from": "inp", "to": "embed"}, {"from": "embed", "to": "enc"}]}
    eid = next(e.id for e in bp.edges if e.src == "inp")
    plan = {"drawn_as": [{"ids": ["embed"], "on_edge": eid, "how": "label"}]}
    codes = [f for f in check_against_analysis(bp, an, None, plan) if f.code == "edge-unstated" and "inp" in f.ids]
    assert not codes


def test_proposed_name_reads_subscripts_as_part_of_the_symbol():
    from paperfig.consistency import _tokens
    assert _tokens("UNet εθ") <= _tokens("time-conditional<br>UNet ε<sub>θ</sub>")


def test_fact_scope_must_contain_both_ends(tmp_path):
    from test_artifacts import TEXT, draft
    an = draft()
    an["components"][2]["parent"] = None
    an["data_flow"].append({"from": "embed", "to": "mdta", "label": None, "kind": "data",
                            "provenance": {"ref": "Sec. 3", "quote": "Restormer first applies a convolution"}})
    a = tmp_path / "a.json"
    a.write_text(json.dumps(an))
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"facts": [{"id": "f1", "from": "embed", "to": "mdta", "quote": "first applies a convolution",
                                        "ref": "Sec. 3", "scope": "mdta"}]}))
    t = tmp_path / "m.txt"
    t.write_text(TEXT)
    assert any("scope" in p and "embed" in p for p in artifacts.validate("facts", f, text=t, analysis=a))


def test_derived_style_names_itself(tmp_path):
    from paperfig.styles import derive_style
    cards = tmp_path / "c"
    cards.mkdir()
    (cards / "a.json").write_text(json.dumps({"id": "a", "measured": {"palette": [{"hex": "#2a9d8f", "share": 0.2, "neutral": False}]}}))
    out = derive_style("soft-pastel", cards, tmp_path / "style.json")
    d = json.loads(out.read_text())
    assert "derived" in d["name"].lower() and d["id"] != "soft-pastel"
