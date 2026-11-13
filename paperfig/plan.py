"""Figure plan (round 2): what the figure tells the reader, and which stated facts it deliberately leaves out.
Only the plan may omit a fact; an omitted fact is reported (info), any other missing fact stays an error."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import PaperFigError
from .lint import Finding

GATE_CODES = ("fact-missing", "fact-out-of-scope", "fact-unknown-id", "fact-reversed")


def load_plan(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"figure plan {path}: {e}") from e


def apply_plan(findings: list, plan: dict | None) -> list:
    if not plan:
        return findings
    omitted = {o["fact"]: o for o in plan.get("omitted", []) if isinstance(o, dict) and o.get("fact")}
    out = []
    for f in findings:
        fid = f.ids[0] if f.ids else None
        if f.code in GATE_CODES and fid in omitted:
            o = omitted[fid]
            out.append(Finding("fact-omitted", "info", [fid], f"not drawn by plan ({o['where']}): {o['reason']}"))
        elif f.code == "fact-covered" and fid in omitted:  # the plan and the figure disagree: one of them is wrong
            out.append(f)
            out.append(Finding("fact-omitted-drawn", "warn", [fid], f"the plan lists {fid} as left out, but the figure "
                               f"draws it ({f.message}) — drop it from omitted, or check the path really shows this flow"))
        else:
            out.append(f)
    n = sum(1 for f in out if f.code.startswith("fact-"))
    n_omit = sum(1 for f in out if f.code in ("fact-omitted", "fact-waived"))  # waived = left out too
    if n and n_omit == n:  # the gate would verify nothing: the main line must be checked
        out.append(Finding("facts-all-omitted", "error", [], f"the plan leaves out all {n} stated facts, so nothing the "
                           "figure draws is checked against the paper — keep the main line's facts, and map components "
                           "drawn as an edge label or merged into one box with the plan's drawn_as"))
    elif n and n_omit * 2 > n:
        out.append(Finding("fact-omitted-majority", "warn", [], f"the plan leaves out {n_omit} of {n} stated facts — are "
                           "they really details? Components drawn as an edge label or merged into one box belong in "
                           "drawn_as, not omitted"))
    return out
