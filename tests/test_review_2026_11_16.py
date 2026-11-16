"""Whole-skill review, 2026-11-16 (user: 梳理废代码、冗余矛盾、可优化处). Each test pins one defect the review found and
fixed: quotes from a CJK draft, sketch re-runs, misspelt paradigms, style derive on neutral strokes, loss lines on
the accent, label knock-outs on tinted panels, <small> through absorb."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from paperfig import artifacts as A
from paperfig import color, kb
from paperfig.errors import PaperFigError

ROOT = Path(__file__).resolve().parents[1]


def test_quotes_from_a_cjk_draft_are_verifiable():
    """normalise kept only [0-9a-z]: every Chinese quote shrank to '' and no draft-analysis could pass."""
    text = "第三节 方法。我们提出了一种多尺度注意力模块，用于融合局部与全局特征。实验部分见下文。"
    q = "我们提出了一种多尺度注意力模块，用于融合局部与全局特征"
    assert A.normalise(q) and A.quote_in(q, A.normalise(text))
    assert not A.quote_in("我们提出了一种全新的图神经网络结构用于分类", A.normalise(text))  # a paraphrase still fails
    # Latin text normalises as before (case, punctuation, line breaks, ligatures ignored)
    assert A.quote_in("The encoder maps each patch to a token", A.normalise("the en-\ncoder maps EACH patch, to a token."
                                                                            .replace("-\n", "")))
    assert A.normalise("ﬁne-tuning") == "finetuning"


def test_sketch_rerun_skips_its_own_outputs(tmp_path):
    from paperfig.sketch import _fill, make_sketches
    with pytest.raises(PaperFigError, match="root"):
        _fill({"edges": []})
    out = tmp_path / "concepts"
    out.mkdir()
    (out / "sketches.json").write_text(json.dumps({"sheet": "x", "concepts": []}))
    (out / "c1.blueprint.json").write_text("{}")
    with pytest.raises(PaperFigError, match="at least one concept"):  # only outputs given: nothing to sketch
        make_sketches([out / "sketches.json", out / "c1.blueprint.json"], out)


def test_kb_match_says_when_a_paradigm_is_unknown():
    assert kb.known_paradigm("GAT") and kb.known_paradigm("gat")
    assert not kb.known_paradigm("Graph Attention Network")
    assert "CLIP" in kb.nearest_paradigms("clip-style")
    r = subprocess.run([sys.executable, "-m", "paperfig", "kb", "match", "--paradigm", "Latent Diffusion"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "no card has paradigm 'Latent Diffusion'" in r.stderr
    r = subprocess.run([sys.executable, "-m", "paperfig", "kb", "match", "--paradigm", "CLIP", "--partition", "bogus"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2 and "invalid choice" in r.stderr  # was silently accepted


def _hue(hx):
    _, a, b = color.lab(hx)
    return math.degrees(math.atan2(b, a)) % 360


def _hue_dist(a, b):
    return min(abs(a - b), 360 - abs(a - b))


def _card(cid, hexes):
    return {"id": cid, "figure_type": "overview",
            "measured": {"palette": [{"hex": h, "share": s, "neutral": False} for h, s in hexes] +
                                    [{"hex": "#ffffff", "share": 0.6, "neutral": True}]}}


def test_style_derive_on_neutral_strokes_keeps_tone_names_true(tmp_path):
    """editorial-minimal strokes 7 tones in near-black: hues came from the strokes and a derived 'green' was purple."""
    from paperfig.styles import derive_style, load_recipe
    cards = tmp_path / "cards"
    cards.mkdir()
    (cards / "a.json").write_text(json.dumps(_card("a", [("#2e7d32", 0.10), ("#6a1b9a", 0.08), ("#c62828", 0.06)])))
    base = load_recipe("editorial-minimal")["palette"]["tones"]
    out = derive_style("editorial-minimal", cards, tmp_path / "style.json")
    tones = load_recipe(str(out))["palette"]["tones"]
    changed = [k for k in tones if k in base and tones[k]["fill"] != base[k]["fill"]]
    assert changed
    for k in changed:  # each derived colour sits near the hue its name had in the base recipe
        assert _hue_dist(_hue(tones[k]["fill"]), _hue(base[k]["fill"])) < 60, (k, tones[k]["fill"], base[k]["fill"])


@pytest.mark.parametrize("base", ["soft-pastel", "editorial-minimal", "depth-cv"])
def test_style_derive_keeps_loss_lines_off_the_accent(tmp_path, base):
    from paperfig.styles import derive_style, load_recipe
    cards = tmp_path / "cards"
    cards.mkdir()
    (cards / "a.json").write_text(json.dumps(_card("a", [("#0f766e", 0.10), ("#1d4ed8", 0.08), ("#b45309", 0.06)])))
    b = load_recipe(base)["palette"]
    base_acc = b["tones"][b["roles"]["proposed"]["tone"]]["stroke"].lower()
    r = load_recipe(str(derive_style(base, cards, tmp_path / "style.json")))
    pal = r["palette"]
    acc = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"].lower()
    for kind, e in r["edges"].items():  # neither the derived accent nor the base's (editorial: loss = its teal accent)
        if kind != "data" and isinstance(e, dict) and e.get("color"):
            assert e["color"].lower() not in (acc, base_acc), (base, kind, e["color"])


def test_label_knockout_matches_the_panel_under_the_label(tmp_path):
    """The knock-out is the fill of the panel under the label (it was the lowest framed group holding both ends, else
    white — white boxes on tinted panels in the STORM corpus figure; checked there on the contact sheet)."""
    from paperfig import pipeline as P
    bp = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double", "legend": "none"},
          "root": {"id": "root", "layout": {"type": "row"}, "children": [
              {"id": "a", "label": "Input", "role": "io", "provenance": [{"source": "user", "ref": "t"}]},
              {"id": "p", "title": "Panel", "frame": "box", "tone": "blue", "layout": {"type": "row"},
               "provenance": [{"source": "user", "ref": "t"}], "children": [
                   {"id": "b", "label": "Encoder", "provenance": [{"source": "user", "ref": "t"}]},
                   {"id": "c", "label": "Decoder", "provenance": [{"source": "user", "ref": "t"}]}]}]},
          "edges": [{"id": "e1", "src": "b", "dst": "c", "label": "latent z", "provenance": [{"source": "user", "ref": "t"}]}]}
    f = tmp_path / "k.blueprint.json"
    f.write_text(json.dumps(bp))
    res = P.build(f, "soft-pastel", out_dir=tmp_path, formats=())
    xml = Path(res.drawio).read_text(encoding="utf-8")
    import re
    edge = re.search(r'<mxCell id="pf-e1"[^>]*style="([^"]*)"', xml).group(1)
    panel = re.search(r'<mxCell id="pf-p"[^>]*style="([^"]*)"', xml).group(1)
    bg = re.search(r"labelBackgroundColor=([^;]+)", edge).group(1)
    fill = re.search(r"fillColor=([^;]+)", panel).group(1)
    assert bg.lower() == fill.lower() != "#ffffff"


def test_absorb_keeps_small_text():
    from paperfig.absorb import _label_markup
    from paperfig.markup import to_html
    assert _label_markup(to_html("Encoder<br><small>12 layers</small>")) == "Encoder<br><small>12 layers</small>"
    assert _label_markup('<span style="color:red">x</span> y') == "x y"
