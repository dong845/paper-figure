import json

import pytest
from PIL import Image, ImageDraw

from paperfig import kb
from paperfig.color import de2000
from paperfig.errors import PaperFigError


def card(cid="restormer-fig2", url="https://arxiv.org/abs/2111.09881", fig=2, domains=("image-restoration",), **kw):
    c = {
        "id": cid, "title": "Restormer: Efficient Transformer for High-Resolution Image Restoration",
        "paper_url": url, "venue": "CVPR", "year": 2022, "domains": list(domains), "figure": fig,
        "figure_type": "overview", "layout_pattern": "u-shape", "flow_direction": "left-to-right",
        "grouping": "encoder levels left, decoder right, refinement on top",
        "shapes_depth": "flat rounded boxes, light fills",
        "elements": ["thumbnail", "operator-glyph", "legend"],
        "proposed_highlight": "MDTA and GDFN named in the legend and expanded as detail panels",
        "lesson": "Detail panels sit in the overview's empty corner, linked by colour.",
        "source": {"paper_url": url, "figure": fig, "read": "figure crop and caption"},
        "measured": {"source": "computed: paperfig kb measure", "palette": [{"hex": "#f4a582", "share": 0.4, "neutral": False}],
                     "whitespace_ratio": 0.6, "ink_ratio": 0.4, "aspect": 2.6, "size_px": [1300, 500]},
    }
    c.update(kw)
    return c


def write_kb(root, cards=(), palettes=None, rules=None, domains=None, styles=None):
    (root / "cards").mkdir(parents=True)
    (root / "domains").mkdir()
    (root / "formats.json").write_text(json.dumps({"venues": {"cvpr": {
        "name": "CVPR", "columns": 2, "textwidth_in": 6.875, "columnwidth_in": 3.28125,
        "evidence": "cvpr.sty: \\textwidth 6.875in", "source_url": "https://github.com/cvpr-org/author-kit", "verified": "2026-11-12"}}}))
    (root / "palettes.json").write_text(json.dumps({"palettes": palettes if palettes is not None else {
        "okabe-ito": {"name": "Okabe-Ito", "kind": "qualitative", "colors": ["#E69F00", "#56B4E9"],
                      "source": {"url": "https://jfly.uni-koeln.de/color/", "read": "Fig. 16 colour set"}}}}))
    (root / "typography.json").write_text(json.dumps({"rules": rules if rules is not None else []}))
    (root / "styles.json").write_text(json.dumps({"styles": styles if styles is not None else {}}))
    for d in domains or []:
        (root / "domains" / f"{d['id']}.json").write_text(json.dumps(d))
    for c in cards:
        (root / "cards" / f"{c['id']}.json").write_text(json.dumps(c))
    return root


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "kb", tmp_path / "data"


def test_card_schema():
    assert kb.card_problems(card()) == []
    bad = card()
    del bad["lesson"]
    assert any("lesson" in p for p in kb.card_problems(bad))
    assert any("figure_type" in p for p in kb.card_problems(card(figure_type="poster")))
    m = card()
    m["measured"]["source"] = "eyeballed"
    assert any("computed:" in p for p in kb.card_problems(m))


def test_validate_rejects_unsourced(dirs):
    root, data = dirs
    write_kb(root, palettes={"p": {"name": "P", "kind": "qualitative", "colors": ["#123456"]}},
             rules=[{"id": "r1", "text": "Use sans-serif labels.", "applies_to": ["all"]}])
    probs = kb.validate(root, data)
    assert any("palettes.p" in p and "source" in p for p in probs)
    assert any("typography.r1" in p and "source" in p for p in probs)


def test_validate_rejects_duplicate_card(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a"), card("b")])  # same paper + figure under two ids
    assert any("duplicate" in p for p in kb.validate(root, data))


def test_validate_domain_conventions_need_two_known_cards(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a")], domains=[{"id": "image-restoration", "name": "Image restoration", "conventions": [
        {"text": "U-shaped encoder-decoder", "evidence_cards": ["a"]},
        {"text": "Thumbnails at both ends", "evidence_cards": ["a", "ghost"]}]}])
    probs = kb.validate(root, data)
    assert any("at least 2" in p for p in probs) and any("ghost" in p for p in probs)


def test_validate_clean_kb_has_no_problems(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a"), card("b", url="https://arxiv.org/abs/2204.04676", fig=3)],
             domains=[{"id": "image-restoration", "name": "Image restoration",
                       "conventions": [{"text": "U-shaped encoder-decoder", "evidence_cards": ["a", "b"]}]}])
    assert kb.validate(root, data) == []


def test_query_merges_user_layer(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a")])
    kb.add_card(card("u", url="https://arxiv.org/abs/2204.04676", fig=1), data=data, kb_dir=root)
    brief = kb.query("image-restoration", "cvpr", kb_dir=root, data=data)
    assert {c["id"]: c["layer"] for c in brief["cards"]} == {"a": "repo", "u": "user"}
    assert brief["format"]["textwidth_in"] == 6.875 and brief["palettes"]


def test_query_excludes_paper(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a", url="https://arxiv.org/abs/2111.09881v3"), card("b", url="https://arxiv.org/abs/2204.04676", fig=3)])
    for ex in ("2111.09881", "arXiv:2111.09881v1", "https://arxiv.org/pdf/2111.09881",
               "Restormer: efficient transformer for high-resolution image restoration"):
        ids = [c["id"] for c in kb.query("image-restoration", exclude_paper=ex, kb_dir=root, data=data)["cards"]]
        assert "a" not in ids, ex
    assert any("excluded" in n for n in kb.query("image-restoration", exclude_paper="2111.09881", kb_dir=root, data=data)["notes"])


def test_query_unknown_domain_and_venue_say_so(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a")])
    brief = kb.query("quantum-chemistry", "nowhere", kb_dir=root, data=data)
    assert brief["cards"] == [] and brief["format"] is None and brief["domain"] is None
    assert any("quantum-chemistry" in n for n in brief["notes"]) and any("nowhere" in n for n in brief["notes"])


def test_add_card_dedupes_and_validates(dirs):
    root, data = dirs
    write_kb(root, cards=[card("a")])
    with pytest.raises(PaperFigError, match="already"):
        kb.add_card(card("dup", url="https://arxiv.org/abs/2111.09881v2"), data=data, kb_dir=root)  # repo has it
    p = kb.add_card(card("n", url="https://arxiv.org/abs/2204.04676", fig=1), data=data, kb_dir=root)
    assert p.parent == data / "cards"
    with pytest.raises(PaperFigError, match="already"):
        kb.add_card(card("n2", url="https://arxiv.org/abs/2204.04676", fig=1), data=data, kb_dir=root)
    with pytest.raises(PaperFigError, match="lesson"):
        bad = card("x", url="https://arxiv.org/abs/1111.11111")
        del bad["lesson"]
        kb.add_card(bad, data=data, kb_dir=root)
    assert sorted(f.name for f in (data / "cards").iterdir()) == ["n.json"]


def test_add_card_refuses_path_tricks(dirs):
    root, data = dirs
    write_kb(root)
    with pytest.raises(PaperFigError, match="id"):
        kb.add_card(card("../evil", url="https://arxiv.org/abs/1111.11111"), data=data, kb_dir=root)


def test_measure_palette_on_synthetic(tmp_path):
    from paperfig.cardmeasure import measure

    cols = {"#d6604d": (0, 0, 300, 200), "#4393c3": (300, 0, 500, 200), "#1b7837": (500, 0, 600, 200)}
    im = Image.new("RGB", (800, 300), "white")
    d = ImageDraw.Draw(im)
    for hexc, box in cols.items():
        d.rectangle(box, fill=hexc)
    p = tmp_path / "s.png"
    im.save(p)
    m = measure(p)
    assert m["source"].startswith("computed:")
    got = [e["hex"] for e in m["palette"]]
    assert len(got) == 3, m["palette"]
    for want in cols:
        assert min(de2000(want, g) for g in got) < 3, (want, got)
    share = {g["hex"]: g["share"] for g in m["palette"]}
    red = min(got, key=lambda g: de2000(g, "#d6604d"))
    assert 0.45 < share[red] < 0.55  # 300 of 600 inked columns
    assert 0.4 < m["whitespace_ratio"] < 0.55 and m["aspect"] == pytest.approx(800 / 300, rel=0.01)


def test_measure_blank_image_reports_no_palette(tmp_path):
    from paperfig.cardmeasure import measure

    p = tmp_path / "w.png"
    Image.new("RGB", (100, 50), "white").save(p)
    m = measure(p)
    assert m["palette"] == [] and m["whitespace_ratio"] == 1.0


def test_repo_kb_validates(tmp_path):
    assert kb.validate(data=tmp_path / "no-user-layer") == []  # the shipped layer alone


def test_measure_keeps_small_accent_colours(tmp_path):
    from paperfig.cardmeasure import measure

    im = Image.new("RGB", (900, 300), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 600, 200), fill="#9e9e9e")  # big neutral area (text, strokes, gray boxes)
    d.rectangle((650, 0, 750, 100), fill="#3e7cb1")  # blue accent
    d.rectangle((800, 0, 820, 60), fill="#4daf4a")  # small green accent: <1% of the ink
    p = tmp_path / "a.png"
    im.save(p)
    got = measure(p)["palette"]
    for want in ("#3e7cb1", "#4daf4a", "#9e9e9e"):
        assert min(de2000(want, g["hex"]) for g in got) < 3, (want, got)
    assert next(g for g in got if de2000("#9e9e9e", g["hex"]) < 3)["neutral"]


def test_palette_safety_is_computed_and_checked(dirs):
    s = kb.palette_safety(["#000000", "#ffffff", "#ff0000", "#00ff00"])
    assert s["source"].startswith("computed:")
    assert s["min_de"]["normal"] > 20 and s["min_de"]["deutan"] < s["min_de"]["normal"]  # red/green collapse for deutans
    assert set(s["min_de"]) == {"normal", "protan", "deutan", "tritan", "gray"}
    root, data = dirs
    pal = {"name": "P", "kind": "qualitative", "colors": ["#000000", "#ffffff"],
           "source": {"url": "https://example.org/p", "read": "table 1"}}
    write_kb(root, palettes={"p": dict(pal, safety=kb.palette_safety(pal["colors"]))})
    assert kb.validate(root, data) == []
    stale = dict(pal, safety=dict(kb.palette_safety(pal["colors"]), min_de={"normal": 1.0, "protan": 1.0, "deutan": 1.0,
                                                                             "tritan": 1.0, "gray": 1.0}))
    write_kb(tmp := root.parent / "kb2", palettes={"p": stale})
    assert any("stale" in p for p in kb.validate(tmp, data))


def test_typography_lint_refs_must_exist(dirs):
    root, data = dirs
    src = {"url": "https://example.org/g", "quote": "Lines must be thick."}
    write_kb(root, rules=[{"id": "r1", "text": "Thick lines.", "applies_to": ["all"], "source": src, "lint": ["min-font"]},
                          {"id": "r2", "text": "Thick lines.", "applies_to": ["all"], "source": src, "lint": ["no-such-check"]}])
    probs = kb.validate(root, data)
    assert len(probs) == 1 and "no-such-check" in probs[0]


def test_lint_checks_constant_matches_source():
    import re
    from pathlib import Path

    from paperfig import lint

    src = Path(lint.__file__).read_text()
    assert set(re.findall(r'add\("([a-z-]+)"', src.split("CHECKS = frozenset", 1)[1].split("})", 1)[1])) == lint.CHECKS
    assert {"min-font", "gray-confusable", "tone-confusable", "edge-kind-color-only"} <= lint.CHECKS
