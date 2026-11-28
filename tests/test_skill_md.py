"""SKILL.md is the orchestrator's only guide: every command and file it names must exist."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
DOCS = [SKILL] + [p.read_text(encoding="utf-8") for p in sorted((ROOT / "agents").glob("*.md"))] + \
       [p.read_text(encoding="utf-8") for p in sorted((ROOT / "references").glob("*.md"))]


def _commands(text):
    return sorted({m.group(1) + ("" if m.group(2) is None else " " + m.group(2))
                   for m in re.finditer(r"\$PAPERFIG ([a-z-]+)(?: ([a-z-]+))?", text)})


def test_frontmatter():
    m = re.match(r"---\nname: paper-figure\ndescription: (.+?)\n---\n", SKILL, re.S)
    assert m and 200 < len(m.group(1)) < 1024


def test_every_named_command_exists():
    seen = set()
    for doc in DOCS:
        for cmd in _commands(doc):
            parts = cmd.split()
            key = tuple(parts)
            if key in seen:
                continue
            seen.add(key)
            r = subprocess.run([sys.executable, "-m", "paperfig", *parts, "--help"], capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0 and len(parts) == 2:  # second word was an argument, not a subcommand
                r = subprocess.run([sys.executable, "-m", "paperfig", parts[0], "--help"], capture_output=True, text=True, cwd=ROOT)
            assert r.returncode == 0, f"$PAPERFIG {cmd}: {r.stderr[-300:]}"
    assert len(seen) >= 15


def test_every_named_file_exists():
    names = set(re.findall(r"`((?:agents|references|kb|styles|bench|paperfig/schema)/[A-Za-z0-9_./-]+\.(?:md|json))`", "\n".join(DOCS)))
    missing = [n for n in names if "<" not in n and not (ROOT / n).exists()]
    assert not missing, missing
    for n in ("agents/draft-analyst.md", "agents/code-analyst.md", "agents/reference-scout.md", "agents/figure-card-writer.md",
              "agents/reviewer.md", "references/blueprint.md", "references/design.md", "references/build-kb.md"):
        assert n in SKILL or n.split("/")[1].replace(".md", "") in SKILL, n
