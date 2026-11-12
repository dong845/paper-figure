"""Regression tests for the whole-branch review findings (Important 1-6)."""
import base64
import io
import re

import pytest
from PIL import Image

from paperfig.blueprint import load
from paperfig.errors import BlueprintError
from paperfig.layout import solve
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def one(children, edges=(), layout=None, **fig):
    f = {"type": "overview", "venue": "cvpr", "width": "double"}
    f.update(fig)
    return {"schema_version": 1, "figure": f,
            "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges]}


# ---- 1. EXIF orientation -------------------------------------------------
def test_exif_rotated_photo_gets_portrait_box(tmp_path):
    im = Image.new("RGB", (400, 200), "red")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW on display: displayed size is 200x400
    im.save(tmp_path / "phone.jpg", exif=exif)
    bp = load(one([leaf("img", "", visual="image", asset={"path": "phone.jpg", "status": "provided"})]), base_dir=tmp_path)
    b = solve(bp, R)["img"].box
    assert b.w / b.h == pytest.approx(0.5)


# ---- 2. extreme aspect: crop, never stretch -------------------------------
def _embedded_size(xml, cid):
    st = re.search(rf'id="{cid}"[^>]*style="([^"]*)"', xml).group(1)
    b64 = re.search(r"image=data:image/[a-z]+,([A-Za-z0-9+/=]+)", st).group(1)
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


def test_extreme_aspect_image_is_cropped_not_stretched(tmp_path):
    from paperfig.drawio import emit
    from paperfig.route import route_all
    Image.new("RGB", (20, 400), "blue").save(tmp_path / "strip.png")
    bp = load(one([leaf("img", "", visual="image", asset={"path": "strip.png", "status": "provided"})]), base_dir=tmp_path)
    p = solve(bp, R)
    xml = emit(bp, p, route_all(bp, p, R), R)
    w, h = _embedded_size(xml, "pf-img")
    box = p["img"].box
    assert w / h == pytest.approx(box.w / box.h, rel=0.02)


# ---- 3. corrupt / truncated files ------------------------------------------
def test_truncated_image_rejected_with_path(tmp_path):
    Image.new("RGB", (64, 64), "green").save(tmp_path / "ok.png")
    data = (tmp_path / "ok.png").read_bytes()
    (tmp_path / "trunc.png").write_bytes(data[: len(data) // 2])
    with pytest.raises(BlueprintError, match="trunc.png"):
        load(one([leaf("img", "", visual="image", asset={"path": "trunc.png", "status": "provided"})]), base_dir=tmp_path)


def test_non_image_file_rejected_with_path(tmp_path):
    (tmp_path / "notes.png").write_text("not an image")
    with pytest.raises(BlueprintError, match="notes.png"):
        load(one([leaf("img", "", visual="image", asset={"path": "notes.png", "status": "provided"})]), base_dir=tmp_path)


def test_cli_unexpected_exception_has_distinct_exit_code(monkeypatch, capsys):
    import paperfig.__main__ as M
    import paperfig.pipeline as P

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(P, "build", boom)
    assert M.main(["build", "whatever.json"]) == 3
    err = capsys.readouterr().err
    assert "internal error" in err and "synthetic failure" in err


# ---- 4. small figures: no false png-mismatch --------------------------------
@pytest.mark.parametrize("style", ["soft-pastel", "depth-cv"])
def test_single_node_figure_has_no_png_mismatch(tmp_path, style):
    import json
    from paperfig import pipeline as P
    from paperfig.errors import ExportError
    try:
        P.find_drawio() if hasattr(P, "find_drawio") else __import__("paperfig.export").export.find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    d = tmp_path / "fig"
    d.mkdir()
    (d / "blueprint.json").write_text(json.dumps(one([leaf("a", "Only node")])))
    res = P.build(d / "blueprint.json", style, out_dir=tmp_path / "out")
    assert not any(f.code == "png-mismatch" for f in res.report.findings), res.report.to_markdown()


# ---- 5. repair must not trade crossings for overlaps ------------------------
def _containers_bp():
    return load(one([
        {"id": "ga", "title": "Group A", "layout": {"type": "column"}, "children": [leaf("a1", "A1"), leaf("a2", "A2")]},
        {"id": "gb", "title": "Group B", "layout": {"type": "column"}, "children": [leaf("b1", "B1"), leaf("b2", "B2")]},
        {"id": "gc", "title": "Group C", "children": [leaf("c1", "C1")]},
    ], [{"src": "a1", "dst": "b2"}, {"src": "a2", "dst": "b1"}, {"src": "ga", "dst": "gc"},
        {"src": "a2", "dst": "gc"}, {"src": "b2", "dst": "c1"}], layout={"type": "row", "gap": "loose"}))


def _overlaps(routes):
    from paperfig.route import _overlap_len
    items = list(routes.values())
    return sum(_overlap_len(a.points, b.points) > 1.0 for i, a in enumerate(items) for b in items[i + 1:])


def test_repair_does_not_create_collinear_overlaps():
    from paperfig.pipeline import solve_and_route
    bp = _containers_bp()
    _, r = solve_and_route(bp, R)
    assert _overlaps(r) == 0


def test_repair_never_makes_global_badness_worse(monkeypatch):
    from paperfig import route as RT
    from paperfig.pipeline import solve_and_route
    bp = _containers_bp()
    _, with_repair = solve_and_route(bp, R)
    monkeypatch.setattr(RT, "_repair", lambda *a, **k: None)
    _, without = solve_and_route(bp, R)
    assert RT.global_badness(with_repair) <= RT.global_badness(without)


def test_lint_collinear_overlap_is_error(mini_bp, tmp_path):
    from paperfig.lint import check
    from test_lint import build, codes
    # two skip edges forced onto the same run
    mini_bp["edges"].append({"src": "inp", "dst": "out", "kind": "skip", "provenance": PROV})
    bp, f = build(mini_bp, tmp_path)
    xml = f.read_text()
    # move the second skip's waypoints onto the first skip's waypoints
    pts = re.findall(r'<mxCell id="pf-e5".*?<Array as="points">(.*?)</Array>', xml, re.S)
    xml = re.sub(r'(<mxCell id="pf-e6".*?<Array as="points">).*?(</Array>)', lambda m: m.group(1) + pts[0] + m.group(2), xml, count=1, flags=re.S)
    f.write_text(xml)
    rep = check(f, bp, R, None, 6.875)
    assert "edge-overlap" in codes(rep, "error")


# ---- 6. min-font counts sub/superscript runs --------------------------------
def test_min_font_uses_script_run_size(tmp_path):
    from paperfig.lint import check, SCRIPT_SCALE_RENDER
    from test_lint import build
    (tmp_path / "s").mkdir()
    (tmp_path / "p").mkdir()
    bp, f = build(one([leaf("a", "Block F<sub>enc,i</sub>")]), tmp_path / "s")
    plain_bp, pf = build(one([leaf("a", "Block Fenc")]), tmp_path / "p")
    rep = check(f, bp, R, None, 6.875)
    rep_plain = check(pf, plain_bp, R, None, 6.875)
    # the subscript prints at SCRIPT_SCALE_RENDER of the cell font (figures differ slightly in width)
    assert rep.stats["smallest_text_pt"] == pytest.approx(rep_plain.stats["smallest_text_pt"] * SCRIPT_SCALE_RENDER, rel=0.08)


def test_script_scale_matches_drawio_render(tmp_path):
    from paperfig import export as X
    from paperfig.errors import ExportError
    from paperfig.measure import measure
    try:
        X.find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    label = "x<sub>abcdefghijklmnop</sub>"
    pred, _ = measure(label, 12)
    style = "text;html=1;whiteSpace=nowrap;fontFamily=Helvetica;fontSize=12;spacing=0;align=left;fillColor=none;strokeColor=none;"
    from xml.sax.saxutils import quoteattr
    xml = ('<mxfile><diagram name="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
           f'<mxCell id="t" value={quoteattr(label)} style="{style}" vertex="1" parent="1"><mxGeometry x="0" y="0" width="{pred + 40:.0f}" height="20" as="geometry"/></mxCell>'
           '</root></mxGraphModel></diagram></mxfile>')
    (tmp_path / "t.drawio").write_text(xml)
    out = X.export(tmp_path / "t.drawio", "png", tmp_path / "t.png", scale=4, border=0)
    g = Image.open(out).convert("L")
    px = g.load()
    cols = [x for x in range(g.size[0]) if any(px[x, y] < 128 for y in range(g.size[1]))]
    rendered = (max(cols) - min(cols) + 1) / 4
    assert rendered == pytest.approx(pred, rel=0.04, abs=2), (rendered, pred)


def test_build_reports_cropped_image(tmp_path):
    import json
    from paperfig import pipeline as P
    from paperfig.errors import ExportError
    from paperfig.export import find_drawio
    try:
        find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    d = tmp_path / "fig"
    d.mkdir()
    Image.new("RGB", (20, 400), "blue").save(d / "strip.png")
    (d / "blueprint.json").write_text(json.dumps(one([leaf("img", "", visual="image", asset={"path": "strip.png", "status": "provided"}), leaf("b", "B")],
                                                     [{"src": "img", "dst": "b"}])))
    res = P.build(d / "blueprint.json", "soft-pastel", out_dir=tmp_path / "out")
    f = [x for x in res.report.findings if x.code == "image-cropped"]
    assert f and f[0].ids == ["img"] and f[0].severity == "info"
