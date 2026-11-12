"""Figure plan (round 2): what the figure tells the reader, and which stated facts it deliberately leaves out.
Only the plan may omit a fact; an omitted fact is reported (info), any other missing fact stays an error."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import PaperFigError
from .lint import Finding

GATE_CODES = ("fact-missing", "fact-out-of-scope", "fact-unknown-id")


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
        else:
            out.append(f)
    return out
