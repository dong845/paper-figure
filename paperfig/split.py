"""Split an overview with detail panels into the two figures top-venue papers often use (round 8): the overview,
whose expanded node points to the new figure, and one module figure per detail panel. Facts, drawn_as and omitted
entries go to the part that draws their ends; the plan's mechanism pointer is dropped from the overview."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .errors import PaperFigError


def _ids(n) -> set:
    out = {n["id"]}
    for c in n.get("children", []):
        out |= _ids(c)
    return out


def _resolves(x: str, ids: set, drawn_as: list, edge_ids: set) -> bool:
    if x in ids:
        return True
    for m in drawn_as:
        if x in m.get("ids", []):
            t = m.get("into")
            if m.get("on_edge") is not None:
                return m["on_edge"] in edge_ids
            return all(i in ids for i in (t if isinstance(t, list) else [t]))
    return False


def _edge_ids(d: dict) -> set:
    out = set()
    for i, e in enumerate(d.get("edges", [])):
        out.add(e.get("id", f"e{i}"))
    return out


def _letter(p: dict):
    m = re.match(r"\s*\(([a-z])\)", str(p.get("title", "")), re.I)
    return m.group(1).lower() if m else None


def _texts(d: dict) -> str:
    out = []

    def walk(n):
        out.extend(str(n.get(k, "")) for k in ("label", "title", "full_name", "abbrev"))
        for c in n.get("children", []):
            walk(c)
    walk(d["root"])
    out += [str(e.get("label", "")) for e in d.get("edges", [])] + [str(a.get("label", "")) for a in d.get("annotations", []) or []]
    return " ".join(out)


def _note_applies(note: str, text: str) -> bool:
    """A legend note 'X = Y' belongs to a part that draws X (any symbol or word of it)."""
    lhs = note.split("=", 1)[0]
    terms = [t for t in re.split(r"[\s/,]+", lhs) if t and (len(t) > 1 or not t.isalnum())]
    return not terms or any(t in text for t in terms)


def split(blueprint_path, out_dir, first_fig: int = 2, style: str | None = None) -> dict:
    src = Path(blueprint_path)
    try:
        bp = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"split: cannot read {src}: {e}") from e
    load = lambda name: json.loads((src.parent / name).read_text(encoding="utf-8")) if (src.parent / name).is_file() else None
    facts = (load("facts.json") or {}).get("facts", [])
    plan = load("figure_plan.json") or {}

    panels = []

    def take(n):
        if "children" not in n:
            return
        keep = []
        for c in n.get("children", []):
            if c.get("detail_of"):
                panels.append(c)
            else:
                take(c)
                keep.append(c)
        n["children"] = keep
    ov = copy.deepcopy(bp)
    take(ov["root"])
    if not panels:
        raise PaperFigError("split: the blueprint has no detail panel (a group with detail_of) to move out")

    if all(_letter(p) for p in panels):  # number the module figures in the panels' own (a), (b), … order
        panels.sort(key=_letter)
    out = Path(out_dir)
    res = {"overview": None, "modules": [], "dropped_edges": [], "dropped_facts": []}
    # edges: overview keeps those with both ends still drawn; a panel takes its internal edges
    by_id = {e.get("id", f"e{i}"): e for i, e in enumerate(bp.get("edges", []))}
    ov_ids = _ids(ov["root"])
    ov["edges"] = [e for e in bp.get("edges", []) if e["src"] in ov_ids and e["dst"] in ov_ids]
    for a in ov.get("annotations", []) or []:
        a["covers"] = [c for c in a.get("covers", []) if c in ov_ids]
    ov["annotations"] = [a for a in ov.get("annotations", []) or [] if a["covers"]]
    parts = [("overview", ov)]
    for k, pnl in enumerate(panels):
        fig_no = first_fig + k
        node = pnl["detail_of"]

        def mark(n):  # the expanded node points to its own figure
            if n["id"] == node:
                if n.get("children"):
                    n["title"] = f"{n.get('title', '')} (Fig. {fig_no})".strip()
                else:
                    n["label"] = f"{n.get('label', '')}<br><i>(Fig. {fig_no})</i>"
            for c in n.get("children", []):
                mark(c)
        mark(ov["root"])
        ids = _ids(pnl) - {pnl["id"]}
        mod = {"schema_version": bp.get("schema_version", 1), "figure": dict(copy.deepcopy(bp["figure"]), type="module-detail"),
               "root": {"id": "root", "layout": copy.deepcopy(pnl.get("layout", {"type": "row"})),
                        "children": copy.deepcopy(pnl["children"])},
               "edges": [copy.deepcopy(e) for e in bp.get("edges", []) if e["src"] in ids and e["dst"] in ids]}
        anns = [copy.deepcopy(a) for a in bp.get("annotations", []) or [] if set(a.get("covers", [])) <= ids]
        if anns:
            mod["annotations"] = anns
        parts.append((f"module-{pnl['id']}", mod))
    kept_edges = [e for _, p in parts for e in p.get("edges", [])]
    res["dropped_edges"] = sorted(eid for eid, e in by_id.items() if not any(e == k for k in kept_edges))

    placed_facts: set = set()
    for _, part in parts:  # legend notes follow what each part draws
        notes = part["figure"].get("legend_notes")
        if notes:
            txt = _texts(part)
            part["figure"]["legend_notes"] = [n for n in notes if _note_applies(n, txt)]
    panel_of = {f"module-{p['id']}": p["id"] for p in panels}
    for name, part in parts:
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        pids, eids = _ids(part["root"]), _edge_ids(part)
        def kept(m):
            if m.get("on_edge") is not None:
                return m["on_edge"] in eids
            t = m.get("into")
            return all(x in pids for x in (t if isinstance(t, list) else [t]))
        das = [m for m in plan.get("drawn_as", []) or [] if kept(m)]
        omitted = {o.get("fact") for o in plan.get("omitted", []) or []}
        whole = panel_of.get(name)  # in a module figure the panel is the whole figure: its scope needs no stating
        mine = [f for f in facts if (name == "overview" and f["id"] in omitted)  # left out on purpose: keeps its reason
                or (all(_resolves(x, pids, das, eids) for x in (f["from"], f["to"], *f.get("via", [])))
                    and (not f.get("scope") or f["scope"] in pids or f["scope"] == whole
                         or any(a.get("id") == f["scope"] for a in part.get("annotations", []) or [])))]
        if whole:
            mine = [{k: v for k, v in f.items() if not (k == "scope" and v == whole)} for f in mine]
        placed_facts |= {f["id"] for f in mine}
        fids = {f["id"] for f in mine}
        p = copy.deepcopy(plan) if name == "overview" else {k: copy.deepcopy(plan[k]) for k in ("color_semantics",) if k in plan}
        p["drawn_as"] = das
        p["omitted"] = [o for o in plan.get("omitted", []) or [] if o.get("fact") in fids]
        if name == "overview":
            for m in p.get("mechanism", []) or []:
                if m.get("panel") and m["panel"] not in pids:
                    m.pop("panel")  # its zoom-in is now a figure of its own
            for key in ("core", "train_only", "infer_kept"):
                if isinstance(p.get(key), list):
                    p[key] = [x for x in p[key] if x in pids]
            for kr in p.get("key_representations", []) or []:
                kr["ids"] = [x for x in kr.get("ids", []) if x in pids]
        (d / "blueprint.json").write_text(json.dumps(part, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (d / "facts.json").write_text(json.dumps({"facts": mine}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (d / "figure_plan.json").write_text(json.dumps(p, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        for a in ("analysis.draft.json", "analysis.code.json"):
            if (src.parent / a).is_file():
                (d / a).write_text((src.parent / a).read_text(encoding="utf-8"), encoding="utf-8")
        if name == "overview":
            res["overview"] = str(d / "blueprint.json")
        else:
            res["modules"].append(str(d / "blueprint.json"))
            _fit_width(d / "blueprint.json", style)
    res["dropped_facts"] = sorted(f["id"] for f in facts if f["id"] not in placed_facts)
    return res


def _fit_width(bp_path: Path, style) -> None:
    """A module figure is a column figure when its text holds the floor there; else it keeps the page width."""
    from .lint import MIN_FONT_PT
    from .pipeline import build
    import tempfile
    d = json.loads(bp_path.read_text(encoding="utf-8"))
    if d["figure"].get("width") == "single":
        return
    wide = d["figure"]["width"]
    d["figure"]["width"] = "single"
    bp_path.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            r = build(bp_path, style, None, out_dir=tmp, formats=(), suggest_split=False, quick=True)
            ok = (r.report.stats.get("smallest_text_pt") or 0) >= MIN_FONT_PT
    except Exception:  # noqa: BLE001 — keep the page width when the column build fails
        ok = False
    if not ok:
        d["figure"]["width"] = wide
        bp_path.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
