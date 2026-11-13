"""Benchmark harness (plan Task 8): prepare blind inputs for each benchmark paper, then report runs
against the original figures. Inputs and original crops live only in the cache; the repo keeps configs
and `baseline.json` (numbers, model, git sha — no images)."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from .errors import PaperFigError
from .refs import cache_root
from .run import POINTS

REQUIRED = ("paper", "title", "arxiv_id", "venue", "width", "figure", "figure_type", "domain", "code")


def load_config(path) -> dict:
    try:
        c = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PaperFigError(f"benchmark config {path}: {e}") from e
    miss = [k for k in REQUIRED if k not in c]
    if miss:
        raise PaperFigError(f"benchmark config {path}: missing {', '.join(miss)}")
    if c["figure_type"] not in ("overview", "teaser", "module-detail"):
        raise PaperFigError(f"benchmark config {path}: figure_type must be overview, teaser or module-detail")
    code = c["code"]
    if not isinstance(code, dict) or not code.get("repo") or "/" not in code["repo"]:
        raise PaperFigError(f"benchmark config {path}: code.repo must be 'owner/name'")
    return c


def _http_get(url: str, timeout: float = 120) -> bytes:
    from .refs import _get_retry

    return _get_retry(url, timeout=timeout)


def _fetch_pdf(arxiv_id: str) -> Path:
    from .refs import fetch

    return fetch(arxiv_id)


def safe_unzip(data: bytes, dest: Path) -> list[str]:
    """Extract a GitHub archive (one top-level folder, stripped) refusing members that escape ``dest``."""
    dest = Path(dest).resolve()
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for m in z.infolist():
            parts = Path(m.filename).parts[1:]  # drop "<repo>-<sha>/"
            if not parts or m.is_dir():
                continue
            target = (dest / Path(*parts)).resolve()
            if dest not in target.parents:
                raise PaperFigError(f"archive member {m.filename!r} would land outside {dest}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(m))
            out.append(str(target.relative_to(dest)))
    return out


def _fetch_code(code: dict, dest: Path) -> tuple[str, list[str]]:
    repo, ref = code["repo"], code.get("ref") or "HEAD"
    try:
        sha = json.loads(_http_get(f"https://api.github.com/repos/{repo}/commits/{ref}"))["sha"]
    except (OSError, ValueError, KeyError) as e:
        raise PaperFigError(f"cannot resolve {repo}@{ref}: {e}") from e
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    files = []
    if code.get("paths"):
        for p in code["paths"]:
            if ".." in Path(p).parts or Path(p).is_absolute():
                raise PaperFigError(f"code path {p!r} must stay inside the repository")
            try:
                data = _http_get(f"https://raw.githubusercontent.com/{repo}/{sha}/{p}")
            except OSError as e:
                raise PaperFigError(f"cannot fetch {repo}/{p}@{sha[:7]}: {e}") from e
            (dest / p).parent.mkdir(parents=True, exist_ok=True)
            (dest / p).write_bytes(data)
            files.append(p)
    else:
        try:
            files = safe_unzip(_http_get(f"https://codeload.github.com/{repo}/zip/{sha}", timeout=600), dest)
        except OSError as e:
            raise PaperFigError(f"cannot download {repo}@{sha[:7]}: {e}") from e
    return sha, files


GUIDANCE = ("SKILL.md", "references", "agents")


def guidance_citing(arxiv_id: str, root=None) -> list[str]:
    """Lines of the shipped guidance (SKILL.md, references/, agents/) that cite a card of this paper: a blind run on it
    reads lessons drawn from its own figure. Returns 'file:line: text' entries; [] when nothing cites it."""
    from .kb import _card_keys, load_kb, paper_key

    root = Path(root) if root else Path(__file__).resolve().parent.parent
    key = paper_key(arxiv_id)
    ids = {cid for cid, c in load_kb().cards.items() if key in _card_keys(c)}
    if not ids:
        return []
    pat = re.compile(r"\b(" + "|".join(re.escape(i) for i in sorted(ids)) + r")\b")
    out = []
    for g in GUIDANCE:
        for f in sorted([root / g] if (root / g).is_file() else (root / g).rglob("*.md")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if pat.search(line):
                    out.append(f"{f.relative_to(root)}:{n}: {line.strip()[:120]}")
    return out


def prepare(config_path) -> dict:
    from .extract import extract_draft, method_section
    from .refs import crop_figures

    c = load_config(config_path)
    d = cache_root() / "bench" / c["paper"]
    d.mkdir(parents=True, exist_ok=True)
    pdf = d / "paper.pdf"
    if not pdf.is_file():
        shutil.copyfile(_fetch_pdf(c["arxiv_id"]), pdf)
    draft = extract_draft(pdf, blind=bool(c.get("blind", True)))
    method = method_section(draft)
    (d / "method.txt").write_text(method, encoding="utf-8")
    crop = crop_figures(pdf, d / "original", numbers={int(c["figure"])})[0]
    sha, files = _fetch_code(c["code"], d / "code")
    rec = {"paper": c["paper"], "pdf": str(pdf), "method": str(d / "method.txt"), "method_words": len(method.split()),
           "warnings": draft.warnings, "original": str(crop.png), "original_page": crop.page,
           "code_dir": str(d / "code"), "repo": c["code"]["repo"], "commit": sha, "code_files": len(files),
           "prepared": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
           "guidance_leaks": guidance_citing(c["arxiv_id"])}
    (d / "prepared.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def _find_run(runs_root: Path, arxiv_id: str):
    from .refs import _strip_version

    best = None
    for rj in sorted(Path(runs_root).glob("*/run.json")) if Path(runs_root).is_dir() else []:
        try:
            rec = json.loads(rj.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if _strip_version(str((rec.get("paper") or {}).get("arxiv_id") or "")) == _strip_version(arxiv_id):
            if best is None or rj.stat().st_mtime > best[0].stat().st_mtime:
                best = (rj, rec)
    return best


def report(bench_dir, runs_root, out_dir) -> dict:
    from .contact import compose
    from .kb import REPO_KB, kb_version
    from .run import check

    bench_dir, out_dir = Path(bench_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    papers, models = {}, set()
    for cp in sorted(bench_dir.glob("*/config.json")):
        c = load_config(cp)
        found = _find_run(Path(runs_root), c["arxiv_id"])
        if not found:
            papers[c["paper"]] = {"status": "no run"}
            continue
        rj, rec = found
        models.add(rec.get("model"))
        rounds = rec.get("rounds", [])
        last = rounds[-1] if rounds else {}
        stats = {}
        if last.get("lint_file") and Path(last["lint_file"]).is_file():
            stats = json.loads(Path(last["lint_file"]).read_text(encoding="utf-8")).get("stats", {})
        probs = check(rj.parent)
        papers[c["paper"]] = {
            "status": "ok" if not probs else "incomplete", "check_problems": len(probs), "rounds": len(rounds),
            "final_lint": {k: v for k, v in (last.get("lint") or {}).items()}, "critic": last.get("critic", {}),
            "critic_issues": last.get("critic_issues", {}), "facts_covered": stats.get("facts_covered"),
            "decisions": sorted({x["point"] for x in rec.get("decisions", [])} & set(POINTS)),
            "figure_type": c["figure_type"], "venue": c["venue"]}
        panels = []
        orig = cache_root() / "bench" / c["paper"] / "original" / f"fig{c['figure']}.png"
        if orig.is_file():
            panels.append((f"Original (Fig. {c['figure']})", orig))
        if rounds:
            first = Path(rounds[0]["lint_file"]).parent / "fig.png"
            final = Path(last["lint_file"]).parent / "fig.png"
            if first.is_file() and len(rounds) > 1:
                panels.append(("Ours, round 1", first))
            if final.is_file():
                panels.append((f"Ours, final (round {len(rounds)})", final))
        if panels:
            compose(panels, out_dir / f"{c['paper']}.png")
    done = [p for p in papers.values() if p.get("critic")]
    dims = sorted({k for p in done for k in p["critic"]})
    summary = {"papers": len(papers), "with_run": sum(1 for p in papers.values() if p["status"] != "no run"),
               "check_ok": sum(1 for p in papers.values() if p["status"] == "ok"),
               "critic_mean": {k: round(sum(p["critic"].get(k, 0) for p in done) / len(done), 2) for k in dims} if done else {},
               "final_lint_errors": sum(p.get("final_lint", {}).get("error", 0) for p in papers.values() if p["status"] != "no run")}
    base = {"created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "git_sha": kb_version(REPO_KB),
            "models": sorted(m for m in models if m), "summary": summary, "papers": papers}
    (bench_dir / "baseline.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
    return base
