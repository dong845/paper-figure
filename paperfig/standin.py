"""Stand-in pictures for data images the user has not supplied yet (user, 2026-11-24: "no image? draw a virtual one as
a placeholder"). A grey box with a caption reads as an unfinished figure; a plausible picture of the right kind
(a CT slice, a heat map, a spectrogram ...) shows the design as it will look. They stay placeholders: the frame is
dashed, the caption stays on them, and lint asset-pending still asks for the real file. Pillow only, deterministic
per element, no network."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CACHE = Path.home() / ".cache" / "paper-figure" / "standins"
KINDS = {  # the first kind whose words appear in the element's spec / label / id
    "mask": ("mask", "segmentation", "label map", "labels", "annotation map"),
    "volume": ("volume", "stack", "slices", "3d scan", "ct scan", "mri scan"),
    "slice": ("ct", "mri", "slice", "x-ray", "xray", "radiograph", "lung", "brain", "mammo", "scan", "medical"),
    "heatmap": ("heatmap", "heat map", "attention", "saliency", "probability map", "map", "density"),
    "spectrogram": ("spectrogram", "audio", "waveform", "speech", "sound", "mel"),
    "photo": ("photo", "image", "rgb", "frame", "video", "scene", "camera", "picture"),
}


ZOOM = ("zoom", "crop", "patch", "close up", "detail", "roi")
VIEWS = ("triplanar", "tri planar", "multi view", "multiview", "views", "orthogonal")


def _words(node) -> str:
    asset = getattr(node, "asset", None)
    words = " ".join(str(x or "") for x in (getattr(asset, "spec", ""), node.label, node.id)).lower()
    return f' {words.replace("_", " ").replace("-", " ")} '


def base_kind(node) -> str | None:
    w = _words(node)
    return next((kind for kind, keys in KINDS.items() if any(f" {k} " in w for k in keys)), None)


def kind_of(node, domain: str | None = None) -> str:
    """The picture to draw: the element's own kind, else the figure's (a 'zoom' next to CT slices is a CT zoom, not
    a landscape); a zoom / several views of that kind are drawn as such."""
    w = _words(node)
    kind = base_kind(node) or domain or "photo"
    if any(f" {k} " in w for k in VIEWS):
        return f"views:{kind}"
    if kind == "slice" and any(f" {k} " in w for k in ZOOM):
        return "zoom"
    return kind


def domain_of(nodes) -> str | None:
    """The most common specific kind among a figure's pending images (volumes count as slices)."""
    ks = [k for k in (base_kind(n) for n in nodes) if k and k != "photo"]
    ks = ["slice" if k == "volume" else k for k in ks]
    return max(ks, key=ks.count) if ks else None  # a tie goes to the first named: deterministic


def _ramp(stops: list[tuple[int, int, int]]) -> list[int]:
    """A 256-entry palette through the given colours (for an 'L' image put through it)."""
    pal = []
    n = len(stops) - 1
    for i in range(256):
        t = i / 255 * n
        k = min(int(t), n - 1)
        f = t - k
        a, b = stops[k], stops[k + 1]
        pal += [round(a[j] + (b[j] - a[j]) * f) for j in range(3)]
    return pal


def _field(w, h, rnd, blobs=6, blur=0.12) -> Image.Image:
    """A smooth random field in 0..255: soft blobs, blurred."""
    im = Image.new("L", (w, h), 20)
    d = ImageDraw.Draw(im)
    for _ in range(blobs):
        r = rnd.uniform(0.12, 0.3) * min(w, h)
        x, y = rnd.uniform(0.15, 0.85) * w, rnd.uniform(0.15, 0.85) * h
        d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.randint(120, 255))
    return im.filter(ImageFilter.GaussianBlur(blur * min(w, h)))


def _slice(w, h, rnd) -> Image.Image:
    """An axial chest-CT-like slice: body, two lungs with vessels, spine, scanner noise."""
    s = min(w, h)
    im = Image.new("L", (w, h), 8)
    d = ImageDraw.Draw(im)
    cx, cy = w / 2, h / 2
    d.ellipse((cx - 0.46 * w, cy - 0.36 * h, cx + 0.46 * w, cy + 0.38 * h), fill=118)  # soft tissue
    for sx in (-1, 1):  # lungs
        lx = cx + sx * 0.2 * w
        d.ellipse((lx - 0.15 * w, cy - 0.26 * h, lx + 0.15 * w, cy + 0.22 * h), fill=26)
        for _ in range(14):  # vessels
            vx, vy = lx + rnd.uniform(-0.11, 0.11) * w, cy + rnd.uniform(-0.2, 0.17) * h
            r = rnd.uniform(0.004, 0.012) * s
            d.ellipse((vx - r, vy - r, vx + r, vy + r), fill=rnd.randint(90, 150))
    d.ellipse((cx - 0.07 * s, cy + 0.2 * h, cx + 0.07 * s, cy + 0.2 * h + 0.13 * s), fill=235)  # vertebra
    d.ellipse((cx - 0.06 * s, cy - 0.06 * h, cx + 0.05 * s, cy + 0.08 * h), fill=150)  # heart / mediastinum
    im = im.filter(ImageFilter.GaussianBlur(0.006 * s))
    noise = Image.effect_noise((w, h), 14).filter(ImageFilter.GaussianBlur(0.6))
    return Image.blend(im, noise, 0.12).convert("RGB")


def _volume(w, h, rnd) -> Image.Image:
    """A stack of slices seen at an angle: three offset copies, back to front."""
    out = Image.new("RGB", (w, h), "white")
    n, off = 3, 0.08
    sw, sh = round(w * (1 - off * (n - 1))), round(h * (1 - off * (n - 1)))
    for k in range(n):
        sl = _slice(sw, sh, random.Random(rnd.random()))
        x, y = round((n - 1 - k) * off * w), round(k * off * h)
        out.paste(sl, (x, y))
        ImageDraw.Draw(out).rectangle((x, y, x + sw - 1, y + sh - 1), outline=(255, 255, 255), width=max(1, w // 120))
    return out


def _mask(w, h, rnd) -> Image.Image:
    """A label map: flat regions of a few classes on black, as a segmentation output looks."""
    im = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for col in [(230, 75, 60), (70, 160, 230), (250, 200, 60), (90, 190, 120)][:rnd.randint(2, 4)]:
        r = rnd.uniform(0.1, 0.22) * min(w, h)
        x, y = rnd.uniform(0.25, 0.75) * w, rnd.uniform(0.25, 0.75) * h
        d.ellipse((x - r, y - 0.8 * r, x + r, y + 0.8 * r), fill=col)
    return im


def _heatmap(w, h, rnd) -> Image.Image:
    im = _field(w, h, rnd)
    im = im.convert("P")
    im.putpalette(_ramp([(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]))  # viridis
    return im.convert("RGB")


def _spectrogram(w, h, rnd) -> Image.Image:
    im = Image.new("L", (w, h), 10)
    d = ImageDraw.Draw(im)
    f0 = rnd.uniform(0.06, 0.1) * h
    for k in range(1, 9):  # harmonics, louder low
        y = h - k * f0 - rnd.uniform(-2, 2)
        d.line((0, y, w, y + rnd.uniform(-0.05, 0.05) * h), fill=max(40, 230 - 22 * k), width=max(1, h // 60))
    for _ in range(int(w / 12)):  # onsets
        x = rnd.uniform(0, w)
        d.line((x, h, x, h * rnd.uniform(0.3, 0.7)), fill=rnd.randint(40, 110), width=1)
    im = Image.blend(im.filter(ImageFilter.GaussianBlur(0.008 * min(w, h) + 0.5)), Image.effect_noise((w, h), 30), 0.15)
    im = im.convert("P")
    im.putpalette(_ramp([(0, 0, 4), (81, 18, 124), (183, 55, 121), (252, 137, 97), (252, 253, 191)]))  # magma
    return im.convert("RGB")


def _photo(w, h, rnd) -> Image.Image:
    """An unfocused landscape-like picture: sky gradient, ground, soft shapes — clearly a stand-in, not a sample."""
    top, bottom = (rnd.randint(150, 190), rnd.randint(185, 215), 235), (rnd.randint(90, 130), 140, 95)
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    horizon = rnd.uniform(0.5, 0.65) * h
    for y in range(h):
        c = top if y < horizon else bottom
        f = y / horizon if y < horizon else (y - horizon) / max(1, h - horizon)
        d.line((0, y, w, y), fill=tuple(round(c[j] * (1 - 0.25 * f)) for j in range(3)))
    for _ in range(4):
        r = rnd.uniform(0.08, 0.2) * min(w, h)
        x, y = rnd.uniform(0.1, 0.9) * w, horizon + rnd.uniform(-0.05, 0.2) * h
        d.ellipse((x - r, y - r, x + r, y + r), fill=(rnd.randint(60, 120), rnd.randint(90, 140), rnd.randint(60, 100)))
    return im.filter(ImageFilter.GaussianBlur(0.01 * min(w, h)))


def _zoom(w, h, rnd) -> Image.Image:
    """A close-up of a slice: one lung region at 3x, so vessels read as structure."""
    big = _slice(3 * w, 3 * h, rnd)
    x0, y0 = round(rnd.uniform(0.25, 0.4) * 3 * w), round(rnd.uniform(0.3, 0.4) * 3 * h)
    return big.crop((x0, y0, x0 + w, y0 + h))


def _views(w, h, rnd, kind) -> Image.Image:
    """Several views of one sample side by side (axial / coronal / sagittal, or three frames)."""
    out = Image.new("RGB", (w, h), "white")
    gap = max(1, w // 40)
    vw = (w - 2 * gap) // 3
    for k in range(3):
        out.paste(DRAW[kind](vw, h, random.Random(rnd.random())), (k * (vw + gap), 0))
    return out


DRAW = {"slice": _slice, "volume": _volume, "heatmap": _heatmap, "spectrogram": _spectrogram, "photo": _photo,
        "zoom": _zoom, "mask": _mask}


def standin_png(node, w: float, h: float, scale: float = 3.0, domain: str | None = None) -> str:
    """A stand-in picture for a pending data image, cached by element and size; returns its path."""
    kind = kind_of(node, domain)
    W, H = max(8, round(w * scale)), max(8, round(h * scale))
    key = hashlib.sha1(f"{node.id}|{kind}|{W}x{H}".encode()).hexdigest()[:16]
    path = CACHE / f"{kind.replace(':', '-')}-{key}.png"
    if not path.is_file():
        CACHE.mkdir(parents=True, exist_ok=True)
        rnd = random.Random(key)
        im = _views(W, H, rnd, kind.split(":", 1)[1]) if kind.startswith("views:") else DRAW[kind](W, H, rnd)
        im.save(path, optimize=True)
    return str(path)
