"""Validation of the JSON artifacts subagents write (spec §4: the orchestrator never trusts an artifact it
did not validate). Beyond the schema, every quote is checked against the source it claims to quote:
draft/facts quotes against the method text, code excerpts against the cited file and line."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import jsonschema

from .errors import PaperFigError

SCHEMAS = {"draft-analysis": "draft_analysis", "code-analysis": "code_analysis", "refs": "refs", "facts": "facts",
           "figure-plan": "figure_plan"}
KINDS = ("draft-analysis", "code-analysis", "facts", "refs", "card", "blueprint", "figure-plan")
MIN_QUOTE = 12  # alphanumeric characters a quote (or each part around an ellipsis) needs to be verifiable
WINDOW = 3  # code excerpts may sit this many lines away from the cited line


def normalise(s: str) -> str:
    """Lower-case alphanumerics only, after NFKC (ligatures) — immune to line breaks, hyphenation, spacing."""
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", s or "").lower())


def quote_in(quote: str, norm_text: str) -> bool:
    parts = [normalise(p) for p in re.split(r"…|\.\.\.", quote or "")]
    parts = [p for p in parts if p]
    if not parts or any(len(p) < MIN_QUOTE for p in parts):
        return False
    pos = 0
    for p in parts:
        i = norm_text.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def _load(path) -> tuple[object, list[str]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), []
    except (OSError, ValueError) as e:
        return None, [f"{path}: not readable JSON ({e})"]


def _schema(kind: str, data) -> list[str]:
    schema = json.loads((Path(__file__).parent / "schema" / f"{SCHEMAS[kind]}.schema.json").read_text())
    out = []
    for err in sorted(jsonschema.Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or kind
        out.append(f"schema at {where}: {err.message}")
    return out


def _ids(items, label, probs) -> set:
    seen = set()
    for i, c in enumerate(items):
        if c.get("id") in seen:
            probs.append(f"{label}[{i}]: duplicate id '{c['id']}'")
        seen.add(c.get("id"))
    return seen


def _quotes(data, sections, norm_text, probs):
    for sec in sections:
        for i, item in enumerate(data.get(sec, [])):
            q = (item.get("provenance") or {}).get("quote", "")
            if not quote_in(q, norm_text):
                probs.append(f"{sec}[{i}]: quote not found in the method text: {q[:80]!r}")


def _draft(data, text, probs):
    if data.get("taxonomy") is not None:
        from .kb import taxonomy_problems
        probs.extend(taxonomy_problems(data["taxonomy"]))
    comp = _ids(data["components"], "components", probs)
    for i, c in enumerate(data["components"]):
        if c.get("parent") and c["parent"] not in comp:
            probs.append(f"components[{i}]: parent '{c['parent']}' is not a component")
    for i, e in enumerate(data["data_flow"]):
        for end in ("from", "to"):
            if e[end] not in comp:
                probs.append(f"data_flow[{i}]: '{e[end]}' is not a component id")
    for i, s in enumerate(data["stages"]):
        for m in s["members"]:
            if m not in comp:
                probs.append(f"stages[{i}]: member '{m}' is not a component id")
    for i, s in enumerate(data["losses"]):
        for m in s["inputs"]:
            if m not in comp:
                probs.append(f"losses[{i}]: input '{m}' is not a component id")
    for i, c in enumerate(data["contributions"]):
        for m in c["components"]:
            if m not in comp:
                probs.append(f"contributions[{i}]: component '{m}' is not a component id")
    for i, f in enumerate(data.get("existing_figures", [])):
        for m in f.get("shows", []):
            if m not in comp:
                probs.append(f"existing_figures[{i}]: '{m}' is not a component id")
    for i, a in enumerate(data["assets"]):
        if a.get("for_component") and a["for_component"] not in comp:
            probs.append(f"assets[{i}]: for_component '{a['for_component']}' is not a component id")
    for i, e in enumerate(data.get("equations", [])):
        for m in e["relates"]:
            if m not in comp:
                probs.append(f"equations[{i}]: relates '{m}' is not a component id")
    if text is not None:
        _quotes(data, ("components", "data_flow", "stages", "losses", "train_vs_infer", "contributions", "existing_figures",
                       "equations"), text, probs)


def _code(data, repo, probs):
    comp = _ids(data["components"], "components", probs)
    for i, c in enumerate(data["components"]):
        if c.get("parent") and c["parent"] not in comp:
            probs.append(f"components[{i}]: parent '{c['parent']}' is not a component")
    for i, e in enumerate(data["data_flow"]):
        for end in ("from", "to"):
            if e[end] not in comp:
                probs.append(f"data_flow[{i}]: '{e[end]}' is not a component id")
    if repo is None:
        return
    root = Path(repo).resolve()
    cache = {}
    for sec in ("components", "data_flow", "hyperparameters", "train_vs_infer"):
        for i, item in enumerate(data.get(sec, [])):
            pv = item["provenance"]
            f = (root / pv["file"]).resolve()
            if root != f and root not in f.parents:
                probs.append(f"{sec}[{i}]: file '{pv['file']}' is outside the repo")
                continue
            if f not in cache:
                try:
                    cache[f] = f.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    cache[f] = None
            lines = cache[f]
            if lines is None:
                probs.append(f"{sec}[{i}]: file '{pv['file']}' not found in the repo")
                continue
            if pv["line"] > len(lines):
                probs.append(f"{sec}[{i}]: line {pv['line']} is past the end of {pv['file']} ({len(lines)} lines)")
                continue
            n = pv["excerpt"].count("\n") + 1
            lo, hi = max(0, pv["line"] - 1 - WINDOW), min(len(lines), pv["line"] + WINDOW + n)
            ex = normalise(pv["excerpt"])
            if len(ex) < MIN_QUOTE and not any(ex == normalise(x) for x in lines[lo:hi]):
                probs.append(f"{sec}[{i}]: excerpt {pv['excerpt']!r} is too short to verify — cite the whole line or 12+ characters")
                continue
            if ex not in normalise("\n".join(lines[lo:hi])):
                probs.append(f"{sec}[{i}]: excerpt not found within {WINDOW} lines of {pv['file']}:{pv['line']}: {pv['excerpt'][:60]!r}")


def _facts(path, text, analysis, probs, repo=None):
    from .errors import BlueprintError
    from .facts import load_facts

    raw, rp = _load(path)
    if rp:
        probs.extend(rp)
        return
    sp = _schema("facts", raw)
    if sp:
        probs.extend(sp)
        return
    try:
        facts = load_facts(path)
    except BlueprintError as e:
        probs.extend(e.problems if hasattr(e, "problems") else [str(e)])
        return
    comp = stages = None
    if analysis is not None:
        a, ap = _load_analyses(analysis)
        if ap or not isinstance(a, dict):
            probs.extend(ap or [f"{analysis}: not an analysis object"])
        else:
            comp = {c.get("id") for c in a.get("components", [])}
            stages = {s.get("id") for s in a.get("stages", [])}
            succ, kids = {}, {}
            nonflow = {}
            for e in a.get("data_flow", []):
                succ.setdefault(e.get("from"), set()).add(e.get("to"))
                if e.get("kind") not in (None, "data", "skip", "train_only", "infer_only"):
                    nonflow[(e.get("from"), e.get("to"))] = e.get("kind")
            for c in a.get("components", []):
                if c.get("parent"):
                    kids.setdefault(c["parent"], set()).add(c.get("id"))
    for f in facts:
        fid = f.get("id")
        if comp is not None:
            for end in ("from", "to"):
                if f[end] not in comp:
                    probs.append(f"fact {fid}: '{f[end]}' is not a component id of the analysis")
            for v in f.get("via", []) or []:
                if v not in comp:
                    probs.append(f"fact {fid}: via '{v}' is not a component id of the analysis")
            if f.get("scope") and f["scope"] not in comp | stages:
                probs.append(f"fact {fid}: scope '{f['scope']}' is neither a component nor a stage")
            elif f.get("scope") in comp:  # a path that must stay inside a component needs both ends inside it
                inside = {f["scope"]}
                grow = True
                while grow:
                    new = {k for parent, ks in kids.items() if parent in inside for k in ks} - inside
                    grow = bool(new)
                    inside |= new
                for end in ("from", "to"):
                    if f[end] not in inside:
                        probs.append(f"fact {fid}: scope '{f['scope']}' cannot hold the path — '{f[end]}' is not inside it "
                                     "(drop the scope, or scope to a stage that contains both ends)")
            if f["from"] in comp and f["to"] in comp and not _reaches(f["from"], f["to"], succ, kids):
                probs.append(f"fact {fid}: no data_flow path from '{f['from']}' to '{f['to']}' in the analysis "
                             "(add the missing flow, or the fact is not supported)")
        if comp is not None and (f["from"], f["to"]) in nonflow and nonflow[(f["from"], f["to"])] not in (f.get("kinds") or []):
            probs.append(f"fact {fid}: the analysis draws {f['from']} → {f['to']} as a "
                         f"'{nonflow[(f['from'], f['to'])]}' edge — add \"kinds\": [\"{nonflow[(f['from'], f['to'])]}\"] so the "
                         "gate follows that edge kind (never relabel the edge as data)")
        ref = str(f.get("ref", ""))
        fp, _, ln = ref.rpartition(":")
        code_ref = bool(fp) and ln.isdigit()  # "file:line": a fact read from the code
        if repo is not None and (code_ref or text is None):  # the quote must be on (or near) the cited file:line
            src = (Path(repo) / fp).resolve() if fp else None
            if not (code_ref and src and src.is_file() and Path(repo).resolve() in src.parents):
                probs.append(f"fact {fid}: ref '{ref}' must be file:line inside the repo")
            else:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
                k = int(ln)
                win = normalise("\n".join(lines[max(0, k - 1 - WINDOW): k + WINDOW]))
                if normalise(f["quote"]) not in win:
                    probs.append(f"fact {fid}: quote not found within {WINDOW} lines of {ref}: {f['quote'][:60]!r}")
        elif text is not None and not quote_in(f["quote"], text):  # a fact read from the paper (mixed runs: either)
            probs.append(f"fact {fid}: quote not found in the method text: {f['quote'][:80]!r}")


def _family(x, kids) -> set:
    out, stack = {x}, [x]
    while stack:
        for k in kids.get(stack.pop(), ()):
            if k not in out:
                out.add(k)
                stack.append(k)
    return out


def _reaches(src, dst, succ, kids) -> bool:
    """A path along data_flow from src (or anything inside it) to dst (or anything inside it)."""
    goal, seen = _family(dst, kids), set()
    stack = list(_family(src, kids))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for m in succ.get(n, ()):
            inner = _family(m, kids)  # data entering a container reaches its parts
            if inner & goal:
                return True
            stack.extend(inner)
    return False


def _refs(data, probs):
    from .kb import paper_key

    ex = data["paper_excluded"]
    ex_keys = {paper_key(ex["title"])} | ({paper_key(ex["arxiv_id"])} if ex.get("arxiv_id") else set())
    seen = set()
    for i, s in enumerate(data["selected"]):
        keys = {paper_key(s["title"]), paper_key(s["url"])} | ({paper_key(s["arxiv_id"])} if s.get("arxiv_id") else set())
        if keys & ex_keys:
            probs.append(f"selected[{i}]: '{s['title']}' is the paper itself")
        if keys & seen:
            probs.append(f"selected[{i}]: duplicate of an earlier selection")
        seen |= keys
        if not Path(s["crop"]).is_file():
            probs.append(f"selected[{i}]: crop file {s['crop']} does not exist")
        if not s["viewed"]:
            probs.append(f"selected[{i}]: crop was not viewed — a figure may only be selected after looking at it")
    # the method family's source figure (user comparison 2026-11-15: the author's figure borrowed CLIP's similarity matrix
    # and beat a blind run that studied only neighbouring papers' layouts)
    mr = data.get("method_route")
    if mr is None:
        probs.append("method_route: run the second retrieval route — `kb match` with the analysis' taxonomy (figures of "
                     "the same paradigm / architecture) — and record query, hits, used (or why_not)")
    if isinstance(mr, dict):
        extra = [x for x in mr.get("used", []) if x not in mr.get("hits", [])]
        if extra:
            probs.append(f"method_route: used {', '.join(extra)} — not among the hits of the kb match")
        if not mr.get("used") and len((mr.get("why_not") or "").split()) < 2:
            probs.append("method_route: nothing used — say why_not (the hits draw a different structure, none found …)")
    par = data.get("paradigm")
    roles = [s for s in data["selected"] if s.get("role") == "paradigm"]
    if par is None:
        probs.append("paradigm: name the method family this paper extends and its source paper (CLIP for contrastive "
                     "image-text pretraining, U-Net, Transformer, DDPM, NeRF, GCN …), select that paper's figure with "
                     "role \"paradigm\" — or say selected: false with why_not")
    elif par["selected"] and len(roles) != 1:
        probs.append(f"paradigm: selected is true, so exactly one selected entry needs role \"paradigm\" ({len(roles)} found)")
    elif not par["selected"] and len((par.get("why_not") or "").split()) < 2:
        probs.append("paradigm: selected is false — give why_not (e.g. the source paper has no method figure)")


BRIEF_V2 = ("problem", "io", "contributions", "mechanism", "train_only", "infer_kept", "key_representations",
            "color_semantics", "annotate", "export")


def _brief_v2(data, bp, probs):
    """The design Brief (user's guide): 5 s global, 30 s contribution, 2 min mechanism; train/infer; grammar."""
    miss = [k for k in BRIEF_V2 if k not in data]
    if miss:
        probs.append(f"brief_version 2 needs: {', '.join(miss)}")
    if "layout" not in data:
        probs.append("layout: say how the figure is arranged and which reference figure it learns that from — "
                     "skeleton_from, partition (one enclosed unit per stream / stage the text separates, each with its "
                     "own losses), inputs_at, legend_at (read references/layout.md)")
    if "color_by" not in data:
        probs.append("color_by: say what the fill colour encodes — modality (a multi-modal / two-tower model: image "
                     "side, text side …; the contribution gets figure.highlight \"ring\"), role, stage or type")
    if len(data.get("contributions", [])) > 3:
        probs.append("contributions: at most 3 (the guide: a reader holds three, not more)")
    mech = data.get("mechanism")
    if mech is not None and not 1 <= len(mech) <= 2:
        probs.append("mechanism: 1 or 2 entries — the 2-minute level must exist, and only one or two zoom-ins")
    if bp is None:
        return
    brackets = {a.id for a in getattr(bp, "annotations", [])}
    drawn = {i for m in data.get("drawn_as", []) for i in m.get("ids", [])}
    _layout_vs_blueprint(data.get("layout"), bp, probs)
    _merge_consistency(data, bp, probs)

    def known(where, xs, also=()):
        for x in xs:
            if x not in bp.index and x not in brackets and x not in also:
                probs.append(f"{where}: '{x}' is not in the blueprint (node, group or bracket)")
    for i, c in enumerate(data.get("contributions", [])):
        known(f"contributions[{i}]", c["ids"])
    for i, m in enumerate(mech or []):
        known(f"mechanism[{i}]", m["ids"])
        if m.get("panel") is not None:
            el = bp.index.get(m["panel"])
            if el is None:
                probs.append(f"mechanism[{i}]: panel '{m['panel']}' is not in the blueprint")
            elif not (el.is_group and el.detail_of):
                probs.append(f"mechanism[{i}]: panel '{m['panel']}' must be a group with detail_of (the zoom-in is "
                             "linked to the block it expands)")
    known("train_only", data.get("train_only", []), drawn)  # a training-only step drawn as an edge label counts
    known("infer_kept", data.get("infer_kept", []), drawn)
    for i, k in enumerate(data.get("key_representations", [])):
        known(f"key_representations[{i}]", k["ids"])


def _figure_plan(data, facts, refs, blueprint, probs, analysis=None):
    from .kb import load_kb, paper_key

    ids = [c["id"] for c in data["concepts"]]
    if len(set(ids)) != len(ids):
        probs.append("concepts: duplicate concept id")
    if data["chosen"] not in ids:
        probs.append(f"chosen '{data['chosen']}' is not one of the concepts ({', '.join(ids)})")
    cards = set(load_kb().cards)
    known_refs = set()
    if refs is not None:
        r, rp = _load(refs)
        if isinstance(r, dict):
            for s in r.get("selected", []):
                known_refs |= {paper_key(x) for x in (s.get("arxiv_id"), s.get("title"), s.get("url")) if x}
        else:
            probs.extend(rp)
        cdir = Path(refs).parent / "cards"  # this run's own cards (MODE=run) count as references
        for f in sorted(cdir.glob("*.json")) if cdir.is_dir() else []:
            try:
                cards.add(json.loads(f.read_text(encoding="utf-8")).get("id") or f.stem)
            except (OSError, ValueError):
                cards.add(f.stem)
    for i, d in enumerate(data["data_visuals"]):  # images are real files with a recorded origin, never generated
        if d["source"] in ("repo", "dataset", "public-sample", "code-output") and not d.get("path"):
            probs.append(f"data_visuals[{i}] ({d['what']}): source '{d['source']}' needs the file's path")
        if d["source"] in ("dataset", "public-sample"):
            for k in ("licence", "url"):
                if not d.get(k):
                    probs.append(f"data_visuals[{i}] ({d['what']}): a dataset sample needs its {k}")
    for i, c in enumerate(data["concepts"]):
        if c["adapts"] == "none":  # no reference fits: designed from the material and the venue's conventions
            if len(c.get("takes", "").split()) < 3:
                probs.append(f"concepts[{i}]: adapts 'none' needs `takes` to name the conventions it follows "
                             "(venue, domain, material) — at least a short phrase")
            continue
        if c["adapts"] not in cards and paper_key(c["adapts"]) not in known_refs:
            probs.append(f"concepts[{i}]: adapts '{c['adapts']}' is neither a knowledge-base card id, a card of this "
                         "run, a selected reference, nor 'none'")
    lay = data.get("layout")
    if isinstance(lay, dict) and lay.get("skeleton_from") not in cards and paper_key(lay.get("skeleton_from") or "") not in known_refs:
        probs.append(f"layout.skeleton_from: '{lay.get('skeleton_from')}' is neither a knowledge-base card id, a card of "
                     "this run, nor a selected reference — learn the arrangement from a real figure (references/layout.md)")
    if refs is not None and isinstance(r, dict):
        par = [x for x in r.get("selected", []) if x.get("role") == "paradigm"]
        if par:
            keys = {paper_key(x) for x in (par[0].get("arxiv_id"), par[0].get("title"), par[0].get("url")) if x}
            card = par[0].get("card")
            if not any(c["adapts"] == card or paper_key(c["adapts"]) in keys for c in data["concepts"] if c["adapts"] != "none"):
                probs.append(f"concepts: none adapts the paradigm figure ('{par[0]['title']}') — one concept should take "
                             "its depiction of the core mechanism (CLIP: the image-text similarity matrix)")
    if facts is not None:
        f, fp = _load(facts)
        fids = {x.get("id") for x in (f or {}).get("facts", [])} if isinstance(f, dict) else set()
        ends = set()
        for x in (f or {}).get("facts", []) if isinstance(f, dict) else []:
            ends |= {x.get("from"), x.get("to"), *x.get("via", [])}
        probs.extend(fp)
        comps = set()
        # a component either analysis names (draft or code) may be drawn as part of something else too
        for one in (analysis if isinstance(analysis, (list, tuple)) else [analysis] if analysis is not None else []):
            an, _ = _load(one)
            comps |= {c.get("id") for c in (an or {}).get("components", [])} if isinstance(an, dict) else set()
        for i, m in enumerate(data.get("drawn_as", [])):
            for cid in m["ids"]:
                if cid not in ends and cid not in comps:
                    probs.append(f"drawn_as[{i}]: '{cid}' is neither in a fact (from / to / via) nor an analysis "
                                 "component (pass --analysis)")
        for o in data["omitted"]:
            if o["fact"] not in fids:
                probs.append(f"omitted fact '{o['fact']}' is not in the facts file")
    bp = None
    if blueprint is not None:
        from .blueprint import load
        from .errors import BlueprintError

        try:
            bp = load(blueprint)
            for cid in data["core"]:
                if cid not in bp.index:
                    probs.append(f"core '{cid}' is not in the blueprint")
            eids = {e.id for e in bp.edges}
            for i, m in enumerate(data.get("drawn_as", [])):
                for cid in m["ids"]:
                    if cid in bp.index:
                        probs.append(f"drawn_as[{i}]: '{cid}' is itself drawn in the blueprint — map only components the figure does not draw as their own element")
                if m.get("on_edge") is not None and m["on_edge"] not in eids:
                    probs.append(f"drawn_as[{i}]: on_edge '{m['on_edge']}' is not a blueprint edge id (give the edge an explicit \"id\")")
                into = m.get("into")
                for t_ in (into if isinstance(into, list) else [into] if into else []):
                    if t_ not in bp.index:
                        probs.append(f"drawn_as[{i}]: into '{t_}' is not in the blueprint")
        except BlueprintError as e:
            probs.append(f"blueprint: {e}")
            bp = None
    if data.get("brief_version") == 2:
        _brief_v2(data, bp, probs)
    if analysis is not None:
        _against_analysis(data, analysis, bp, probs)


CONTRASTIVE = ("one-to-one", "many-to-one", "many-to-many", "one-way")


def _layout_vs_blueprint(lay, bp, probs):
    """The plan's arrangement is the blueprint's (user review 2026-11-15: streams as enclosed panels, each with its
    own losses; the key at the edge)."""
    if not isinstance(lay, dict):
        return
    units = lay.get("units", []) or []
    if len(units) >= 2:
        for u in units:
            if not u.get("job"):
                probs.append(f"layout.units['{u['id']}']: give its job — teach (draws the objectives in full), extend "
                             "(reuses an earlier unit's objectives compactly and spends its space on what is new) or "
                             "same (a parallel unit drawn identically); references/layout.md § 0b")
    for u in units:
        el = bp.index.get(u["id"])
        if el is None or not el.is_group:
            probs.append(f"layout.units: '{u['id']}' is not a group in the blueprint")
            continue
        if el.frame == "none":
            probs.append(f"layout.units: '{u['id']}' has frame none — a unit is an enclosed region (frame box or "
                         "dashed, titled as the text names it): enclosure is the strongest grouping cue")
        for x in u.get("losses", []) or []:
            if x not in bp.index:
                probs.append(f"layout.units['{u['id']}']: loss '{x}' is not in the blueprint")
            elif u["id"] not in bp.ancestors(x):
                probs.append(f"layout.units['{u['id']}']: loss '{x}' is not inside '{u['id']}' — each unit draws its own "
                             "losses (draw a copy inside it and map both with drawn_as)")
    want = lay.get("legend_at")
    if want == "none":
        if bp.figure.legend != "none":
            probs.append("layout.legend_at is none but the blueprint's figure.legend is not 'none'")
    elif want and want != "auto" and getattr(bp.figure, "legend_at", "auto") != want:
        probs.append(f"layout.legend_at is '{want}' but the blueprint's figure.legend_at is "
                     f"'{getattr(bp.figure, 'legend_at', 'auto')}' — set it there")


def _merge_consistency(data, bp, probs):
    """Components drawn apart somewhere are not merged into one box elsewhere (user review 2026-11-15: the two
    encoders were separate towers in one stream and one 'F_I, F_T (shared)' box in the other). A merge inside an
    overview with the parts expanded in a detail panel is the zoom-in pattern and stays allowed."""
    targets: dict = {}
    for m in data.get("drawn_as", []) or []:
        t = m.get("into")
        nodes = t if isinstance(t, list) else [t] if t else []
        for cid in m.get("ids", []):
            targets.setdefault(cid, set()).update(n for n in nodes if n in bp.index)
    for cid in list(targets):
        if cid in bp.index:
            targets[cid].add(cid)
    owners: dict = {}
    for cid, ns in targets.items():
        for n in ns:
            owners.setdefault(n, set()).add(cid)

    def in_detail(n):
        return any(getattr(bp.index[a], "detail_of", None) for a in bp.ancestors(n))
    for n, cs in owners.items():
        if len(cs) < 2:
            continue
        apart = sorted(c for c in cs if any(len(owners[t]) == 1 and not in_detail(t) for t in targets[c]))
        if len(apart) >= 2:
            probs.append(f"drawn_as: '{n}' merged {', '.join(apart)} into one box, but the figure draws them apart "
                         "elsewhere — draw them the same way everywhere (two towers stay two towers)")


def _streams_vs_layout(data, stages, comps, bp, probs, losses_info=(), contributions=()):
    """Two or more stages / streams in the text: one enclosed unit each, drawing every loss that defines the method
    in each stream that optimises it. User's choice (2026-11-15): losses that define the supervision (contrastive /
    matching objectives), contribution losses and the plan's supervision ids must be drawn in every stream, each as
    its own element; a conventional objective (reconstruction, KL, actor-critic — DreamerV3's authors drew none) may
    go to the caption."""
    lay = data.get("layout")
    if len(stages) < 2 or not isinstance(lay, dict):
        return
    if lay.get("partition") == "single":
        probs.append(f"layout.partition is single, but the text separates {len(stages)} stages / streams "
                     f"({', '.join(s['id'] for s in stages)}) — give each its own enclosed unit (lanes, stage-panels, "
                     "lane-grid), as the text does")
        return
    units = {u.get("of"): u for u in lay.get("units", []) or [] if u.get("of")}
    for s in stages:
        if s["id"] not in units:
            probs.append(f"layout.units: no unit draws the stream / stage '{s['id']}' ({s.get('name')})")
    if bp is None:
        return
    into: dict = {}
    for m in data.get("drawn_as", []) or []:
        t = m.get("into")
        for cid in m.get("ids", []):
            into.setdefault(cid, set()).update(t if isinstance(t, list) else [t] if t else [])
    role = {c["id"]: c.get("role") for c in comps}
    skip = {(n["loss"], n["unit"]) for n in lay.get("not_drawn", []) or []}

    def norm(x):
        return re.sub(r"[^a-z0-9]", "", str(x).lower())
    by_name = {norm(c.get("name")): c["id"] for c in comps}
    method = {by_name.get(norm(x.get("name"))) for x in losses_info if x.get("positives") in CONTRASTIVE}
    for ctb in contributions:
        method |= set(ctb.get("components", []) or [])
    sup = set((data.get("supervision") or {}).get("ids", []) or [])

    def required(loss):
        return loss in method or loss in sup or role.get(loss) == "proposed" or bool(into.get(loss, set()) & sup)
    # one box standing for several of a stream's losses hides them (user review 2026-11-15: "L_fdn as in (a)")
    for s in stages:
        u = units.get(s["id"])
        if u is None:
            continue
        losses = [x for x in (s.get("losses") or [m for m in s.get("members", []) if role.get(m) == "loss"]) if required(x)]
        holders: dict = {}
        for loss in losses:
            for n in into.get(loss, set()) | ({loss} if loss in bp.index else set()):
                if n in bp.index and u["id"] in bp.ancestors(n):
                    holders.setdefault(n, set()).add(loss)
        for n, ls in holders.items():
            if len(ls) >= 2:
                probs.append(f"layout: '{n}' stands for {len(ls)} losses of stream '{s['id']}' ({', '.join(sorted(ls))}) — "
                             "draw each loss the stream optimises as its own element (size is not the limit)")
    for s in stages:
        u = units.get(s["id"])
        if u is None:
            continue
        losses = s.get("losses")
        if losses is None:
            losses = [m for m in s.get("members", []) if role.get(m) == "loss"]
        for loss in losses:
            if (loss, u["id"]) in skip or not required(loss):
                continue
            nodes = ({loss} if loss in bp.index else set()) | into.get(loss, set())
            if not any(n in bp.index and u["id"] in bp.ancestors(n) for n in nodes):
                probs.append(f"layout: stream '{s['id']}' optimises '{loss}' (analysis), but its unit '{u['id']}' does not "
                             f"draw it — each stream shows its own losses: draw it inside '{u['id']}' (map the copy with "
                             "drawn_as), or list it in layout.not_drawn with the reason")


def _against_analysis(data, analysis, bp, probs):
    """Plan decisions the analysis makes necessary (user comparison, 2026-11-15)."""
    an: dict = {"losses": [], "components": [], "existing_figures": [], "stages": [], "contributions": []}
    for one in (analysis if isinstance(analysis, (list, tuple)) else [analysis]):
        a, _ = _load(one)
        if isinstance(a, dict):
            for k in an:
                an[k].extend(a.get(k, []) or [])
    _streams_vs_layout(data, an["stages"], an["components"], bp, probs, an["losses"], an["contributions"])
    # two or more contrastive objectives: which pairs are positive IS the method — decide how it is shown
    con = [x for x in an["losses"] if x.get("positives") in CONTRASTIVE]
    sup = data.get("supervision")
    if len(con) >= 2 and sup is None:
        probs.append(f"supervision: the analysis has {len(con)} contrastive objectives "
                     f"({', '.join(x['name'] + ' ' + x['positives'] for x in con[:5])}) — what is a positive for each is "
                     "the method, not a routine loss: draw it (a pair-matrix per objective, after CLIP) and list the ids, "
                     "or give why_not")
    if sup is not None:
        if not sup.get("ids") and len((sup.get("why_not") or "").split()) < 2:
            probs.append("supervision: list the drawn ids, or give why_not")
        if bp is not None:
            for x in sup.get("ids", []):
                if x not in bp.index:
                    probs.append(f"supervision: '{x}' is not in the blueprint")
    # a module the text shows in a figure of its own stays one box here (its internals live in that figure)
    if bp is not None and an["existing_figures"]:
        kept = {e["id"] for e in data.get("expanded_despite_figure", [])}
        kids: dict = {}
        for c in an["components"]:
            if c.get("parent"):
                kids.setdefault(c["parent"], []).append(c["id"])
        for fig in an["existing_figures"]:
            for mod in fig.get("shows", []):
                if mod in kept:
                    continue
                inner, stack = [], list(kids.get(mod, []))
                while stack:
                    x = stack.pop()
                    if x in bp.index:
                        inner.append(x)
                    stack.extend(kids.get(x, []))
                if bp.index.get(mod) is not None and bp.index[mod].is_group:  # drawn as an expanded group
                    inner += [x.id for x in bp.leaves() if mod in bp.ancestors(x.id) and x.id not in inner]
                if len(inner) >= 2:
                    probs.append(f"{fig['ref']} shows '{mod}' in detail, but this figure draws its parts "
                                 f"({', '.join(sorted(set(inner))[:5])}) — keep '{mod}' one box and let {fig['ref']} "
                                 "carry the internals, or list it in expanded_despite_figure with the reason")


def _load_analyses(analysis):
    """One analysis file, or several (draft + code): their components, stages, data flows and equations merged —
    a run with both may state a flow or name a part in either (blind STORM / DreamerV3 runs crashed on the list)."""
    paths = analysis if isinstance(analysis, (list, tuple)) else [analysis]
    merged: dict = {"components": [], "stages": [], "data_flow": [], "equations": []}
    probs: list = []
    for one in paths:
        a, ap = _load(one)
        probs.extend(ap)
        if isinstance(a, dict):
            for k in merged:
                merged[k].extend(a.get(k, []) or [])
        elif not ap:
            probs.append(f"{one}: not an analysis object")
    return merged, probs


def validate(kind: str, path, text=None, repo=None, analysis=None, facts=None, refs=None, blueprint=None) -> list[str]:
    if kind not in KINDS:
        raise PaperFigError(f"unknown artifact kind '{kind}' (one of: {', '.join(KINDS)})")
    norm = None
    if text is not None:
        try:
            norm = normalise(Path(text).read_text(encoding="utf-8"))
        except OSError as e:
            raise PaperFigError(f"cannot read method text {text}: {e}") from e
    if kind == "facts":
        probs = []
        _facts(path, norm, analysis, probs, repo=repo)
        return probs
    if kind == "blueprint":
        from .blueprint import load
        from .errors import BlueprintError

        try:
            load(path)
            return []
        except BlueprintError as e:
            return list(getattr(e, "problems", [str(e)]))
    data, probs = _load(path)
    if probs:
        return probs
    if kind == "card":
        from .kb import card_problems

        return card_problems(data)
    probs = _schema(kind, data)
    if probs:
        return probs
    if kind == "draft-analysis":
        _draft(data, norm, probs)
    elif kind == "code-analysis":
        _code(data, repo, probs)
    elif kind == "refs":
        _refs(data, probs)
    elif kind == "figure-plan":
        _figure_plan(data, facts, refs, blueprint, probs, analysis)
        if analysis is not None and data.get("mechanism"):
            an, ap = _load_analyses(analysis)
            probs.extend(ap)
            eqs = {e.get("id") for e in (an or {}).get("equations", [])} if isinstance(an, dict) else set()
            for i, m in enumerate(data["mechanism"]):
                for q in m.get("equations", []):
                    if q not in eqs:
                        probs.append(f"mechanism[{i}]: equation '{q}' is not in the analysis' equations")
    return probs
