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


@pytest.mark.skipif(not os.path.isfile(os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")), reason="bench pdf not cached")
def test_pdf_reading_order_follows_columns():
    d = extract_draft(os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf"), blind=True)
    m = method_section(d)
    # page 3: the Overall Pipeline paragraph ends the left column and continues at the top of the right column
    i, j = m.find("where the number of blocks"), m.find("are gradually increased from the top to bottom")
    assert 0 <= i < j, (i, j)
    assert m.find("Overall Pipeline") < m.find("pixel-unshuffle") < m.find("The major computational overhead")


@pytest.mark.skipif(not os.path.isfile(os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")), reason="bench pdf not cached")
def test_pdf_drops_figure_internal_text_keeps_caption():
    d = extract_draft(os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf"))
    assert "HxWx2C" not in d.text and "Transposed-Attention" not in d.text  # labels drawn inside Fig. 2
    assert "Figure 2. Architecture of Restormer" in d.text  # caption kept when not blind
    b = extract_draft(os.path.expanduser("~/.cache/paper-figure/bench/blip2/paper.pdf"))
    assert "Write a romantic message" not in b.text  # text inside BLIP-2 Fig. 1
    assert "arXiv:2301.12597" not in b.text  # rotated margin stamp
    assert "Figure 1. Overview of BLIP-2" in b.text


def test_txt_draft_with_numbered_headings(tmp_path):
    p = tmp_path / "method.txt"
    p.write_text("1. Introduction\nWe study things.\n\n3. Method\nOur model has an encoder.\n\n3.1. Encoder\nIt encodes.\n\n4. Experiments\nNumbers.\n")
    d = extract_draft(p)
    m = method_section(d)
    assert d.source_kind == "txt" and m.startswith("3. Method") and "It encodes." in m and "Numbers." not in m


def _txt(tmp_path, body):
    p = tmp_path / "d.txt"
    p.write_text(body)
    return method_section(extract_draft(p))


def test_method_spans_model_and_training_sections(tmp_path):
    m = _txt(tmp_path, "1 Introduction\nIntro.\n\n2 Related Work\nOthers.\n\n3 Model\nThe encoder.\n\n4 Training\nContrastive loss.\n\n5 Experiments\nNumbers.\n")
    assert m.startswith("3 Model") and "Contrastive loss." in m and "Numbers." not in m and "Others." not in m


def test_unnamed_method_section_found_by_structure(tmp_path):
    m = _txt(tmp_path, "1 Introduction\nIntro.\n\n3 Problem Statement\nSets.\n\n4 Deep Learning on Point Sets\nOur net.\n\n4.2 Architecture\nLayers.\n\n"
                       "5 Experiment\nResults.\n\n5.2 Architecture Design Analysis\nAblation.\n")
    assert m.startswith("4 Deep Learning on Point Sets") and "Layers." in m and "Ablation." not in m


def test_uppercase_and_split_line_headings(tmp_path):
    m = _txt(tmp_path, "1\nINTRODUCTION\nIntro.\n\n2\nGAT ARCHITECTURE\nAttention layer.\n\n3\nEVALUATION\nScores.\n")
    assert "Attention layer." in m and "Scores." not in m and "Intro." not in m


def test_headings_in_separate_blocks_and_affiliations_ignored(tmp_path):
    body = ("Title of the Paper\n\n3\nStanford University\n\nAbstract text.\n\n1\n\nIntroduction\n\nIntro.\n\n"
            "1K\nRandom Trajectories\n\n2\n\nModel\n\nThe encoder.\n\n3\n\nTraining\n\nThe loss.\n\n4\n\nExperimental Setup\n\nNumbers.\n")
    m = _txt(tmp_path, body)
    assert m.startswith("2") and "The encoder." in m and "The loss." in m and "Numbers." not in m and "Stanford" not in m


def test_small_caps_headings(tmp_path):
    m = _txt(tmp_path, "1\n\nI NTRODUCTION\n\nIntro.\n\n2\n\nGAT A RCHITECTURE\n\nLayer.\n\n3\n\nE VALUATION\n\nScores.\n")
    assert "Layer." in m and "Scores." not in m and "Intro." not in m
