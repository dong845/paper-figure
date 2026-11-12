import pytest

from paperfig.blueprint import load, Group, Node
from paperfig.errors import BlueprintError
from conftest import leaf


def _errors(bp, **kw):
    with pytest.raises(BlueprintError) as ei:
        load(bp, **kw)
    return str(ei.value)


def test_valid_minimal_loads(mini_bp):
    bp = load(mini_bp)
    assert isinstance(bp.root, Group)
    assert isinstance(bp.index["enc"], Node)
    assert bp.parent["msa"] == "csfm"
    assert bp.parent["root"] is None
    assert len(bp.edges) == 6
    assert len({e.id for e in bp.edges}) == 6  # auto ids unique
    assert bp.index["enc"].visual == "box"  # default
    assert bp.figure.legend == "auto"  # default


def test_duplicate_id_rejected(mini_bp):
    mini_bp["root"]["children"].append(leaf("enc", "Again"))
    assert "duplicate id 'enc'" in _errors(mini_bp)


def test_unknown_edge_endpoint_rejected(mini_bp):
    mini_bp["edges"].append({"src": "enc", "dst": "nope", "provenance": [{"source": "code", "ref": "a.py:1"}]})
    assert "unknown dst 'nope'" in _errors(mini_bp)


def test_missing_provenance_rejected(mini_bp):
    del mini_bp["root"]["children"][1]["provenance"]
    assert "'enc'" in _errors(mini_bp) and "provenance" in _errors(mini_bp)


def test_text_visual_exempt_from_provenance(mini_bp):
    mini_bp["root"]["children"].append({"id": "note", "label": "inference only", "visual": "text", "role": "annotation"})
    load(mini_bp)


def test_edge_missing_provenance_rejected(mini_bp):
    del mini_bp["edges"][0]["provenance"]
    assert "provenance" in _errors(mini_bp)


def test_proposed_without_name_rejected(mini_bp):
    del mini_bp["root"]["children"][2]["children"][0]["full_name"]
    assert "'msa'" in _errors(mini_bp) and "full_name" in _errors(mini_bp)


def test_proposed_label_must_contain_name(mini_bp):
    mini_bp["root"]["children"][2]["title"] = "Fusion block"
    msg = _errors(mini_bp)
    assert "'csfm'" in msg and "CSFM" in msg


def test_proposed_name_match_ignores_markup_and_linebreaks(mini_bp):
    # label "Multi-Scale<br>Attention" must match full_name "Multi-Scale Attention"
    load(mini_bp)


def test_grid_cell_collision_rejected(mini_bp):
    mini_bp["root"]["layout"] = {"type": "grid"}
    for i, c in enumerate(mini_bp["root"]["children"]):
        c["cell"] = [0, i]
    mini_bp["root"]["children"][1]["cell"] = [0, 0]
    assert "overlap" in _errors(mini_bp)


def test_grid_span_collision_rejected(mini_bp):
    mini_bp["root"]["layout"] = {"type": "grid"}
    for i, c in enumerate(mini_bp["root"]["children"]):
        c["cell"] = [0, i]
    mini_bp["root"]["children"][0]["span"] = [1, 2]
    assert "overlap" in _errors(mini_bp)


def test_grid_child_without_cell_rejected(mini_bp):
    mini_bp["root"]["layout"] = {"type": "grid"}
    assert "cell" in _errors(mini_bp)


def test_missing_asset_file_rejected(mini_bp, tmp_path):
    mini_bp["root"]["children"][0].update(visual="image", asset={"path": "imgs/x.png", "status": "provided"})
    msg = _errors(mini_bp, base_dir=tmp_path)
    assert "imgs/x.png" in msg


def test_requested_asset_needs_no_file(mini_bp, tmp_path):
    mini_bp["root"]["children"][0].update(visual="image", asset={"status": "requested", "spec": "input LQ image"})
    load(mini_bp, base_dir=tmp_path)


def test_image_without_asset_rejected(mini_bp):
    mini_bp["root"]["children"][0]["visual"] = "image"
    assert "asset" in _errors(mini_bp)


def test_edge_to_own_ancestor_rejected(mini_bp):
    mini_bp["edges"].append({"src": "msa", "dst": "csfm", "provenance": [{"source": "code", "ref": "m.py:3"}]})
    assert "ancestor" in _errors(mini_bp)


def test_self_loop_rejected(mini_bp):
    mini_bp["edges"].append({"src": "enc", "dst": "enc", "provenance": [{"source": "code", "ref": "m.py:3"}]})
    assert "self-loop" in _errors(mini_bp)


def test_markup_tag_whitelist(mini_bp):
    mini_bp["root"]["children"][1]["label"] = "<span>Encoder</span>"
    assert "tag" in _errors(mini_bp)


def test_literal_less_than_is_fine(mini_bp):
    mini_bp["root"]["children"][1]["label"] = "t < T"
    load(mini_bp)


def test_bad_enum_rejected(mini_bp):
    mini_bp["root"]["children"][1]["visual"] = "hexagon"
    assert "hexagon" in _errors(mini_bp)


def test_all_errors_reported_together(mini_bp):
    del mini_bp["root"]["children"][1]["provenance"]
    mini_bp["edges"].append({"src": "enc", "dst": "zzz", "provenance": [{"source": "code", "ref": "a"}]})
    msg = _errors(mini_bp)
    assert "'enc'" in msg and "zzz" in msg


def test_load_from_file_resolves_assets_relative(mini_bp, tmp_path):
    import json
    from PIL import Image
    (tmp_path / "a").mkdir()
    Image.new("RGB", (4, 4)).save(tmp_path / "a" / "x.png")
    mini_bp["root"]["children"][0].update(visual="image", asset={"path": "a/x.png", "status": "provided"})
    p = tmp_path / "bp.json"
    p.write_text(json.dumps(mini_bp))
    bp = load(p)
    assert bp.index["inp"].asset.path == str(tmp_path / "a" / "x.png")


def test_auto_edge_ids_avoid_node_ids(mini_bp):
    mini_bp["root"]["children"].append(leaf("e1", "Node named e1"))
    bp = load(mini_bp)
    ids = [e.id for e in bp.edges]
    assert "e1" not in ids and len(set(ids)) == len(ids)
