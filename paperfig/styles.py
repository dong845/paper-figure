"""Style recipes (spec §4 选质感): composable sections → drawio style dicts.

Recipe sections: typography, spacing, palette, shape, effects, tensor, edges,
image. `compose(base, mix)` swaps whole sections from other recipes, so a
user can ask for "B's palette with C's depth effects".
"""
from __future__ import annotations

import copy
from functools import lru_cache
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
    from .measure import font_problem
    for key in ("family", "title_family"):
        why = data["typography"].get(key) and font_problem(data["typography"][key])
        if why:
            raise StyleError(f"style '{rid}' typography.{key}: {why}")
    return Recipe(rid, data)


def compose(base_id: str, mix: dict[str, str] | None = None) -> Recipe:
    r = load_recipe(base_id)
    data = copy.deepcopy(r.data)
    names = [base_id]
    for section, other in (mix or {}).items():
        if section not in SECTIONS:
            raise StyleError(f"unknown style section '{section}' (sections: {', '.join(SECTIONS)})")
        data[section] = copy.deepcopy(load_recipe(other).data[section])
        base_ty = r.data["typography"]
        if (section == "typography" and "title_family" in base_ty  # a size-only mix keeps the base's title face;
                and data[section].get("family") == base_ty.get("family")):  # a new body face sets the titles too
            data[section].setdefault("title_family", base_ty["title_family"])
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
DETAIL_LIGHTEN = 0.80  # a zoom-in panel is a large area whose parts carry their own colours (op kinds, the key part):
# at 55 % its tint competed with them (Restormer's salmon MDTA panel under purple / green / pink layers); published
# detail panels sit on white or a faint tint and keep the source's hue on the border and the callout


def colors_for(recipe: Recipe, el, parent=None) -> tuple[str, str, str]:
    """(fill, stroke, font) for a leaf node or group, after role/tone/nesting rules."""
    pal = recipe["palette"]
    if el.is_group:
        # an area is a lighter tint of the tone its elements carry, so the elements inside still stand out
        if getattr(el, "detail_of", None) and not el.tone:
            # tinted like the node it zooms into (design.md), so the callout halo can match it; yellow only when
            # the source is unknown (a blueprint built in code without load)
            ds = getattr(el, "detail_source", None)
            name = (ds[0] or pal["roles"].get(ds[1], pal["roles"]["reused"])["tone"]) if ds else "yellow"
            t = _tone(recipe, name)
            return mix(t["fill"], "#ffffff", DETAIL_LIGHTEN), t["stroke"], t["font"]
        if el.role == "proposed" or el.tone:
            t = _tone(recipe, el.tone or pal["roles"]["proposed"]["tone"])
            return mix(t["fill"], "#ffffff", AREA_LIGHTEN), t["stroke"], t["font"]
        c = pal["container"]["dashed" if el.frame == "dashed" else "box"]
        return c["fill"], c["stroke"], c["font"]
    role = pal["roles"].get(el.role, pal["roles"]["reused"])
    if (recipe.data.get("inner") == "white" and parent is not None and parent.is_group and el.visual in ("box", "decision")
            and el.role not in ("loss",)):
        # panel style (VERA, arXiv 2611.22815): the panel carries the hue, its boxes are white with a light edge in
        # that hue and dark text; a box the author gave its own tone is the emphasis — a pale tint, text in the hue
        host = parent if (parent.role == "proposed" or parent.tone) else None
        pt = _tone(recipe, el.tone or (host.tone if host and host.tone else None) or role["tone"])
        if el.tone:
            return mix(pt["fill"], "#ffffff", 0.45), pt["stroke"], pt["font"]
        return "#ffffff", mix(pt["stroke"], "#ffffff", 0.35), recipe["typography"]["color"]
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


def lead_size(recipe: Recipe, size: float) -> tuple[float, float]:
    """(diameter, width it takes incl. the gap to the text) of a lead mark — an icon or a letter disc — set before
    text of this size: a little taller than the capitals, so it reads as part of the name; a disc's letter is set at
    the figure's small size (never the smallest text in the figure), so the disc is at least 1.6 times that."""
    d = round(max(1.2 * size, 1.6 * recipe["typography"]["small_size"]), 2)
    return d, round(d + 0.4 * size, 2)


TILE_ICON = 2.2  # a tile's icon, in body sizes


def tile(node) -> bool:
    return box_lead(node) and getattr(node, "icon", None) and getattr(node, "icon_at", "left") == "top"


def box_lead(node) -> bool:
    return (not node.is_group and node.visual == "box"
            and bool(getattr(node, "icon", None) or getattr(node, "marker", None)))


DISPLAY_FONTS = {"Nunito": "Nunito-Bold.woff2"}  # shipped display faces (fonts/, OFL)


def title_lead(recipe: Recipe, group) -> float:
    return lead_size(recipe, recipe["typography"]["title_size"])[1] if getattr(group, "marker", None) else 0.0


def title_family(recipe: Recipe) -> str:
    """The face of group titles: the recipe's display face when it names one, else the body family."""
    ty = recipe["typography"]
    return ty.get("title_family") or ty["family"]


def is_bold_title(recipe: Recipe, group) -> bool:
    return True if title_family(recipe) in DISPLAY_FONTS else _is_bold(recipe, group)


@lru_cache(maxsize=None)
def _font_source(family: str) -> str:
    """A data URI of the shipped face: draw.io renders it and embeds it into the PDF as TrueType (a file:// URL is
    ignored by the exporter and falls back to Times) — and the .drawio stays self-contained."""
    import base64
    import os
    import urllib.parse

    from .measure import SHIPPED_FONTS
    raw = open(os.path.join(SHIPPED_FONTS, DISPLAY_FONTS[family]), "rb").read()
    return urllib.parse.quote("data:font/woff2;base64," + base64.b64encode(raw).decode(), safe="")


def _title_font_keys(recipe: Recipe, color: str, group) -> dict:
    fam = title_family(recipe)
    st = _font_keys(recipe, color, recipe["typography"]["title_size"], is_bold_title(recipe, group))
    st["fontFamily"] = fam
    if fam in DISPLAY_FONTS:
        st["fontSource"] = _font_source(fam)
    return st


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
    if tile(node):  # the name sits under its large icon
        st["spacingTop"] = _num((TILE_ICON + 0.4) * ty["size"])
    elif box_lead(node):  # the name sits right of its icon / letter disc
        st["spacingLeft"] = _num(lead_size(recipe, ty["size"])[1])
    v = node.visual
    if v == "textcard":
        ink = recipe.data.get("ink_scale", 1.0)
        st.update({"rounded": "1", "absoluteArcSize": "1", "arcSize": _num(2 * max(sh["radius"], 4)), "align": "left",
                   "verticalAlign": "top", "spacingLeft": _num(recipe["spacing"]["node_pad_x"]), "spacingTop":
                   _num(recipe["spacing"]["node_pad_y"]), "spacing": "0", "whiteSpace": "nowrap",
                   "fontSize": _num(ty["small_size"]), "fontStyle": "0", "fontColor": ty["color"],
                   "fillColor": fill if getattr(node, "tone", None) else "#ffffff", "strokeColor": stroke,
                   "strokeWidth": _num(sh["stroke_width"])})
        if "$" in (node.label or "").replace("\\$", ""):  # draw.io sizes a no-wrap label from its raw TeX: the
            st["whiteSpace"] = "wrap"  # export bounds would run past the card; wrap keeps them on it (layout adds slack)
        if node.card_style == "code":
            st.update({"fontFamily": "Courier New", "fillColor": "#f6f8fa" if not getattr(node, "tone", None) else fill})
        elif node.card_style == "quote":  # a real input sentence: dashed card in its source's tone (user's own figure)
            st.update({"dashed": "1", "dashPattern": "4 3"})
            tone = (recipe["palette"].get("tones") or {}).get(getattr(node, "tone", None) or "")
            if tone:  # the tone IS the meaning (caption vs label sentence vs concept): never receded
                st.update({"fillColor": tone["fill"], "strokeColor": tone["stroke"]})
        elif node.card_style == "bubble":
            from .layout import BUBBLE_TAIL
            st.update({"shape": "callout", "perimeter": "calloutPerimeter", "size": _num(BUBBLE_TAIL * ink),
                       "position": "0.15", "position2": "0.08", "base": _num(12 * ink)})
        return st
    if v == "text":
        st.update({"strokeColor": "none", "fillColor": "none", "fontColor": font if getattr(node, "tone", None) else ty["color"], "fontStyle": "2" if node.role == "annotation" else st["fontStyle"]})
        st["fontSize"] = _num(ty["small_size"])
        return st
    if v in ("box", "tokens", "chip"):
        st.update({"rounded": "1" if sh["radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["radius"])})
    elif v == "decision":
        st.update({"shape": "rhombus", "perimeter": "rhombusPerimeter"})
    elif v == "trapezoid":
        from .shapes import TRAPEZOID_SIZE
        st.update({"shape": "trapezoid", "perimeter": "trapezoidPerimeter", "size": _num(TRAPEZOID_SIZE),
                   "direction": {"in": "south", "out": "north", "down": "west", "up": "east"}.get(node.taper, "south"), "rounded": "1" if sh["radius"] else "0",
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
            st.update({"imageBorder": recipe["palette"]["image_border"], "strokeWidth": _num(sh["stroke_width"])})
        if v == "glyph" and node.glyph in ("heatmap", "mask", "kspace"):  # schematic data: a dashed frame says "not a result"
            st.update({"imageBorder": recipe["palette"]["image_border"], "strokeWidth": _num(sh["stroke_width"]),
                       "dashed": "1", "dashPattern": "3 2"})
        return st
    elif v == "placeholder":
        st.update({"rounded": "0", "dashed": "1", "dashPattern": "4 3", "fillColor": "#eef0f3", "strokeColor": "#a3aab5",
                   "fontColor": "#4b5563", "fontSize": _num(ty["small_size"]), "fontStyle": "2",
                   "strokeWidth": _num(sh["stroke_width"]), "pfasset": "pending"})
        return st
    sw = sh["stroke_width"] * recipe["palette"]["roles"].get(node.role, {}).get("stroke_scale", 1.0)
    if recipe.data.get("highlight") == "outline" and node.role == "proposed":  # contribution: heavy outline on white
        fill, sw = "#ffffff", 2.2 * float(sw)
    elif recipe.data.get("highlight") == "ring" and node.role == "proposed":
        # colour means modality (user comparison 2026-11-15, a CLIP-style figure): keep the fill, ring it in the accent
        pal = recipe["palette"]
        stroke, sw = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"], 2.2 * float(sh["stroke_width"])
    st.update({"fillColor": fill, "strokeColor": stroke, "strokeWidth": _num(sw)})
    if parent is not None and getattr(parent, "detail_of", None):
        st["shadow"] = "0"  # dense detail panels stay flat: depth there is texture, not meaning
    else:
        st.update(_effects(recipe, fill, stroke))
    return st


def group_style(recipe: Recipe, group) -> dict:
    fill, stroke, font = colors_for(recipe, group)
    sh = recipe["shape"]
    st = {"html": "1", "whiteSpace": "wrap", "container": "1", "collapsible": "0", "recursiveResize": "0",
          "verticalAlign": "top", "align": "left" if getattr(group, "marker", None) else getattr(group, "title_align", "center"),
          "spacingTop": "4"}
    if st["align"] == "left":
        st["spacingLeft"] = _num(recipe["spacing"]["group_pad"] + title_lead(recipe, group))
    st.update(_title_font_keys(recipe, font, group))
    if group.frame == "none":
        st.update({"fillColor": "none", "strokeColor": "none"})
        return st
    gsw = sh["group_stroke_width"] if group.role == "proposed" else sh["stroke_width"]
    if recipe.data.get("highlight") == "outline" and group.role == "proposed":
        # a proposed panel too: heavy outline on white (SimCSE blind run: two proposed panels filled the whole figure
        # orange — the fill encoded nothing, and highlight "outline" changed only boxes)
        fill, gsw = "#ffffff", 1.4 * float(gsw)  # a panel's stroke is already heavy: 2.2x (as for boxes) read as a slab
    elif recipe.data.get("highlight") == "ring" and group.role == "proposed":
        pal = recipe["palette"]
        stroke, gsw = pal["tones"][pal["roles"]["proposed"]["tone"]]["stroke"], 1.4 * float(gsw)
    st.update({"rounded": "1" if sh["group_radius"] else "0", "absoluteArcSize": "1", "arcSize": _num(2 * sh["group_radius"]),
               "fillColor": fill, "strokeColor": stroke, "strokeWidth": _num(gsw)})
    if group.frame == "dashed":
        st.update({"dashed": "1", "dashPattern": "6 4"})
    if group.role == "proposed" or group.tone or getattr(group, "detail_of", None):
        st.update(_effects(recipe, fill, stroke))
    else:  # plain panels stay flat: nested shadows/gradients add noise, not meaning
        st.update({"shadow": "0"})
    return st


ARROW_BASE = 5.0  # endSize at ink 1; draw.io draws a block head ~1.4 endSizes long, so ~7 px (user, round 2: the head
# plus a short straight run must fit the gap — 6 drew 8.4 px heads that ate the run; route.HEAD_DRAWN)


def label_knock(recipe: Recipe) -> float:
    """Side padding of an edge label's knock-out: the line stops this far from the first and last glyph (blind runs
    2026-11-14: 'k < K', '{x_i}' and 'h0' labels touched their own line)."""
    return 3.0 * recipe.data.get("ink_scale", 1.0)


def arrow_size(recipe: Recipe) -> float:
    """The arrowhead endSize edges are drawn with — layout and routing reserve room from the same number."""
    return ARROW_BASE * recipe.data.get("ink_scale", 1.0) ** 0.5


def wide_arrow(recipe: Recipe) -> dict:
    """draw.io flexArrow geometry for a stage hand-over, in drawio units from the body size: band, head width and
    length (draw.io draws the head endSize x 3 long), the clearance off each panel, and the shortest arrow that
    still reads as one (head plus a shaft as long)."""
    s, ink = recipe["typography"]["size"], recipe.data.get("ink_scale", 1.0)
    return {"band": 0.9 * s, "head": 2.0 * s, "head_len": 0.9 * s, "clear": 2.5 * ink, "min_len": 1.8 * s}


def wide_style(recipe: Recipe, edge) -> dict:
    w = wide_arrow(recipe)
    if getattr(edge, "tone", None):
        t = _tone(recipe, edge.tone)
        fill, stroke = t["fill"], t["stroke"]
    else:  # a neutral hand-over in the data lines' colour, filled with a pale tint of it
        stroke = recipe["edges"]["data"]["color"]
        fill = mix(stroke, "#ffffff", 0.82)
    ty = recipe["typography"]
    return {"shape": "flexArrow", "html": "1", "edgeStyle": "none", "rounded": "0", "width": _num(w["band"]),
            "endWidth": _num(w["head"] - w["band"]), "endSize": _num(w["head_len"] / 3), "startArrow": "none",
            "endArrow": "block", "fillColor": fill, "strokeColor": stroke,
            "strokeWidth": _num(recipe["shape"]["stroke_width"]), "fontFamily": ty["family"],
            "fontSize": _num(ty["small_size"]), "fontColor": ty["color"]}


def edge_style_for_kind(recipe: Recipe, kind: str) -> dict:
    one_sided = kind.endswith(":end")  # legend key of a one-sided loss (edge heads "end")
    kind = kind.split(":")[0]
    e = recipe["edges"][kind]
    arrow = _num(arrow_size(recipe))  # heads grow slower than strokes
    st = {"html": "1", "edgeStyle": "none", "rounded": "1" if recipe["shape"]["edge_rounded"] else "0",
          "strokeColor": e["color"], "strokeWidth": _num(e["width"]),
          "endArrow": e["end"], "endFill": "0" if e["end"] in ("open",) else "1", "endSize": arrow,
          "startArrow": e["start"], "startFill": "1", "startSize": arrow,
          "fontFamily": recipe["typography"]["family"], "fontSize": _num(recipe["typography"]["small_size"]),
          "fontColor": recipe["typography"]["color"], "labelBackgroundColor": "#ffffff",
          # draw.io's line jumps: where two lines must cross, the upper one hops over the lower (an arc), so a
          # crossing never reads as a junction (the router avoids crossings; this is for the few it cannot)
          "jumpStyle": "arc", "jumpSize": _num(1.6 * arrow_size(recipe))}
    if e["dash"]:
        st.update({"dashed": "1", "dashPattern": e["dash"]})
    if one_sided:
        st["startArrow"] = "none"
    return st


def edge_style(recipe: Recipe, edge) -> dict:
    st = edge_style_for_kind(recipe, edge.kind)
    if getattr(edge, "heads", "auto") == "end":  # one-sided: only the target's head
        st["startArrow"] = "none"
    elif getattr(edge, "heads", "auto") == "none":  # an undirected link (a toy graph's edge drawn as elements)
        st["startArrow"] = st["endArrow"] = "none"
    if getattr(edge, "tone", None):  # one path's semantic colour (declared in color_semantics)
        st["strokeColor"] = _tone(recipe, edge.tone)["stroke"]
    if getattr(edge, "curved", False):  # a spline through the same routed bends
        st.update({"curved": "1", "rounded": "1"})
    return st


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
    tw, th = measure(group.title, recipe["typography"]["title_size"], is_bold_title(recipe, group), title_family(recipe))
    left = getattr(group, "title_align", "center") == "left" or getattr(group, "marker", None)
    x = tb.x + recipe["spacing"]["group_pad"] + title_lead(recipe, group) if left else tb.cx - tw / 2
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


ACCENT_FILL_L = 74  # the contribution's fill: >= ~12 L* below the other fills, so it stands out in grayscale
# print (grammar.gray_highlight) — published overviews' colours sit at L* ~72-77 (KB cards); 82 read as one with 87
PHOTO_DEPICTS = {"real-photos", "3d-render"}  # depicts values whose pixels are not the figure's own colours


def derive_style(base: str, cards_dir, out, card_ids=None) -> Path:
    """A run-local recipe whose tones come from the references' measured palettes (the colours they actually
    use), mapped by hue onto the base recipe's tone names; the most saturated, most used colour becomes the
    accent for the proposed parts. Fills are tinted (L* 87, accent ACCENT_FILL_L), strokes L* 55, fonts dark enough for
    4.5:1 on their fill. Everything else comes from `base`. Style stays open: this is one more candidate."""
    import math
    from . import color

    r = load_recipe(base)
    data = copy.deepcopy(r.data)
    cols, used, skipped = [], [], []
    for f in sorted(Path(cards_dir).glob("*.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if card_ids and c.get("id") not in card_ids:
            continue
        ms = c.get("measured") or {}
        dep = set(((c.get("taxonomy") or {}).get("depicts")) or [])
        if ms.get("photo_share") is None and dep & PHOTO_DEPICTS:
            skipped.append(c.get("id") or f.stem)  # its palette was measured with the photos in it (browns, skin)
            continue
        pal = ms.get("palette") or []
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
        raise StyleError(f"no chromatic colours measured in the cards under {cards_dir} — nothing to derive from"
                         + (f" ({len(skipped)} card(s) skipped: palette measured with photos in it — "
                            f"{', '.join(skipped)})" if skipped else ""))
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
    def _hue(t: dict) -> float:
        # the more chromatic of fill and stroke names the tone: editorial-minimal strokes 7 tones in near-black
        # #1f2937 (hue ≈270), so stroke hues mapped every reference colour onto the wrong tone names
        labs = [color.lab(t[x]) for x in ("stroke", "fill") if isinstance(t.get(x), str)]
        _, a, b = max(labs, key=lambda v: math.hypot(v[1], v[2]))
        if math.hypot(a, b) < 5:
            raise StyleError("a base tone has no chromatic fill or stroke — its hue (and name) is undefined")
        return math.degrees(math.atan2(b, a)) % 360

    hue_of = {k: _hue(tones[k]) for k in names}
    reused_tone = data["palette"]["roles"].get("reused", {}).get("tone")
    base_acc = tones.get(data["palette"]["roles"]["proposed"]["tone"], {}).get("stroke", "").lower()
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
        fill = _set_L(hx, ACCENT_FILL_L if k == accent else 87)
        font = _set_L(hx, 30)
        while color.contrast(font, fill) < 4.5 and color.lab(font)[0] > 5:
            font = _set_L(font, color.lab(font)[0] - 4)
        tones[k] = {"fill": fill, "stroke": stroke, "font": font}
    data["palette"]["roles"]["proposed"]["tone"] = accent
    acc_strokes = {tones[accent]["stroke"].lower(), base_acc} - {""}
    for kind, e in data["edges"].items():
        if kind != "data" and isinstance(e, dict) and str(e.get("color", "")).lower() in acc_strokes:
            e["color"] = "#6b7280"  # training/other paths never borrow the accent (one colour, one meaning)
    data["derived_from"] = {"base": base, "cards": used, "skipped_photo_palettes": skipped}
    data["id"] = Path(out).stem  # never mistaken for the base recipe in samples or the lint's style line
    data["name"] = f"derived from the references (base {base})"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
