"""User 2026-11-14 on the DreamerV3 run: the original's small squares (categorical latent grids, observation vectors)
'both enrich the content and look good'. Structure glyphs draw what a representation IS — not data, so they need no
illustrative mark: onehot (a categorical latent), vector (a bracketed column), patches (an image in patches and
windows, regular or shifted)."""
import base64
import copy
import json
import re

import pytest

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.drawio import parse_cells
from paperfig.errors import BlueprintError

NODES = {"z": dict(glyph="onehot", grid=[4, 5]), "q": dict(glyph="vector", nodes=5),
         "w": dict(glyph="patches", grid=[8, 8]), "s": dict(glyph="patches", grid=[8, 8], variant="shifted")}


def _bp():
    nodes = [leaf(k, k, visual="glyph", **v) for k, v in NODES.items()]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": nodes},
            "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}


def _svgs(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps(_bp()))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(r.drawio.read_text())
    return r, {k: base64.b64decode(c[f"pf-{k}"].style["image"].split(",", 1)[1]).decode() for k in NODES}


def test_structure_glyphs_render_unmarked(tmp_path):
    r, svg = _svgs(tmp_path)
    assert not [f for f in r.report.findings if f.code == "schematic-unmarked" or f.severity == "error"]
    rows = re.findall(r'<rect[^>]*data-row="(\d)"[^>]*data-on="1"', svg["z"])
    assert sorted(set(rows)) == ["0", "1", "2", "3"] and len(rows) == 4  # exactly one class on per row
    assert svg["q"].count("<rect") == 5 and svg["q"].count("<path") >= 2  # five cells between two brackets
    assert svg["w"] != svg["s"]  # shifted windows move the window lines


def test_grid_only_where_it_means_something():
    d = _bp()
    d["root"]["children"][1]["grid"] = [3, 3]  # a vector has no grid
    with pytest.raises(BlueprintError, match="grid"):
        load(d)
