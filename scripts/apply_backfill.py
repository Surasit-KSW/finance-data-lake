"""
apply_backfill.py
===================
Merge one or more AI-backfill result JSON files (id -> {description,
category}) into script-catalog.json, flipping status to "active" for
matched entries. Used once during the initial catalog backfill (see the
implementation plan, Task 10), and again any time a batch of
"needs_description" entries gets reviewed.

Usage:
    python apply_backfill.py backfill_finance-ops-workspace.json backfill_finance-data-lake.json
    python apply_backfill.py --catalog "D:\\...\\script-catalog.json" backfill_x.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from script_catalog.backfill import apply_backfill

DEFAULT_CATALOG = Path(
    r"D:\_Work_Workspace\03_Data_Projects\_Finance-Vault\09-AI-Memory\script-catalog.json"
)


def run_apply(catalog_path: Path, backfill_paths: list[Path]) -> list[dict]:
    """Merge every backfill file into the catalog and save the result."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    combined_backfill: dict[str, dict] = {}
    for backfill_path in backfill_paths:
        combined_backfill.update(json.loads(backfill_path.read_text(encoding="utf-8")))

    updated = apply_backfill(catalog, combined_backfill)

    catalog_path.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply AI backfill results into script-catalog.json")
    parser.add_argument("backfill_files", nargs="+", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()

    updated = run_apply(args.catalog, args.backfill_files)

    remaining = sum(1 for e in updated if e.get("status") == "needs_description")
    print(
        f"Applied backfill from {len(args.backfill_files)} file(s) -> {args.catalog} "
        f"({remaining} entries still need description)"
    )


if __name__ == "__main__":
    main()
