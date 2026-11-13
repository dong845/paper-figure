"""Round 3: glyph visuals from the user's guide §9.1 (graph, database, prototype, heatmap, mask, k-space)."""
import base64
import copy
import json

import pytest

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.drawio import parse_cells
from paperfig.errors import BlueprintError

GLYPHS = {"g": dict(glyph="graph", nodes=6), "db": dict(glyph="database"), "pr": dict(glyph="prototype"),
          "hm": dict(glyph="heatmap", illustrative=True), "mk": dict(glyph="mask", illustrative=True),
          "ks": dict(glyph="kspace", pattern="cartesian", illustrative=True)}


def _bp(nodes):
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
            "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}


def _svg(cell):
    uri = cell.style["image"]
    assert uri.startswith("data:image/svg+xml,"), uri[:40]
    return base64.b64decode(uri.split(",", 1)[1]).decode()


def test_glyphs_render(tmp_path):
    nodes = [leaf(k, k.upper(), visual="glyph", **v) for k, v in GLYPHS.items()]
    (tmp_path / "blueprint.json").write_text(json.dumps(_bp(nodes)))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]
    cells = parse_cells(res.drawio.read_text())
    svgs = {k: _svg(cells[f"pf-{k}"]) for k in GLYPHS}
    assert svgs["g"].count("<circle") == 6  # one circle per graph node
    assert "<ellipse" in svgs["db"] and "<polygon" in svgs["pr"]
    assert svgs["hm"].count("<rect") >= 16 and svgs["ks"].count("<line") >= 5
    assert cells["pf-hm"].style.get("dashed") == "1"  # schematic glyphs carry a dashed frame
    # deterministic: the same blueprint draws the same glyphs
    res2 = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o2", formats=("png",))
    assert parse_cells(res2.drawio.read_text())["pf-mk"].style["image"] == cells["pf-mk"].style["image"]


def test_schematic_glyph_needs_marker(tmp_path):
    nodes = [leaf("a", "Encoder"), leaf("hm", "Attention map", visual="glyph", glyph="heatmap")]
    (tmp_path / "blueprint.json").write_text(json.dumps(_bp(nodes)))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    assert any(f.code == "schematic-unmarked" and "hm" in f.ids for f in res.report.findings)
    with pytest.raises(BlueprintError, match="glyph"):
        load(_bp([leaf("x", "X", visual="glyph")]))
