import json
from pathlib import Path
import os

import pytest
from PIL import Image

from paperfig import refs
from paperfig.errors import PaperFigError

S2 = {"total": 2, "data": [
    {"paperId": "abc", "title": "Restormer: Efficient Transformer", "year": 2022, "venue": "CVPR", "citationCount": 1500,
     "externalIds": {"ArXiv": "2111.09881", "DOI": "x"}},
    {"paperId": "def", "title": "No arXiv paper", "year": 2021, "venue": "ICCV", "citationCount": 10, "externalIds": {}}]}

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry><id>http://arxiv.org/abs/2301.12597v3</id><published>2023-01-30T00:00:00Z</published>
<title>BLIP-2: Bootstrapping Language-Image
 Pre-training</title><arxiv:journal_ref>ICML 2023</arxiv:journal_ref></entry>
</feed>"""


def test_parse_s2_response():
    c = refs.parse_s2(S2)
    assert c[0].arxiv_id == "2111.09881" and c[0].venue == "CVPR" and c[0].citations == 1500
    assert c[1].arxiv_id is None


def test_parse_arxiv_atom():
    c = refs.parse_arxiv(ATOM)
    assert c[0].arxiv_id == "2301.12597" and c[0].year == 2023 and "BLIP-2" in c[0].title and "\n" not in c[0].title


def test_search_offline_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("network is unreachable")
    monkeypatch.setattr(refs, "_get", boom)
    with pytest.raises(PaperFigError, match="network"):
        refs.search("image restoration transformer")


def test_search_empty(monkeypatch):
    monkeypatch.setattr(refs, "_get", lambda url, **k: json.dumps({"total": 0, "data": []}).encode() if "semanticscholar" in url else
                        b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert refs.search("zzzz nonexistent topic") == []


def test_search_filters_years_and_excludes(monkeypatch):
    monkeypatch.setattr(refs, "_get", lambda url, **k: json.dumps(S2).encode())
    out = refs.search("x", years=(2022, 2024), exclude_arxiv={"0000.00000"})
    assert [c.title for c in out] == ["Restormer: Efficient Transformer"]
    out = refs.search("x", exclude_arxiv={"2111.09881"})
    assert all(c.arxiv_id != "2111.09881" for c in out)


RPDF = os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")
BPDF = os.path.expanduser("~/.cache/paper-figure/bench/blip2/paper.pdf")


@pytest.mark.skipif(not os.path.isfile(RPDF), reason="bench pdf not cached")
def test_crop_restormer_fig2(tmp_path):
    crops = refs.crop_figures(RPDF, tmp_path, numbers={2})
    f = next(c for c in crops if c.number == 2)
    assert f.problem is None and f.page == 3 and "Architecture of Restormer" in f.caption
    x0, y0, x1, y1 = f.bbox  # PDF points; measured: figure text spans x 53.0-544.1, y 79.1-255.3, caption top 263.9
    assert x0 <= 54 and x1 >= 543 and y0 <= 80
    assert 255 <= y1 < 263.9, "crop must end above the caption"
    w, h = Image.open(f.png).size
    assert abs(w - (x1 - x0) / 72 * 200) <= 2 and abs(h - (y1 - y0) / 72 * 200) <= 2
    assert json.loads((tmp_path / "fig2.json").read_text())["page"] == 3


@pytest.mark.skipif(not os.path.isfile(BPDF), reason="bench pdf not cached")
def test_crop_blip2_fig1(tmp_path):
    crops = refs.crop_figures(BPDF, tmp_path, numbers={1})
    f = next(c for c in crops if c.number == 1)
    assert f.problem is None and f.page == 1 and f.caption.startswith("Figure 1.")
    x0, y0, x1, y1 = f.bbox  # right column; title/authors (y <= 192.5, spanning both columns) and arXiv stamp excluded
    assert x0 >= 300 and x1 <= 548
    assert 192.5 < y0 <= 219 and 318 <= y1 < 332


def test_crop_reports_missing_caption(tmp_path):
    from paperfig.export import find_drawio, export
    from paperfig.errors import ExportError
    try:
        find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    d = tmp_path / "a.drawio"
    d.write_text('<mxfile><diagram name="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                 '<mxCell id="a" value="Just a box" style="rounded=0;" vertex="1" parent="1"><mxGeometry x="0" y="0" width="200" height="80" as="geometry"/></mxCell>'
                 '</root></mxGraphModel></diagram></mxfile>')
    pdf = export(d, "pdf", tmp_path / "a.pdf")
    with pytest.raises(PaperFigError, match="no figure caption"):
        refs.crop_figures(pdf, tmp_path / "out", numbers={1})
    with pytest.raises(PaperFigError, match="no figure caption"):
        refs.crop_figures(pdf, tmp_path / "out")


def _drawio_pdf(tmp_path, cells):
    from paperfig.export import find_drawio, export
    from paperfig.errors import ExportError
    try:
        find_drawio()
    except ExportError:
        pytest.skip("no drawio")
    body = "".join(f'<mxCell id="c{i}" value="{v}" style="{st}" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
                   for i, (v, st, x, y, w, h) in enumerate(cells))
    d = tmp_path / "s.drawio"
    d.write_text('<mxfile><diagram name="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>' + body + '</root></mxGraphModel></diagram></mxfile>')
    return export(d, "pdf", tmp_path / "s.pdf")


BOX = "rounded=0;fillColor=#dae8fc;strokeColor=#6c8ebf;"
CAP = "text;align=left;verticalAlign=top;fontSize=10;"


def test_crop_caption_below_synthetic(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 300, 120), ("Figure 1: A blue box with a caption below it.", CAP, 0, 140, 300, 20)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={1})[0]
    assert f.problem is None and f.layout == "caption-below"
    cap = refs._captions(refs._layout(pdf))[0]
    assert f.bbox[3] < cap.y0 and (f.bbox[3] - f.bbox[1]) >= 0.8 * 120 * 0.75  # drawio px -> pt is 0.75


def test_crop_caption_above_synthetic(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("Figure 3. The caption sits above this box.", CAP, 0, 0, 300, 20), ("", BOX, 0, 40, 300, 120)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={3})[0]
    assert f.problem is None and f.layout == "caption-above"
    cap = refs._captions(refs._layout(pdf))[0]
    assert f.bbox[1] > cap.y1 and (f.bbox[3] - f.bbox[1]) >= 0.8 * 120 * 0.75


def test_crop_requested_number_absent_is_loud(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 300, 120), ("Figure 1: A blue box.", CAP, 0, 140, 300, 20)])
    with pytest.raises(PaperFigError, match="figure 4"):
        refs.crop_figures(pdf, tmp_path / "o", numbers={1, 4})


def test_inline_reference_is_not_a_caption(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 300, 120), ("As shown in Figure 1, the box is blue.", CAP, 0, 140, 300, 20)])
    with pytest.raises(PaperFigError, match="no figure caption"):
        refs.crop_figures(pdf, tmp_path / "o")


def test_fetch_rejects_bad_id_and_non_pdf(tmp_path, monkeypatch):
    with pytest.raises(PaperFigError, match="arXiv id"):
        refs.fetch("../../etc/passwd", cache=tmp_path)
    monkeypatch.setattr(refs, "_get", lambda url, **k: b"<html>not a pdf</html>")
    with pytest.raises(PaperFigError, match="not a PDF"):
        refs.fetch("2111.09881", cache=tmp_path)
    assert not list(tmp_path.rglob("*.pdf"))


def test_fetch_caches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(refs, "_get", lambda url, **k: calls.append(url) or b"%PDF-1.5 fake")
    p1 = refs.fetch("2111.09881v2", cache=tmp_path)
    p2 = refs.fetch("2111.09881v2", cache=tmp_path)
    assert p1 == p2 and p1.read_bytes().startswith(b"%PDF") and len(calls) == 1


def test_s2_rate_limited_falls_back_to_arxiv(monkeypatch):
    import urllib.error
    def get(url, **k):
        if "semanticscholar" in url:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return ATOM.encode()
    monkeypatch.setattr(refs, "_get", get)
    monkeypatch.setattr(refs, "_sleep", lambda s: None)
    out = refs.search("blip")
    assert [c.arxiv_id for c in out] == ["2301.12597"] and out[0].venue == "ICML"
    assert any("429" in n for n in out.notes) and any("arXiv" in n for n in out.notes)


def test_venue_filter_uses_aliases():
    c = refs.parse_s2({"data": [{"title": "A", "year": 2022, "venue": "Computer Vision and Pattern Recognition",
                                 "publicationVenue": {"name": "Computer Vision and Pattern Recognition", "alternate_names": ["CVPR"]},
                                 "externalIds": {"ArXiv": "2111.09881"}, "citationCount": 1}]})
    assert refs.venue_matches(c[0], {"cvpr"}) and not refs.venue_matches(c[0], {"ICCV"})


def test_crop_skips_table_body_above_figure(tmp_path):
    # Table caption above its table (CVPR/NeurIPS convention), then the figure, then its caption.
    rule = "line;strokeWidth=1;html=1;"
    pdf = _drawio_pdf(tmp_path, [
        ("Table 1: Results of every method on the benchmark set.", CAP, 0, 0, 300, 20),
        ("", rule, 0, 26, 300, 4), ("Method A 22.77 0.810 14.92", CAP, 0, 32, 300, 16),
        ("Method B 23.10 0.812 15.01", CAP, 0, 50, 300, 16), ("", rule, 0, 70, 300, 4),
        ("", BOX, 0, 110, 300, 100),
        ("Figure 2: A blue box under a table.", CAP, 0, 225, 300, 20)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={2})[0]
    lay = refs._layout(pdf)
    tbl_last = max(b.y1 for b in lay.pages[0].blocks if "Method B" in b.text)
    assert f.problem is None and f.bbox[1] > tbl_last, (f.bbox, tbl_last)


def test_crop_skips_table_with_vertical_rules_and_method_header(tmp_path):
    hr, vr = "line;strokeWidth=1;html=1;", "line;direction=south;strokeWidth=1;html=1;"
    pdf = _drawio_pdf(tmp_path, [
        ("Table 1: Results of every method on the benchmark set.", CAP, 0, 0, 300, 20),
        ("", hr, 0, 24, 300, 2),
        ("Method", CAP, 4, 27, 60, 14), ("PSNR SSIM PSNR SSIM", CAP, 100, 27, 190, 14),
        ("", vr, 80, 26, 2, 50), ("", vr, 190, 26, 2, 50),
        ("Ours 22.77 0.810 14.92 0.811", CAP, 4, 45, 290, 14), ("Base 23.10 0.812 15.01 0.700", CAP, 4, 60, 290, 14),
        ("", hr, 0, 76, 300, 2),
        ("", BOX, 0, 92, 300, 100),
        ("Figure 2: A blue box under a ruled table.", CAP, 0, 205, 300, 20)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={2})[0]
    lay = refs._layout(pdf)
    tbl_last = max(b.y1 for b in lay.pages[0].blocks if "Base" in b.text)
    assert f.problem is None and f.bbox[1] > tbl_last, (f.bbox, tbl_last)
    assert not refs._is_heading(lay, next(b for b in lay.pages[0].blocks if b.text == "Method"), lay.pages[0])


def test_line_plot_after_table_caption_is_kept(tmp_path):
    # caption-BELOW table, then a line plot (axes + a diagonal curve): nothing may be skipped
    hr, vr = "line;strokeWidth=1;html=1;", "line;direction=south;strokeWidth=1;html=1;"
    pdf = _drawio_pdf(tmp_path, [
        ("Ours 22.77 0.810 14.92 0.811", CAP, 4, 0, 290, 14), ("", hr, 0, 16, 300, 2),
        ("Table 1: Results of every method on the benchmark set.", CAP, 0, 20, 300, 20),
        ("", vr, 20, 60, 2, 100), ("", hr, 20, 160, 280, 2),
        ("", "ellipse;fillColor=#000000;", 60, 120, 6, 6), ("", "ellipse;fillColor=#000000;", 150, 90, 6, 6),
        ("", "ellipse;fillColor=#000000;", 240, 70, 6, 6),
        ("Figure 2: A scatter plot below a table.", CAP, 0, 175, 300, 20)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={2})[0]
    assert f.problem is None and f.bbox[1] <= 60 * 0.72 + 2, f.bbox  # starts at the plot's y axis top


def _synthetic_doc(pages_spec):
    """pages_spec: list of lists of (x0, x1) body-line extents; lines are 12pt apart, 9pt tall."""
    pages = []
    for n, spec in enumerate(pages_spec, 1):
        blocks = []
        for x0, x1, k in spec:
            lines = [refs.Line(x0, 80 + 12 * i, x1, 89 + 12 * i, "lorem ipsum dolor sit amet consectetur adipiscing elit")
                     for i in range(k)]
            blocks.append(refs.Block(x0, lines[0].y0, x1, lines[-1].y1, lines))
        pages.append(refs.Page(n, 612, 792, blocks))
    doc = refs.Doc(Path("x.pdf"), pages)
    refs._body_stats(doc)
    return doc


def test_columns_are_per_page():
    two = [(50, 286, 40), (309, 545, 40)]
    one = [(50, 545, 40)]
    doc = _synthetic_doc([two, two, one, one, one, [(60, 200, 1)]])
    approx = lambda cols: [(round(a), round(b)) for a, b in cols]
    assert approx(doc.pages[0].cols) == [(50, 286), (309, 545)]
    assert approx(doc.pages[2].cols) == [(50, 545)]
    assert approx(doc.pages[5].cols) == [(50, 545)]  # a figure-only page inherits its neighbour's layout


def test_short_paragraph_with_math_is_body():
    doc = _synthetic_doc([[(50, 545, 40)], [(50, 545, 40)]])
    pg = doc.pages[0]
    mk = lambda x1, h, y: refs.Line(50, y, x1, y + h, "words " * 9)
    para = [mk(545, 12.3, 600), mk(545, 9, 614), mk(300, 9, 626)]  # inline math line, full line, short last line
    assert refs._is_body(doc, refs.Block(50, 600, 545, 635, para), pg)
    cap_like = [mk(545, 8.0, 600), mk(545, 8.0, 610), mk(400, 8.0, 620)]  # smaller font: a caption, not body
    assert not refs._is_body(doc, refs.Block(50, 600, 545, 628, cap_like), pg)


def test_sparse_page_inherits_majority_layout_not_reference_indent():
    two = [(55, 291, 40), (307, 543, 40)]
    refs_page = [(65, 291, 30)]  # hanging-indent continuation lines of a reference list
    doc = _synthetic_doc([two, two, two, two, refs_page, [(60, 200, 1)]])
    assert [(round(a), round(b)) for a, b in doc.pages[5].cols] == [(55, 291), (307, 543)]


class _StubRenders:
    dpi = 200

    def __init__(self, boxes):
        self.boxes = boxes  # graphics boxes on the page

    def graphics_in(self, page, box):
        hit = [b for b in self.boxes if b[0] < box[2] and b[2] > box[0] and b[1] < box[3] and b[3] > box[1]]
        if not hit:
            return None
        return (max(box[0], min(b[0] for b in hit)), max(box[1], min(b[1] for b in hit)),
                min(box[2], max(b[2] for b in hit)), min(box[3], max(b[3] for b in hit)))


def _cap(x0, y0, x1, y1, page=1):
    return refs.Caption("figure", 1, page, x0, y0, x1, y1, "Figure 1. x", [])


def test_span_covers_its_caption():
    doc = _synthetic_doc([[(65, 291, 40)]])
    sx0, sx1, _ = refs._span(doc, _cap(55, 400, 540, 420), [])
    assert sx0 <= 55 and sx1 >= 540


def test_column_span_widens_when_graphics_are_clipped():
    two = [(55, 291, 40), (307, 543, 40)]
    doc = _synthetic_doc([two, two])
    cap = _cap(60, 300, 150, 310)  # short left-aligned caption under a full-width figure
    wide = _StubRenders([(60, 100, 540, 290)])
    ra, rb, span, _ = refs._regions(doc, cap, [cap], set(), wide)
    assert span == "full" and ra[0] <= 60 and ra[2] >= 540
    narrow = _StubRenders([(70, 100, 280, 290)])  # a true column figure stays a column figure
    ra, rb, span, _ = refs._regions(doc, cap, [cap], set(), narrow)
    assert span == "column" and ra[2] <= 300


def test_captions_in_different_columns_are_not_side_by_side():
    two = [(50, 286, 40), (309, 545, 40)]
    doc = _synthetic_doc([two, two])
    right, left = _cap(309, 163, 545, 215), _cap(50, 190, 286, 231)
    assert refs._span(doc, right, [right, left])[2] == "column"
    a, b = _cap(60, 400, 160, 410), _cap(180, 400, 280, 410)  # two minipage captions inside the left column
    sx0, sx1, kind = refs._span(doc, a, [a, b])
    assert kind == "side-by-side" and sx1 <= 175


def test_table_caption_beside_figure_splits_span():
    doc = _synthetic_doc([[(50, 545, 40)], [(50, 545, 40)]])
    fig = _cap(60, 400, 280, 410)
    tab = refs.Caption("table", 2, 1, 320, 400, 540, 410, "Table 2. y", [])
    sx0, sx1, kind = refs._span(doc, fig, [fig, tab])
    assert kind == "side-by-side" and sx1 <= 300


def _throttled_call(args):
    import time as _t
    host, cache = args
    os.environ["PAPERFIG_CACHE"] = cache
    refs.MIN_INTERVAL[host] = 0.4
    refs._throttle(host)
    return _t.monotonic()


def test_throttle_spaces_calls_across_processes(tmp_path):
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(3) as pool:
        times = sorted(pool.map(_throttled_call, [("example.test", str(tmp_path))] * 3))
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 0.35 for g in gaps), gaps


def test_arxiv_query_drops_stopwords_and_title_uses_phrase():
    q = refs._arxiv_query("Simple Baselines for Image Restoration", None)
    assert "all:for" not in q and "all:Simple" in q
    assert refs._arxiv_title_query("Simple Baselines for Image Restoration") == 'ti:"Simple Baselines for Image Restoration"'


def test_search_title_uses_match_then_arxiv(monkeypatch):
    seen = []

    def get(url, **k):
        seen.append(url)
        if "search/match" in url:
            return json.dumps({"data": [{"paperId": "x", "title": "Simple Baselines for Image Restoration", "year": 2022,
                                         "venue": "European Conference on Computer Vision", "externalIds": {"ArXiv": "2204.04676"},
                                         "citationCount": 900, "matchScore": 180.2}]}).encode()
        raise AssertionError(url)

    monkeypatch.setattr(refs, "_get", get)
    out = refs.search_title("Simple Baselines for Image Restoration")
    assert out[0].arxiv_id == "2204.04676" and out[0].venue == "ECCV" and "search/match" in seen[0]

    def get404(url, **k):
        if "search/match" in url:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "Title match not found", {}, None)
        return ATOM.encode()

    monkeypatch.setattr(refs, "_get", get404)
    monkeypatch.setattr(refs, "_sleep", lambda s: None)
    out = refs.search_title("BLIP-2: Bootstrapping Language-Image Pre-training")
    assert out[0].arxiv_id == "2301.12597" and any("arXiv" in n for n in out.notes)


def test_crop_all_reports_numbering_gaps(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 300, 120), ("Figure 2: A blue box.", CAP, 0, 140, 300, 20)])
    crops = refs.crop_figures(pdf, tmp_path / "o")
    by = {c.number: c for c in crops}
    assert by[2].problem is None and by[1].problem and "no caption" in by[1].problem


def test_crop_side_caption_synthetic(tmp_path):
    side_cap = "text;align=left;verticalAlign=top;fontSize=10;whiteSpace=wrap;"
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 200, 120),
                                 ("Figure 1: A side caption next to the box, long enough to wrap onto lines.", side_cap, 220, 20, 160, 80)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={1})[0]
    cap = refs._captions(refs._layout(pdf))[0]
    assert f.problem is None and f.layout == "caption-side", f
    assert f.bbox[2] <= cap.x0 and (f.bbox[3] - f.bbox[1]) >= 0.8 * 120 * 0.72


def test_crop_without_graphics_is_a_problem_not_a_text_grab(tmp_path):
    pdf = _drawio_pdf(tmp_path, [("Some words placed above the caption only, no drawing at all here.", CAP, 0, 0, 300, 20),
                                 ("Figure 1: A caption with nothing drawn.", CAP, 0, 60, 300, 20)])
    with pytest.raises(PaperFigError, match="no figure graphics"):
        refs.crop_figures(pdf, tmp_path / "o", numbers={1})


def test_indented_justified_list_is_body():
    doc = _synthetic_doc([[(108, 504, 40)], [(108, 504, 40)]])
    pg = doc.pages[0]
    lines = [refs.Line(135, 520 + 12 * i, 504, 529 + 12 * i, "words " * 12) for i in range(3)]
    lines[-1] = refs.Line(135, 544, 300, 553, "words " * 5)
    assert refs._is_body(doc, refs.Block(135, 520, 504, 553, lines), pg)


def _caption_doc(lines):
    """One page, two columns (body lines 9pt tall, 12pt pitch) plus a custom block made of `lines`."""
    doc = _synthetic_doc([[(50, 286, 40), (309, 545, 40)]])
    blk = refs.Block(min(l.x0 for l in lines), min(l.y0 for l in lines), max(l.x1 for l in lines), max(l.y1 for l in lines), lines)
    doc.pages[0].blocks.append(blk)
    return doc


def test_caption_inside_merged_column_block():
    body = [refs.Line(50, 100 + 12 * i, 286, 109 + 12 * i, "lorem ipsum dolor sit amet consectetur adipiscing elit") for i in range(5)]
    cap = [refs.Line(50, 300, 286, 308, "Figure 10. Baseline 3D CNN segmentation network. The"),
           refs.Line(50, 310, 286, 318, "network is fully convolutional and predicts part scores")]
    after = [refs.Line(50, 340 + 12 * i, 286, 349 + 12 * i, "lorem ipsum dolor sit amet consectetur adipiscing elit") for i in range(3)]
    caps = refs._captions(_caption_doc(body + cap + after))
    c = next(c for c in caps if c.number == 10)
    assert c.text.startswith("Figure 10.") and "lorem" not in c.text and c.y1 <= 319


def test_caption_after_unaligned_label_line():
    lines = [refs.Line(358, 336, 517, 345, "Computational cost in log scale (GMACs)"),
             refs.Line(312, 349, 542, 358, "Figure 1. PSNR vs. computational cost on the SIDD dataset")]
    caps = refs._captions(_caption_doc(lines))
    assert any(c.number == 1 for c in caps)


def test_wrapped_inline_reference_is_not_a_caption():
    lines = [refs.Line(50, 100, 286, 109, "and the decoder recovers the resolution, as shown in"),
             refs.Line(50, 112, 286, 121, "Figure 3. The decoder then predicts the output image with")]
    assert not any(c.number == 3 for c in refs._captions(_caption_doc(lines)))


def test_caption_is_split_out_of_its_block():
    lines = [refs.Line(358, 323, 372, 334, "10 1"), refs.Line(358, 336, 517, 345, "Computational cost in log scale (GMACs)"),
             refs.Line(312, 349, 542, 358, "Figure 1. PSNR vs. computational cost on the SIDD dataset"),
             refs.Line(312, 360, 542, 369, "and more caption words that continue the sentence here")]
    doc = _caption_doc(lines)
    cap = next(c for c in refs._captions(doc) if c.number == 1)
    pg = doc.pages[0]
    cap_blk = next(b for b in pg.blocks if id(b) in cap.blocks)
    assert [ln.text[:6] for ln in cap_blk.lines] == ["Figure", "and mo"]
    assert any(b.lines[0].text == "10 1" and len(b.lines) == 2 for b in pg.blocks)  # labels kept as their own block
    assert len(refs._captions(doc)) == 1  # idempotent


def test_minipage_figure_beside_table_excludes_table(tmp_path):
    hr, vr = "line;strokeWidth=1;html=1;", "line;direction=south;strokeWidth=1;html=1;"
    cells = [("Table 2: Results of every method on the benchmark.", CAP, 0, 0, 260, 20), ("", hr, 0, 24, 260, 2),
             ("Method A 22.77 0.810 14.92", CAP, 4, 30, 250, 14), ("Method B 23.10 0.812 15.01", CAP, 4, 50, 250, 14),
             ("", hr, 0, 70, 260, 2), ("", vr, 120, 24, 2, 48),
             ("", BOX, 300, 20, 200, 120), ("Figure 4: The box beside the table.", CAP, 300, 150, 200, 20)]
    pdf = _drawio_pdf(tmp_path, cells)
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={4})[0]
    tbl_right = max(b.x1 for b in refs._layout(pdf).pages[0].blocks if "Method" in b.text)
    assert f.problem is None and f.bbox[0] > tbl_right, (f.bbox, tbl_right)


def test_image_grid_with_short_caption_is_not_narrowed(tmp_path):
    cells = [("", BOX, x, 0, 90, 90) for x in (0, 110, 220, 330, 440)]  # five columns with white gaps between
    cells.append(("Figure 3: A short caption.", "text;align=center;verticalAlign=top;fontSize=10;", 180, 100, 170, 20))
    pdf = _drawio_pdf(tmp_path, cells)
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={3})[0]
    assert f.problem is None and f.bbox[2] - f.bbox[0] >= 0.9 * 530 * 0.72, f.bbox


def test_crop_records_embedded_image_boxes(tmp_path):
    import base64
    import io as _io
    b = _io.BytesIO()
    Image.new("RGB", (40, 30), "#ff8800").save(b, "PNG")
    uri = "data:image/png," + base64.b64encode(b.getvalue()).decode()
    pdf = _drawio_pdf(tmp_path, [("", BOX, 0, 0, 300, 120), ("", f"shape=image;image={uri};imageAspect=0;", 20, 20, 80, 60),
                                 ("Figure 1: A box with a photo inside.", CAP, 0, 140, 300, 20)])
    f = refs.crop_figures(pdf, tmp_path / "o", numbers={1})[0]
    meta = json.loads((tmp_path / "o" / "fig1.json").read_text())
    assert len(meta["images_px"]) == 1
    x0, y0, x1, y1 = meta["images_px"][0]
    w, h = Image.open(f.png).size
    assert 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h and (x1 - x0) > 0.15 * w


def test_project_url_is_not_the_web_conference():
    assert refs.canonical_venue("Project page: https://www.example.com/proj") is None
    assert refs.canonical_venue("Accepted to WWW 2020") == "WWW"
    assert refs.canonical_venue("WWW'21") == "WWW"
    assert refs.canonical_venue("The Web Conference 2022") == "WWW"


def test_image_boxes_normalised_for_flipped_images():
    xml = '<image top="300" left="100" width="50" height="-40" src="a.png"/><image top="10" left="200" width="-30" height="20" src="b.png"/>'
    assert refs._parse_image_boxes(xml) == [(100.0, 260.0, 150.0, 300.0), (170.0, 10.0, 200.0, 30.0)]


def test_caption_with_a_titled_parenthetical_is_found():
    """Trajectory Transformer: 'Figure 1 (Architecture) …' has no colon; the scout had to crop by hand (F55)."""
    from paperfig.refs import _cap_match
    assert _cap_match("Figure 1 (Architecture) The Trajectory Transformer models") == ("figure", 1)
    assert _cap_match("Figure 2 (Beam search). Decoding") == ("figure", 2)
    assert _cap_match("Figure 1 (left) shows the architecture") is None  # running text, not a caption
    assert _cap_match("Figure 3: Overview") == ("figure", 3)
