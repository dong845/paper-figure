import copy
import pytest

PROV = [{"source": "draft", "ref": "Sec. 3"}]


def leaf(id, label, **kw):
    d = {"id": id, "label": label, "provenance": copy.deepcopy(PROV)}
    d.update(kw)
    return d


MINI = {
    "schema_version": 1,
    "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
    "root": {
        "id": "root",
        "layout": {"type": "row"},
        "children": [
            leaf("inp", "Input", role="io"),
            leaf("enc", "Encoder", role="reused", tone="blue"),
            {
                "id": "csfm",
                "title": "Cross-Scale Fusion Module (CSFM)",
                "role": "proposed",
                "full_name": "Cross-Scale Fusion Module",
                "abbrev": "CSFM",
                "layout": {"type": "row"},
                "provenance": copy.deepcopy(PROV),
                "children": [
                    leaf("msa", "Multi-Scale<br>Attention", role="proposed", full_name="Multi-Scale Attention"),
                    leaf("gf", "Gated<br>Fusion", role="proposed", full_name="Gated Fusion"),
                ],
            },
            leaf("dec", "Decoder", role="reused", tone="green"),
            leaf("out", "Output", role="io"),
        ],
    },
    "edges": [
        {"src": "inp", "dst": "enc", "provenance": copy.deepcopy(PROV)},
        {"src": "enc", "dst": "csfm", "provenance": copy.deepcopy(PROV)},
        {"src": "msa", "dst": "gf", "provenance": copy.deepcopy(PROV)},
        {"src": "csfm", "dst": "dec", "provenance": copy.deepcopy(PROV)},
        {"src": "dec", "dst": "out", "provenance": copy.deepcopy(PROV)},
        {"src": "enc", "dst": "dec", "kind": "skip", "provenance": copy.deepcopy(PROV)},
    ],
}


@pytest.fixture
def mini_bp():
    return copy.deepcopy(MINI)
