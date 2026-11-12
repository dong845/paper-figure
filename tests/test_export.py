import os
import stat

import pytest
from PIL import Image

from paperfig import export as X
from paperfig.errors import ExportError
from paperfig.measure import measure

try:
    DRAWIO = X.find_drawio()
except ExportError:
    DRAWIO = None
needs_drawio = pytest.mark.skipif(DRAWIO is None, reason="draw.io desktop not installed")

TINY = ('<mxfile><diagram name="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="a" value="A" style="rounded=0;" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="50" as="geometry"/></mxCell>'
        '</root></mxGraphModel></diagram></mxfile>')


def fake_bin(tmp_path, body):
    p = tmp_path / "fake-drawio"
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPERFIG_DRAWIO", str(tmp_path / "nope"))
    with pytest.raises(ExportError, match="PAPERFIG_DRAWIO"):
        X.find_drawio()


def test_env_binary_used(monkeypatch, tmp_path):
    b = fake_bin(tmp_path, "exit 0")
    monkeypatch.setenv("PAPERFIG_DRAWIO", b)
    assert X.find_drawio() == b


def test_timeout_raises(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    b = fake_bin(tmp_path, "sleep 5")
    with pytest.raises(ExportError, match="timed out"):
        X.export(src, "png", tmp_path / "a.png", binary=b, timeout_s=1)


def test_no_output_file_raises(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    b = fake_bin(tmp_path, "exit 0")
    with pytest.raises(ExportError, match="no output"):
        X.export(src, "png", tmp_path / "a.png", binary=b)


def test_nonzero_exit_raises_with_stderr(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    b = fake_bin(tmp_path, "echo boom >&2; exit 3")
    with pytest.raises(ExportError, match="boom"):
        X.export(src, "png", tmp_path / "a.png", binary=b)


def test_stale_output_not_accepted(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    out = tmp_path / "a.png"
    out.write_bytes(b"old")
    os.utime(out, (1, 1))
    b = fake_bin(tmp_path, "exit 0")
    with pytest.raises(ExportError, match="no output"):
        X.export(src, "png", out, binary=b)


def test_print_px():
    assert X.print_px(6.875, 300) == 2063


@needs_drawio
def test_real_export_png(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    out = X.export(src, "png", tmp_path / "a.png", width_px=600)
    with Image.open(out) as im:
        assert abs(im.size[0] - 600) <= 2


@needs_drawio
def test_real_export_pdf(tmp_path):
    src = tmp_path / "a.drawio"
    src.write_text(TINY)
    out = X.export(src, "pdf", tmp_path / "a.pdf")
    assert out.read_bytes()[:4] == b"%PDF"


def _dark_extent(png, thresh=128):
    with Image.open(png) as im:
        g = im.convert("L")
        w, h = g.size
        px = g.load()
        cols = [x for x in range(w) if any(px[x, y] < thresh for y in range(h))]
    return (min(cols), max(cols)) if cols else None


@needs_drawio
@pytest.mark.parametrize("label,bold", [("Cross-Scale Fusion Module (CSFM)", False), ("Cross-Scale Fusion Module (CSFM)", True),
                                        ("Multi-Dconv Head Transposed Attention", False)])
def test_measure_matches_drawio_render(tmp_path, label, bold):
    """PIL widths (used for box sizing and the overflow lint) must match drawio's browser rendering."""
    pred, _ = measure(label, 12, bold)
    style = f"text;html=1;whiteSpace=nowrap;fontFamily=Helvetica;fontSize=12;fontStyle={1 if bold else 0};spacing=0;align=left;fillColor=none;strokeColor=none;"
    xml = ('<mxfile><diagram name="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
           f'<mxCell id="t" value="{label}" style="{style}" vertex="1" parent="1"><mxGeometry x="0" y="0" width="{pred + 40:.0f}" height="20" as="geometry"/></mxCell>'
           '</root></mxGraphModel></diagram></mxfile>')
    src = tmp_path / "t.drawio"
    src.write_text(xml)
    scale = 4
    out = X.export(src, "png", tmp_path / "t.png", scale=scale, border=0)
    lo, hi = _dark_extent(out)
    rendered = (hi - lo + 1) / scale
    assert rendered == pytest.approx(pred, rel=0.04, abs=2), (rendered, pred)
