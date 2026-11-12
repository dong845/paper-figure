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
    with pytest.raises(PaperFigError, match="auto mode"):
        run.decide(d, "blueprint", "approved", by="user", why="y")
    assert [x["point"] for x in json.loads((d / "run.json").read_text())["decisions"]] == ["style"]


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
    probs = run.check(d)
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
