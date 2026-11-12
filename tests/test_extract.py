import os
import zipfile

import pytest

from paperfig.extract import extract_draft, method_section
from paperfig.codemap import code_map

TEX_MAIN = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
We study things. % a comment that must vanish
\input{method}
\section{Experiments}
Results.
\end{document}
"""
TEX_METHOD = r"""
\section{Method}
Our encoder feeds the FusionBlock.
\begin{figure*}[t]
  \includegraphics{fig.pdf}
  \caption{Overview of our pipeline: the encoder feeds the FusionBlock which secretly does X.}
\end{figure*}
The decoder reconstructs the image.
"""


def write_tex(tmp_path):
    (tmp_path / "main.tex").write_text(TEX_MAIN)
    (tmp_path / "method.tex").write_text(TEX_METHOD)
    return tmp_path


def test_tex_input_resolved(tmp_path):
    d = extract_draft(write_tex(tmp_path))
    assert "Our encoder feeds the FusionBlock." in d.text and "Results." in d.text
    assert "a comment that must vanish" not in d.text
    assert [s.title for s in d.sections] == ["Introduction", "Method", "Experiments"]


def test_blind_strips_figure_env_and_caption(tmp_path):
    d = extract_draft(write_tex(tmp_path), blind=True)
    assert "secretly does X" not in d.text and "includegraphics" not in d.text
    assert "The decoder reconstructs the image." in d.text


def test_method_section_found(tmp_path):
    d = extract_draft(write_tex(tmp_path))
    m = method_section(d)
    assert "FusionBlock" in m and "Results." not in m and "We study things" not in m


PDF = os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")


@pytest.mark.skipif(not os.path.isfile(PDF), reason="bench pdf not cached")
def test_pdf_blind_drops_caption_paragraphs():
    full = extract_draft(PDF)
    blind = extract_draft(PDF, blind=True)
    cap = "Architecture of Restormer for high-resolution image restoration"
    assert cap in full.text.replace("\n", " ") and cap not in blind.text.replace("\n", " ")
    assert "Multi-Dconv Head Transposed Attention" in blind.text


def test_md_blind(tmp_path):
    p = tmp_path / "d.md"
    p.write_text("# Method\nText before.\n\n![overview](fig.png)\n\nFigure 1: the hidden caption.\n\nText after.\n")
    d = extract_draft(p, blind=True)
    assert "hidden caption" not in d.text and "fig.png" not in d.text and "Text after." in d.text


def test_docx_text(tmp_path):
    p = tmp_path / "d.docx"
    body = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>Method</w:t></w:r></w:p><w:p><w:r><w:t>Our block is new.</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", body)
    assert "Our block is new." in extract_draft(p).text


def test_unsupported_format_raises(tmp_path):
    from paperfig.errors import PaperFigError
    p = tmp_path / "d.odt"
    p.write_text("x")
    with pytest.raises(PaperFigError, match="odt"):
        extract_draft(p)


def test_codemap_classes_and_forward(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "model.py").write_text(
        "import torch.nn as nn\n\nclass Block(nn.Module):\n    def __init__(self):\n        super().__init__()\n\n"
        "    def forward(self, x):\n        return x\n\ndef helper():\n    pass\n")
    m = code_map(tmp_path)
    f = next(x for x in m["files"] if x["path"].endswith("model.py"))
    c = f["classes"][0]
    assert c["name"] == "Block" and c["bases"] == ["nn.Module"] and c["forward_line"] == 7
    assert f["functions"][0]["name"] == "helper"


def test_codemap_skips_venv_and_reports_syntax_errors(tmp_path):
    (tmp_path / "venv" / "lib").mkdir(parents=True)
    (tmp_path / "venv" / "lib" / "x.py").write_text("class Hidden: pass\n")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    m = code_map(tmp_path)
    assert not any("venv" in f["path"] for f in m["files"])
    assert any(e["path"].endswith("bad.py") for e in m["errors"])


@pytest.mark.skipif(not os.path.isfile(PDF), reason="bench pdf not cached")
def test_pdf_method_section_includes_subsections():
    m = method_section(extract_draft(PDF, blind=True))
    assert len(m.split()) > 600
    assert "Gated-Dconv Feed-Forward Network" in m.replace("\n", " ") or "GDFN" in m


BLIP = os.path.expanduser("~/.cache/paper-figure/bench/blip2/paper.pdf")


@pytest.mark.skipif(not os.path.isfile(BLIP), reason="bench pdf not cached")
def test_two_column_pdf_method_section():
    m = method_section(extract_draft(BLIP, blind=True))
    assert len(m.split()) > 1000 and "learnable query embeddings" in m.replace("\n", " ")
