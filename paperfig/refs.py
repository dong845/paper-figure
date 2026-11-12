"""Reference papers: search (Semantic Scholar -> arXiv fallback), fetch PDFs into the cache, crop figures.

Network use is limited to two free, key-less services (an optional free Semantic Scholar key is read
from SEMANTIC_SCHOLAR_API_KEY). Calls are spaced politely per host. PDFs and crops live only in the
user cache (spec §6.3: the repo never stores reference figures).

Figure cropping works on the PDF's own text layer (``pdftotext -bbox-layout``) and a page render
(``pdftoppm``): find the caption line, bound the region by body text / headings / other captions,
then take the graphics (ink that is not text) in that region plus the figure's own labels.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import PaperFigError

UA = "paper-figure/0.1 (research figure tool)"  # generic on purpose: no personal details
S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,year,venue,publicationVenue,externalIds,citationCount"
ARXIV_URL = "https://export.arxiv.org/api/query"
# seconds between calls per host; arXiv asks for one request every three seconds
MIN_INTERVAL = {"api.semanticscholar.org": 1.0, "export.arxiv.org": 3.0, "arxiv.org": 3.0}
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
ARXIV_ID = re.compile(r"^(\d{4}\.\d{4,5}|[a-z][a-z\-]*(\.[A-Z]{2})?/\d{7})(v\d+)?$")

# canonical venue -> name patterns (matched case-insensitively on word boundaries)
VENUES = {
    "CVPR": ["cvpr", "computer vision and pattern recognition"],
    "ICCV": ["iccv", "international conference on computer vision"],
    "ECCV": ["eccv", "european conference on computer vision"],
    "WACV": ["wacv", "winter conference on applications of computer vision"],
    "NeurIPS": ["neurips", "nips", "neural information processing systems"],
    "ICML": ["icml", "international conference on machine learning"],
    "ICLR": ["iclr", "international conference on learning representations"],
    "ACL": ["acl", "annual meeting of the association for computational linguistics"],
    "EMNLP": ["emnlp", "empirical methods in natural language processing"],
    "NAACL": ["naacl", "north american chapter of the association for computational linguistics"],
    "AAAI": ["aaai"],
    "IJCAI": ["ijcai", "international joint conference on artificial intelligence"],
    "MICCAI": ["miccai", "medical image computing and computer assisted intervention",
               "medical image computing and computer-assisted intervention"],
    "KDD": ["kdd", "knowledge discovery and data mining"],
    "WWW": ["www", "the web conference", "world wide web conference"],
    "SIGGRAPH": ["siggraph"],
    "TPAMI": ["tpami", "pattern analysis and machine intelligence"],
    "TMLR": ["tmlr", "transactions on machine learning research"],
    "ICASSP": ["icassp", "acoustics, speech and signal processing"],
    "Interspeech": ["interspeech"],
    "CoRL": ["corl", "conference on robot learning"],
    "ICRA": ["icra", "international conference on robotics and automation"],
    "RSS": ["robotics: science and systems"],
}
_VENUE_RE = {k: [re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])") for p in v] for k, v in VENUES.items()}


def cache_root() -> Path:
    return Path(os.environ.get("PAPERFIG_CACHE") or Path.home() / ".cache" / "paper-figure")


# ---------------------------------------------------------------------------------------- network
def _sleep(s: float) -> None:
    time.sleep(s)


_LOCAL_LAST: dict[str, float] = {}


def _throttle(host: str) -> None:
    """Wait until MIN_INTERVAL has passed since the last call to ``host`` by *any* paperfig process
    (parallel scouts share one budget): a per-host lock file holds the last call's wall-clock time."""
    gap = MIN_INTERVAL.get(host, 1.0)
    try:
        import fcntl
    except ImportError:  # Windows: no file locks — space calls within this process only
        wait = gap - (time.monotonic() - _LOCAL_LAST.get(host, -1e9))
        if wait > 0:
            _sleep(wait)
        _LOCAL_LAST[host] = time.monotonic()
        return
    d = cache_root() / "ratelimit"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{host}.lock", "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # held while waiting, so callers queue up
        try:
            f.seek(0)
            try:
                last = float(f.read().strip() or 0)
            except ValueError:
                last = 0.0
            wait = gap - (time.time() - last)
            if wait > 0:
                _sleep(min(wait, gap))
            f.seek(0)
            f.truncate()
            f.write(repr(time.time()))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _get(url: str, timeout: float = 30, headers: dict | None = None) -> bytes:
    host = urllib.parse.urlparse(url).hostname or ""
    _throttle(host)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_retry(url: str, tries: int = 3, **kw) -> bytes:
    for i in range(tries):
        try:
            return _get(url, **kw)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                _sleep(2.0 ** (i + 1))
                continue
            raise
    raise AssertionError("unreachable")


def _err_text(e: BaseException) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason}"
    if isinstance(e, urllib.error.URLError):
        return f"network error: {e.reason}"
    return f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------------------- search
@dataclass
class Candidate:
    title: str
    year: int | None
    venue: str | None
    arxiv_id: str | None
    url: str
    citations: int | None
    source: str
    venue_names: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Candidates(list):
    """A result list that also carries notes (which service answered, why something is missing)."""

    def __init__(self, items=(), notes=()):
        super().__init__(items)
        self.notes = list(notes)


def canonical_venue(text: str | None) -> str | None:
    t = (text or "").lower()
    for k, pats in _VENUE_RE.items():
        if any(p.search(t) for p in pats):
            return k
    return None


def venue_matches(c: Candidate, venues) -> bool:
    want = {v.strip() for v in venues if v and v.strip()}
    canon = {canonical_venue(v) or v.lower() for v in want}
    if c.venue and (c.venue in canon or c.venue.lower() in canon):
        return True
    names = [n.lower() for n in c.venue_names if n]
    return any(canonical_venue(n) in canon for n in names) or any(w.lower() in n for w in want for n in names)


def _clean(s) -> str:
    return " ".join(str(s or "").split())


def _strip_version(aid: str) -> str:
    return re.sub(r"v\d+$", "", aid.strip())


def parse_s2(obj: dict) -> list[Candidate]:
    out = []
    for it in (obj or {}).get("data") or []:
        ext = it.get("externalIds") or {}
        pv = it.get("publicationVenue") or {}
        names = [n for n in [it.get("venue"), pv.get("name"), *(pv.get("alternate_names") or [])] if n]
        venue = next((canonical_venue(n) for n in names if canonical_venue(n)), None) or (_clean(names[0]) if names else None)
        aid = ext.get("ArXiv")
        url = (f"https://arxiv.org/abs/{aid}" if aid else
               f"https://doi.org/{ext['DOI']}" if ext.get("DOI") else
               f"https://www.semanticscholar.org/paper/{it.get('paperId', '')}")
        out.append(Candidate(_clean(it.get("title")), it.get("year"), venue, aid, url, it.get("citationCount"),
                             "semantic-scholar", names))
    return out


def parse_arxiv(xml: str | bytes) -> list[Candidate]:
    root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    out = []
    for e in root.findall("a:entry", NS):
        eid = (e.findtext("a:id", "", NS) or "").strip()
        if "/abs/" not in eid:  # arXiv reports query errors as an entry without an abs id
            continue
        aid = _strip_version(eid.split("/abs/", 1)[1])
        pub = e.findtext("a:published", "", NS) or ""
        jref = _clean(e.findtext("arxiv:journal_ref", "", NS)) or None
        comment = _clean(e.findtext("arxiv:comment", "", NS)) or None
        venue = canonical_venue(jref) or canonical_venue(comment)
        out.append(Candidate(_clean(e.findtext("a:title", "", NS)), int(pub[:4]) if pub[:4].isdigit() else None,
                             venue, aid, f"https://arxiv.org/abs/{aid}", None, "arxiv", [n for n in (jref, comment) if n]))
    return out


STOPWORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is", "of", "on", "or", "the", "to", "via",
             "with", "without", "towards", "toward", "using"}


def _arxiv_title_query(title: str) -> str:
    return 'ti:"' + _clean(title).replace('"', "") + '"'


def _arxiv_query(q: str, years) -> str:
    terms = []
    for tok in re.findall(r'"[^"]+"|\S+', q):
        if tok.startswith('"'):
            terms.append(f'all:"{tok.strip(chr(34))}"')
        else:
            w = re.sub(r"[^\w\-]", "", tok)
            if w and w.lower() not in STOPWORDS:
                terms.append(f"all:{w}")
    if years:
        terms.append(f"submittedDate:[{years[0]}01010000 TO {years[1]}12312359]")
    return " AND ".join(terms)


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def search(query: str, years=None, venues=None, limit: int = 20, exclude_arxiv=(), exclude_titles=()) -> Candidates:
    """Find candidate reference papers. Raises PaperFigError only when no service could be reached."""
    q = _clean(query)
    if not q:
        raise PaperFigError("empty search query")
    if years is not None:
        years = (int(years[0]), int(years[1]))
        if years[0] > years[1]:
            raise PaperFigError(f"year range {years[0]}-{years[1]} is reversed")
    limit = max(1, int(limit))
    notes, raw, s2_err, ax_err = [], [], None, None
    try:
        params = {"query": q, "fields": S2_FIELDS, "limit": min(100, limit * 3)}
        if years:
            params["year"] = f"{years[0]}-{years[1]}"
        key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        body = _get_retry(S2_URL + "?" + urllib.parse.urlencode(params), headers={"x-api-key": key} if key else None)
        raw = parse_s2(json.loads(body))
        notes.append(f"semantic scholar: {len(raw)} results")
    except (OSError, ValueError) as e:
        s2_err = _err_text(e)
        notes.append(f"semantic scholar failed ({s2_err}); falling back to arXiv")
    if not raw:
        try:
            params = {"search_query": _arxiv_query(q, years), "max_results": min(100, limit * 3), "sortBy": "relevance"}
            raw = parse_arxiv(_get_retry(ARXIV_URL + "?" + urllib.parse.urlencode(params)))
            notes.append(f"arXiv: {len(raw)} results")
        except (OSError, ValueError, ET.ParseError) as e:
            ax_err = _err_text(e)
            notes.append(f"arXiv failed ({ax_err})")
    if s2_err and ax_err:
        raise PaperFigError(f"reference search failed — network unreachable or both services down "
                            f"(semantic scholar: {s2_err}; arXiv: {ax_err})")
    ex_ids = {_strip_version(x) for x in exclude_arxiv if x}
    ex_titles = {_norm_title(t) for t in exclude_titles if t}
    out, seen, dropped = [], set(), Counter()
    for c in raw:
        key = c.arxiv_id or _norm_title(c.title)
        if key in seen:
            continue
        seen.add(key)
        if (c.arxiv_id and _strip_version(c.arxiv_id) in ex_ids) or _norm_title(c.title) in ex_titles:
            dropped["excluded"] += 1
        elif years and (c.year is None or not years[0] <= c.year <= years[1]):
            dropped["outside years"] += 1
        elif venues and not venue_matches(c, venues):
            dropped["venue not matched" if c.venue else "venue unknown"] += 1
        else:
            out.append(c)
    if dropped:
        notes.append("filtered out: " + ", ".join(f"{n} {k}" for k, n in dropped.items()))
    if not out:
        notes.append("no results after filtering" if raw else "no results")
    return Candidates(out[:limit], notes)


def search_title(title: str) -> Candidates:
    """Resolve one exact title: Semantic Scholar's title match, else an arXiv title-phrase query."""
    t = _clean(title)
    if not t:
        raise PaperFigError("empty title")
    notes, s2_err = [], None
    try:
        key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        body = _get_retry(S2_URL + "/match?" + urllib.parse.urlencode({"query": t, "fields": S2_FIELDS}),
                          headers={"x-api-key": key} if key else None)
        out = parse_s2(json.loads(body))
        if out:
            return Candidates(out[:1], ["semantic scholar: title match"])
        notes.append("semantic scholar: no title match")
    except (OSError, ValueError) as e:
        s2_err = _err_text(e)
        notes.append(f"semantic scholar title match failed ({s2_err}); trying arXiv")
    try:
        params = {"search_query": _arxiv_title_query(t), "max_results": 5}
        out = parse_arxiv(_get_retry(ARXIV_URL + "?" + urllib.parse.urlencode(params)))
    except (OSError, ValueError, ET.ParseError) as e:
        if s2_err:
            raise PaperFigError(f"title lookup failed — network unreachable? (semantic scholar: {s2_err}; arXiv: {_err_text(e)})") from e
        return Candidates([], notes + [f"arXiv failed ({_err_text(e)})"])
    best = [c for c in out if _norm_title(c.title) == _norm_title(t)] or out[:1]
    return Candidates(best[:1], notes + [f"arXiv: {len(out)} title results" + ("" if best else ", none matched")])


def fetch(arxiv_id: str, cache=None) -> Path:
    """Download an arXiv PDF into the cache (once) and return its path."""
    aid = (arxiv_id or "").strip()
    if not ARXIV_ID.match(aid):
        raise PaperFigError(f"not a valid arXiv id: {arxiv_id!r} (expected e.g. 2111.09881 or cs/0112017)")
    d = (Path(cache) if cache else cache_root() / "refs") / aid.replace("/", "_")
    p = d / "paper.pdf"
    if p.is_file() and p.read_bytes()[:5] == b"%PDF-":
        return p
    try:
        data = _get_retry(f"https://arxiv.org/pdf/{aid}", timeout=120)
    except OSError as e:
        raise PaperFigError(f"could not download arXiv {aid}: {_err_text(e)}") from e
    if not data.startswith(b"%PDF"):
        raise PaperFigError(f"arXiv {aid}: the response is not a PDF ({len(data)} bytes, starts {data[:24]!r})")
    d.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(p)
    return p


# ---------------------------------------------------------------------------------------- layout
@dataclass
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def w(self) -> float:
        return self.x1 - self.x0


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines)


@dataclass
class Page:
    number: int
    w: float
    h: float
    blocks: list
    cols: list = field(default_factory=list)  # body-text columns on this page [(left, right)]

    @property
    def text_x(self):
        return (self.cols[0][0], self.cols[-1][1]) if self.cols else None


@dataclass
class Doc:
    path: Path
    pages: list
    body_h: float | None = None
    cols: list = field(default_factory=list)  # the most common page layout [(left, right)]
    text_x: tuple | None = None
    text_y: tuple | None = None
    style_vote: str | None = None


_TAG = re.compile(r'<(page|block|line|word)\b([^>]*)>|</(block|line|word)>|([^<]+)')
_ATTR = re.compile(r'(\w+)="([^"]*)"')


def _tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise PaperFigError(f"'{name}' not found — install poppler (macOS: brew install poppler; Debian: apt install poppler-utils)")
    return exe


def _layout(pdf) -> Doc:
    pdf = Path(pdf)
    r = subprocess.run([_tool("pdftotext"), "-bbox-layout", str(pdf), "-"], capture_output=True, timeout=300)
    if r.returncode != 0:
        raise PaperFigError(f"pdftotext failed on {pdf.name}: {r.stderr.decode(errors='replace').strip()[:300]}")
    pages, page, block, line, words, in_word = [], None, None, None, [], False
    for m in _TAG.finditer(r.stdout.decode("utf-8", errors="replace")):
        tag, attrs, close, text = m.groups()
        if tag:
            a = {k: v for k, v in _ATTR.findall(attrs)}
            if tag == "page":
                page = Page(len(pages) + 1, float(a.get("width", 0)), float(a.get("height", 0)), [])
                pages.append(page)
            elif tag == "block":
                block = Block(*(float(a[k]) for k in ("xMin", "yMin", "xMax", "yMax")), [])
            elif tag == "line":
                line = Line(*(float(a[k]) for k in ("xMin", "yMin", "xMax", "yMax")), "")
                words = []
            elif tag == "word":
                in_word, words = True, words + [""]
        elif close == "word":
            in_word = False
        elif close == "line" and line is not None and block is not None:
            line.text = " ".join(w for w in words if w)
            block.lines.append(line)
            line = None
        elif close == "block" and block is not None and page is not None:
            if block.lines:
                page.blocks.append(block)
            block = None
        elif text is not None and in_word and words:
            words[-1] += html.unescape(text)
    if not pages:
        raise PaperFigError(f"pdftotext returned no pages for {pdf.name}")
    doc = Doc(pdf, pages)
    _body_stats(doc)
    return doc


def _non_overlapping(cols):
    """Strongest first; drop clusters overlapping a stronger one (indented first lines, abstracts)."""
    kept = []
    for c in sorted(cols, key=lambda c: -c[2]):
        if all(c[1] <= k[0] or c[0] >= k[1] for k in kept):
            kept.append(c)
    return sorted((left, right) for left, right, _ in kept)


def _body_stats(doc: Doc) -> None:
    """Body line height, then body-text columns per page (a two-column paper often ends with a
    single-column appendix), and the vertical text area."""
    hist = Counter()
    for pg in doc.pages:
        for b in pg.blocks:
            for ln in b.lines:
                nw = len(ln.text.split())
                if nw >= 5:
                    hist[round(ln.h * 2) / 2] += nw
    if not hist:
        return
    doc.body_h = hist.most_common(1)[0][0]
    cand = [(pg.number, ln) for pg in doc.pages for b in pg.blocks for ln in b.lines
            if len(ln.text.split()) >= 6 and _h_ok(doc, ln.h)]
    if not cand:
        return
    # justified body lines share both edges: cluster on (left, right) together
    bins = Counter((round(ln.x0 / 3), round(ln.x1 / 3)) for _, ln in cand)
    clusters, taken = [], set()
    for key, _ in bins.most_common():
        if key in taken:
            continue
        group = [k for k in bins if k not in taken and abs(k[0] - key[0]) <= 1 and abs(k[1] - key[1]) <= 1]
        taken.update(group)
        members = [ln for _, ln in cand if (round(ln.x0 / 3), round(ln.x1 / 3)) in group]
        clusters.append(members)
    need = max(5, 0.03 * len(cand))
    model = []
    for cl in clusters:
        if len(cl) >= need:
            xs0, xs1 = sorted(ln.x0 for ln in cl), sorted(ln.x1 for ln in cl)
            model.append((xs0[len(cl) // 2], xs1[len(cl) // 2]))
    for pg in doc.pages:
        mine = [ln for n, ln in cand if n == pg.number]
        if len(mine) < 8:  # too little body text to read a layout from (figure / table pages)
            continue
        counts = [(lo, hi, sum(1 for ln in mine if abs(ln.x0 - lo) <= 3 and abs(ln.x1 - hi) <= 3)) for lo, hi in model]
        pg.cols = _non_overlapping([c for c in counts if c[2] >= 2])
    layouts = Counter(tuple(pg.cols) for pg in doc.pages if pg.cols)
    if not layouts:
        return
    doc.cols = list(layouts.most_common(1)[0][0])

    def same(a, b):
        return abs(a[0] - b[0]) <= 4 and abs(a[1] - b[1]) <= 4

    for pg in doc.pages:
        # sparse pages, and pages whose text fills only some of the usual columns, use the usual layout
        if not pg.cols or (len(pg.cols) < len(doc.cols) and all(any(same(c, d) for d in doc.cols) for c in pg.cols)):
            pg.cols = list(doc.cols)
    doc.text_x = (doc.cols[0][0], doc.cols[-1][1])
    ys = [(b.y0, b.y1) for pg in doc.pages for b in pg.blocks if _is_body(doc, b, pg)]
    if ys:
        doc.text_y = (min(y for y, _ in ys), max(y for _, y in ys))


def _h_ok(doc: Doc, h: float) -> bool:
    return doc.body_h is not None and abs(h - doc.body_h) <= 0.08 * doc.body_h


def _col_of(cols, x0: float):
    return next((c for c in cols if abs(x0 - c[0]) <= 4), None)


def _is_body(doc: Doc, b: Block, pg: Page) -> bool:
    col = _col_of(pg.cols, b.x0)
    if col is None and len(b.lines) >= 2:  # an indented list / quote, still justified to the column's right edge
        col = next((c for c in pg.cols if c[0] - 4 <= b.x0 <= c[0] + 0.3 * (c[1] - c[0]) and abs(b.x1 - c[1]) <= 4), None)
        if col is not None:
            col = (b.x0, col[1])
    if col is None or b.x1 > col[1] + 4:
        return False
    cw = col[1] - col[0]
    if len(b.lines) == 1:
        ln = b.lines[0]
        return _h_ok(doc, ln.h) and ln.w >= 0.9 * cw and len(ln.text.split()) >= 6
    # a paragraph's last line is usually short; inline math makes lines taller, never shorter
    full = b.lines[:-1]
    ok = [ln for ln in full if ln.w >= 0.75 * cw and 0.92 * doc.body_h <= ln.h <= 1.6 * doc.body_h]
    return len(ok) >= 0.5 * len(full) and any(_h_ok(doc, ln.h) for ln in b.lines)


_HEAD_RE = re.compile(r"^(\d+(\.\d+)*\.?|[A-Z]\.|[IVX]+\.)\s+[A-Z]")
_HEAD_WORDS = {"abstract", "references", "acknowledgements", "acknowledgments", "introduction", "conclusion",
               "conclusions", "appendix", "related work"}  # not "method": a common table header cell


def _is_heading(doc: Doc, b: Block, pg: Page) -> bool:
    if len(b.lines) > 2:
        return False
    t = b.text.strip()
    if t.lower().rstrip(".:") in _HEAD_WORDS:
        return True
    return bool(_HEAD_RE.match(t)) and len(t.split()) <= 14 and (not pg.cols or _col_of(pg.cols, b.x0) is not None)


# ---------------------------------------------------------------------------------------- captions
_CAP_RE = re.compile(r"^(?P<kind>Figure|FIGURE|Fig\.?|FIG\.?|Table|TABLE)\s*(?P<num>\d+|[IVXL]+)\s*(?P<sep>[:.|](?!\d)|$)")


@dataclass
class Caption:
    kind: str  # figure | table
    number: int | str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    blocks: list  # ids (id()) of blocks consumed by this caption


def _cap_match(text: str):
    m = _CAP_RE.match(text.strip())
    if not m:
        return None
    kind = "table" if m.group("kind").lower().startswith("tab") else "figure"
    num = m.group("num")
    if kind == "figure" and not num.isdigit():
        return None
    return kind, (int(num) if num.isdigit() else num)


def _join(lines) -> str:
    out = ""
    for ln in lines:
        t = ln.text.strip()
        out = (out + t) if out.endswith("-") else (out + " " + t if out else t)
    return out


def _block_of(lines) -> Block:
    return Block(min(ln.x0 for ln in lines), min(ln.y0 for ln in lines), max(ln.x1 for ln in lines),
                 max(ln.y1 for ln in lines), list(lines))


def _captions(doc: Doc) -> list[Caption]:
    caps, starts = [], set()
    for pg in doc.pages:
        for b in pg.blocks:
            m = _cap_match(b.lines[0].text)
            if m:
                caps.append((pg, b, 0, m))
                starts.add(id(b))
    found = {(m[0], m[1]) for _, _, _, m in caps}
    for pg in doc.pages:  # caption merged into a block of figure labels: accept a later line start
        for b in pg.blocks:
            if id(b) in starts:
                continue
            for i, ln in enumerate(b.lines[1:], 1):
                m = _cap_match(ln.text)
                if not m or (m[0], m[1]) in found:
                    continue
                prev = b.lines[i - 1]
                col = _col_of(pg.cols, prev.x0)
                body_like = _h_ok(doc, prev.h) and col is not None and prev.w >= 0.75 * (col[1] - col[0])
                # a sentence wrapping onto "Figure 3." follows its line closely; a caption follows a figure or a gap
                if not body_like or ln.y0 - prev.y1 > 0.6 * ln.h:
                    caps.append((pg, b, i, m))
                    found.add((m[0], m[1]))
                    break
    out = []
    for pg, b, i, (kind, num) in caps:
        lines = [b.lines[i]]
        for ln in b.lines[i + 1:]:  # the caption ends where its lines stop running on (merged blocks hold more)
            if ln.y0 - lines[-1].y1 > 0.6 * lines[0].h:
                break
            lines.append(ln)
        j = i + len(lines)
        if i > 0 or j < len(b.lines):  # split the caption out of a merged block: labels / body around it stay text
            parts = [ls for ls in (b.lines[:i], lines, b.lines[j:]) if ls]
            new = [_block_of(ls) for ls in parts]
            k = pg.blocks.index(b)
            pg.blocks[k:k + 1] = new
            starts.discard(id(b))
            b = new[1 if i > 0 else 0]
            starts.add(id(b))
        x0, y0 = min(ln.x0 for ln in lines), min(ln.y0 for ln in lines)
        x1, y1 = max(ln.x1 for ln in lines), max(ln.y1 for ln in lines)
        used = [id(b)]
        lh = max(1.0, sorted(ln.h for ln in lines)[len(lines) // 2])
        for _ in range(10):  # continuation blocks directly underneath
            nxt = [o for o in pg.blocks if id(o) not in used and id(o) not in starts
                   and -1 <= o.y0 - y1 <= 0.6 * lh and min(o.x1, x1) - max(o.x0, x0) >= 0.5 * min(o.x1 - o.x0, x1 - x0)
                   and abs(sorted(ln.h for ln in o.lines)[len(o.lines) // 2] - lh) <= 0.15 * lh]
            if not nxt:
                break
            o = min(nxt, key=lambda o: o.y0)
            lines = lines + o.lines
            used.append(id(o))
            x0, x1, y1 = min(x0, o.x0), max(x1, o.x1), max(y1, o.y1)
        out.append(Caption(kind, num, pg.number, x0, y0, x1, y1, _join(lines), used))
    out.sort(key=lambda c: (c.page, c.y0))
    return out


# ---------------------------------------------------------------------------------------- crop
@dataclass
class FigureCrop:
    number: int
    page: int
    png: Path | None
    caption: str
    bbox: tuple | None  # PDF points (x0, y0, x1, y1), origin top-left
    layout: str | None = None  # caption-below | caption-above | text-only
    span: str | None = None  # full | column | side-by-side
    problem: str | None = None


def page_size_px(pdf, page: int, dpi: int = 200) -> tuple[int, int]:
    r = subprocess.run([_tool("pdfinfo"), "-f", str(page), "-l", str(page), str(pdf)], capture_output=True, text=True, timeout=60)
    m = re.search(rf"Page\s+{page} size:\s*([\d.]+) x ([\d.]+)", r.stdout)
    if not m:
        raise PaperFigError(f"pdfinfo could not read page {page} of {Path(pdf).name}")
    return round(float(m.group(1)) * dpi / 72), round(float(m.group(2)) * dpi / 72)


class _Renders:
    def __init__(self, doc: Doc, dpi: int):
        self.doc, self.dpi, self._img, self._mask = doc, dpi, {}, {}
        self._tmp = tempfile.TemporaryDirectory(prefix="paperfig-crop-")

    def close(self):
        self._tmp.cleanup()

    def image(self, page: int):
        from PIL import Image

        if page not in self._img:
            prefix = Path(self._tmp.name) / f"p{page}"
            r = subprocess.run([_tool("pdftoppm"), "-f", str(page), "-l", str(page), "-r", str(self.dpi), "-png",
                                "-hide-annotations", "-singlefile", str(self.doc.path), str(prefix)],
                               capture_output=True, timeout=300)  # link boxes are not part of any figure
            if r.returncode != 0 or not prefix.with_suffix(".png").is_file():
                raise PaperFigError(f"pdftoppm failed on page {page}: {r.stderr.decode(errors='replace').strip()[:300]}")
            self._img[page] = Image.open(prefix.with_suffix(".png")).convert("RGB")
        return self._img[page]

    def ink_mask(self, page: int):
        """Non-white pixels (text included)."""
        from PIL import ImageChops

        if ("ink", page) not in self._mask:
            r, g, b = self.image(page).split()
            self._mask[("ink", page)] = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v < 240 else 0)
        return self._mask[("ink", page)]

    def graphics_rows(self, page: int, box) -> list[bool]:
        """Per pixel row of ``box`` (PDF points): does the row hold any graphics (non-text ink)?"""
        from PIL import Image

        k = self.dpi / 72
        m = self.graphics_mask(page)
        x0, y0 = max(0, int(box[0] * k)), max(0, int(box[1] * k))
        x1, y1 = min(m.width, int(box[2] * k + 0.999)), min(m.height, int(box[3] * k + 0.999))
        if x1 - x0 < 1 or y1 - y0 < 1:
            return []
        col = m.crop((x0, y0, x1, y1)).convert("F").resize((1, y1 - y0), Image.Resampling.BOX)
        return [v > 0 for v in _flat(col)]

    def ink_cols(self, page: int, box) -> list[bool]:
        """Per pixel column of ``box`` (PDF points): does the column hold any ink (text included)?"""
        from PIL import Image

        k = self.dpi / 72
        m = self.ink_mask(page)
        x0, y0 = max(0, int(box[0] * k)), max(0, int(box[1] * k))
        x1, y1 = min(m.width, int(box[2] * k + 0.999)), min(m.height, int(box[3] * k + 0.999))
        if x1 - x0 < 1 or y1 - y0 < 1:
            return []
        row = m.crop((x0, y0, x1, y1)).convert("F").resize((x1 - x0, 1), Image.Resampling.BOX)
        return [v > 0 for v in _flat(row)]

    def graphics_mask(self, page: int):
        """Non-white pixels that are not text: images and vector drawings."""
        from PIL import ImageDraw

        if page not in self._mask:
            m = self.ink_mask(page).copy()
            d, k = ImageDraw.Draw(m), self.dpi / 72
            for blk in self.doc.pages[page - 1].blocks:
                for ln in blk.lines:
                    d.rectangle([(ln.x0 - 1.5) * k, (ln.y0 - 1.5) * k, (ln.x1 + 1.5) * k, (ln.y1 + 1.5) * k], fill=0)
            self._mask[page] = m
        return self._mask[page]

    def graphics_in(self, page: int, box):
        k = self.dpi / 72
        m = self.graphics_mask(page)
        x0, y0 = max(0, int(box[0] * k)), max(0, int(box[1] * k))
        x1, y1 = min(m.width, int(box[2] * k + 0.999)), min(m.height, int(box[3] * k + 0.999))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        bb = m.crop((x0, y0, x1, y1)).getbbox()
        if not bb:
            return None
        return ((x0 + bb[0]) / k, (y0 + bb[1]) / k, (x0 + bb[2]) / k, (y0 + bb[3]) / k)


def _flat(im):
    """Pixel values in row order (Pillow 12 renamed getdata to get_flattened_data)."""
    return im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()


def _overlap_x(a0, a1, b0, b1) -> float:
    return min(a1, b1) - max(a0, b0)


def _span(doc: Doc, cap: Caption, caps_on_page, force_full: bool = False) -> tuple[float, float, str]:
    pg = doc.pages[cap.page - 1]
    tx0, tx1 = pg.text_x or (0.0, pg.w)
    tx0, tx1 = min(tx0, cap.x0), max(tx1, cap.x1)  # a figure is at least as wide as the text area its caption uses
    kind = "full"
    if len(pg.cols) >= 2 and not force_full:
        crosses = any(cap.x0 < a[1] - 5 and cap.x1 > b[0] + 5 for a, b in zip(pg.cols, pg.cols[1:]))
        if not crosses:
            cx = (cap.x0 + cap.x1) / 2
            col = min(pg.cols, key=lambda c: 0 if c[0] - 6 <= cx <= c[1] + 6 else min(abs(cx - c[0]), abs(cx - c[1])))
            tx0, tx1, kind = col[0], col[1], "column"
    lo_split = hi_split = False
    for o in caps_on_page:  # side-by-side captions (minipages): split the span between them
        if o is cap or min(o.y1, cap.y1) - max(o.y0, cap.y0) <= 0:
            continue
        if _overlap_x(o.x0, o.x1, cap.x0, cap.x1) > 0 or not tx0 - 6 <= (o.x0 + o.x1) / 2 <= tx1 + 6:
            continue  # overlapping, or in another column: not a side-by-side neighbour
        if o.x0 >= cap.x1:
            tx1, hi_split = min(tx1, (cap.x1 + o.x0) / 2), True
        else:
            tx0, lo_split = max(tx0, (o.x1 + cap.x0) / 2), True
        kind = "side-by-side"
    # pad outer edges (figures may overhang the text block a little), never a split edge
    return (tx0 if lo_split else max(0.0, tx0 - 6)), (tx1 if hi_split else min(pg.w, tx1 + 6)), kind


def _barrier(doc: Doc, pg: Page, b: Block, sx0: float, sx1: float, cap_ids: set) -> bool:
    if _overlap_x(b.x0, b.x1, sx0, sx1) <= 2:
        return False
    if id(b) in cap_ids or _is_body(doc, b, pg) or _is_heading(doc, b, pg):
        return True
    return b.x0 < sx0 - 6 or b.x1 > sx1 + 6  # text that runs outside the span cannot belong to this figure


def _attach_text(doc: Doc, page: Page, bbox, region, cap: Caption, barriers: set):
    d = max(6.0, 0.9 * (doc.body_h or 8.0))
    cand = [b for b in page.blocks if id(b) not in barriers and id(b) not in cap.blocks
            and b.x0 >= region[0] - 1 and b.x1 <= region[2] + 1 and b.y0 >= region[1] - 1 and b.y1 <= region[3] + 1]
    x0, y0, x1, y1 = bbox
    changed = True
    while changed:
        changed = False
        for b in cand:
            if b.x0 >= x0 and b.x1 <= x1 and b.y0 >= y0 and b.y1 <= y1:
                continue
            gap = max(b.x0 - x1, x0 - b.x1, b.y0 - y1, y0 - b.y1, 0)
            if gap <= d:
                x0, y0, x1, y1 = min(x0, b.x0), min(y0, b.y0), max(x1, b.x1), max(y1, b.y1)
                changed = True
    return x0, y0, x1, y1


def _only_straight_rules(renders: "_Renders", page: int, box) -> bool:
    """True when the graphics in ``box`` are nothing but full-length horizontal / vertical rules
    (a ruled table once its text is masked); False for images, fills, curves, markers, boxes."""
    from PIL import Image, ImageDraw

    k = renders.dpi / 72
    m = renders.graphics_mask(page)
    x0, y0 = max(0, int(box[0] * k)), max(0, int(box[1] * k))
    x1, y1 = min(m.width, int(box[2] * k + 0.999)), min(m.height, int(box[3] * k + 0.999))
    if x1 - x0 < 2 or y1 - y0 < 1:
        return True
    c = m.crop((x0, y0, x1, y1))
    bb = c.getbbox()
    if not bb:
        return True
    c = c.crop(bb)
    w, h = c.size
    # find rules on the full ink mask: text line boxes span table rows and would cut vertical rules
    f = renders.ink_mask(page).crop((x0 + bb[0], y0 + bb[1], x0 + bb[2], y0 + bb[3])).convert("F")
    rows = list(_flat(f.resize((1, h), Image.Resampling.BOX)))
    cols = list(_flat(f.resize((w, 1), Image.Resampling.BOX)))
    thin = max(1, int(2.5 * k))  # a rule is at most 2.5 pt thick; a filled box or image is a long run

    def thin_runs(prof, full):
        out, j = [], 0
        while j < len(prof):
            if prof[j] >= full:
                e = j
                while e < len(prof) and prof[e] >= full:
                    e += 1
                if e - j <= thin:
                    out.extend(range(j, e))
                j = e
            else:
                j += 1
        return out

    d = ImageDraw.Draw(c)
    for j in thin_runs(rows, 0.5 * 255):  # horizontal rules across the content
        d.line([(0, j), (w, j)], fill=0)
    for i in thin_runs(cols, 0.8 * 255):  # vertical rules through the whole band
        d.line([(i, 0), (i, h)], fill=0)
    left = c.histogram()[255]
    return left <= max(12, 0.002 * w * h)


def _table_bottom(renders: "_Renders", page: int, box) -> float | None:
    """Bottom of a ruled table at the top of ``box`` (a caption-above table between its caption and
    this figure). Graphics bands are scanned top-down; the table is the leading run of bands that
    hold only straight rules. Returns its bottom, or None when there is nothing to skip."""
    k = renders.dpi / 72
    rows = renders.graphics_rows(page, box)
    bands, start = [], None
    for j, v in enumerate(rows + [False]):
        if v and start is None:
            start = j
        elif not v and start is not None:
            bands.append((box[1] + start / k, box[1] + j / k))
            start = None
    bottom = None
    for y0, y1 in bands:
        if not _only_straight_rules(renders, page, (box[0], y0, box[2], y1)):
            return bottom  # first real graphic: the figure starts here
        bottom = y1
    return None  # nothing but rules all the way down: not a table we can separate


def _regions(doc: Doc, cap: Caption, caps, all_cap_ids: set, renders: "_Renders", force_full: bool = False):
    caps_on_page = [c for c in caps if c.page == cap.page]
    sx0, sx1, span = _span(doc, cap, caps_on_page, force_full)
    res = _regions_in(doc, cap, caps_on_page, all_cap_ids, renders, sx0, sx1, span)
    if span == "column" and not force_full:
        # graphics clipped at the column edge: the figure is wider than its (short) caption suggests
        ra, rb = res[0], res[1]
        clipped = [g for g in (renders.graphics_in(cap.page, ra), renders.graphics_in(cap.page, rb))
                   if g and (g[0] <= ra[0] + 1.5 or g[2] >= ra[2] - 1.5)]
        if clipped:
            full = _regions(doc, cap, caps, all_cap_ids, renders, force_full=True)
            wide = [g for g in (renders.graphics_in(cap.page, full[0]), renders.graphics_in(cap.page, full[1]))
                    if g and (g[0] < sx0 - 1 or g[2] > sx1 + 1)]
            if wide:
                return full
    return res


def _regions_in(doc: Doc, cap: Caption, caps_on_page, all_cap_ids: set, renders: "_Renders", sx0, sx1, span):
    pg = doc.pages[cap.page - 1]
    ty0, ty1 = doc.text_y or (6.0, pg.h - 6.0)
    others = all_cap_ids - set(cap.blocks)
    above = [b for b in pg.blocks if b.y1 <= cap.y0 + 0.5 and id(b) not in cap.blocks and _barrier(doc, pg, b, sx0, sx1, others)]
    below = [b for b in pg.blocks if b.y0 >= cap.y1 - 0.5 and id(b) not in cap.blocks and _barrier(doc, pg, b, sx0, sx1, others)]
    top = max([max(0.0, ty0 - 6)] + [b.y1 for b in above])
    bottom = min([min(pg.h, ty1 + 6)] + [b.y0 for b in below])
    if above:
        lim = max(above, key=lambda b: b.y1)
        tcap = next((c for c in caps_on_page if c.kind == "table" and id(lim) in c.blocks), None)
        if tcap is not None and lim.y1 >= top - 0.01:
            # a caption-above table between its caption and this figure: start below its last rule
            tb = _table_bottom(renders, cap.page, (sx0, top, sx1, cap.y0 - 0.5))
            if tb is not None:
                top = tb + 0.5
    ra = (sx0, top, sx1, cap.y0 - 0.5)
    rb = (sx0, cap.y1 + 0.5, sx1, bottom)
    return ra, rb, span, {id(b) for b in above + below} | others


def _graphic_h(g) -> float:
    return 0.0 if g is None else g[3] - g[1]


def _side_strip(doc: Doc, cap: Caption, x0: float, x1: float, cap_ids: set):
    """Region beside a caption (wrapfigure / side caption): the strip x0..x1, bounded above and below by
    the nearest body text, heading or other caption in that strip."""
    pg = doc.pages[cap.page - 1]
    ty0, ty1 = doc.text_y or (6.0, pg.h - 6.0)
    others = cap_ids - set(cap.blocks)
    bar = [b for b in pg.blocks if id(b) not in cap.blocks and _barrier(doc, pg, b, x0, x1, others)]
    top = max([max(0.0, ty0 - 6)] + [b.y1 for b in bar if b.y1 <= cap.y0 + 1])
    bottom = min([min(pg.h, ty1 + 6)] + [b.y0 for b in bar if b.y0 >= cap.y1 - 1])
    return (x0, top, x1, bottom), {id(b) for b in bar} | others


def _decide(doc: Doc, cap: Caption, caps, renders: _Renders, cap_ids: set):
    ra, rb, span, barriers = _regions(doc, cap, caps, cap_ids, renders)
    hcap = cap.y1 - cap.y0
    for which, (x0, x1) in (("left", (ra[0], cap.x0 - 2)), ("right", (cap.x1 + 2, ra[2]))):
        if x1 - x0 < 30:
            continue
        beside = renders.graphics_in(cap.page, (x0, cap.y0, x1, cap.y1))  # graphics level with the caption itself
        if _graphic_h(beside) >= max(10.0, 0.5 * hcap):
            region, bars = _side_strip(doc, cap, x0, x1, cap_ids)
            pg = doc.pages[cap.page - 1]
            owned = any(id(b) in cap_ids and abs(b.y1 - region[1]) < 0.01 for b in pg.blocks)  # under another caption
            g = renders.graphics_in(cap.page, region)
            if owned or g is None or _only_straight_rules(renders, cap.page, region):  # a table, not this figure
                continue
            return which, region, rb, g, None, "side", bars
    ga, gb = renders.graphics_in(cap.page, ra), renders.graphics_in(cap.page, rb)
    a_ok, b_ok = _graphic_h(ga) >= 8, _graphic_h(gb) >= 8
    if a_ok and b_ok:
        side = "above" if _style_vote(doc, caps, renders, cap_ids) != "caption-above" else "below"
    elif a_ok or b_ok:
        side = "above" if a_ok else "below"
    else:
        side = None
    return side, ra, rb, ga, gb, span, barriers


def _style_vote(doc: Doc, caps, renders: _Renders, cap_ids: set) -> str:
    """Document-level caption placement from the unambiguous figures (most papers: caption below)."""
    if doc.style_vote is None:
        votes = Counter()
        for c in caps:
            if c.kind != "figure":
                continue
            ra, rb, _, _ = _regions(doc, c, caps, cap_ids, renders)
            a, b = _graphic_h(renders.graphics_in(c.page, ra)) >= 8, _graphic_h(renders.graphics_in(c.page, rb)) >= 8
            if a != b:
                votes["caption-below" if a else "caption-above"] += 1
        doc.style_vote = "caption-above" if votes["caption-above"] > votes["caption-below"] else "caption-below"
    return doc.style_vote


def _narrow_to_caption(doc: Doc, cap: Caption, caps, cap_ids: set, renders: _Renders, region, side):
    """A caption much narrower than its region (minipages: a figure beside a table or another figure, captions at
    different heights): keep only the ink intervals — split by white vertical gutters — that overlap the caption,
    then recompute the region for that x-range. None when nothing needs narrowing."""
    width = region[2] - region[0]
    if width <= 0 or (cap.x1 - cap.x0) >= 0.6 * width:
        return None
    k = renders.dpi / 72
    cols = renders.ink_cols(cap.page, region)
    need = max(1, int(6 * k))
    ivs, start, last, white = [], None, None, 0
    for i, v in enumerate(cols + [False] * (need + 1)):
        if v:
            start = i if start is None else start
            last, white = i, 0
        elif start is not None:
            white += 1
            if white >= need:
                ivs.append((region[0] + start / k, region[0] + (last + 1) / k))
                start = None
    keep = [iv for iv in ivs if iv[1] > cap.x0 - 4 and iv[0] < cap.x1 + 4]
    if not keep or len(keep) == len(ivs):
        return None
    # narrow only when the dropped side is another float's (its caption sits there): an image grid with a short
    # centred caption has white gaps between its columns too
    drop = [iv for iv in ivs if iv not in keep]
    lh = doc.body_h or 9.0
    owned = any(o is not cap and o.page == cap.page and any(a <= (o.x0 + o.x1) / 2 <= b for a, b in drop)
                and o.y1 >= region[1] - 3 * lh and o.y0 <= region[3] + 3 * lh for o in caps)
    if not owned:
        return None
    sx0, sx1 = max(region[0], min(a for a, _ in keep) - 2), min(region[2], max(b for _, b in keep) + 2)
    ra, rb, _, bars = _regions_in(doc, cap, [c for c in caps if c.page == cap.page], cap_ids, renders, sx0, sx1, "minipage")
    return (ra if side == "above" else rb), bars, "minipage"


def _crop_one(doc: Doc, cap: Caption, caps, renders: _Renders, cap_ids: set, out_dir: Path, dpi: int) -> FigureCrop:
    pg = doc.pages[cap.page - 1]
    side, ra, rb, ga, gb, span, barriers = _decide(doc, cap, caps, renders, cap_ids)
    fc = FigureCrop(cap.number, cap.page, None, cap.text, None, span=span)
    if side in ("left", "right") and ga is not None:
        region, bbox, fc.layout = ra, _attach_text(doc, pg, ga, ra, cap, barriers), "caption-side"
    elif side in ("above", "below"):
        region, g = (ra, ga) if side == "above" else (rb, gb)
        narrowed = _narrow_to_caption(doc, cap, caps, cap_ids, renders, region, side)
        if narrowed is not None:
            region, barriers, fc.span = narrowed
            g = renders.graphics_in(cap.page, region)
            if g is None:
                fc.problem = f"no figure graphics found next to the caption's column on page {cap.page}"
                return fc
        bbox, fc.layout = _attach_text(doc, pg, g, region, cap, barriers), ("caption-below" if side == "above" else "caption-above")
    else:  # never guess from text alone: neighbouring body text would be cropped as a "figure"
        fc.problem = f"no figure graphics found above, below or beside the caption on page {cap.page}"
        return fc
    pad = 2.0
    bbox = (max(region[0], bbox[0] - pad), max(region[1], bbox[1] - pad), min(region[2], bbox[2] + pad), min(region[3], bbox[3] + pad))
    if bbox[2] - bbox[0] < 20 or bbox[3] - bbox[1] < 10:
        fc.problem = f"figure region on page {cap.page} is degenerate ({bbox[2] - bbox[0]:.0f}x{bbox[3] - bbox[1]:.0f} pt)"
        return fc
    k = dpi / 72
    img = renders.image(cap.page).crop((int(bbox[0] * k), int(bbox[1] * k), int(bbox[2] * k + 0.5), int(bbox[3] * k + 0.5)))
    out_dir.mkdir(parents=True, exist_ok=True)
    fc.png, fc.bbox = out_dir / f"fig{cap.number}.png", tuple(round(v, 2) for v in bbox)
    img.save(fc.png)
    meta = {"number": cap.number, "page": cap.page, "bbox_pt": list(fc.bbox), "dpi": dpi, "caption": cap.text,
            "layout": fc.layout, "span": fc.span, "pdf": str(doc.path)}
    (out_dir / f"fig{cap.number}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return fc


def crop_figures(pdf, out_dir, numbers=None, dpi: int = 200) -> list[FigureCrop]:
    """Crop figures by caption. Requested numbers that cannot be cropped raise PaperFigError; in
    all-figures mode a failed figure is returned with ``problem`` set (never silently dropped)."""
    pdf, out_dir = Path(pdf), Path(out_dir)
    if not pdf.is_file():
        raise PaperFigError(f"PDF not found: {pdf}")
    doc = _layout(pdf)
    caps = _captions(doc)
    figs = [c for c in caps if c.kind == "figure"]
    if not figs:
        raise PaperFigError(f"no figure caption ('Figure N.' / 'Fig. N:' at the start of a line) found in {pdf.name} — "
                            "the PDF may have no text layer; crop this figure by hand")
    first = {}
    for c in figs:
        first.setdefault(c.number, c)
    wanted = sorted({int(n) for n in numbers}) if numbers else list(range(1, max(first) + 1))
    cap_ids = {i for c in caps for i in c.blocks}
    renders = _Renders(doc, dpi)
    try:
        out = [_crop_one(doc, first[n], caps, renders, cap_ids, out_dir, dpi) for n in wanted if n in first]
    finally:
        renders.close()
    for n in wanted:  # a number with no caption is reported, never silently skipped
        if n not in first:
            out.append(FigureCrop(n, 0, None, "", None, problem=f"no caption 'Figure {n}' found in {pdf.name}"))
    out.sort(key=lambda c: c.number)
    problems = [f"figure {c.number}: {c.problem}" for c in out if c.problem]
    if numbers and problems:
        raise PaperFigError("; ".join(problems))
    return out
