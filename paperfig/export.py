"""Export via the draw.io desktop CLI. Fails loudly: missing binary, non-zero
exit, timeout, or a missing/stale output file all raise ExportError."""
from __future__ import annotations

import math
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from .errors import ExportError

INSTALL_HINT = ("install draw.io desktop (https://github.com/jgraph/drawio-desktop/releases) "
                "or set PAPERFIG_DRAWIO to its executable; on headless Linux run under xvfb-run")
_DEFAULTS = {
    "Darwin": ["/Applications/draw.io.app/Contents/MacOS/draw.io", "~/Applications/draw.io.app/Contents/MacOS/draw.io"],
    "Linux": ["/opt/drawio/drawio", "/usr/bin/drawio", "/snap/bin/drawio", "/usr/local/bin/drawio"],
    "Windows": ["C:/Program Files/draw.io/draw.io.exe", "~/AppData/Local/Programs/draw.io/draw.io.exe"],
}


def find_drawio() -> str:
    env = os.environ.get("PAPERFIG_DRAWIO")
    if env:
        p = Path(env).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        raise ExportError(f"PAPERFIG_DRAWIO={env} is not an executable file; {INSTALL_HINT}")
    for name in ("drawio", "draw.io"):
        w = shutil.which(name)
        if w:
            return w
    for cand in _DEFAULTS.get(platform.system(), []):
        p = Path(cand).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise ExportError(f"draw.io desktop not found; {INSTALL_HINT}")


def print_px(width_in: float, dpi: int = 300) -> int:
    return int(math.floor(width_in * dpi + 0.5))


def export(src, fmt: str, out, width_px: int | None = None, scale: float | None = None, border: int = 12,
           timeout_s: float = 120, binary: str | None = None) -> Path:
    if fmt not in ("png", "pdf", "svg"):
        raise ExportError(f"unsupported export format '{fmt}'")
    src, out = Path(src).resolve(), Path(out).resolve()
    if not src.is_file():
        raise ExportError(f"input diagram not found: {src}")
    out.parent.mkdir(parents=True, exist_ok=True)
    exe = binary or find_drawio()
    cmd = [exe, "-x", "-f", fmt, "-o", str(out), "--border", str(border)]
    if fmt == "png" and width_px:
        cmd += ["--width", str(int(width_px))]
    elif scale:
        cmd += ["-s", str(scale)]
    if fmt == "pdf":
        cmd += ["--crop"]
    extra = os.environ.get("PAPERFIG_DRAWIO_ARGS")
    if extra:
        cmd += extra.split()
    cmd.append(str(src))
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise ExportError(f"draw.io export timed out after {timeout_s:.0f}s: {' '.join(cmd)}")
    except OSError as e:
        raise ExportError(f"cannot run draw.io ({exe}): {e}; {INSTALL_HINT}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise ExportError(f"draw.io export failed (exit {proc.returncode}): {tail}")
    if not out.is_file() or out.stat().st_size == 0 or out.stat().st_mtime < start - 1:
        tail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise ExportError(f"draw.io export produced no output file {out}" + (f": {tail}" if tail else ""))
    return out
