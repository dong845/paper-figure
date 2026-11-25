"""Visual components (user, 2026-11-24: "the original's font has character ... colourful icons ... looks matter"):
a display face for panel titles, and the parts a designed figure is built from."""
import pathlib

from paperfig import pipeline as P

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pdf_fonts(pdf) -> set:
    from pypdf import PdfReader
    names = set()
    for page in PdfReader(str(pdf)).pages:
        for f in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
            names.add(str(f.get_object().get("/BaseFont", "")))
    return names


def test_panel_titles_set_in_the_shipped_display_face_embed_as_truetype(tmp_path):
    r = P.build(ROOT / "examples" / "restormer.blueprint.json", "soft-pastel", out_dir=tmp_path, formats=("png", "pdf"))
    codes = {f.code for f in r.report.findings if f.severity in ("error", "warn")}
    assert "pdf-fallback-font" not in codes and "text-overflow" not in codes
    xml = next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8")
    assert "fontFamily=Nunito" in xml and "fontSource=data%3Afont%2Fwoff2" in xml  # self-contained, no network
    assert any("Nunito" in n for n in _pdf_fonts(next(tmp_path.glob("*.pdf"))))


def test_a_size_mix_keeps_the_base_title_face():
    from paperfig.styles import compose, title_family
    assert title_family(compose("soft-pastel", {"typography": "compact"})) == "Nunito"
    assert title_family(compose("editorial-minimal")) == "Helvetica"


def _bp(children, edges=()):
    from conftest import PROV
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": children},
            "edges": [dict(e, provenance=PROV) for e in edges]}


def test_letter_discs_and_icons_lead_the_name_without_overflow_or_fallback_fonts(tmp_path):
    import json

    from conftest import PROV, leaf
    bp = _bp([{"id": "pa", "title": "Medical Visual<br>Tools", "marker": "A", "provenance": PROV,
               "layout": {"type": "column"},
               "children": [leaf("t", "<b>Inspect</b><br><i>view · zoom</i>", icon="search"),
                            leaf("r", "residual $M_{res} > \\tau$", marker="C")]}])
    src = tmp_path / "bp.json"
    src.write_text(json.dumps(bp))
    r = P.build(src, "soft-pastel", out_dir=tmp_path, formats=("png", "pdf"))
    bad = [f for f in r.report.findings if f.code in ("text-overflow", "pdf-fallback-font", "overlap")]
    assert not bad, bad
    xml = next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8")
    for deco in ("pfdeco-pa-marker", "pfdeco-r-marker", "pfdeco-t-icon"):
        assert f'id="{deco}"' in xml
    assert "shape=ellipse" in xml


def test_stand_in_pictures_follow_the_figures_domain():
    from types import SimpleNamespace as NS

    from paperfig.standin import domain_of, kind_of

    def n(id, label, spec=""):
        return NS(id=id, label=label, asset=NS(spec=spec))
    nodes = [n("a", "CT volume", "chest CT"), n("b", "zoom"), n("c", "triplanar"), n("d", "attention map")]
    dom = domain_of(nodes)
    assert dom == "slice"
    assert [kind_of(x, dom) for x in nodes] == ["volume", "zoom", "views:slice", "heatmap"]
    assert kind_of(n("e", "frame"), None) == "photo"
    assert kind_of(n("m", "Mask"), dom) == "mask"  # a segmentation output is a label map, not another slice


def test_entities_inside_math_measure_as_the_drawn_character():
    from paperfig.measure import measure
    assert measure(r"\(M &gt; \tau\)", 12)[0] == measure(r"$M > \tau$", 12)[0]


def test_friendly_panels_white_boxes_tiles_decisions_and_one_formula_line(tmp_path):
    """The VERA look (user, 2026-11-25): Comic Sans, white boxes in tinted panels, an emphasis box takes a tone,
    tool tiles (icon above the name), a decision diamond, and a name with one line of math is not a formula block."""
    import json

    from conftest import PROV, leaf
    from paperfig.lint import parse_cells
    bp = _bp([{"id": "pa", "title": "Tools", "marker": "A", "role": "proposed", "full_name": "Tools", "tone": "orange", "provenance": PROV,
               "layout": {"type": "column"},
               "children": [leaf("t", "<b>Visual tools</b><br>view · zoom", icon="search", icon_at="top"),
                            leaf("u", "<b>Residual update</b><br>$m_c \\leftarrow m_c (1 - q)$"),
                            leaf("k", "<b>Check</b><br>$M > \\tau$ ?", visual="decision"),
                            leaf("e", "Retrieve by ID", tone="green")]}])
    src = tmp_path / "bp.json"
    src.write_text(json.dumps(bp))
    r = P.build(src, "friendly", out_dir=tmp_path, formats=("png", "pdf"))
    codes = {f.code for f in r.report.findings if f.severity in ("error", "warn")}
    assert not codes & {"text-overflow", "overlap", "pdf-fallback-font", "formula-in-block"}, codes
    cells = parse_cells(next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8"))
    assert cells["pf-t"].style["fillColor"] == "#ffffff" and cells["pf-u"].style["fillColor"] == "#ffffff"
    assert cells["pf-e"].style["fillColor"] != "#ffffff"  # the author's emphasis
    assert cells["pf-k"].style.get("shape") == "rhombus" and "spacingTop" in cells["pf-t"].style
    assert cells["pf-t"].style["fontFamily"] == "Comic Sans MS"


def test_two_formula_lines_in_a_block_are_still_flagged():
    from paperfig.lint import formula_in_label
    import re
    lab = "$a = b + c$<br>$d \\leftarrow d \\cdot e$"
    assert sum(formula_in_label(x) for x in re.split(r"<br>", lab)) == 2
