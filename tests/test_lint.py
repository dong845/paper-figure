import json
import re

import pytest

from paperfig.blueprint import load
from paperfig.drawio import emit
from paperfig.layout import solve
from paperfig.lint import check
from paperfig.route import route_all
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def build(bp_dict, tmp_path, recipe=R, mutate=None):
    bp = load(bp_dict, base_dir=tmp_path)
    p = solve(bp, recipe)
    r = route_all(bp, p, recipe)
    xml = emit(bp, p, r, recipe)
    if mutate:
        xml = mutate(xml)
    f = tmp_path / "fig.drawio"
    f.write_text(xml)
    return bp, f


def codes(rep, severity=None):
    return {f.code for f in rep.findings if severity is None or f.severity == severity}


def set_geom(xml, cid, **kw):
    """Rewrite attributes of the mxGeometry of cell `cid`."""
    def repl(m):
        head, geom = m.group(1), m.group(2)
        for k, v in kw.items():
            geom = re.sub(rf'\s{k}="[^"]*"', f' {k}="{v}"', geom, count=1)
        return head + geom
    pat = re.compile(rf'(<mxCell id="{cid}".*?)(<mxGeometry[^>]*>)', re.S)
    return pat.sub(repl, xml, count=1)


def geom_x(xml, cid):
    return float(re.search(rf'<mxCell id="{cid}".*?<mxGeometry x="([\d.\-]+)"', xml, re.S).group(1))


def test_clean_figure_has_no_errors(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path)
    rep = check(f, bp, R, None, 6.875)
    assert rep.ok, rep.to_markdown()
    assert "png-mismatch" in codes(rep, "info")  # no png supplied: reported, not silently passed


def test_coverage_missing_flagged(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: re.sub(r'<mxCell id="pf-gf".*?</mxCell>', "", x, flags=re.S))
    rep = check(f, bp, R, None, 6.875)
    assert "coverage-missing" in codes(rep, "error")


def test_coverage_extra_flagged(mini_bp, tmp_path):
    extra = '<mxCell id="pf-ghost" value="Ghost" style="rounded=1;" vertex="1" parent="1"><mxGeometry x="900" y="0" width="80" height="40" as="geometry"/></mxCell></root>'
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: x.replace("</root>", extra))
    rep = check(f, bp, R, None, 6.875)
    assert "coverage-extra" in codes(rep, "error")


def test_proposed_name_missing_flagged(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: x.replace("Cross-Scale Fusion Module (CSFM)", "Fusion"))
    rep = check(f, bp, R, None, 6.875)
    assert "proposed-name-missing" in codes(rep, "error")


def test_text_overflow_flagged(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: set_geom(x, "pf-enc", width="30"))
    rep = check(f, bp, R, None, 6.875)
    assert "text-overflow" in codes(rep, "error")


def test_overlap_flagged(mini_bp, tmp_path):
    def mut(x):
        return set_geom(x, "pf-inp", x=str(geom_x(x, "pf-enc") - 10))
    bp, f = build(mini_bp, tmp_path, mutate=mut)
    rep = check(f, bp, R, None, 6.875)
    assert "overlap" in codes(rep, "error")


def test_child_outside_parent_flagged(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: set_geom(x, "pf-msa", y="-60"))
    rep = check(f, bp, R, None, 6.875)
    assert "child-outside-parent" in codes(rep, "error")


def test_edge_through_node_flagged(mini_bp, tmp_path):
    # force the skip edge enc->dec to run straight through the CSFM container
    def mut(x):
        return re.sub(r'(<mxCell id="pf-e5".*?<mxGeometry[^>]*>).*?(</mxGeometry>)', r"\1\2", x, flags=re.S)
    bp, f = build(mini_bp, tmp_path, mutate=mut)
    rep = check(f, bp, R, None, 6.875)
    assert "edge-through-node" in codes(rep, "error")


def test_min_font_flagged_when_figure_too_wide(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path)
    rep = check(f, bp, R, None, 1.0)  # squeeze a ~630px figure into 1 inch
    assert "min-font" in codes(rep, "error")
    assert not any(x.code == "min-font" for x in check(f, bp, R, None, 6.875).findings if x.severity == "error")


def test_text_contrast_flagged(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: x.replace("fontColor=#1e3a8a", "fontColor=#dfe7f7", 1))
    rep = check(f, bp, R, None, 6.875)
    assert "text-contrast" in codes(rep, "error")


def test_asset_pending_warned(mini_bp, tmp_path):
    mini_bp["root"]["children"][0].update(visual="image", asset={"status": "requested", "spec": "rainy input"})
    bp, f = build(mini_bp, tmp_path)
    rep = check(f, bp, R, None, 6.875)
    assert "asset-pending" in codes(rep, "warn")


def test_tone_confusable_warned(tmp_path):
    bpd = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
           "root": {"id": "root", "children": [leaf("a", "A", tone="red"), leaf("b", "B", tone="green")]}, "edges": []}
    bp, f = build(bpd, tmp_path)
    rep = check(f, bp, R, None, 6.875)
    assert "tone-confusable" in codes(rep, "warn")
    assert all(x.provisional for x in rep.findings if x.code == "tone-confusable")


def test_gap_uneven_warned(tmp_path):
    bpd = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
           "root": {"id": "root", "children": [leaf("a", "A"), leaf("b", "B"), leaf("c", "C"), leaf("d", "D")]}, "edges": []}
    def mut(x):
        return set_geom(x, "pf-d", x=str(geom_x(x, "pf-d") + 90))
    bp, f = build(bpd, tmp_path, mutate=mut)
    rep = check(f, bp, R, None, 6.875)
    assert "gap-uneven" in codes(rep, "warn")


def test_png_mismatch_when_stale(mini_bp, tmp_path):
    import os
    from PIL import Image
    bp, f = build(mini_bp, tmp_path)
    png = tmp_path / "fig.png"
    Image.new("RGB", (100, 100)).save(png)
    os.utime(png, (1, 1))
    rep = check(f, bp, R, png, 6.875)
    assert "png-mismatch" in codes(rep, "error")


def test_png_aspect_mismatch(mini_bp, tmp_path):
    from PIL import Image
    bp, f = build(mini_bp, tmp_path)
    png = tmp_path / "fig.png"
    Image.new("RGB", (100, 100)).save(png)
    rep = check(f, bp, R, png, 6.875)
    assert "png-mismatch" in codes(rep, "error")


def test_report_markdown_and_json(mini_bp, tmp_path):
    bp, f = build(mini_bp, tmp_path, mutate=lambda x: set_geom(x, "pf-enc", width="30"))
    rep = check(f, bp, R, None, 6.875)
    md = rep.to_markdown()
    assert "text-overflow" in md and "error" in md
    d = json.loads(rep.to_json())
    assert d["ok"] is False and any(x["code"] == "text-overflow" for x in d["findings"])


def test_edge_jog_warned(tmp_path):
    bpd = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
           "root": {"id": "root", "children": [leaf("a", "A"), leaf("b", "B")]},
           "edges": [{"src": "a", "dst": "b", "provenance": PROV}]}

    def mut(x):
        m = re.search(r'exitY=([\d.]+)', x)
        # replace straight edge by one with a 3px jog in the middle
        a = re.search(r'<mxCell id="pf-a".*?<mxGeometry x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', x, re.S)
        ax, ay, aw, ah = map(float, a.groups())
        y = ay + ah / 2
        mid = ax + aw + 14
        pts = f'<Array as="points"><mxPoint x="{mid}" y="{y}" /><mxPoint x="{mid}" y="{y + 3}" /></Array>'
        x = x.replace('exitY=0.5000;', 'exitY=0.5000;', 1)
        x = re.sub(r'(<mxCell id="pf-e0".*?entryY=)[\d.]+', lambda mm: mm.group(1) + "%.4f" % (0.5 + 3 / ah), x, count=1, flags=re.S)
        return re.sub(r'(<mxCell id="pf-e0".*?<mxGeometry relative="1" as="geometry")\s*/>', r'\1>' + pts + '</mxGeometry>', x, count=1, flags=re.S)
    bp, f = build(bpd, tmp_path, mutate=mut)
    rep = check(f, bp, R, None, 6.875)
    assert "edge-jog" in codes(rep, "warn"), rep.to_markdown()


def test_gray_only_confusion_is_info_not_warn(tmp_path):
    bpd = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
           "root": {"id": "root", "children": [leaf("a", "A", tone="blue"), leaf("b", "B", tone="green")]}, "edges": []}
    bp, f = build(bpd, tmp_path)
    rep = check(f, bp, R, None, 6.875)
    assert "tone-confusable" not in codes(rep, "warn")
    assert "gray-confusable" in codes(rep, "info")


def test_png_with_border_matches(mini_bp, tmp_path):
    from paperfig.export import export, find_drawio
    from paperfig.errors import ExportError
    try:
        find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    bp, f = build(mini_bp, tmp_path)
    png = export(f, "png", tmp_path / "fig.png", width_px=2063)
    rep = check(f, bp, R, png, 6.875)
    assert "png-mismatch" not in codes(rep), rep.to_markdown()


def test_edge_through_legend_flagged(mini_bp, tmp_path):
    def mut(x):
        # drag the legend up onto the skip edge's lowest run
        return set_geom(x, "pfdeco-legend", y="95")
    bp, f = build(mini_bp, tmp_path, mutate=mut)
    rep = check(f, bp, R, None, 6.875)
    assert "edge-through-legend" in codes(rep, "error")
