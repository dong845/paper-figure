"""Round 7 B: curved edges — a feedback loop or long cross-panel link drawn as a smooth curve through the router's
own bend points (same path, so the same obstacle checks hold)."""
import copy
import json

from conftest import MINI
from paperfig import pipeline as P
from paperfig.drawio import parse_cells


def test_curved_edge_keeps_its_route_and_is_drawn_smooth(tmp_path):
    d = copy.deepcopy(MINI)
    loop = {"src": "dec", "dst": "enc", "label": "feedback", "curved": True,
            "provenance": copy.deepcopy(d["edges"][0]["provenance"])}
    d["edges"].append(loop)
    (tmp_path / "s.json").write_text(json.dumps(dict(d, edges=d["edges"][:-1] + [dict(loop, curved=False)])))
    (tmp_path / "c.json").write_text(json.dumps(d))
    a = P.build(tmp_path / "s.json", "soft-pastel", out_dir=tmp_path / "a", formats=())
    b = P.build(tmp_path / "c.json", "soft-pastel", out_dir=tmp_path / "b", formats=())
    ca, cb = parse_cells(a.drawio.read_text()), parse_cells(b.drawio.read_text())
    ka = next(k for k, c in ca.items() if c.edge and c.source == "pf-dec" and c.target == "pf-enc")
    kb = next(k for k, c in cb.items() if c.edge and c.source == "pf-dec" and c.target == "pf-enc")
    assert cb[kb].style.get("curved") == "1" and ca[ka].style.get("curved") != "1"
    assert cb[kb].points == ca[ka].points and len(cb[kb].points) >= 2  # same bends: the curve follows the route
    others = [c for k, c in cb.items() if c.edge and k != kb and k.startswith("pf-")]
    assert all(c.style.get("curved") != "1" for c in others)
    assert {f.code for f in b.report.findings if f.severity == "error"} <= {f.code for f in a.report.findings if f.severity == "error"}
