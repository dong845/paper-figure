"""Round 8: typographic hierarchy (<small> secondary text: dimensions, settings — smaller and muted, still held to
the print floor) and a figure font family (sans default; serif to match a serif body; Nature asks for sans)."""
import copy
import json

from conftest import MINI, PROV, leaf
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.measure import measure


def test_small_runs_measure_smaller():
    full, _ = measure("abcdefgh", 12)
    small, _ = measure("<small>abcdefgh</small>", 12)
    assert 0.75 * full < small < 0.85 * full


def _bp(tmp_path, label, **fig):
    d = copy.deepcopy(MINI)
    d["root"]["children"][1]["label"] = label
    d["figure"].update(fig)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    return tmp_path / "b.json"


def test_small_text_is_muted_and_counts_for_the_print_floor(tmp_path):
    plain = P.build(_bp(tmp_path / "a", "Encoder"), "soft-pastel", out_dir=tmp_path / "a" / "o", formats=())
    small = P.build(_bp(tmp_path / "b", "Encoder<br><small>n × 64</small>"), "soft-pastel", out_dir=tmp_path / "b" / "o", formats=())
    v = parse_cells(small.drawio.read_text())["pf-enc"].value
    assert "font-size:80%" in v.replace(" ", "") and "#6b7280" in v
    assert not [f for f in small.report.findings if f.code == "text-overflow"]  # the span is read back as <small>
    assert small.report.stats["smallest_text_pt"] < plain.report.stats["smallest_text_pt"]  # the floor sees it


def test_serif_font_sets_every_text_cell_and_its_metrics(tmp_path):
    res = P.build(_bp(tmp_path / "s", "Encoder", font="serif"), "soft-pastel", out_dir=tmp_path / "s" / "o", formats=())
    cells = parse_cells(res.drawio.read_text())
    fams = {c.style.get("fontFamily") for c in cells.values() if c.value and c.style.get("fontFamily")}
    assert fams == {"Times New Roman"}, fams
    assert measure("Transformer", 12, family="Times New Roman")[0] != measure("Transformer", 12)[0]


def test_serif_for_nature_is_flagged(tmp_path):
    res = P.build(_bp(tmp_path / "n", "Encoder", font="serif", venue="nature", width="double"), "soft-pastel",
                  out_dir=tmp_path / "n" / "o", formats=())
    assert any(f.code == "font-family" and f.severity == "warn" for f in res.report.findings)
