"""User 2026-11-14: keep only common icons in the repo; fetch any other Lucide icon on first use (cached), and
search Lucide's own tags — a fixed list always misses one. No test touches the network: the fetcher is stubbed."""
import pytest

from paperfig import icons
from paperfig.errors import PaperFigError

SVG = '<!-- @license lucide-static v0.460.0 - ISC -->\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="currentColor"><path d="M0 0h24"/></svg>'


@pytest.fixture
def net(tmp_path, monkeypatch):
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith("/tags.json"):
            return (b'{"joystick": ["game", "console", "control stick"], "gamepad-2": ["console"], "cat": ["pet"],'
                    b' "usb": ["universal", "serial", "bus", "controller", "connector"], "dices": ["dice", "game"]}')
        if url.endswith("/nope.svg"):
            return b"<html>404</html>"
        return SVG.encode()
    monkeypatch.setattr(icons, "_get", get)
    monkeypatch.setattr(icons, "CACHE", tmp_path / "icons")
    monkeypatch.delenv("PAPERFIG_OFFLINE", raising=False)
    return calls


def test_local_icon_needs_no_network(net):
    assert icons.resolve("bot").is_file() and net == []


def test_missing_icon_is_fetched_once_and_cached(net):
    p = icons.resolve("joystick")
    assert p.is_file() and "<svg" in p.read_text() and len(net) == 1
    icons.resolve("joystick")
    assert len(net) == 1  # second use reads the cache


def test_bad_names_and_non_svg_answers_are_refused(net):
    with pytest.raises(PaperFigError, match="name"):
        icons.resolve("../etc/passwd")
    with pytest.raises(PaperFigError, match="not an SVG"):
        icons.resolve("nope")


def test_offline_names_the_missing_icon(net, monkeypatch):
    monkeypatch.setenv("PAPERFIG_OFFLINE", "1")
    with pytest.raises(PaperFigError, match="joystick"):
        icons.resolve("joystick")


def test_search_uses_lucide_tags(net):
    names = [n for n, _ in icons.search("game controller")]
    assert names[0] == "joystick" and "cat" not in names  # real Lucide tags: 'control stick', not 'controller'
    assert icons.search("gamepad")[0][0] == "gamepad-2"


def test_an_icon_node_builds_with_a_fetched_icon(net, tmp_path):
    import copy
    import json
    from conftest import MINI
    from paperfig import pipeline as P
    d = copy.deepcopy(MINI)
    d["root"]["children"][0].update(visual="icon", icon="joystick", label="Action")
    (tmp_path / "b.json").write_text(json.dumps(d))
    r = P.build(tmp_path / "b.json", "soft-pastel", out_dir=tmp_path / "o", formats=())
    assert not [f for f in r.report.findings if f.severity == "error"]
