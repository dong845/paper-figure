import copy
import random

import pytest
from PIL import Image

from paperfig.blueprint import load
from paperfig.layout import solve
from paperfig.styles import load_recipe
from paperfig import measure
from conftest import leaf, PROV

R = load_recipe("soft-pastel")
GAP = R["spacing"]["gap"]["normal"]


def row_bp(children, layout=None, edges=None):
    return {
        "schema_version": 1,
        "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
        "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
        "edges": edges or [],
    }


def gaps(placed, ids, axis="x"):
    out = []
    for a, b in zip(ids, ids[1:]):
        A, B = placed[a].footprint, placed[b].footprint
        out.append(B.x - A.right if axis == "x" else B.y - A.bottom)
    return out


def test_row_gaps_uniform():
    bp = load(row_bp([leaf("a", "A"), leaf("b", "Longer label"), leaf("c", "C")]))
    p = solve(bp, R)
    assert gaps(p, ["a", "b", "c"]) == pytest.approx([GAP, GAP])


def test_column_center_alignment():
    bp = load(row_bp([leaf("a", "A"), leaf("b", "A much longer label")], {"type": "column", "equalize": False}))
    p = solve(bp, R)
    assert p["a"].box.cx == pytest.approx(p["b"].box.cx)
    assert gaps(p, ["a", "b"], "y") == pytest.approx([GAP])


def test_row_start_alignment():
    bp = load(row_bp([leaf("a", "A"), leaf("b", "two<br>lines<br>tall")], {"type": "row", "align": "start", "equalize": False}))
    p = solve(bp, R)
    assert p["a"].box.y == pytest.approx(p["b"].box.y)


def test_equalize_heights_in_row():
    bp = load(row_bp([leaf("a", "A"), leaf("b", "two<br>lines")]))
    p = solve(bp, R)
    assert p["a"].box.h == pytest.approx(p["b"].box.h)


def test_equalize_widths_in_column():
    bp = load(row_bp([leaf("a", "A"), leaf("b", "A much longer label")], {"type": "column"}))
    p = solve(bp, R)
    assert p["a"].box.w == pytest.approx(p["b"].box.w)


def test_box_fits_measured_text():
    bp = load(row_bp([leaf("a", "A rather long module name")]))
    p = solve(bp, R)
    from paperfig.styles import _is_bold
    tw, th = measure.measure("A rather long module name", R["typography"]["size"], bold=_is_bold(R, load(row_bp([leaf("a", "x")])).index["a"]))
    assert p["a"].box.w >= tw + 2 * R["spacing"]["node_pad_x"] - 1e-6
    assert p["a"].box.h >= th + 2 * R["spacing"]["node_pad_y"] - 1e-6


def test_grid_columns_aligned():
    ch = [leaf("a", "A", cell=[0, 0]), leaf("b", "Bbbbbbbbbbbb", cell=[0, 1]), leaf("c", "Cccccccccccccccccc", cell=[1, 0]), leaf("d", "D", cell=[1, 1])]
    p = solve(load(row_bp(ch, {"type": "grid"})), R)
    assert p["a"].box.cx == pytest.approx(p["c"].box.cx)
    assert p["b"].box.cx == pytest.approx(p["d"].box.cx)
    assert p["a"].box.cy == pytest.approx(p["b"].box.cy)


def test_span_occupies_two_columns():
    ch = [leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[0, 1]), leaf("w", "Wide", cell=[1, 0], span=[1, 2])]
    p = solve(load(row_bp(ch, {"type": "grid", "equalize": False})), R)
    assert p["w"].box.cx == pytest.approx((p["a"].box.cx + p["b"].box.cx) / 2, abs=1)


def test_nested_group_contains_children_with_padding(mini_bp):
    bp = load(mini_bp)
    p = solve(bp, R)
    pad = R["spacing"]["group_pad"]
    g = p["csfm"].box
    for cid in ("msa", "gf"):
        c = p[cid].box
        assert c.x >= g.x + pad - 1e-6 and c.right <= g.right - pad + 1e-6 and c.bottom <= g.bottom - pad + 1e-6


def test_title_band_reserved(mini_bp):
    p = solve(load(mini_bp), R)
    t = p["csfm"].title_box
    assert t is not None
    for cid in ("msa", "gf"):
        assert p[cid].box.y >= t.bottom - 1e-6


def test_group_widened_for_long_title():
    g = {"id": "g", "title": "An extremely long container title that is wider than content", "layout": {"type": "row"},
         "children": [leaf("a", "A")]}
    p = solve(load(row_bp([g])), R)
    tw, _ = measure.measure(g["title"], R["typography"]["title_size"], bold=True)
    assert p["g"].box.w >= tw
    assert p["a"].box.cx == pytest.approx(p["g"].box.cx)


def test_gap_widened_for_edge_label():
    label = "concat + projection to C channels"
    e = [{"src": "a", "dst": "b", "label": label, "provenance": PROV}]
    p = solve(load(row_bp([leaf("a", "A"), leaf("b", "B")], edges=e)), R)
    lw, _ = measure.measure(label, R["typography"]["small_size"])
    assert gaps(p, ["a", "b"])[0] >= lw + 2 * R["spacing"]["edge_label_pad"] - 1e-6


def test_extreme_aspect_image_clamped(tmp_path):
    Image.new("RGB", (1, 20)).save(tmp_path / "thin.png")
    n = leaf("img", "", visual="image", asset={"path": "thin.png", "status": "provided"})
    p = solve(load(row_bp([n]), base_dir=tmp_path), R)
    b = p["img"].box
    assert b.w / b.h == pytest.approx(0.25)
    assert max(b.w, b.h) == pytest.approx(R["image"]["default_long_side"])


def test_image_keeps_aspect(tmp_path):
    Image.new("RGB", (300, 200)).save(tmp_path / "x.png")
    n = leaf("img", "Input", visual="image", asset={"path": "x.png", "status": "provided"})
    p = solve(load(row_bp([n]), base_dir=tmp_path), R)
    assert p["img"].box.w / p["img"].box.h == pytest.approx(1.5)
    assert p["img"].label_box.y >= p["img"].box.bottom


def test_requested_asset_box_fits_notice():
    n = leaf("img", "", visual="image", asset={"status": "requested", "spec": "low-quality input image from the test set"})
    p = solve(load(row_bp([n])), R)
    from paperfig.layout import placeholder_text
    tw, th = measure.measure(placeholder_text(load(row_bp([n])).index["img"]), R["typography"]["small_size"])
    assert p["img"].box.w >= tw and p["img"].box.h >= th


def test_tensor_label_below():
    n = leaf("t", "F<sub>1</sub>", visual="tensor")
    p = solve(load(row_bp([n])), R)
    assert p["t"].label_box.y >= p["t"].box.bottom
    assert p["t"].footprint.contains(p["t"].box) and p["t"].footprint.contains(p["t"].label_box)


def test_size_hint_cannot_shrink_below_text():
    p = solve(load(row_bp([leaf("a", "Transformer Block", size=[10, 10])])), R)
    tw, _ = measure.measure("Transformer Block", R["typography"]["size"], bold=True)
    assert p["a"].box.w >= tw


def test_size_hint_enlarges():
    p = solve(load(row_bp([leaf("a", "A", size=[200, 90])])), R)
    assert (p["a"].box.w, p["a"].box.h) == (200, 90)


def _random_tree(rng, depth, counter):
    kids = []
    for _ in range(rng.randint(1, 4)):
        counter[0] += 1
        i = counter[0]
        if depth < 3 and rng.random() < 0.3:
            kids.append({"id": f"g{i}", "title": rng.choice([None, "Stage", "A long group title here"]) or "",
                         "layout": {"type": rng.choice(["row", "column"]), "align": rng.choice(["start", "center", "end"]),
                                    "gap": rng.choice(["tight", "normal", "loose"])},
                         "frame": rng.choice(["box", "dashed", "none"]), "children": _random_tree(rng, depth + 1, counter)})
        else:
            vis = rng.choice(["box", "box", "op", "tensor", "text", "tokens"])
            n = leaf(f"n{i}", rng.choice(["A", "Encoder", "x<sub>t</sub>", "Two<br>lines", "特征融合模块", "⊕"]), visual=vis)
            if vis == "tokens":
                n["tokens"] = rng.randint(1, 8)
            kids.append(n)
    return kids


@pytest.mark.parametrize("seed", range(50))
def test_no_sibling_overlap_property(seed):
    rng = random.Random(seed)
    tree = _random_tree(rng, 0, [0])
    for g in tree:
        if "title" in g and not g["title"]:
            del g["title"]
    bp = load(row_bp(tree, {"type": rng.choice(["row", "column"])}))
    p = solve(bp, R)
    for g in bp.groups():
        kids = [p[c.id].footprint for c in g.children]
        for i in range(len(kids)):
            assert p[g.id].box.contains(kids[i], eps=1e-6)
            for j in range(i + 1, len(kids)):
                assert not kids[i].intersects(kids[j]), (g.id, g.children[i].id, g.children[j].id)


def test_axis_alignment_titled_group(mini_bp):
    p = solve(load(mini_bp), R)
    assert p["enc"].box.cy == pytest.approx(p["msa"].box.cy, abs=0.01)
    assert p["csfm"].axis[1] == pytest.approx(p["msa"].box.cy, abs=0.01)


def test_tensor_box_centers_align_in_row():
    bp = load(row_bp([leaf("t", "F<sub>1</sub>", visual="tensor"), leaf("b", "Block")]))
    p = solve(bp, R)
    assert p["t"].box.cy == pytest.approx(p["b"].box.cy, abs=0.01)
    assert p["root"].box.contains(p["t"].footprint, eps=1e-6)


def test_row_peer_widths_equalized(mini_bp):
    p = solve(load(mini_bp), R)
    assert p["msa"].box.w == pytest.approx(p["gf"].box.w)


def test_very_different_widths_not_equalized():
    p = solve(load(row_bp([leaf("a", "A"), leaf("b", "A considerably longer module label")])), R)
    assert p["b"].box.w > 1.6 * p["a"].box.w


def test_grid_row_gap_widened_for_vertical_edge_label():
    ch = [leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[1, 0])]
    e = [{"src": "a", "dst": "b", "label": "two<br>lines", "provenance": PROV}]
    p = solve(load(row_bp(ch, {"type": "grid"}, edges=e)), R)
    _, lh = measure.measure("two<br>lines", R["typography"]["small_size"])
    assert p["b"].box.y - p["a"].box.bottom >= lh + 2 * R["spacing"]["edge_label_pad"] - 1e-6


def test_grid_row_aligns_on_shape_centres(tmp_path):
    Image.new("RGB", (100, 100)).save(tmp_path / "x.png")
    ch = [leaf("img", "Caption under image", visual="image", asset={"path": "x.png", "status": "provided"}, cell=[0, 0]),
          leaf("b", "Block<br>two lines<br>three", cell=[0, 1])]
    p = solve(load(row_bp(ch, {"type": "grid"}), base_dir=tmp_path), R)
    assert p["img"].box.cy == pytest.approx(p["b"].box.cy, abs=0.01)


def test_badge_space_reserved(mini_bp):
    base = solve(load(mini_bp), R)["enc"].box.w
    mini_bp["root"]["children"][1]["badges"] = ["frozen"]
    with_badge = solve(load(mini_bp), R)["enc"].box.w
    assert with_badge > base


def test_grid_row_gap_widened_for_diagonal_edge_label():
    ch = [leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[1, 1])]
    e = [{"src": "a", "dst": "b", "label": "↓2", "provenance": PROV}]
    p = solve(load(row_bp(ch, {"type": "grid"}, edges=e)), R)
    _, lh = measure.measure("↓2", R["typography"]["small_size"])
    assert p["b"].box.y - p["a"].box.bottom >= lh + 2 * R["spacing"]["edge_label_pad"] - 1e-6


def test_group_axis_of_descendant_aligns_across_groups():
    g1 = {"id": "g1", "title": "Stage 1", "frame": "dashed", "axis_of": "a", "layout": {"type": "column"},
          "children": [leaf("a", "A")]}
    g2 = {"id": "g2", "title": "Stage 2", "frame": "dashed", "axis_of": "b", "layout": {"type": "column"},
          "children": [leaf("t", "a two<br>line note", visual="text", role="annotation"), leaf("b", "B")]}
    bp = load(row_bp([g1, g2]))
    p = solve(bp, R)
    assert p["a"].box.cy == pytest.approx(p["b"].box.cy, abs=0.01)


def test_axis_of_must_be_descendant(mini_bp):
    from paperfig.errors import BlueprintError
    mini_bp["root"]["children"][2]["axis_of"] = "enc"
    with pytest.raises(BlueprintError, match="axis_of"):
        load(mini_bp)
