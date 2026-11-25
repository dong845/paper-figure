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
