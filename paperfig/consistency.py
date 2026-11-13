"""The blueprint against the analyses (round-4 review): the facts gate checks that stated connections are drawn;
this checks the other direction — a proposed module keeps its role and its paper name, and a drawn data edge
between two analysed components is one the analyses state (directly, or between a group and its members)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .lint import Finding

FLOW = ("data", "skip", "train_only", "infer_only")
GENERIC = {"the", "a", "an", "of", "for", "layer", "layers", "module", "block", "network", "net", "unit", "operation"}


def _tokens(s) -> set:
    """Key words of a name: alphanumeric runs, generic words dropped, plural 's' trimmed (features ~ feature)."""
    words = re.findall(r"[0-9a-zα-ωθ]+", _plain(s).replace("-", " "))
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in GENERIC}


def _plain(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(s or ""))).strip().lower()


def check_against_analysis(bp, draft: dict | None, code: dict | None) -> list[Finding]:
    out: list[Finding] = []
    comps = {}
    for a in (draft or {}, code or {}):
        for c in a.get("components", []):
            comps.setdefault(c.get("id"), c)
    for cid, c in comps.items():
        if c.get("role") != "proposed" or cid not in bp.index:
            continue
        el = bp.index[cid]
        if el.role != "proposed":
            out.append(Finding("proposed-mismatch", "error", [cid], f"'{cid}' is proposed in the analysis but drawn "
                               f"as '{el.role}' — the paper's contribution must read as the contribution"))
            continue
        drawn = " ".join(_plain(x) for x in (getattr(el, "label", None), getattr(el, "title", None), el.full_name, el.abbrev))
        names = [n for n in (c.get("abbrev"), c.get("name")) if n]
        if names and not any(_tokens(n) <= _tokens(drawn) for n in names):
            out.append(Finding("proposed-name", "warn", [cid], f"'{cid}' should carry the paper's name "
                               f"({' / '.join(names)}); the drawing says: {drawn[:80]!r}"))

    flows = [(e.get("from"), e.get("to")) for a in (draft or {}, code or {}) for e in a.get("data_flow", [])]
    if not flows:
        return out

    def family(x):
        fam = {x}
        stack = [x]
        while stack:  # members
            el = bp.index.get(stack.pop())
            for ch in getattr(el, "children", []) or []:
                fam.add(ch.id)
                stack.append(ch.id)
        p = bp.parent.get(x)
        while p is not None:  # containers
            fam.add(p.id if hasattr(p, "id") else p)
            p = bp.parent.get(p.id if hasattr(p, "id") else p)
        return fam

    for e in bp.edges:
        if e.kind not in FLOW or e.src not in comps or e.dst not in comps:
            continue
        fs, fd = family(e.src), family(e.dst)
        if not any(a in fs and b in fd for a, b in flows):
            out.append(Finding("edge-unstated", "warn", [e.src, e.dst], f"the figure draws {e.src} → {e.dst}, but "
                               "neither analysis states that flow — check it against the paper (or add it to the "
                               "analysis with its quote)"))
    return out


def check_run_dir(bp, bp_dir: Path) -> list[Finding]:
    def load(name):
        p = Path(bp_dir) / name
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
        except (OSError, ValueError):
            return None
    draft, code = load("analysis.draft.json"), load("analysis.code.json")
    if draft is None and code is None:
        return []
    return check_against_analysis(bp, draft, code)
