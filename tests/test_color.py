import pytest

from paperfig import color as C


def test_contrast_black_white_21():
    assert C.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert C.contrast("#ffffff", "#ffffff") == pytest.approx(1.0)


def test_contrast_symmetric():
    assert C.contrast("#1e3a8a", "#e8f0fe") == pytest.approx(C.contrast("#e8f0fe", "#1e3a8a"))


@pytest.mark.parametrize("lab1,lab2,expected", [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),   # Sharma 2005 pair 1
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),               # pair 7
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),            # pair 17
])
def test_de2000_reference_pairs(lab1, lab2, expected):
    assert C.de2000_lab(lab1, lab2) == pytest.approx(expected, abs=1e-3)


def test_lab_of_white():
    L, a, b = C.lab("#ffffff")
    assert L == pytest.approx(100, abs=0.05) and abs(a) < 0.05 and abs(b) < 0.05


def test_deutan_collapses_red_green():
    normal = C.de2000("#d62728", "#2ca02c")
    sim = C.de2000(C.simulate("#d62728", "deutan"), C.simulate("#2ca02c", "deutan"))
    assert normal > 40 and sim < 15


def test_gray_simulation_is_neutral():
    g = C.simulate("#3fa66b", "gray")
    r, gg, b = C.hex_rgb(g)
    assert r == gg == b


def test_bad_hex_raises():
    with pytest.raises(ValueError):
        C.hex_rgb("blue")
