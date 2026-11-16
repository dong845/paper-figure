"""The release zip ships the repo cards as one gzip pack (kb/cards.json.gz) and leaves out kb/index.json, so the
unpacked package stays under a skill host's 3 MB cap (user, 2026-11-16: the host also limits the unzipped size).
A run must not be able to tell: the pack loads as the same cards, and every `kb` command works on it."""
import gzip
import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from paperfig import kb
from paperfig.errors import PaperFigError

ROOT = Path(__file__).resolve().parents[1]


def _kb_dir(tmp_path, cards):
    root = tmp_path / "kb"
    for f in ("formats.json", "palettes.json", "typography.json", "styles.json", "taxonomy.json"):
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(kb.REPO_KB / f, root / f)
    (root / "cards").mkdir()
    for c in cards:
        (root / "cards" / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")
    return root


def _cards(n=3):
    base = json.loads((kb.REPO_CARDS / "clip-2021-fig1.json").read_text(encoding="utf-8"))
    return [dict(base, id=f"p{i}-2021-fig1", figure=i + 1) for i in range(n)]


def _strip(k):
    return {cid: {x: y for x, y in c.items() if x not in ("layer", "_file")} for cid, c in k.cards.items()}


def test_a_pack_loads_as_the_same_cards_as_the_loose_files(tmp_path):
    root = _kb_dir(tmp_path, _cards())
    loose = _strip(kb.load_kb(root, tmp_path / "data"))
    assert kb.write_cards_pack(root / "cards", root / kb.CARDS_PACK) == 3
    shutil.rmtree(root / "cards")
    k = kb.load_kb(root, tmp_path / "data")
    assert _strip(k) == loose and {c["layer"] for c in k.cards.values()} == {"repo"}
    assert kb.find_cards("2103.00020", 2, kb_dir=root, data=tmp_path / "data") == ["p1-2021-fig1"]
    out = kb.copy_card("p2-2021-fig1", tmp_path / "run", kb_dir=root, data=tmp_path / "data")
    assert json.loads(out.read_text()) == loose["p2-2021-fig1"]
    # the release has no index.json (generated from the cards; only this check read it): validate must not flag it
    assert not any("index.json" in p for p in kb.validate(kb_dir=root, data=tmp_path / "data"))


def test_a_loose_card_replaces_its_packed_copy(tmp_path):
    cards = _cards(2)
    root = _kb_dir(tmp_path, cards)
    kb.write_cards_pack(root / "cards", root / kb.CARDS_PACK)
    (root / "cards" / "p1-2021-fig1.json").unlink()
    (root / "cards" / "p0-2021-fig1.json").write_text(json.dumps(dict(cards[0], lesson="edited after install")))
    k = kb.load_kb(root, tmp_path / "data")
    assert k.cards["p0-2021-fig1"]["lesson"] == "edited after install" and "p1-2021-fig1" in k.cards
    assert not any("duplicate" in p for p in k.problems)


def test_a_broken_pack_fails_loudly(tmp_path):
    root = _kb_dir(tmp_path, [])
    (root / kb.CARDS_PACK).write_bytes(b"not gzip")
    with pytest.raises(PaperFigError, match="unreadable card pack"):
        kb.load_kb(root, tmp_path / "data")
    (root / kb.CARDS_PACK).write_bytes(gzip.compress(json.dumps({"count": 2, "cards": []}).encode()))
    with pytest.raises(PaperFigError, match="not a card pack"):
        kb.load_kb(root, tmp_path / "data")
    with pytest.raises(PaperFigError, match="no cards"):
        kb.write_cards_pack(root / "cards", tmp_path / "x.json.gz")


def test_the_release_zip_is_under_three_megabytes_unpacked_and_loads_every_card(tmp_path):
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    spec = importlib.util.spec_from_file_location("release_zip", ROOT / "tools" / "release_zip.py")
    rz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rz)
    r = rz.build(tmp_path / "pkg.zip", worktree=True)  # it checks the cards against the tree's own and refuses > 3 MB
    assert r["unpacked_bytes"] < 3_000_000 and r["packed_bytes"] < 3_000_000
    assert r["cards"] == len(list(kb.REPO_CARDS.glob("*.json")))
    with zipfile.ZipFile(tmp_path / "pkg.zip") as z:
        names = z.namelist()
        assert "kb/cards.json.gz" in names and "SKILL.md" in names
        assert not any(n.startswith(("cards/", "tests/", "bench/", "docs/", "tools/")) or n == "kb/index.json"
                       for n in names)
        assert not any(n.endswith(".pyc") for n in names)
        for i in z.infolist():  # unzip must give readable folders and files
            mode = i.external_attr >> 16
            assert mode & 0o444 == 0o444 and (not i.is_dir() or mode & 0o111 == 0o111), (i.filename, oct(mode))
