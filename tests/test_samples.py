import json
import subprocess
import sys

import pytest
from PIL import Image

from paperfig import pipeline, samples
from paperfig.errors import PaperFigError, ExportError
from paperfig.export import find_drawio

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


@needs_drawio
def test_samples_builds_each_style_and_sheet(mini_bp, tmp_path):
    bpp = write_bp(tmp_path, mini_bp)
    res = samples.make_samples(bpp, ["soft-pastel", "depth-cv", "editorial-minimal"], out_dir=tmp_path / "s")
    assert [s.style for s in res.shown] == ["soft-pastel", "depth-cv", "editorial-minimal"] and res.skipped == []
    for s in res.shown:
        assert s.png.is_file() and s.png.parent == tmp_path / "s" / s.style
    sheet = Image.open(res.sheet)
    scaled = [Image.open(s.png).height * min(1.0, sheet.width / Image.open(s.png).width) for s in res.shown]
    assert sheet.height >= 0.9 * sum(scaled) and res.sheet.name == "samples.png"  # all three panels stacked
    assert json.loads((tmp_path / "s" / "samples.json").read_text())["shown"][0]["style"] == "soft-pastel"


@needs_drawio
def test_samples_skips_failing_style_with_reason(mini_bp, tmp_path, monkeypatch):
    real = pipeline.build

    def build(bp, style=None, *a, **k):
        res = real(bp, style, *a, **k)
        if style == "depth-cv":
            res.report.add("text-overflow", "error", ["enc"], "label 'Encoder' overflows its box")
        return res

    monkeypatch.setattr(pipeline, "build", build)
    bpp = write_bp(tmp_path, mini_bp)
    res = samples.make_samples(bpp, ["soft-pastel", "depth-cv", "no-such-style"], out_dir=tmp_path / "s")
    assert [s.style for s in res.shown] == ["soft-pastel"]
    reasons = dict(res.skipped)
    assert "text-overflow" in reasons["depth-cv"] and "no-such-style" in reasons
    assert "no-such-style" in json.dumps(json.loads((tmp_path / "s" / "samples.json").read_text())["skipped"])


@needs_drawio
def test_samples_all_failing_is_an_error(mini_bp, tmp_path):
    bpp = write_bp(tmp_path, mini_bp)
    with pytest.raises(PaperFigError, match="no sample passed"):
        samples.make_samples(bpp, ["nope-a", "nope-b"], out_dir=tmp_path / "s")


def test_samples_rejects_empty_style_list(mini_bp, tmp_path):
    with pytest.raises(PaperFigError, match="at least one style"):
        samples.make_samples(write_bp(tmp_path, mini_bp), [], out_dir=tmp_path / "s")


@needs_drawio
def test_samples_cli(mini_bp, tmp_path):
    bpp = write_bp(tmp_path, mini_bp)
    r = subprocess.run([sys.executable, "-m", "paperfig", "samples", str(bpp), "--styles", "soft-pastel,nope",
                        "--out", str(tmp_path / "s")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped nope" in r.stdout and "samples.png" in r.stdout
