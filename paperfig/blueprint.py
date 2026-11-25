"""Load and validate a figure blueprint (spec §5).

All problems are collected and raised together in one BlueprintError so the
caller (or the user) can fix them in one pass.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Union

import jsonschema

from .errors import BlueprintError

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "blueprint.schema.json"
ALLOWED_TAGS = {"i", "b", "sub", "sup", "br", "small"}
TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)\s*/?>")

Role = Literal["proposed", "reused", "io", "data", "loss", "op", "annotation"]
Visual = Literal["box", "tensor", "tokens", "image", "icon", "op", "text", "placeholder", "glyph", "textcard", "chip"]
EdgeKind = Literal["data", "skip", "loss", "train_only", "infer_only", "grad", "control"]
Side = Literal["auto", "left", "right", "top", "bottom"]


@dataclass
class Provenance:
    source: str
    ref: str


@dataclass
class Asset:
    path: str | None
    status: str
    spec: str = ""
    grounds: dict | None = None  # generated: {"ref", "quote"} — where the source describes this visual scene


@dataclass
class Layout:
    type: str = "row"
    align: str = "center"
    gap: str = "normal"
    equalize: bool = True
    cols: int = 12  # canvas: number of equal columns a child's span is a share of
    order: str = "auto"  # "fixed": never reordered to cross fewer lines (order.auto_order)


@dataclass
class Node:
    id: str
    label: str
    role: str = "reused"
    visual: str = "box"
    tone: str | None = None
    full_name: str | None = None
    abbrev: str | None = None
    badges: list[str] = field(default_factory=list)
    icon: str | None = None
    marker: str | None = None  # a letter disc before a box's name (a table row's module letter)
    asset: Asset | None = None
    size: tuple[float, float] | None = None
    tokens: int | None = None
    provenance: list[Provenance] = field(default_factory=list)
    cell: tuple[int, int] | None = None
    span: tuple[int, int] = (1, 1)
    taper: str = "in"
    sheets: int = 3
    op: str | None = None
    place: str = "grid"
    glyph: str | None = None  # visual "glyph": graph, database, prototype, heatmap, mask, kspace, documents
    nodes: int = 5  # graph glyph: node count
    pattern: str = "cartesian"  # kspace glyph: sampling pattern
    variant: str | None = None  # pointcloud / plot / patches glyph: which shape, curve or partition
    grid: tuple | None = None  # onehot / patches / pair-matrix glyph: [rows, cols]
    col_tone: str | None = None  # pair-matrix glyph: the column side's tone (rows take the node's own tone)
    positives: list | None = None  # pair-matrix glyph: 1-based [row, col] cells drawn as positive pairs
    axes: list | None = None  # pair-matrix glyph: [row symbol, column symbol] — header cells read z_1 …, t_1 …
    illustrative: bool = False  # schematic glyph declared as illustrative (not a result)
    values: tuple | None = None  # tokens: one value in [0, 1] per cell, drawn as the cell's shade
    card_style: str = "plain"  # textcard: plain | code | bubble | quote
    stub: dict | None = None  # {"side": ..., "label": ...}: a short outgoing arrow with no drawn target
    accent: bool = True  # glyph: use the accent colour for its focal element
    align_x: str | None = None  # line up (horizontally) with this node after layout
    pin: tuple | None = None  # (dx, dy): a hand move absorbed from draw.io, applied after layout
    align_y: str | None = None

    is_group = False


@dataclass
class Group:
    id: str
    children: list["Element"]
    title: str | None = None
    role: str | None = None
    tone: str | None = None
    full_name: str | None = None
    abbrev: str | None = None
    frame: str = "box"
    axis_of: str | None = None  # descendant whose centre line is this group's alignment axis
    detail_of: str | None = None  # node this panel zooms into (callout)
    align_x: str | None = None  # line up (horizontally) with this node after layout
    pin: tuple | None = None  # (dx, dy): a hand move absorbed from draw.io, applied after layout
    align_y: str | None = None
    title_align: str = "center"
    marker: str | None = None  # a letter disc before the title (Ⓐ in the text, drawn as a shape: no font fallback)
    place: str = "grid"  # "free": anchored at its grid cell, does not size rows/columns
    layout: Layout = field(default_factory=Layout)
    provenance: list[Provenance] = field(default_factory=list)
    cell: tuple[int, int] | None = None
    span: tuple[int, int] = (1, 1)
    detail_source: tuple | None = None  # (tone, role) of the node a detail panel zooms into: its tint (load)

    is_group = True

    @property
    def label(self) -> str:
        return self.title or ""


Element = Union[Node, Group]


@dataclass
class Edge:
    id: str
    src: str
    dst: str
    kind: str = "data"
    label: str | None = None
    src_side: str = "auto"
    dst_side: str = "auto"
    provenance: list[Provenance] = field(default_factory=list)
    tone: str | None = None  # one path's semantic colour
    curved: bool = False  # drawn as a smooth curve through the router's bends (feedback loops, long links)
    bundle: str | None = None  # edges from one source with the same bundle name share one trunk, then branch
    heads: str = "auto"  # "end": only the target's head (a one-sided loss/penalty; TWM run: entropy hinge on the policy)


@dataclass
class Annotation:
    id: str
    kind: str
    covers: list[str]
    label: str
    side: str = "top"
    placement: str = "outer"  # inner: right above/below what it covers (between rows)


@dataclass
class Figure:
    type: str
    venue: str
    width: str | float
    label_language: str = "en"
    legend: str = "auto"
    title: str | None = None
    style: str | None = None
    legend_notes: list = field(default_factory=list)
    legend_labels: dict = field(default_factory=dict)
    highlight: str = "fill"  # fill | outline | ring
    font: str = "sans"  # sans (the style's family, Helvetica) | serif (Times New Roman, to match a serif body)
    tone_legend: bool = False  # a swatch per tone used, named by the plan's color_semantics (VS-Net blind run)
    legend_at: str = "auto"  # auto (a free corner, else right column / bottom band) | corner | bottom | right | top


@dataclass
class Blueprint:
    figure: Figure
    root: Group
    edges: list[Edge]
    discrepancies: list[dict]
    index: dict[str, Element]
    parent: dict[str, str | None]
    source_path: Path | None = None
    annotations: list[Annotation] = field(default_factory=list)

    @property
    def annotation_members(self) -> dict[str, list[str]]:
        return {a.id: list(a.covers) for a in self.annotations}

    def ancestors(self, eid: str) -> list[str]:
        out, p = [], self.parent.get(eid)
        while p is not None:
            out.append(p)
            p = self.parent.get(p)
        return out

    def leaves(self) -> list[Node]:
        return [e for e in self.index.values() if not e.is_group]

    def groups(self) -> list[Group]:
        return [e for e in self.index.values() if e.is_group]


def _cycle_cells(g, hub: str | None, probs: list) -> None:
    """A loop: members clockwise around a rectangle (top row left→right, bottom row right→left), the optional hub
    inside it — laid out as a grid, so edges between neighbours run along the loop's sides."""
    members = [c for c in g.children if c.id != hub]
    if hub and hub not in {c.id for c in g.children}:
        probs.append(f"'{g.id}': cycle hub '{hub}' is not one of its children")
        return
    if len(members) < 3:
        probs.append(f"'{g.id}': a cycle needs at least 3 members")
        return
    if any(c.cell is not None for c in g.children):
        probs.append(f"'{g.id}': cycle children get their places from the loop — remove their `cell`")
        return
    k = (len(members) + 1) // 2
    bottom = 2 if hub else 1
    for i, c in enumerate(members):
        c.cell = (0, i) if i < k else (bottom, k - 1 - (i - k))
    if hub:
        h = next(c for c in g.children if c.id == hub)
        h.cell, h.span = (1, 0), (1, k)
    g.layout.type = "grid"


GRIDLIKE = ("grid", "canvas")
FILE_STATUSES = ("provided", "from-code")


def has_file(asset) -> bool:
    """An asset drawn from a real file: provided, produced by the code, or a generated illustration once made."""
    return asset is not None and (asset.status in FILE_STATUSES or (asset.status == "generated" and bool(asset.path)))  # children placed by cell/span: a grid sizes tracks to content, a canvas has equal columns


def plain_text(label: str) -> str:
    """Label without markup; <br> becomes a space; whitespace collapsed."""
    s = re.sub(r"<br\s*/?>", " ", label or "")
    s = re.sub(r"<[^>]+>", "", s)  # any tag, attributes included (draw.io's <span style=…> for <small>)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _norm(s: str) -> str:
    # math delimiters dropped: a name written "$n_{it}$" is drawn as "\(n_{it}\)" (VS-Net blind run: validate passed,
    # the build's lint failed on the same name)
    t = re.sub(r"\\[()\[\]]|\$", "", plain_text(s))
    return re.sub(r"[\s\-‐]+", " ", t).strip().lower()


def name_shown(label: str, name: str | None) -> bool:
    return bool(name) and _norm(name) in _norm(label)


def _image_problem(path: str) -> str | None:
    """Fully decode the image (header-only checks miss truncated files)."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
    except Exception as e:  # PIL raises several unrelated types for bad files
        return f"{type(e).__name__}: {e}"
    return None


def _schema_problems(data: dict) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    probs = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(top)"
        probs.append(f"schema at {where}: {err.message}")
    return probs


def load(src: str | Path | dict, base_dir: str | Path | None = None) -> Blueprint:
    source_path = None
    if isinstance(src, (str, Path)):
        source_path = Path(src).resolve()
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise BlueprintError([f"blueprint file not found: {source_path}"])
        except json.JSONDecodeError as e:
            raise BlueprintError([f"blueprint is not valid JSON: {e}"])
        base = Path(base_dir) if base_dir else source_path.parent
    else:
        data = src
        base = Path(base_dir) if base_dir else Path.cwd()

    probs = _schema_problems(data)
    if probs:  # structure is unreliable; semantic checks would only add noise
        raise BlueprintError(probs)

    index: dict[str, Element] = {}
    parent: dict[str, str | None] = {}

    def prov(lst):
        return [Provenance(p["source"], p["ref"]) for p in (lst or [])]

    def build(d: dict, par: str | None) -> Element:
        eid = d["id"]
        if eid in index:
            probs.append(f"duplicate id '{eid}'")
        if "children" in d:
            lay = d.get("layout", {})
            g = Group(
                id=eid,
                children=[],
                title=d.get("title"),
                role=d.get("role"),
                tone=d.get("tone"),
                full_name=d.get("full_name"),
                abbrev=d.get("abbrev"),
                frame=d.get("frame", "none" if par is None else "box"),
                axis_of=d.get("axis_of"),
                detail_of=d.get("detail_of"),
                align_x=d.get("align_x"),
                pin=tuple(d["pin"]) if d.get("pin") else None,
                align_y=d.get("align_y"),
                title_align=d.get("title_align", "center"),
                marker=d.get("marker"),
                place=d.get("place", "grid"),
                layout=Layout(lay.get("type", "row"), lay.get("align", "center"), lay.get("gap", "normal"), lay.get("equalize", True),
                              int(lay.get("cols", 12)), lay.get("order", "auto")),
                provenance=prov(d.get("provenance")),
                cell=tuple(d["cell"]) if "cell" in d else None,
                span=tuple(d.get("span", (1, 1))),
            )
            index.setdefault(eid, g)
            parent.setdefault(eid, par)
            g.children = [build(c, eid) for c in d["children"]]
            if lay.get("type") == "cycle":
                _cycle_cells(g, lay.get("hub"), probs)
            return g
        a = d.get("asset")
        asset = None
        if a:
            path = a.get("path")
            if path:
                path = str(Path(path).expanduser())
                path = str((base / path).resolve()) if not Path(path).is_absolute() else path
            asset = Asset(path, a["status"], a.get("spec", ""), a.get("grounds"))
        n = Node(
            id=eid,
            label=d["label"],
            role=d.get("role", "reused"),
            visual=d.get("visual", "box"),
            tone=d.get("tone"),
            full_name=d.get("full_name"),
            abbrev=d.get("abbrev"),
            badges=list(d.get("badges", [])),
            icon=d.get("icon"),
            marker=d.get("marker"),
            asset=asset,
            size=tuple(d["size"]) if "size" in d else None,
            tokens=d.get("tokens"),
            taper=d.get("taper", "in"),
            sheets=d.get("sheets", 3),
            op=d.get("op"),
            place=d.get("place", "grid"),
            glyph=d.get("glyph"),
            nodes=int(d.get("nodes", 5)),
            pattern=d.get("pattern", "cartesian"),
            variant=d.get("variant"),
            grid=tuple(d["grid"]) if d.get("grid") else None,
            col_tone=d.get("col_tone"),
            axes=d.get("axes"),
            positives=d.get("positives"),
            illustrative=bool(d.get("illustrative", False)),
            values=tuple(d["values"]) if d.get("values") is not None else None,
            card_style=d.get("card_style", "plain"),
            stub=d.get("stub"),
            accent=bool(d.get("accent", True)),
            align_x=d.get("align_x"),
                pin=tuple(d["pin"]) if d.get("pin") else None,
            align_y=d.get("align_y"),
            provenance=prov(d.get("provenance")),
            cell=tuple(d["cell"]) if "cell" in d else None,
            span=tuple(d.get("span", (1, 1))),
        )
        index.setdefault(eid, n)
        parent.setdefault(eid, par)
        return n

    root = build(data["root"], None)

    edges = []
    taken = set(index) | {e["id"] for e in data.get("edges", []) if "id" in e}
    for i, e in enumerate(data.get("edges", [])):
        eid = e.get("id")
        if eid is None:  # auto id that never collides with a node id or an explicit edge id
            eid = f"e{i}"
            k = 0
            while eid in taken:
                k += 1
                eid = f"e{i}_{k}"
            taken.add(eid)
        edges.append(
            Edge(
                id=eid,
                src=e["src"],
                dst=e["dst"],
                kind=e.get("kind", "data"),
                label=e.get("label"),
                src_side=e.get("src_side", "auto"),
                dst_side=e.get("dst_side", "auto"),
                provenance=prov(e.get("provenance")),
                tone=e.get("tone"),
                curved=bool(e.get("curved", False)),
                bundle=e.get("bundle"),
                heads=e.get("heads", "auto"),
            )
        )
    f = data["figure"]
    figure = Figure(f["type"], f["venue"], f["width"], f.get("label_language", "en"), f.get("legend", "auto"), f.get("title"), f.get("style"), list(f.get("legend_notes", [])),
                    dict(f.get("legend_labels", {})), f.get("highlight", "fill"), f.get("font", "sans"),
                    bool(f.get("tone_legend", False)), f.get("legend_at", "auto"))
    anns = [Annotation(a["id"], a["kind"], list(a["covers"]), a["label"], a.get("side", "top"), a.get("placement", "outer"))
            for a in data.get("annotations", [])]
    bp = Blueprint(figure, root, edges, list(data.get("discrepancies", [])), index, parent, source_path, anns)
    _semantic_checks(bp, probs)
    for g in bp.groups():  # a detail panel is tinted like the node it zooms into (design.md), not a fixed yellow
        src = index.get(g.detail_of) if g.detail_of else None
        if src is not None:
            g.detail_source = (src.tone, src.role)
    if not isinstance(figure.width, (int, float)):  # a named width needs a known venue (else give inches)
        import json as _json
        known = _json.loads((Path(__file__).resolve().parent.parent / "kb" / "formats.json").read_text())["venues"]
        if str(figure.venue).lower() not in known:
            probs.append(f"figure.venue '{figure.venue}' is not in kb/formats.json (known: {', '.join(sorted(known))}); "
                         "use the template's id (e.g. MICCAI papers use the LNCS template: 'lncs') or give "
                         "figure.width in inches")
    if probs:
        raise BlueprintError(probs)
    return bp


ENTITIES = {"lt", "gt", "amp", "nbsp"}


def _check_markup(eid: str, text: str | None, probs: list[str]):
    for m in re.finditer(r"&([A-Za-z][A-Za-z0-9]*|#\d+);", text or ""):
        if m.group(1) not in ENTITIES:
            probs.append(f"'{eid}': entity &{m.group(1)}; is not supported (only &lt; &gt; &amp; &nbsp;) — it would print "
                         "as text; type the character itself")
    for m in TAG_RE.finditer(text or ""):
        if m.group(1).lower() not in ALLOWED_TAGS:
            probs.append(f"'{eid}': markup tag <{m.group(1)}> not allowed (allowed: {', '.join(sorted(ALLOWED_TAGS))})")


def _semantic_checks(bp: Blueprint, probs: list[str]):
    edge_ids = set()
    for e in bp.edges:
        if e.id in edge_ids or e.id in bp.index:
            probs.append(f"duplicate id '{e.id}' (edge)")
        edge_ids.add(e.id)

    for el in bp.index.values():
        text = el.title if el.is_group else el.label
        _check_markup(el.id, text, probs)
        if not el.is_group and getattr(el, "positives", None) is not None:
            from .glyphs import GRIDDED, check_positives
            if el.glyph != "pair-matrix":
                probs.append(f"'{el.id}': positives is for a pair-matrix glyph")
            else:
                probs += [f"'{el.id}': {p}" for p in check_positives(el.positives, tuple(el.grid or GRIDDED["pair-matrix"]))]
        needs_prov = (not el.is_group and el.visual != "text") or (el.is_group and el.role == "proposed")
        if needs_prov and not el.provenance:
            probs.append(f"'{el.id}': missing provenance (every drawn component must trace to the draft or code)")
        if el.role == "proposed":
            if not (el.full_name or el.abbrev):
                probs.append(f"'{el.id}': proposed element needs full_name and/or abbrev (the author's name for it)")
            else:
                shown = el.title if el.is_group else el.label
                named = lambda t: name_shown(t or "", el.full_name) or name_shown(t or "", el.abbrev)  # noqa: E731
                by_bracket = el.is_group and any(el.id in a.covers and named(a.label) for a in bp.annotations)
                if not (named(shown) or by_bracket):
                    want = " / ".join(x for x in (el.full_name, el.abbrev) if x)
                    where = (" — in its title, or in the label of a bracket that covers it" if el.is_group else "")
                    probs.append(f"'{el.id}': proposed element's visible text {shown!r} must contain its name ({want}){where}")
        if not el.is_group:
            if el.visual == "image":
                if el.asset is None:
                    probs.append(f"'{el.id}': image node needs an asset (status provided/from-code/requested/placeholder)")
            if el.asset and el.asset.status == "generated":  # a concept illustration, never data (SKILL ⑤)
                if not getattr(el, "illustrative", False):
                    probs.append(f"'{el.id}': a generated image must be marked \"illustrative\": true (a concept "
                                 "illustration, never data, an input sample or a result)")
                if not (el.asset.spec or "").strip():
                    probs.append(f"'{el.id}': a generated image needs asset.spec — the scene it shows (its prompt)")
                if not (el.asset.grounds and str(el.asset.grounds.get("quote", "")).strip()):
                    probs.append(f"'{el.id}': a generated image needs asset.grounds {{ref, quote}} — where the paper or "
                                 "code describes this visual scene; a scene the source does not describe is invented "
                                 "(a text, API or unit-test environment stays an icon or a text card)")
            if el.asset and has_file(el.asset):
                if not el.asset.path:
                    probs.append(f"'{el.id}': asset with status {el.asset.status} needs a path")
                elif not Path(el.asset.path).is_file():
                    probs.append(f"'{el.id}': asset file not found: {el.asset.path}")
                elif el.visual == "image":
                    err = _image_problem(el.asset.path)
                    if err:
                        probs.append(f"'{el.id}': asset {el.asset.path} is not a readable image ({err})")
            if el.visual == "tokens" and not el.tokens:
                probs.append(f"'{el.id}': tokens visual needs a token count")
            if "frozen" in el.badges and "trainable" in el.badges:
                probs.append(f"'{el.id}': badges 'frozen' and 'trainable' contradict each other")
            if el.op and el.visual != "op":
                probs.append(f"'{el.id}': op '{el.op}' needs visual 'op'")
            if el.visual == "op" and not el.op and not el.label.strip():
                probs.append(f"'{el.id}': op node needs an op kind or a label")
            if el.visual == "icon" and not el.icon:
                probs.append(f"'{el.id}': icon visual needs an icon name")
            for ax in ("align_x", "align_y"):
                t = getattr(el, ax, None)
                if t and (t not in bp.index or t == el.id or el.id in bp.ancestors(t) or t in bp.ancestors(el.id)):
                    probs.append(f"'{el.id}': {ax} '{t}' must be another node outside this element (not its own part or container)")
            if el.values is not None and (el.visual != "tokens" or len(el.values) != (el.tokens or 1)):
                probs.append(f"'{el.id}': values need visual tokens and one value per token ({el.tokens or 1})")
            if el.visual == "glyph":
                from .glyphs import GLYPHS
                if el.glyph not in GLYPHS:
                    probs.append(f"'{el.id}': glyph visual needs \"glyph\": one of {', '.join(GLYPHS)}")
                from .glyphs import GRIDDED, VARIANTS
                if el.grid is not None and el.glyph not in GRIDDED:
                    probs.append(f"'{el.id}': grid is for the {' / '.join(GRIDDED)} glyphs, not {el.glyph}")
                if el.variant is not None and el.variant not in VARIANTS.get(el.glyph, ()):
                    probs.append(f"'{el.id}': variant '{el.variant}' — the {el.glyph} glyph takes "
                                 f"{', '.join(VARIANTS.get(el.glyph, ())) or 'no variant'}")
        else:
            if el.detail_of and (el.detail_of not in bp.index or el.id in bp.ancestors(el.detail_of) or el.detail_of == el.id):
                probs.append(f"'{el.id}': detail_of '{el.detail_of}' must name a node outside this panel")
            if el.axis_of and (el.axis_of not in bp.index or el.id not in bp.ancestors(el.axis_of)):
                probs.append(f"'{el.id}': axis_of '{el.axis_of}' must be a descendant of the group")
            for ax in ("align_x", "align_y"):
                t = getattr(el, ax, None)
                if t and (t not in bp.index or t == el.id or el.id in bp.ancestors(t) or t in bp.ancestors(el.id)):
                    probs.append(f"'{el.id}': {ax} '{t}' must be another node outside this element (not its own part or container)")
            if el.layout.type in GRIDLIKE:
                occupied: dict[tuple[int, int], str] = {}
                for c in el.children:
                    if c.cell is None:
                        probs.append(f"'{c.id}': child of {el.layout.type} '{el.id}' needs a cell [row, col]")
                        continue
                    if el.layout.type == "canvas" and c.cell[1] + c.span[1] > el.layout.cols:
                        probs.append(f"canvas '{el.id}': '{c.id}' spans columns {c.cell[1]}–{c.cell[1] + c.span[1] - 1} "
                                     f"but the canvas has {el.layout.cols} cols (0–{el.layout.cols - 1})")
                    for r in range(c.cell[0], c.cell[0] + c.span[0]):
                        for k in range(c.cell[1], c.cell[1] + c.span[1]):
                            if (r, k) in occupied:
                                probs.append(f"grid '{el.id}': '{c.id}' and '{occupied[(r, k)]}' overlap at cell [{r}, {k}]")
                            occupied[(r, k)] = c.id

    for a in bp.annotations:
        if a.id in bp.index or a.id in edge_ids:
            probs.append(f"duplicate id '{a.id}' (annotation)")
        _check_markup(a.id, a.label, probs)
        for c in a.covers:
            if c not in bp.index:
                probs.append(f"annotation '{a.id}': covers unknown id '{c}'")
    for e in bp.edges:
        _check_markup(e.id, e.label, probs)
        if not e.provenance:
            probs.append(f"edge '{e.id}' ({e.src}->{e.dst}): missing provenance")
        for end, name in (("src", e.src), ("dst", e.dst)):
            if name not in bp.index:
                probs.append(f"edge '{e.id}': unknown {end} '{name}'")
        if e.src == e.dst:
            probs.append(f"edge '{e.id}': self-loop on '{e.src}' is not supported")
            continue
        if e.src in bp.index and e.dst in bp.index:
            if e.src in bp.ancestors(e.dst) or e.dst in bp.ancestors(e.src):
                probs.append(f"edge '{e.id}': '{e.src}' -> '{e.dst}' connects an element to its own ancestor container")
