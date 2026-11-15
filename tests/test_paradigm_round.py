"""User comparison (2026-11-15) on their own unpublished paper: the author's own figure, drawn after studying CLIP, beat the blind run that
studied neighbouring papers. Five gaps, each with a backstop here:
1. the scout names the paradigm's source figure (CLIP for contrastive pretraining) and one concept adapts it;
2. losses that define the supervision structure (which pairs are positive: 1:1, N:1, N:M) are drawn, not
   dropped as "routine";
3. a multi-modal method colours by modality and marks its contribution with a ring, not a hue;
4. a module the text shows in its own figure is one box in the overview;
5. (assets) the author is asked for real samples — SKILL.md step 5, no code backstop beyond the plan's source."""
import json

from conftest import leaf
from paperfig import artifacts
from test_blind_round3 import _fig, _grammar
from test_plan import FACTS, _bp_with_panel, brief_v2, plan, write


def _refs(tmp_path, crop, *, paradigm=True, role=True, **extra):
    sel = {"title": "Learning Transferable Visual Models From Natural Language Supervision", "arxiv_id": "2103.00020",
           "url": "https://arxiv.org/abs/2103.00020", "venue": "ICML", "year": 2021, "why": "the paradigm's source",
           "figure": 1, "crop": str(crop), "caption": "Figure 1. Summary of our approach", "viewed": True}
    if role:
        sel["role"] = "paradigm"
    doc = {"paper_excluded": {"arxiv_id": None, "title": "A Case Paper"}, "queries": [{"query": "q q", "results": 3}],
           "selected": [sel], "rejected": [], "notes": [],
           "method_route": {"query": {"paradigm": "CLIP"}, "hits": ["clip-2021-fig1"], "used": ["clip-2021-fig1"]}}
    if paradigm:
        doc["paradigm"] = {"family": "contrastive image-text pretraining", "source": "CLIP", "selected": True}
    doc.update(extra)
    return write(tmp_path, "refs.json", doc)


# ---- 1. paradigm source
def test_refs_must_name_the_paradigm(tmp_path):
    crop = tmp_path / "c.png"
    crop.write_bytes(b"x")
    assert artifacts.validate("refs", _refs(tmp_path, crop)) == []
    assert any("paradigm" in p for p in artifacts.validate("refs", _refs(tmp_path, crop, paradigm=False)))
    assert any("role" in p for p in artifacts.validate("refs", _refs(tmp_path, crop, role=False)))
    none = _refs(tmp_path, crop, role=False, paradigm=False)
    d = json.loads(none.read_text())
    d["paradigm"] = {"family": "unrolled CS reconstruction", "source": "ISTA", "selected": False}
    none.write_text(json.dumps(d))
    assert any("why_not" in p for p in artifacts.validate("refs", none))
    d["paradigm"]["why_not"] = "ISTA has no method figure"
    none.write_text(json.dumps(d))
    assert artifacts.validate("refs", none) == []


def test_a_concept_must_adapt_the_paradigm_figure(tmp_path):
    crop = tmp_path / "c.png"
    crop.write_bytes(b"x")
    refs = _refs(tmp_path, crop)
    facts = write(tmp_path, "facts.json", {"facts": FACTS})
    probs = artifacts.validate("figure-plan", write(tmp_path, "p.json", plan()), facts=facts, refs=refs)
    assert any("paradigm" in p for p in probs), probs
    ok = plan(concepts=[{"id": "c1", "name": "x", "adapts": "2103.00020", "takes": "the similarity matrix"},
                        {"id": "c2", "name": "z", "adapts": "uformer-2022-fig2", "takes": "layout"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "q.json", ok), facts=facts, refs=refs) == []


# ---- 2. supervision structure
def _analysis(tmp_path, losses, **kw):
    a = {"losses": losses, "components": kw.get("components", []), "existing_figures": kw.get("figures", [])}
    return write(tmp_path, "analysis.json", a)


def _loss(name, positives):
    return {"name": name, "inputs": ["enc"], "positives": positives, "provenance": {"ref": "Sec. 3", "quote": "a quoted line"}}


def test_two_contrastive_objectives_need_a_supervision_decision(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    an = _analysis(tmp_path, [_loss("L_cap", "one-to-one"), _loss("L_lab", "many-to-one")])
    probs = artifacts.validate("figure-plan", write(tmp_path, "p.json", brief_v2()), blueprint=bpp, analysis=an)
    assert any("supervision" in p for p in probs), probs
    ok = brief_v2(supervision={"ids": ["out"], "how": "a pair matrix per objective"})
    assert artifacts.validate("figure-plan", write(tmp_path, "q.json", ok), blueprint=bpp, analysis=an) == []
    bad = brief_v2(supervision={"ids": ["ghost"], "how": "a pair matrix per objective"})
    assert any("ghost" in p for p in artifacts.validate("figure-plan", write(tmp_path, "r.json", bad), blueprint=bpp, analysis=an))
    # one contrastive loss alone needs no decision
    one = _analysis(tmp_path, [_loss("L_cap", "one-to-one")])
    assert artifacts.validate("figure-plan", write(tmp_path, "s.json", brief_v2()), blueprint=bpp, analysis=one) == []


def test_a_loss_that_shows_the_supervision_is_not_conventional(tmp_path):
    d = _fig([leaf("net", "Net", role="proposed", full_name="Net"), leaf("lab", "L_lab", role="loss")],
             [{"src": "net", "dst": "lab", "kind": "loss", "heads": "end"}])
    contrib = {"contributions": [{"ids": ["net"], "what": "the network"}]}
    assert any(f.code == "loss-conventional" for f in _grammar(tmp_path / "a", d, contrib))
    found = _grammar(tmp_path / "b", d, dict(contrib, supervision={"ids": ["lab"], "how": "N:1 matrix"}))
    assert not any(f.code == "loss-conventional" for f in found)


def test_pair_matrix_glyph_shows_the_positive_structure():
    from paperfig.glyphs import GLYPHS, glyph_svg
    assert "pair-matrix" in GLYPHS
    import re

    def positives(variant, grid):
        s = glyph_svg("pair-matrix", 60, 60, "#d1fae5", "#065f46", "#2563eb", variant=variant, grid=grid, seed="x")
        cells = re.findall(r'data-r="(\d+)" data-c="(\d+)" data-pos="1"', s)
        return [(int(r), int(c)) for r, c in cells]
    diag = positives("one-to-one", (5, 5))
    assert sorted(diag) == [(i, i) for i in range(5)]
    n1 = positives("many-to-one", (5, 3))
    assert sorted(r for r, _ in n1) == list(range(5))  # every row exactly one positive
    assert len({c for _, c in n1}) == 3  # every label column used, so some rows share one
    nm = positives("many-to-many", (5, 5))
    rows = [r for r, _ in nm]
    assert set(rows) == set(range(5)) and max(rows.count(r) for r in rows) >= 2
    assert positives("many-to-many", (5, 5)) == nm  # deterministic


# ---- 3. colour by modality, contribution as a ring
def test_ring_highlight_keeps_the_modality_fill_and_rings_the_contribution(tmp_path):
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    from paperfig.styles import load_recipe
    kids = [leaf("img", "Image enc.", tone="green"), leaf("agg", "Fusion", role="proposed", full_name="Fusion", tone="green"),
            leaf("txt", "Text enc.", tone="purple")]
    d = _fig(kids, [{"src": "img", "dst": "agg"}, {"src": "agg", "dst": "txt"}])
    d["figure"]["highlight"] = "ring"
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    cells = parse_cells(r.drawio.read_text())
    pal = load_recipe("soft-pastel")["palette"]
    green = pal["tones"]["green"]
    accent = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"]
    agg, img = cells["pf-agg"].style, cells["pf-img"].style
    assert agg["fillColor"].lower() == green["fill"].lower()  # the modality colour stays
    assert agg["strokeColor"].lower() == accent.lower()  # the ring is the contribution's accent
    assert float(agg["strokeWidth"]) >= 2 * float(img["strokeWidth"])
    from paperfig.blueprint import load
    from paperfig.grammar import check_grammar
    found = check_grammar(load(tmp_path / "b.json"), r.drawio, load_recipe("soft-pastel"),
                          {"color_semantics": {"green": "image side", "purple": "text side"}})
    assert not any(f.code == "tone-two-meanings" for f in found), [f.message for f in found]


def test_brief_v2_states_what_colour_encodes(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    b = brief_v2()
    b.pop("color_by", None)
    assert any("color_by" in p for p in artifacts.validate("figure-plan", write(tmp_path, "p.json", b), blueprint=bpp))


# ---- 4. a module with its own figure is one box
def test_a_module_shown_in_its_own_figure_is_collapsed(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))  # csfm with children msa, gf
    comps = [{"id": "csfm", "name": "CSFM"}, {"id": "msa", "name": "MSA", "parent": "csfm"},
             {"id": "gf", "name": "GF", "parent": "csfm"}]
    figs = [{"ref": "Fig. 3", "shows": ["csfm"], "provenance": {"ref": "Sec. 3.2", "quote": "as illustrated in Fig. 3"}}]
    an = _analysis(tmp_path, [], components=comps, figures=figs)
    probs = artifacts.validate("figure-plan", write(tmp_path, "p.json", brief_v2()), blueprint=bpp, analysis=an)
    assert any("Fig. 3" in p and "csfm" in p for p in probs), probs
    # the zoom-in is the author's own choice to keep: an explicit reason clears it
    ok = brief_v2(expanded_despite_figure=[{"id": "csfm", "why": "the overview's only mechanism"}])
    assert artifacts.validate("figure-plan", write(tmp_path, "q.json", ok), blueprint=bpp, analysis=an) == []


def test_pair_matrix_builds_end_to_end(tmp_path):
    """The glyph unit test bypassed the blueprint schema, which still rejected 'pair-matrix' (seen on a demo build)."""
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    m = leaf("m", "L_lab", visual="glyph", glyph="pair-matrix", variant="many-to-one", grid=[5, 3], tone="green",
             col_tone="purple", role="loss")
    d = _fig([leaf("e", "Encoder"), m], [{"src": "e", "dst": "m"}])
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    assert "image" in parse_cells(r.drawio.read_text())["pf-m"].style
