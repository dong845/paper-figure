"""Knowledge base (spec §6): a read-only layer shipped in the repo (``kb/``) plus a user layer that
grows with use (``$PAPERFIG_DATA`` or ``~/.local/share/paper-figure``). Every entry carries its source;
``validate`` rejects anything unsourced. ``query`` assembles the brief a run starts from."""
from __future__ import annotations

import gzip
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from .color import de2000, simulate
from .errors import PaperFigError

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_KB = REPO_ROOT / "kb"
# Cards and domain notes sit at the top level, not under kb/: a skill package allows one directory level (root/dir/file).
REPO_CARDS = REPO_ROOT / "cards"
# The release zip (tools/release_zip.py) ships the repo cards as one gzip file in the kb dir instead of cards/*.json:
# the same cards, byte for byte, in a fifth of the space (a skill host caps the unpacked package at 3 MB).
CARDS_PACK = "cards.json.gz"
REPO_DOMAINS = REPO_ROOT / "domains"
CARD_SCHEMA = REPO_ROOT / "schemas" / "card.schema.json"
PALETTE_KINDS = {"qualitative", "sequential", "diverging"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ARXIV = re.compile(r"(\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.I)


SAFETY_METHOD = ("computed: paperfig.kb.palette_safety — minimum pairwise CIEDE2000 between the palette's colours "
                 "as seen normally, under Machado et al. 2009 protan/deutan/tritan simulation (severity 1.0), "
                 "and in grayscale (Rec. 709 luminance)")


def palette_safety(colors) -> dict:
    """How far apart the palette's colours stay for each kind of reader (higher = safer)."""
    out = {}
    for kind in ("normal", "protan", "deutan", "tritan", "gray"):
        seen = [c if kind == "normal" else simulate(c, kind) for c in colors]
        out[kind] = round(min((de2000(a, b) for i, a in enumerate(seen) for b in seen[i + 1:]), default=0.0), 2)
    return {"source": SAFETY_METHOD, "min_de": out}


def data_dir() -> Path:
    return Path(os.environ.get("PAPERFIG_DATA") or Path.home() / ".local" / "share" / "paper-figure")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def paper_key(s: str) -> str:
    """One key per paper whatever form it is given in: arXiv abs/pdf URL, 'arXiv:ID', bare ID, other URL, or title."""
    s = (s or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/" + _ARXIV.pattern + r"(?:\.pdf)?/?$", s, re.I)
    if m:
        return "arxiv:" + m.group(1).lower()
    m = re.match(r"^(?:arxiv:)?" + _ARXIV.pattern + "$", s, re.I)
    if m:
        return "arxiv:" + m.group(1).lower()
    if re.match(r"^https?://", s, re.I):
        return "url:" + re.sub(r"^https?://(www\.)?", "", s.lower()).rstrip("/")
    return "title:" + _norm_title(s)


def _card_keys(c: dict) -> set:
    return {paper_key(c.get("paper_url", "")), "title:" + _norm_title(c.get("title", ""))}


@dataclass
class KB:
    root: Path
    data: Path
    formats: dict = field(default_factory=dict)
    palettes: dict = field(default_factory=dict)
    typography: list = field(default_factory=list)
    principles: list = field(default_factory=list)
    styles: dict = field(default_factory=dict)
    domains: dict = field(default_factory=dict)
    cards: dict = field(default_factory=dict)  # id -> card (with "layer": repo|user)
    problems: list = field(default_factory=list)  # found while loading (unreadable files, collisions)


def _read(path: Path, problems: list, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{label}: missing file {path}")
    except (OSError, ValueError) as e:
        problems.append(f"{label}: unreadable JSON ({e})")
    return None


def card_problems(c: dict) -> list[str]:
    if not isinstance(c, dict):
        return ["card: not a JSON object"]
    schema = json.loads(CARD_SCHEMA.read_text())
    probs = []
    for err in sorted(jsonschema.Draft202012Validator(schema).iter_errors(c), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "card"
        probs.append(f"schema at {where}: {err.message}")
    src = c.get("source") if isinstance(c.get("source"), dict) else {}
    if src and isinstance(c.get("paper_url"), str) and isinstance(src.get("paper_url"), str):
        if paper_key(src["paper_url"]) != paper_key(c["paper_url"]):
            probs.append("source.paper_url names a different paper than paper_url")
    if src and isinstance(src.get("figure"), int) and isinstance(c.get("figure"), int) and src["figure"] != c["figure"]:
        probs.append("source.figure differs from figure")
    probs += taxonomy_problems(c.get("taxonomy"))
    f = c.get("fetch")
    if isinstance(f, dict):
        if not f.get("arxiv_id") and not (f.get("pdf_url") and f.get("key")):
            probs.append("fetch: give arxiv_id, or pdf_url with a key")
        if isinstance(f.get("figure"), int) and isinstance(c.get("figure"), int) and f["figure"] != c["figure"]:
            probs.append("fetch.figure differs from figure")
    return probs


TAXONOMY = REPO_KB / "taxonomy.json"


def load_taxonomy(kb_dir=None) -> dict:
    p = (Path(kb_dir) / "taxonomy.json") if kb_dir else TAXONOMY
    return json.loads(p.read_text(encoding="utf-8"))


def taxonomy_problems(t, kb_dir=None) -> list[str]:
    """A card's (or an analysis') `taxonomy` against the controlled vocabulary in kb/taxonomy.json."""
    if t is None:
        return []
    if not isinstance(t, dict):
        return ["taxonomy: not an object"]
    voc = load_taxonomy(kb_dir)
    probs, other = [], False
    if t.get("family") is not None:
        if t["family"] not in voc["family"]:
            probs.append(f"taxonomy.family '{t['family']}' is not in kb/taxonomy.json (use 'other' + note)")
        other |= t["family"] == "other"
    for key in ("architecture", "training", "depicts"):
        for v in t.get(key, []) or []:
            if v not in voc[key]:
                probs.append(f"taxonomy.{key} '{v}' is not in kb/taxonomy.json (use 'other' + note)")
            other |= v == "other"
    for v in t.get("modality", []) or []:
        if v not in voc["modality"]:
            probs.append(f"taxonomy.modality '{v}' is not in kb/taxonomy.json")
    if other and len((t.get("note") or "").split()) < 2:
        probs.append("taxonomy: a value is 'other' — say what it is in note (recurring notes become vocabulary, `kb gaps`)")
    return probs


def fetch_recipe(c: dict) -> tuple:
    """(cache key, pdf url or None, figure) — how to download and crop this figure again."""
    f = c.get("fetch") if isinstance(c.get("fetch"), dict) else {}
    fig = f.get("figure") or c.get("figure")
    if f.get("arxiv_id"):
        return f["arxiv_id"], None, fig
    if f.get("pdf_url"):
        return f.get("key"), f["pdf_url"], fig
    m = re.search(r"(\d{4}\.\d{4,5})", str(c.get("paper_url", "")))
    if m:
        return m.group(1), None, fig
    return None, None, fig


def _index_entry(cid: str, c: dict) -> dict:
    key, url, fig = fetch_recipe(c)
    return {"id": cid, "title": c.get("title"), "paper_url": c.get("paper_url"), "venue": c.get("venue"),
            "year": c.get("year"), "figure": c.get("figure"), "figure_type": c.get("figure_type"),
            "domains": c.get("domains"), "layout_pattern": c.get("layout_pattern"),
            "taxonomy": c.get("taxonomy"), "arrangement": c.get("arrangement"), "insights": c.get("insights"),
            "structure": c.get("structure"),
            "lesson": c.get("lesson"), "fetch": {"key": key, "pdf_url": url, "figure": fig}}


def build_index(kb_dir=None, data=None, layers=("repo",)) -> dict:
    """kb/index.json: one entry per figure card with its facets and its download recipe — generated, never edited."""
    k = load_kb(kb_dir, data)
    figs = [_index_entry(cid, c) for cid, c in sorted(k.cards.items()) if c.get("layer") in layers]
    return {"about": "Generated by `paperfig kb index` from cards/ — do not edit. Facets use kb/taxonomy.json.",
            "count": len(figs), "figures": figs}


def write_index(kb_dir=None, data=None) -> Path:
    root = Path(kb_dir) if kb_dir else REPO_KB
    out = root / "index.json"
    out.write_text(json.dumps(build_index(kb_dir, data), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def match(paradigm=None, family=None, architecture=(), training=(), partition=None, modality=(),
          exclude_paper=None, n=8, kb_dir=None, data=None) -> list[dict]:
    """Figures of the same method, ranked: paradigm 4 (+1 for the paradigm's own source figure), family 3, each shared
    architecture 2, training 1, modality 0.5, partition 1; an overview / composite +1, a teaser -1. Only figures that
    share at least one method facet are returned."""
    k = load_kb(kb_dir, data)
    ex = {paper_key(x) for x in (exclude_paper or []) if x}
    hits = []
    for cid, c in k.cards.items():
        t = c.get("taxonomy")
        if not isinstance(t, dict) or (ex and ex & _card_keys(c)):
            continue
        why, score = [], 0.0
        if paradigm and str(t.get("paradigm", "")).lower() == str(paradigm).lower():
            score += 4; why.append(f"paradigm {t['paradigm']}")
        if family and t.get("family") == family:
            score += 3; why.append(f"family {family}")
        for a in set(architecture or []) & set(t.get("architecture", [])):
            score += 2; why.append(f"architecture {a}")
        for a in set(training or []) & set(t.get("training", [])):
            score += 1; why.append(f"training {a}")
        if not why:
            continue
        for a in set(modality or []) & set(t.get("modality", [])):
            score += 0.5
        arr = c.get("arrangement") if isinstance(c.get("arrangement"), dict) else {}
        if partition and arr.get("partition") == partition:
            score += 1; why.append(f"partition {partition}")
        # a method figure teaches more than a teaser; the paradigm's own source figure carries the field's picture
        score += {"overview": 1.0, "composite": 1.0, "module-detail": 0.0, "teaser": -1.0}.get(c.get("figure_type"), 0.0)
        if paradigm and t.get("paradigm_source") and str(t.get("paradigm", "")).lower() == str(paradigm).lower():
            score += 1; why.append("the paradigm's source figure")
        e = _index_entry(cid, c)
        e.update(score=score, why=why)
        hits.append(e)
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:max(0, int(n))]


def forms(relation: str, n: int = 8, min_quality: int = 1, exclude_paper=None, kb_dir=None, data=None,
          cards: dict | None = None) -> list[dict]:
    """Published figures that draw `relation` (references/derive.md), for calibrating a derived design: figures
    whose core relation it is first, then those that draw it as a secondary relation; within each, the better
    designed first (structure.quality.score), then by id. Each hit carries the form that figure gives it."""
    allc = cards if cards is not None else load_kb(kb_dir, data).cards
    ex = {paper_key(x) for x in (exclude_paper or []) if x}
    hits = []
    for cid, c in allc.items():
        st = c.get("structure")
        if not isinstance(st, dict) or (ex and ex & _card_keys(c)):
            continue
        q = int((st.get("quality") or {}).get("score") or 0)
        if q < min_quality:
            continue
        core = (st.get("core") or {}).get("relation") == relation
        form = next((r.get("form") for r in st.get("relations", []) or [] if r.get("type") == relation), None)
        if not core and form is None:
            continue
        hits.append({"id": cid, "title": c.get("title"), "venue": c.get("venue"), "year": c.get("year"),
                     "core": core, "form": (st.get("core") or {}).get("what") if core and not form else form,
                     "quality": q, "strengths": (st.get("quality") or {}).get("strengths"),
                     "weaknesses": (st.get("quality") or {}).get("weaknesses"), "lesson": c.get("lesson")})
    hits.sort(key=lambda h: (not h["core"], -h["quality"], h["id"]))
    return hits[:max(0, int(n))]


def gaps(kb_dir=None, data=None, thin=3, cards: dict | None = None) -> dict:
    """What to add next: cards without facets or structure, recurring 'other' notes (new vocabulary), thin
    families."""
    k = load_kb(kb_dir, data)
    if cards is not None:
        k.cards = cards
    voc = load_taxonomy(kb_dir)
    untagged = sorted(cid for cid, c in k.cards.items() if not isinstance(c.get("taxonomy"), dict))
    notes: dict = {}
    fam: dict = {f: 0 for f in voc["family"] if f != "other"}
    for c in k.cards.values():
        t = c.get("taxonomy")
        if not isinstance(t, dict):
            continue
        if t.get("family") in fam:
            fam[t["family"]] += 1
        if t.get("note") and ("other" in [t.get("family")] + list(t.get("architecture", [])) + list(t.get("training", []))
                              + list(t.get("depicts", []))):
            key = " ".join(t["note"].lower().split())
            notes[key] = notes.get(key, 0) + 1
    known = {x.lower() for x in voc.get("paradigms", [])}
    new_par: dict = {}
    for c in k.cards.values():
        par = (c.get("taxonomy") or {}).get("paradigm") if isinstance(c.get("taxonomy"), dict) else None
        if par and par.lower() not in known:
            new_par[par] = new_par.get(par, 0) + 1
    no_fetch = sorted(cid for cid, c in k.cards.items() if not fetch_recipe(c)[0])
    no_structure = sorted(cid for cid, c in k.cards.items() if not isinstance(c.get("structure"), dict))
    return {"untagged": untagged, "no_fetch": no_fetch, "no_structure": no_structure, "other_notes": sorted(notes.items(), key=lambda x: (-x[1], x[0])),
            "new_paradigms": sorted(new_par.items(), key=lambda x: (-x[1], x[0])),
            "thin_families": sorted(f for f, n in fam.items() if n < thin), "family_counts": fam}


def write_cards_pack(cards_dir: Path, out: Path) -> int:
    """Pack every cards/*.json into one gzip file (CARDS_PACK) that _load_cards reads like the loose files."""
    cards = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(cards_dir).glob("*.json"))]
    if not cards:
        raise PaperFigError(f"no cards to pack in {cards_dir}")
    body = json.dumps({"about": "The repo's cards/*.json in one file (tools/release_zip.py) — do not edit; edit "
                                "cards/<id>.json in the repo.", "count": len(cards), "cards": cards},
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    Path(out).write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    return len(cards)


def _read_pack(pack: Path) -> list[dict]:
    """A shipped pack that cannot be read is a broken install, not an empty knowledge base: fail loudly."""
    try:
        data = json.loads(gzip.decompress(pack.read_bytes()).decode("utf-8"))
    except (OSError, EOFError, ValueError) as e:
        raise PaperFigError(f"{pack}: unreadable card pack ({e}) — reinstall the skill") from e
    cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(cards, list) or data.get("count") != len(cards):
        raise PaperFigError(f"{pack}: not a card pack (needs 'cards' and a matching 'count') — reinstall the skill")
    return cards


def _load_cards(d: Path, layer: str, k: KB, pack: Path | None = None) -> None:
    packed = set()
    if pack is not None and pack.is_file():
        for c in _read_pack(pack):
            cid = c.get("id") if isinstance(c, dict) else None
            if not isinstance(cid, str) or cid in k.cards:
                k.problems.append(f"{layer}: {pack.name}: a card without an id or with a duplicate id ({cid!r})")
                continue
            # its file name in the repo, so labels and the id = file-name check read as for a loose card
            k.cards[cid] = dict(c, layer=layer, _file=str(d / f"{cid}.json"))
            packed.add(cid)
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.json")):
        c = _read(f, k.problems, f"{layer}: cards/{f.name}")
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if cid in packed:  # a card edited or added after install (MODE=repo) replaces its packed copy
            packed.discard(cid)
        elif cid in k.cards:
            k.problems.append(f"{layer}: cards/{f.name}: duplicate card id '{cid}' (already in the {k.cards[cid]['layer']} layer)")
            continue
        c = dict(c, layer=layer, _file=str(f))
        k.cards[cid if isinstance(cid, str) else f.stem] = c


def load_kb(kb_dir=None, data=None) -> KB:
    root = Path(kb_dir) if kb_dir else REPO_KB
    k = KB(root, Path(data) if data else data_dir())
    f = _read(root / "formats.json", k.problems, "formats")
    k.formats = (f or {}).get("venues", {}) if isinstance(f, dict) else {}
    p = _read(root / "palettes.json", k.problems, "palettes")
    k.palettes = (p or {}).get("palettes", {}) if isinstance(p, dict) else {}
    t = _read(root / "typography.json", k.problems, "typography")
    k.typography = (t or {}).get("rules", []) if isinstance(t, dict) else []
    pr = _read(root / "principles.json", k.problems, "principles") if (root / "principles.json").is_file() else None
    k.principles = (pr or {}).get("rules", []) if isinstance(pr, dict) else []
    s = _read(root / "styles.json", k.problems, "styles")
    k.styles = (s or {}).get("styles", {}) if isinstance(s, dict) else {}
    ddir = REPO_DOMAINS if root == REPO_KB else root / "domains"  # another kb_dir (tests) keeps both inside it
    for df in sorted(ddir.glob("*.json")) if ddir.is_dir() else []:
        d = _read(df, k.problems, f"domains/{df.name}")
        if isinstance(d, dict):
            k.domains[d.get("id") or df.stem] = dict(d, _file=str(df))
    _load_cards(REPO_CARDS if root == REPO_KB else root / "cards", "repo", k, pack=root / CARDS_PACK)
    _load_cards(k.data / "cards", "user", k)
    return k


def _src_ok(src, need=("url",)) -> bool:
    return isinstance(src, dict) and all(isinstance(src.get(n), str) and src[n].strip() for n in need) \
        and str(src.get("url", "")).startswith(("http://", "https://"))


def validate(kb_dir=None, data=None) -> list[str]:
    k = load_kb(kb_dir, data)
    probs = list(k.problems)
    for key, v in k.formats.items():
        if not isinstance(v, dict) or not str(v.get("source_url", "")).startswith("http") or not v.get("evidence"):
            probs.append(f"formats.{key}: no source (needs source_url + evidence)")
            continue
        for n in ("textwidth_in", "columnwidth_in"):
            if not isinstance(v.get(n), (int, float)) or v[n] <= 0:
                probs.append(f"formats.{key}: {n} must be a positive number")
    for key, v in k.palettes.items():
        if not isinstance(v, dict):
            probs.append(f"palettes.{key}: not an object")
            continue
        if not _src_ok(v.get("source"), ("url", "read")):
            probs.append(f"palettes.{key}: no source (needs source.url + source.read)")
        cols = v.get("colors")
        if not isinstance(cols, list) or len(cols) < 2 or not all(isinstance(c, str) and _HEX.match(c) for c in cols):
            probs.append(f"palettes.{key}: colors must be a list of at least 2 #rrggbb values")
        if v.get("kind") not in PALETTE_KINDS:
            probs.append(f"palettes.{key}: kind must be one of {sorted(PALETTE_KINDS)}")
        if "safety" in v:
            if not str((v["safety"] or {}).get("source", "")).startswith("computed:"):
                probs.append(f"palettes.{key}: safety must carry source 'computed: ...'")
            elif isinstance(cols, list) and all(isinstance(c, str) and _HEX.match(c) for c in cols):
                fresh = palette_safety(cols)["min_de"]
                old = (v["safety"] or {}).get("min_de", {})
                if any(abs(fresh[x] - float(old.get(x, -99))) > 0.05 for x in fresh):
                    probs.append(f"palettes.{key}: safety numbers are stale (recompute with kb.palette_safety)")
    seen_rules = set()
    for i, (sec, r) in enumerate([("typography", r) for r in k.typography] + [("principles", r) for r in k.principles]):
        rid = r.get("id", f"#{i}") if isinstance(r, dict) else f"#{i}"
        if (sec, rid) in seen_rules:
            probs.append(f"{sec}.{rid}: duplicate rule id")
        seen_rules.add((sec, rid))
        if not isinstance(r, dict) or not r.get("text") or not isinstance(r.get("applies_to"), list):
            probs.append(f"{sec}.{rid}: needs text and applies_to")
        if not isinstance(r, dict) or not _src_ok(r.get("source"), ("url", "quote")):
            probs.append(f"{sec}.{rid}: no source (needs source.url + a verbatim source.quote)")
        if isinstance(r, dict) and "lint" in r:
            from .lint import CHECKS

            for name in r["lint"] if isinstance(r["lint"], list) else [r["lint"]]:
                if name not in CHECKS:
                    probs.append(f"typography.{rid}: lint check '{name}' does not exist")
    for sid, s in k.styles.items():
        if not isinstance(s, dict) or not s.get("file") or not (k.root.parent / s["file"]).is_file():
            probs.append(f"styles.{sid}: style file missing ({(s or {}).get('file') if isinstance(s, dict) else s})")
            continue
        for cid in s.get("evidence_cards", []):
            if cid not in k.cards:
                probs.append(f"styles.{sid}: evidence card '{cid}' does not exist")
    for did, d in k.domains.items():
        if Path(d["_file"]).stem != did:
            probs.append(f"domains/{Path(d['_file']).name}: id '{did}' must match the file name")
        convs = d.get("conventions")
        if not d.get("name") or not isinstance(convs, list):
            probs.append(f"domains.{did}: needs name and a conventions list")
            continue
        for j, cv in enumerate(convs):
            ev = cv.get("evidence_cards", []) if isinstance(cv, dict) else []
            if not isinstance(cv, dict) or not cv.get("text"):
                probs.append(f"domains.{did}.conventions[{j}]: needs text")
            if len(set(ev)) < 2:
                probs.append(f"domains.{did}.conventions[{j}]: needs at least 2 evidence cards, has {len(set(ev))}")
            for cid in ev:
                if cid not in k.cards:
                    probs.append(f"domains.{did}.conventions[{j}]: evidence card '{cid}' does not exist")
    by_fig = {}
    for cid, c in k.cards.items():
        label = f"{'user: ' if c['layer'] == 'user' else ''}cards/{Path(c['_file']).name}"
        body = {x: y for x, y in c.items() if x not in ("layer", "_file")}
        probs += [f"{label}: {p}" for p in card_problems(body)]
        if Path(c["_file"]).stem != cid:
            probs.append(f"{label}: id '{cid}' must match the file name")
        fk = (paper_key(c.get("paper_url", "")), c.get("figure"))
        if fk in by_fig:
            probs.append(f"{label}: duplicate of card '{by_fig[fk]}' (same paper and figure)")
        else:
            by_fig[fk] = cid
    idx = k.root / "index.json"
    # the release ships the cards packed and leaves out the index (generated from them, read only by this check)
    released = not idx.is_file() and (k.root / CARDS_PACK).is_file()
    if any(c.get("layer") == "repo" for c in k.cards.values()) and not released:
        want = build_index(kb_dir, data)
        have = _read(idx, [], "index") if idx.is_file() else None
        if have != json.loads(json.dumps(want)):
            probs.append("index.json is missing or stale — run `paperfig kb index` after changing cards")
    return probs


def kb_version(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def query(domain: str, venue: str | None = None, exclude_paper=None, n_cards: int = 8,
          kb_dir=None, data=None, run_cards=None) -> dict:
    """`exclude_paper`: one or several papers (the paper being drawn, figures the scout rejected as redraws of it).
    `run_cards`: this run's own card directory — the most similar references, ranked first; nothing is filed."""
    k = load_kb(kb_dir, data)
    notes = [f"kb problem: {p}" for p in k.problems]
    if run_cards:
        rd = Path(run_cards)
        for f in sorted(rd.glob("*.json")) if rd.is_dir() else []:
            c = _read(f, notes, f"run card {f.name}")
            probs = card_problems(c) if isinstance(c, dict) else ["not a JSON object"]
            if probs:
                notes.append(f"run card {f.name} skipped: {'; '.join(probs)[:200]}")
                continue
            k.cards[c["id"]] = dict(c, layer="run", _file=str(f))
        if not rd.is_dir():
            notes.append(f"run card directory {rd} does not exist")
    fmt = k.formats.get(venue.lower()) if venue else None
    if venue and fmt is None:
        notes.append(f"venue '{venue}' is not in kb/formats.json (known: {', '.join(sorted(k.formats))}) — "
                     "give figure.width in inches")
    dom = k.domains.get(domain)
    if dom is None:
        notes.append(f"no domain volume for '{domain}' (known: {', '.join(sorted(k.domains)) or 'none yet'})")
    cards = [c for c in k.cards.values() if domain in (c.get("domains") or []) or c.get("layer") == "run"]
    run_figs = {(paper_key(c.get("paper_url", "")), c.get("figure")) for c in cards if c.get("layer") == "run"}
    if run_figs:  # a run's card shadows a repo/user card of the same paper figure (no duplicate in the brief)
        cards = [c for c in cards if c.get("layer") == "run"
                 or (paper_key(c.get("paper_url", "")), c.get("figure")) not in run_figs]
    excluded: set = set()
    for ex in ([exclude_paper] if isinstance(exclude_paper, str) else exclude_paper or []):
        key, before = paper_key(ex), len(cards)
        excluded |= {cid for cid, c in k.cards.items() if key in _card_keys(c)}
        cards = [c for c in cards if key not in _card_keys(c)]
        if before - len(cards):
            notes.append(f"excluded {before - len(cards)} card(s) of {key}")
    if dom is not None and excluded:  # a blind run must not read conventions drawn from the excluded figure
        kept, dropped, trimmed = [], 0, 0
        for cv in dom.get("conventions", []):
            ev = [c for c in cv.get("evidence_cards", []) if c not in excluded]
            if len(set(ev)) < 2:
                dropped += 1
                continue
            trimmed += len(ev) < len(cv.get("evidence_cards", []))
            kept.append(dict(cv, evidence_cards=ev))
        dom = dict(dom, conventions=kept)
        if dropped or trimmed:
            notes.append(f"excluded paper: dropped {dropped} domain convention(s) resting on it, removed its cards from "
                         f"the evidence of {trimmed} other(s)")
    v = (venue or "").lower()
    cards.sort(key=lambda c: (c.get("layer") != "run", str(c.get("venue", "")).lower() != v, c.get("figure_type") != "overview", -int(c.get("year") or 0), c["id"]))
    if not cards:
        notes.append(f"no figure cards for domain '{domain}'")
    typo = [r for r in k.typography if isinstance(r, dict) and ("all" in r.get("applies_to", []) or v in
                                                                [a.lower() for a in r.get("applies_to", [])])]
    return {
        "domain": {x: y for x, y in dom.items() if x != "_file"} if dom else None,
        "venue": venue, "format": fmt, "palettes": k.palettes, "typography": typo, "styles": k.styles,
        "principles": k.principles,
        "cards": [{x: y for x, y in c.items() if x != "_file"} for c in cards[:max(0, int(n_cards))]],
        # every recorded arrangement, from any domain: a layout skeleton travels across topics (the plan's
        # layout.skeleton_from); excluded papers stay out
        "arrangements": sorted(({"id": cid, "title": c.get("title"), **c["arrangement"]} for cid, c in k.cards.items()
                                if isinstance(c.get("arrangement"), dict) and cid not in excluded),
                               key=lambda a: (a.get("partition", ""), a["id"])),
        "notes": notes, "kb_version": kb_version(k.root),
    }


def add_card(card: dict, data=None, kb_dir=None) -> Path:
    """Add a card to the user layer (never the repo); refuses invalid cards and duplicates."""
    probs = card_problems(card)
    if probs:
        raise PaperFigError("card rejected: " + "; ".join(probs))
    k = load_kb(kb_dir, data)
    if card["id"] in k.cards:
        raise PaperFigError(f"card id '{card['id']}' already exists in the {k.cards[card['id']]['layer']} layer")
    fk = (paper_key(card["paper_url"]), card["figure"])
    for c in k.cards.values():
        if (paper_key(c.get("paper_url", "")), c.get("figure")) == fk:
            raise PaperFigError(f"a card for this paper's figure {card['figure']} is already in the {c['layer']} layer "
                                f"as '{c['id']}'")
    out = k.data / "cards" / f"{card['id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    tmp.write_text(json.dumps(card, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    return out



def find_cards(paper: str, figure: int, kb_dir=None, data=None) -> list[str]:
    """Ids of existing cards (repo or user layer) for this paper's figure — reuse them instead of writing a new one."""
    key = paper_key(paper)
    return sorted(cid for cid, c in load_kb(kb_dir, data).cards.items()
                  if c.get("figure") == figure and key in _card_keys(c))


def harvest(run_dir, kb_dir=None, data=None) -> dict:
    """Keep a finished run's valid cards: add them to the user layer, skipping invalid ones and duplicates
    (same id, or same paper + figure). Never touches the repo layer."""
    added, skipped = [], []
    for f in sorted((Path(run_dir) / "refs" / "cards").glob("*.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
            add_card(c, data=data, kb_dir=kb_dir)
            added.append(c["id"])
        except (OSError, ValueError, PaperFigError, KeyError, TypeError):
            skipped.append(f.stem)
    return {"added": added, "skipped": skipped}


def copy_card(card_id: str, out_dir, kb_dir=None, data=None) -> Path:
    """Copy an existing card into a run's card directory, so a reused card serves the run like a new one
    (style derive, --cards, the brief, the critic's MODEL)."""
    k = load_kb(kb_dir, data)
    c = k.cards.get(card_id)
    if c is None:
        raise PaperFigError(f"no card '{card_id}' in the knowledge base")
    out = Path(out_dir) / f"{card_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({x: y for x, y in c.items() if x not in ("layer", "_file")}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    return out


THIN = 6  # fewer cards than this and a domain's conventions rest on too little evidence
TYPES = ("overview", "teaser", "module-detail")


def coverage(kb_dir=None, data=None) -> dict:
    """Per domain: card count, figure types and what is missing — the skill's own map of its blind spots."""
    k = load_kb(kb_dir, data)
    doms: dict = {}
    for c in k.cards.values():
        t = "overview" if c.get("figure_type") == "composite" else c.get("figure_type")
        for d in c.get("domains") or []:
            e = doms.setdefault(d, {"cards": 0, "types": {}})
            e["cards"] += 1
            e["types"][t] = e["types"].get(t, 0) + 1
    for d in k.domains:
        doms.setdefault(d, {"cards": 0, "types": {}})
    for d, e in doms.items():
        e["volume"] = d in k.domains
        e["missing_types"] = [t for t in TYPES if not e["types"].get(t)]
        e["thin"] = e["cards"] < THIN or not e["volume"]
    return {"domains": dict(sorted(doms.items())), "cards": len(k.cards)}
