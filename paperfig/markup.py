"""Label mini-markup: <b> <i> <sub> <sup> <br>, plus &lt; &gt; &amp; entities.

A '<' that does not start one of these tags is literal text.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .blueprint import TAG_RE, plain_text

_BR = re.compile(r"<br\s*/?>", re.I)
# TeX math: $…$ (or \(…\) as drawio stores it) is typeset by draw.io's MathJax at export; \$ is a literal dollar
MATH_RE = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$|\\\((.+?)\\\)")
_TEX_SYM = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
            "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
            "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
            "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ",
            "Psi": "Ψ", "Omega": "Ω", "top": "⊤", "cdot": "·", "times": "×", "mid": "|", "sum": "Σ", "prod": "Π",
            "in": "∈", "leq": "≤", "geq": "≥", "approx": "≈", "sim": "∼", "infty": "∞", "partial": "∂",
            "nabla": "∇", "odot": "⊙", "oplus": "⊕", "otimes": "⊗", "rightarrow": "→", "to": "→", "ldots": "…",
            "dots": "…", "hat": "", "tilde": "", "bar": "", "mathbf": "", "mathrm": "", "mathcal": "", "boldsymbol": "",
            "text": "", "operatorname": "", "left": "", "right": "", "quad": "  ", ",": " ", ";": " "}


def tex_runs(tex: str) -> list:
    """Approximate glyph runs of a TeX formula, for measuring only (MathJax draws the real thing)."""
    out: list = []
    i, n = 0, len(tex)

    def group(j):  # the {…} or single token starting at j -> (text, next index)
        if j < n and tex[j] == "{":
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(tex[k], 0)
                k += 1
            return tex[j + 1:k - 1], k
        if j < n and tex[j] == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", tex[j:])
            return m.group(0), j + len(m.group(0))
        return (tex[j] if j < n else ""), j + 1

    def flat(t: str) -> str:
        t = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", t)
        t = re.sub(r"\\sqrt", "√", t)
        t = re.sub(r"\\([A-Za-z]+|.)", lambda m: _TEX_SYM.get(m.group(1), m.group(1)[:1] if m.group(1).isalpha() else m.group(1)), t)
        return t.replace("{", "").replace("}", "").replace("_", "").replace("^", "")

    buf = ""
    while i < n:
        c = tex[i]
        if c in "_^":
            if buf:
                out.append(Run(flat(buf), italic=True, math=True))
                buf = ""
            g, i = group(i + 1)
            out.append(Run(flat(g), italic=True, script="sub" if c == "_" else "sup", math=True))
            continue
        buf += c
        i += 1
    if buf:
        out.append(Run(flat(buf), italic=True, math=True))
    return [r for r in out if r.text]


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    script: str = ""  # "", "sub", "sup"
    math: bool = False  # typeset by MathJax (wider glyphs than the text font)


def _decode(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def parse(label: str) -> list[list[Run]]:
    lines: list[list[Run]] = [[]]
    bold = italic = 0
    script: list[str] = []
    pos = 0
    label = label or ""

    def emit(text: str):
        pos2 = 0
        for m in MATH_RE.finditer(text or ""):
            plain_part = text[pos2:m.start()].replace("\\$", "$")
            if plain_part:
                lines[-1].append(Run(_decode(plain_part), bold > 0, italic > 0, script[-1] if script else ""))
            lines[-1].extend(tex_runs(m.group(1) or m.group(2)))
            pos2 = m.end()
        rest = (text or "")[pos2:].replace("\\$", "$")
        if rest:
            lines[-1].append(Run(_decode(rest), bold > 0, italic > 0, script[-1] if script else ""))

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

    def segment(t: str) -> str:  # math passes through to MathJax untouched; the rest is escaped text
        r, p2 = [], 0
        for mm in MATH_RE.finditer(t):
            r.append(html.escape(text(_decode(t[p2:mm.start()]).replace("\\$", "$")), quote=False))
            r.append("\\(" + html.escape(mm.group(1) or mm.group(2), quote=False) + "\\)")
            p2 = mm.end()
        r.append(html.escape(text(_decode(t[p2:]).replace("\\$", "$")), quote=False))
        return "".join(r)

    for m in TAG_RE.finditer(label):
        out.append(segment(label[pos : m.start()]))
        tag = m.group(1).lower()
        out.append("<br>" if tag == "br" else ("</%s>" if m.group(0).startswith("</") else "<%s>") % tag)
        pos = m.end()
    out.append(segment(label[pos:]))
    return "".join(out)


def plain(label: str) -> str:
    return plain_text(label)
