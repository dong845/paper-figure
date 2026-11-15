"""User request (2026-11-15): references found by content alone often draw a different architecture, so every
reference figure is annotated on several facets (method family, paradigm, architecture, training, modality, what
it depicts, how it is arranged, what to learn and what not to copy) in a controlled vocabulary, with a recipe to
download it again (no local image cache needed). A run retrieves by content (the scout) and by method (`kb match`).
The knowledge base keeps growing: run cards carry the same facets, and `kb gaps` says what to add next."""
import copy
import json

import pytest

from paperfig import kb

TAX = {"family": "contrastive-vlp", "paradigm": "CLIP", "paradigm_source": False,
       "architecture": ["two-tower"], "training": ["contrastive-1to1"], "modality": ["image", "text"],
       "depicts": ["real-photos", "similarity-matrix"], "task": "image-text pretraining"}
INS = {"structure": "two encoders meet in a matrix", "data": "real photos and typed captions",
       "emphasis": "positives tinted on the diagonal", "flow": "left to right", "avoid": "tiny cell labels"}


def _card(cid="x-2021-fig1", **kw):
    c = copy.deepcopy(json.loads(open(f"{kb.REPO_CARDS}/clip-2021-fig1.json").read()))
    c.update(id=cid, taxonomy=copy.deepcopy(TAX), insights=copy.deepcopy(INS),
             fetch={"arxiv_id": "2103.00020", "figure": 1})
    c.update(kw)
    return c


def test_taxonomy_values_come_from_the_vocabulary():
    assert kb.card_problems(_card()) == []
    bad = _card()
    bad["taxonomy"]["family"] = "clip-ish"
    bad["taxonomy"]["architecture"] = ["two-tower", "spaghetti"]
    probs = kb.card_problems(bad)
    assert any("clip-ish" in p for p in probs) and any("spaghetti" in p for p in probs), probs
    other = _card()
    other["taxonomy"]["family"] = "other"
    assert any("note" in p for p in kb.card_problems(other))  # 'other' must say what
    other["taxonomy"]["note"] = "a new family: event-camera reconstruction"
    assert kb.card_problems(other) == []


def test_fetch_recipe_resolves_arxiv_or_url():
    assert kb.fetch_recipe(_card()) == ("2103.00020", None, 1)
    c = _card(fetch={"pdf_url": "https://example.org/a.pdf", "key": "ex-a", "figure": 3})
    assert kb.fetch_recipe(c) == ("ex-a", "https://example.org/a.pdf", 3)
    plain = _card()
    plain.pop("fetch")  # older cards: the arXiv id from paper_url, the card's figure
    assert kb.fetch_recipe(plain) == ("2103.00020", None, 1)


def _kb_dir(tmp_path, cards):
    root = tmp_path / "kb"
    (root / "cards").mkdir(parents=True)
    for name in ("formats.json", "palettes.json", "typography.json", "styles.json", "principles.json", "taxonomy.json"):
        (root / name).write_text(open(f"{kb.REPO_KB}/{name}").read())
    (root / "domains").mkdir()
    for c in cards:
        (root / "cards" / f"{c['id']}.json").write_text(json.dumps(c))
    return root


def test_index_is_built_from_the_cards_and_kept_fresh(tmp_path):
    root = _kb_dir(tmp_path, [_card("a-2020-fig1"), _card("b-2021-fig2")])
    idx = kb.build_index(kb_dir=root, data=tmp_path / "data")
    assert [e["id"] for e in idx["figures"]] == ["a-2020-fig1", "b-2021-fig2"]
    e = idx["figures"][0]
    assert e["taxonomy"]["paradigm"] == "CLIP" and e["fetch"] == {"key": "2103.00020", "pdf_url": None, "figure": 1}
    assert e["insights"]["avoid"] and e["arrangement"]["partition"]
    kb.write_index(kb_dir=root, data=tmp_path / "data")
    assert not any("index" in p for p in kb.validate(kb_dir=root, data=tmp_path / "data"))
    (root / "cards" / "c-2022-fig1.json").write_text(json.dumps(_card("c-2022-fig1")))
    assert any("index.json" in p for p in kb.validate(kb_dir=root, data=tmp_path / "data"))  # a new card without a rebuilt index


def test_match_ranks_by_method_not_topic(tmp_path):
    clip = _card("clip-like-2021-fig1")
    sam = _card("sam-like-2023-fig1", taxonomy=dict(TAX, family="promptable-segmentation", paradigm="SAM",
                                                     architecture=["prompt-conditioned", "encoder-decoder"],
                                                     training=["supervised"], modality=["image"]))
    fusion = _card("fusion-2021-fig1", taxonomy=dict(TAX, family="fusion-vlp", paradigm="ALBEF",
                                                      architecture=["two-tower", "fusion-encoder"],
                                                      training=["contrastive-1to1", "multi-objective"]))
    root = _kb_dir(tmp_path, [clip, sam, fusion])
    kb.write_index(kb_dir=root, data=tmp_path / "data")
    hits = kb.match(paradigm="CLIP", family="contrastive-vlp", architecture=["two-tower"],
                    training=["contrastive-multi-positive"], kb_dir=root, data=tmp_path / "data")
    assert [h["id"] for h in hits][:2] == ["clip-like-2021-fig1", "fusion-2021-fig1"]
    assert "sam-like-2023-fig1" not in [h["id"] for h in hits]  # nothing in common
    assert hits[0]["why"]  # each hit says what matched
    assert kb.match(paradigm="CLIP", exclude_paper=["2103.00020"], kb_dir=root, data=tmp_path / "data") == []  # the paper itself is never a hit


def test_gaps_report_what_to_add_next(tmp_path):
    odd = _card("odd-2024-fig1", taxonomy=dict(TAX, family="other", note="event cameras"))
    odd2 = _card("odd2-2024-fig1", taxonomy=dict(TAX, family="other", note="Event cameras"))
    root = _kb_dir(tmp_path, [_card("a-2020-fig1"), odd, odd2])
    g = kb.gaps(kb_dir=root, data=tmp_path / "data")
    assert g["untagged"] == []
    assert any("event cameras" in n.lower() for n, _ in g["other_notes"])
    assert "promptable-segmentation" in g["thin_families"]  # vocabulary families with fewer than 3 figures


# ---- a run uses both routes: the analysis tags the paper, the scout records the method route
def test_analysis_taxonomy_uses_the_vocabulary(tmp_path):
    from paperfig import artifacts
    from test_artifacts import draft
    ok = draft()
    ok["taxonomy"] = {"family": "contrastive-vlp", "paradigm": "CLIP", "architecture": ["two-tower", "multi-stream"],
                      "training": ["contrastive-multi-positive"], "modality": ["image", "text"]}
    p = tmp_path / "a.json"
    p.write_text(json.dumps(ok))
    assert not any("taxonomy" in x for x in artifacts.validate("draft-analysis", p))
    ok["taxonomy"]["architecture"] = ["tower-ish"]
    p.write_text(json.dumps(ok))
    assert any("tower-ish" in x for x in artifacts.validate("draft-analysis", p))


def test_refs_method_route_uses_what_it_found(tmp_path):
    from paperfig import artifacts
    from test_paradigm_round import _refs
    crop = tmp_path / "c.png"
    crop.write_bytes(b"x")
    route = {"query": {"paradigm": "CLIP", "family": "contrastive-vlp"}, "hits": ["clip-2021-fig1", "albef-2021-fig1"],
             "used": ["albef-2021-fig1"]}
    assert artifacts.validate("refs", _refs(tmp_path, crop, method_route=route)) == []
    bad = dict(route, used=["mgca-2022-fig2"])
    assert any("mgca" in p for p in artifacts.validate("refs", _refs(tmp_path, crop, method_route=bad)))
    none = dict(route, used=[])
    assert any("why_not" in p for p in artifacts.validate("refs", _refs(tmp_path, crop, method_route=none)))
    none["why_not"] = "both hits draw the single-encoder variant, not two streams"
    assert artifacts.validate("refs", _refs(tmp_path, crop, method_route=none)) == []


def test_match_prefers_method_figures_and_the_source(tmp_path):
    """Measured on the real index (2026-11-15): a MedCLIP motivation teaser outranked CLIP's own figure."""
    teaser = _card("teaser-2022-fig2", figure_type="teaser", taxonomy=dict(TAX, training=["contrastive-multi-positive"]))
    source = _card("source-2021-fig1", figure_type="overview", taxonomy=dict(TAX, paradigm_source=True))
    root = _kb_dir(tmp_path, [teaser, source])
    hits = kb.match(paradigm="CLIP", family="contrastive-vlp", training=["contrastive-multi-positive"], kb_dir=root,
                    data=tmp_path / "data")
    assert [h["id"] for h in hits] == ["source-2021-fig1", "teaser-2022-fig2"]


RPDF = __import__("os").path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")


@pytest.mark.skipif(not __import__("os").path.isfile(RPDF), reason="bench pdf not cached")
def test_a_recorded_box_restores_the_exact_crop(tmp_path):
    """Re-download check (2026-11-15): 19 of 20 crops came back identical, one did not — the cached crop had been
    re-cropped by hand (the automatic crop cut its panel headings). The recipe keeps page + box, so the exact crop
    comes back whatever the automatic cropper does today."""
    from PIL import Image, ImageChops
    from paperfig import refs
    auto = refs.crop_figures(RPDF, tmp_path / "a", numbers={2})[0]
    out = refs.crop_bbox(RPDF, auto.page, auto.bbox, tmp_path / "b" / "fig2.png")
    a, b = Image.open(auto.png).convert("RGB"), Image.open(out).convert("RGB")
    assert a.size == b.size and ImageChops.difference(a, b).getbbox() is None
    taller = (auto.bbox[0], auto.bbox[1] - 20, auto.bbox[2], auto.bbox[3])  # a hand-widened box is honoured as given
    assert Image.open(refs.crop_bbox(RPDF, auto.page, taller, tmp_path / "c.png")).height > a.height


def test_an_offline_scout_needs_no_queries_paradigm_or_method_route(tmp_path):
    """The no-reference derivation run (ISTA-Net, 2026-11-15) had to invent placeholder queries, a paradigm and a
    method route to pass validation. Offline is a declared state: nothing selected, a note why."""
    import json as _j
    from paperfig import artifacts
    doc = {"paper_excluded": {"title": "X"}, "offline": True, "queries": [], "selected": [], "rejected": [],
           "notes": ["derivation test: no references"]}
    p = tmp_path / "refs.json"
    p.write_text(_j.dumps(doc))
    assert artifacts.validate("refs", p) == []
    p.write_text(_j.dumps(dict(doc, notes=[])))
    assert any("offline" in x for x in artifacts.validate("refs", p))
    p.write_text(_j.dumps(dict(doc, offline=False)))  # not offline: the routes are still required
    probs = artifacts.validate("refs", p)
    assert any("method_route" in x for x in probs) and any("paradigm" in x for x in probs), probs
