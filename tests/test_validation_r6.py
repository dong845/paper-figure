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
