"""Faithfulness gate: facts from the paper/code, written independently of the blueprint, must each be
represented by a directed path in the blueprint (spec G5; lesson from the BLIP-2 round-1 figure, where
figure-vs-blueprint checks all passed while the blueprint itself had misread the method).

A fact `from -> to` is covered when some element in {from} ∪ descendants(from) reaches
{to} ∪ descendants(to) through blueprint edges; reaching a container counts as reaching everything in it, and a
member with no outgoing edge of its own leaves through its container's edges. In a loop everything reaches
everything, so a path that goes around the loop while the figure draws the opposite arrow is `fact-reversed`.
With `scope`, every element on the path must lie inside that group (or annotation's covered set).
A component drawn several times is reached at any copy, but each step of the path starts from the copy the step before
reached — the path is one chain of drawn arrows, never a jump between copies.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from .blueprint import Blueprint
from .errors import BlueprintError
from .lint import Finding


def load_facts(path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BlueprintError([f"facts file {path}: {e}"])
    facts = data.get("facts") if isinstance(data, dict) else None
    probs = []
    if not isinstance(facts, list):
        raise BlueprintError([f"facts file {path}: expected {{\"facts\": [...]}}"])
    for i, f in enumerate(facts):
        for k in ("from", "to", "quote", "ref"):
            if not isinstance(f, dict) or not isinstance(f.get(k), str) or not f.get(k):
                probs.append(f"facts[{i}]: missing '{k}' (each fact needs from, to, quote, ref)")
    if probs:
        raise BlueprintError(probs)
    for i, f in enumerate(facts):
        f.setdefault("id", f"fact{i}")
    return facts


def _panels(bp: Blueprint) -> dict[str, str]:
    """{overview node: its detail panel} — a panel's contents are the inside of the node it zooms into (ISTA-Net
    blind run: facts from the phase row into the opened phase could not pass, so the runner rewrote the facts)."""
    return {g.detail_of: g.id for g in bp.groups() if getattr(g, "detail_of", None) and g.detail_of in bp.index}


def _descendants(bp: Blueprint, eid: str) -> set[str]:
    panels = _panels(bp)
    out, stack, seen = set(), [eid], {eid}
    while stack:
        cur = stack.pop()
        el = bp.index[cur]
        kids = [c.id for c in el.children] if el.is_group else []
        if cur in panels:
            kids.append(panels[cur])
        for c in kids:
            if c not in seen:
                seen.add(c)
                out.add(c)
                stack.append(c)
    return out


def _scope_members(bp: Blueprint, scope: str, annotations: dict) -> set[str] | None:
    if scope in bp.index:
        return {scope} | _descendants(bp, scope)
    if scope in annotations:
        members = set()
        for c in annotations[scope]:
            members |= {c} | _descendants(bp, c)
        return members
    return None


FLOW_KINDS = {"data", "skip", "train_only", "infer_only"}  # gradients / losses / control are not data flow


def _search(bp: Blueprint, src: str, dst: str, allowed: set[str] | None, kinds: set[str], direct: bool = False):
    """Shortest directed path (list of ids) from src (or anything inside it) to dst (or anything inside it).
    Entering a container reaches its contents as goals, but the search continues only through the
    container's own outgoing edges and its entry points (children with no incoming data edge): a
    container is not a hub that connects unrelated children."""
    adj: dict[str, list[str]] = {}
    has_in: set[str] = set()
    for e in bp.edges:
        if e.kind in kinds:
            adj.setdefault(e.src, []).append(e.dst)
            has_in.add(e.dst)

    opened = _panels(bp)
    zoom = {v: k for k, v in opened.items()}  # detail panel -> the node it opens

    def out_of(x):
        """x's own edges; a member with none (an exit point) also leaves through its containers' edges — and a detail
        panel through the node it opens."""
        nb = list(adj.get(x, []))
        seen = {x}
        while not adj.get(x):
            if x in zoom:
                x = zoom[x]
            elif bp.parent.get(x) is not None:
                p = bp.parent[x]
                x = p.id if hasattr(p, "id") else p
            else:
                break
            if x in seen:
                break
            seen.add(x)
            nb += adj.get(x, [])
        return nb
    ok = (lambda x: True) if allowed is None else (lambda x: x in allowed)
    if src == dst:  # only through drawn_as: both ends drawn as the same element
        return [src] if ok(src) else None
    goals = {dst} | _descendants(bp, dst)
    starts = [x for x in [src, *sorted(_descendants(bp, src))] if ok(x)]
    if direct:
        for a in starts:
            for b in out_of(a):
                if b in goals:
                    return [a, b]
        return None
    parent: dict[str, str | None] = {x: None for x in starts}

    def trace(m):
        path = []
        while m is not None:
            path.append(m)
            m = parent[m]
        return list(reversed(path))

    q = deque(starts)
    while q:
        cur = q.popleft()
        for n in out_of(cur):
            if not ok(n):
                continue
            if n not in parent:
                parent[n] = cur
                q.append(n)
            if n in goals:
                return trace(n)
            if bp.index[n].is_group or n in opened:  # a node with a detail panel is entered like a container
                for c in sorted(_descendants(bp, n)):
                    if not ok(c):
                        continue
                    if c in goals:  # reaching a container reaches everything in it
                        if c not in parent:
                            parent[c] = n
                        return trace(c)
                    if c in has_in:  # ...but the flow continues only through its entry points
                        continue
                    if c not in parent:
                        parent[c] = n
                        q.append(c)
    return None


def drawn_as_maps(bp: Blueprint, drawn_as) -> tuple[dict[str, list[str]], dict]:
    """The plan's `drawn_as`: paper components the figure draws as part of another element. `into` = one node (or
    several copies, e.g. one per timestep); `on_edge` = a label on that edge (an embedding `E` on an arrow)."""
    into: dict[str, list[str]] = {}
    on_edge: dict = {}
    edges = {e.id: e for e in bp.edges}
    for m in drawn_as or []:
        if m.get("on_edge") is not None:
            if m["on_edge"] in edges:
                for i in m["ids"]:
                    on_edge[i] = edges[m["on_edge"]]
        else:
            t = m.get("into")
            for i in m["ids"]:
                into[i] = [x for x in (t if isinstance(t, list) else [t]) if x in bp.index]
    return into, on_edge


def _ends(x, role, into, on_edge) -> list[str]:
    """Blueprint elements standing for component x as a path's start ('from') or end ('to')."""
    if x in on_edge:  # on an edge s -> d: it is reached when s is, and it reaches what d reaches
        e = on_edge[x]
        return [e.dst if role == "from" else e.src]
    return into.get(x) or [x]


def _path(bp, f, allowed, into=None, on_edge=None):
    """The fact's path through its stops, or None. A component drawn several times (`drawn_as` copies) may be reached
    at any copy, but the next step starts from the copy reached: the path is one chain of drawn arrows."""
    into, on_edge = into or {}, on_edge or {}
    kinds = FLOW_KINDS | set(f.get("kinds", []))
    stops = [f["from"], *f.get("via", []), f["to"]]
    direct = bool(f.get("direct")) and len(stops) == 2

    def join(p, seg):
        return seg if not p else p + (seg[1:] if p[-1] == seg[0] else seg)

    def next_starts(b, path, reached):
        """Where the step after stop b starts: the copy just reached (CaseLIP v5: each step once picked its own copy,
        joining arrows that do not meet), or past the arrow b is drawn on."""
        if b in on_edge:
            e = on_edge[b]
            return {e.dst: join(path, [e.src, e.dst])}
        return {reached: path}

    # {element the next step starts from: the shortest path so far}
    states: dict[str, list[str]] = {x: [] for x in _ends(stops[0], "from", into, on_edge)}
    for i, (a, b) in enumerate(zip(stops, stops[1:])):
        if not states:
            return None
        fixed = None
        if a in on_edge and b in on_edge and on_edge[a] is on_edge[b]:  # both on one labelled arrow
            fixed = [on_edge[a].src, on_edge[a].dst]
        elif a in on_edge and any(on_edge[a].dst == d or on_edge[a].dst in _descendants(bp, d)
                                  for d in _ends(b, "to", into, on_edge) if d in bp.index):
            fixed = [on_edge[a].src, on_edge[a].dst]  # drawn on the arrow that enters its target (or a member of it)
        new: dict[str, list[str]] = {}

        def keep(key, path):
            if key not in new or len(path) < len(new[key]):
                new[key] = path
        if fixed is not None:
            best = min(states.values(), key=len)
            crossed_it = best[-len(fixed):] == fixed  # the step before already continued past this arrow
            for k in _ends(b, "from", into, on_edge):
                keep(k, best if crossed_it else join(best, fixed))
        else:  # every copy pair (a component drawn once per time step): the shortest path wins
            for s_, so_far in states.items():
                if s_ not in bp.index:
                    continue
                for d_ in _ends(b, "to", into, on_edge):
                    if d_ not in bp.index:
                        continue
                    cand = _search(bp, s_, d_, allowed, kinds, direct=direct)
                    if cand is None:
                        continue
                    last = i == len(stops) - 2
                    for k, pth in ({d_: join(so_far, cand)} if last else next_starts(b, join(so_far, cand), d_)).items():
                        keep(k, pth)
        states = new
    return min(states.values(), key=len) if states else None


def check_facts(bp: Blueprint, facts: list[dict], annotations: dict | None = None, drawn_as=None) -> list[Finding]:
    annotations = annotations or {}
    into, on_edge = drawn_as_maps(bp, drawn_as)
    out = []
    for f in facts:
        fid, a, b, scope = f.get("id", ""), f["from"], f["to"], f.get("scope")
        what = f"{a} -> {b}" + (f" within '{scope}'" if scope else "")
        cite = f"{f.get('ref', '')}: “{f.get('quote', '')}”"
        if f.get("waive"):
            out.append(Finding("fact-waived", "warn", [fid], f"{what} not drawn — waived: {f['waive']} ({cite}); "
                               "a fact is left out through the plan's omitted list, shown to the user"))
            continue
        unknown = [x for x in (a, b, *f.get("via", [])) if x not in bp.index and not into.get(x) and x not in on_edge]
        if scope and scope not in bp.index and scope not in annotations:
            unknown.append(scope)
        if unknown:
            out.append(Finding("fact-unknown-id", "error", [fid], f"fact {what}: ids not in the blueprint: {', '.join(unknown)} ({cite})"))
            continue
        allowed = _scope_members(bp, scope, annotations) if scope else None
        path = _path(bp, f, allowed, into, on_edge)
        if path is not None and len(path) > 2 and not f.get("via") and \
                _path(bp, {"from": b, "to": a, "direct": True, "kinds": f.get("kinds", [])}, None, into, on_edge):
            out.append(Finding("fact-reversed", "error", [fid, a, b], f"the paper says {a} -> {b}, but the figure draws "
                               f"the opposite arrow {b} -> {a}; {a} reaches {b} only around a loop "
                               f"({' → '.join(path)}), which a reader does not read as this flow — draw it, or leave it "
                               f"out through the plan ({cite})"))
            continue
        if path is not None:
            out.append(Finding("fact-covered", "info", [fid], f"{what}: {' → '.join(path)}"))
            continue
        if scope and _path(bp, f, None, into, on_edge) is not None:
            out.append(Finding("fact-out-of-scope", "error", [fid, a, b],
                               f"{what}: a path exists but leaves '{scope}' — the stage/panel does not show this flow ({cite})"))
        else:
            how = (" via " + ", ".join(f["via"])) if f.get("via") else (" as a direct edge" if f.get("direct") else "")
            out.append(Finding("fact-missing", "error", [fid, a, b], f"the paper says {what}{how}, but the blueprint has no such data-flow path ({cite})"))
    return out
