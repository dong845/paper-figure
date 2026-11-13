"""Absorb hand edits (round 7 C): the author moves boxes or retypes labels in draw.io; the moves become `pin` offsets
and the edits become labels in the blueprint, so a rebuild keeps them instead of overwriting them.

The engine's own drawing of the current blueprint is the reference: an element whose box in the edited file sits
elsewhere was moved (by the difference, minus what its container's move already carried); one whose plain text
differs was relabelled. Edge reroutes, resizes and deletions are reported, not absorbed — the blueprint has no
field that would keep them faithfully.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
from pathlib import Path

from .blueprint import plain_text
from .drawio import parse_cells
from .errors import PaperFigError

MOVE_EPS = 0.5  # drawing units: smaller differences are float noise, not a hand move
KEEP_TAGS = ("b", "i", "sub", "sup")


def _label_markup(value: str) -> str:
    """draw.io's HTML label → blueprint markup: line breaks as <br>, only <b> <i> <sub> <sup> kept."""
    s = re.sub(r"<\s*/?\s*(div|p)\b[^>]*>", "<br>", value or "", flags=re.I)
    s = re.sub(r"<br\s*/?>", "<br>", s, flags=re.I)
    s = re.sub(r"<(?!/?(?:%s|br)\b)[^>]+>" % "|".join(KEEP_TAGS), "", s, flags=re.I)
    s = html.unescape(s).replace(" ", " ")
    s = re.sub(r"(<br>\s*)+", "<br>", s).strip()
    s = re.sub(r"^(<br>)+|(<br>)+$", "", s)
    return s.replace("&", "&amp;") if "&" in s and "&amp;" not in s else s


def absorb(blueprint_path, edited_drawio, style: str | None = None, mix: dict | None = None) -> dict:
    from . import pipeline
    from .blueprint import load

    bp_path = Path(blueprint_path)
    try:
        data = json.loads(bp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"absorb: cannot read {bp_path}: {e}") from e
    try:
        edited = parse_cells(Path(edited_drawio).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"absorb: cannot read {edited_drawio}: {e}") from e
    with tempfile.TemporaryDirectory() as tmp:  # the engine's drawing of the blueprint as it stands
        res = pipeline.build(bp_path, style, mix, out_dir=tmp, formats=(), name="reference")
        ref = parse_cells(res.drawio.read_text(encoding="utf-8"))
    bp = load(bp_path)

    nodes: dict[str, dict] = {}

    def walk(d):
        nodes[d["id"]] = d
        for c in d.get("children", []):
            walk(c)
    walk(data["root"])

    moved, relabelled, missing, resized = [], [], [], []
    carried: dict[str, tuple[float, float]] = {}  # absolute move already applied to an element by its containers

    def visit(eid: str, inherited: tuple[float, float]):
        el = bp.index[eid]
        a, b = ref.get(f"pf-{eid}"), edited.get(f"pf-{eid}")
        own = inherited
        if eid != bp.root.id and a is not None and a.box is not None:
            if b is None or b.box is None:
                missing.append(eid)
            else:
                dx, dy = b.box.x - a.box.x, b.box.y - a.box.y
                ex, ey = dx - inherited[0], dy - inherited[1]
                if abs(ex) > MOVE_EPS or abs(ey) > MOVE_EPS:
                    old = nodes[eid].get("pin") or [0.0, 0.0]
                    nodes[eid]["pin"] = [round(old[0] + ex, 1), round(old[1] + ey, 1)]
                    moved.append(eid)
                own = (dx, dy)
                if abs(b.box.w - a.box.w) > 1 or abs(b.box.h - a.box.h) > 1:
                    resized.append(eid)
                if plain_text(b.value or "") != plain_text(a.value or ""):
                    key = "title" if el.is_group else "label"
                    nodes[eid][key] = _label_markup(b.value)
                    relabelled.append(eid)
        carried[eid] = own
        for c in getattr(el, "children", []) or []:
            visit(c.id, own)

    visit(bp.root.id, (0.0, 0.0))
    rerouted = sorted(k[3:] for k, c in edited.items() if k.startswith("pf-") and c.edge and k in ref
                      and c.points != ref[k].points)
    if moved or relabelled:
        shutil.copyfile(bp_path, bp_path.with_name(bp_path.name + ".bak"))
        bp_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        load(bp_path)  # what was written must still be a valid blueprint
    return {"moved": moved, "relabelled": relabelled, "not_absorbed": {"missing": missing, "resized": resized,
            "rerouted_edges": rerouted}, "backup": str(bp_path.with_name(bp_path.name + ".bak")) if moved or relabelled else None}
