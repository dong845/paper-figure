import json
import subprocess
import sys

import pytest

from paperfig import run
from paperfig.errors import PaperFigError


def test_init_creates_layout_and_record(tmp_path):
    d = run.init(tmp_path / "r", mode="auto", figure_type="overview", venue="cvpr", draft=str(tmp_path / "p.pdf"),
                 paper_title="Restormer", arxiv_id="2111.09881")
    rec = json.loads((d / "run.json").read_text())
    assert rec["mode"] == "auto" and rec["figure"] == {"type": "overview", "venue": "cvpr", "focus": None}
    assert rec["paper"] == {"title": "Restormer", "arxiv_id": "2111.09881"}
    assert rec["inputs"]["draft"].endswith("p.pdf") and rec["inputs"]["code"] is None
    assert "kb_version" in rec and rec["decisions"] == [] and rec["rounds"] == []
    for sub in ("inputs", "assets", "refs", "samples", "build", "critic"):
        assert (d / sub).is_dir()
    with pytest.raises(PaperFigError, match="already"):
        run.init(tmp_path / "r", mode="auto", figure_type="overview")


def test_init_needs_draft_or_code(tmp_path):
    with pytest.raises(PaperFigError, match="draft or code"):
        run.init(tmp_path / "r", mode="interactive", figure_type="overview")


def test_decide_validates_point_and_actor(tmp_path):
    d = run.init(tmp_path / "r", mode="auto", figure_type="overview", code=str(tmp_path))
    run.decide(d, "style", "soft-pastel", by="auto", why="design brief recommends it for CV")
    with pytest.raises(PaperFigError, match="point"):
        run.decide(d, "colour", "x", by="auto", why="y")
    # the user may step into an auto run (pilot: a delivery-gate revision had to be recorded as --by auto, F56)
    run.decide(d, "delivery", "revise", by="user", why="user: name the CNN part")
    assert [(x["point"], x["by"]) for x in json.loads((d / "run.json").read_text())["decisions"]] == \
        [("style", "auto"), ("delivery", "user")]


def _complete_run(tmp_path, mode="auto"):
    """A run directory with every required artifact, using the test fixtures' minimal valid files."""
    from test_artifacts import TEXT, draft

    d = run.init(tmp_path / "r", mode=mode, figure_type="overview", draft=str(tmp_path / "p.pdf"))
    (d / "inputs" / "method.txt").write_text(TEXT)
    (d / "analysis.draft.json").write_text(json.dumps(draft()))
    (d / "facts.json").write_text(json.dumps({"facts": [{"id": "f1", "from": "inp", "to": "embed",
                                                          "quote": "first applies a convolution", "ref": "Sec. 3"}]}))
    return d


def test_check_lists_everything_missing(tmp_path):
    d = _complete_run(tmp_path)
    probs = run.check(d, final=True)
    for need in ("blueprint.json", "brief.json", "refs/refs.json", "samples/samples.json", "round", "report.md"):
        assert any(need in p for p in probs), (need, probs)
    for point in ("blueprint", "assets", "style", "delivery"):
        assert any(f"decision '{point}'" in p for p in probs)


def test_check_flags_invalid_artifacts(tmp_path):
    d = _complete_run(tmp_path)
    bad = json.loads((d / "analysis.draft.json").read_text())
    bad["components"][0]["provenance"]["quote"] = "words that are not in the method text"
    (d / "analysis.draft.json").write_text(json.dumps(bad))
    assert any("analysis.draft.json" in p and "not found" in p for p in run.check(d))


def test_round_records_lint_and_critic(tmp_path):
    d = _complete_run(tmp_path)
    b = d / "build" / "r1"
    b.mkdir()
    (b / "fig.lint.json").write_text(json.dumps({"ok": True, "counts": {"error": 0, "warn": 2, "info": 3}, "stats": {}, "findings": []}))
    (d / "critic" / "r1.json").write_text(json.dumps({"viewed_png": True, "scores": {"faithfulness": 4, "conciseness": 4,
                                                       "readability": 4, "aesthetics": 3, "salience": 4}, "issues": [], "io_audit": []}))
    run.record_round(d, 1, b / "fig.lint.json", d / "critic" / "r1.json", "first build")
    rec = json.loads((d / "run.json").read_text())
    assert rec["rounds"][0]["lint"]["error"] == 0 and rec["rounds"][0]["critic"]["aesthetics"] == 3
    with pytest.raises(PaperFigError, match="viewed"):
        (d / "critic" / "r2.json").write_text(json.dumps({"viewed_png": False, "scores": {}, "issues": []}))
        run.record_round(d, 2, b / "fig.lint.json", d / "critic" / "r2.json", "x")


def test_run_cli_roundtrip(tmp_path):
    r = subprocess.run([sys.executable, "-m", "paperfig", "run", "init", str(tmp_path / "r"), "--mode", "auto",
                        "--type", "overview", "--code", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "paperfig", "run", "decide", str(tmp_path / "r"), "--point", "assets",
                        "--decision", "placeholders for 2 images", "--by", "auto", "--why", "benchmark: no user"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "paperfig", "run", "check", str(tmp_path / "r")], capture_output=True, text=True)
    assert r.returncode == 1 and "decision 'style'" in r.stdout


def test_check_reports_malformed_record_instead_of_crashing(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "run.json").write_text(json.dumps({"mode": "auto", "decisions": [], "rounds": []}))
    probs = run.check(d)
    assert any("inputs" in p for p in probs)


REPORT = "# Report\n\n## Figure\nx\n\n## References\nx\n\n## Rounds\nx\n\n## Open issues\nnone\n\n## Placeholders\nnone\n"


def test_check_before_delivery_does_not_need_the_delivery_decision(tmp_path):
    d = _complete_run(tmp_path)
    for p in ("blueprint", "assets", "style"):
        run.decide(d, p, "x", by="auto", why="y")
    assert not any("decision 'delivery'" in p for p in run.check(d))
    assert any("decision 'delivery'" in p for p in run.check(d, final=True))


def test_deliver_copies_last_round_and_final_check_verifies(tmp_path):
    d = _complete_run(tmp_path)
    for n in (1, 2):
        b = d / "build" / f"r{n}"
        b.mkdir()
        for ext in ("drawio", "png", "pdf", "lint.md"):
            (b / f"fig.{ext}").write_text(f"round {n} {ext}")
        (b / "fig.lint.json").write_text(json.dumps({"ok": True, "counts": {"error": 0, "warn": 0, "info": 0}, "stats": {}}))
        (d / "critic" / f"r{n}.json").write_text(json.dumps({"viewed_png": True, "scores": {}, "issues": []}))
        run.record_round(d, n, b / "fig.lint.json", d / "critic" / f"r{n}.json", "")
    (d / "report.md").write_text(REPORT)
    out = tmp_path / "deliver"
    run.deliver(d, out)
    assert (out / "fig.png").read_text() == "round 2 png" and (out / "report.md").is_file()
    (out / "fig.png").write_text("edited by hand")
    assert any("fig.png" in p and "last round" in p for p in run.check(d, final=True))


def test_check_requires_brief_md_and_report_sections(tmp_path):
    d = _complete_run(tmp_path)
    (d / "report.md").write_text("# Report\nall good\n")
    probs = run.check(d)
    assert any("brief.md" in p for p in probs) and any("report.md" in p and "Open issues" in p for p in probs)


def test_round_needs_reader_test_when_planned(tmp_path):
    d = _complete_run(tmp_path)
    (d / "figure_plan.json").write_text(json.dumps({"takeaway": "x" * 12}))
    b = d / "build" / "r1"
    b.mkdir()
    (b / "fig.lint.json").write_text(json.dumps({"ok": True, "counts": {"error": 0, "warn": 0, "info": 0}, "stats": {}, "findings": []}))
    crit = {"viewed_png": True, "scores": {"faithfulness": 4}, "issues": [], "io_audit": []}
    (d / "critic" / "r1.json").write_text(json.dumps(crit))
    with pytest.raises(PaperFigError, match="reader"):
        run.record_round(d, 1, b / "fig.lint.json", d / "critic" / "r1.json", "")
    crit["reader"] = {"takeaway_from_png": "A CNN-transformer encoder feeds a cascaded upsampler that outputs a mask.",
                      "top_level_units": 6, "crossings": 0, "bends": 3}
    (d / "critic" / "r1.json").write_text(json.dumps(crit))
    run.record_round(d, 1, b / "fig.lint.json", d / "critic" / "r1.json", "")
    rec = json.loads((d / "run.json").read_text())
    assert rec["rounds"][0]["reader"]["top_level_units"] == 6


def test_planned_report_lists_omitted(tmp_path):
    d = _complete_run(tmp_path)
    (d / "report.md").write_text(REPORT)
    assert not any("Omitted" in p for p in run.check(d))
    (d / "figure_plan.json").write_text(json.dumps({"takeaway": "x" * 12}))
    assert any("report.md" in p and "Omitted" in p for p in run.check(d))
