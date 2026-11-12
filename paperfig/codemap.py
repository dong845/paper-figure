"""Code map for the code-analyst agent: classes, bases, methods and forward() lines, via ast (Python).
Other source files are listed by path so the agent knows they exist."""
from __future__ import annotations

import ast
from pathlib import Path

SKIP_DIRS = {".git", "venv", ".venv", "env", "build", "dist", "node_modules", "__pycache__", "site-packages", ".tox", ".eggs"}
OTHER_SRC = {".cpp", ".cu", ".c", ".h", ".hpp", ".js", ".ts", ".jl", ".m", ".rs", ".go", ".java", ".lua"}


def _name(n) -> str:
    try:
        return ast.unparse(n)
    except Exception:  # pragma: no cover
        return "?"


def code_map(repo) -> dict:
    repo = Path(repo).expanduser()
    files, others, errors = [], [], []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
            continue
        if p.suffix in OTHER_SRC:
            others.append(str(rel))
            continue
        if p.suffix != ".py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            errors.append({"path": str(rel), "error": f"SyntaxError line {e.lineno}: {e.msg}"})
            continue
        classes, funcs = [], []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [{"name": m.name, "line": m.lineno} for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                fwd = next((m["line"] for m in methods if m["name"] in ("forward", "__call__", "call")), None)
                classes.append({"name": node.name, "line": node.lineno, "bases": [_name(b) for b in node.bases],
                                "methods": methods, "forward_line": fwd})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append({"name": node.name, "line": node.lineno})
        if classes or funcs:
            files.append({"path": str(rel), "classes": classes, "functions": funcs})
    return {"repo": str(repo), "files": files, "other_sources": others, "errors": errors}
