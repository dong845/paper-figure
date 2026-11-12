import io
import json
import os
import zipfile

import pytest
from PIL import Image

from paperfig import bench
from paperfig.errors import PaperFigError

RPDF = os.path.expanduser("~/.cache/paper-figure/bench/restormer/paper.pdf")


def cfg(**kw):
    c = {"paper": "restormer", "title": "Restormer: Efficient Transformer for High-Resolution Image Restoration",
         "arxiv_id": "2111.09881", "venue": "cvpr", "width": "double", "figure": 2, "figure_type": "overview",
         "focus": None, "domain": "image-restoration", "blind": True,
         "code": {"repo": "swz30/Restormer", "ref": "main", "paths": ["basicsr/models/archs/restormer_arch.py"]}}
    c.update(kw)
    return c


def write_cfg(tmp_path, c):
    d = tmp_path / "bench" / c["paper"]
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(c))
    return d / "config.json"


def test_config_validation(tmp_path):
    with pytest.raises(PaperFigError, match="figure_type"):
        bench.load_config(write_cfg(tmp_path, cfg(figure_type="poster")))
    bad = cfg()
    del bad["arxiv_id"]
    with pytest.raises(PaperFigError, match="arxiv_id"):
        bench.load_config(write_cfg(tmp_path / "x", bad))


def _zip(members):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return b.getvalue()


def test_safe_unzip_rejects_path_traversal(tmp_path):
    with pytest.raises(PaperFigError, match="outside"):
        bench.safe_unzip(_zip({"repo-abc/../../evil.py": "x"}), tmp_path / "code")
    bench.safe_unzip(_zip({"repo-abc/a/b.py": "print(1)", "repo-abc/c.txt": "x"}), tmp_path / "ok")
    assert (tmp_path / "ok" / "a" / "b.py").read_text() == "print(1)"  # top-level folder stripped


@pytest.mark.skipif(not os.path.isfile(RPDF), reason="bench pdf not cached")
def test_prepare_end_to_end_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERFIG_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(bench, "_fetch_pdf", lambda arxiv_id: RPDF)
    calls = []

    def http(url, **k):
        calls.append(url)
        if "/commits/" in url:
            return json.dumps({"sha": "0123456789abcdef0123456789abcdef01234567"}).encode()
        if url.startswith("https://raw.githubusercontent.com/"):
            return b"class Restormer(nn.Module):\n    pass\n"
        raise AssertionError(url)

    monkeypatch.setattr(bench, "_http_get", http)
    rec = bench.prepare(write_cfg(tmp_path, cfg()))
    d = tmp_path / "cache" / "bench" / "restormer"
    assert rec["commit"].startswith("0123456") and (d / "code" / "basicsr/models/archs/restormer_arch.py").is_file()
    assert any("/0123456789abcdef0123456789abcdef01234567/" in u for u in calls)  # pinned to the resolved commit
    m = (d / "method.txt").read_text()
    assert "are gradually increased from the top to bottom" in m and "Figure 2." not in m  # blind method text
    assert Image.open(d / "original" / "fig2.png").size[0] > 1000
    assert json.loads((d / "prepared.json").read_text())["method_words"] > 800


def _fake_run(root, paper, arxiv, rounds, crit, lint_err=0):
    r = root / f"bench-{paper}"
    (r / "build" / "r1").mkdir(parents=True)
    png = r / "build" / "r1" / "fig.png"
    Image.new("RGB", (400, 200), "white").save(png)
    (r / "build" / "r1" / "fig.lint.json").write_text(json.dumps({"ok": lint_err == 0, "counts": {"error": lint_err, "warn": 1, "info": 2},
                                                                  "stats": {"facts_covered": "9/10"}, "findings": []}))
    (r / "run.json").write_text(json.dumps({"mode": "auto", "model": "m", "paper": {"arxiv_id": arxiv, "title": paper},
        "figure": {"type": "overview"}, "decisions": [{"point": p, "decision": "d", "by": "auto", "why": "w"} for p in bench.POINTS],
        "rounds": [{"n": i + 1, "lint": {"error": lint_err, "warn": 1, "info": 2, "ok": lint_err == 0},
                    "lint_file": str(r / "build" / "r1" / "fig.lint.json"), "critic": crit, "critic_issues": {"high": 0, "medium": 1, "low": 2}}
                   for i in range(rounds)]}))
    return r


def test_report_writes_baseline_and_sheets(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERFIG_CACHE", str(tmp_path / "cache"))
    orig = tmp_path / "cache" / "bench" / "restormer" / "original"
    orig.mkdir(parents=True)
    Image.new("RGB", (300, 150), "gray").save(orig / "fig2.png")
    write_cfg(tmp_path, cfg())
    crit = {"faithfulness": 4, "conciseness": 4, "readability": 3, "aesthetics": 3, "salience": 5}
    _fake_run(tmp_path / "runs", "restormer", "2111.09881", 2, crit)
    out = tmp_path / "out"
    base = bench.report(tmp_path / "bench", tmp_path / "runs", out)
    p = base["papers"]["restormer"]
    assert p["rounds"] == 2 and p["final_lint"]["error"] == 0 and p["critic"] == crit and p["facts_covered"] == "9/10"
    assert (out / "restormer.png").is_file() and json.loads((tmp_path / "bench" / "baseline.json").read_text())["papers"]
    assert "png" not in json.dumps(base)  # numbers only, no image paths in the baseline


def test_report_lists_papers_without_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERFIG_CACHE", str(tmp_path / "cache"))
    write_cfg(tmp_path, cfg())
    base = bench.report(tmp_path / "bench", tmp_path / "runs", tmp_path / "out")
    assert base["papers"]["restormer"]["status"] == "no run"
