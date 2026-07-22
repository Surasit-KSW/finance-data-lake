"""
script_catalog/extract.py
==========================
Best-effort extraction of a short description and CLI flags from a script's
existing docstring / argparse calls. Pre-fills new catalog entries; the
one-time AI backfill pass (see the implementation plan, Task 10) later
overwrites `description` and assigns `category` with higher-quality summaries.
"""
import ast
from pathlib import Path


def extract_description(path: Path) -> str | None:
    """Return the module-level docstring's first non-empty, non-rule line, or None."""
    if path.suffix.lower() != ".py":
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return None
    docstring = ast.get_docstring(tree)
    if not docstring:
        return None
    for line in docstring.strip().splitlines():
        line = line.strip()
        if line and not set(line) <= {"=", "-"}:
            return line
    return None


def extract_cli_flags(path: Path) -> list[str]:
    """Return every `--flag` string passed to `add_argument(...)` calls."""
    if path.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []

    flags: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_add_argument = isinstance(func, ast.Attribute) and func.attr == "add_argument"
        if not is_add_argument:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
                flags.append(arg.value)
    return flags
