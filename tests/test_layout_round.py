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
           "units": [{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]},
                     {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_cap_b", "l_aux"]}]}
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
    probs = _check(tmp_path, "lossless", _layout(units=[{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]},
                                                        {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_aux"]}]),
                   bp=bare, drawn=one)
    assert any("l_cap" in p and "ref" in p for p in probs), probs
    # a unit's loss must sit inside that unit
    probs = _check(tmp_path, "misplaced", _layout(units=[{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]},
                                                         {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_cap_a", "l_aux"]}]))
    assert any("l_cap_a" in p and "inside" in p for p in probs), probs
    # an explicit reason keeps a loss out of a unit
    ok = _layout(units=[{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_aux"]}],
                 not_drawn=[{"loss": "l_cap", "unit": "ref", "why": "the caption says both streams share the four terms"}])
    assert _check(tmp_path, "reasoned", ok, bp=bare, drawn=one) == []
    # user's choice (2026-11-15): a conventional loss (reconstruction, KL, actor-critic) may go to the caption —
    # DreamerV3's authors drew none; losses that define the supervision must be drawn in every stream
    plain = _layout(units=[{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_aux"]}])
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
    lay = _layout(units=[{"id": "fdn", "of": "fdn_s", "job": "teach", "losses": ["l_cap_a"]}, {"id": "ref", "of": "ref_s", "job": "extend", "losses": ["l_all_b"]}])
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


# ---- v5 vs the author's figure: matrices with named rows and columns, sized for the 7 pt floor
def test_pair_matrix_names_its_rows_and_columns(tmp_path):
    from paperfig.glyphs import glyph_svg
    s = glyph_svg("pair-matrix", 120, 120, "#d1fae5", "#065f46", "#2563eb", variant="one-to-one", grid=(4, 4),
                  seed="x", axes=("z", "t"), font_px=9.0)
    import re
    rows = re.findall(r'data-axis="row"[^>]*>z<tspan[^>]*>(\d)</tspan>', s)
    cols = re.findall(r'data-axis="col"[^>]*>t<tspan[^>]*>(\d)</tspan>', s)
    assert rows == ["1", "2", "3", "4"] and cols == ["1", "2", "3", "4"], s[:400]


def test_named_matrix_grows_to_fit_its_labels_and_counts_for_the_font_floor(tmp_path):
    from paperfig.lint import check
    from paperfig.blueprint import load
    from paperfig.styles import load_recipe
    def build(name, **kw):
        m = leaf("m", "L<sub>cap</sub>", visual="glyph", glyph="pair-matrix", variant="one-to-one", grid=[5, 5],
                 tone="green", col_tone="purple", **kw)
        r, cells = _build(tmp_path / name, {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                                             "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf("e", "Encoder"), m]},
                                             "edges": [dict(src="e", dst="m", provenance=copy.deepcopy(PROV))]})
        return r, cells
    _, plain = build("plain")
    r, named = build("named", axes=["z", "t"])
    assert named["pf-m"].box.w > plain["pf-m"].box.w  # room for z1..z5 / t1..t5 at the label size
    assert "pfglyphfont" in named["pf-m"].style
    from paperfig.lint import figure_bbox, pt_per_px, smallest_text
    rec = load_recipe("soft-pastel")
    scale = pt_per_px(figure_bbox(named, rec), 6.875)
    glyph_pt = float(named["pf-m"].style["pfglyphfont"]) * scale
    small = smallest_text(named, rec, scale)
    assert small[0] <= glyph_pt + 1e-6  # the matrix's own text is one of the candidates for the floor
    named["pf-m"].style["pfglyphfont"] = "2.0"  # a tiny header label is caught as the smallest text
    assert smallest_text(named, rec, scale)[1] == "pf-m"


# ---- v6 vs the author's figure: the run had to search node ids to get the pattern it wanted, and every
# image-side arrow jogged under the matrix's name (the port moved off the label)
def test_pair_matrix_positives_are_set_by_the_blueprint_not_the_id(tmp_path):
    import re
    import pytest
    from paperfig.glyphs import glyph_svg
    def on(s):
        return {(int(a), int(b)) for a, b in re.findall(r'data-r="(\d+)" data-c="(\d+)" data-pos="1"', s)}
    kw = dict(variant="many-to-one", grid=(3, 2), positives=[[1, 1], [2, 1], [3, 2]])
    a = glyph_svg("pair-matrix", 90, 90, "#d1fae5", "#065f46", "#2563eb", seed="l_lab_a", **kw)
    b = glyph_svg("pair-matrix", 90, 90, "#d1fae5", "#065f46", "#2563eb", seed="l_lab_b", **kw)
    assert on(a) == {(0, 0), (1, 0), (2, 1)} and a == b  # 1-based [row, col], the same in both lanes
    with pytest.raises(ValueError):
        glyph_svg("pair-matrix", 90, 90, "#d1fae5", "#065f46", "#2563eb", seed="x", grid=(3, 3), positives=[[4, 1]])


def test_a_bad_positive_cell_is_a_blueprint_error(tmp_path):
    import pytest
    from paperfig.blueprint import BlueprintError, load
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [
             leaf("m", "L", visual="glyph", glyph="pair-matrix", grid=[3, 3], positives=[[1, 1], [3, 4]])]},
         "edges": []}
    (tmp_path / "b.json").write_text(json.dumps(d))
    with pytest.raises(BlueprintError, match="positives"):
        load(tmp_path / "b.json")


def test_image_side_arrow_enters_the_row_names_straight(tmp_path):
    """An encoder bar under a row of matrices: each arrow rises straight into the matrix's row-name column (z_1 …),
    beside the matrix's name — no jog to get round the name."""
    from paperfig.lint import _polyline
    mats = [leaf(f"m{i}", f"L<sub>{k}</sub><br>1:1", visual="glyph", glyph="pair-matrix", variant="one-to-one",
                 grid=[3, 3], tone="green", col_tone="purple", axes=["z", "t"]) for i, k in enumerate(("cap", "lab", "con"))]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column", "gap": "loose"}, "children": [
             {"id": "row", "frame": "none", "layout": {"type": "row", "gap": "loose"}, "children": mats},
             leaf("enc", "Image encoder F<sub>I</sub>", tone="green", size=[520, 40])]},
         "edges": [dict(src="enc", dst=f"m{i}", kind="loss", heads="end", provenance=copy.deepcopy(PROV)) for i in range(3)]}
    _, cells = _build(tmp_path, d)
    edges = [c for c in cells.values() if c.edge and c.target in {f"pf-m{i}" for i in range(3)}]
    assert len(edges) == 3
    for e in edges:
        poly = _polyline(e, cells)
        xs = {round(p[0], 1) for p in poly}
        assert len(xs) == 1, (e.id, poly)  # one vertical run, no jog
        m = cells[e.target].box
        assert m.x < poly[-1][0] < m.x + 0.3 * m.w, (e.id, poly[-1], m)  # into the row-name column


def test_text_side_arrow_lands_on_the_middle_of_the_column_names(tmp_path):
    from paperfig.glyphs import pair_matrix_header
    from paperfig.lint import _polyline
    from paperfig.styles import load_recipe
    m = leaf("m", "L<sub>cap</sub>", visual="glyph", glyph="pair-matrix", grid=[3, 3], tone="green", col_tone="purple",
             axes=["z", "t"])
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column", "gap": "loose"}, "children": [
             leaf("txt", "Text encoder", tone="purple", size=[400, 36]), m]},
         "edges": [dict(src="txt", dst="m", kind="loss", heads="end", provenance=copy.deepcopy(PROV))]}
    _, cells = _build(tmp_path, d)
    e = next(c for c in cells.values() if c.edge)
    b = cells["pf-m"].box
    hw = pair_matrix_header(b.w, b.h, (3, 3), ["z", "t"], load_recipe("soft-pastel")["typography"]["small_size"])
    assert abs(_polyline(e, cells)[-1][0] - (b.x + hw + (b.w - hw) / 2)) < 1.0


def test_a_figure_with_pair_matrices_keys_its_positive_and_negative_cells(tmp_path):
    """The author's figure keys the filled cell (positive pair) and the empty one (negative pair); v6 left the
    reader to guess what the blue cells mean."""
    m = leaf("m", "L<sub>cap</sub>", visual="glyph", glyph="pair-matrix", grid=[3, 3], tone="green", col_tone="purple")
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf("e", "Encoder"), m]},
         "edges": [dict(src="e", dst="m", kind="loss", heads="end", provenance=copy.deepcopy(PROV))]}
    _, cells = _build(tmp_path, d)
    keys = [k for k in cells if k.startswith("pfdeco-legend-") and k.endswith("-cell")]
    assert len(keys) == 2, sorted(k for k in cells if k.startswith("pfdeco-legend"))
    fills = {cells[k].style["fillColor"].lower() for k in keys}
    assert "#ffffff" in fills and len(fills) == 2
    texts = " ".join(c.value for k, c in cells.items() if k.startswith("pfdeco-legend-") and k.endswith("-text"))
    assert "positive pair" in texts and "negative pair" in texts
    d["root"]["children"][1] = leaf("m", "Head")  # no matrix, no cell key
    _, cells = _build(tmp_path / "plain", d)
    assert not any(k.endswith("-cell") for k in cells)


def test_a_matrix_named_only_by_its_loss_is_flagged(tmp_path):
    """"L_cap 1:1" leaves the reader to look up what is paired; the author writes "image ↔ own caption · 1:1"."""
    from paperfig.lint import matrix_label_findings
    from paperfig.blueprint import load
    def bp(label):
        return load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
                     "root": {"id": "root", "layout": {"type": "row"}, "children": [
                         leaf("m", label, visual="glyph", glyph="pair-matrix", grid=[3, 3])]}, "edges": []})
    assert [f[0] for f in matrix_label_findings(bp("L<sub>cap</sub><br>1:1"))] == ["matrix-pairing-unnamed"]
    assert matrix_label_findings(bp("L<sub>cap</sub><br>image ↔ own caption · 1:1")) == []
    assert matrix_label_findings(bp("L<sub>proto</sub><br>query → prototype")) == []  # one-way pairing is named too


# ---- the author's second-stream panel: two towers facing a column of loss boxes. An encoder or an embedding
# that feeds several rows is one tall box covering exactly those rows, so every arrow is one short horizontal line.
def test_a_grid_box_spanning_rows_covers_them(tmp_path):
    kids = [leaf("enc", "Encoder", cell=[0, 0], span=[3, 1])]
    kids += [leaf(f"l{i}", f"Loss {i}", cell=[i, 1]) for i in range(3)]
    kids += [leaf("emb", "Embedding", cell=[1, 2], span=[2, 1])]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids},
         "edges": [dict(src="enc", dst=f"l{i}", provenance=copy.deepcopy(PROV)) for i in range(3)]
                  + [dict(src="emb", dst=f"l{i}", provenance=copy.deepcopy(PROV)) for i in (1, 2)]}
    _, cells = _build(tmp_path, d)
    enc, emb = cells["pf-enc"].box, cells["pf-emb"].box
    l0, l1, l2 = (cells[f"pf-l{i}"].box for i in range(3))
    assert enc.y <= l0.y + 1 and enc.bottom >= l2.bottom - 1, (enc, l0, l2)  # the tower covers all three rows
    assert emb.y <= l1.y + 1 and emb.bottom >= l2.bottom - 1, (emb, l1, l2)
    from paperfig.lint import _polyline
    for e in (c for c in cells.values() if c.edge):  # each line one straight horizontal run
        assert len({round(p[1], 1) for p in _polyline(e, cells)}) == 1, (e.id, _polyline(e, cells))


def test_a_long_matrix_name_stays_below_and_clear_of_the_row_names(tmp_path):
    """A name wider than the cells used to hang under the row-name column — where the line from below enters — so
    the engine moved it beside the matrix (a gap in the row of matrices). It starts after the row names instead."""
    from paperfig.glyphs import pair_matrix_header
    from paperfig.lint import _polyline
    from paperfig.styles import load_recipe
    m = leaf("m", "<i>L</i><sub>patch</sub><br>patch embedding ↔ own caption · 1 : 1", visual="glyph",
             glyph="pair-matrix", grid=[3, 3], tone="orange", col_tone="purple", axes=["h", "t"])
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column", "gap": "loose"}, "children": [
             m, leaf("h", "patch readout h", tone="orange", size=[300, 36])]},
         "edges": [dict(src="h", dst="m", provenance=copy.deepcopy(PROV))]}
    _, cells = _build(tmp_path, d)
    from paperfig.lint import _label_box
    b = cells["pf-m"].box
    lb = _label_box(cells["pf-m"], load_recipe("soft-pastel"))
    hw = pair_matrix_header(b.w, b.h, (3, 3), ["h", "t"], load_recipe("soft-pastel")["typography"]["small_size"])
    assert lb.y >= b.bottom - 0.5, (b, lb)  # still below
    assert lb.x >= b.x + hw - 0.5, (b.x + hw, lb)  # after the row names
    x_in = _polyline(next(c for c in cells.values() if c.edge), cells)[-1][0]
    assert b.x < x_in < b.x + hw and x_in < lb.x, (x_in, b, lb)


def test_image_side_arrow_from_the_left_lands_on_the_middle_row_name(tmp_path):
    from paperfig.glyphs import pair_matrix_header
    from paperfig.lint import _polyline
    from paperfig.styles import load_recipe
    m = leaf("m", "L<sub>cap</sub>", visual="glyph", glyph="pair-matrix", grid=[5, 5], tone="green", col_tone="purple",
             axes=["z", "t"])
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "loose", "align": "start"}, "children": [
             leaf("z", "CLS → z", tone="green", size=[90, 200]), m]},
         "edges": [dict(src="z", dst="m", dst_side="left", provenance=copy.deepcopy(PROV))]}
    _, cells = _build(tmp_path, d)
    b = cells["pf-m"].box
    hw = pair_matrix_header(b.w, b.h, (5, 5), ["z", "t"], load_recipe("soft-pastel")["typography"]["small_size"])
    y = _polyline(next(c for c in cells.values() if c.edge), cells)[-1][1]
    assert abs(y - (b.y + hw + (b.h - hw) / 2)) < 1.0, (y, b, hw)  # the middle row name (z_3), not the box centre



# ---- § 0b: each panel has a job. The runs drew the second stream as a copy of the first; the author teaches the
# objectives once (matrices) and draws them compactly where the panel's job is what is new
def test_each_unit_of_a_partition_states_its_job(tmp_path):
    lay = _layout(units=[{"id": "fdn", "of": "fdn_s", "losses": ["l_cap_a"]},
                         {"id": "ref", "of": "ref_s", "losses": ["l_cap_b", "l_aux"]}])
    probs = _check(tmp_path, "nojob", lay)
    assert any("job" in p and "0b" in p for p in probs), probs
    assert _check(tmp_path, "jobs", _layout()) == []


def test_an_extending_panel_that_redraws_a_taught_matrix_is_flagged(tmp_path):
    from test_blind_round3 import _grammar
    def mat(i, label):
        return leaf(i, label, role="loss", visual="glyph", glyph="pair-matrix", grid=[3, 3])
    d = _two_streams()
    d["root"]["children"][0]["children"][1] = mat("l_cap_a", "<i>L</i><sub>cap</sub><br>image ↔ caption · 1 : 1")
    d["root"]["children"][1]["children"][2] = mat("l_cap_b", "<i>L</i><sub>cap</sub><br>image ↔ caption · 1 : 1")
    found = _grammar(tmp_path / "copy", d, {"layout": _layout()})
    assert any(f.code == "objective-repeated" and "l_cap_b" in f.ids for f in found), [f.code for f in found]
    d["root"]["children"][1]["children"][2] = leaf("l_cap_b", "<i>L</i><sub>cap</sub><br>1 : 1", role="loss")
    found = _grammar(tmp_path / "compact", d, {"layout": _layout()})
    assert not any(f.code == "objective-repeated" for f in found)


# ---- user (2026-11-15, after v7): "确保一些线的对齐" — a card's arrow into the text-encoder bar sat 13–18 px beside
# the bar's drop into the matrix below, so card → bar → matrix read as a broken line
def _through_bar():
    kids = [leaf("card", "“quote”", cell=[0, 1], span=[1, 2], size=[140, 40]),
            leaf("bar", "Text encoder", cell=[1, 0], span=[1, 3], size=[520, 36]),
            leaf("left", "Other", cell=[2, 0]), leaf("mat", "Matrix", cell=[2, 1], size=[90, 60]),
            leaf("thin", "x", cell=[2, 2], size=[30, 30])]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
            "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids},
            "edges": [dict(src="card", dst="bar", provenance=copy.deepcopy(PROV)),
                      dict(src="bar", dst="mat", provenance=copy.deepcopy(PROV))]}


def test_a_line_through_a_bar_continues_on_the_same_line(tmp_path):
    from paperfig.lint import _polyline
    _, cells = _build(tmp_path, _through_bar())
    inn = next(c for c in cells.values() if c.edge and c.target == "pf-bar")
    out = next(c for c in cells.values() if c.edge and c.source == "pf-bar")
    xi, xo = _polyline(inn, cells)[-1][0], _polyline(out, cells)[0][0]
    assert abs(xi - xo) < 0.5, (xi, xo)


def test_a_near_miss_through_a_bar_is_flagged():
    from paperfig.lint import through_offsets
    pairs = through_offsets({"in": [(100.0, 0.0), (100.0, 50.0)], "out": [(113.0, 86.0), (113.0, 120.0)]},
                            {"in": ("card", "bar", "bottom", "top"), "out": ("bar", "mat", "bottom", "top")})
    assert pairs == [("in", "out", 13.0)]
    assert through_offsets({"in": [(100.0, 0.0), (100.0, 50.0)], "out": [(100.0, 86.0), (100.0, 120.0)]},
                           {"in": ("card", "bar", "bottom", "top"), "out": ("bar", "mat", "bottom", "top")}) == []
    assert through_offsets({"in": [(100.0, 0.0), (100.0, 50.0)], "out": [(300.0, 86.0), (300.0, 120.0)]},
                           {"in": ("card", "bar", "bottom", "top"), "out": ("bar", "mat", "bottom", "top")}) == []


# ---- v7 vs the author's draft: titles carried the loss equations, the key was turned off with matrices drawn, and
# orange filled a readout while also ringing the contribution
def _finish_bp(title="(a) Main stream", legend="auto", h_tone="green"):
    from paperfig.blueprint import load
    m = leaf("m", "L<sub>cap</sub><br>image ↔ caption", visual="glyph", glyph="pair-matrix", grid=[3, 3])
    return load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double", "legend": legend,
                                                  "highlight": "ring"},
                 "root": {"id": "root", "layout": {"type": "row"}, "children": [
                     {"id": "u", "title": title, "frame": "box", "layout": {"type": "row"}, "provenance": copy.deepcopy(PROV),
                      "children": [leaf("h", "readout h", tone=h_tone), leaf("s", "Sampler", role="proposed", full_name="Sampler"), m]}]},
                 "edges": []})


def test_finishing_lints_titles_keys_and_the_ring_hue():
    from paperfig.lint import finish_findings
    from paperfig.styles import load_recipe
    r = load_recipe("soft-pastel")
    assert finish_findings(_finish_bp(), r) == []
    long = "(a) Main stream: image–text pairs · step loss L = L_cap + λL_lab + λL_con + λL_patch"
    assert [f[0] for f in finish_findings(_finish_bp(title=long), r)] == ["title-long"]
    assert [f[0] for f in finish_findings(_finish_bp(legend="none"), r)] == ["matrix-unkeyed"]
    ring = r["palette"]["roles"]["proposed"]["tone"]
    found = finish_findings(_finish_bp(h_tone=ring), r)
    assert [f[0] for f in found] == ["ring-hue-reused"] and found[0][2] == ["h"]


def test_min_font_says_how_much_narrower_and_which_labels_to_break():
    from paperfig.lint import widest_lines
    from paperfig.drawio import Cell
    from paperfig.geometry import Box
    from paperfig.styles import load_recipe
    cells = {"a": Cell("a", "1", "a very long single line label here", {}, True, False, box=Box(0, 0, 10, 10)),
             "b": Cell("b", "1", "short<br>two lines", {}, True, False, box=Box(0, 0, 10, 10)),
             "c": Cell("c", "1", "medium length label", {}, True, False, box=Box(0, 0, 10, 10))}
    assert [k for k, _ in widest_lines(cells, load_recipe("soft-pastel"), 2)] == ["a", "c"]


def test_aligning_through_a_bar_never_swaps_neighbouring_ports(tmp_path):
    """Aligning moved a port past its neighbour on the same side, and the two lines crossed (corpus dreamerv3:
    crossings 1 -> 2). A move keeps every port's order on both sides of the moved line."""
    kids = [leaf("c1", "“a”", cell=[0, 0], size=[60, 36]), leaf("c2", "“b”", cell=[0, 1], size=[200, 36]),
            leaf("bar", "Bar", cell=[1, 0], span=[1, 3], size=[420, 36]),
            leaf("m", "M", cell=[2, 0], size=[60, 40]), leaf("k", "K", cell=[2, 2], size=[60, 40])]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "normal"}, "children": kids},
         "edges": [dict(src="c1", dst="bar", provenance=copy.deepcopy(PROV)),
                   dict(src="c2", dst="bar", provenance=copy.deepcopy(PROV)),
                   dict(src="bar", dst="m", provenance=copy.deepcopy(PROV)),
                   dict(src="bar", dst="k", provenance=copy.deepcopy(PROV))]}
    r, cells = _build(tmp_path, d)
    import json as _j
    stats = _j.loads(r.lint_json.read_text())["stats"]
    assert stats.get("edge_crossings", 0) == 0, stats
