"""Style recipes (spec §4 选质感): composable sections → drawio style dicts.

Recipe sections: typography, spacing, palette, shape, effects, tensor, edges,
image. `compose(base, mix)` swaps whole sections from other recipes, so a
user can ask for "B's palette with C's depth effects".
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import StyleError

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
SECTIONS = ("typography", "spacing", "palette", "shape", "effects", "tensor", "edges", "image")
EDGE_KINDS = ("data", "skip", "loss", "train_only", "infer_only", "grad", "control")


@dataclass
class Recipe:
    id: str
    data: dict

    def __getitem__(self, k):
        return self.data[k]


def available() -> list[str]:
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def load_recipe(rid: str) -> Recipe:
    p = STYLES_DIR / f"{rid}.json"
    if not p.is_file():
        raise StyleError(f"unknown style '{rid}' (available: {', '.join(available())})")
    data = json.loads(p.read_text())
    missing = [s for s in SECTIONS if s not in data]
    if missing:
        raise StyleError(f"style '{rid}' is missing section(s): {', '.join(missing)}")
    for k in EDGE_KINDS:
        if k not in data["edges"]:
            raise StyleError(f"style '{rid}' has no edge style for kind '{k}'")
    return Recipe(rid, data)


def compose(base_id: str, mix: dict[str, str] | None = None) -> Recipe:
    r = load_recipe(base_id)
    data = copy.deepcopy(r.data)
    names = [base_id]
    for section, other in (mix or {}).items():
        if section not in SECTIONS:
            raise StyleError(f"unknown style section '{section}' (sections: {', '.join(SECTIONS)})")
        data[section] = copy.deepcopy(load_recipe(other).data[section])
        names.append(f"{section}={other}")
    return Recipe("+".join(names), data)


def darken(hex_color: str, amount: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    f = max(0.0, 1.0 - amount)
    return "#%02x%02x%02x" % (round(r * f), round(g * f), round(b * f))


def _tone(recipe: Recipe, name: str) -> dict:
    tones = recipe["palette"]["tones"]
    if name not in tones:
        raise StyleError(f"unknown tone '{name}' (tones: {', '.join(tones)})")
    return tones[name]


def colors_for(recipe: Recipe, el, parent=None) -> tuple[str, str, str]:
    """(fill, stroke, font) for a leaf node or group, after role/tone/nesting rules."""
    pal = recipe["palette"]
    if el.is_group:
        if el.role == "proposed" or el.tone:
            t = _tone(recipe, el.tone or pal["roles"]["proposed"]["tone"])
            return t["fill"], t["stroke"], t["font"]
        c = pal["container"]["dashed" if el.frame == "dashed" else "box"]
        return c["fill"], c["stroke"], c["font"]
    role = pal["roles"].get(el.role, pal["roles"]["reused"])
    t = _tone(recipe, el.tone or role["tone"])
    fill, stroke, font = t["fill"], t["stroke"], t["font"]
    if el.role == "proposed" and parent is not None and getattr(parent, "role", None) == "proposed" and not el.tone:
        fill = pal["nested_in_proposed"]["fill"]
    return fill, stroke, font


def _is_bold(recipe: Recipe, el) -> bool:
    pal = recipe["palette"]
    if el.is_group:
        if el.role == "proposed":
            return True
        return pal["container"]["dashed" if el.frame == "dashed" else "box"]["bold"]
    return pal["roles"].get(el.role, pal["roles"]["reused"])["bold"]


def _font_keys(recipe: Recipe, color: str, size: float, bold: bool) -> dict:
    ty = recipe["typography"]
    return {"fontFamily": ty["family"], "fontSize": _num(size), "fontColor": color, "fontStyle": "1" if bold else "0"}


def _num(x: float) -> str:
    return ("%.2f" % x).rstrip("0").rstrip(".")


def _effects(recipe: Recipe, fill: str) -> dict:
    fx = recipe["effects"]
    out = {"shadow": "1" if fx["shadow"] else "0"}
    if fx["gradient"] and fill not in ("none", "#ffffff"):
        out["gradientColor"] = darken(fill, fx["gradient_darken"])
        out["gradientDirection"] = "south"
    return out


def node_style(recipe: Recipe, node, parent=None) -> dict:
    fill, stroke, font = colors_for(recipe, node, parent)
    sh, ty = recipe["shape"], recipe["typography"]
    bold = _is_bold(recipe, node)
    st = {"html": "1", "whiteSpace": "wrap"}
    st.update(_font_keys(recipe, font, ty["size"], bold))
    v = node.visual
    if v == "text":
        st.update({"strokeColor": "none", "fillColor": "none", "fontColor": ty["color"], "fontStyle": "2" if node.role == "annotation" else st["fontStyle"]})
        st["fontSize"] = _num(ty["small_size"])
        return st
    if v in ("box", "tokens"):
        st.update({"rounded": "1" if sh["radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["radius"])})
    elif v == "op":
        st.update({"shape": "ellipse", "perimeter": "ellipsePerimeter", "aspect": "fixed"})
    elif v == "tensor":
        t = recipe["tensor"]
        st.update({"shape": "cube", "size": _num(t["depth"]), "flipH": "1", "darkOpacity": _num(t.get("dark_opacity", 0)),
                   "darkOpacity2": _num(t.get("dark_opacity2", 0)), "verticalLabelPosition": "bottom", "verticalAlign": "top",
                   "whiteSpace": "nowrap", "labelBackgroundColor": "none", "fontSize": _num(ty["small_size"]), "fontColor": font,
                   "fontStyle": "0"})
    elif v in ("image", "icon"):
        st.update({"shape": "image", "verticalLabelPosition": "bottom", "verticalAlign": "top", "imageAspect": "0", "whiteSpace": "nowrap",
                   "fontSize": _num(ty["small_size"]), "fontColor": ty["color"], "fontStyle": "0"})
        if v == "image":
            st.update({"imageBorder": recipe["palette"]["image_border"], "strokeWidth": "1"})
        return st
    elif v == "placeholder":
        st.update({"rounded": "0", "dashed": "1", "dashPattern": "6 4", "fillColor": "#fff7f7", "strokeColor": "#c2410c",
                   "fontColor": "#9a3412", "fontSize": _num(ty["small_size"]), "fontStyle": "2", "strokeWidth": "1.2"})
        return st
    st.update({"fillColor": fill, "strokeColor": stroke, "strokeWidth": _num(sh["stroke_width"])})
    st.update(_effects(recipe, fill))
    return st


def group_style(recipe: Recipe, group) -> dict:
    fill, stroke, font = colors_for(recipe, group)
    sh, ty = recipe["shape"], recipe["typography"]
    st = {"html": "1", "whiteSpace": "wrap", "container": "1", "collapsible": "0", "recursiveResize": "0",
          "verticalAlign": "top", "align": "center", "spacingTop": "4"}
    st.update(_font_keys(recipe, font, ty["title_size"], _is_bold(recipe, group)))
    if group.frame == "none":
        st.update({"fillColor": "none", "strokeColor": "none"})
        return st
    st.update({"rounded": "1" if sh["group_radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["group_radius"]),
               "fillColor": fill, "strokeColor": stroke,
               "strokeWidth": _num(sh["group_stroke_width"] if group.role == "proposed" else sh["stroke_width"])})
    if group.frame == "dashed":
        st.update({"dashed": "1", "dashPattern": "6 4"})
    st.update(_effects(recipe, fill))
    return st


def edge_style_for_kind(recipe: Recipe, kind: str) -> dict:
    e = recipe["edges"][kind]
    st = {"html": "1", "edgeStyle": "none", "rounded": "1" if recipe["shape"]["edge_rounded"] else "0",
          "strokeColor": e["color"], "strokeWidth": _num(e["width"]),
          "endArrow": e["end"], "endFill": "0" if e["end"] in ("open",) else "1", "endSize": "6",
          "startArrow": e["start"], "startFill": "1", "startSize": "6",
          "fontFamily": recipe["typography"]["family"], "fontSize": _num(recipe["typography"]["small_size"]),
          "fontColor": recipe["typography"]["color"], "labelBackgroundColor": "#ffffff"}
    if e["dash"]:
        st.update({"dashed": "1", "dashPattern": e["dash"]})
    return st


def edge_style(recipe: Recipe, edge) -> dict:
    return edge_style_for_kind(recipe, edge.kind)


def to_style_string(st: dict, prefix: str | None = None) -> str:
    parts = [prefix] if prefix else []
    for k, v in st.items():
        parts.append(k if v is None else f"{k}={v}")
    return ";".join(parts) + ";"
