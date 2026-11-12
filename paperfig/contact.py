"""Contact sheet: labelled panels (e.g. Original | B | C) for side-by-side review."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .errors import PaperFigError

GUTTER, LABEL_H = 30, 44


def _font(size):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose(panels: list[tuple[str, Path]], out, width: int = 1600, height: int = 700) -> Path:
    ims = []
    for label, p in panels:
        p = Path(p)
        if not p.is_file():
            raise PaperFigError(f"contact sheet panel not found: {p}")
        im = Image.open(p).convert("RGB")
        ims.append((label, im))
    mean_aspect = sum(im.width / im.height for _, im in ims) / len(ims)
    font = _font(26)
    if mean_aspect > 1.6:  # wide figures: stack, equal width
        scaled = [(l, im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)) for l, im in ims]
        W = width + 2 * GUTTER
        H = GUTTER + sum(LABEL_H + im.height + GUTTER for _, im in scaled)
        sheet = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(sheet)
        y = GUTTER
        for l, im in scaled:
            d.text((GUTTER, y + 6), l, fill="#111827", font=font)
            sheet.paste(im, (GUTTER, y + LABEL_H))
            d.rectangle([GUTTER - 1, y + LABEL_H - 1, GUTTER + im.width, y + LABEL_H + im.height], outline="#d1d5db")
            y += LABEL_H + im.height + GUTTER
    else:
        scaled = [(l, im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)) for l, im in ims]
        W = GUTTER + sum(im.width + GUTTER for _, im in scaled)
        H = GUTTER + LABEL_H + height + GUTTER
        sheet = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(sheet)
        x = GUTTER
        for l, im in scaled:
            d.text((x, GUTTER + 6), l, fill="#111827", font=font)
            sheet.paste(im, (x, GUTTER + LABEL_H))
            d.rectangle([x - 1, GUTTER + LABEL_H - 1, x + im.width, GUTTER + LABEL_H + im.height], outline="#d1d5db")
            x += im.width + GUTTER
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
