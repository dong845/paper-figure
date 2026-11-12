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

SCHEMA_PATH = Path(__file__).parent / "schema" / "blueprint.schema.json"
ALLOWED_TAGS = {"i", "b", "sub", "sup", "br"}
TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)\s*/?>")

Role = Literal["proposed", "reused", "io", "data", "loss", "op", "annotation"]
Visual = Literal["box", "tensor", "tokens", "image", "icon", "op", "text", "placeholder"]
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


@dataclass
class Layout:
    type: str = "row"
    align: str = "center"
    gap: str = "normal"
    equalize: bool = True


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
    asset: Asset | None = None
    size: tuple[float, float] | None = None
    tokens: int | None = None
    provenance: list[Provenance] = field(default_factory=list)
    cell: tuple[int, int] | None = None
    span: tuple[int, int] = (1, 1)

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
    layout: Layout = field(default_factory=Layout)
    provenance: list[Provenance] = field(default_factory=list)
    cell: tuple[int, int] | None = None
    span: tuple[int, int] = (1, 1)

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


@dataclass
class Figure:
    type: str
    venue: str
    width: str | float
    label_language: str = "en"
    legend: str = "auto"
    title: str | None = None


@dataclass
class Blueprint:
    figure: Figure
    root: Group
    edges: list[Edge]
    discrepancies: list[dict]
    index: dict[str, Element]
    parent: dict[str, str | None]
    source_path: Path | None = None

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


def plain_text(label: str) -> str:
    """Label without markup; <br> becomes a space; whitespace collapsed."""
    s = re.sub(r"<br\s*/?>", " ", label or "")
    s = TAG_RE.sub("", s)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _norm(s: str) -> str:
    return re.sub(r"[\s\-‐]+", " ", plain_text(s)).strip().lower()


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
                layout=Layout(lay.get("type", "row"), lay.get("align", "center"), lay.get("gap", "normal"), lay.get("equalize", True)),
                provenance=prov(d.get("provenance")),
                cell=tuple(d["cell"]) if "cell" in d else None,
                span=tuple(d.get("span", (1, 1))),
            )
            index.setdefault(eid, g)
            parent.setdefault(eid, par)
            g.children = [build(c, eid) for c in d["children"]]
            return g
        a = d.get("asset")
        asset = None
        if a:
            path = a.get("path")
            if path:
                path = str(Path(path).expanduser())
                path = str((base / path).resolve()) if not Path(path).is_absolute() else path
            asset = Asset(path, a["status"], a.get("spec", ""))
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
            asset=asset,
            size=tuple(d["size"]) if "size" in d else None,
            tokens=d.get("tokens"),
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
            )
        )
    f = data["figure"]
    figure = Figure(f["type"], f["venue"], f["width"], f.get("label_language", "en"), f.get("legend", "auto"), f.get("title"))
    bp = Blueprint(figure, root, edges, list(data.get("discrepancies", [])), index, parent, source_path)
    _semantic_checks(bp, probs)
    if probs:
        raise BlueprintError(probs)
    return bp


def _check_markup(eid: str, text: str | None, probs: list[str]):
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
        needs_prov = (not el.is_group and el.visual != "text") or (el.is_group and el.role == "proposed")
        if needs_prov and not el.provenance:
            probs.append(f"'{el.id}': missing provenance (every drawn component must trace to the draft or code)")
        if el.role == "proposed":
            if not (el.full_name or el.abbrev):
                probs.append(f"'{el.id}': proposed element needs full_name and/or abbrev (the author's name for it)")
            else:
                shown = el.title if el.is_group else el.label
                if not (name_shown(shown or "", el.full_name) or name_shown(shown or "", el.abbrev)):
                    want = " / ".join(x for x in (el.full_name, el.abbrev) if x)
                    probs.append(f"'{el.id}': proposed element's visible text {shown!r} must contain its name ({want})")
        if not el.is_group:
            if el.visual == "image":
                if el.asset is None:
                    probs.append(f"'{el.id}': image node needs an asset (status provided/from-code/requested/placeholder)")
            if el.asset and el.asset.status in ("provided", "from-code"):
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
            if el.visual == "icon" and not el.icon:
                probs.append(f"'{el.id}': icon visual needs an icon name")
        else:
            if el.axis_of and (el.axis_of not in bp.index or el.id not in bp.ancestors(el.axis_of)):
                probs.append(f"'{el.id}': axis_of '{el.axis_of}' must be a descendant of the group")
            if el.layout.type == "grid":
                occupied: dict[tuple[int, int], str] = {}
                for c in el.children:
                    if c.cell is None:
                        probs.append(f"'{c.id}': child of grid '{el.id}' needs a cell [row, col]")
                        continue
                    for r in range(c.cell[0], c.cell[0] + c.span[0]):
                        for k in range(c.cell[1], c.cell[1] + c.span[1]):
                            if (r, k) in occupied:
                                probs.append(f"grid '{el.id}': '{c.id}' and '{occupied[(r, k)]}' overlap at cell [{r}, {k}]")
                            occupied[(r, k)] = c.id

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
