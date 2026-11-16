"""Build the upload zip for skill hosts: `python3 tools/release_zip.py [--worktree] [OUT.zip]` (default
out/paper-figure.zip; `--worktree` packs the tracked files as they are now, to check a change before committing it).

What ships is `git archive HEAD` (so `.gitattributes` export-ignore applies and uncommitted edits do not), with two
changes that keep the unpacked package under the host's 3 MB cap without changing what a run sees:
- cards/*.json (441 files, ~3.7 MB) become one gzip file, kb/cards.json.gz (~0.9 MB), which `kb.load_kb` reads;
- kb/index.json (~2.3 MB) is left out: it is generated from the cards, and only `kb validate`'s staleness check
  reads it (`kb index` rebuilds it from the pack when wanted).
Before writing the zip it loads the knowledge base from the staged tree and checks every card is identical to the
one in HEAD and `kb validate` finds nothing new, then refuses a package that breaks the host's limits
(3 MB packed and unpacked, root/dir/file depth). Lives in tools/ (export-ignore): a maintainer's tool, not shipped.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 3_000_000  # bytes, packed and unpacked; the host's "3 MB" read as the smaller decimal megabyte

_PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[2])
from paperfig import kb
assert kb.__file__.startswith(sys.argv[2]), kb.__file__  # the tree's own code, not an installed copy
k = kb.load_kb(data=sys.argv[1])
cards = {cid: {x: y for x, y in c.items() if x not in ("layer", "_file")} for cid, c in k.cards.items()}
print(json.dumps({"cards": cards, "problems": kb.validate(data=sys.argv[1])}))
"""


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


_PACK = r"""
import sys
sys.path.insert(0, sys.argv[1])
from paperfig import kb
assert kb.__file__.startswith(sys.argv[1]), kb.__file__
print(kb.write_cards_pack(kb.REPO_CARDS, kb.REPO_KB / kb.CARDS_PACK))
"""


def _pack(tree: Path) -> int:
    """Pack with the staged tree's own packer (the same code its loader comes from), in a fresh interpreter so an
    already-imported paperfig (tests) cannot stand in for it; -B keeps __pycache__ out of the package."""
    out = subprocess.run([sys.executable, "-B", "-c", _PACK, str(tree.resolve())], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"packing the cards in {tree} failed:\n{out.stderr[-2000:]}")
    return int(out.stdout.strip())


def _probe(tree: Path, empty_data: Path) -> dict:
    """The knowledge base as the tree's own code loads it (a fresh interpreter, so each tree's own code)."""
    out = subprocess.run([sys.executable, "-B", "-c", _PROBE, str(empty_data), str(tree.resolve())], cwd=tree,
                         capture_output=True, text=True)  # -B: no __pycache__ written into the package
    if out.returncode != 0:
        raise SystemExit(f"loading the knowledge base from {tree} failed:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout)


def build(out: Path, worktree: bool = False) -> dict:
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no").strip())
    tree = (_git("stash", "create").decode().strip() if worktree else "") or "HEAD"  # stash create: a commit of
    if dirty and tree == "HEAD":                                                       # the work tree, nothing touched
        print("note: uncommitted changes are not in the zip (it packs HEAD; --worktree packs them)", file=sys.stderr)
    head = _git("rev-parse", "--short", "HEAD").decode().strip() + (" + uncommitted" if tree != "HEAD" else "")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stage, ref, data = tmp / "stage", tmp / "ref", tmp / "data"
        data.mkdir()
        with zipfile.ZipFile(io.BytesIO(_git("archive", "--format=zip", tree))) as z:
            z.extractall(stage)
            z.extractall(ref)
            # git's own mode per file (extractall drops it, so an executable script would lose its x bit)
            modes = {i.filename: (i.external_attr >> 16) & 0o777 or 0o644 for i in z.infolist() if not i.is_dir()}
        n = _pack(stage)
        shutil.rmtree(stage / "cards")
        (stage / "kb" / "index.json").unlink(missing_ok=True)

        want, got = _probe(ref, data), _probe(stage, data)
        if got["cards"] != want["cards"]:
            diff = sorted(set(want["cards"]) ^ set(got["cards"])) or \
                sorted(c for c in want["cards"] if want["cards"][c] != got["cards"].get(c))
            raise SystemExit(f"packed cards differ from HEAD's cards/: {diff[:10]}")
        if len(got["cards"]) != n:
            raise SystemExit(f"packed {n} cards, the staged knowledge base loads {len(got['cards'])}")
        new = sorted(set(got["problems"]) - set(want["problems"]))
        if new:
            raise SystemExit("kb validate finds new problems in the packed tree:\n" + "\n".join(new[:10]))

        files = sorted(p for p in stage.rglob("*") if p.is_file())
        rel = [p.relative_to(stage).as_posix() for p in files]
        deep = [r for r in rel if r.count("/") > 1]
        unpacked = sum(p.stat().st_size for p in files)
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_name(out.name + ".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for d in sorted({r.rsplit("/", 1)[0] for r in rel if "/" in r}):
                info = zipfile.ZipInfo(d + "/", (1980, 1, 1, 0, 0, 0))
                info.external_attr = (0o040755 << 16) | 0x10  # a directory, rwxr-xr-x (0 = unreadable folders)
                z.writestr(info, b"")
            for p, r in zip(files, rel):
                info = zipfile.ZipInfo(r, (1980, 1, 1, 0, 0, 0))
                info.external_attr = (0o100000 | modes.get(r, 0o644)) << 16
                z.writestr(info, p.read_bytes(), zipfile.ZIP_DEFLATED, 9)
        packed = part.stat().st_size
        report = {"head": head, "zip": str(out), "files": len(files), "cards": n, "packed_bytes": packed,
                  "unpacked_bytes": unpacked, "too_deep": deep[:10]}
        bad = [m for m, hit in (("unpacked ≥ 3 MB", unpacked >= LIMIT), ("zip ≥ 3 MB", packed >= LIMIT),
                                ("deeper than root/dir/file", bool(deep)), ("no SKILL.md", "SKILL.md" not in rel)) if hit]
        if bad:
            part.unlink()
            raise SystemExit(f"refused: {', '.join(bad)} — {json.dumps(report)}")
        part.replace(out)
        return report


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--worktree"]
    r = build(Path(args[0]).expanduser() if args else ROOT / "out" / "paper-figure.zip", "--worktree" in sys.argv[1:])
    print(f"{r['zip']}  (HEAD {r['head']}): {r['files']} files, {r['cards']} cards packed, "
          f"zip {r['packed_bytes'] / 1e6:.2f} MB, unpacked {r['unpacked_bytes'] / 1e6:.2f} MB")
