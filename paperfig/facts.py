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
                    if c in has_in or not ok(c):
                        continue
                    if c not in parent:
                        parent[c] = n
                        q.append(c)
                    if c in goals:
                        return trace(c)
    return None


def _path(bp, f, allowed):
    kinds = FLOW_KINDS | set(f.get("kinds", []))
    stops = [f["from"], *f.get("via", []), f["to"]]
    full: list[str] = []
    for a, b in zip(stops, stops[1:]):
        seg = _search(bp, a, b, allowed, kinds, direct=bool(f.get("direct")) and len(stops) == 2)
        if seg is None:
            return None
        full += seg if not full else seg[1:]
    return full


def check_facts(bp: Blueprint, facts: list[dict], annotations: dict | None = None) -> list[Finding]:
    annotations = annotations or {}
    out = []
    for f in facts:
        fid, a, b, scope = f.get("id", ""), f["from"], f["to"], f.get("scope")
        what = f"{a} -> {b}" + (f" within '{scope}'" if scope else "")
        cite = f"{f.get('ref', '')}: “{f.get('quote', '')}”"
        if f.get("waive"):
            out.append(Finding("fact-waived", "info", [fid], f"{what} not drawn — waived: {f['waive']} ({cite})"))
            continue
        unknown = [x for x in (a, b, *f.get("via", [])) if x not in bp.index]
        if scope and scope not in bp.index and scope not in annotations:
            unknown.append(scope)
        if unknown:
            out.append(Finding("fact-unknown-id", "error", [fid], f"fact {what}: ids not in the blueprint: {', '.join(unknown)} ({cite})"))
            continue
        allowed = _scope_members(bp, scope, annotations) if scope else None
        path = _path(bp, f, allowed)
        if path is not None:
            out.append(Finding("fact-covered", "info", [fid], f"{what}: {' → '.join(path)}"))
            continue
        if scope and _path(bp, f, None) is not None:
            out.append(Finding("fact-out-of-scope", "error", [fid, a, b],
                               f"{what}: a path exists but leaves '{scope}' — the stage/panel does not show this flow ({cite})"))
        else:
            how = (" via " + ", ".join(f["via"])) if f.get("via") else (" as a direct edge" if f.get("direct") else "")
            out.append(Finding("fact-missing", "error", [fid, a, b], f"the paper says {what}{how}, but the blueprint has no such data-flow path ({cite})"))
    return out
