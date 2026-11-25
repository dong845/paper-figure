"""draw.io used as draw.io (user, 2026-11-25: "the font was in draw.io all along and the skill never knew"): the
font menu's faces are measured from their own files and an unknown face stops the build; wires are draw.io's own
orthogonal connectors (they stay right-angled when the user drags a box); crossings hop."""
import json
import pathlib

import pytest

from paperfig import pipeline as P
from paperfig.errors import StyleError
from paperfig.lint import parse_cells
from paperfig.measure import font_problem, measure
from paperfig.styles import STYLES_DIR, load_recipe

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_a_face_the_engine_cannot_measure_stops_the_style(tmp_path):
    data = json.loads((STYLES_DIR / "soft-pastel.json").read_text())
    data["typography"]["family"] = "Arial"  # not in draw.io's menu: it used to be measured as Helvetica in silence
    p = tmp_path / "mine.json"
    p.write_text(json.dumps(data))
    with pytest.raises(StyleError, match="draw.io menu font"):
        load_recipe(str(p))


@pytest.mark.parametrize("family", ["Verdana", "Georgia", "Tahoma"])
def test_menu_faces_are_measured_from_their_own_files(family):
    if font_problem(family):
        pytest.skip(font_problem(family))
    from paperfig.measure import _font
    for bold in (False, True):
        assert family.lower() in pathlib.Path(_font("primary", family, bold)[1]).name.lower()  # not Helvetica's file


def test_bold_code_text_is_measured_in_the_code_face():
    if font_problem("Courier New"):
        pytest.skip(font_problem("Courier New"))
    regular, bold = (measure("def forward(x):", 12, b, "Courier New")[0] for b in (False, True))
    assert regular == pytest.approx(bold)  # monospace: bold used to fall back to a proportional face


def test_wires_are_orthogonal_connectors_that_hop_and_zoom_lines_stay_straight(tmp_path):
    P.build(ROOT / "examples" / "restormer.blueprint.json", "soft-pastel", out_dir=tmp_path, formats=())
    cells = parse_cells(next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8"))
    flows = [c for k, c in cells.items() if c.edge and not k.startswith("pfdeco") and c.source and c.target]
    assert flows and all(c.style.get("edgeStyle") == "orthogonalEdgeStyle" for c in flows)
    assert all(c.style.get("jumpStyle") == "arc" for c in flows)
    legs = [c for k, c in cells.items() if c.edge and k.startswith("pfdeco")]
    assert legs and all(c.style.get("edgeStyle") == "none" for c in legs)


def _stages(tmp_path, edges, layout="row"):
    from conftest import PROV, leaf
    panel = lambda i, kids: {"id": i, "title": f"Stage {i}", "layout": {"type": "column"}, "provenance": PROV, "children": kids}
    bp = {"schema_version": 1, "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
          "root": {"id": "root", "layout": {"type": layout}, "children": [
              panel("s1", [leaf("a1", "<b>Explore</b><br>free views"), leaf("a2", "Record")]),
              panel("s2", [leaf("b1", "<b>Check</b><br>coverage")]), panel("s3", [leaf("c1", "Answer")])]},
          "edges": [dict(e, provenance=PROV) for e in edges]}
    src = tmp_path / "bp.json"
    src.write_text(json.dumps(bp))
    return src


def test_a_wide_arrow_crosses_the_gap_between_two_stages(tmp_path):
    """User, 2026-11-25 (draw.io audit): one wide arrow for a stage hand-over instead of thin wires between panels."""
    src = _stages(tmp_path, [{"src": "s1", "dst": "s2", "wide": True}, {"src": "s2", "dst": "s3", "wide": True, "label": "pass"},
                             {"src": "a1", "dst": "a2"}])
    r = P.build(src, "friendly", out_dir=tmp_path, formats=("png",))
    assert not [f for f in r.report.findings if f.severity == "error"], r.report.findings
    cells = parse_cells(next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8"))
    wide = [c for c in cells.values() if c.edge and c.style.get("shape") == "flexArrow"]
    assert len(wide) == 2 and all(c.style.get("edgeStyle") == "none" for c in wide)
    s1, s2 = cells["pf-s1"].box, cells["pf-s2"].box
    assert s2.x - s1.right >= 1.8 * 11  # the layout made room for head and shaft
    thin = [c for c in cells.values() if c.edge and c.source == "pf-a1"]
    assert thin and thin[0].style.get("shape") != "flexArrow"


def test_a_wide_arrow_runs_down_between_stacked_stages(tmp_path):
    src = _stages(tmp_path, [{"src": "s1", "dst": "s2", "wide": True}], layout="column")
    r = P.build(src, "friendly", out_dir=tmp_path, formats=())
    cells = parse_cells(next(tmp_path.glob("*.drawio")).read_text(encoding="utf-8"))
    (w,) = [c for c in cells.values() if c.edge and c.style.get("shape") == "flexArrow"]
    assert w.style["exitY"] == "1.0000" and w.style["entryY"] == "0.0000"


def test_a_wide_arrow_that_would_jump_a_stage_is_refused(tmp_path):
    from paperfig.errors import BlueprintError
    src = _stages(tmp_path, [{"src": "s1", "dst": "s3", "wide": True}])
    with pytest.raises(BlueprintError, match="wide arrow"):
        P.build(src, "friendly", out_dir=tmp_path, formats=())
