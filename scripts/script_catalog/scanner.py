"""
script_catalog/scanner.py
==========================
Walk configured repo roots and collect entry-point script files, respecting
per-repo exclude_dirs plus a fixed set of always-excluded directories.
"""
import datetime
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from script_catalog.entrypoint import is_entrypoint

SCANNED_EXTENSIONS = (".py", ".mjs", ".bat", ".cmd")
ALWAYS_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


@dataclass
class RepoConfig:
    name: str
    root: Path
    exclude_dirs: list[str] = field(default_factory=list)


def load_repos_config(config_path: Path) -> list[RepoConfig]:
    """Load repos.yaml into a list of RepoConfig."""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    repos = []
    for entry in data["repos"]:
        repos.append(RepoConfig(
            name=entry["name"],
            root=Path(entry["root"]),
            exclude_dirs=entry.get("exclude_dirs") or [],
        ))
    return repos


def _is_excluded(path: Path, root: Path, exclude_dirs: list[str]) -> bool:
    """Return True if any path segment relative to root is an excluded dir."""
    excluded = ALWAYS_EXCLUDED_DIRS | set(exclude_dirs)
    relative_parts = path.relative_to(root).parts
    return any(part in excluded for part in relative_parts)


def _mtime_date(path: Path) -> str:
    """Return the file's last-modified date as YYYY-MM-DD."""
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def scan_repo(repo: RepoConfig) -> list[dict]:
    """
    Walk `repo.root`, returning a raw entry (no description/category yet)
    for every entry-point file found, skipping excluded directories.
    """
    entries = []
    if not repo.root.exists():
        return entries

    for path in repo.root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCANNED_EXTENSIONS:
            continue
        if path.name == "__init__.py":
            continue
        if _is_excluded(path, repo.root, repo.exclude_dirs):
            continue
        if not is_entrypoint(path):
            continue

        relative_path = path.relative_to(repo.root).as_posix()
        language = path.suffix.lower().lstrip(".")
        if language == "cmd":
            language = "bat"

        entries.append({
            "id": f"{repo.name}:{relative_path}",
            "repo": repo.name,
            "path": str(path),
            "language": language,
            "last_modified": _mtime_date(path),
        })
    return entries


def scan_all(repos: list[RepoConfig]) -> list[dict]:
    """Scan every configured repo and return the combined list of raw entries."""
    all_entries = []
    for repo in repos:
        all_entries.extend(scan_repo(repo))
    return all_entries
