import pytest

from paperfig.blueprint import load
from paperfig.errors import RouteError
from paperfig.geometry import Box, segment_hits_box
from paperfig.layout import solve
from paperfig.route import route_all, find_path
from paperfig.styles import load_recipe
from conftest import leaf, PROV

R = load_recipe("soft-pastel")


def bp_of(children, edges, layout=None):
    return load({
        "schema_version": 1,
        "figure": {"type": "overview", "venue": "cvpr", "width": "double"},
        "root": {"id": "root", "layout": layout or {"type": "row"}, "children": children},
        "edges": [dict(e, provenance=PROV) for e in edges],
    })


def run(bp):
    p = solve(bp, R)
    return p, route_all(bp, p, R)


def segs(points):
    return list(zip(points, points[1:]))


def assert_clear(bp, p, routes):
    """No route segment passes through a leaf it does not connect, nor through a non-ancestor framed group."""
    for e in bp.edges:
        r = routes[e.id]
        ends = {e.src, e.dst}
        anc = set(bp.ancestors(e.src)) | set(bp.ancestors(e.dst))
        for a, b in segs(r.points):
            for el in bp.index.values():
                if el.id in ends or el.id in anc:
                    continue
                if el.is_group and el.frame == "none":
                    continue
                if any(el.id in bp.ancestors(x) for x in ends):
                    continue
                assert not segment_hits_box(a, b, p[el.id].footprint), (e.id, el.id, a, b)


def test_straight_line_between_aligned_neighbours():
    bp = bp_of([leaf("a", "A"), leaf("b", "Bbbbbbbb<br>two")], [{"src": "a", "dst": "b"}])
    p, r = run(bp)
    pts = r["e0"].points
    assert len(pts) == 2 and pts[0][1] == pts[1][1]
    assert pts[0][0] == pytest.approx(p["a"].box.right) and pts[1][0] == pytest.approx(p["b"].box.x)


def test_detours_around_blocker():
    bp = bp_of([leaf("a", "A"), leaf("b", "Blocker"), leaf("c", "C")], [{"src": "a", "dst": "c"}])
    p, r = run(bp)
    for s, t in segs(r["e0"].points):
        assert not segment_hits_box(s, t, p["b"].box)


def test_ports_spread_on_shared_side():
    col = {"id": "col", "layout": {"type": "column"}, "frame": "none", "children": [leaf("b", "B"), leaf("c", "C")]}
    bp = bp_of([leaf("a", "A<br>tall<br>box"), col], [{"src": "a", "dst": "b"}, {"src": "a", "dst": "c"}])
    p, r = run(bp)
    y0, y1 = r["e0"].points[0][1], r["e1"].points[0][1]
    assert r["e0"].points[0][0] == pytest.approx(p["a"].box.right) == r["e1"].points[0][0]
    assert y0 < y1  # sorted by the target's position: b above c
    assert y1 - y0 >= 8


def _unet():
    ch = [
        leaf("e1", "Enc 1", cell=[0, 0]), leaf("e2", "Enc 2", cell=[1, 1]), leaf("b", "Bottleneck", cell=[2, 2]),
        leaf("d2", "Dec 2", cell=[1, 3]), leaf("d1", "Dec 1", cell=[0, 4]),
    ]
    edges = [{"src": "e1", "dst": "e2"}, {"src": "e2", "dst": "b"}, {"src": "b", "dst": "d2"}, {"src": "d2", "dst": "d1"},
             {"src": "e1", "dst": "d1", "kind": "skip"}, {"src": "e2", "dst": "d2", "kind": "skip"}]
    return bp_of(ch, edges, {"type": "grid"})


def test_unet_skips_do_not_cross_nodes():
    bp = _unet()
    p, r = run(bp)
    assert_clear(bp, p, r)
    sk = [e.id for e in bp.edges if e.kind == "skip"]
    s4, s5 = segs(r[sk[0]].points), segs(r[sk[1]].points)
    for a, b in s4:
        for c, d in s5:
            if a[1] == b[1] == c[1] == d[1]:
                lo = max(min(a[0], b[0]), min(c[0], d[0])); hi = min(max(a[0], b[0]), max(c[0], d[0]))
                assert hi - lo <= 0.5, "skip connections overlap"


def test_routes_are_orthogonal_and_end_on_ports():
    bp = _unet()
    p, r = run(bp)
    for e in bp.edges:
        pts = r[e.id].points
        for a, b in segs(pts):
            assert a[0] == pytest.approx(b[0]) or a[1] == pytest.approx(b[1])
        for (x, y), eid in ((pts[0], e.src), (pts[-1], e.dst)):
            bx = p[eid].box
            on_lr = (x == pytest.approx(bx.x) or x == pytest.approx(bx.right)) and bx.y <= y <= bx.bottom
            on_tb = (y == pytest.approx(bx.y) or y == pytest.approx(p[eid].footprint.bottom)) and bx.x <= x <= bx.right
            assert on_lr or on_tb


def test_edge_into_container_allowed_border_crossing(mini_bp):
    mini_bp["edges"].append({"src": "inp", "dst": "msa", "kind": "skip", "provenance": PROV})
    bp = load(mini_bp)
    p, r = run(bp)
    assert_clear(bp, p, r)
    x, y = r[bp.edges[-1].id].points[-1]
    b = p["msa"].box
    on_v = (x == pytest.approx(b.x) or x == pytest.approx(b.right)) and b.y <= y <= b.bottom
    on_h = (y == pytest.approx(b.y) or y == pytest.approx(b.bottom)) and b.x <= x <= b.right
    assert on_v or on_h


def test_mini_figure_routes_cleanly(mini_bp):
    bp = load(mini_bp)
    p, r = run(bp)
    assert_clear(bp, p, r)


def test_first_segment_perpendicular_to_port():
    bp = _unet()
    p, r = run(bp)
    for e in bp.edges:
        rt = r[e.id]
        (x0, y0), (x1, y1) = rt.points[0], rt.points[1]
        dx, dy = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}[rt.src_side]
        assert (x1 - x0) * dx > 0 if dx else (y1 - y0) * dy > 0
        (xa, ya), (xb, yb) = rt.points[-2], rt.points[-1]
        dx, dy = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}[rt.dst_side]
        assert (xa - xb) * dx > 0 if dx else (ya - yb) * dy > 0


def test_explicit_sides_respected():
    bp = bp_of([leaf("a", "A"), leaf("b", "B")], [{"src": "a", "dst": "b", "src_side": "top", "dst_side": "top"}])
    p, r = run(bp)
    rt = r["e0"]
    assert rt.src_side == "top" and rt.dst_side == "top"
    assert rt.points[0][1] == pytest.approx(p["a"].box.y)
    assert min(y for _, y in rt.points) < p["a"].box.y


def test_no_path_raises_route_error():
    ring = [Box(-50, -50, 100, 20), Box(-50, 30, 100, 20), Box(-50, -30, 20, 60), Box(30, -30, 20, 60)]
    with pytest.raises(RouteError):
        find_path("x", (-200, 0), "right", (0, 0), "right", ring, [])


def test_find_path_simple_bend():
    pts = find_path("x", (0, 0), "right", (100, 100), "bottom", [], [])
    assert pts[0] == (0, 0) and pts[-1] == (100, 100)
    assert len(pts) == 3  # one bend


def test_main_edge_stays_straight_when_side_shared(mini_bp):
    bp = load(mini_bp)
    p, r = run(bp)
    for e in bp.edges:
        if e.kind == "data" and (e.src, e.dst) in (("enc", "csfm"), ("csfm", "dec")):
            assert len(r[e.id].points) == 2, (e.id, r[e.id].points)


def test_blocked_skip_goes_around_via_top_or_bottom(mini_bp):
    bp = load(mini_bp)
    p, r = run(bp)
    skip = next(e for e in bp.edges if e.kind == "skip")
    assert r[skip.id].src_side == r[skip.id].dst_side and r[skip.id].src_side in ("top", "bottom")
    assert len(r[skip.id].points) == 4  # down, across, up


def test_unblocked_skip_stays_horizontal():
    bp = _unet()
    p, r = run(bp)
    top_skip = next(e for e in bp.edges if e.kind == "skip" and e.src == "e1")
    assert len(r[top_skip.id].points) == 2
