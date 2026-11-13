"""Round 4: real math in labels — `$…$` is TeX, typeset by draw.io's MathJax at export (no math font needed)."""
import copy
import json

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.markup import to_html
from paperfig.measure import measure


def test_math_segments_become_mathjax_and_measure_as_glyphs():
    assert to_html(r"score $\alpha_{ij}$ (a|b)") == r"score \(\alpha_{ij}\) (a∣b)"
    assert to_html(r"$p(z | x)$") == r"\(p(z | x)\)"  # TeX keeps its own bar
    w_math, _ = measure(r"$\alpha_{ij}$", 12)
    w_raw, _ = measure(r"\alpha_{ij}", 12)
    w_ref, _ = measure("α<sub>ij</sub>", 12)
    from paperfig.measure import MATH_WIDTH
    assert w_math < w_raw and abs(w_math / w_ref - MATH_WIDTH) < 0.35, (w_math, w_ref, w_raw)  # MathJax is wider
    assert to_html(r"costs \$5") == "costs $5"


def test_math_figure_switches_mathjax_on(tmp_path):
    nodes = [leaf("a", r"$\mathbf{W}_Q$"), leaf("b", "Softmax")]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
         "root": {"id": "root", "layout": {"type": "row", "gap": "normal"}, "children": nodes},
         "edges": [{"src": "a", "dst": "b", "label": r"$QK^\top/\sqrt{d}$", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=("png",))
    xml = res.drawio.read_text()
    assert 'math="1"' in xml and r"\(\mathbf{W}_Q\)" in xml
    assert not [f for f in res.report.findings if f.severity == "error"], [f.message for f in res.report.findings if f.severity == "error"]
