"""Edge-layout metrics on built figures (drawio cells), the baseline for line-layout changes (user 2026-11-14:
arrowheads met in DreamerV3, lines crossed and skimmed blocks in STORM):
  short  an arrow shorter than its heads plus a 1.5-head shaft (layout._arrow_gaps)
  hug    a segment running within 0.8 heads of a box it does not connect
  cross  crossings between edges
  crowd  arrowheads of different edges closer than 1.2 heads (identical tips = one merged head, not counted)
  extra_bends / jogs  bends beyond the minimum for the edge's sides / interior segments under 2 heads (user:
         avoid needless bends)
  head_run / parallel / through_label  the lint's line-reading findings (user 2026-11-14, round 2): an arrowhead
         without a straight run behind it; two lines side by side or on top (one thick line); a line through text
Builds the corpus (and the blind STORM/DreamerV3/Swin runs if they are in the local cache) without export.
Usage: PYTHONPATH=<tree> python3 bench/route_metrics.py OUTDIR [measure]   (ONLY=storm,gat to limit;
'measure' re-measures an OUTDIR built earlier)."""
import json, math, sys
from pathlib import Path
from paperfig import pipeline as P
from paperfig.drawio import parse_cells
from paperfig.lint import _polyline
from paperfig.geometry import Box

H = Path.home() / '.cache/paper-figure/runs'
CASES = [(d.name, (d / 'blueprint.json').resolve(), json.loads((d / 'corpus.json').read_text())) for d in sorted(Path('bench/corpus').resolve().iterdir()) if (d / 'corpus.json').is_file()]
for r in ('bench-storm-20261114-1112', 'bench-dreamerv3-20261114-1112', 'bench-swin-20261114-0931'):
    if not (H / r / 'run.json').is_file():
        continue
    st = json.load(open(json.load(open(H / r / 'run.json'))['rounds'][-1]['lint_file']))['stats']['style'].split('@')[0]
    style, _, mix = st.partition('+')
    CASES.append((r.split('-')[1], H / r / 'blueprint.json', {"style": style, "mix": dict(x.split('=') for x in mix.split('+')) if mix else None}))


def metrics(drawio):
    c = parse_cells(Path(drawio).read_text())
    leaves = {k: v.box for k, v in c.items() if k.startswith('pf-') and v.vertex and v.box is not None and not v.style.get('container')}
    edges = {k: v for k, v in c.items() if v.edge and k.startswith('pf-')}
    polys = {k: _polyline(v, c) for k, v in edges.items()}
    short = hug = cross = crowd = 0
    tips = []
    for k, v in edges.items():
        p = polys[k]
        if not p:
            continue
        head = float(v.style.get('endSize', 6))
        heads = (v.style.get('startArrow', 'none') != 'none') + (v.style.get('endArrow', 'none') != 'none')
        L = sum(math.dist(a, b) for a, b in zip(p, p[1:]))
        if heads and L < (heads + 1.5) * head - 0.5:  # layout._arrow_gaps: heads + a 1.5-head shaft
            short += 1
        ends = {v.source, v.target}
        clear = 0.8 * head
        for a, b in zip(p, p[1:]):
            seglen = math.dist(a, b)
            if seglen < 2 * head:
                continue
            seg = Box(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1]))
            for lid, lb in leaves.items():
                if lid in ends:
                    continue
                if seg.intersects(lb.inflate(clear), eps=0.0) and not seg.intersects(lb, eps=0.0):
                    hug += 1
                    break
        if v.style.get('endArrow', 'none') != 'none':
            tips.append((k, p[-1], head))
        if v.style.get('startArrow', 'none') != 'none':
            tips.append((k, p[0], head))
    for i, (ka, pa, ha) in enumerate(tips):
        for kb, pb, hb in tips[i + 1:]:
            if ka != kb and 0.5 <= math.dist(pa, pb) < 1.2 * max(ha, hb):  # identical tips = one merged head
                crowd += 1
    ks = list(polys)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            for (p1, p2) in zip(polys[a], polys[a][1:]):
                for (q1, q2) in zip(polys[b], polys[b][1:]):
                    h1, h2 = abs(p1[1] - p2[1]) < 0.5, abs(q1[1] - q2[1]) < 0.5
                    if h1 == h2:
                        continue
                    H_, V_ = ((p1, p2), (q1, q2)) if h1 else ((q1, q2), (p1, p2))
                    if min(H_[0][0], H_[1][0]) + 0.5 < V_[0][0] < max(H_[0][0], H_[1][0]) - 0.5 and \
                       min(V_[0][1], V_[1][1]) + 0.5 < H_[0][1] < max(V_[0][1], V_[1][1]) - 0.5:
                        cross += 1
    extra = jogs = 0  # bends beyond the minimum for the edge's sides; interior segments shorter than 2 heads
    for k, v in edges.items():
        p = polys[k]
        if len(p) < 2 or v.source not in c or v.target not in c:
            continue
        head = float(v.style.get('endSize', 6))
        def side_of(pt, box):
            d = {'left': abs(pt[0] - box.x), 'right': abs(pt[0] - box.right), 'top': abs(pt[1] - box.y), 'bottom': abs(pt[1] - box.bottom)}
            return min(d, key=d.get)
        sb, tb = c[v.source].box, c[v.target].box
        ss, ds = side_of(p[0], sb), side_of(p[-1], tb)
        h = lambda sd: sd in ('left', 'right')
        if h(ss) != h(ds):
            need = 1
        elif ss == ds:
            need = 2
        else:
            ov = (min(sb.bottom, tb.bottom) - max(sb.y, tb.y)) if h(ss) else (min(sb.right, tb.right) - max(sb.x, tb.x))
            need = 0 if ov > 2 * head else 2
        extra += max(0, len(p) - 2 - need)
        segs = [math.dist(a, q) for a, q in zip(p, p[1:])]
        jogs += len(segs) >= 3 and min(segs[1:-1]) < 2 * head
    return dict(short=short, hug=hug, cross=cross, crowd=crowd, extra_bends=extra, jogs=int(jogs))

import os as _os
if _os.environ.get('ONLY'):
    CASES = [c for c in CASES if c[0] in _os.environ['ONLY'].split(',')]

out = {}
tot = dict(short=0, hug=0, cross=0, crowd=0, extra_bends=0, jogs=0, head_run=0, parallel=0, through_label=0)
for name, bp, cfg in CASES:
    st = cfg['style']
    st = str(bp.parent / st) if st.endswith('.json') else st
    cwd = Path.cwd()
    import os
    os.chdir(bp.parent)
    if len(sys.argv) > 2 and sys.argv[2] == 'measure':  # re-measure existing builds
        os.chdir(cwd)
        m = metrics(Path(sys.argv[1]).resolve() / name / f'{name}.drawio')
    else:
        try:
            r = P.build(bp, st, cfg.get('mix'), out_dir=Path(sys.argv[1]).resolve() / name, formats=(), name=name)
        finally:
            os.chdir(cwd)
        m = metrics(r.drawio)
        for code in ('edge-head-run', 'edge-parallel', 'edge-through-label'):
            m[code[5:].replace('-', '_')] = sum(1 for f in r.report.findings if f.code == code)
        m['min_pt'] = r.report.stats.get('smallest_text_pt')
        m['size'] = r.report.stats.get('figure_px')
    out[name] = m
    for k in tot:
        tot[k] += m.get(k, 0)
    print(f"{name:22s} {m}")
print('TOTAL', tot)
Path(sys.argv[1], 'metrics.json' if len(sys.argv) < 3 else 'metrics2.json').write_text(json.dumps(out, indent=1))
