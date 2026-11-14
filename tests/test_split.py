"""Round 8: overview + detail panels that crowd the print below 7 pt — suggest (and do) the split top-venue papers
use: an overview figure and a separate module figure, each with its own share of the facts."""
import copy
import json
from pathlib import Path

from paperfig import pipeline as P
from paperfig.blueprint import load

CORPUS = Path(__file__).resolve().parents[1] / "bench/corpus/pointnet"


def _pointnet(tmp_path, width="double"):
    d = json.loads((CORPUS / "blueprint.json").read_text())
    d["figure"]["width"] = width
    for a in d["root"]["children"]:  # grey stand-in images resolve next to the copy
        if a.get("asset", {}).get("path"):
            a["asset"]["path"] = str(CORPUS / a["asset"]["path"])
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    for f in ("facts.json", "figure_plan.json"):
        (tmp_path / f).write_text((CORPUS / f).read_text())
    return tmp_path / "blueprint.json"


def test_split_parts_move_the_panel_and_its_facts(tmp_path):
    from paperfig.split import split
    res = split(_pointnet(tmp_path), tmp_path / "parts")
    ov = json.loads(Path(res["overview"]).read_text())
    ids = set()

    def walk(n):
        ids.add(n["id"])
        for c in n.get("children", []):
            walk(c)
    walk(ov["root"])
    assert "basic_module" not in ids and "bm_max" not in ids  # the panel left the overview
    src = next(n for n in ov["root"]["children"] if n["id"] == "maxpool")
    assert "Fig. 2" in src["label"]
    (mod,) = res["modules"]
    m = json.loads(Path(mod).read_text())
    assert m["figure"]["type"] == "module-detail" and {c["id"] for c in m["root"]["children"]} >= {"bm_max"}
    for part in [res["overview"], mod]:  # each part builds; its facts and plan name only what it draws (no gate errors)
        load(part)
        r = P.build(part, "editorial-minimal", out_dir=Path(part).parent / "o", formats=())
        assert not [f for f in r.report.findings if f.severity == "error"], [f.message for f in r.report.findings if f.severity == "error"]


def test_crowded_overview_with_panels_suggests_the_split(tmp_path):
    r = P.build(_pointnet(tmp_path / "s", "single"), "editorial-minimal", out_dir=tmp_path / "o", formats=())
    f = next(f for f in r.report.findings if f.code == "split-suggested")
    assert f.severity == "warn" and "overview" in f.message and "pt" in f.message


def test_no_suggestion_when_the_print_is_large_enough(tmp_path):
    r = P.build(_pointnet(tmp_path / "d", "double"), "editorial-minimal", out_dir=tmp_path / "o", formats=())
    if (r.report.stats.get("smallest_text_pt") or 0) >= 7.0:
        assert not [f for f in r.report.findings if f.code == "split-suggested"]


def test_omitted_facts_stay_with_the_overview(tmp_path):
    from paperfig.split import split
    res = split(_pointnet(tmp_path), tmp_path / "parts")
    assert res["dropped_facts"] == []
    ov = Path(res["overview"]).parent
    assert "l_reg->softmax_loss" in {f["id"] for f in json.loads((ov / "facts.json").read_text())["facts"]}
    assert any(o["fact"] == "l_reg->softmax_loss" for o in json.loads((ov / "figure_plan.json").read_text())["omitted"])


def test_suggestion_says_when_splitting_does_not_fix_it(tmp_path):
    """Single column: the PointNet overview alone is still far below 7 pt — say so instead of promising a fix."""
    r = P.build(_pointnet(tmp_path / "s", "single"), "editorial-minimal", out_dir=tmp_path / "o", formats=())
    f = next(f for f in r.report.findings if f.code == "split-suggested")
    assert "too wide" in f.message and "double" in f.message


def test_facts_scoped_to_a_panel_move_with_it(tmp_path):
    """Restormer: the facts inside the MDTA / GDFN panels are scoped to the panel; the panel becomes the figure."""
    import shutil
    from paperfig.split import split
    src = Path(__file__).resolve().parents[1] / "bench/corpus/restormer"
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(src / f, tmp_path / f)
    res = split(tmp_path / "blueprint.json", tmp_path / "parts")
    assert res["dropped_facts"] == []
    for part in res["modules"]:
        facts = json.loads((Path(part).parent / "facts.json").read_text())["facts"]
        assert facts and all("scope" not in f for f in facts)
        r = P.build(part, "soft-pastel", out_dir=Path(part).parent / "o", formats=())
        assert not [f for f in r.report.findings if f.code.startswith("fact") and f.severity == "error"]


def _restormer_parts(tmp_path):
    import shutil
    from paperfig.split import split
    src = Path(__file__).resolve().parents[1] / "bench/corpus/restormer"
    for f in ("blueprint.json", "facts.json"):
        shutil.copy(src / f, tmp_path / f)
    return split(tmp_path / "blueprint.json", tmp_path / "parts", style="soft-pastel")


def test_module_figures_follow_the_panel_letters_and_fit_their_width(tmp_path):
    res = _restormer_parts(tmp_path)
    names = [Path(m).parent.name for m in res["modules"]]
    assert names == ["module-mp", "module-gp"]  # (a) MDTA is Fig. 2, (b) GDFN is Fig. 3
    ov = json.loads(Path(res["overview"]).read_text())
    blk = json.dumps(ov)
    assert "MDTA" in blk and "(Fig. 2)" in blk.split("MDTA", 1)[1].split("GDFN")[0]
    widths = {Path(m).parent.name: json.loads(Path(m).read_text())["figure"]["width"] for m in res["modules"]}
    assert widths["module-gp"] == "single"  # a small module is a column figure, not a page-wide blow-up
    for m in res["modules"]:
        r = P.build(m, "soft-pastel", out_dir=Path(m).parent / "o", formats=())
        assert 7.0 <= r.report.stats["smallest_text_pt"] <= 12.0, (m, r.report.stats["smallest_text_pt"])


def test_legend_notes_follow_the_part(tmp_path):
    res = _restormer_parts(tmp_path)
    gp = json.loads(Path([m for m in res["modules"] if m.endswith("module-gp/blueprint.json")][0]).read_text())
    notes = " ".join(gp["figure"].get("legend_notes", []))
    assert "pixel-(un)shuffle" not in notes and "Dconv" in notes
