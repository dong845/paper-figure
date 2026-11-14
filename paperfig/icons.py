"""Icons: a common set ships in assets/icons/; any other Lucide icon is fetched on first use and cached (user,
2026-11-14: a fixed list always misses one). Lucide is ISC-licensed; the version is pinned so a name always means
the same drawing, and `search` reads Lucide's own tags (synonyms) to find a name.

Offline (PAPERFIG_OFFLINE=1) or a failed fetch stops the build with the missing name — never a blank icon.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .errors import PaperFigError

LUCIDE_VERSION = "0.460.0"
BASE = f"https://unpkg.com/lucide-static@{LUCIDE_VERSION}"
LOCAL = Path(__file__).resolve().parent.parent / "assets" / "icons"
CACHE = Path(os.environ.get("PAPERFIG_CACHE") or Path.home() / ".cache" / "paper-figure") / "icons" / f"lucide-{LUCIDE_VERSION}"
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SVG = 50_000  # bytes; a Lucide icon is a few hundred


def _get(url: str) -> bytes:
    from .refs import _get_retry
    return _get_retry(url, timeout=30)


def _offline() -> bool:
    return os.environ.get("PAPERFIG_OFFLINE", "").strip() not in ("", "0")


def resolve(name: str) -> Path:
    """The SVG file for an icon name: shipped, cached, or fetched now (then cached)."""
    if not isinstance(name, str) or not NAME.match(name):
        raise PaperFigError(f"icon name {name!r} is not a Lucide name (lower-case words joined by '-', e.g. 'gamepad-2')")
    for p in (LOCAL / f"{name}.svg", CACHE / f"{name}.svg"):
        if p.is_file():
            return p
    if _offline():
        raise PaperFigError(f"icon '{name}' is neither shipped nor cached and PAPERFIG_OFFLINE is set — fetch it once "
                            f"online (`paperfig icon fetch {name}`) or pick a shipped one (`paperfig icon search …`)")
    try:
        data = _get(f"{BASE}/icons/{name}.svg")
    except Exception as e:  # noqa: BLE001 — any network failure names the icon
        raise PaperFigError(f"icon '{name}' could not be fetched from Lucide {LUCIDE_VERSION}: {e} — check the name with "
                            "`paperfig icon search`, or pick a shipped icon") from e
    text = data.decode("utf-8", errors="replace").lstrip()
    body = re.sub(r"^(<\?xml[^>]*\?>|<!--.*?-->|\s)+", "", text, flags=re.S)  # Lucide opens with a licence comment
    if len(data) > MAX_SVG or not body.startswith("<svg") or "</svg>" not in body:
        raise PaperFigError(f"icon '{name}': Lucide answered with something that is not an SVG (no such icon?) — "
                            "`paperfig icon search` lists real names")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{name}.svg"
    out.write_text(text, encoding="utf-8")
    return out


def _tags() -> dict:
    p = CACHE / "tags.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if _offline():
        raise PaperFigError("icon search needs Lucide's tag list once online (PAPERFIG_OFFLINE is set)")
    data = json.loads(_get(f"{BASE}/tags.json").decode("utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data


def search(query: str, limit: int = 12) -> list[tuple[str, bool]]:
    """(name, shipped) for icons whose name or tags match the query's words — most words matched first, then
    whole-word matches, then shorter (plainer) names."""
    words = [w for w in re.split(r"\W+", query.lower()) if w]
    scored = []
    for name, tags in _tags().items():
        name_words = name.split("-")
        tag_words = {x for t in tags for x in re.split(r"\W+", str(t).lower()) if x}
        score = 0.0
        for w in words:
            stem = w[:max(4, len(w) - 3)]  # "controller" ~ "control"
            if w in name_words:
                score += 3
            elif w in tag_words:
                score += 2
            elif len(w) >= 4 and any(x.startswith(stem) for x in name_words + sorted(tag_words)):
                score += 1.5
            elif len(w) >= 4 and (w in name or any(w in x for x in tag_words)):
                score += 1
        if score:
            scored.append((-score, len(name), name))
    return [(n, (LOCAL / f"{n}.svg").is_file()) for *_, n in sorted(scored)[:limit]]
