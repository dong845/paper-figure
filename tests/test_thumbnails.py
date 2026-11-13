"""Round 7 ②: procedural data thumbnails — deterministic, illustrative-only glyphs that show what the data looks like
(point cloud, waveform, spectrogram, trajectory, molecule, plot) where a grey placeholder used to sit."""
import base64
import copy
import json

import pytest

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.drawio import parse_cells
from paperfig.errors import BlueprintError

NEW = {"pc": dict(glyph="pointcloud", variant="chair"), "pa": dict(glyph="pointcloud", variant="airplane"),
       "wv": dict(glyph="waveform"), "sp": dict(glyph="spectrogram"), "tr": dict(glyph="trajectory"),
       "mo": dict(glyph="molecule"), "pl": dict(glyph="plot", variant="decay")}


def _bp(marked=True):
    nodes = [leaf(k, k.upper(), visual="glyph", illustrative=marked, **v) for k, v in NEW.items()]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
            "edges": [{"src": a["id"], "dst": b["id"], "provenance": copy.deepcopy(PROV)} for a, b in zip(nodes, nodes[1:])]}


def _svg(cell):
    return base64.b64decode(cell.style["image"].split(",", 1)[1]).decode()


def test_thumbnails_render_and_are_deterministic(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps(_bp()))
    a = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "a", formats=())
    b = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "b", formats=())
    ca, cb = parse_cells(a.drawio.read_text()), parse_cells(b.drawio.read_text())
    for k in NEW:
        svg = _svg(ca[f"pf-{k}"])
        assert svg.startswith("<svg") and len(svg) > 300, k
        assert ca[f"pf-{k}"].style["image"] == cb[f"pf-{k}"].style["image"], f"{k} not deterministic"
    assert _svg(ca["pf-pc"]).count("<circle") >= 120  # a cloud, not a few dots
    assert _svg(ca["pf-pc"]) != _svg(ca["pf-pa"])  # the variant changes the shape
    assert not [f for f in a.report.findings if f.severity == "error"], [f.message for f in a.report.findings if f.severity == "error"]


def test_thumbnails_must_be_marked_illustrative(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps(_bp(marked=False)))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    flagged = {f.ids[0] for f in res.report.findings if f.code == "schematic-unmarked"}
    assert flagged == set(NEW)


def test_unknown_variant_is_rejected():
    d = _bp()
    d["root"]["children"][0]["variant"] = "sofa"
    with pytest.raises(BlueprintError, match="variant"):
        load(d)
