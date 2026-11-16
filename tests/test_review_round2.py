"""Review round 2 (user, 2026-11-16: fix the report's proposals in order, effective, robust, compatible with the
existing modules). Each test pins one proposal; most fail on 4a7be80."""
import json

import pytest

from paperfig import kb


# ---- A1: arrangements are asked for after the structure is derived, ranked and capped --------------------------
def test_arrangements_filter_rank_flag_and_cap():
    hits = kb.arrangements(partition="lanes", relation="pairing")
    assert 0 < len(hits) <= 10
    assert {h["arrangement"]["partition"] for h in hits} == {"lanes"}
    assert hits[0]["core_relation"] == "pairing"  # the derived core relation ranks first
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    inside = kb.arrangements(n=1000)
    flagged = [h for h in inside if h["arrangement"].get("legend_at") == "inside"]
    assert flagged and all(h["flag"] for h in flagged)
    assert all(h["flag"] is None for h in inside if h["arrangement"].get("legend_at") != "inside")


def test_arrangements_exclude_the_paper_being_drawn():
    ids = {h["id"] for h in kb.arrangements(partition="stage-panels", n=1000)}
    assert "clip-2021-fig1" in ids
    ids = {h["id"] for h in kb.arrangements(partition="stage-panels", n=1000, exclude_paper=["2103.00020"])}
    assert "clip-2021-fig1" not in ids


def test_brief_is_small_and_has_no_arrangement_dump():
    b = kb.query("speech")
    assert "arrangements" not in b
    assert len(json.dumps(b)) < 150_000  # was ~335 KB, 3/4 of it every card's arrangement


# ---- A2: the brief's cards ranked by method, figure type and quality --------------------------------------------
MRI = {"family": "inverse-problem-reconstruction", "paradigm": "VarNet",
       "architecture": ["unrolled-iterative", "dual-domain"], "training": ["supervised"],
       "modality": ["mri-kspace", "image"]}


def test_brief_ranks_by_method_not_by_venue_or_year():
    ids = [c["id"] for c in kb.query("mri-reconstruction", "miccai", facets=MRI, figure_type="overview")["cards"]]
    # the unrolled-reconstruction figures design.md cites were sorted out by year before
    assert {"e2e-varnet-2020-fig1", "modl-2017-fig1", "vn-2017-fig1", "cascade-cnn-2017-fig4"} <= set(ids)
    assert ids[0] == "e2e-varnet-2020-fig1"  # paradigm + family + architecture + training


def test_brief_puts_the_requested_figure_type_first_when_methods_tie():
    cards = kb.query("diffusion", figure_type="module-detail", n_cards=8)["cards"]
    types = [c["figure_type"] for c in cards]
    assert types[0] == "module-detail" and types == sorted(types, key=lambda t: t != "module-detail")


def test_composite_counts_as_an_overview_everywhere():
    assert kb._same_type("composite", "overview") and kb._same_type("overview", "composite")
    assert not kb._same_type("teaser", "overview")
    assert kb.TYPE_BONUS["composite"] == kb.TYPE_BONUS["overview"]


def test_facets_of_reads_an_analysis(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"taxonomy": dict(MRI, note="x")}))
    assert kb.facets_of(p) == MRI
    p.write_text(json.dumps({"components": []}))
    assert kb.facets_of(p) == {}


# ---- A3: domain habits that break the skill's rules are listed apart, never as instructions ---------------------
def test_conflicting_conventions_are_listed_apart():
    d = kb.query("rl")["domain"]
    assert d["precedence"] and d["conventions_not_followed"]
    assert all(c.get("conflicts_with") for c in d["conventions_not_followed"])
    assert not any(c.get("conflicts_with") for c in d["conventions"])
    texts = " ".join(c["text"] for c in d["conventions"])
    assert "line art" not in texts and "single italic letter" not in texts


def test_conflicts_with_must_say_why(tmp_path):
    import shutil
    root = tmp_path / "kb"
    shutil.copytree(kb.REPO_KB, root, ignore=shutil.ignore_patterns("index.json"))
    shutil.copytree(kb.REPO_CARDS, root / "cards")
    shutil.copytree(kb.REPO_DOMAINS, root / "domains")
    p = root / "domains" / "rl.json"
    d = json.loads(p.read_text())
    d["conventions"][1]["conflicts_with"] = "no"
    p.write_text(json.dumps(d))
    assert any("conflicts_with must say" in x for x in kb.validate(kb_dir=root, data=tmp_path / "data"))


# ---- A4: cards a run can retrieve; volumes and orphans reported; forms by method; derive without photos ---------
def test_new_cards_need_the_fields_retrieval_reads():
    c = json.loads((kb.REPO_CARDS / "clip-2021-fig1.json").read_text())
    assert kb.retrieval_problems(c) == []
    for f in kb.RETRIEVAL_FIELDS:
        bad = {k: v for k, v in c.items() if k != f}
        assert kb.retrieval_problems(bad) and f in kb.retrieval_problems(bad)[0]
    lean = {k: v for k, v in c.items() if k not in ("grouping", "shapes_depth", "proposed_highlight")}
    assert kb.card_problems(lean) == []  # the prose `insights` supersedes is optional now


def test_coverage_names_stale_volumes_and_cards_without_a_volume():
    cov = kb.coverage()
    assert cov["domains"]["diffusion"]["stale"] is True  # 4 of ~47 cards cited
    assert cov["domains"]["mri-reconstruction"].get("stale") is False
    assert "resnet-2015-fig3" in cov["no_volume"] and "clap-2023-fig1" not in cov["no_volume"]


def test_forms_ranks_the_same_method_first():
    gnn = {"family": "graph-neural-network", "architecture": ["graph-message-passing"], "training": ["supervised"]}
    hits = kb.forms("on-structure", min_quality=4, facets=gnn, domain="graph-learning")
    assert all("graph-learning" in (kb.load_kb().cards[h["id"]].get("domains") or []) for h in hits[:3])
    plain = kb.forms("on-structure", min_quality=4)
    assert [h["quality"] for h in plain] == sorted((h["quality"] for h in plain), reverse=True)  # no facets: as before


def test_style_derive_skips_palettes_measured_with_photos(tmp_path):
    import shutil
    from paperfig.styles import StyleError, derive_style
    d = tmp_path / "cards"
    d.mkdir()
    shutil.copy(kb.REPO_CARDS / "dreambooth-2022-fig3.json", d)  # depicts real photos, photo_share unknown
    with pytest.raises(StyleError, match="photos in it"):
        derive_style("soft-pastel", d, tmp_path / "s.json")
    shutil.copy(kb.REPO_CARDS / "clip-2021-fig1.json", d)
    out = derive_style("soft-pastel", d, tmp_path / "s.json")
    meta = json.loads(out.read_text())["derived_from"]
    assert meta["skipped_photo_palettes"] == ["dreambooth-2022-fig3"] and "clip-2021-fig1" in meta["cards"]


# ---- B5: the contribution stands out in grayscale print by its fill alone -------------------------------------
@pytest.mark.parametrize("rid", ["soft-pastel", "depth-cv", "compact"])
def test_accent_fill_differs_from_reused_in_grayscale(rid):
    from paperfig import color
    from paperfig.grammar import GRAY_DL_MIN
    from paperfig.styles import load_recipe
    pal = load_recipe(rid)["palette"]
    acc = pal["tones"][pal["roles"]["proposed"]["tone"]]
    reu = pal["tones"][pal["roles"]["reused"]["tone"]]
    dl = abs(color.lab(acc["fill"])[0] - color.lab(reu["fill"])[0])
    assert dl >= GRAY_DL_MIN, (rid, dl)  # was 5 L* (#f7c198 vs #cadafa): only a bold name set them apart
    assert color.contrast(acc["font"], acc["fill"]) >= 4.5
    assert color.lab(acc["fill"])[0] - color.lab(acc["stroke"])[0] >= 12  # the outline still reads


# ---- B6: no Type 3 fallback fonts from the engine's own glyphs; the PDF is checked ------------------------------
def test_letter_ops_avoid_self_ringed_glyphs():
    from paperfig.shapes import OPS
    assert all(g not in "ⒸⓇ" for g, _ in OPS.values())


def test_pdf_fallback_fonts_are_reported(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from paperfig.lint import Report, check_pdf_fonts
    out = ("name type encoding emb sub uni object ID\n------\n"
           "AAAAAA+Helvetica CID TrueType Identity-H yes yes yes 16 0\n"
           "HAAAAA+PingFangSC-Regular Type 3 Custom yes yes yes 51 0\n")
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/pdffonts")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    rep = Report()
    check_pdf_fonts(tmp_path / "f.pdf", rep)
    f = [x for x in rep.findings if x.code == "pdf-fallback-font"]
    assert f and "PingFangSC-Regular" in f[0].message and "Helvetica" not in f[0].message


# ---- B7: the fit honours a venue's stated text range -------------------------------------------------------------
def test_text_floor_reads_the_venue():
    from paperfig.lint import MIN_FONT_PT, text_floor
    assert text_floor("nature") == 5 and text_floor("cvpr") == MIN_FONT_PT and text_floor(None) == MIN_FONT_PT


def test_nature_build_lands_in_range(tmp_path):
    from pathlib import Path
    from paperfig import pipeline as P
    d = json.loads(Path("examples/restormer.blueprint.json").read_text())
    d["figure"]["venue"] = "nature"
    f = Path("examples") / "_t_nature.blueprint.json"  # beside its assets (relative paths)
    f.write_text(json.dumps(d))
    try:
        r = P.build(f, "soft-pastel", out_dir=tmp_path, formats=())
    finally:
        f.unlink()
    s = r.report.stats
    assert 5.0 <= s["smallest_text_pt"] and s["largest_text_pt"] <= 7.05, s  # was 6.6 / 15.2 (fit aimed at 7.3)
    assert not any(x.code in ("max-font", "min-font") for x in r.report.findings)


# ---- C11 / C15 / C16: panels tinted like their source; frames and icons at the figure's line weight -------------
def test_detail_panel_tinted_like_its_source():
    from paperfig.blueprint import load
    from paperfig.styles import colors_for, load_recipe
    bp = load("examples/restormer.blueprint.json")
    r = load_recipe("soft-pastel")
    panels = [g for g in bp.groups() if g.detail_of]
    assert panels
    for g in panels:
        src = bp.index[g.detail_of]
        tone = src.tone or r["palette"]["roles"].get(src.role, r["palette"]["roles"]["reused"])["tone"]
        assert colors_for(r, g)[1] == r["palette"]["tones"][tone]["stroke"]


def test_icon_lines_take_the_figure_line_weight():
    import base64
    import re
    from paperfig.drawio import icon_data_uri
    svg = base64.b64decode(icon_data_uri("bot", "#123456", 1.4, 28).split(",", 1)[1]).decode()
    assert re.findall(r'stroke-width="([\d.]+)"', svg) == ["1.20"]  # 1.4 px drawn at 28 px (24-unit viewBox)


# ---- E3 / E12: drawn TeX label width; one copy of the arrow geometry ---------------------------------------------
def test_tex_labels_are_sized_as_drawn():
    from paperfig.measure import MATH_MARGIN, drawn_size, measure
    w, _ = measure(r"\(h_t\)", 10.5)
    assert drawn_size(r"\(h_t\)", 10.5)[0] == pytest.approx(w * MATH_MARGIN[0] + MATH_MARGIN[1])
    assert drawn_size("plain text", 10.5) == measure("plain text", 10.5)


def test_arrow_geometry_has_one_source():
    from paperfig import geometry, layout, lint, route
    assert route.END_RUN == lint.HEAD_RUN == geometry.END_RUN
    assert layout._Solver.PARALLEL == route.PARALLEL == lint.PARALLEL_HEADS == geometry.PARALLEL_HEADS


# ---- E1: a line through a stub's label is reported ---------------------------------------------------------------
def test_line_through_a_stub_label_is_reported(tmp_path):
    from paperfig.drawio import emit, parse_cells
    from paperfig.lint import check
    from paperfig.pipeline import solve_and_route
    from paperfig.blueprint import load
    from paperfig.styles import load_recipe
    P = [{"source": "user", "ref": "t"}]
    bp = load({"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double", "legend": "none"},
               "root": {"id": "root", "layout": {"type": "row"}, "children": [
                   {"id": "a", "label": "A", "provenance": P, "stub": {"side": "top", "label": "to the decoder"}},
                   {"id": "b", "label": "B", "provenance": P}]},
               "edges": [{"id": "e1", "src": "a", "dst": "b", "provenance": P}]})
    r = load_recipe("soft-pastel")
    placed, routes = solve_and_route(bp, r)
    lab = [c for k, c in parse_cells(emit(bp, placed, routes, r)).items() if k == "pfdeco-stub-a-label"][0].box
    routes["e1"].points = [(lab.cx, lab.y - 20), (lab.cx, lab.bottom + 20)]  # force a line straight through it
    f = tmp_path / "f.drawio"
    f.write_text(emit(bp, placed, routes, r))
    assert any(x.code == "edge-through-label" and "stub label" in x.message for x in check(f, bp, r, None, 6.875).findings)


# ---- D15 / D16: LaTeX projects and Word drafts --------------------------------------------------------------------
def _tex_project(root):
    (root / "sections").mkdir(parents=True)
    (root / "main.tex").write_text("\\documentclass{article}\\begin{document}\n\\section{Introduction} intro.\n"
                                   "\\input{sections/method}\n\\section{Experiments} results here.\n"
                                   "\\input{missing_file}\n\\end{document}")
    (root / "sections" / "method.tex").write_text("\\section[Method]{Our Method: Scale Attention}\nWe propose X. "
                                                  "\\input{sections/detail}")
    (root / "sections" / "detail.tex").write_text("DETAILPART of the method.")


def test_latex_short_titles_nested_inputs_and_missing_inputs(tmp_path):
    from paperfig.extract import extract_draft, method_section
    _tex_project(tmp_path / "p")
    d = extract_draft(tmp_path / "p")
    m = method_section(d)
    assert "Our Method: Scale Attention" in [s.title for s in d.sections]
    assert "DETAILPART" in m and "results here" not in m  # nested \input resolved from the main file's folder
    assert any("missing_file" in w for w in d.warnings)


def test_latex_zip_and_a_zip_that_escapes(tmp_path):
    import zipfile
    from paperfig.errors import PaperFigError
    from paperfig.extract import extract_draft, method_section
    _tex_project(tmp_path / "p")
    z = tmp_path / "overleaf.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (tmp_path / "p").rglob("*.tex"):
            zf.write(f, "proj/" + str(f.relative_to(tmp_path / "p")))
    assert "DETAILPART" in method_section(extract_draft(z))
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.tex", "x")
    with pytest.raises(PaperFigError, match="outside"):
        extract_draft(bad)


def test_docx_method_stops_at_the_next_heading_and_keeps_equations(tmp_path):
    import zipfile
    from paperfig.extract import extract_draft, method_section
    W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
         'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
    para = lambda t, st=None: (f'<w:p>{f"<w:pPr><w:pStyle w:val=\"{st}\"/></w:pPr>" if st else ""}'
                               f'<w:r><w:t>{t}</w:t></w:r></w:p>')
    eq = '<w:p><w:r><w:t>The output is </w:t></w:r><m:oMath><m:r><m:t>y=Wx+b</m:t></m:r></m:oMath></w:p>'
    body = (para("1 Introduction", "Heading1") + para("Intro.") + para("3 Our Approach", "Heading1")
            + para("We propose a gated module.") + eq + para("4 Experiments", "Heading1") + para("On ImageNet."))
    f = tmp_path / "d.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>')
    d = extract_draft(f)
    m = method_section(d)
    assert "y=Wx+b" in m and "ImageNet" not in m
    assert any("equation" in w for w in d.warnings)


# ---- D17 / D18 / P5 / P25: code-only facets, the author's sketch, figure-type-aware units, compare jobs ----------
def test_code_analysis_may_carry_a_checked_taxonomy():
    from paperfig.artifacts import _code
    probs = []
    _code({"taxonomy": {"family": "not-a-family", "paradigm": "X", "architecture": ["two-tower"],
                        "training": ["supervised"], "modality": ["image"]},
           "components": [], "data_flow": []}, None, probs)
    assert any("not-a-family" in p for p in probs)


def test_plan_job_compare_is_allowed():
    s = json.loads(open("schemas/figure_plan.schema.json").read())
    assert "compare" in json.dumps(s)
