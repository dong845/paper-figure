"""The shipped skill (what `git archive` / GitHub "Download ZIP" packs, after `.gitattributes` export-ignore) keeps to
one directory level — root/dir/file. A skill host rejected the package for `kb/cards/<id>.json` (user, 2026-11-16:
"Skill 包仅支持两级目录结构"), and it must stay under its 3 MB upload limit."""
import io
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _archive() -> zipfile.ZipFile:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "archive", "--worktree-attributes", "--format=zip", "HEAD"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return zipfile.ZipFile(io.BytesIO(out))


def _shipped() -> list[str]:
    """Tracked files that ship (the working tree's files, so a move is checked before it is committed)."""
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, text=True).stdout.split()
    files = [f for f in files if (ROOT / f).is_file()]
    attr = subprocess.run(["git", "-C", str(ROOT), "check-attr", "export-ignore", "--", *files],
                          capture_output=True, text=True).stdout.splitlines()
    ignored = {line.split(": ")[0] for line in attr if line.endswith(": set")}
    return [f for f in files if f not in ignored]


def test_the_shipped_skill_is_at_most_one_directory_deep():
    try:
        files = _shipped()
    except OSError:
        pytest.skip("git not available")
    if not files:
        pytest.skip("not a git checkout")
    deep = sorted(f for f in files if f.count("/") > 1)
    assert deep == [], f"nested deeper than root/dir/file: {deep[:10]}"
    assert "SKILL.md" in files


def test_the_release_archive_stays_under_three_megabytes():
    z = _archive()
    size = sum(i.compress_size + 30 + len(i.filename) * 2 + 46 for i in z.infolist())
    assert size < 3_000_000, f"release zip ≈ {size / 1e6:.2f} MB"


def test_a_flat_example_finds_its_own_facts(tmp_path):
    """examples/<name>.blueprint.json sits beside examples/<name>.facts.json (flat layout): a build checks those facts."""
    from paperfig import pipeline as P
    r = P.build(ROOT / "examples" / "restormer.blueprint.json", "soft-pastel", out_dir=tmp_path, formats=())
    assert any(f.code.startswith("fact-") for f in r.report.findings)
