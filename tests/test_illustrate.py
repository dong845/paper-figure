"""Round 7 ③: concept illustrations by the Codex subscription — scene/actor elements only (a household, a robot arm,
a user), never data, inputs or results; always marked illustrative, the render mode inside the prompt, and every
raster checked against its printed size."""
import copy
import json

import pytest
from PIL import Image

from conftest import PROV, leaf
from paperfig import pipeline as P
from paperfig.blueprint import load
from paperfig.errors import BlueprintError


def _bp(asset, illustrative=True, size=None):
    n = leaf("env", "Household", visual="image", asset=asset, illustrative=illustrative, **({"size": size} if size else {}))
    return {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
            "root": {"id": "root", "layout": {"type": "row"}, "children": [leaf("agent", "Agent"), n]},
            "edges": [{"src": "agent", "dst": "env", "provenance": copy.deepcopy(PROV)}]}


SPEC = "a 7-DoF robot arm above a tabletop with three coloured blocks"
GROUNDS = {"ref": "Sec. 4", "quote": "a 7-DoF Franka arm manipulates coloured blocks on a tabletop"}
TEXT = "4 Experiments. In our setup a 7-DoF Franka arm manipulates coloured blocks on a tabletop under camera view."


def test_generated_image_must_be_marked_and_carry_its_prompt(tmp_path):
    with pytest.raises(BlueprintError, match="illustrative"):
        load(_bp({"status": "generated", "spec": SPEC, "grounds": GROUNDS}, illustrative=False))
    with pytest.raises(BlueprintError, match="spec"):
        load(_bp({"status": "generated", "grounds": GROUNDS}))
    with pytest.raises(BlueprintError, match="grounds"):  # the scene must come from the paper, not be invented
        load(_bp({"status": "generated", "spec": SPEC}))
    load(_bp({"status": "generated", "spec": SPEC, "grounds": GROUNDS}))  # not generated yet: drawn as a placeholder


def test_manifest_prompt_carries_render_mode_palette_and_no_text(tmp_path):
    from paperfig.illustrate import manifest
    (tmp_path / "b.json").write_text(json.dumps(_bp({"status": "generated", "spec": SPEC, "grounds": GROUNDS})))
    items = manifest(tmp_path / "b.json", "soft-pastel", tmp_path / "assets")
    assert [i["filename"] for i in items] == ["env.png"]
    p = items[0]["prompt"]
    assert SPEC in p and "RENDER MODE" in p and "no text" in p.lower() and "#" in p  # palette hexes inside
    assert "white background" in p.lower()


def test_low_resolution_raster_is_flagged(tmp_path):
    Image.new("RGB", (40, 30), "#88aacc").save(tmp_path / "tiny.png")
    d = _bp({"status": "provided", "path": str(tmp_path / "tiny.png")}, size=[150, 110])
    (tmp_path / "b.json").write_text(json.dumps(d))
    res = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert any(f.code == "asset-resolution" and "env" in f.ids for f in res.report.findings)


def test_transparent_margins_are_trimmed(tmp_path):
    from paperfig.illustrate import trim
    im = Image.new("RGBA", (1000, 800), (0, 0, 0, 0))
    for x in range(300, 700):
        for y in range(200, 600):
            im.putpixel((x, y), (120, 160, 200, 255))
    p = tmp_path / "a.png"
    im.save(p)
    trim(p)
    w, h = Image.open(p).size
    assert 400 <= w <= 440 and 400 <= h <= 440  # the subject plus a small pad, not the empty canvas


def test_illustration_needs_a_quote_the_source_really_contains(tmp_path):
    """User 2026-11-14: 'the environment is a kitchen?' — Reflexion's environments are a text game, a Wikipedia API
    and unit tests; a picture the paper never describes is invented, so the quote is checked before any generation."""
    from paperfig.illustrate import check_grounds
    t = tmp_path / "method.txt"
    t.write_text(TEXT)
    ok = _bp({"status": "generated", "spec": SPEC, "grounds": GROUNDS})
    (tmp_path / "ok.json").write_text(json.dumps(ok))
    assert check_grounds(tmp_path / "ok.json", text=t) == {}
    bad = _bp({"status": "generated", "spec": "a kitchen with a sink",
               "grounds": {"ref": "Sec. 3", "quote": "the agent acts in a household kitchen with a sink"}})
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    probs = check_grounds(tmp_path / "bad.json", text=t)
    assert "env" in probs and "not found" in probs["env"]
    import pytest
    from paperfig.errors import PaperFigError
    from paperfig.illustrate import run
    with pytest.raises(PaperFigError, match="not found"):
        run(tmp_path / "bad.json", "soft-pastel", tmp_path / "assets", text=t)
    with pytest.raises(PaperFigError, match="--text"):  # nothing to check against: refuse, never trust
        run(tmp_path / "ok.json", "soft-pastel", tmp_path / "assets")


def test_run_check_rejects_an_ungrounded_illustration(tmp_path):
    from paperfig import run
    from test_run import _complete_run
    d = _complete_run(tmp_path)
    bp = _bp({"status": "generated", "spec": "a kitchen", "grounds": {"ref": "Sec. 3", "quote": "a household kitchen with a sink"}})
    (d / "blueprint.json").write_text(json.dumps(bp))
    assert any("grounds quote not found" in p for p in run.check(d)), run.check(d)
