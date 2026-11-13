"""Concept illustrations (round 7 ③) through the Codex subscription — no API key, no paid spend.

Only for scene / actor / environment elements a reader recognises faster as a picture (a household an agent acts
in, a robot arm, a user at a desk, a road scene). Never for data, an input sample, a plot or a result: those are
real files, data thumbnails or placeholders (SKILL ⑤). The blueprint marks such a node `visual: "image"`,
`asset: {"status": "generated", "spec": "<the scene>"}` and `"illustrative": true`.

The hosted image tool reads only the prompt, so everything that must hold travels inside it: the non-photographic
render mode, the figure's own palette, a plain white background (it sits on the figure's paper), no text.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .errors import PaperFigError

GENERATOR = Path(__file__).resolve().parent.parent / "scripts" / "generate_images_codex.py"
RENDER_MODE = (" RENDER MODE — this must NOT look photographic: draw it as a clean, flat vector-style scientific "
               "illustration (simple shapes, even outlines, soft flat shading, simplified detail; no photographic "
               "depth of field, no lens effects, no photo grain, no realism). A reader must see at a glance that it "
               "is an illustration.")
LAYOUT = (" One subject, centred, with a generous empty margin, isolated on a plain pure white background (no floor "
          "shadow, no frame, no border). No text, no letters, no numbers, no labels, no logos, no watermarks anywhere.")
MIN_PX = 384  # sanity floor after trimming; whether it prints sharply is lint asset-resolution's call


def _palette(style: str | None) -> str:
    from .styles import compose
    pal = compose(style or "soft-pastel", None)["palette"]
    tones = [t for k, t in pal["tones"].items() if isinstance(t, dict) and k not in ("gray", "grey")][:5]
    fills = ", ".join(t["fill"] for t in tones)
    strokes = ", ".join(t["stroke"] for t in tones)
    return (f" Colour palette (match it so the picture belongs to the figure): light fills {fills}; outlines and "
            f"accents {strokes}; dark grey #374151 for linework.")


def manifest(blueprint_path, style: str | None, out_dir) -> list[dict]:
    """One generator item per generated-image node that has no file yet."""
    from .blueprint import load
    bp = load(blueprint_path)
    items = []
    for n in bp.leaves():
        a = getattr(n, "asset", None)
        if a is None or a.status != "generated" or (a.path and Path(a.path).is_file()):
            continue
        prompt = f"{a.spec.strip().rstrip('.')}." + RENDER_MODE + _palette(style or bp.figure.style) + LAYOUT
        items.append({"id": n.id, "filename": f"{n.id}.png", "prompt": prompt, "orientation": "auto",
                      "path": str(Path(out_dir) / f"{n.id}.png")})
    return items


def trim(path, pad: float = 0.03) -> None:
    """Crop a generated picture to what it draws: the tool returns the subject on a wide transparent (or white)
    canvas, which would sit small inside its box."""
    from PIL import Image, ImageChops
    with Image.open(path) as im:
        im = im.convert("RGBA")
        bb = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if bb is None or (bb[2] - bb[0]) * (bb[3] - bb[1]) > 0.98 * im.size[0] * im.size[1]:  # opaque: trim white
            bb = ImageChops.difference(im.convert("RGB"), Image.new("RGB", im.size, "white")).point(
                lambda v: 255 if v > 12 else 0).getbbox()
        if bb is None:
            return
        px = round(pad * max(bb[2] - bb[0], bb[3] - bb[1]))
        box = (max(0, bb[0] - px), max(0, bb[1] - px), min(im.size[0], bb[2] + px), min(im.size[1], bb[3] + px))
        im.crop(box).save(path)


def check_grounds(blueprint_path, text=None, repo=None) -> dict:
    """{node id: problem} for generated images whose grounds quote the source does not contain. A quote is found
    in the method text, or — with a `file:line` ref — within a few lines of that place in the code."""
    from .artifacts import WINDOW, normalise, quote_in
    from .blueprint import load
    bp = load(blueprint_path)
    norm = normalise(Path(text).read_text(encoding="utf-8")) if text else None
    out = {}
    for n in bp.leaves():
        a = getattr(n, "asset", None)
        if a is None or a.status != "generated":
            continue
        g = a.grounds or {}
        q, ref = str(g.get("quote", "")), str(g.get("ref", ""))
        if norm is not None and quote_in(q, norm):
            continue
        fp, _, ln = ref.rpartition(":")
        if repo and fp and ln.isdigit():
            src = (Path(repo) / fp).resolve()
            if src.is_file() and Path(repo).resolve() in src.parents:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
                k = int(ln)
                if normalise(q) and normalise(q) in normalise("\n".join(lines[max(0, k - 1 - WINDOW): k + WINDOW])):
                    continue
        out[n.id] = (f"grounds quote not found in the {'method text' if norm is not None else ''}"
                     f"{' or ' if norm is not None and repo else ''}{'code at ' + ref if repo else ''}: {q[:80]!r} — "
                     "illustrate only a scene the source describes")
    return out


def run(blueprint_path, style: str | None, out_dir, dry_run: bool = False, text=None, repo=None) -> dict:
    """Check every scene against the source, then generate the missing illustrations, check them, and record their
    paths in the blueprint."""
    if text is None and repo is None:
        raise PaperFigError("illustrate needs --text (the method text) and/or --repo (the code) to check each "
                            "illustration's grounds quote — a scene is drawn only when the source describes it")
    bad = check_grounds(blueprint_path, text, repo)
    if bad:
        raise PaperFigError("refused — " + "; ".join(f"'{k}': {v}" for k, v in bad.items()))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items = manifest(blueprint_path, style, out)
    if not items:
        return {"generated": [], "failed": [], "note": "no generated-image node without a file"}
    man = out / "illustrations.manifest.json"
    man.write_text(json.dumps([{k: v for k, v in i.items() if k != "id"} for i in items], indent=1), encoding="utf-8")
    if dry_run:
        return {"generated": [], "failed": [], "manifest": str(man), "items": items}
    proc = subprocess.run([sys.executable, str(GENERATOR), str(man), "--out-dir", str(out), "--orientation", "auto",
                           "--allow-generic", "--concurrency", "2"], capture_output=True, text=True)
    from PIL import Image
    done, failed = [], []
    for i in items:
        p = Path(i["path"])
        try:
            trim(p)
            with Image.open(p) as im:
                w, h = im.size
            if min(w, h) < MIN_PX:
                failed.append((i["id"], f"only {w}x{h} px"))
                continue
            done.append(i["id"])
        except (OSError, ValueError):
            failed.append((i["id"], "no image written"))
    if done:
        bp_path = Path(blueprint_path)
        data = json.loads(bp_path.read_text(encoding="utf-8"))

        def walk(d):
            if d.get("id") in done:
                d["asset"]["path"] = str(out / f"{d['id']}.png")
            for c in d.get("children", []):
                walk(c)
        walk(data["root"])
        bp_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if failed and not done:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise PaperFigError(f"no illustration was generated: {failed} — generator said: {tail}")
    return {"generated": done, "failed": failed, "manifest": str(man), "log": (proc.stdout or "")[-1500:]}
