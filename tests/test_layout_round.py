"""User review (2026-11-15) of a blind run on their own (unpublished) paper: the expression was readable, but the
arrangement lost to the author's figure — the method has two streams, so the figure should be two panels, each
drawing its own losses; inputs sit at the outer edge; lines stay short; and the legend never sits in the middle of
the figure. Studied against 15 published method figures (ALBEF, BLIP, BLIP-2, MGCA, CycleGAN, UniCL, DreamBooth,
BYOL, data2vec, GLIP, DETR, CoCa, ImageBind, MedCLIP, Reflexion): every key sits at the outer edge or a corner,
or there is none and the lines are labelled directly. Each test here is a backstop for one of those rules."""
import copy
import json

from conftest import PROV, leaf
from paperfig import artifacts
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from test_plan import _bp_with_panel, brief_v2, write


def _build(tmp_path, d):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", None, out_dir=tmp_path / "o", formats=())
    return r, parse_cells(r.drawio.read_text())


def _three_rows(legend_at=None):
    """wide row / narrow row pushed right / wide row: the only empty space inside is left of the middle row."""
    def row(i, n, align="center"):
        return {"id": f"r{i}", "frame": "none", "layout": {"type": "row", "gap": "normal"},
                "children": [leaf(f"n{i}{k}", f"Block {i}{k}", role="proposed" if k == 0 else "reused",
                                  full_name=f"Block {i}{k}" if k == 0 else None) for k in range(n)]}
    kids = [row(0, 6), row(1, 2), row(2, 6)]
    for k in kids:
        for c in k["children"]:
            if c.get("full_name") is None:
                c.pop("full_name")
    fig = {"type": "overview", "venue": "neurips", "width": "double"}
    if legend_at:
        fig["legend_at"] = legend_at
    edges = [{"src": "n00", "dst": "n10", "kind": "loss", "heads": "end"}, {"src": "n10", "dst": "n20", "kind": "train_only"}]
    return {"schema_version": 1, "figure": fig,
            "root": {"id": "root", "layout": {"type": "column", "gap": "loose", "align": "end"}, "children": kids},
            "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}


def _content_box(cells):
    bs = [c.box for k, c in cells.items() if k.startswith("pf-") and c.box is not None and c.source is None]
    x0, y0 = min(b.x for b in bs), min(b.y for b in bs)
    x1, y1 = max(b.right for b in bs), max(b.bottom for b in bs)
    return x0, y0, x1, y1


def _legend_is_at_the_edge(cells):
    lg = cells["pfdeco-legend"].box
    x0, y0, x1, y1 = _content_box(cells)
    outside = lg.y >= y1 - 1 or lg.bottom <= y0 + 1 or lg.x >= x1 - 1 or lg.right <= x0 + 1
    if outside:
        return True
    # inside the content box: only in a corner — nothing between it and two adjacent sides
    others = [c.box for k, c in cells.items() if k.startswith("pf-") and c.box is not None and c.source is None
              and not (k == "pf-root")]
    left = not any(b.right <= lg.x and b.bottom > lg.y and b.y < lg.bottom for b in others)
    right = not any(b.x >= lg.right and b.bottom > lg.y and b.y < lg.bottom for b in others)
    top = not any(b.bottom <= lg.y and b.right > lg.x and b.x < lg.right for b in others)
    bottom = not any(b.y >= lg.bottom and b.right > lg.x and b.x < lg.right for b in others)
    return (left or right) and (top or bottom)


# ---- the legend sits at the edge, never between content
def test_legend_never_sits_between_content(tmp_path):
    _, cells = _build(tmp_path, _three_rows())
    assert "pfdeco-legend" in cells
    assert _legend_is_at_the_edge(cells), cells["pfdeco-legend"].box


def test_legend_at_is_honoured(tmp_path):
    for where in ("bottom", "right", "top"):
        _, cells = _build(tmp_path / where, _three_rows(where))
        lg = cells["pfdeco-legend"].box
        x0, y0, x1, y1 = _content_box(cells)
        assert {"bottom": lg.y >= y1 - 1, "right": lg.x >= x1 - 1, "top": lg.bottom <= y0 + 1}[where], (where, lg)


# ---- the figure's top level mirrors the method's streams; each stream draws its own losses
def _two_streams(frame="box"):
    def unit(uid, title, kids):
        return {"id": uid, "title": title, "frame": frame, "layout": {"type": "row", "gap": "normal"},
                "provenance": copy.deepcopy(PROV), "children": kids}
    a = unit("fdn", "(a) Main stream", [leaf("img_a", "Image enc."), leaf("l_cap_a", "L_cap", role="loss")])
    b = unit("ref", "(b) Auxiliary stream", [leaf("img_b", "Image enc."), leaf("agg", "Aggregator", role="proposed",
                                                                                   full_name="Aggregator"),
                                             leaf("l_cap_b", "L_cap", role="loss"), leaf("l_aux", "L_aux", role="loss")])
    edges = [{"src": "img_a", "dst": "l_cap_a", "kind": "loss", "heads": "end"},
             {"src": "img_b", "dst": "agg"}, {"src": "agg", "dst": "l_aux", "kind": "loss", "heads": "end"},
             {"src": "img_b", "dst": "l_cap_b", "kind": "loss", "heads": "end"}]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "column", "gap": "normal"}, "children": [a, b]},
            "edges": [dict(e, provenance=copy.deepcopy(PROV)) for e in edges]}


QUOTE = {"ref": "Sec. 3", "quote": "a quoted line from the text"}


def _streams_analysis(tmp_path, conventional=False):
    comps = [{"id": i, "name": n, "role": r, "what": "w", "provenance": QUOTE}
             for i, n, r in (("img_enc", "Image encoder", "reused"), ("agg", "Aggregator", "proposed"),
                             ("l_cap", "L_cap", "loss"), ("l_aux", "L_aux", "loss"))]
    pos = "none" if conventional else "one-to-one"  # contrastive losses define the supervision: they must be drawn
    losses = [{"name": "L_cap", "inputs": ["img_enc"], "positives": pos, "provenance": QUOTE},
              {"name": "L_aux", "inputs": ["agg"], "positives": "one-way" if not conventional else "none", "provenance": QUOTE}]
    stages = [{"id": "fdn_s", "name": "Main stream", "members": ["img_enc", "l_cap"], "losses": ["l_cap"],
               "provenance": QUOTE},
              {"id": "ref_s", "name": "Auxiliary stream", "members": ["img_enc", "agg", "l_aux"],
               "losses": ["l_cap", "l_aux"], "provenance": QUOTE}]
    return write(tmp_path, "analysis.json", {"components": comps, "stages": stages, "losses": losses, "existing_figures": []})


DRAWN = [{"ids": ["l_cap"], "into": ["l_cap_a", "l_cap_b"], "how": "once in each stream"},
         {"ids": ["img_enc"], "into": ["img_a", "img_b"], "how": "the shared encoder drawn in each stream"}]


def _layout(**kw):
    lay = {"skeleton_from": "dreambooth-2022-fig3", "takes": "one lane per stream, each lane ends in its own loss",
           "partition": "lanes", "why": "the text trains two streams", "inputs_at": "left", "legend_at": "auto",
           "units": [{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]},
                     {"id": "ref", "of": "ref_s", "losses": ["l_cap_b", "l_aux"]}]}
    lay.update(kw)
    return lay


def _check(tmp_path, name, layout, bp=None, drawn=DRAWN, conventional=False):
    bpp = write(tmp_path, f"bp-{name}.json", bp or _two_streams())
    an = _streams_analysis(tmp_path, conventional)
    p = brief_v2(layout=layout, drawn_as=drawn, contributions=[{"name": "Aggregator", "solves": "x y", "shown_by": "a b",
                                                               "ids": ["agg"]}],
                 mechanism=[{"explains": "how it aggregates", "ids": ["agg"]}], infer_kept=["img_a"],
                 key_representations=[], core=["img_a", "agg"],
                 **({} if conventional else {"supervision": {"ids": ["l_cap_a"], "how": "a pair matrix per objective"}}))
    return artifacts.validate("figure-plan", write(tmp_path, f"p-{name}.json", p), blueprint=bpp, analysis=an)


def test_brief_v2_needs_a_layout(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    b = brief_v2()
    b.pop("layout", None)
    assert any("layout" in p for p in artifacts.validate("figure-plan", write(tmp_path, "p.json", b), blueprint=bpp))


def test_layout_skeleton_comes_from_a_reference(tmp_path, mini_bp):
    bpp = write(tmp_path, "bp.json", _bp_with_panel(mini_bp))
    bad = brief_v2(layout=dict(brief_v2()["layout"], skeleton_from="my-imagination"))
    assert any("skeleton_from" in p for p in artifacts.validate("figure-plan", write(tmp_path, "p.json", bad), blueprint=bpp))


def test_each_stream_is_a_unit_that_draws_its_own_losses(tmp_path):
    assert _check(tmp_path, "ok", _layout()) == []
    # one panel for everything: the two streams are not told apart
    probs = _check(tmp_path, "single", _layout(partition="single", units=[]))
    assert any("stream" in p.lower() and "ref_s" in p for p in probs), probs
    # the auxiliary stream also optimises L_cap (the text's total loss) but its panel does not draw it
    bare = _two_streams()
    bare["root"]["children"][1]["children"] = [c for c in bare["root"]["children"][1]["children"] if c["id"] != "l_cap_b"]
    bare["edges"] = [e for e in bare["edges"] if e["dst"] != "l_cap_b"]
    one = [dict(DRAWN[0], into=["l_cap_a"]), DRAWN[1]]
    probs = _check(tmp_path, "lossless", _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]},
                                                        {"id": "ref", "of": "ref_s", "losses": ["l_aux"]}]),
                   bp=bare, drawn=one)
    assert any("l_cap" in p and "ref" in p for p in probs), probs
    # a unit's loss must sit inside that unit
    probs = _check(tmp_path, "misplaced", _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]},
                                                         {"id": "ref", "of": "ref_s", "losses": ["l_cap_a", "l_aux"]}]))
    assert any("l_cap_a" in p and "inside" in p for p in probs), probs
    # an explicit reason keeps a loss out of a unit
    ok = _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "losses": ["l_aux"]}],
                 not_drawn=[{"loss": "l_cap", "unit": "ref", "why": "the caption says both streams share the four terms"}])
    assert _check(tmp_path, "reasoned", ok, bp=bare, drawn=one) == []
    # user's choice (2026-11-15): a conventional loss (reconstruction, KL, actor-critic) may go to the caption —
    # DreamerV3's authors drew none; losses that define the supervision must be drawn in every stream
    plain = _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "losses": ["l_aux"]}])
    assert _check(tmp_path, "conventional", plain, bp=bare, drawn=one, conventional=True) == []


def test_a_unit_is_an_enclosed_region(tmp_path):
    probs = _check(tmp_path, "frameless", _layout(), bp=_two_streams(frame="none"))
    assert any("fdn" in p and "frame" in p for p in probs), probs


def test_layout_legend_place_matches_the_blueprint(tmp_path):
    probs = _check(tmp_path, "legend", _layout(legend_at="bottom"))
    assert any("legend_at" in p for p in probs), probs
    bp = _two_streams()
    bp["figure"]["legend_at"] = "bottom"
    assert _check(tmp_path, "legend2", _layout(legend_at="bottom"), bp=bp) == []


def test_an_edge_between_two_units_needs_a_reason(tmp_path):
    from test_blind_round3 import _grammar
    d = _two_streams()
    d["edges"].append(dict(src="agg", dst="l_cap_a", kind="loss", heads="end", provenance=copy.deepcopy(PROV)))
    lay = _layout()
    found = _grammar(tmp_path / "a", d, {"layout": lay})
    assert any(f.code == "unit-crossing" for f in found), [f.code for f in found]
    found = _grammar(tmp_path / "b", d, {"layout": dict(lay, links=[{"src": "agg", "dst": "l_cap_a", "why": "a cross-stream loss"}])})
    assert not any(f.code == "unit-crossing" for f in found)


def test_kb_query_lists_arrangements_from_every_domain():
    """A layout skeleton travels across domains (PaperBanana: random references help structure almost as much as
    matched ones), so the brief lists every card that records its arrangement, not only the paper's domain."""
    from paperfig.kb import query
    q = query("speech")
    ids = {a["id"] for a in q["arrangements"]}
    assert {"dreambooth-2022-fig3", "byol-2020-fig2", "cyclegan-2017-fig3"} <= ids
    assert all(a["partition"] and a["losses_at"] and a["legend_at"] for a in q["arrangements"])


# ---- user review of the v3 run (2026-11-15): all of a stream's losses, encoders never merged, quoted inputs
def test_one_box_may_not_stand_for_several_losses_of_a_stream(tmp_path):
    bp = _two_streams()
    ref = bp["root"]["children"][1]
    ref["children"] = [c for c in ref["children"] if c["id"] != "l_cap_b"] + [leaf("l_all_b", "L_fdn as in (a)", role="loss")]
    bp["edges"] = [e for e in bp["edges"] if e["dst"] != "l_cap_b"] + [dict(src="img_b", dst="l_all_b", kind="loss", heads="end", provenance=copy.deepcopy(PROV))]
    an_extra = [{"ids": ["l_cap"], "into": ["l_cap_a", "l_all_b"], "how": "the four terms in one box"},
                {"ids": ["l_aux"], "into": ["l_all_b"], "how": "merged"}, DRAWN[1]]
    lay = _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "losses": ["l_all_b"]}])
    probs = _check(tmp_path, "collapsed", lay, bp=bp, drawn=an_extra)
    assert any("l_all_b" in p and "each" in p for p in probs), probs


def test_components_drawn_apart_somewhere_are_not_merged_elsewhere(tmp_path):
    bp = _two_streams()
    a = bp["root"]["children"][0]
    a["children"].insert(1, leaf("txt_a", "Text enc."))
    b = bp["root"]["children"][1]
    b["children"][0] = leaf("enc_b", "F_I, F_T (shared)")
    bp["edges"] = [dict(e, src="enc_b") if e["src"] == "img_b" else e for e in bp["edges"]]
    drawn = [DRAWN[0], {"ids": ["img_enc"], "into": ["img_a"], "how": "image tower"},
             {"ids": ["txt_enc"], "into": ["txt_a"], "how": "text tower"},
             {"ids": ["img_enc", "txt_enc"], "into": "enc_b", "how": "both towers in one box"}]
    probs = _check(tmp_path, "merged", _layout(), bp=bp, drawn=drawn)
    assert any("enc_b" in p and "merged" in p for p in probs), probs


def test_quote_cards_are_tinted_dashed_and_take_their_tone(tmp_path):
    q = leaf("cap", "<i>“a dog running on wet grass”</i><br><small>caption · 1 per image</small>", visual="textcard",
             card_style="quote", tone="purple")
    _, cells = _build(tmp_path, {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
                                 "root": {"id": "root", "layout": {"type": "row"}, "children": [q, leaf("e", "Text enc.")]},
                                 "edges": [dict(src="cap", dst="e", provenance=copy.deepcopy(PROV))]})
    from paperfig.styles import load_recipe
    pal = load_recipe("soft-pastel")["palette"]["tones"]["purple"]
    st = cells["pf-cap"].style
    assert st.get("dashed") == "1" and st["fillColor"].lower() == pal["fill"].lower()
    assert st["strokeColor"].lower() == pal["stroke"].lower()


def test_lanes_are_allowed_to_be_tall(tmp_path):
    """User 2026-11-15: size is never the limit — stacked streams make a tall figure, and that is right."""
    from test_blind_round3 import _grammar
    d = _two_streams()
    for k in range(2, 5):  # four stacked lanes: clearly taller than wide
        d["root"]["children"].append({"id": f"u{k}", "title": f"({k}) stream", "frame": "box", "provenance": copy.deepcopy(PROV),
                                      "layout": {"type": "row"}, "children": [leaf(f"x{k}", f"Block {k}")]})
    found = _grammar(tmp_path / "a", d, {})
    assert any(f.code == "aspect-tall" for f in found)
    found = _grammar(tmp_path / "b", d, {"layout": _layout()})
    assert not any(f.code == "aspect-tall" for f in found)


def test_a_figure_taller_than_a_page_is_an_error(tmp_path):
    """v4 run (2026-11-15): 'size is not the limit' grew a two-stream figure to 14 in tall at 6.875 in wide — it
    cannot be placed on any page. The author's own figure for the same paper is ~4.8 in tall at that width."""
    from paperfig.lint import page_height_findings
    assert page_height_findings(4.8, "cvpr") == []
    warn = page_height_findings(6.5, "cvpr")
    assert [f[0] for f in warn] == ["page-share"] and warn[0][1] == "warn"
    err = page_height_findings(14.0, "cvpr")
    assert [f[0] for f in err] == ["page-overflow"] and err[0][1] == "error"


def test_quote_cards_leave_room_under_the_role_line(tmp_path):
    """v4 run: the small role line touched the quote card's dashed bottom border."""
    lab = "<i>“a dog running on wet grass”</i><br><small>caption · 1 per image</small>"
    def h(style):
        _, cells = _build(tmp_path / style, {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
                                             "root": {"id": "root", "layout": {"type": "row"},
                                                      "children": [leaf("c", lab, visual="textcard", card_style=style, tone="purple")]},
                                             "edges": []})
        return cells["pf-c"].box.h
    assert h("quote") > h("plain") + 2
