"""Run directory: one figure job's inputs, artifacts, decisions and rounds (spec §4, plan: reproducible runs).

``check`` is the gate before delivery: every artifact present and validated against its sources, every
confirmation point decided, the last build lint-clean and reviewed by a critic that looked at the PNG."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .errors import PaperFigError

POINTS = ("blueprint", "assets", "style", "delivery")  # the four user confirmation points (spec §4)
SUBDIRS = ("inputs", "assets", "refs", "samples", "build", "critic")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _read(d: Path) -> dict:
    p = Path(d) / "run.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PaperFigError(f"{d} is not a run directory (no run.json) — start with `paperfig run init`") from None
    except ValueError as e:
        raise PaperFigError(f"{p}: unreadable ({e})") from e


def _write(d: Path, rec: dict) -> None:
    p = Path(d) / "run.json"
    tmp = p.with_suffix(".part")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def init(run_dir, mode: str, figure_type: str, venue: str | None = None, draft: str | None = None, code: str | None = None,
         paper_title: str | None = None, arxiv_id: str | None = None, focus: str | None = None, model: str | None = None) -> Path:
    from .kb import REPO_KB, kb_version

    if mode not in ("interactive", "auto"):
        raise PaperFigError(f"mode must be interactive or auto, got {mode!r}")
    if figure_type not in ("overview", "teaser", "module-detail"):
        raise PaperFigError(f"figure type must be overview, teaser or module-detail, got {figure_type!r}")
    d = Path(run_dir)
    if (d / "run.json").exists():
        raise PaperFigError(f"{d} already holds a run (run.json exists) — use a new directory")
    if not draft and not code:
        raise PaperFigError("a run needs a draft or code (or both)")
    for s in SUBDIRS:
        (d / s).mkdir(parents=True, exist_ok=True)
    ab = lambda p: str(Path(p).expanduser().resolve()) if p else None  # noqa: E731
    _write(d, {"created": _now(), "mode": mode, "model": model, "kb_version": kb_version(REPO_KB),
               "paper": {"title": paper_title, "arxiv_id": arxiv_id},
               "figure": {"type": figure_type, "venue": venue, "focus": focus},
               "inputs": {"draft": ab(draft), "code": ab(code)}, "decisions": [], "rounds": []})
    return d


def decide(run_dir, point: str, decision: str, by: str, why: str) -> None:
    if point not in POINTS:
        raise PaperFigError(f"unknown confirmation point {point!r} (one of: {', '.join(POINTS)})")
    if by not in ("user", "auto"):
        raise PaperFigError(f"by must be user or auto, got {by!r}")
    rec = _read(run_dir)
    if rec["mode"] == "auto" and by != "auto":
        raise PaperFigError("this run is in auto mode: decisions are recorded with --by auto (nobody was asked)")
    if not decision.strip() or not why.strip():
        raise PaperFigError("a decision needs both the decision and the reason")
    rec["decisions"].append({"point": point, "decision": decision, "by": by, "why": why, "at": _now()})
    _write(run_dir, rec)


def record_round(run_dir, n: int, lint_json, critic_json, note: str = "") -> None:
    try:
        lint = json.loads(Path(lint_json).read_text(encoding="utf-8"))
        crit = json.loads(Path(critic_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"cannot read round {n} files: {e}") from e
    if crit.get("viewed_png") is not True:
        raise PaperFigError(f"critic report {critic_json} does not confirm it viewed the PNG — rerun the critic")
    sev = {"high": 0, "medium": 0, "low": 0}
    for i in crit.get("issues", []):
        sev[i.get("severity", "low")] = sev.get(i.get("severity", "low"), 0) + 1
    rec = _read(run_dir)
    rec["rounds"].append({"n": int(n), "lint": dict(lint.get("counts", {}), ok=bool(lint.get("ok"))), "lint_file": str(lint_json),
                          "critic": crit.get("scores", {}), "critic_issues": sev, "critic_file": str(critic_json),
                          "note": note, "at": _now()})
    _write(run_dir, rec)


def check(run_dir) -> list[str]:
    from .artifacts import validate

    d = Path(run_dir)
    rec = _read(d)
    probs = []

    def need(rel):
        if not (d / rel).is_file():
            probs.append(f"missing {rel}")
            return False
        return True

    def val(kind, rel, **kw):
        if need(rel):
            probs.extend(f"{rel}: {p}" for p in validate(kind, d / rel, **kw))

    if rec["inputs"].get("draft"):
        if need("inputs/method.txt"):
            val("draft-analysis", "analysis.draft.json", text=d / "inputs" / "method.txt")
            val("facts", "facts.json", text=d / "inputs" / "method.txt", analysis=d / "analysis.draft.json")
    if rec["inputs"].get("code"):
        val("code-analysis", "analysis.code.json", repo=rec["inputs"]["code"])
    val("blueprint", "blueprint.json")
    if need("brief.json"):
        try:
            json.loads((d / "brief.json").read_text(encoding="utf-8"))
        except ValueError as e:
            probs.append(f"brief.json: unreadable ({e})")
    if need("refs/refs.json"):
        probs.extend(f"refs/refs.json: {p}" for p in validate("refs", d / "refs" / "refs.json"))
        try:
            r = json.loads((d / "refs" / "refs.json").read_text(encoding="utf-8"))
            if not r.get("selected") and not r.get("notes"):
                probs.append("refs/refs.json: no reference selected and no note saying why")
        except ValueError:
            pass
    if need("samples/samples.json"):
        try:
            if not json.loads((d / "samples" / "samples.json").read_text(encoding="utf-8")).get("shown"):
                probs.append("samples/samples.json: no style sample was shown")
        except ValueError as e:
            probs.append(f"samples/samples.json: unreadable ({e})")
    if not rec["rounds"]:
        probs.append("no build round recorded (paperfig run round)")
    else:
        last = rec["rounds"][-1]
        if last["lint"].get("error", 1) or not last["lint"].get("ok"):
            probs.append(f"final round {last['n']} still has lint errors — errors block delivery")
    need("report.md")
    have = {x["point"] for x in rec["decisions"]}
    for p in POINTS:
        if p not in have:
            probs.append(f"no decision 'paperfig run decide --point {p}' recorded (decision '{p}')")
    return probs
