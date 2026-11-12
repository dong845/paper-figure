import pytest

from paperfig import measure as M


def test_measure_grows_with_text():
    w1, _ = M.measure("Enc", 12)
    w2, _ = M.measure("Encoder block", 12)
    assert w2 > w1 > 0


def test_scales_with_size():
    w12, h12 = M.measure("Encoder", 12)
    w24, h24 = M.measure("Encoder", 24)
    assert w24 == pytest.approx(2 * w12, rel=0.05)
    assert h24 == pytest.approx(2 * h12, rel=0.05)


def test_bold_wider_than_regular():
    assert M.measure("Encoder", 12, bold=True)[0] > M.measure("Encoder", 12)[0]


def test_markup_bold_run_wider():
    assert M.measure("<b>Encoder</b>", 12)[0] > M.measure("Encoder", 12)[0]


def test_two_lines_taller():
    _, h1 = M.measure("Multi-Scale", 12)
    w2, h2 = M.measure("Multi-Scale<br>Attention", 12)
    assert h2 == pytest.approx(2 * h1)
    assert w2 == pytest.approx(M.measure("Multi-Scale", 12)[0])  # widest line


def test_sub_is_smaller():
    assert M.measure("x<sub>tt</sub>", 12)[0] < M.measure("xtt", 12)[0]


def test_cjk_measured_wider_than_latin_fallback():
    w, _ = M.measure("特征融合", 12)
    assert w >= 4 * 12 * 0.95


def test_symbol_outside_primary_font_measured():
    w, _ = M.measure("⊕", 12)
    assert 4 < w < 20


def test_measure_without_any_font_falls_back_to_estimate(monkeypatch):
    monkeypatch.setattr(M, "_FONT_CACHE", {})
    monkeypatch.setattr(M, "_candidates", lambda family, bold: [])
    monkeypatch.setattr(M, "_fallback_candidates", lambda: [])
    w, h = M.measure("abcd", 10)
    assert w == pytest.approx(4 * 0.6 * 10)
    assert h == pytest.approx(10 * M.LINE_HEIGHT)


def test_empty_label_zero_width():
    w, h = M.measure("", 12)
    assert w == 0 and h == pytest.approx(12 * M.LINE_HEIGHT)
