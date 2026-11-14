"""Round-6 validation run (Reflexion, an agent loop): fixes for what the runner hit."""
import copy

from conftest import MINI, PROV, leaf
from paperfig.blueprint import load
from paperfig.facts import check_facts
from paperfig.plan import apply_plan


def _loop():
    """actor -> evaluator -> reflect -> memory -> actor: a drawn loop."""
    ids = ["actor", "evaluator", "reflect", "memory"]
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf(i, i.title()) for i in ids]},
            "edges": [{"src": a, "dst": b, "provenance": copy.deepcopy(PROV)}
                      for a, b in zip(ids, ids[1:] + ids[:1])]}


def _fact(a, b, **kw):
    return {"id": f"{a}-{b}", "from": a, "to": b, "quote": "q", "ref": "Sec. 3", **kw}


def _codes(ff):
    return {f.ids[0]: f.code for f in ff if f.ids}


def test_a_loop_does_not_cover_the_reverse_of_a_drawn_arrow():
    """In a loop everything reaches everything; a fact whose reverse is a drawn arrow is not drawn."""
    bp = load(_loop())
    got = _codes(check_facts(bp, [_fact("memory", "reflect"), _fact("evaluator", "actor"),
                                  _fact("actor", "reflect"), _fact("memory", "actor")]))
    assert got["memory-reflect"] == "fact-reversed" and got["evaluator-actor"] == "fact-reversed"
    assert got["actor-reflect"] == "fact-covered" and got["memory-actor"] == "fact-covered"


def test_plan_can_omit_a_reversed_fact():
    bp = load(_loop())
    ff = apply_plan(check_facts(bp, [_fact("memory", "reflect"), _fact("memory", "actor")]),
                    {"omitted": [{"fact": "memory-reflect", "where": "caption", "reason": "detail"}]})
    assert _codes(ff)["memory-reflect"] == "fact-omitted"


def test_plan_omitting_a_drawn_fact_is_flagged():
    bp = load(_loop())
    ff = apply_plan(check_facts(bp, [_fact("memory", "actor"), _fact("actor", "evaluator")]),
                    {"omitted": [{"fact": "memory-actor", "where": "caption", "reason": "detail"}]})
    hit = [f for f in ff if f.code == "fact-omitted-drawn"]
    assert hit and hit[0].severity == "warn" and hit[0].ids == ["memory-actor"]


def test_an_edge_from_a_group_leaves_from_its_exit_members():
    """Symmetric to entering a container: csfm -> dec carries what leaves gf (gf has no edge of its own out)."""
    bp = load(copy.deepcopy(MINI))
    got = _codes(check_facts(bp, [_fact("gf", "dec"), _fact("msa", "dec")]))
    assert got == {"gf-dec": "fact-covered", "msa-dec": "fact-covered"}


def _pdf(path, streams):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    w = PdfWriter()
    for s in streams:
        page = w.add_blank_page(width=200, height=100)
        obj = DecodedStreamObject()
        obj.set_data(s)
        page[NameObject("/Contents")] = w._add_object(obj)
    with open(path, "wb") as fh:
        w.write(fh)


INK = b"q 0 0 1 rg 10 10 50 20 re f Q BT /F1 7 Tf (Actor) Tj ET"
WHITE = b".24 0 0 -.24 0 100 cm\nq\n0 0 3000 1383 re\nW* n\nq\n1 1 1 RG 1 1 1 rg\n/G3 gs\n0 443 960 443 re\nf\nQ\nQ\n"


def test_trailing_white_page_is_dropped(tmp_path):
    """draw.io can spill a background-only second page when the page height rounds short of the content."""
    from pypdf import PdfReader
    from paperfig.pipeline import scale_pdf_to_width
    p = tmp_path / "fig.pdf"
    _pdf(p, [INK, WHITE])
    scale_pdf_to_width(p, 396)
    r = PdfReader(str(p))
    assert len(r.pages) == 1 and abs(float(r.pages[0].mediabox.width) - 396) < 0.5


def test_second_page_with_content_fails_loudly(tmp_path):
    import pytest
    from paperfig.errors import ExportError
    from paperfig.pipeline import scale_pdf_to_width
    p = tmp_path / "fig.pdf"
    _pdf(p, [INK, INK])
    with pytest.raises(ExportError, match="pages"):
        scale_pdf_to_width(p, 396)


def test_final_check_rejects_a_multipage_pdf(tmp_path):
    import json
    from paperfig import run
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    out = tmp_path / "deliver"
    out.mkdir()
    _pdf(out / "fig.pdf", [INK, WHITE])
    rec = json.loads((d / "run.json").read_text())
    rec["delivered"] = {"dir": str(out), "round": None, "files": {}}
    (d / "run.json").write_text(json.dumps(rec))
    assert any("2 pages" in p for p in run.check(d, final=True)), run.check(d, final=True)


def test_textcard_with_math_keeps_drawio_bounds_on_the_card(tmp_path):
    """draw.io sizes a no-wrap label from its raw TeX, so a math card at the figure edge widened the export with a
    blank strip; a math card wraps inside its own (slightly wider) box instead."""
    import json
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    kids = [leaf("a", "$\\tau_{t+1}$ return a + b", visual="textcard", card_style="code"),
            leaf("b", "return a - b", visual="textcard", card_style="code")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": kids},
         "edges": [{"src": "a", "dst": "b", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    assert c["pf-a"].style["whiteSpace"] == "wrap" and c["pf-b"].style["whiteSpace"] == "nowrap"


def test_png_margins_measured(tmp_path):
    from PIL import Image, ImageDraw
    from paperfig.lint import png_margins
    im = Image.new("RGB", (400, 100), "white")
    ImageDraw.Draw(im).rectangle([12, 12, 300, 88], fill="#336699")
    im.save(tmp_path / "f.png")
    assert png_margins(tmp_path / "f.png") == (12, 12, 99, 11)


def test_proposed_swatch_matches_the_proposed_boxes(tmp_path):
    """Nodes with an explicit tone: the legend's 'proposed' swatch is what those boxes are drawn in."""
    import json
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    d = copy.deepcopy(MINI)
    for c in d["root"]["children"][2]["children"]:
        c["tone"] = "purple"
    d["root"]["children"][2]["tone"] = "purple"
    d["figure"]["legend"] = "auto"
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    sw = next(v for k, v in c.items() if k.endswith("-swatch"))
    assert sw.style["fillColor"].lower() == c["pf-msa"].style["fillColor"].lower()


def _stub_bp(side, gap="loose"):
    import json
    d = {"schema_version": 1, "figure": {"type": "module-detail", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": gap},
                  "children": [leaf("a", "Block A", stub={"side": side, "label": "to the decoder"}), leaf("b", "Block B")]},
         "edges": []}
    return d


def test_stub_label_sits_past_the_arrow_tip(tmp_path):
    import json
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    for side in ("right", "bottom"):
        (tmp_path / f"{side}.json").write_text(json.dumps(_stub_bp(side)))
        res = P.build(tmp_path / f"{side}.json", "soft-pastel", out_dir=tmp_path / side, formats=())
        c = parse_cells(res.drawio.read_text())
        arrow, lab, a = c["pfdeco-stub-a"], c["pfdeco-stub-a-label"], c["pf-a"].box
        assert arrow.value in ("", None) and "decoder" in lab.value
        assert not lab.box.intersects(a, eps=0.5)
        if side == "right":  # above the arrow, starting at its root
            assert lab.box.bottom <= arrow.sp[1] and lab.box.x >= a.right
        else:  # beside the arrow
            assert lab.box.x > arrow.sp[0] and lab.box.y < arrow.tp[1]


def test_excluded_paper_leaves_the_domain_conventions():
    """A blind run must not read conventions that rest on the figure being redrawn."""
    from paperfig import kb
    full = kb.query("llm-agents", "neurips")["domain"]["conventions"]
    assert any("reflexion-2023-fig2" in c["evidence_cards"] for c in full)
    q = kb.query("llm-agents", "neurips", exclude_paper=["2303.11366"])
    convs = q["domain"]["conventions"]
    assert all("reflexion-2023-fig2" not in c["evidence_cards"] and len(set(c["evidence_cards"])) >= 2 for c in convs)
    resting = [c for c in full if len(set(c["evidence_cards"]) - {"reflexion-2023-fig2"}) < 2]
    assert len(convs) == len(full) - len(resting)
    assert any("convention" in n for n in q["notes"])


def test_bench_prepare_reports_guidance_citing_the_paper():
    from paperfig.bench import guidance_citing
    hits = guidance_citing("2303.11366")
    assert any("design.md" in h for h in hits)
    assert guidance_citing("2112.10752") == []  # a benchmark paper is never carded


def _rounds(tmp_path, issues):
    import json
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    lint = {"ok": True, "counts": {"error": 0, "warn": 0, "info": 0}, "stats": {}, "findings": []}
    for n in (1, 2):
        (d / "build" / f"r{n}").mkdir()
        (d / "build" / f"r{n}" / "fig.lint.json").write_text(json.dumps(lint))
    (d / "critic" / "r1.json").write_text(json.dumps({"viewed_png": True, "scores": {}, "issues": issues, "io_audit": []}))
    return d


def test_critic_issues_need_ids(tmp_path):
    import pytest
    from paperfig import run
    from paperfig.errors import PaperFigError
    d = _rounds(tmp_path, [{"severity": "high", "where": "x", "problem": "p", "concrete_fix": "f"}])
    with pytest.raises(PaperFigError, match="id"):
        run.record_round(d, 1, d / "build/r1/fig.lint.json", d / "critic" / "r1.json", "first")


def test_fix_note_names_every_high_and_medium_issue(tmp_path):
    import pytest
    from paperfig import run
    from paperfig.errors import PaperFigError
    iss = [{"id": f"i{k}", "severity": s, "where": "x", "problem": "p", "concrete_fix": "f"}
           for k, s in ((1, "high"), (2, "medium"), (3, "low"))]
    d = _rounds(tmp_path, iss)
    run.record_round(d, 1, d / "build/r1/fig.lint.json", d / "critic" / "r1.json", "first")
    with pytest.raises(PaperFigError, match="i2"):
        run.record_round(d, 2, d / "build/r2/fig.lint.json", None, "applied: i1", critic_of=1)
    run.record_round(d, 2, d / "build/r2/fig.lint.json", None, "applied: i1; open: i2 (needs the user)", critic_of=1)


def test_documents_glyph_for_text_memory(tmp_path):
    """An agent's memory of reflections / logs: stacked text pages, not a feature-map stack or a database drum."""
    import base64
    import json
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    nodes = [leaf("mem", "Memory", visual="glyph", glyph="documents"), leaf("act", "Actor")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row"}, "children": nodes},
         "edges": [{"src": "mem", "dst": "act", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    svg = base64.b64decode(parse_cells(res.drawio.read_text())["pf-mem"].style["image"].split(",", 1)[1]).decode()
    assert svg.count("<path") >= 3 and svg.count("<line") >= 3  # three sheets, text lines on the front one
    assert not [f for f in res.report.findings if f.code == "schematic-unmarked"]


def test_legend_keeps_clear_of_stubs(tmp_path):
    """The legend goes into free space — which is exactly where a stub points; it must avoid the arrow and its label."""
    import json
    from paperfig import pipeline as P
    from paperfig.drawio import parse_cells
    kids = [leaf("a", "Encoder", cell=[0, 0]), leaf("b", "Fusion", cell=[0, 1], role="proposed", full_name="Fusion"),
            leaf("c", "Decoder", cell=[1, 0], stub={"side": "top", "label": "to the head"})]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double", "legend": "auto"},
         "root": {"id": "root", "layout": {"type": "grid", "gap": "loose"}, "children": kids},
         "edges": [{"src": "a", "dst": "b", "provenance": copy.deepcopy(PROV)},
                   {"src": "a", "dst": "c", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    c = parse_cells(res.drawio.read_text())
    lg = c["pfdeco-legend"].box
    lab, arrow = c["pfdeco-stub-c-label"].box, c["pfdeco-stub-c"]
    from paperfig.geometry import Box
    seg = Box(arrow.sp[0] - 2, min(arrow.sp[1], arrow.tp[1]), 4, abs(arrow.tp[1] - arrow.sp[1]))
    assert not lg.intersects(lab, eps=0.5) and not lg.intersects(seg, eps=0.5), (lg, lab, seg)
    # a legend moved onto the stub by hand is caught
    import re
    from paperfig import lint as L
    from paperfig.blueprint import load
    from paperfig.styles import load_recipe
    text = res.drawio.read_text()
    m = re.search(r'(<mxCell id="pfdeco-legend"[^>]*>\s*<mxGeometry )x="[^"]*" y="[^"]*"', text)
    moved = tmp_path / "moved.drawio"
    moved.write_text(text[:m.start()] + m.group(1) + f'x="{lab.x}" y="{lab.y}"' + text[m.end():])
    rep = L.check(moved, load(tmp_path / "b.json"), load_recipe("soft-pastel"), None, 5.5)
    assert any(f.code == "overlap" and "legend" in f.ids and "c" in f.ids for f in rep.findings)


def test_blank_page_ignores_resource_names_that_look_like_operators():
    from types import SimpleNamespace
    from paperfig.pipeline import _blank_page

    def page(data):
        return SimpleNamespace(get_contents=lambda: SimpleNamespace(get_data=lambda: data))
    assert _blank_page(page(b"q /B gs /S cs 1 1 1 rg 0 0 10 10 re f Q"))
    assert not _blank_page(page(b"q 0 0 0 RG 0 0 m 10 10 l S Q"))
    assert not _blank_page(page(b"q 0 0 10 10 re f Q"))  # default colour is black


def test_tone_undeclared_explains_a_rendered_colour_key(tmp_path):
    """PointNet run: the plan keyed color_semantics by the colour editorial-minimal paints ('teal') instead of the
    blueprint tone ('orange'); the warning must say which keys are unused and that keys are blueprint tones."""
    import json
    from paperfig import pipeline as P
    d = copy.deepcopy(MINI)
    d["root"]["children"][2]["tone"] = "orange"
    for c in d["root"]["children"][2]["children"]:
        c["tone"] = "orange"
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    (tmp_path / "figure_plan.json").write_text(json.dumps({"color_semantics": {"teal": "ours", "blue": "encoder",
                                                                                "green": "decoder"}}))
    res = P.build(tmp_path / "blueprint.json", "editorial-minimal", out_dir=tmp_path / "o", formats=())
    f = next(f for f in res.report.findings if f.code == "tone-undeclared")
    assert "orange" in f.message and "teal" in f.message and "blueprint" in f.message


def test_gray_highlight_ignores_symbol_labels_for_the_bold_cue():
    """ControlNet: every named proposed block is bold; the one proposed symbol 'E' keeps its math italics."""
    from paperfig.grammar import gray_highlight
    p = {"fillColor": "#f7c198", "strokeWidth": "1.5", "fontStyle": "1"}
    sym = {"fillColor": "#f7c198", "strokeWidth": "1.5", "fontStyle": "0"}
    r = {"fillColor": "#cadafa", "strokeWidth": "1.5", "fontStyle": "0"}
    assert gray_highlight([p, p, sym], [r, r], ["Encoder<br>copy", "Middle<br>copy", "<i>E</i>"], ["Encoder", "Middle"]) is None
    # a named proposed block without bold still counts
    assert gray_highlight([p, sym, dict(sym)], [r], ["Encoder copy", "<i>E</i>", "Fusion"], ["Encoder"]) is not None


def test_tone_confusable_is_one_finding_listing_the_pairs(tmp_path):
    """Latent Diffusion: five separate colour-blindness warnings for one figure read as five problems."""
    from pathlib import Path
    from paperfig import pipeline as P
    d = Path(__file__).resolve().parents[1] / "bench/corpus/latent-diffusion"
    res = P.build(d / "blueprint.json", str(d / "style.json"), out_dir=tmp_path / "o", formats=())
    hits = [f for f in res.report.findings if f.code == "tone-confusable"]
    assert len(hits) == 1 and hits[0].message.count(" vs ") >= 5 and len(hits[0].ids) >= 5


def test_guidance_naming_the_paper_by_arxiv_id_is_a_leak():
    """Round 8: guidance written after seeing a validation paper's original names its arXiv id — a later blind
    run of that paper must hear about it."""
    from paperfig.bench import guidance_citing
    hits = guidance_citing("2301.04104")
    assert any("design.md" in h for h in hits)
