import pytest

from paperfig import styles as S
from paperfig.blueprint import load
from paperfig.errors import StyleError

SECTIONS = {"typography", "spacing", "palette", "shape", "effects", "tensor", "edges", "image"}
KINDS = ["data", "skip", "loss", "train_only", "infer_only", "grad", "control"]


def test_available_lists_four_recipes():
    assert {"soft-pastel", "depth-cv", "editorial-minimal", "drawio-default"} <= set(S.available())


@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv", "editorial-minimal", "drawio-default"])
def test_all_recipes_have_all_sections(rid):
    r = S.load_recipe(rid)
    assert SECTIONS <= set(r.data)
    for tone in ["blue", "green", "orange", "purple", "teal", "pink", "gray", "red", "yellow"]:
        assert set(r.data["palette"]["tones"][tone]) == {"fill", "stroke", "font"}


def test_unknown_recipe_raises():
    with pytest.raises(StyleError, match="unknown style 'nope'"):
        S.load_recipe("nope")


def test_compose_takes_effects_from_mix():
    r = S.compose("soft-pastel", {"effects": "depth-cv"})
    assert r.data["effects"]["shadow"] is True
    assert r.data["palette"] == S.load_recipe("soft-pastel").data["palette"]


def test_unknown_section_rejected():
    with pytest.raises(StyleError, match="section"):
        S.compose("soft-pastel", {"colour": "depth-cv"})


def test_proposed_role_uses_accent_and_bold(mini_bp):
    bp = load(mini_bp)
    r = S.load_recipe("soft-pastel")
    st = S.group_style(r, bp.index["csfm"])
    orange = r.data["palette"]["tones"]["orange"]
    assert st["strokeColor"] == orange["stroke"] and st["fontStyle"] == "1"


def test_nested_proposed_leaf_white_fill(mini_bp):
    bp = load(mini_bp)
    r = S.load_recipe("soft-pastel")
    st = S.node_style(r, bp.index["msa"], bp.index["csfm"])
    assert st["fillColor"] == "#ffffff"


def test_tone_overrides_role_default(mini_bp):
    bp = load(mini_bp)
    r = S.load_recipe("soft-pastel")
    st = S.node_style(r, bp.index["dec"], bp.root)
    assert st["fillColor"] == r.data["palette"]["tones"]["green"]["fill"]


def test_unknown_tone_raises(mini_bp):
    mini_bp["root"]["children"][1]["tone"] = "chartreuse"
    bp = load(mini_bp)
    with pytest.raises(StyleError, match="chartreuse"):
        S.node_style(S.load_recipe("soft-pastel"), bp.index["enc"], bp.root)


@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv", "editorial-minimal", "drawio-default"])
def test_every_edge_kind_styled_in_every_recipe(rid):
    r = S.load_recipe(rid)
    for k in KINDS:
        st = S.edge_style_for_kind(r, k)
        assert st["strokeColor"].startswith("#") and float(st["strokeWidth"]) > 0


@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv", "editorial-minimal", "drawio-default"])
def test_edge_kinds_distinguishable_without_color(rid):
    r = S.load_recipe(rid)
    sigs = {}
    for k in KINDS:
        st = S.edge_style_for_kind(r, k)
        sig = (st.get("dashed", "0"), st.get("dashPattern", ""), st.get("startArrow", "none"), st.get("endArrow"))
        assert sig not in sigs, f"{k} looks like {sigs.get(sig)} without color"
        sigs[sig] = k


def test_gradient_effect_adds_gradient_color(mini_bp):
    bp = load(mini_bp)
    st = S.node_style(S.load_recipe("depth-cv"), bp.index["enc"], bp.root)
    assert st["gradientColor"].startswith("#") and st["shadow"] == "1"


def test_style_string_roundtrip():
    s = S.to_style_string({"rounded": "1", "fillColor": "#fff"}, prefix="text")
    assert s == "text;rounded=1;fillColor=#fff;"


def test_colors_for_returns_fill_stroke_font(mini_bp):
    bp = load(mini_bp)
    fill, stroke, font = S.colors_for(S.load_recipe("soft-pastel"), bp.index["enc"], bp.root)
    assert all(c.startswith("#") for c in (fill, stroke, font))


def test_gradient_keeps_hue_not_muddy(mini_bp):
    from paperfig import color
    bp = load(mini_bp)
    r = S.load_recipe("depth-cv")
    st = S.group_style(r, bp.index["csfm"])
    fill = r.data["palette"]["tones"]["orange"]["fill"]
    g = st["gradientColor"]
    rr, gg, bb = color.hex_rgb(g)
    assert rr > gg > bb  # still orange, not gray-brown
    L0, a0, b0 = color.lab(fill)
    L1, a1, b1 = color.lab(g)
    assert (a1 ** 2 + b1 ** 2) ** 0.5 > (a0 ** 2 + b0 ** 2) ** 0.5  # chroma rises as it darkens


@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv"])
def test_reused_recedes_proposed_bold(rid, mini_bp):
    bp = load(mini_bp)
    r = S.load_recipe(rid)
    assert S.node_style(r, bp.index["enc"], bp.root)["fontStyle"] == "0"
    assert S.node_style(r, bp.index["msa"], bp.index["csfm"])["fontStyle"] == "1"


def test_inline_bold_respected_on_proposed(mini_bp):
    mini_bp["root"]["children"][1].update(role="proposed", label="<b>EncX</b><br>Encoder X", abbrev="EncX")
    bp = load(mini_bp)
    st = S.node_style(S.load_recipe("soft-pastel"), bp.index["enc"], bp.root)
    assert st["fontStyle"] == "0"


@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv"])
def test_reused_stroke_muted(rid, mini_bp):
    from paperfig import color
    bp = load(mini_bp)
    r = S.load_recipe(rid)
    re_ = S.node_style(r, bp.index["enc"], bp.root)
    pr = S.group_style(r, bp.index["csfm"])
    assert float(re_["strokeWidth"]) < float(pr["strokeWidth"])
    tone = r.data["palette"]["tones"]["blue"]["stroke"]
    def chroma(h):
        L, a, b = color.lab(h); return (a * a + b * b) ** 0.5
    assert chroma(re_["strokeColor"]) < chroma(tone)
