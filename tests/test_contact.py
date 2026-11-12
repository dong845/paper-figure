from PIL import Image

from paperfig.contact import compose


def mk(tmp_path, name, size, color):
    p = tmp_path / name
    Image.new("RGB", size, color).save(p)
    return p


def test_contact_sheet_wide_panels_stack(tmp_path):
    a = mk(tmp_path, "a.png", (900, 300), "red")
    b = mk(tmp_path, "b.png", (1200, 400), "blue")
    out = compose([("Original", a), ("B", b)], tmp_path / "s.png", width=1000)
    with Image.open(out) as im:
        w, h = im.size
    assert w == 1000 + 2 * 30
    assert h > 2 * (1000 / 3)  # stacked


def test_contact_sheet_tall_panels_side_by_side(tmp_path):
    a = mk(tmp_path, "a.png", (300, 400), "red")
    b = mk(tmp_path, "b.png", (600, 800), "blue")
    out = compose([("A", a), ("B", b)], tmp_path / "s.png", height=500)
    with Image.open(out) as im:
        w, h = im.size
    assert h < 700 and w > 2 * 300


def test_contact_missing_panel_raises(tmp_path):
    import pytest
    from paperfig.errors import PaperFigError
    with pytest.raises(PaperFigError, match="nope.png"):
        compose([("A", tmp_path / "nope.png")], tmp_path / "s.png")
