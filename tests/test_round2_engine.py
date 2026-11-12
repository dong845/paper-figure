import copy
import json

import pytest

from conftest import MINI, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.errors import ExportError
from paperfig.export import find_drawio

try:
    find_drawio()
    HAVE = True
except ExportError:
    HAVE = False
needs_drawio = pytest.mark.skipif(not HAVE, reason="draw.io desktop not installed")


def write_bp(tmp_path, d):
    p = tmp_path / "fig" / "blueprint.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(d))
    return p


@needs_drawio
def test_placeholder_is_image_frame(tmp_path):
    d = copy.deepcopy(MINI)
    d["root"]["children"][0] = leaf("inp", "CT slice", role="io", visual="placeholder", size=[120, 90],
                                    asset={"status": "requested", "spec": "an axial abdominal CT slice from the Synapse dataset, 512x512"})
    res = P.build(write_bp(tmp_path, d), "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    cells = parse_cells(res.drawio.read_text())
    c = cells["pf-inp"]
    assert "ASSET NEEDED" not in c.value and "Synapse" not in c.value
    assert abs(c.box.w / c.box.h - 120 / 90) < 0.05 and c.box.w < 200
    assert any(f.code == "asset-pending" for f in res.report.findings)


def test_short_dashed_edge_keeps_dash():
    from paperfig.drawio import fit_dash

    assert fit_dash("6 4", 200) == "6 4"
    short = [float(x) for x in fit_dash("6 4", 18).split()]
    assert sum(short) * 2.5 <= 18 + 1e-6 and all(x >= 1 for x in short)
    assert [float(x) for x in fit_dash("8 3 2 3", 20).split()] and len(fit_dash("8 3 2 3", 20).split()) == 4


def test_subscript_label_judged_by_base_size():
    from paperfig.drawio import Cell
    from paperfig.geometry import Box
    from paperfig.lint import smallest_text
    from paperfig.styles import compose

    r = compose("soft-pastel")
    cells = {"pf-a": Cell("pf-a", "1", "z<sub>t</sub> latent", {"fontSize": "12"}, True, False, box=Box(0, 0, 50, 20))}
    pt, cid = smallest_text(cells, r, 7.1 / 12)[:2]
    assert abs(pt - 7.1) < 1e-6  # the base size counts; the subscript is typeset smaller on purpose


def test_titled_group_blocks_only_title_text():
    from paperfig.blueprint import load
    from paperfig.route import _obstacles
    from paperfig.styles import compose

    d = copy.deepcopy(MINI)
    d["root"]["children"].insert(0, leaf("cond", "Condition", role="io"))
    d["edges"].append({"src": "cond", "dst": "gf", "provenance": [{"source": "draft", "ref": "Sec. 3"}]})
    bp = load(d)
    recipe = compose("soft-pastel")
    placed, _ = P.solve_and_route(bp, recipe)
    e = next(x for x in bp.edges if x.src == "cond")
    obs = _obstacles(bp, placed, e, 6.0)
    band = placed["csfm"].title_box
    assert band is not None and not any(abs(o.w - (band.w + 6.0)) < 1e-6 and abs(o.y - (band.y - 3.0)) < 1e-6 for o in obs)


def test_round_stores_absolute_paths(tmp_path, monkeypatch):
    from paperfig import run

    d = run.init(tmp_path / "r", mode="auto", figure_type="overview", code=str(tmp_path))
    b = d / "build" / "r1"
    b.mkdir(parents=True)
    (b / "fig.lint.json").write_text(json.dumps({"ok": True, "counts": {"error": 0}, "stats": {}}))
    (d / "critic" / "r1.json").write_text(json.dumps({"viewed_png": True, "scores": {}, "issues": []}))
    monkeypatch.chdir(d)
    run.record_round(d, 1, "build/r1/fig.lint.json", "critic/r1.json", "")
    rec = json.loads((d / "run.json").read_text())
    assert rec["rounds"][0]["lint_file"].startswith("/") and rec["rounds"][0]["critic_file"].startswith("/")


@needs_drawio
def test_legend_in_empty_space_no_overlap(tmp_path):
    from conftest import PROV
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": [
             leaf("a", "Encoder with a long name", role="reused", cell=[0, 0]), leaf("b", "Decoder block", role="reused", cell=[0, 1]),
             leaf("c", "Fusion module", role="proposed", full_name="Fusion module", cell=[1, 0]),
             leaf("e", "Head", role="reused", cell=[2, 0])]},
         "edges": [{"src": "a", "dst": "b", "provenance": copy.deepcopy(PROV)},
                   {"src": "a", "dst": "c", "kind": "skip", "provenance": copy.deepcopy(PROV)},
                   {"src": "c", "dst": "e", "provenance": copy.deepcopy(PROV)}]}
    res = P.build(write_bp(tmp_path, d), "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    cells = parse_cells(res.drawio.read_text())
    boxes = [c.box for cid, c in cells.items() if cid.startswith("pf-") and c.box is not None]
    from paperfig.geometry import Box
    root = Box(min(b.x for b in boxes), min(b.y for b in boxes), 0, 0)
    root = Box(root.x, root.y, max(b.right for b in boxes) - root.x, max(b.bottom for b in boxes) - root.y)
    lg = cells["pfdeco-legend"].box
    assert lg.y < root.bottom and lg.x >= root.x - 1 and lg.right <= root.right + 1, (lg, root)  # inside, not a band below
    assert not any(f.code in ("overlap", "edge-through-legend") for f in res.report.findings), [f.message for f in res.report.findings if f.code in ("overlap", "edge-through-legend")]


def test_legend_may_sit_inside_a_frameless_group():
    from types import SimpleNamespace
    from paperfig.lint import _legend_hits
    from paperfig.geometry import Box

    g = SimpleNamespace(is_group=True, frame="none", title=None)
    framed = SimpleNamespace(is_group=True, frame="box", title="Encoder")
    leaf_ = SimpleNamespace(is_group=False, frame=None, title=None)
    lg = Box(100, 100, 40, 20)
    assert not _legend_hits(g, Box(0, 0, 300, 300), lg, 24)
    assert _legend_hits(framed, Box(0, 0, 300, 300), lg, 24)
    assert _legend_hits(leaf_, Box(110, 110, 10, 10), lg, 24)
    titled = SimpleNamespace(is_group=True, frame="none", title="Stage 1")
    assert _legend_hits(titled, Box(90, 95, 300, 300), lg, 24)  # its title band runs through the legend


def test_legend_keeps_clear_of_bracket_labels(tmp_path):
    """BLIP-2 regression: the in-figure legend landed on the stage-2 bracket label."""
    import re
    from pathlib import Path
    from paperfig import lint as L
    from paperfig.blueprint import load
    from paperfig.styles import load_recipe

    src = Path(__file__).resolve().parents[1] / "bench/phase0/blip2/blueprint.json"
    res = P.build(src, "soft-pastel", out_dir=tmp_path / "o", formats=("png",),
                  facts_path=src.parent / "facts.json")
    cells = parse_cells(res.drawio.read_text())
    lg = cells["pfdeco-legend"].box
    anns = [c.box for cid, c in cells.items() if cid.startswith("pfdeco-ann-") and cid.endswith("-label")]
    assert anns and not any(lg.intersects(b, eps=0.5) for b in anns), (lg, anns)
    # the lint must catch a legend moved onto a bracket label by hand
    lab = anns[0]
    text = res.drawio.read_text()
    m = re.search(r'(<mxCell id="pfdeco-legend"[^>]*>\s*<mxGeometry )x="[^"]*" y="[^"]*"', text)
    assert m, "legend geometry not found"
    moved = text[:m.start()] + m.group(1) + f'x="{lab.x}" y="{lab.y}"' + text[m.end():]
    bad = tmp_path / "moved.drawio"
    bad.write_text(moved)
    rep = L.check(bad, load(src), load_recipe("soft-pastel"), res.png, 6.875)
    ann_ids = {a.id for a in load(src).annotations}
    assert any(f.code == "overlap" and "legend" in f.ids and ann_ids & set(f.ids) for f in rep.findings), \
        [f.message for f in rep.findings]
