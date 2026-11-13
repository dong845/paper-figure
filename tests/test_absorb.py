"""Round 7 C: absorb hand edits — the author drags boxes or retypes a label in draw.io; `paperfig absorb` writes the
moves back as `pin` offsets and the label edits as labels, so the next build keeps them."""
import copy
import json
import re

from conftest import MINI
from paperfig import pipeline as P
from paperfig.absorb import absorb
from paperfig.drawio import parse_cells


def _built(tmp_path):
    (tmp_path / "blueprint.json").write_text(json.dumps(copy.deepcopy(MINI)))
    res = P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    return res.drawio.read_text()


def _move(xml, cid, dx, dy):
    m = re.search(rf'(<mxCell id="{cid}"[^>]*>\s*<mxGeometry )x="([-\d.]+)" y="([-\d.]+)"', xml)
    return xml[:m.start()] + m.group(1) + f'x="{float(m.group(2)) + dx}" y="{float(m.group(3)) + dy}"' + xml[m.end():]


def test_moves_become_pins_and_survive_a_rebuild(tmp_path):
    xml = _move(_built(tmp_path), "pf-dec", 0, 30)
    (tmp_path / "edited.drawio").write_text(xml)
    rep = absorb(tmp_path / "blueprint.json", tmp_path / "edited.drawio", "soft-pastel")
    bp = json.loads((tmp_path / "blueprint.json").read_text())
    dec = next(c for c in bp["root"]["children"] if c["id"] == "dec")
    assert dec["pin"] == [0.0, 30.0] and rep["moved"] == ["dec"]
    want = parse_cells(xml)["pf-dec"].box
    got = parse_cells(P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o2", formats=())
                      .drawio.read_text())["pf-dec"].box
    assert abs(got.x - want.x) < 1 and abs(got.y - want.y) < 1


def test_a_moved_group_pins_once(tmp_path):
    xml = _move(_built(tmp_path), "pf-csfm", 0, 25)  # children are relative: they move with it
    (tmp_path / "edited.drawio").write_text(xml)
    rep = absorb(tmp_path / "blueprint.json", tmp_path / "edited.drawio", "soft-pastel")
    assert rep["moved"] == ["csfm"]
    bp = json.loads((tmp_path / "blueprint.json").read_text())
    csfm = next(c for c in bp["root"]["children"] if c["id"] == "csfm")
    assert csfm["pin"] == [0.0, 25.0] and all("pin" not in k for k in csfm["children"])


def test_label_edits_are_absorbed(tmp_path):
    xml = _built(tmp_path).replace('value="Decoder"', 'value="Light&lt;br&gt;Decoder"')
    (tmp_path / "edited.drawio").write_text(xml)
    rep = absorb(tmp_path / "blueprint.json", tmp_path / "edited.drawio", "soft-pastel")
    bp = json.loads((tmp_path / "blueprint.json").read_text())
    assert next(c for c in bp["root"]["children"] if c["id"] == "dec")["label"] == "Light<br>Decoder"
    assert rep["relabelled"] == ["dec"]


def test_an_untouched_file_changes_nothing(tmp_path):
    xml = _built(tmp_path)
    before = (tmp_path / "blueprint.json").read_text()
    (tmp_path / "edited.drawio").write_text(xml)
    rep = absorb(tmp_path / "blueprint.json", tmp_path / "edited.drawio", "soft-pastel")
    assert rep["moved"] == [] and rep["relabelled"] == [] and (tmp_path / "blueprint.json").read_text() == before


def test_a_pin_onto_a_neighbour_fails_with_the_reason(tmp_path):
    import pytest
    from paperfig.errors import LayoutError
    d = copy.deepcopy(MINI)
    d["root"]["children"][3]["pin"] = [60, 0]  # dec onto out
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    with pytest.raises(LayoutError, match="pin.*dec.*out|dec.*pin.*out"):
        P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())


def test_a_pin_out_of_its_frame_fails_with_the_reason(tmp_path):
    import pytest
    from paperfig.errors import LayoutError
    d = copy.deepcopy(MINI)
    d["root"]["children"][2]["children"][0]["pin"] = [0, 200]  # msa out of the CSFM frame
    (tmp_path / "blueprint.json").write_text(json.dumps(d))
    with pytest.raises(LayoutError, match="outside 'csfm'"):
        P.build(tmp_path / "blueprint.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
