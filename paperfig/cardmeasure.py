"""Measurements for figure cards, computed from a figure crop (never estimated by eye)."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops

from .color import de2000, lab
from .errors import PaperFigError

WHITE_MIN = 245  # a pixel is background when its darkest channel is at least this
MERGE_DE = 8.0  # clusters closer than this (CIEDE2000) are one colour
CHROMA_SPREAD = 20  # max(R,G,B) - min(R,G,B) above this: a chromatic pixel
MIN_SHARE_CHROMA = 0.03  # of the chromatic pixels
MIN_SHARE_NEUTRAL = 0.05  # of the neutral pixels
THUMB = 800  # thin outlines blur into fills below this
METHOD = (f"computed: paperfig kb measure (non-white pixels of a <= {THUMB} px thumbnail, white = min(R,G,B) >= {WHITE_MIN}; "
          f"chromatic (RGB spread > {CHROMA_SPREAD}) and neutral pixels clustered separately by PIL median-cut + k-means "
          f"(k=8 / 3); clusters within dE00 {MERGE_DE:g} merged; kept if >= {MIN_SHARE_CHROMA:g} of chromatic / "
          f">= {MIN_SHARE_NEUTRAL:g} of neutral pixels; share = fraction of all non-white pixels)")


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
        out.append({"hex": hx, "share": round(n / n_ink, 3), "neutral": math.hypot(a, bb) < 8})
    return out


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
    ink = [px for px, m in zip(_flat(small), _flat(mn)) if m < WHITE_MIN]
    # accents carry a figure's palette: cluster chromatic and neutral pixels separately so that big
    # gray areas (text, strokes, photos) cannot swallow small saturated colours
    chroma = [px for px in ink if max(px) - min(px) > CHROMA_SPREAD]
    neutral = [px for px in ink if max(px) - min(px) <= CHROMA_SPREAD]
    palette = _clusters(chroma, 8, MIN_SHARE_CHROMA, len(ink)) + _clusters(neutral, 3, MIN_SHARE_NEUTRAL, len(ink))
    palette.sort(key=lambda e: -e["share"])
    return {"source": METHOD, "palette": palette, "whitespace_ratio": round(whitespace, 3),
            "ink_ratio": round(1 - whitespace, 3), "aspect": round(w / h, 3), "size_px": [w, h]}
