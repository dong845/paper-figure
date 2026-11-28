"""Run directory: one figure job's inputs, artifacts, decisions and rounds (spec §4, plan: reproducible runs).

``check`` is the gate before delivery: every artifact present and validated against its sources, every
confirmation point decided, the last build lint-clean and reviewed by a critic that looked at the PNG."""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .errors import PaperFigError

# the user confirmation points (spec §4); `references` (user, 2026-11-25): the user picks the figures to follow before
# the plan, so the costly steps follow a look they chose, not one guessed for them
POINTS = ("references", "blueprint", "assets", "style", "delivery")
REPORT_SECTIONS = ("## Figure", "## References", "## Rounds", "## Open issues", "## Placeholders")
DELIVER_FILES = ("fig.drawio", "fig.png", "fig.pdf", "fig.lint.md")
DELIVER_OPTIONAL = ("fig.svg", "fig.blueprint.json")  # delivered when the round built it (the blueprint: rebuild or
# absorb hand edits without the run cache)
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
         paper_title: str | None = None, arxiv_id: str | None = None, focus: str | None = None, model: str | None = None,
         page_share: float | None = None) -> Path:
    from .kb import REPO_KB, kb_version

    if mode not in ("interactive", "auto"):
        raise PaperFigError(f"mode must be interactive or auto, got {mode!r}")
    if figure_type not in ("overview", "teaser", "module-detail"):
        raise PaperFigError(f"figure type must be overview, teaser or module-detail, got {figure_type!r}")
    if page_share is not None and not 0.1 <= page_share <= 1.0:
        raise PaperFigError(f"page share is the fraction of the page height the figure may take (0.1-1), got {page_share}")
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
               "figure": {"type": figure_type, "venue": venue, "focus": focus, "page_share": page_share},
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


def record_round(run_dir, n: int, lint_json, critic_json, note: str = "", critic_of: int | None = None,
                 by_user: bool = False) -> None:
    """One build round. A critic reviews a build once; the next build may apply that review's issues without a
    second critic (`critic_of` = the reviewed round) — the user asked for fewer critic rounds (2026-11-13). A user's
    revision (`by_user`) is recorded after any round without a critic; the note says what the user asked."""
    if critic_json is None and by_user:
        return _record_user_round(run_dir, n, lint_json, note)
    if critic_json is None:
        return _record_fix_round(run_dir, n, lint_json, note, critic_of)
    try:
        lint = json.loads(Path(lint_json).read_text(encoding="utf-8"))
        crit = json.loads(Path(critic_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"cannot read round {n} files: {e}") from e
    if crit.get("viewed_png") is not True:
        raise PaperFigError(f"critic report {critic_json} does not confirm it viewed the PNG — rerun the critic")
    reader = crit.get("reader")
    if isinstance(reader, dict) and "caption_free" not in reader and isinstance(reader.get("levels"), dict) \
            and "caption_free" in reader["levels"]:  # critics also nest it under levels; read it where they put it
        reader = dict(reader, caption_free=reader["levels"]["caption_free"])
    plan_file = Path(run_dir) / "figure_plan.json"
    if plan_file.is_file():  # a planned figure is judged by what a reader gets from it
        if not isinstance(reader, dict) or not str(reader.get("takeaway_from_png", "")).strip() \
                or not isinstance(reader.get("top_level_units"), int):
            raise PaperFigError(f"critic report {critic_json} has no reader test (reader.takeaway_from_png, "
                                "reader.top_level_units) — rerun the reviewer (STAGE=figure) with the current agents/reviewer.md")
        try:
            v2 = json.loads(plan_file.read_text(encoding="utf-8")).get("brief_version") == 2
        except (OSError, ValueError):
            v2 = False
        lv = reader.get("levels")
        if v2 and (not isinstance(lv, dict) or not all(str(lv.get(k, "")).strip() for k in ("glance", "contribution", "mechanism"))
                   or not isinstance(reader.get("caption_free"), bool)):
            raise PaperFigError(f"critic report {critic_json} lacks the three reading levels (reader.levels.glance / "
                                ".contribution / .mechanism) or reader.caption_free — a v2 brief is judged at 5 s, "
                                "30 s and 2 min")
    ids = [str(i.get("id") or "").strip() for i in crit.get("issues", []) if isinstance(i, dict)]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise PaperFigError(f"critic report {critic_json}: every issue needs a unique `id` (i1, i2, …) — the fix "
                            "build's --note names them as applied or open")
    sev = {"high": 0, "medium": 0, "low": 0}
    for i in crit.get("issues", []):
        sev[i.get("severity", "low")] = sev.get(i.get("severity", "low"), 0) + 1
    rec = _read(run_dir)
    lint_json, critic_json = Path(lint_json).resolve(), Path(critic_json).resolve()  # check --final may run elsewhere
    rec["rounds"].append({"n": int(n), "lint": dict(lint.get("counts", {}), ok=bool(lint.get("ok"))), "lint_file": str(lint_json),
                          "critic": crit.get("scores", {}), "critic_issues": sev, "critic_file": str(critic_json),
                          "reader": reader, "note": note, "at": _now()})
    _write(run_dir, rec)


def _record_user_round(run_dir, n: int, lint_json, note: str) -> None:
    if not str(note).strip():
        raise PaperFigError("a user revision round needs --note with what the user asked for")
    rec = _read(run_dir)
    reviewed = [r for r in rec["rounds"] if r.get("critic") is not None]
    if not reviewed:
        raise PaperFigError("record the critic's round before a user revision")
    if rec["rounds"] and int(n) <= rec["rounds"][-1]["n"]:
        raise PaperFigError(f"round {n} must come after round {rec['rounds'][-1]['n']}")
    try:
        lint = json.loads(Path(lint_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"cannot read round {n} lint: {e}") from e
    last = reviewed[-1]
    rec["rounds"].append({"n": int(n), "lint": dict(lint.get("counts", {}), ok=bool(lint.get("ok"))),
                          "lint_file": str(Path(lint_json).resolve()), "critic": None, "by_user": True,
                          "critic_of": last["n"], "critic_issues": last.get("critic_issues"),
                          "critic_file": last.get("critic_file"), "reader": last.get("reader"), "note": note, "at": _now()})
    _write(run_dir, rec)


def _record_fix_round(run_dir, n: int, lint_json, note: str, critic_of: int | None) -> None:
    if critic_of is None:
        raise PaperFigError("a round needs --critic, or --critic-of K for the fix build right after the reviewed round K")
    rec = _read(run_dir)
    rounds = rec["rounds"]
    reviewed = [r for r in rounds if r["n"] == critic_of and r.get("critic") is not None]
    if not reviewed:
        raise PaperFigError(f"--critic-of {critic_of}: no round {critic_of} reviewed by a critic is recorded")
    if not rounds or rounds[-1]["n"] != critic_of or int(n) != critic_of + 1:
        raise PaperFigError(f"a fix build without a critic must directly follow its reviewed round ({critic_of} → "
                            f"{critic_of + 1}); round {n} would drift from the review — run the critic on it instead")
    if not str(note).strip():
        raise PaperFigError("a fix build's --note must say which of the critic's issues it applied")
    try:
        crit = json.loads(Path(reviewed[0].get("critic_file") or "").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        crit = {}
    need = [str(i.get("id")) for i in crit.get("issues", []) if isinstance(i, dict) and i.get("id")
            and i.get("severity") in ("high", "medium")]
    missing = [x for x in need if not re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", note)]
    if missing:
        raise PaperFigError(f"the fix build's --note does not mention the critic's high/medium issue(s) "
                            f"{', '.join(missing)} — write 'applied: i1, i2; open: i3 (why)'")
    try:
        lint = json.loads(Path(lint_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"cannot read round {n} lint: {e}") from e
    rounds.append({"n": int(n), "lint": dict(lint.get("counts", {}), ok=bool(lint.get("ok"))),
                   "lint_file": str(Path(lint_json).resolve()), "critic": None, "critic_of": int(critic_of),
                   "critic_issues": reviewed[0].get("critic_issues"), "critic_file": reviewed[0].get("critic_file"),
                   "reader": reviewed[0].get("reader"), "note": note, "at": _now()})
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
    lint = json.loads((build / "fig.lint.json").read_text(encoding="utf-8")) if (build / "fig.lint.json").is_file() else {}
    for fig in (lint.get("stats") or {}).get("module_figures") or []:  # the plan's own-figure modules (build_figures)
        for ext in ("drawio", "png", "pdf", "lint.md"):
            if not (build / f"{fig}.{ext}").is_file():
                raise PaperFigError(f"last round's module figure {build / f'{fig}.{ext}'} is missing")
    extra = [f"{fig}.{ext}" for fig in (lint.get("stats") or {}).get("module_figures") or []
             for ext in ("drawio", "png", "pdf", "lint.md", "svg")]
    for name in DELIVER_OPTIONAL + tuple(extra):
        src = build / name
        if src.is_file():
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


REVIEW_SCORES = ("design_quality", "originality", "function", "faithfulness")


def _design_review_problems(d: Path) -> list[str]:
    """A v2 run is reviewed once at the design stage (agents/reviewer.md, STAGE=design) and answers every high /
    medium issue in it (user, 2026-11-28: an independent reviewer that shares everything and gives feedback)."""
    try:
        v2 = json.loads((d / "figure_plan.json").read_text(encoding="utf-8")).get("brief_version") == 2
    except (OSError, ValueError):
        return []
    if not v2:
        return []
    f = d / "critic" / "design.json"
    if not f.is_file():
        return ["missing critic/design.json — dispatch the reviewer with STAGE=design before the blueprint"]
    try:
        r = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"critic/design.json: unreadable ({e})"]
    out = []
    if r.get("stage") != "design":
        out.append("critic/design.json: stage is not 'design'")
    miss = [k for k in REVIEW_SCORES if not isinstance((r.get("scores") or {}).get(k), (int, float))]
    if miss:
        out.append(f"critic/design.json: scores lack {', '.join(miss)}")
    for i in r.get("issues") or []:
        if i.get("severity") in ("high", "medium") and len(str(i.get("resolution") or "").split()) < 2:
            out.append(f"critic/design.json: issue {i.get('id')} ({i.get('severity')}) has no resolution — "
                       "write 'applied: …' or 'declined: why'")
    return out


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
            val("facts", "facts.json", text=d / "inputs" / "method.txt",
                analysis=[d / n for n in ("analysis.draft.json", "analysis.code.json") if (d / n).is_file()],
                repo=rec["inputs"].get("code") or None)  # a mixed run: a fact cites the paper or a file:line
    if rec["inputs"].get("code"):
        val("code-analysis", "analysis.code.json", repo=rec["inputs"]["code"])
        if not rec["inputs"].get("draft"):  # code-only: facts cite file:line and were never re-checked here
            val("facts", "facts.json", analysis=[d / "analysis.code.json"], repo=rec["inputs"]["code"])
    val("blueprint", "blueprint.json")
    if (d / "blueprint.json").is_file() and '"generated"' in (d / "blueprint.json").read_text(encoding="utf-8"):
        from .illustrate import check_grounds  # a generated scene must be one the paper or code describes
        try:
            text = d / "inputs" / "method.txt"
            bad = check_grounds(d / "blueprint.json", text if text.is_file() else None, rec["inputs"].get("code"))
        except PaperFigError:
            bad = {}  # an invalid blueprint is reported by its own validation above
        probs.extend(f"blueprint.json: illustration '{k}': {v}" for k, v in bad.items())
    if rec["inputs"].get("draft") or rec["inputs"].get("code"):
        val("figure-plan", "figure_plan.json", facts=d / "facts.json" if (d / "facts.json").is_file() else None,
            refs=d / "refs" / "refs.json" if (d / "refs" / "refs.json").is_file() else None,
            blueprint=d / "blueprint.json" if (d / "blueprint.json").is_file() else None,
            analysis=[d / n for n in ("analysis.draft.json", "analysis.code.json") if (d / n).is_file()] or None)
    probs.extend(_design_review_problems(d))
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
        plan_v2 = False
        if (d / "figure_plan.json").is_file():
            try:
                plan_v2 = json.loads((d / "figure_plan.json").read_text(encoding="utf-8")).get("brief_version") == 2
            except (OSError, ValueError):
                pass
        want = REPORT_SECTIONS + (("## Omitted",) if (d / "figure_plan.json").is_file() else ()) + \
            (("## Caption draft",) if plan_v2 else ())
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
        bp_now, bp_built = d / "blueprint.json", (build / "fig.blueprint.json") if build is not None else None
        if bp_now.is_file() and bp_built is not None and bp_built.is_file() and _sha(bp_now) != _sha(bp_built):
            probs.append("blueprint.json changed after the last build round — build and review it again before delivery")
        pdf = Path(dl["dir"]) / "fig.pdf" if dl and dl.get("dir") else None
        if pdf is not None and pdf.is_file():
            try:
                from pypdf import PdfReader
                n = len(PdfReader(str(pdf)).pages)
            except Exception as e:  # noqa: BLE001 — any unreadable PDF is a delivery problem
                probs.append(f"delivered fig.pdf cannot be read: {e}")
            else:
                if n != 1:
                    probs.append(f"delivered fig.pdf has {n} pages — a figure is one page (rebuild the round)")
    return probs
