"""Label mini-markup: <b> <i> <sub> <sup> <br>, plus &lt; &gt; &amp; entities.

A '<' that does not start one of these tags is literal text.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .blueprint import TAG_RE, plain_text

_BR = re.compile(r"<br\s*/?>", re.I)


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    script: str = ""  # "", "sub", "sup"


def _decode(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def parse(label: str) -> list[list[Run]]:
    lines: list[list[Run]] = [[]]
    bold = italic = 0
    script: list[str] = []
    pos = 0
    label = label or ""

    def emit(text: str):
        if text:
            lines[-1].append(Run(_decode(text), bold > 0, italic > 0, script[-1] if script else ""))

    for m in TAG_RE.finditer(label):
        emit(label[pos : m.start()])
        pos = m.end()
        tag = m.group(1).lower()
        closing = m.group(0).startswith("</")
        if tag == "br":
            lines.append([])
        elif tag == "b":
            bold += -1 if closing else 1
        elif tag == "i":
            italic += -1 if closing else 1
        elif tag in ("sub", "sup"):
            if closing:
                if script:
                    script.pop()
            else:
                script.append(tag)
    emit(label[pos:])
    return lines


def to_html(label: str) -> str:
    """drawio html=1 label: escape text, keep whitelisted tags, normalise <br>."""
    out, pos = [], 0
    label = label or ""
    depth = [0]

    def text(t: str) -> str:  # inside parentheses an ASCII "|" is the conditional bar: "∣" never reads as "l"
        r = []
        for ch in t:
            depth[0] += ch == "("
            depth[0] -= ch == ")" and depth[0] > 0
            r.append("∣" if ch == "|" and depth[0] > 0 else ch)
        return "".join(r)

    for m in TAG_RE.finditer(label):
        out.append(html.escape(text(_decode(label[pos : m.start()])), quote=False))
        tag = m.group(1).lower()
        out.append("<br>" if tag == "br" else ("</%s>" if m.group(0).startswith("</") else "<%s>") % tag)
        pos = m.end()
    out.append(html.escape(text(_decode(label[pos:])), quote=False))
    return "".join(out)


def plain(label: str) -> str:
    return plain_text(label)
