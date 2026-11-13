import json
import subprocess
import sys

import pytest

from paperfig import artifacts

TEXT = """3. Method. Our main goal is to develop an efficient Transformer model that can handle high-resolution
images for restoration tasks. Given a degraded image, Restormer first applies a convolution to obtain low-level
feature embeddings. These shallow features pass through a 4-level symmetric encoder-decoder and are trans-
formed into deep features. The Multi-Dconv Head Transposed Attention (MDTA) module computes cross-covariance
across channels."""

PROV = {"ref": "Sec. 3", "quote": "Restormer first applies a convolution to obtain low-level feature embeddings"}


def draft(**kw):
    d = {
        "paper": {"title": "Restormer", "task": "image restoration: degraded image to restored image"},
        "components": [
            {"id": "inp", "name": "Degraded image", "abbrev": None, "role": "io", "what": "input", "provenance": PROV},
            {"id": "embed", "name": "3x3 convolution", "abbrev": None, "role": "reused", "what": "embedding", "provenance": PROV},
            {"id": "mdta", "name": "Multi-Dconv Head Transposed Attention", "abbrev": "MDTA", "role": "proposed",
             "what": "channel attention", "provenance": {"ref": "Sec. 3.1", "quote": "Multi-Dconv Head Transposed Attention (MDTA) module"}},
        ],
        "data_flow": [{"from": "inp", "to": "embed", "label": None, "kind": "data", "provenance": PROV}],
        "stages": [], "losses": [], "train_vs_infer": [], "assets": [], "unclear": [],
        "contributions": [{"text": "MDTA: channel attention", "components": ["mdta"],
                           "provenance": {"ref": "Sec. 3.1", "quote": "Multi-Dconv Head Transposed Attention (MDTA) module"}}],
    }
    d.update(kw)
    return d


def write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
    return p


def test_quote_matching_tolerates_layout_noise():
    t = artifacts.normalise(TEXT)
    assert artifacts.quote_in("pass through a 4-level symmetric encoder-decoder and are transformed into deep features", t)
    assert artifacts.quote_in("Restormer first applies … low-level feature embeddings", t)  # ellipsis: parts in order
    assert not artifacts.quote_in("Restormer first applies a transformer", t)
    assert not artifacts.quote_in("embeddings … Restormer first applies", t)  # order matters


def test_draft_analysis_valid_passes(tmp_path):
    text = write(tmp_path, "m.txt", TEXT)
    assert artifacts.validate("draft-analysis", write(tmp_path, "a.json", draft()), text=text) == []


def test_draft_quote_not_in_text_is_error(tmp_path):
    d = draft()
    d["components"][2]["provenance"]["quote"] = "MDTA attends over spatial windows"
    probs = artifacts.validate("draft-analysis", write(tmp_path, "a.json", d), text=write(tmp_path, "m.txt", TEXT))
    assert any("components[2]" in p and "not found" in p for p in probs)


def test_draft_flow_and_stage_ids_checked(tmp_path):
    d = draft(data_flow=[{"from": "inp", "to": "ghost", "label": None, "kind": "data", "provenance": PROV}],
              stages=[{"id": "s1", "name": "Stage 1", "members": ["embed", "nobody"], "provenance": PROV}])
    probs = artifacts.validate("draft-analysis", write(tmp_path, "a.json", d), text=write(tmp_path, "m.txt", TEXT))
    assert any("ghost" in p for p in probs) and any("nobody" in p for p in probs)
    dup = draft()
    dup["components"].append(dict(dup["components"][0]))
    assert any("duplicate" in p for p in artifacts.validate("draft-analysis", write(tmp_path, "b.json", dup)))


def test_draft_schema_errors_reported(tmp_path):
    d = draft()
    d["components"][0]["role"] = "hero"
    assert any("role" in p for p in artifacts.validate("draft-analysis", write(tmp_path, "a.json", d)))
    assert any("JSON" in p for p in artifacts.validate("draft-analysis", write(tmp_path, "c.json", "{not json")))


def code_doc(**kw):
    d = {"repo": "r", "commit": None,
         "components": [{"id": "mdta", "symbol": "Attention", "paper_name": "MDTA", "role": "proposed", "what": "attention",
                         "provenance": {"file": "arch.py", "line": 3, "excerpt": "class Attention(nn.Module):"}}],
         "data_flow": [], "hyperparameters": [], "train_vs_infer": [], "assets": [], "unclear": []}
    d.update(kw)
    return d


def test_code_analysis_excerpt_checked_at_line(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "arch.py").write_text("import torch\nfrom torch import nn\nclass Attention(nn.Module):\n    def forward(self, x):\n        return x\n")
    assert artifacts.validate("code-analysis", write(tmp_path, "c.json", code_doc()), repo=repo) == []
    bad = code_doc()
    bad["components"][0]["provenance"].update(line=5)  # still within +-3 lines: ok
    assert artifacts.validate("code-analysis", write(tmp_path, "c2.json", bad), repo=repo) == []
    far = code_doc()
    far["components"][0]["provenance"].update(excerpt="class Attention(nn.Module, Mixin):")
    assert any("excerpt" in p for p in artifacts.validate("code-analysis", write(tmp_path, "c3.json", far), repo=repo))
    out = code_doc()
    out["components"][0]["provenance"].update(file="../outside.py")
    assert any("outside the repo" in p for p in artifacts.validate("code-analysis", write(tmp_path, "c4.json", out), repo=repo))
    gone = code_doc()
    gone["components"][0]["provenance"].update(file="nope.py")
    assert any("nope.py" in p for p in artifacts.validate("code-analysis", write(tmp_path, "c5.json", gone), repo=repo))


def test_facts_ids_and_quotes_cross_checked(tmp_path):
    a = write(tmp_path, "a.json", draft())
    facts = {"facts": [{"id": "f1", "from": "inp", "to": "embed", "quote": "first applies a convolution", "ref": "Sec. 3"},
                       {"id": "f2", "from": "inp", "to": "decoder", "quote": "4-level symmetric encoder-decoder", "ref": "Sec. 3"},
                       {"id": "f3", "from": "inp", "to": "mdta", "quote": "an invented sentence about MDTA", "ref": "Sec. 3"}]}
    probs = artifacts.validate("facts", write(tmp_path, "f.json", facts), text=write(tmp_path, "m.txt", TEXT), analysis=a)
    assert any("f2" in p and "decoder" in p for p in probs)
    assert any("f3" in p and "not found" in p for p in probs)
    assert not any("f1" in p for p in probs)


def test_refs_selection_checked(tmp_path):
    crop = tmp_path / "fig2.png"
    crop.write_bytes(b"png")
    sel = lambda **k: dict({"title": "SwinIR: Image Restoration Using Swin Transformer", "arxiv_id": "2108.10257",
                            "url": "https://arxiv.org/abs/2108.10257", "venue": "ICCV", "year": 2021, "why": "same task",
                            "figure": 2, "crop": str(crop), "caption": "Figure 2. The architecture", "viewed": True}, **k)
    doc = {"paper_excluded": {"arxiv_id": "2111.09881", "title": "Restormer"}, "queries": [{"query": "image restoration transformer",
           "years": None, "venues": None, "results": 12, "notes": []}], "selected": [sel()], "rejected": [], "notes": []}
    assert artifacts.validate("refs", write(tmp_path, "r.json", doc)) == []
    doc["selected"] = [sel(), sel(arxiv_id="2111.09881v2", title="Restormer: Efficient Transformer"), sel(crop=str(tmp_path / "missing.png")),
                       sel(viewed=False, arxiv_id="2205.00001", title="Other")]
    probs = artifacts.validate("refs", write(tmp_path, "r2.json", doc))
    assert any("the paper itself" in p for p in probs) and any("missing.png" in p for p in probs)
    assert any("viewed" in p for p in probs) and any("duplicate" in p for p in probs)


def test_validate_cli(tmp_path):
    text = write(tmp_path, "m.txt", TEXT)
    ok = write(tmp_path, "a.json", draft())
    r = subprocess.run([sys.executable, "-m", "paperfig", "validate", "draft-analysis", str(ok), "--text", str(text)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stdout + r.stderr
    d = draft()
    d["components"][1]["provenance"] = {"ref": "Sec. 3", "quote": "nowhere in the text at all"}
    bad = write(tmp_path, "b.json", d)
    r = subprocess.run([sys.executable, "-m", "paperfig", "validate", "draft-analysis", str(bad), "--text", str(text)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "not found" in r.stdout


def test_code_analysis_parent_must_exist(tmp_path):
    d = code_doc()
    d["components"][0]["parent"] = "ghost_block"
    assert any("ghost_block" in p for p in artifacts.validate("code-analysis", write(tmp_path, "c.json", d)))


def test_code_excerpt_too_short_is_rejected_unless_whole_line(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text("def f(x, y):\n    z = x + y\n    return z\n")
    d = code_doc()
    d["components"][0]["provenance"] = {"file": "m.py", "line": 2, "excerpt": "x + y"}  # fragment: matches anywhere
    assert any("too short" in p for p in artifacts.validate("code-analysis", write(tmp_path, "a.json", d), repo=repo))
    d["components"][0]["provenance"]["excerpt"] = "z = x + y"  # the whole (short) line is fine
    assert artifacts.validate("code-analysis", write(tmp_path, "b.json", d), repo=repo) == []


def test_fact_needs_a_path_in_the_analysis_flow(tmp_path):
    d = draft()
    d["components"].append({"id": "sub", "name": "Inner conv", "abbrev": None, "role": "reused", "what": "x",
                            "parent": "embed", "provenance": PROV})
    a = write(tmp_path, "a.json", d)
    facts = {"facts": [{"id": "ok", "from": "inp", "to": "embed", "quote": "first applies a convolution", "ref": "Sec. 3"},
                       {"id": "into", "from": "inp", "to": "sub", "quote": "first applies a convolution", "ref": "Sec. 3"},
                       {"id": "made_up", "from": "mdta", "to": "inp", "quote": "first applies a convolution", "ref": "Sec. 3"}]}
    probs = artifacts.validate("facts", write(tmp_path, "f.json", facts), analysis=a)
    assert any("made_up" in p and "no data_flow path" in p for p in probs)
    assert not any("'ok'" in p or "fact ok:" in p or "fact into:" in p for p in probs), probs


def test_contributions_checked(tmp_path):
    d = draft()
    d["contributions"][0]["components"] = ["nope"]
    assert any("contributions[0]" in p and "nope" in p for p in artifacts.validate("draft-analysis", write(tmp_path, "a.json", d)))
    del d["contributions"]
    assert any("contributions" in p for p in artifacts.validate("draft-analysis", write(tmp_path, "b.json", d)))


def test_facts_schema_rejects_unknown_keys(tmp_path):
    facts = {"facts": [{"id": "f1", "from": "inp", "to": "embed", "quote": "first applies a convolution", "ref": "Sec. 3",
                        "vias": ["x"]}]}
    assert any("vias" in p for p in artifacts.validate("facts", write(tmp_path, "f.json", facts)))


def test_equation_quote_checked(tmp_path):
    """Round 3 (user's guide §5: formulas guarantee the mechanism): the analysis records the contribution's key
    equations verbatim, tied to components; a plan's mechanism may cite them."""
    text = write(tmp_path, "m.txt", TEXT)
    eq = {"id": "eq_mdta", "text": "A = softmax(K·Q / α)", "relates": ["mdta"],
          "provenance": {"ref": "Eq. 1", "quote": "computes cross-covariance across channels"}}
    assert artifacts.validate("draft-analysis", write(tmp_path, "a.json", draft(equations=[eq])), text=text) == []
    bad = dict(eq, provenance={"ref": "Eq. 1", "quote": "computes attention over pixels"})
    probs = artifacts.validate("draft-analysis", write(tmp_path, "b.json", draft(equations=[bad])), text=text)
    assert any("equations[0]" in p and "not found" in p for p in probs), probs
    probs = artifacts.validate("draft-analysis", write(tmp_path, "c.json", draft(equations=[dict(eq, relates=["ghost"])])), text=text)
    assert any("ghost" in p for p in probs), probs
