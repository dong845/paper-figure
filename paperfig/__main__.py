"""CLI: python -m paperfig build|lint|extract|codemap|refs|kb|samples|validate|run|bench|doctor|contact ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import PaperFigError


def _figure_style(path):
    import json

    try:
        return json.loads(open(path, encoding="utf-8").read()).get("figure", {}).get("style")
    except (OSError, ValueError, AttributeError):
        return None  # the build itself will report the unreadable blueprint


def parse_mix(items) -> dict:
    mix = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--mix expects section=style, got {it!r}")
        k, v = it.split("=", 1)
        mix[k.strip()] = v.strip()
    return mix


def _years(text):
    if not text:
        return None
    import re

    m = re.fullmatch(r"\s*(\d{4})\s*(?:-\s*(\d{4}))?\s*", text)
    if not m:
        raise PaperFigError(f"--years expects YYYY or YYYY-YYYY, got {text!r}")
    return int(m.group(1)), int(m.group(2) or m.group(1))


def _refs(a) -> int:
    import json

    from . import refs

    if a.refs_cmd == "search":
        venues = [v for v in (a.venues or "").split(",") if v.strip()]
        if a.title:
            res = refs.search_title(a.query)
        else:
            res = refs.search(a.query, years=_years(a.years), venues=venues or None, limit=a.limit,
                              exclude_arxiv=a.exclude_arxiv, exclude_titles=a.exclude_title)
        for n in res.notes:
            print(f"note: {n}", file=sys.stderr)
        for c in res:
            print(f"{c.year or '----'}  {(c.venue or '?')[:12]:12}  {str(c.citations if c.citations is not None else '-'):>6}  "
                  f"{c.arxiv_id or '-':12}  {c.title}")
        if a.out:
            Path(a.out).write_text(json.dumps({"query": a.query, "notes": res.notes, "candidates": [c.to_dict() for c in res]},
                                              indent=1, ensure_ascii=False), encoding="utf-8")
        if not res:
            print("no candidates", file=sys.stderr)
        return 0
    if a.refs_cmd == "fetch":
        print(refs.fetch(a.arxiv_id))
        return 0
    if a.refs_cmd == "crop":
        nums = None
        if a.figures:
            try:
                nums = {int(x) for x in a.figures.split(",") if x.strip()}
            except ValueError:
                raise PaperFigError(f"--figures expects numbers like 1,3, got {a.figures!r}") from None
        crops = refs.crop_figures(a.pdf, a.out, numbers=nums, dpi=a.dpi)
        bad = 0
        for c in crops:
            if c.problem:
                bad += 1
                print(f"fig{c.number}: PROBLEM — {c.problem}")
            else:
                print(f"fig{c.number}: page {c.page}, {c.layout}, {c.span} -> {c.png}")
        return 1 if bad else 0
    raise PaperFigError(f"unknown refs command {a.refs_cmd!r}")


def _kb(a) -> int:
    import json

    from . import kb

    if a.kb_cmd == "validate":
        probs = kb.validate()
        for p in probs:
            print(f"problem: {p}")
        k = kb.load_kb()
        layers = {L: sum(1 for c in k.cards.values() if c["layer"] == L) for L in ("repo", "user")}
        print(f"{'FAIL' if probs else 'ok'}: {len(k.formats)} venues, {len(k.palettes)} palettes, {len(k.typography)} "
              f"typography rules, {len(k.styles)} styles, {len(k.domains)} domains, {len(k.cards)} cards "
              f"(repo {layers['repo']}, user {layers['user']}); {len(probs)} problems")
        return 1 if probs else 0
    if a.kb_cmd == "query":
        brief = kb.query(a.domain, a.venue, a.exclude_paper, a.cards, run_cards=a.run_cards)
        Path(a.out).write_text(json.dumps(brief, indent=1, ensure_ascii=False), encoding="utf-8")
        for n in brief["notes"]:
            print(f"note: {n}", file=sys.stderr)
        print(f"{a.out}: format {'yes' if brief['format'] else 'no'}, {len(brief['palettes'])} palettes, "
              f"{len(brief['typography'])} rules, domain {'yes' if brief['domain'] else 'no'}, {len(brief['cards'])} cards")
        return 0
    if a.kb_cmd == "add-card":
        try:
            card = json.loads(Path(a.card).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PaperFigError(f"cannot read card {a.card}: {e}") from e
        print(kb.add_card(card))
        return 0
    if a.kb_cmd == "measure":
        from .cardmeasure import measure

        m = measure(a.png)
        if a.into:
            try:
                card = json.loads(Path(a.into).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise PaperFigError(f"cannot read card {a.into}: {e}") from e
            card["measured"] = m
            Path(a.into).write_text(json.dumps(card, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(m, indent=1))
        return 0
    raise PaperFigError(f"unknown kb command {a.kb_cmd!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="paperfig")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="blueprint -> .drawio + PNG/PDF + lint report")
    b.add_argument("blueprint")
    b.add_argument("--style", default=None, help="style recipe (default: figure.style in the blueprint, else soft-pastel)")
    b.add_argument("--mix", action="append", help="section=style, e.g. effects=depth-cv (repeatable)")
    b.add_argument("--out")
    b.add_argument("--name")
    b.add_argument("--formats", default="png,pdf")
    b.add_argument("--facts", help="facts.json (default: facts.json next to the blueprint)")
    b.add_argument("--plan", help="figure_plan.json (default: figure_plan.json next to the blueprint)")
    l = sub.add_parser("lint", help="lint an existing .drawio against its blueprint")
    l.add_argument("drawio")
    l.add_argument("--blueprint", required=True)
    l.add_argument("--style", default="soft-pastel")
    l.add_argument("--png")
    x = sub.add_parser("extract", help="draft (.tex dir/file, .pdf, .md, .docx) -> plain text")
    x.add_argument("draft")
    x.add_argument("--blind", action="store_true", help="drop figures and captions (benchmark protocol)")
    x.add_argument("--method-only", action="store_true")
    x.add_argument("--out", required=True)
    cm = sub.add_parser("codemap", help="repository -> classes / forward() map (JSON)")
    cm.add_argument("repo")
    cm.add_argument("--out", required=True)
    rf = sub.add_parser("refs", help="reference papers: search / fetch / crop figures")
    rsub = rf.add_subparsers(dest="refs_cmd", required=True)
    rs = rsub.add_parser("search", help="Semantic Scholar (arXiv fallback) -> candidate papers")
    rs.add_argument("query")
    rs.add_argument("--title", action="store_true", help="the query is an exact paper title: resolve that one paper")
    rs.add_argument("--years", help="YYYY or YYYY-YYYY")
    rs.add_argument("--venues", help="comma list, e.g. CVPR,ICCV,ECCV")
    rs.add_argument("--limit", type=int, default=20)
    rs.add_argument("--exclude-arxiv", action="append", default=[])
    rs.add_argument("--exclude-title", action="append", default=[])
    rs.add_argument("--out", help="write candidates JSON here")
    rfe = rsub.add_parser("fetch", help="download an arXiv PDF into the cache")
    rfe.add_argument("arxiv_id")
    rc = rsub.add_parser("crop", help="crop figures from a PDF by their captions")
    rc.add_argument("pdf")
    rc.add_argument("--out", required=True)
    rc.add_argument("--figures", help="comma list of figure numbers (default: all)")
    rc.add_argument("--dpi", type=int, default=200)
    kp = sub.add_parser("kb", help="knowledge base: validate / query / add-card / measure")
    ksub = kp.add_subparsers(dest="kb_cmd", required=True)
    ksub.add_parser("validate", help="check every KB entry (repo + user layer) has its source and a valid shape")
    kq = ksub.add_parser("query", help="the brief a run starts from (format, palettes, typography, domain, cards)")
    kq.add_argument("--domain", required=True)
    kq.add_argument("--venue")
    kq.add_argument("--exclude-paper", action="append", help="arXiv id, URL or title of the paper being drawn (its own "
                    "cards are left out); repeat it for figures the scout rejected as redraws of that paper")
    kq.add_argument("--cards", type=int, default=8)
    kq.add_argument("--run-cards", help="this run's card directory (RUN/refs/cards): included and ranked first")
    kq.add_argument("--out", required=True)
    ka = ksub.add_parser("add-card", help="add a figure card to the user layer")
    ka.add_argument("card")
    km = ksub.add_parser("measure", help="palette / whitespace / aspect of a figure crop")
    km.add_argument("png")
    km.add_argument("--into", help="card JSON to write the 'measured' block into")
    sp = sub.add_parser("samples", help="build a blueprint in several styles + a labelled selection sheet")
    sp.add_argument("blueprint")
    sp.add_argument("--styles", required=True, help="comma list, e.g. soft-pastel,depth-cv,editorial-minimal")
    sp.add_argument("--mix", action="append", default=[], help="section=style (applied to every sample)")
    sp.add_argument("--out", required=True)
    sp.add_argument("--facts")
    va = sub.add_parser("validate", help="check an agent artifact (schema + quotes against their sources)")
    va.add_argument("kind", choices=["draft-analysis", "code-analysis", "facts", "refs", "card", "blueprint", "figure-plan"])
    va.add_argument("file")
    va.add_argument("--text", help="method text the quotes must come from (draft-analysis, facts)")
    va.add_argument("--repo", help="repository the code excerpts must come from (code-analysis)")
    va.add_argument("--analysis", help="analysis.draft.json whose component ids facts must use (facts), whose equations "
                    "a plan's mechanism may cite (figure-plan)")
    va.add_argument("--facts", dest="facts_file", help="facts.json whose ids the plan may omit (figure-plan)")
    va.add_argument("--refs", help="refs.json whose selections a plan concept may adapt (figure-plan)")
    va.add_argument("--blueprint", dest="bp_file", help="blueprint that must contain the plan's core ids (figure-plan)")
    rp = sub.add_parser("run", help="run directory: init / decide / round / check")
    rsb = rp.add_subparsers(dest="run_cmd", required=True)
    ri = rsb.add_parser("init")
    ri.add_argument("dir")
    ri.add_argument("--mode", choices=["interactive", "auto"], required=True)
    ri.add_argument("--type", choices=["overview", "teaser", "module-detail"], required=True)
    ri.add_argument("--venue")
    ri.add_argument("--draft")
    ri.add_argument("--code")
    ri.add_argument("--title")
    ri.add_argument("--arxiv")
    ri.add_argument("--focus")
    ri.add_argument("--model")
    rd = rsb.add_parser("decide")
    rd.add_argument("dir")
    rd.add_argument("--point", required=True, choices=["blueprint", "assets", "style", "delivery"])
    rd.add_argument("--decision", required=True)
    rd.add_argument("--by", required=True, choices=["user", "auto"])
    rd.add_argument("--why", required=True)
    rr = rsb.add_parser("round")
    rr.add_argument("dir")
    rr.add_argument("--n", type=int, required=True)
    rr.add_argument("--lint", required=True, help="the build's *.lint.json")
    rr.add_argument("--critic", help="the critic's JSON report for this build")
    rr.add_argument("--critic-of", type=int, help="the reviewed round whose issues this fix build applies (no second critic)")
    rr.add_argument("--note", default="")
    rdl = rsb.add_parser("deliver", help="copy the last round's files + report to OUT and record their hashes")
    rdl.add_argument("dir")
    rdl.add_argument("--out", required=True)
    rc2 = rsb.add_parser("check")
    rc2.add_argument("dir")
    rc2.add_argument("--final", action="store_true", help="also require the delivery decision and verified delivered files")
    bp_ = sub.add_parser("bench", help="benchmark: prepare inputs / report runs")
    bsb = bp_.add_subparsers(dest="bench_cmd", required=True)
    bpr = bsb.add_parser("prepare", help="fetch PDF + code, blind method text, original crop (cache only)")
    bpr.add_argument("configs", nargs="+")
    bre = bsb.add_parser("report", help="contact sheets + baseline.json from the latest run per paper")
    bre.add_argument("bench_dir")
    bre.add_argument("--runs", required=True, help="directory holding run directories")
    bre.add_argument("--out", required=True)
    sub.add_parser("doctor", help="check Python packages, poppler and draw.io")
    c = sub.add_parser("contact", help="labelled contact sheet")
    c.add_argument("--panel", action="append", required=True, help="Label=path.png (repeatable)")
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            from . import pipeline

            fmts = tuple(x for x in a.formats.split(",") if x)
            bad = [x for x in fmts if x not in ("png", "pdf", "svg")]
            if bad:
                raise PaperFigError(f"unknown format(s): {', '.join(bad)} (use png, pdf, svg)")
            build = pipeline.build

            res = build(a.blueprint, a.style or _figure_style(a.blueprint), parse_mix(a.mix), a.out, fmts, a.name,
                        facts_path=a.facts, plan_path=a.plan)
            print(res.report.to_markdown())
            print(f"\ndrawio: {res.drawio}\npng:    {res.png}\npdf:    {res.pdf}\nlint:   {res.lint_md}")
            return 0 if res.report.ok else 1
        if a.cmd == "lint":
            from .blueprint import load
            from .lint import check
            from .pipeline import venue_width
            from .styles import compose

            bp = load(a.blueprint)
            rep = check(a.drawio, bp, compose(a.style), a.png, venue_width(bp.figure))
            print(rep.to_markdown())
            return 0 if rep.ok else 1
        if a.cmd == "extract":
            from .extract import extract_draft, method_section

            d = extract_draft(a.draft, blind=a.blind)
            text = method_section(d) if a.method_only else d.text
            Path(a.out).write_text(text, encoding="utf-8")
            for w in d.warnings:
                print(f"warning: {w}", file=sys.stderr)
            print(f"{a.out}: {len(text.split())} words, {len(d.sections)} sections ({d.source_kind}{', blind' if a.blind else ''})")
            return 0
        if a.cmd == "codemap":
            import json

            from .codemap import code_map

            m = code_map(a.repo)
            Path(a.out).write_text(json.dumps(m, indent=1), encoding="utf-8")
            print(f"{a.out}: {len(m['files'])} python files, {sum(len(f['classes']) for f in m['files'])} classes, {len(m['errors'])} parse errors")
            return 0
        if a.cmd == "refs":
            return _refs(a)
        if a.cmd == "kb":
            return _kb(a)
        if a.cmd == "bench":
            import json as _json

            from . import bench as B

            if a.bench_cmd == "prepare":
                bad = 0
                for cfgp in a.configs:
                    try:
                        r = B.prepare(cfgp)
                        print(f"{r['paper']}: {r['method_words']} method words, commit {r['commit'][:7]}, "
                              f"{r['code_files']} code files, original p{r['original_page']}")
                        for w in r["warnings"]:
                            print(f"  warning: {w}")
                    except PaperFigError as e:
                        bad += 1
                        print(f"{cfgp}: FAILED — {e}")
                return 1 if bad else 0
            base = B.report(a.bench_dir, a.runs, a.out)
            print(_json.dumps(base["summary"], indent=1))
            for k, v in base["papers"].items():
                print(f"{k:14} {v['status']:10} rounds={v.get('rounds', '-')} lint_err={v.get('final_lint', {}).get('error', '-')} "
                      f"facts={v.get('facts_covered', '-')} critic={v.get('critic', {})}")
            return 0
        if a.cmd == "doctor":
            from .doctor import check as doctor_check

            rep = doctor_check()
            for r in rep:
                print(f"{'ok  ' if r['ok'] else 'MISSING'}  {r['name']:10}  {r['detail']}")
            return 0 if all(r["ok"] for r in rep) else 1
        if a.cmd == "run":
            from . import run as R

            if a.run_cmd == "init":
                print(R.init(a.dir, a.mode, a.type, a.venue, a.draft, a.code, a.title, a.arxiv, a.focus, a.model))
            elif a.run_cmd == "decide":
                R.decide(a.dir, a.point, a.decision, a.by, a.why)
                print(f"recorded {a.point}: {a.decision}")
            elif a.run_cmd == "round":
                R.record_round(a.dir, a.n, a.lint, a.critic, a.note, critic_of=a.critic_of)
                print(f"recorded round {a.n}")
            elif a.run_cmd == "deliver":
                for f in R.deliver(a.dir, a.out):
                    print(f"delivered {f}")
            else:
                probs = R.check(a.dir, final=a.final)
                for p in probs:
                    print(f"problem: {p}")
                print(f"{'FAIL' if probs else 'ok'}: run {a.dir} ({len(probs)} problems)")
                return 1 if probs else 0
            return 0
        if a.cmd == "validate":
            from .artifacts import validate

            probs = validate(a.kind, a.file, text=a.text, repo=a.repo, analysis=a.analysis, facts=a.facts_file,
                             refs=a.refs, blueprint=a.bp_file)
            for p in probs:
                print(f"problem: {p}")
            print(f"{'FAIL' if probs else 'ok'}: {a.kind} {a.file} ({len(probs)} problems)")
            return 1 if probs else 0
        if a.cmd == "samples":
            from .samples import make_samples

            res = make_samples(a.blueprint, a.styles.split(","), parse_mix(a.mix), a.out, a.facts)
            for smp in res.shown:
                print(f"shown {smp.style}: {smp.png} ({smp.warnings} warnings)")
            for st, why in res.skipped:
                print(f"skipped {st}: {why}")
            print(f"sheet: {res.sheet}")
            return 0
        if a.cmd == "contact":
            from .contact import compose as sheet

            panels = []
            for p in a.panel:
                if "=" not in p:
                    raise SystemExit(f"--panel expects Label=path, got {p!r}")
                k, v = p.split("=", 1)
                panels.append((k, Path(v)))
            print(sheet(panels, a.out))
            return 0
    except PaperFigError as e:
        print(f"paperfig: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # never let a crash look like a lint failure (exit 1)
        import traceback

        traceback.print_exc()
        print(f"paperfig: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
