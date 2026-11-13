"""Faithfulness gate: facts from the paper/code, written independently of the blueprint, must each be
represented by a directed path in the blueprint (spec G5; lesson from the BLIP-2 round-1 figure, where
figure-vs-blueprint checks all passed while the blueprint itself had misread the method).

A fact `from -> to` is covered when some element in {from} ∪ descendants(from) reaches
{to} ∪ descendants(to) through blueprint edges; reaching a container counts as reaching everything in it.
With `scope`, every element on the path must lie inside that group (or annotation's covered set).
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


def _descendants(bp: Blueprint, eid: str) -> set[str]:
    out, stack = set(), [eid]
    while stack:
        el = bp.index[stack.pop()]
        if el.is_group:
            for c in el.children:
                out.add(c.id)
                stack.append(c.id)
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
    ok = (lambda x: True) if allowed is None else (lambda x: x in allowed)
    if src == dst:  # only through drawn_as: both ends drawn as the same element
        return [src] if ok(src) else None
    goals = {dst} | _descendants(bp, dst)
    starts = [x for x in [src, *sorted(_descendants(bp, src))] if ok(x)]
    if direct:
        for a in starts:
            for b in adj.get(a, []):
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
        for n in adj.get(cur, []):
            if not ok(n):
                continue
            if n not in parent:
                parent[n] = cur
                q.append(n)
            if n in goals:
                return trace(n)
            if bp.index[n].is_group:
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
    into, on_edge = into or {}, on_edge or {}
    kinds = FLOW_KINDS | set(f.get("kinds", []))
    stops = [f["from"], *f.get("via", []), f["to"]]
    full: list[str] = []
    for a, b in zip(stops, stops[1:]):
        if a in on_edge and b in on_edge and on_edge[a] is on_edge[b]:  # both on one labelled arrow
            e = on_edge[a]
            seg = [e.src, e.dst]
        else:
            seg = None
            for s_ in _ends(a, "from", into, on_edge):
                for d_ in _ends(b, "to", into, on_edge):
                    seg = _search(bp, s_, d_, allowed, kinds, direct=bool(f.get("direct")) and len(stops) == 2)
                    if seg is not None:
                        break
                if seg is not None:
                    break
        if seg is None:
            return None
        full += seg if not full or full[-1] != seg[0] else seg[1:]
    return full


def check_facts(bp: Blueprint, facts: list[dict], annotations: dict | None = None, drawn_as=None) -> list[Finding]:
    annotations = annotations or {}
    into, on_edge = drawn_as_maps(bp, drawn_as)
    out = []
    for f in facts:
        fid, a, b, scope = f.get("id", ""), f["from"], f["to"], f.get("scope")
        what = f"{a} -> {b}" + (f" within '{scope}'" if scope else "")
        cite = f"{f.get('ref', '')}: “{f.get('quote', '')}”"
        if f.get("waive"):
            out.append(Finding("fact-waived", "info", [fid], f"{what} not drawn — waived: {f['waive']} ({cite})"))
            continue
        unknown = [x for x in (a, b, *f.get("via", [])) if x not in bp.index and not into.get(x) and x not in on_edge]
        if scope and scope not in bp.index and scope not in annotations:
            unknown.append(scope)
        if unknown:
            out.append(Finding("fact-unknown-id", "error", [fid], f"fact {what}: ids not in the blueprint: {', '.join(unknown)} ({cite})"))
            continue
        allowed = _scope_members(bp, scope, annotations) if scope else None
        path = _path(bp, f, allowed, into, on_edge)
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
