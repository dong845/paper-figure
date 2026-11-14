"""Blind DreamerV3 run (Nature): the 7 pt heuristic was applied although kb/formats.json records Nature's own range
(5–7 pt), and nothing checked the 7 pt maximum."""
import copy
import json

from conftest import MINI
from paperfig import pipeline as P


def _build(tmp_path, venue, width="double"):
    d = copy.deepcopy(MINI)
    d["figure"].update(venue=venue, width=width)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "b.json").write_text(json.dumps(d))
    return P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())


def test_nature_is_judged_by_its_own_range(tmp_path):
    r = _build(tmp_path / "n", "nature", width=4.5)  # text prints between Nature's 5 pt floor and the 7 pt heuristic
    assert 5.0 <= r.report.stats["smallest_text_pt"] < 7.0
    assert "min-font" not in {f.code for f in r.report.findings}
    big = _build(tmp_path / "d", "nature")  # double column: the titles print above Nature's 7 pt maximum
    assert big.report.stats["largest_text_pt"] > 7.0
    f = next(f for f in big.report.findings if f.code == "max-font")
    assert f.severity == "warn" and "7" in f.message


def test_other_venues_keep_the_heuristic(tmp_path):
    r = _build(tmp_path / "c", "cvpr")
    assert "largest_text_pt" in r.report.stats and not [f for f in r.report.findings if f.code == "max-font"]
