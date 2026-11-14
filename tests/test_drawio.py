import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from paperfig.blueprint import load
from paperfig.drawio import emit, parse_cells
from paperfig.styles import ARROW_BASE
from paperfig.layout import solve
from paperfig.legend import build as build_legend
from paperfig.route import route_all
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def compile_(bp, recipe=R):
    p = solve(bp, recipe)
    r = route_all(bp, p, recipe)
    return p, r, emit(bp, p, r, recipe)


def cells_by_id(xml):
    root = ET.fromstring(xml)
    return {c.get("id"): c for c in root.iter("mxCell")}


def style_of(cell):
    out = {}
    for tok in (cell.get("style") or "").split(";"):
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def test_emitted_xml_parses_and_ids_present(mini_bp):
    bp = load(mini_bp)
    _, _, xml = compile_(bp)
    c = cells_by_id(xml)
    for el in bp.index.values():
        if el.id == "root":
            continue
        assert f"pf-{el.id}" in c
    for e in bp.edges:
        cell = c[f"pf-{e.id}"]
        assert cell.get("edge") == "1" and cell.get("source") == f"pf-{e.src}" and cell.get("target") == f"pf-{e.dst}"


def test_children_geometry_parent_relative(mini_bp):
    bp = load(mini_bp)
    p, _, xml = compile_(bp)
    c = cells_by_id(xml)
    assert c["pf-msa"].get("parent") == "pf-csfm"
    g = c["pf-msa"].find("mxGeometry")
    assert float(g.get("x")) == pytest.approx(p["msa"].box.x - p["csfm"].box.x, abs=0.01)
    assert float(g.get("y")) == pytest.approx(p["msa"].box.y - p["csfm"].box.y, abs=0.01)


def test_parse_cells_returns_absolute_boxes(mini_bp):
    bp = load(mini_bp)
    p, _, xml = compile_(bp)
    cells = parse_cells(xml)
    b = cells["pf-msa"].box
    assert (b.x, b.y) == pytest.approx((p["msa"].box.x, p["msa"].box.y), abs=0.01)


def test_edge_waypoints_match_route(mini_bp):
    bp = load(mini_bp)
    _, r, xml = compile_(bp)
    c = cells_by_id(xml)
    for e in bp.edges:
        arr = c[f"pf-{e.id}"].find("mxGeometry/Array")
        pts = [(float(m.get("x")), float(m.get("y"))) for m in arr] if arr is not None else []
        want = r[e.id].points[1:-1]
        assert len(pts) == len(want)
        for (x, y), (wx, wy) in zip(pts, want):
            assert x == pytest.approx(wx, abs=0.01) and y == pytest.approx(wy, abs=0.01)


def test_edge_exit_entry_points_match_ports(mini_bp):
    bp = load(mini_bp)
    p, r, xml = compile_(bp)
    c = cells_by_id(xml)
    for e in bp.edges:
        st = style_of(c[f"pf-{e.id}"])
        b = p[e.src].box
        x = b.x + float(st["exitX"]) * b.w + float(st.get("exitDx", 0))
        y = b.y + float(st["exitY"]) * b.h + float(st.get("exitDy", 0))
        assert (x, y) == pytest.approx(r[e.id].points[0], abs=0.05)
        assert st["exitPerimeter"] == "0" and st["entryPerimeter"] == "0"


def test_image_data_uri_has_no_semicolon_base64(mini_bp, tmp_path):
    Image.new("RGB", (40, 30), "red").save(tmp_path / "x.png")
    mini_bp["root"]["children"][0].update(visual="image", asset={"path": "x.png", "status": "provided"})
    bp = load(mini_bp, base_dir=tmp_path)
    _, _, xml = compile_(bp)
    st = cells_by_id(xml)["pf-inp"].get("style")
    assert "image=data:image/png," in st and ";base64" not in st


def test_large_image_downscaled(mini_bp, tmp_path):
    Image.new("RGB", (4000, 3000), "red").save(tmp_path / "big.png")
    mini_bp["root"]["children"][0].update(visual="image", asset={"path": "big.png", "status": "provided"})
    bp = load(mini_bp, base_dir=tmp_path)
    _, _, xml = compile_(bp)
    assert len(xml) < 400_000


def test_html_label_escaped(mini_bp):
    mini_bp["root"]["children"][1]["label"] = "Enc & <b>Proj</b>"
    bp = load(mini_bp)
    _, _, xml = compile_(bp)
    assert cells_by_id(xml)["pf-enc"].get("value") == "Enc &amp; <b>Proj</b>"


def test_placeholder_rendered_as_image_frame(mini_bp):
    # round 2: a pending image is a dashed image frame; its spec goes to the report, not into the figure
    mini_bp["root"]["children"][0].update(visual="image", asset={"status": "requested", "spec": "rainy input"})
    bp = load(mini_bp)
    _, _, xml = compile_(bp)
    cell = cells_by_id(xml)["pf-inp"]
    assert style_of(cell)["dashed"] == "1" and style_of(cell)["pfasset"] == "pending"
    assert "rainy input" not in cell.get("value") and "ASSET NEEDED" not in cell.get("value")


def test_tensor_style_cube_depth_top_right():
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "children": [leaf("t", "F<sub>1</sub>", visual="tensor")]}})
    _, _, xml = compile_(bp, load_recipe("depth-cv"))
    st = style_of(cells_by_id(xml)["pf-t"])
    assert st["shape"] == "cube" and st["flipH"] == "1" and st["verticalLabelPosition"] == "bottom"


def test_tokens_children_inside_group():
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "children": [leaf("q", "Queries", visual="tokens", tokens=4)]}})
    p, _, xml = compile_(bp)
    c = cells_by_id(xml)
    toks = [k for k in c if k.startswith("pfdeco-q-tok")]
    assert len(toks) == 4 and all(c[k].get("parent") == "pf-q" for k in toks)


def test_legend_lists_used_kinds_only(mini_bp):
    bp = load(mini_bp)
    p, r, xml = compile_(bp)
    vals = " ".join(c.get("value") or "" for c in ET.fromstring(xml).iter("mxCell"))
    assert "skip connection" in vals and "loss" not in vals


def test_legend_none_when_disabled(mini_bp):
    mini_bp["figure"]["legend"] = "none"
    bp = load(mini_bp)
    _, _, xml = compile_(bp)
    assert not any(k.startswith("pfdeco-legend") for k in cells_by_id(xml))


def test_legend_below_figure(mini_bp):
    bp = load(mini_bp)
    p = solve(bp, R)
    lg = build_legend(bp, R, p[bp.root.id].box)
    assert lg is not None and lg.box.y >= p[bp.root.id].box.bottom


def test_badge_placed_top_right(mini_bp):
    mini_bp["root"]["children"][1]["badges"] = ["frozen"]
    bp = load(mini_bp)
    p, _, xml = compile_(bp)
    cells = parse_cells(xml)
    badge = cells["pfdeco-enc-badge0"].box
    enc = p["enc"].box
    assert badge.cx > enc.cx and badge.cy < enc.cy
    assert "data:image/svg+xml," in cells_by_id(xml)["pfdeco-enc-badge0"].get("style")


def test_unknown_icon_raises(mini_bp):
    from paperfig.errors import PaperFigError
    mini_bp["root"]["children"][0].update(visual="icon", icon="does-not-exist")
    bp = load(mini_bp)
    with pytest.raises(PaperFigError, match="does-not-exist"):
        compile_(bp)


def test_legend_below_routed_edges(mini_bp):
    bp = load(mini_bp)
    p, r, xml = compile_(bp)
    cells = parse_cells(xml)
    lowest = max(y for rt in r.values() for _, y in rt.points)
    assert cells["pfdeco-legend"].box.y >= lowest + 10


def test_ink_scale_enlarges_tokens_and_arrows():
    import copy as _c
    from paperfig.styles import Recipe
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "children": [leaf("q", "Queries", visual="tokens", tokens=2), leaf("b", "B")]},
               "edges": [{"src": "q", "dst": "b", "provenance": PROV}]})
    d = _c.deepcopy(R.data); d["ink_scale"] = 2.0
    R2 = Recipe("x", d)
    p, r, xml = compile_(bp, R2)
    cells = parse_cells(xml)
    assert cells["pfdeco-q-tok0"].box.w == pytest.approx(28)
    assert float(style_of(cells_by_id(xml)["pf-e0"])["endSize"]) == pytest.approx(ARROW_BASE * 2 ** 0.5, abs=0.01)


def test_badge_inside_corner_with_clearance(mini_bp):
    mini_bp["root"]["children"][1]["badges"] = ["frozen"]
    bp = load(mini_bp)
    p, _, xml = compile_(bp)
    b = parse_cells(xml)["pfdeco-enc-badge0"].box
    enc = p["enc"].box
    assert enc.contains(b.inflate(3.9))


def test_legend_swatch_is_wide(mini_bp):
    bp = load(mini_bp)
    _, _, xml = compile_(bp)
    sw = next(c for k, c in parse_cells(xml).items() if k.endswith("-swatch"))
    assert sw.box.w >= 1.8 * sw.box.h


def test_flipped_tensor_exit_mirrored_for_drawio():
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "children": [leaf("t", "<i>X</i>", visual="tensor"), leaf("b", "B")]},
               "edges": [{"src": "t", "dst": "b", "provenance": PROV}]})
    p, r, xml = compile_(bp)
    st = style_of(cells_by_id(xml)["pf-e0"])
    assert float(st["exitX"]) == pytest.approx(0.0)  # drawio mirrors constraints of flipH shapes: 0 means the right face
    from paperfig.lint import _polyline
    cells = parse_cells(xml)
    assert _polyline(cells["pf-e0"], cells)[0][0] == pytest.approx(p["t"].box.right)


def test_arrow_size_grows_slower_than_ink():
    import copy as _c
    from paperfig.styles import Recipe, edge_style_for_kind
    d = _c.deepcopy(R.data); d["ink_scale"] = 1.6
    assert float(edge_style_for_kind(Recipe("x", d), "data")["endSize"]) == pytest.approx(ARROW_BASE * 1.6 ** 0.5, abs=0.01)


def test_plain_container_flat_in_depth_style(mini_bp):
    from paperfig.styles import group_style
    mini_bp["root"]["children"].append({"id": "plain", "title": "Panel", "layout": {"type": "row"}, "children": [leaf("z", "Z")]})
    bp = load(mini_bp)
    rc = load_recipe("depth-cv")
    assert group_style(rc, bp.index["plain"])["shadow"] == "0"
    assert group_style(rc, bp.index["csfm"])["shadow"] == "1"


def test_edge_label_sits_on_longest_segment():
    ch = [leaf("a", "A", cell=[0, 0]), leaf("b", "B", cell=[1, 1])]
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
               "root": {"id": "root", "layout": {"type": "grid"}, "children": ch},
               "edges": [{"src": "a", "dst": "b", "label": "↓2", "provenance": PROV}]})
    p, r, xml = compile_(bp)
    from paperfig.lint import _label_point, _polyline
    cells = parse_cells(xml)
    pts = r["e0"].points
    segs_ = list(zip(pts, pts[1:]))
    (s, t) = max(segs_, key=lambda st: abs(st[1][0] - st[0][0]) + abs(st[1][1] - st[0][1]))
    mx, my = _label_point(cells["pf-e0"], _polyline(cells["pf-e0"], cells))
    assert (mx, my) == pytest.approx(((s[0] + t[0]) / 2, (s[1] + t[1]) / 2), abs=0.5)
