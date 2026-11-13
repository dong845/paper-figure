"""Measurements for figure cards, computed from a figure crop (never estimated by eye)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageChops

from .color import de2000, lab
from .errors import PaperFigError

WHITE_MIN = 245  # a pixel is background when its darkest channel is at least this
MERGE_DE = 4.0  # clusters closer than this (CIEDE2000) are one colour (pastel panels differ subtly)
NEUTRAL_CHROMA = 2.5  # CIELAB chroma below this is gray; pastel tints (#e6f0f8 = 5.3) are colours
CHROMA_SPREAD = 20  # max(R,G,B) - min(R,G,B) above this: a chromatic pixel
MIN_SHARE_CHROMA = 0.02  # of the chromatic pixels (thin coloured strokes are few pixels)
MIN_SHARE_NEUTRAL = 0.03  # of all non-white pixels (anti-aliasing fringes are neutral and must not count)
THUMB = 800  # thin outlines blur into fills below this
METHOD = (f"computed: paperfig kb measure (non-white pixels of a <= {THUMB} px thumbnail, white = min(R,G,B) >= {WHITE_MIN}, "
          f"minus the embedded images recorded by `refs crop` (images_px; their share is photo_share, null without a record); "
          f"chromatic (RGB spread > {CHROMA_SPREAD}) and neutral pixels clustered separately by PIL median-cut + k-means "
          f"(k=8 / 3); clusters within dE00 {MERGE_DE:g} merged; kept if >= {MIN_SHARE_CHROMA:g} of chromatic pixels / "
          f"neutral ones if >= {MIN_SHARE_NEUTRAL:g} of all non-white pixels; share = fraction of the non-photo non-white pixels)")


def _flat(im):
    return im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()


def _hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v))) for v in rgb))


def _clusters(pix: list, k: int, min_share: float, n_ink: int) -> list[dict]:
    """Median-cut + k-means clusters of ``pix``; merge near-identical ones; keep those holding at least
    ``min_share`` of ``pix``. Shares are reported against all ink pixels."""
    if not pix:
        return []
    strip = Image.new("RGB", (len(pix), 1))
    strip.putdata(pix)
    q = strip.quantize(colors=max(1, min(k, len(set(pix)))), method=Image.Quantize.MEDIANCUT, kmeans=8,
                       dither=Image.Dither.NONE)
    pal = q.getpalette()
    merged = []
    for n, i in sorted(q.getcolors(maxcolors=256), key=lambda c: -c[0]):
        rgb = list(pal[3 * i:3 * i + 3])
        for m in merged:
            if de2000(_hex(m[0]), _hex(rgb)) < MERGE_DE:
                tot = m[1] + n
                m[0] = [(m[0][j] * m[1] + rgb[j] * n) / tot for j in range(3)]
                m[1] = tot
                break
        else:
            merged.append([rgb, n])
    out = []
    for rgb, n in merged:
        if n / len(pix) < min_share:
            continue
        hx = _hex(rgb)
        _, a, bb = lab(hx)
        out.append({"hex": hx, "share": round(n / n_ink, 3), "neutral": math.hypot(a, bb) < NEUTRAL_CHROMA})
    return out


def _image_mask(png: Path, small):
    """255 inside the embedded images that `refs crop` recorded next to the crop (figN.json "images_px"),
    scaled to the thumbnail; None when no record exists (photo share unknown)."""
    from PIL import ImageDraw

    meta = png.with_suffix(".json")
    try:
        boxes = json.loads(meta.read_text(encoding="utf-8")).get("images_px")
    except (OSError, ValueError):
        return None
    if boxes is None:
        return None
    full = Image.open(png).size
    boxes = [(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)) for x0, y0, x1, y1 in boxes]
    boxes = [b for b in boxes if b[2] - b[0] >= 1 and b[3] - b[1] >= 1]  # zero-width/height records cover nothing
    if any((x1 - x0) * (y1 - y0) >= 0.5 * full[0] * full[1] for x0, y0, x1, y1 in boxes):
        return None  # the figure itself is a raster image: photos inside it cannot be told apart
    sx, sy = small.width / full[0], small.height / full[1]
    m = Image.new("L", small.size, 0)
    d = ImageDraw.Draw(m)
    for x0, y0, x1, y1 in boxes:
        d.rectangle([x0 * sx, y0 * sy, max(x0 * sx, x1 * sx - 1), max(y0 * sy, y1 * sy - 1)], fill=255)
    return m


def measure(png) -> dict:
    p = Path(png)
    try:
        im = Image.open(p).convert("RGB")
    except (OSError, ValueError) as e:
        raise PaperFigError(f"cannot read image {p}: {e}") from e
    w, h = im.size
    small = im.copy()
    small.thumbnail((THUMB, THUMB))
    r, g, b = small.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    total = small.width * small.height
    white = mn.histogram()[WHITE_MIN:]
    whitespace = sum(white) / total
    photo = _image_mask(p, small)
    if photo is None:
        ink = [px for px, m in zip(_flat(small), _flat(mn)) if m < WHITE_MIN]
        photo_share = None
    else:  # embedded photos and thumbnails are content, not the figure's palette
        ink_all = [(px, ph) for px, m, ph in zip(_flat(small), _flat(mn), _flat(photo)) if m < WHITE_MIN]
        ink = [px for px, ph in ink_all if not ph]
        photo_share = round((len(ink_all) - len(ink)) / len(ink_all), 3) if ink_all else 0.0
    # accents carry a figure's palette: cluster chromatic and neutral pixels separately so that big
    # gray areas (text, strokes, photos) cannot swallow small saturated colours
    chroma = [px for px in ink if max(px) - min(px) > CHROMA_SPREAD]
    neutral = [px for px in ink if max(px) - min(px) <= CHROMA_SPREAD]
    palette = _clusters(chroma, 8, MIN_SHARE_CHROMA, len(ink))
    palette += [e for e in _clusters(neutral, 3, 0.0, len(ink)) if e["share"] >= MIN_SHARE_NEUTRAL]
    palette.sort(key=lambda e: -e["share"])
    return {"source": METHOD, "palette": palette, "whitespace_ratio": round(whitespace, 3),
            "ink_ratio": round(1 - whitespace, 3), "photo_share": photo_share, "aspect": round(w / h, 3),
            "size_px": [w, h]}
