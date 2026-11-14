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
    s = re.sub(r"</?(sub|sup|i|b)>", "", str(s or ""), flags=re.I)  # ε<sub>θ</sub> is the one symbol εθ
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip().lower()


def check_against_analysis(bp, draft: dict | None, code: dict | None, plan: dict | None = None) -> list[Finding]:
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
        brackets = [a.label for a in getattr(bp, "annotations", []) if el.is_group and cid in a.covers]
        drawn = " ".join(_plain(x) for x in (getattr(el, "label", None), getattr(el, "title", None), el.full_name, el.abbrev,
                                             *brackets))
        names = [n for n in (c.get("abbrev"), c.get("name")) if n]
        if names and not any(_tokens(n) <= _tokens(drawn) for n in names):
            out.append(Finding("proposed-name", "warn", [cid], f"'{cid}' should carry the paper's name "
                               f"({' / '.join(names)}); the drawing says: {drawn[:80]!r}"))

    flows = [(e.get("from"), e.get("to")) for a in (draft or {}, code or {}) for e in a.get("data_flow", [])]
    if not flows:
        return out
    for m in (plan or {}).get("drawn_as", []) or []:  # components drawn as part of something else
        ids = set(m.get("ids", []))
        if m.get("into"):
            tg = m["into"] if isinstance(m["into"], list) else [m["into"]]
            flows = [(tg[0] if a in ids else a, tg[0] if b in ids else b) for a, b in flows] + \
                    [(a, t) for a, b in flows if b in ids for t in tg] + [(t, b) for a, b in flows if a in ids for t in tg]
        else:  # on an edge: a -> c -> b is the drawn a -> b
            flows = flows + [(a, b2) for a, c in flows if c in ids for c2, b2 in flows if c2 == c]

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
    return check_against_analysis(bp, draft, code, load("figure_plan.json"))
