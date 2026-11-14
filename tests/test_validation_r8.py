"""Round 8 blind runs (Swin, DreamerV3): small fixes for what the runners hit."""
import copy
import json

import pytest

from conftest import MINI, PROV, leaf
from paperfig import pipeline as P


def test_glued_children_are_not_uneven_gaps(tmp_path):
    kids = [leaf(f"c{i}", f"x{i}", visual="chip") for i in range(5)]
    d = {"schema_version": 1, "figure": {"type": "overview", "venue": "neurips", "width": "double"},
         "root": {"id": "root", "layout": {"type": "column"}, "children": [
             {"id": "g", "layout": {"type": "column", "gap": "none"}, "frame": "none", "children": kids,
              "provenance": copy.deepcopy(PROV)}, leaf("n", "Next")]},
         "edges": [{"src": "g", "dst": "n", "provenance": copy.deepcopy(PROV)}]}
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert not [f for f in r.report.findings if f.code == "gap-uneven" and "g" in f.ids]


def test_nbsp_is_a_space_not_text():
    from paperfig.markup import to_html
    assert "&nbsp;" not in to_html("Swin&nbsp;Transformer") and " " in to_html("Swin&nbsp;Transformer")


def test_unknown_entities_are_rejected():
    from paperfig.blueprint import load
    from paperfig.errors import BlueprintError
    d = copy.deepcopy(MINI)
    d["root"]["children"][1]["label"] = "Enc&thinsp;oder"
    with pytest.raises(BlueprintError, match="entity"):
        load(d)


def test_sketch_accepts_a_proposed_role_without_a_name(tmp_path):
    from paperfig.sketch import _fill
    from paperfig.blueprint import load
    sk = {"root": {"id": "root", "layout": {"type": "row"},
                   "children": [{"id": "a", "label": "Encoder"}, {"id": "b", "label": "Our block", "role": "proposed"}]},
          "edges": [{"src": "a", "dst": "b"}]}
    load(_fill(sk))


def test_split_message_does_not_round_below_the_floor_up_to_it():
    from paperfig.pipeline import _fmt_pt
    assert _fmt_pt(6.96) == "6.96" and _fmt_pt(6.5) == "6.5"
