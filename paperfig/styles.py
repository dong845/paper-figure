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
    if not p.is_file() and str(rid).endswith(".json") and Path(rid).is_file():  # a run's own recipe (style is open)
        p = Path(rid)
        rid = p.stem
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


AREA_LIGHTEN = 0.55  # group fill = tone fill mixed 55 % toward white


def colors_for(recipe: Recipe, el, parent=None) -> tuple[str, str, str]:
    """(fill, stroke, font) for a leaf node or group, after role/tone/nesting rules."""
    pal = recipe["palette"]
    if el.is_group:
        # an area is a lighter tint of the tone its elements carry, so the elements inside still stand out
        if getattr(el, "detail_of", None) and not el.tone:
            t = _tone(recipe, "yellow")  # detail panels are tinted so the callout halo can match them
            return mix(t["fill"], "#ffffff", AREA_LIGHTEN), t["stroke"], t["font"]
        if el.role == "proposed" or el.tone:
            t = _tone(recipe, el.tone or pal["roles"]["proposed"]["tone"])
            return mix(t["fill"], "#ffffff", AREA_LIGHTEN), t["stroke"], t["font"]
        c = pal["container"]["dashed" if el.frame == "dashed" else "box"]
        return c["fill"], c["stroke"], c["font"]
    role = pal["roles"].get(el.role, pal["roles"]["reused"])
    t = _tone(recipe, el.tone or role["tone"])
    fill, stroke, font = t["fill"], t["stroke"], t["font"]
    if el.role == "proposed" and parent is not None and getattr(parent, "role", None) == "proposed" and not el.tone:
        fill = pal["nested_in_proposed"]["fill"]
    mute = role.get("mute", 0.0)
    if mute:
        stroke = mix(stroke, "#9ca3af", mute)  # reused components recede: stroke drifts to neutral gray
    return fill, stroke, font


def _is_bold(recipe: Recipe, el) -> bool:
    """Whole-label bold. A label with its own <b> markup controls weight itself (e.g. bold abbreviation,
    regular expansion), so the cell is not bolded."""
    text = el.title if el.is_group else el.label
    if text and "<b>" in text.lower():
        return False
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


def mix(a: str, b: str, t: float) -> str:
    ha, hb = a.lstrip("#"), b.lstrip("#")
    if len(ha) != 6 or len(hb) != 6:
        return a
    ca = [int(ha[i : i + 2], 16) for i in (0, 2, 4)]
    cb = [int(hb[i : i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def _effects(recipe: Recipe, fill: str, stroke: str | None = None) -> dict:
    fx = recipe["effects"]
    out = {"shadow": "1" if fx["shadow"] else "0"}
    if fx["gradient"] and fill not in ("none", "#ffffff"):
        # deepen towards the tone's own stroke colour (keeps hue); scaling RGB to black turns pastels muddy
        out["gradientColor"] = mix(fill, stroke, fx["gradient_darken"]) if stroke and stroke.startswith("#") else darken(fill, fx["gradient_darken"])
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
        st.update({"strokeColor": "none", "fillColor": "none", "fontColor": font if getattr(node, "tone", None) else ty["color"], "fontStyle": "2" if node.role == "annotation" else st["fontStyle"]})
        st["fontSize"] = _num(ty["small_size"])
        return st
    if v in ("box", "tokens"):
        st.update({"rounded": "1" if sh["radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["radius"])})
    elif v == "trapezoid":
        from .shapes import TRAPEZOID_SIZE
        st.update({"shape": "trapezoid", "perimeter": "trapezoidPerimeter", "size": _num(TRAPEZOID_SIZE),
                   "direction": "south" if node.taper == "in" else "north", "rounded": "1" if sh["radius"] else "0",
                   "arcSize": "8"})
    elif v == "slab":
        from .shapes import slab_rotated
        st.update({"rounded": "1" if sh["radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(min(6.0, 2 * sh["radius"])),
                   "fontSize": _num(ty["small_size"]), "fontStyle": "0", "spacing": "1"})
        if slab_rotated(node):
            st["horizontal"] = "0"
    elif v == "stack":
        st.update({"verticalLabelPosition": "bottom", "verticalAlign": "top", "whiteSpace": "nowrap",
                   "fontSize": _num(ty["small_size"]), "fontStyle": "0", "fontColor": font})
    elif v == "op":
        st.update({"shape": "ellipse", "perimeter": "ellipsePerimeter", "aspect": "fixed"})
        if getattr(node, "op", None):  # typed operator: just its glyph, ring sized like the others
            from .shapes import OPS, op_glyph_style, op_ring
            st.update(op_glyph_style(OPS[node.op][0], op_ring(ty["size"]), "#374151", recipe.data.get("ink_scale", 1.0)))
            return st
    elif v == "tensor":
        t = recipe["tensor"]
        st.update({"shape": "cube", "size": _num(t["depth"]), "flipH": "1", "darkOpacity": _num(t.get("dark_opacity", 0)),
                   "darkOpacity2": _num(t.get("dark_opacity2", 0)), "verticalLabelPosition": "bottom", "verticalAlign": "top",
                   "whiteSpace": "nowrap", "labelBackgroundColor": "none", "fontSize": _num(ty["small_size"]), "fontColor": font,
                   "fontStyle": "0"})
    elif v in ("image", "icon", "glyph"):
        st.update({"shape": "image", "verticalLabelPosition": "bottom", "verticalAlign": "top", "imageAspect": "0", "whiteSpace": "nowrap",
                   "fontSize": _num(ty["small_size"]), "fontColor": ty["color"], "fontStyle": "0"})
        if v == "image":
            st.update({"imageBorder": recipe["palette"]["image_border"], "strokeWidth": "1"})
        if v == "glyph" and node.glyph in ("heatmap", "mask", "kspace"):  # schematic data: a dashed frame says "not a result"
            st.update({"imageBorder": recipe["palette"]["image_border"], "strokeWidth": "1", "dashed": "1", "dashPattern": "3 2"})
        return st
    elif v == "placeholder":
        st.update({"rounded": "0", "dashed": "1", "dashPattern": "4 3", "fillColor": "#eef0f3", "strokeColor": "#a3aab5",
                   "fontColor": "#4b5563", "fontSize": _num(ty["small_size"]), "fontStyle": "2", "strokeWidth": "1", "pfasset": "pending"})
        return st
    sw = sh["stroke_width"] * recipe["palette"]["roles"].get(node.role, {}).get("stroke_scale", 1.0)
    st.update({"fillColor": fill, "strokeColor": stroke, "strokeWidth": _num(sw)})
    if parent is not None and getattr(parent, "detail_of", None):
        st["shadow"] = "0"  # dense detail panels stay flat: depth there is texture, not meaning
    else:
        st.update(_effects(recipe, fill, stroke))
    return st


def group_style(recipe: Recipe, group) -> dict:
    fill, stroke, font = colors_for(recipe, group)
    sh, ty = recipe["shape"], recipe["typography"]
    st = {"html": "1", "whiteSpace": "wrap", "container": "1", "collapsible": "0", "recursiveResize": "0",
          "verticalAlign": "top", "align": getattr(group, "title_align", "center"), "spacingTop": "4"}
    if st["align"] == "left":
        st["spacingLeft"] = _num(recipe["spacing"]["group_pad"])
    st.update(_font_keys(recipe, font, ty["title_size"], _is_bold(recipe, group)))
    if group.frame == "none":
        st.update({"fillColor": "none", "strokeColor": "none"})
        return st
    st.update({"rounded": "1" if sh["group_radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["group_radius"]),
               "fillColor": fill, "strokeColor": stroke,
               "strokeWidth": _num(sh["group_stroke_width"] if group.role == "proposed" else sh["stroke_width"])})
    if group.frame == "dashed":
        st.update({"dashed": "1", "dashPattern": "6 4"})
    if group.role == "proposed" or group.tone or getattr(group, "detail_of", None):
        st.update(_effects(recipe, fill, stroke))
    else:  # plain panels stay flat: nested shadows/gradients add noise, not meaning
        st.update({"shadow": "0"})
    return st


def edge_style_for_kind(recipe: Recipe, kind: str) -> dict:
    e = recipe["edges"][kind]
    arrow = _num(6 * recipe.data.get("ink_scale", 1.0) ** 0.5)  # heads grow slower than strokes
    st = {"html": "1", "edgeStyle": "none", "rounded": "1" if recipe["shape"]["edge_rounded"] else "0",
          "strokeColor": e["color"], "strokeWidth": _num(e["width"]),
          "endArrow": e["end"], "endFill": "0" if e["end"] in ("open",) else "1", "endSize": arrow,
          "startArrow": e["start"], "startFill": "1", "startSize": arrow,
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


def title_text_box(recipe, group, placed_group):
    """Where draw.io draws a group's title text (inside its title band)."""
    from .geometry import Box
    from .measure import measure

    tb = placed_group.title_box
    if tb is None or not group.title:
        return None
    tw, th = measure(group.title, recipe["typography"]["title_size"], _is_bold(recipe, group), recipe["typography"]["family"])
    x = tb.x + recipe["spacing"]["group_pad"] if getattr(group, "title_align", "center") == "left" else tb.cx - tw / 2
    return Box(x, tb.y + 4, tw, th)


def _set_L(hex_color: str, L_target: float) -> str:
    """Move a colour toward black or white until its L* reaches L_target (hue roughly kept)."""
    from . import color
    L0 = color.lab(hex_color)[0]
    other = "#ffffff" if L_target > L0 else "#000000"
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if (color.lab(mix(hex_color, other, m))[0] < L_target) == (other == "#ffffff"):
            lo = m
        else:
            hi = m
    return mix(hex_color, other, (lo + hi) / 2)


def derive_style(base: str, cards_dir, out, card_ids=None) -> Path:
    """A run-local recipe whose tones come from the references' measured palettes (the colours they actually
    use), mapped by hue onto the base recipe's tone names; the most saturated, most used colour becomes the
    accent for the proposed parts. Fills are tinted (L* 87, accent 82), strokes L* 55, fonts dark enough for
    4.5:1 on their fill. Everything else comes from `base`. Style stays open: this is one more candidate."""
    import math
    from . import color

    r = load_recipe(base)
    data = copy.deepcopy(r.data)
    cols, used = [], []
    for f in sorted(Path(cards_dir).glob("*.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if card_ids and c.get("id") not in card_ids:
            continue
        pal = (c.get("measured") or {}).get("palette") or []
        got = False
        for e in pal:
            if not isinstance(e, dict) or e.get("neutral") or (e.get("share") or 0) < 0.02:
                continue
            L, a, b = color.lab(e["hex"])
            ch = math.hypot(a, b)
            if ch < 15:
                continue
            cols.append((math.degrees(math.atan2(b, a)) % 360, ch, float(e["share"]), e["hex"]))
            got = True
        if got:
            used.append(c.get("id") or f.stem)
    if not cols:
        raise StyleError(f"no chromatic colours measured in the cards under {cards_dir} — nothing to derive from")
    clusters: list[dict] = []  # greedy hue clusters, 30 degrees wide
    for h, ch, sh, hx in sorted(cols, key=lambda x: -x[2] * x[1]):
        for cl in clusters:
            if min(abs(h - cl["h"]), 360 - abs(h - cl["h"])) <= 30:
                cl["w"] += sh * ch
                cl["members"].append(hx)
                break
        else:
            clusters.append({"h": h, "w": sh * ch, "rep": hx, "members": [hx]})
    clusters.sort(key=lambda c: -c["w"])
    tones = data["palette"]["tones"]
    names = [k for k, v in tones.items() if isinstance(v, dict) and k not in ("gray", "grey")]
    hue_of = {k: math.degrees(math.atan2(color.lab(tones[k]["stroke"])[2], color.lab(tones[k]["stroke"])[1])) % 360
              for k in names}
    reused_tone = data["palette"]["roles"].get("reused", {}).get("tone")
    taken, accent = {}, None
    for cl in clusters[:6]:
        free = [k for k in names if k not in taken]
        if not free:
            break
        k = min(free, key=lambda n: min(abs(hue_of[n] - cl["h"]), 360 - abs(hue_of[n] - cl["h"])))
        taken[k] = cl["rep"]
        if accent is None and k != reused_tone:  # the contribution never shares the reused parts' tone
            accent = k
    if accent is None:  # every derived hue landed on the reused tone: keep the base accent
        accent = data["palette"]["roles"]["proposed"]["tone"]
    for k, hx in taken.items():
        stroke = _set_L(hx, 55)
        fill = _set_L(hx, 82 if k == accent else 87)
        font = _set_L(hx, 30)
        while color.contrast(font, fill) < 4.5 and color.lab(font)[0] > 5:
            font = _set_L(font, color.lab(font)[0] - 4)
        tones[k] = {"fill": fill, "stroke": stroke, "font": font}
    data["palette"]["roles"]["proposed"]["tone"] = accent
    acc_stroke = tones[accent]["stroke"].lower()
    for kind, e in data["edges"].items():
        if kind != "data" and isinstance(e, dict) and str(e.get("color", "")).lower() == acc_stroke:
            e["color"] = "#6b7280"  # training/other paths never borrow the accent (one colour, one meaning)
    data["derived_from"] = {"base": base, "cards": used}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
