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


def _reaches(bp: Blueprint, src: str, dst: str, allowed: set[str] | None) -> bool:
    adj: dict[str, list[str]] = {}
    for e in bp.edges:
        adj.setdefault(e.src, []).append(e.dst)
    starts = {src} | _descendants(bp, src)
    goals = {dst} | _descendants(bp, dst)
    if allowed is not None:
        starts &= allowed
    seen, q = set(starts), deque(starts)
    while q:
        cur = q.popleft()
        nxt = list(adj.get(cur, []))
        for n in list(nxt):
            nxt.extend(_descendants(bp, n))  # entering a container reaches its contents
        for n in nxt:
            if n in goals:
                if allowed is None or n in allowed:
                    return True
            if n not in seen and (allowed is None or n in allowed):
                seen.add(n)
                q.append(n)
    return False


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
        unknown = [x for x in (a, b) if x not in bp.index]
        if scope and scope not in bp.index and scope not in annotations:
            unknown.append(scope)
        if unknown:
            out.append(Finding("fact-unknown-id", "error", [fid], f"fact {what}: ids not in the blueprint: {', '.join(unknown)} ({cite})"))
            continue
        allowed = _scope_members(bp, scope, annotations) if scope else None
        if _reaches(bp, a, b, allowed):
            continue
        if scope and _reaches(bp, a, b, None):
            out.append(Finding("fact-out-of-scope", "error", [fid, a, b],
                               f"{what}: a path exists but leaves '{scope}' — the stage/panel does not show this flow ({cite})"))
        else:
            out.append(Finding("fact-missing", "error", [fid, a, b], f"the paper says {what}, but the blueprint has no such path ({cite})"))
    return out
