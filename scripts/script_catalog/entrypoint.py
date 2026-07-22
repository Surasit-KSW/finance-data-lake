"""
script_catalog/entrypoint.py
=============================
Detect whether a source file is a runnable entry-point (as opposed to a
helper/library module that's only ever imported). Used by scanner.py to
filter which files make it into the catalog.
"""
import re
from pathlib import Path

_MAIN_GUARD_RE = re.compile(r"""__name__\s*==\s*['"]__main__['"]""")
_MJS_MAIN_CALL_RE = re.compile(r"^\s*(await\s+)?main\s*\(", re.MULTILINE)


def is_python_entrypoint(path: Path) -> bool:
    """Return True if the .py file contains a `if __name__ == "__main__":` guard."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return bool(_MAIN_GUARD_RE.search(text))


def is_batch_entrypoint(path: Path) -> bool:
    """.bat / .cmd files are always considered entry-points."""
    return path.suffix.lower() in (".bat", ".cmd")


def is_mjs_entrypoint(path: Path) -> bool:
    """Return True if the .mjs file calls a top-level main()-style function."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return bool(_MJS_MAIN_CALL_RE.search(text))


def is_entrypoint(path: Path) -> bool:
    """Dispatch to the right entry-point check based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".py":
        return is_python_entrypoint(path)
    if suffix in (".bat", ".cmd"):
        return is_batch_entrypoint(path)
    if suffix == ".mjs":
        return is_mjs_entrypoint(path)
    return False
