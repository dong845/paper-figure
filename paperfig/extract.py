"""Draft text extraction for the analysis agents and the critic (spec §3, §4 ①).

`blind=True` removes figures and their captions so a benchmark run never sees the original figure's
description (phase-1 blind protocol)."""
from __future__ import annotations

import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import PaperFigError

METHOD_HEADINGS = re.compile(r"^\s*(\d+(\.\d+)*\.?\s*)?(method|methods|methodology|approach|our approach|proposed method|model|framework|architecture)\b", re.I)
SECTION_RE = re.compile(r"\\(section|subsection)\*?\{([^}]*)\}")


@dataclass
class Section:
    title: str
    start: int
    level: int = 1


@dataclass
class Draft:
    text: str
    sections: list[Section] = field(default_factory=list)
    source_kind: str = ""
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ tex
def _strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


def _resolve_inputs(path: Path, seen=None) -> str:
    seen = seen or set()
    if path in seen:
        return ""
    seen.add(path)
    src = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))

    def repl(m):
        name = m.group(2)
        cand = (path.parent / name)
        if cand.suffix != ".tex":
            cand = cand.with_suffix(".tex") if not (path.parent / name).is_file() else cand
        return _resolve_inputs(cand, seen) if cand.is_file() else ""

    return re.sub(r"\\(input|include)\{([^}]*)\}", repl, src)


def _tex_main(path: Path) -> Path:
    if path.is_file():
        return path
    cands = [p for p in path.glob("*.tex") if "\\documentclass" in p.read_text(encoding="utf-8", errors="replace")]
    if not cands:
        raise PaperFigError(f"no .tex file with \\documentclass in {path}")
    return sorted(cands, key=lambda p: -p.stat().st_size)[0]


def _tex(path: Path, blind: bool) -> Draft:
    src = _resolve_inputs(_tex_main(path))
    if blind:
        src = re.sub(r"\\begin\{(figure\*?|wrapfigure|subfigure)\}.*?\\end\{\1\}", "", src, flags=re.S)
        src = re.sub(r"\\caption(of)?\{(?:[^{}]|\{[^{}]*\})*\}", "", src)
    body = src.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    out, sections = [], []
    pos = 0
    for m in SECTION_RE.finditer(body):
        out.append(_detex(body[pos:m.start()]))
        sections.append(Section(m.group(2).strip(), sum(len(x) for x in out) + 1, 1 if m.group(1) == "section" else 2))
        out.append("\n" + m.group(2).strip() + "\n")
        pos = m.end()
    out.append(_detex(body[pos:]))
    return Draft("".join(out), sections, "tex")


def _detex(s: str) -> str:
    s = re.sub(r"\\(label|ref|cite[tp]?|eqref|includegraphics)(\[[^\]]*\])?\{[^}]*\}", "", s)
    s = re.sub(r"\\(textbf|textit|emph|mathrm|text)\{([^}]*)\}", r"\2", s)
    return re.sub(r"[ \t]+", " ", s)


# ------------------------------------------------------------------ pdf
CAPTION_START = re.compile(r"^\s*(Figure|Fig\.)\s*\d+[.:]", re.I)


def _pdf(path: Path, blind: bool) -> Draft:
    try:
        txt = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True, timeout=120).stdout
    except FileNotFoundError:
        raise PaperFigError("pdftotext (poppler) is required to read PDF drafts: brew install poppler / apt install poppler-utils")
    paras = re.split(r"\n\s*\n", txt)
    if blind:
        paras = [p for p in paras if not CAPTION_START.match(p)]
    text = "\n\n".join(paras)
    sections = [Section(m.group(0).strip(), m.start()) for m in re.finditer(r"(?m)^\s*\d+(\.\d+)?\.?\s+[A-Z][A-Za-z\- ]{2,60}$", text)]
    return Draft(text, sections, "pdf")


# ------------------------------------------------------------------ md / docx
def _md(path: Path, blind: bool) -> Draft:
    src = path.read_text(encoding="utf-8", errors="replace")
    if blind:
        src = re.sub(r"!\[[^\]]*\]\([^)]*\)\s*(\n\s*\n)?(\s*(Figure|Fig\.)\s*\d+[.:][^\n]*(\n(?!\s*\n)[^\n]*)*)?", "", src)
        src = "\n\n".join(p for p in re.split(r"\n\s*\n", src) if not CAPTION_START.match(p))
    sections = [Section(m.group(2).strip(), m.start(), len(m.group(1))) for m in re.finditer(r"(?m)^(#{1,3})\s+(.+)$", src)]
    return Draft(src, sections, "md")


def _docx(path: Path, blind: bool) -> Draft:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise PaperFigError(f"cannot read .docx {path}: {e}")
    paras = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
    if blind:
        paras = [p for p in paras if not CAPTION_START.match(p)]
    text = "\n\n".join(p for p in paras if p.strip())
    sections = [Section(p.strip(), text.find(p)) for p in paras if METHOD_HEADINGS.match(p) and len(p) < 80]
    return Draft(text, sections, "docx")


def extract_draft(path, blind: bool = False) -> Draft:
    path = Path(path).expanduser()
    if not path.exists():
        raise PaperFigError(f"draft not found: {path}")
    if path.is_dir() or path.suffix == ".tex":
        return _tex(path, blind)
    kind = path.suffix.lower()
    if kind == ".pdf":
        return _pdf(path, blind)
    if kind in (".md", ".markdown", ".txt"):
        return _md(path, blind)
    if kind == ".docx":
        return _docx(path, blind)
    raise PaperFigError(f"unsupported draft format '{kind[1:] or path.name}' (use a .tex dir/file, .pdf, .md or .docx)")


def method_section(d: Draft) -> str:
    """Text of the method chapter (heading match) up to the next top-level section; whole text if none."""
    secs = sorted(d.sections, key=lambda s: s.start)
    for i, s in enumerate(secs):
        if METHOD_HEADINGS.match(s.title):
            nxt = next((t for t in secs[i + 1:] if t.level <= s.level), None)
            return d.text[s.start:(nxt.start if nxt else len(d.text))]
    d.warnings.append("no method heading found; using the whole draft")
    return d.text
