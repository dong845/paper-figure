"""Cards record the structure a figure draws (references/derive.md): the core relation and the spatial form each
relation takes, what each channel means, and a design-quality judgement — so a run calibrates a *derived* design
against published figures that drew the same relation, not only against figures of the same topic (user,
2026-11-15: "the skill cannot always have a reference to learn from")."""
import copy
import json

from paperfig import artifacts
from paperfig import kb as K


def _card(cid, core="pairing", rels=("pairing", "sequence"), score=4):
    base = json.loads((K.REPO_KB / "cards" / "clip-2021-fig1.json").read_text())
    c = copy.deepcopy(base)
    c["id"] = cid
    c["structure"] = {"core": {"relation": core, "what": "image and text towers face each other across the matrix"},
                      "relations": [{"type": r, "form": f"{r} drawn as published"} for r in rels],
                      "channels": {"colour": "modality", "line": "data only"},
                      "quality": {"score": score, "strengths": "the pairing is the geometry",
                                  "weaknesses": "the encoders carry no data"}}
    return c


def test_relation_vocabulary_is_one_list_for_plans_and_cards():
    plan = json.loads((K.REPO_KB.parent / "paperfig/schema/figure_plan.schema.json").read_text())
    card = json.loads((K.REPO_KB.parent / "paperfig/schema/card.schema.json").read_text())
    p = plan["properties"]["structure"]["properties"]["core"]["properties"]["relation"]["enum"]
    c = card["properties"]["structure"]["properties"]["core"]["properties"]["relation"]["enum"]
    assert p == c


def test_a_card_with_a_structure_validates_and_a_wrong_relation_does_not(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_card("x-2021-fig1")))
    assert artifacts.validate("card", good) == []
    bad = _card("y-2021-fig1", core="wiring")
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    assert any("structure" in x for x in artifacts.validate("card", p))


def test_forms_finds_published_drawings_of_a_relation_best_first():
    data = {"a-2020-fig1": _card("a-2020-fig1", core="pairing", score=3),
            "b-2021-fig1": _card("b-2021-fig1", core="sequence", rels=("sequence", "pairing"), score=5),
            "c-2022-fig1": _card("c-2022-fig1", core="pairing", score=5),
            "d-2023-fig1": _card("d-2023-fig1", core="zoom", rels=("zoom",), score=5)}
    for k, c in data.items():
        c["layer"] = "repo"
    hits = K.forms("pairing", cards=data)
    assert [h["id"] for h in hits] == ["c-2022-fig1", "a-2020-fig1", "b-2021-fig1"]  # core first, then by quality
    assert hits[0]["form"] and hits[0]["quality"] == 5
    assert [h["id"] for h in K.forms("pairing", cards=data, min_quality=4)] == ["c-2022-fig1", "b-2021-fig1"]
    assert K.forms("iteration", cards=data) == []


def test_gaps_lists_cards_without_a_structure():
    data = {"a-2020-fig1": _card("a-2020-fig1")}
    plain = _card("b-2021-fig1")
    plain.pop("structure")
    data["b-2021-fig1"] = plain
    for c in data.values():
        c["layer"] = "repo"
    assert K.gaps(cards=data)["no_structure"] == ["b-2021-fig1"]
