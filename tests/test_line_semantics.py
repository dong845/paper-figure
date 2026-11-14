"""Round 8: one stroke width; meaning carried by the pattern (solid / dashed / dotted / dash-dot) or a clearly
different colour (user 2026-11-14: '线也可以同一粗细，但是实现和虚线或者不同颜色来表达不同含义')."""
import itertools

import pytest

from paperfig import color
from paperfig.styles import STYLES_DIR, load_recipe

STYLES = sorted(p.stem for p in STYLES_DIR.glob("*.json"))
HUE_DE = 20.0  # same pattern: the colours must differ at least this much (ΔE00)


def pattern(dash):
    if not dash:
        return "solid"
    n = [float(x) for x in str(dash).split()]
    if len(n) >= 4:
        return "dash-dot"
    return "dotted" if n[0] <= 2.5 else "dashed"


@pytest.mark.parametrize("sid", STYLES)
def test_every_pair_of_edge_kinds_reads_apart(sid):
    e = load_recipe(sid)["edges"]
    bad = []
    for a, b in itertools.combinations(sorted(e), 2):
        pa, pb = pattern(e[a]["dash"]), pattern(e[b]["dash"])
        # an arrowhead (open vs filled) is too small to carry a meaning in print: pattern or colour must
        if pa == pb and color.de2000(e[a]["color"], e[b]["color"]) < HUE_DE:
            bad.append((a, b, pa, e[a]["color"], e[b]["color"]))
    assert not bad, bad


@pytest.mark.parametrize("sid", STYLES)
def test_one_stroke_width_for_every_kind(sid):
    e = load_recipe(sid)["edges"]
    assert len({round(v["width"], 2) for v in e.values()}) == 1, {k: v["width"] for k, v in e.items()}


def _two_kinds(tmp_path, k1, k2, tone1=None):
    import copy
    import json
    from conftest import PROV, leaf
    from paperfig import pipeline as P
    kids = [leaf("a", "A"), leaf("b", "B"), leaf("c", "C")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": kids},
         "edges": [dict({"src": "a", "dst": "b", "kind": k1, "provenance": copy.deepcopy(PROV)}, **({"tone": tone1} if tone1 else {})),
                   {"src": "b", "dst": "c", "kind": k2, "provenance": copy.deepcopy(PROV)}]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    return [f for f in res.report.findings if f.code == "edge-kind-color-only"]


def test_colour_alone_is_fine_unless_grayscale_merges_it(tmp_path):
    """data (dark grey) vs control (light grey): same solid line, clearly different even in B/W print → info."""
    f = _two_kinds(tmp_path, "data", "control")
    assert f and all(x.severity == "info" for x in f), [(x.severity, x.message) for x in f]


def test_colour_alone_that_merges_in_grayscale_warns(tmp_path):
    """an orange data path vs a light-grey control line: both solid, clearly different hues, the same grey in B/W."""
    f = _two_kinds(tmp_path / "g", "data", "control", tone1="orange")
    assert f and f[0].severity == "warn" and "grayscale" in f[0].message


def test_dash_lengths_are_one_pattern(tmp_path):
    """'6 4' and '4 3' both print as a dashed line: kinds are told apart by pattern class, not by dash length."""
    f = _two_kinds(tmp_path / "d", "skip", "loss")
    assert f and f[0].severity == "info"  # grey vs red dashed: clear in colour and in grayscale
