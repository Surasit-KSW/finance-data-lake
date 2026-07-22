"""
scan_scripts.py
================
Cross-repo script catalog scanner. Walks every repo listed in repos.yaml,
detects entry-point scripts, and merges results into script-catalog.json
(the Vault) without clobbering AI-backfilled description/category fields.

Usage:
    python scan_scripts.py
    python scan_scripts.py --config repos.yaml --catalog "D:\\...\\script-catalog.json"

See: docs/superpowers/specs/2026-07-22-script-catalog-discovery-design.md
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from script_catalog.scanner import load_repos_config, scan_all
from script_catalog.extract import extract_description, extract_cli_flags
from script_catalog.merge import merge_catalog

DEFAULT_CONFIG = Path(__file__).resolve().parent / "repos.yaml"
DEFAULT_CATALOG = Path(
    r"D:\_Work_Workspace\03_Data_Projects\_Finance-Vault\09-AI-Memory\script-catalog.json"
)


def load_existing_catalog(path: Path) -> list[dict]:
    """Load the existing catalog JSON, or an empty list if it doesn't exist yet."""
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def enrich_with_extraction(entries: list[dict]) -> list[dict]:
    """Fill in best-effort description/cli_flags for each freshly scanned entry."""
    for entry in entries:
        path = Path(entry["path"])
        entry["description"] = extract_description(path)
        entry["cli_flags"] = extract_cli_flags(path)
    return entries


def run_scan(config_path: Path, catalog_path: Path) -> list[dict]:
    """Scan all configured repos, merge into the existing catalog, and save it."""
    repos = load_repos_config(config_path)
    scanned = enrich_with_extraction(scan_all(repos))
    existing = load_existing_catalog(catalog_path)
    merged = merge_catalog(existing, scanned)

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan repos and update script-catalog.json")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()

    merged = run_scan(args.config, args.catalog)

    needs_desc = sum(1 for e in merged if e.get("status") == "needs_description")
    stale = sum(1 for e in merged if e.get("status") == "stale")
    print(
        f"Scanned -> {len(merged)} entries "
        f"({needs_desc} need description, {stale} stale) -> {args.catalog}"
    )


if __name__ == "__main__":
    main()
