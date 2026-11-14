"""Draft text extraction for the analysis agents and the critic (spec §3, §4 ①).

`blind=True` removes figures and their captions so a benchmark run never sees the original figure's
description (phase-1 blind protocol)."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import PaperFigError

METHOD_HEADINGS = re.compile(r"^\s*(\d+(\.\d+)*\.?\s*)?(the\s+)?(method|methods|methodology|approach|our approach|proposed method|model|framework|architecture)\b", re.I)
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


def _pdf_blocks(path: Path, blind: bool) -> list[str]:
    """Text blocks in reading order, rebuilt from the PDF's own layout: within each band between full-width
    blocks, the left column top to bottom, then the right column (pdftotext's default order can put a
    column's continuation before the heading above it). Text drawn inside figures, margin stamps, running
    heads and page numbers are dropped; figure captions too when ``blind``."""
    from . import refs

    doc = refs._layout(path)
    caps = refs._captions(doc)
    cap_ids = {i for c in caps for i in c.blocks}
    fig_caps = [c for c in caps if c.kind == "figure"]
    inside = set()  # ids of text blocks drawn inside a figure
    renders = refs._Renders(doc, 72)
    try:
        for c in fig_caps:
            side, ra, rb, _, _, _, barriers = refs._decide(doc, c, caps, renders, cap_ids)
            region = ra if side in ("above", "left", "right") else rb if side == "below" else None
            if region is None:
                continue
            for b in doc.pages[c.page - 1].blocks:
                if id(b) in barriers or id(b) in cap_ids:
                    continue
                if b.x0 >= region[0] - 1 and b.x1 <= region[2] + 1 and b.y0 >= region[1] - 1 and b.y1 <= region[3] + 1:
                    inside.add(id(b))
    finally:
        renders.close()
    drop_caps = {i for c in fig_caps for i in c.blocks} if blind else set()
    ty0, ty1 = doc.text_y or (0.0, 1e9)
    out = []
    for pg in doc.pages:
        tx0, tx1 = pg.text_x or (0.0, pg.w)
        keep = [b for b in pg.blocks if id(b) not in inside and id(b) not in drop_caps
                and b.x1 > tx0 - 4 and b.x0 < tx1 + 4 and b.x0 > tx0 - 12  # margin stamps / line numbers
                and b.y1 > ty0 - 8 and b.y0 < ty1 + 8]  # running heads, page numbers
        if len(pg.cols) >= 2:
            gaps = list(zip(pg.cols, pg.cols[1:]))
            spans = sorted((b for b in keep if any(b.x0 < a[1] - 5 and b.x1 > n[0] + 5 for a, n in gaps)), key=lambda b: b.y0)
            span_ids = {id(b) for b in spans}
            cols = [[] for _ in pg.cols]
            for b in keep:
                if id(b) in span_ids:
                    continue
                cx = (b.x0 + b.x1) / 2
                k = min(range(len(pg.cols)), key=lambda i: 0 if pg.cols[i][0] - 6 <= cx <= pg.cols[i][1] + 6
                        else min(abs(cx - pg.cols[i][0]), abs(cx - pg.cols[i][1])))
                cols[k].append(b)
            top = -1e9
            for edge in spans + [None]:
                bottom = edge.y0 if edge is not None else 1e9
                for col in cols:
                    out += [b for b in sorted(col, key=lambda b: (b.y0, b.x0)) if top <= (b.y0 + b.y1) / 2 < bottom]
                if edge is not None:
                    out.append(edge)
                    top = edge.y1
        else:
            out += sorted(keep, key=lambda b: (b.y0, b.x0))
    return ["\n".join(ln.text for ln in b.lines) for b in out]


def _pdf(path: Path, blind: bool) -> Draft:
    paras = _pdf_blocks(path, blind)
    if blind:
        paras = [p for p in paras if not CAPTION_START.match(p)]
    text = "\n\n".join(paras)
    return Draft(text, sections_for(text), "pdf")


def _numbered_sections(text: str) -> list[Section]:
    sections = []
    # the number and the title may be on separate lines (common in PDF layouts); the title may be upper case
    for m in re.finditer(r"(?m)^[ \t]*(\d+(?:\.\d+)*)\.?(?:[ \t]+|[ \t]*(?:\n[ \t]*){1,2})([A-Z][A-Za-z\-,: ]{2,70})$", text):
        parts = m.group(1).split(".")
        if int(parts[0]) > 12 or int(parts[0]) == 0 or any(len(p) > 2 for p in parts):
            continue  # table values such as "65.2 OK-VQA" or "0.78 Bandit" are not headings (sections start at 1)
        if len(m.group(2).split()) > 8:
            continue  # a sentence after a footnote number ("2 While there are efficient methods to …"), not a title
        sections.append(Section(f"{m.group(1)} {m.group(2).strip()}", m.start(), len(parts)))
    return sections


NAMED_HEADING = re.compile(r"^(introduction|background|related\s+work|preliminaries|results|experiments|discussion|"
                           r"conclusions?|methods?|methodology|approach|limitations|references|bibliography|"
                           r"(the\s+|our\s+)?(learning\s+)?algorithm|(our\s+|the\s+)?(model|framework|architecture)|"
                           r"(proposed|our)\s+(method|approach)|"
                           r"acknowledge?ments?|appendix|supplementary(\s+(material|information))?|"
                           r"data\s+availability|code\s+availability|online\s+methods)\.?$", re.I)


def _named_sections(text: str) -> list[Section]:
    """Unnumbered headings (Nature-style papers): a paragraph that is only a standard section name."""
    out, pos = [], 0
    for para in re.split(r"(\n\s*\n)", text):
        if NAMED_HEADING.match(para.strip()):
            out.append(Section(para.strip(), pos + (len(para) - len(para.lstrip())), 1))
        pos += len(para)
    return out


def sections_for(text: str) -> list[Section]:
    """The draft's structure: its numbered headings (unnumbered names are method_section's fallback)."""
    return _numbered_sections(text)


TABLE_DIGITS = 0.18  # share of digits above which a "method" text reads as tables (hyper-parameters, scores)


def check_method_text(d: Draft, text: str) -> None:
    """Warn loudly when the method text looks like tables or an appendix rather than prose."""
    chars = [c for c in text if not c.isspace()]
    digits = sum(c.isdigit() for c in chars) / max(1, len(chars))
    tables = len(re.findall(r"(?m)^\s*table\s+\d+", text, re.I))
    if digits > TABLE_DIGITS or (tables >= 3 and digits > TABLE_DIGITS / 2):
        d.warnings.append(f"the method text looks like tables ({digits:.0%} digits, {tables} table headings) — the "
                          "method section was probably not found; check the headings, or give the section by hand")


def _txt(path: Path, blind: bool) -> Draft:
    """Plain text with numbered headings (e.g. a prepared benchmark method text)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if blind:
        text = "\n\n".join(p for p in re.split(r"\n\s*\n", text) if not CAPTION_START.match(p))
    return Draft(text, sections_for(text), "txt")


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
    if kind in (".md", ".markdown"):
        return _md(path, blind)
    if kind == ".txt":
        return _txt(path, blind)
    if kind == ".docx":
        return _docx(path, blind)
    raise PaperFigError(f"unsupported draft format '{kind[1:] or path.name}' (use a .tex dir/file, .pdf, .md, .txt or .docx)")


START_SKIP = re.compile(r"^\s*(abstract|introduction|related\s+work|background|preliminar|problem\s+(statement|formulation|setting|definition)|notation|motivation)", re.I)
END_RE = re.compile(r"(experiment|evaluation|results|empirical|discussion|conclusion|limitation|related\s+work|acknowledg|references|appendix|broader\s+impact|ablation)", re.I)
METHOD_WORDS = re.compile(r"\b(method|methods|methodology|approach|model|models|framework|architecture|proposed|formulation|algorithm)\b", re.I)


def _heading_title(t: str) -> str:
    t = re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", t)
    return re.sub(r"\b([A-Z]) (?=[A-Z]{2,}\b)", r"\1", t)  # small caps extract as "E VALUATION"


def method_section(d: Draft) -> str:
    """The method chapter from the numbered headings; when those give no usable method (fewer than three section
    numbers — a Nature-style paper whose only numbered lines are table rows —, no method heading, or tables), the
    unnumbered standard headings are tried instead."""
    probe = Draft(d.text, list(d.sections), d.source_kind)
    out = _method_from(probe)
    tops = {s.title.split()[0].split(".")[0] for s in d.sections}
    weak = len(tops) < 3 or any("no method heading" in w or "no section headings" in w for w in probe.warnings)
    check_method_text(probe, out)
    weak = weak or any("looks like tables" in w for w in probe.warnings)
    if weak:
        named = _named_sections(d.text)
        if named:
            alt_d = Draft(d.text, named, d.source_kind)
            alt = _method_from(alt_d)
            check_method_text(alt_d, alt)
            if not any("looks like tables" in w or "no method heading" in w for w in alt_d.warnings):
                d.warnings.append("no numbered method section; used the unnumbered heading structure")
                return alt
    d.warnings.extend(w for w in probe.warnings if w not in d.warnings)
    return out


def _method_from(d: Draft) -> str:
    """The method chapter: from the first top-level section that names the method (else the first after
    introduction / related work / background) up to the first later top-level section that is experiments,
    results, discussion or conclusion. A method often spans sections (Model + Training)."""
    secs = sorted(d.sections, key=lambda s: s.start)
    if not secs:
        d.warnings.append("no section headings found; using the whole draft")
        return d.text
    intro = next((s for s in secs if re.search(r"\bintroduction\b", _heading_title(s.title), re.I)), None)
    if intro is not None:  # numbered lines before the introduction are affiliations or title-page noise
        secs = [s for s in secs if s.start >= intro.start]
    top = min(s.level for s in secs)
    lvl1 = [s for s in secs if s.level == top]
    num = lambda s: int(re.match(r"\s*(\d+)", s.title).group(1)) if re.match(r"\s*(\d+)", s.title) else None  # noqa: E731
    start = next((s for s in lvl1 if METHOD_WORDS.search(_heading_title(s.title)) and not END_RE.search(_heading_title(s.title))), None)
    if start is None:
        start = next((s for s in lvl1 if not START_SKIP.match(_heading_title(s.title))
                      and not END_RE.search(_heading_title(s.title))), None)
    if start is None:
        d.warnings.append("no method heading found; using the whole draft")
        return d.text
    n0 = num(start)
    end = None
    for s in lvl1:
        if s.start <= start.start:
            continue
        if n0 is not None and num(s) is not None and num(s) <= n0:
            continue  # out-of-order or restarted numbering (two-column interleaving, appendix): not a successor
        if END_RE.search(_heading_title(s.title)):
            end = s
            break
    return d.text[start.start:(end.start if end else len(d.text))]
