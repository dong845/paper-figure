"""Round 4: style is open — a run may use its own recipe file, derived from the references' measured palettes;
train-only edges never borrow the accent colour (F88)."""
import json
import shutil
from pathlib import Path

import pytest

from paperfig import color
from paperfig.styles import STYLES_DIR, compose, derive_style, load_recipe

RECIPES = ("soft-pastel", "depth-cv", "editorial-minimal", "drawio-default")


def test_style_path(tmp_path):
    p = tmp_path / "mine.json"
    shutil.copy(STYLES_DIR / "soft-pastel.json", p)
    r = load_recipe(str(p))
    assert r["palette"]["roles"]["proposed"]["tone"] == "orange"
    assert compose(str(p), {"edges": "editorial-minimal"})["edges"]["data"] == load_recipe("editorial-minimal")["edges"]["data"]


@pytest.mark.parametrize("rid", RECIPES)
def test_train_only_edge_not_accent(rid):
    r = load_recipe(rid)
    pal = r["palette"]
    acc = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"].lower()
    assert r["edges"]["train_only"]["color"].lower() != acc, rid


def _card(cid, hexes):
    return {"id": cid, "figure_type": "overview",
            "measured": {"palette": [{"hex": h, "share": s, "neutral": False} for h, s in hexes] +
                                    [{"hex": "#ffffff", "share": 0.6, "neutral": True}]}}


def test_style_derive_contrast_safe(tmp_path):
    cards = tmp_path / "cards"
    cards.mkdir()
    # a reference palette: saturated purple accent, teal and muted blue
    (cards / "a.json").write_text(json.dumps(_card("a", [("#7b2cbf", 0.08), ("#2a9d8f", 0.12), ("#8fb3d9", 0.10)])))
    (cards / "b.json").write_text(json.dumps(_card("b", [("#6a1fb0", 0.05), ("#3aa597", 0.07)])))
    out = derive_style("soft-pastel", cards, tmp_path / "style.json")
    r = load_recipe(str(out))
    pal = r["palette"]
    acc = pal["roles"]["proposed"]["tone"]
    h = color.lab(pal["tones"][acc]["stroke"])
    assert h[2] < 0 and h[1] > 20  # the accent took the references' purple
    for name, t in pal["tones"].items():
        assert color.contrast(t["font"], t["fill"]) >= 4.5, (name, t)
    assert r["edges"]["train_only"]["color"].lower() != pal["tones"][acc]["stroke"].lower()
    meta = json.loads(out.read_text())["derived_from"]
    assert sorted(meta["cards"]) == ["a", "b"]
