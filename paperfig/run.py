"""Run directory: one figure job's inputs, artifacts, decisions and rounds (spec §4, plan: reproducible runs).

``check`` is the gate before delivery: every artifact present and validated against its sources, every
confirmation point decided, the last build lint-clean and reviewed by a critic that looked at the PNG."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .errors import PaperFigError

POINTS = ("blueprint", "assets", "style", "delivery")  # the four user confirmation points (spec §4)
REPORT_SECTIONS = ("## Figure", "## References", "## Rounds", "## Open issues", "## Placeholders")
DELIVER_FILES = ("fig.drawio", "fig.png", "fig.pdf", "fig.lint.md")
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
    rec = _read(run_dir)  # in auto mode nobody is asked, but the user may still step in (--by user)
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
    reader = crit.get("reader")
    if (Path(run_dir) / "figure_plan.json").is_file():  # a planned figure is judged by what a reader gets from it
        if not isinstance(reader, dict) or not str(reader.get("takeaway_from_png", "")).strip() \
                or not isinstance(reader.get("top_level_units"), int):
            raise PaperFigError(f"critic report {critic_json} has no reader test (reader.takeaway_from_png, "
                                "reader.top_level_units) — rerun the critic with the current agents/critic.md")
    sev = {"high": 0, "medium": 0, "low": 0}
    for i in crit.get("issues", []):
        sev[i.get("severity", "low")] = sev.get(i.get("severity", "low"), 0) + 1
    rec = _read(run_dir)
    lint_json, critic_json = Path(lint_json).resolve(), Path(critic_json).resolve()  # check --final may run elsewhere
    rec["rounds"].append({"n": int(n), "lint": dict(lint.get("counts", {}), ok=bool(lint.get("ok"))), "lint_file": str(lint_json),
                          "critic": crit.get("scores", {}), "critic_issues": sev, "critic_file": str(critic_json),
                          "reader": reader, "note": note, "at": _now()})
    _write(run_dir, rec)


def _sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _last_build(rec: dict) -> Path | None:
    rounds = rec.get("rounds") or []
    return Path(rounds[-1]["lint_file"]).parent if rounds and rounds[-1].get("lint_file") else None


def deliver(run_dir, out) -> list[Path]:
    """Copy the last round's figure files and the report to ``out`` and record their hashes, so the final
    check can prove the delivered files are the reviewed build."""
    import shutil

    d, out = Path(run_dir), Path(out)
    rec = _read(d)
    build = _last_build(rec)
    if build is None:
        raise PaperFigError("no build round recorded — `paperfig run round` before delivering")
    out.mkdir(parents=True, exist_ok=True)
    copied, files = [], {}
    for name in DELIVER_FILES:
        src = build / name
        if not src.is_file():
            raise PaperFigError(f"last round's {src} is missing")
        shutil.copyfile(src, out / name)
        files[name] = _sha(src)
        copied.append(out / name)
    for extra in ("report.md", "compare.png"):
        for src in (d / extra, out / extra):
            if src.is_file():
                if src.parent != out:
                    shutil.copyfile(src, out / extra)
                copied.append(out / extra)
                break
    rec["delivered"] = {"dir": str(out.resolve()), "round": rec["rounds"][-1]["n"], "files": files, "at": _now()}
    _write(d, rec)
    return copied


def check(run_dir, final: bool = False) -> list[str]:
    from .artifacts import validate

    d = Path(run_dir)
    rec = _read(d)
    probs = [f"run.json has no '{k}' — was it written by `paperfig run init`?" for k in ("inputs", "decisions", "rounds")
             if not isinstance(rec.get(k), (dict, list))]
    rec.setdefault("inputs", {})
    rec["inputs"] = rec["inputs"] if isinstance(rec["inputs"], dict) else {}
    rec["decisions"] = rec.get("decisions") if isinstance(rec.get("decisions"), list) else []
    rec["rounds"] = rec.get("rounds") if isinstance(rec.get("rounds"), list) else []

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
    if rec["inputs"].get("draft") or rec["inputs"].get("code"):
        val("figure-plan", "figure_plan.json", facts=d / "facts.json" if (d / "facts.json").is_file() else None,
            refs=d / "refs" / "refs.json" if (d / "refs" / "refs.json").is_file() else None,
            blueprint=d / "blueprint.json" if (d / "blueprint.json").is_file() else None)
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
    need("brief.md")
    if need("report.md"):
        rep = (d / "report.md").read_text(encoding="utf-8", errors="replace")
        want = REPORT_SECTIONS + (("## Omitted",) if (d / "figure_plan.json").is_file() else ())
        miss = [h for h in want if h.lower() not in rep.lower()]
        if miss:
            probs.append(f"report.md lacks section(s): {', '.join(miss)}")
    have = {x["point"] for x in rec["decisions"]}
    for p in POINTS if final else POINTS[:-1]:
        if p not in have:
            probs.append(f"no decision 'paperfig run decide --point {p}' recorded (decision '{p}')")
    if final:
        dl = rec.get("delivered")
        build = _last_build(rec)
        if not dl:
            probs.append("nothing delivered — `paperfig run deliver RUN --out OUT`")
        elif build is not None:
            if dl.get("round") != rec["rounds"][-1]["n"]:
                probs.append(f"delivered round {dl.get('round')} is not the last round {rec['rounds'][-1]['n']}")
            for name, h in dl.get("files", {}).items():
                copy = Path(dl["dir"]) / name
                if not copy.is_file() or _sha(copy) != h or not (build / name).is_file() or _sha(build / name) != h:
                    probs.append(f"delivered {name} is not the last round's build (missing or changed)")
    return probs
