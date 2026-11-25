"""Intake (user, 2026-11-25): settle up front what used to be found out after a figure was drawn — the venue, the
figures to follow, real images, the page share — and let the user pick the references before the plan, so the costly
steps follow a look the user chose."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

from PIL import Image

from paperfig import artifacts, grammar, run
from test_paradigm_round import _refs
from test_plan import FACTS, plan, write

ROOT = Path(__file__).resolve().parents[1]


def _png(p, size=(300, 120), colour=(70, 130, 220)):
    im = Image.new("RGB", size, "white")
    im.paste(Image.new("RGB", (size[0] // 2, size[1] // 2), colour), (20, 20))
    im.save(p)
    return p


def test_references_is_the_first_confirmation_point(tmp_path):
    assert run.POINTS[0] == "references"
    d = run.init(tmp_path / "r", "interactive", "overview", "cvpr", draft=str(_png(tmp_path / "d.png")), page_share=0.33)
    assert json.loads((d / "run.json").read_text())["figure"]["page_share"] == 0.33
    run.decide(d, "references", "follow 1, 3", by="user", why="the user's own pick")
    assert not any("decision 'references'" in p for p in run.check(d))


def test_picked_names_a_selected_reference(tmp_path):
    crop = _png(tmp_path / "c.png")
    assert artifacts.validate("refs", _refs(tmp_path, crop, picked=["2103.00020"])) == []
    assert any("picked" in p for p in artifacts.validate("refs", _refs(tmp_path, crop, picked=["A Paper Never Found"])))


def test_the_chosen_concept_follows_a_pick(tmp_path):
    crop = _png(tmp_path / "c.png")
    refs = _refs(tmp_path, crop, picked=["2103.00020"])
    facts = write(tmp_path, "facts.json", {"facts": FACTS})
    concepts = [{"id": "c1", "name": "x", "adapts": "uformer-2022-fig2", "takes": "layout"},
                {"id": "c2", "name": "z", "adapts": "2103.00020", "takes": "the similarity matrix"}]
    off = artifacts.validate("figure-plan", write(tmp_path, "p.json", plan(concepts=concepts, chosen="c1")), facts=facts, refs=refs)
    assert any("picked" in p for p in off), off
    on = artifacts.validate("figure-plan", write(tmp_path, "q.json", plan(concepts=concepts, chosen="c2")), facts=facts, refs=refs)
    assert on == [], on


def _run_dir(tmp_path, picked=True, share=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    d = run.init(tmp_path / "r", "interactive", "overview", "cvpr", draft=str(_png(tmp_path / "d.png")), page_share=share)
    (d / "refs").mkdir(exist_ok=True)
    crop = _png(d / "refs" / "fig.png", size=(600, 200))
    doc = json.loads(_refs(tmp_path, crop, **({"picked": ["2103.00020"]} if picked else {})).read_text())
    (d / "refs" / "refs.json").write_text(json.dumps(doc))
    return NS(source_path=d / "blueprint.json", figure=NS(venue="cvpr", width="double", type="overview"))


def test_the_first_pick_sets_the_bar_and_the_page_share_the_shape(tmp_path):
    t = grammar.target_measure(_run_dir(tmp_path))
    assert t and "ink_ratio" in t and "picked" in t["whose"] and abs(t["aspect"] - 3.0) < 0.3  # the crop's own shape
    t = grammar.target_measure(_run_dir(tmp_path / "b", share=0.5))
    assert abs(t["aspect"] - 6.875 / (0.5 * grammar.TEXT_HEIGHT_IN)) < 1e-6 and "ink_ratio" in t
    t = grammar.target_measure(_run_dir(tmp_path / "c", picked=False, share=0.25))
    assert "ink_ratio" not in t and "page share" in t["whose"]  # shape only: no look was chosen
    assert grammar.target_measure(_run_dir(tmp_path / "d", picked=False)) is None


def test_the_sheet_numbers_the_selected_figures(tmp_path):
    crop = _png(tmp_path / "c.png")
    refs = _refs(tmp_path, crop)
    out = tmp_path / "sheet.png"
    r = subprocess.run([sys.executable, "-m", "paperfig", "refs", "sheet", str(refs), "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file()
