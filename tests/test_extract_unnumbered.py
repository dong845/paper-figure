"""Blind DreamerV3 run: a Nature-style paper (unnumbered Introduction / Results / Methods) gave the appendix tables
as the 'method' text — table rows such as '1 Actor Critic' and '0.78 Bandit' were read as numbered headings."""
from pathlib import Path

import pytest

from paperfig.extract import Draft, _numbered_sections, method_section, sections_for

TEXT = "\n\n".join([
    "Mastering Diverse Domains through World Models",
    "Introduction",
    "Reinforcement learning has enabled computers to solve tasks through interaction.",
    "Results",
    "We evaluate the agent across many domains and report its scores in detail here.",
    "Methods",
    "World model learning. The world model learns compact representations of sensory inputs through autoencoding "
    "and enables planning by predicting future representations and rewards for potential actions.",
    "Critic learning. The critic predicts the distribution of returns under the current actor behaviour.",
    "References",
    "1. Sutton, R. Reinforcement learning.",
    "Table 4: Hyperparameters",
    "1 Actor Critic\n\n0 Gamer\n\n2 SimPLe\n\n0.78 Bandit",
])


def test_table_rows_are_not_headings():
    titles = [s.title for s in _numbered_sections(TEXT)]
    assert not any(t.startswith(("0 ", "0.")) for t in titles), titles


def test_unnumbered_section_names_are_found_and_methods_is_the_method():
    d = Draft(TEXT, sections_for(TEXT), "pdf")
    m = method_section(d)
    assert m.lstrip().startswith("Methods") and "World model learning" in m and "Critic learning" in m
    assert "Hyperparameters" not in m and "Sutton" not in m


def test_table_like_method_text_warns():
    d = Draft("Table 5\n\n" + "\n\n".join(f"{i} Task {i}  {i * 3.1:.1f}  {i * 2.7:.1f}  {i * 1.9:.1f}" for i in range(1, 40)),
              [], "pdf")
    from paperfig.extract import check_method_text
    check_method_text(d, d.text)
    assert any("table" in w.lower() for w in d.warnings)


DREAMER = Path.home() / ".cache/paper-figure/bench/dreamerv3/paper.pdf"


@pytest.mark.skipif(not DREAMER.is_file(), reason="needs the cached DreamerV3 PDF")
def test_dreamerv3_method_text_is_the_methods_section():
    from paperfig.extract import extract_draft
    m = method_section(extract_draft(DREAMER, blind=True))
    assert "world model learning" in m.lower() and "critic learning" in m.lower() and m.lower().count("table") < 5


CACHE = Path.home() / ".cache/paper-figure/bench"
EXPECT = {"reflexion": "Reflexion: reinforcement via verbal reflection", "swin": "Method", "gat": "GAT ARCHITECTURE",
          "rag": "Methods", "dreamerv3": "Learning algorithm"}


@pytest.mark.parametrize("paper", sorted(EXPECT))
def test_method_section_starts_at_the_real_heading(paper):
    pdf = CACHE / paper / "paper.pdf"
    if not pdf.is_file():
        pytest.skip("needs the cached PDF")
    from paperfig.extract import extract_draft
    d = extract_draft(pdf, blind=True)
    m = method_section(d)
    import re
    head = " ".join(m.split()[:12])
    assert re.match(r"^(\d+(\.\d+)*\.?\s+)?" + re.escape(EXPECT[paper]), head, re.I), head
    assert not any("looks like tables" in w for w in d.warnings), d.warnings


def test_sentences_are_not_headings():
    t = "1 Introduction\n\nText.\n\n2 While there are efficient methods to implement a sliding-window\n\n3 Method\n\nOurs."
    assert [s.title for s in _numbered_sections(t)] == ["1 Introduction", "3 Method"]
