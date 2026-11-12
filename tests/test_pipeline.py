import json
import subprocess
import sys

import pytest

from paperfig import pipeline as P
from paperfig.errors import PaperFigError
from paperfig.export import find_drawio
from paperfig.errors import ExportError

try:
    find_drawio()
    HAVE = True
except ExportError:
    HAVE = False
needs_drawio = pytest.mark.skipif(not HAVE, reason="draw.io desktop not installed")


def write_bp(tmp_path, d):
    p = tmp_path / "fig" / "blueprint.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(d))
    return p


def test_formats_have_sources():
    kb = P.load_formats()
    for key in ("neurips", "iclr", "icml", "cvpr"):
        v = kb[key]
        assert v["source_url"].startswith("https://") and v["verified"] and v["textwidth_in"] > 0


def test_venue_width_single_double(mini_bp):
    from paperfig.blueprint import load
    bp = load(mini_bp)
    assert P.venue_width(bp.figure) == pytest.approx(6.875)
    bp.figure.width = "single"
    assert P.venue_width(bp.figure) == pytest.approx(3.28125)
    bp.figure.width = 4.0
    assert P.venue_width(bp.figure) == 4.0


def test_unknown_venue_needs_numeric_width(mini_bp):
    from paperfig.blueprint import load
    bp = load(mini_bp)
    bp.figure.venue = "obscureconf"
    with pytest.raises(PaperFigError, match="obscureconf"):
        P.venue_width(bp.figure)


@needs_drawio
def test_build_end_to_end_mini(mini_bp, tmp_path):
    bpp = write_bp(tmp_path, mini_bp)
    res = P.build(bpp, "soft-pastel", out_dir=tmp_path / "out")
    for f in (res.drawio, res.png, res.pdf, res.lint_md, res.lint_json):
        assert f.is_file() and f.stat().st_size > 0
    assert res.report.ok, res.report.to_markdown()
    assert not any(f.code == "png-mismatch" for f in res.report.findings)
    assert res.png.name == "fig.png"


@needs_drawio
def test_build_reports_errors_exit_code(mini_bp, tmp_path):
    mini_bp["root"]["children"][1]["label"] = "x " * 3
    mini_bp["figure"]["width"] = 0.5  # absurdly narrow -> min-font error
    bpp = write_bp(tmp_path, mini_bp)
    r = subprocess.run([sys.executable, "-m", "paperfig", "build", str(bpp), "--style", "soft-pastel", "--out", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "min-font" in r.stdout


def test_cli_reports_blueprint_errors_cleanly(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{}")
    r = subprocess.run([sys.executable, "-m", "paperfig", "build", str(p)], capture_output=True, text=True)
    assert r.returncode == 2 and "blueprint has" in r.stderr and "Traceback" not in r.stderr


def test_cli_mix_parsing():
    from paperfig.__main__ import parse_mix
    assert parse_mix(["effects=depth-cv", "tensor=depth-cv"]) == {"effects": "depth-cv", "tensor": "depth-cv"}
    with pytest.raises(SystemExit):
        parse_mix(["bad"])
