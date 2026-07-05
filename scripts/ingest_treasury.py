"""
ingest_treasury.py — Copy treasury source files to Bronze with canonical naming.

Source filenames (from Finance team):
  Control LC TR DD.MM.YYYY.xlsx        → control_lc_tr_YYYY_MM_DD.xlsx
  Copy of AMC_Cashflow_DD.MM.YY.xlsx   → amc_cashflow_YYYY_MM_DD.xlsx
  AMC_Cashflow_DD.MM.YY.xlsx           → amc_cashflow_YYYY_MM_DD.xlsx

Target: 01_Bronze_Raw/treasury/

Usage:
    python scripts/ingest_treasury.py
    python scripts/ingest_treasury.py --src "C:/Users/me/Downloads"
    python scripts/ingest_treasury.py --src "C:/Users/me/Downloads" --run-etl
    python scripts/ingest_treasury.py --dry-run

Options:
    --src DIR      Source directory to scan (default: ~/Downloads)
    --run-etl      After copying, run etl_treasury_positions.py + etl_treasury_banks.py
    --dry-run      Print what would happen without copying
"""
import sys
import re
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

LAKE_ROOT = Path(__file__).resolve().parents[1]
BRONZE    = LAKE_ROOT / "01_Bronze_Raw" / "treasury"

# ── Filename patterns ──────────────────────────────────────────────────────────
# Each entry: (regex, canonical_prefix)
# Regex must capture groups: (day, month, year) — year may be 2 or 4 digits
PATTERNS = [
    (
        # "Control LC TR 04.07.2026.xlsx"  or  "Control LC TR 04.07.26.xlsx"
        re.compile(r"Control\s+LC\s+TR\s+(\d{2})\.(\d{2})\.(\d{2,4})\.xlsx", re.IGNORECASE),
        "control_lc_tr",
    ),
    (
        # "Copy of AMC_Cashflow_04.07.26.xlsx"  or  "AMC_Cashflow_04.07.2026.xlsx"
        re.compile(r"(?:Copy\s+of\s+)?AMC_Cashflow_(\d{2})\.(\d{2})\.(\d{2,4})\.xlsx", re.IGNORECASE),
        "amc_cashflow",
    ),
]


def _parse_date(day: str, month: str, year: str) -> str:
    """Return YYYY_MM_DD string. Expands 2-digit year to 4-digit (2000+)."""
    y = int(year)
    if y < 100:
        y += 2000
    return f"{y:04d}_{int(month):02d}_{int(day):02d}"


def find_source_files(src_dir: Path) -> list[tuple[Path, str]]:
    """
    Scan src_dir for files matching treasury patterns.
    Returns list of (source_path, canonical_name) pairs.
    """
    results = []
    for f in src_dir.iterdir():
        if not f.is_file() or f.suffix.lower() != ".xlsx":
            continue
        for pattern, prefix in PATTERNS:
            m = pattern.match(f.name)
            if m:
                date_str = _parse_date(*m.groups())
                canonical = f"{prefix}_{date_str}.xlsx"
                results.append((f, canonical))
                break  # matched — skip remaining patterns
    return results


def copy_to_bronze(src: Path, canonical: str, dry_run: bool) -> str:
    dst = BRONZE / canonical
    if dst.exists():
        return f"  SKIP  (already exists): {canonical}"
    if dry_run:
        return f"  DRY   {src.name!r:55s} → treasury/{canonical}"
    BRONZE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"  OK    {src.name!r:55s} → treasury/{canonical}"


def run_etl() -> None:
    etl_dir = LAKE_ROOT / "04_Data_Pipelines" / "silver_transform"
    scripts = ["etl_treasury_positions.py", "etl_treasury_banks.py"]
    for script in scripts:
        path = etl_dir / script
        print(f"\n  Running {script} ...")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(LAKE_ROOT),
            capture_output=False,
        )
        if result.returncode != 0:
            print(f"  ERROR: {script} exited with code {result.returncode}")
        else:
            print(f"  OK    {script} complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy treasury files to Bronze layer.")
    parser.add_argument("--src", default=None, help="Source directory (default: ~/Downloads)")
    parser.add_argument("--run-etl", action="store_true", help="Run Silver ETL after copy")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, no changes")
    args = parser.parse_args()

    src_dir = Path(args.src) if args.src else Path.home() / "Downloads"
    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Scanning: {src_dir}")
    print(f"Target:   {BRONZE}")
    print("=" * 70)

    matches = find_source_files(src_dir)

    if not matches:
        print(
            "\n  No matching files found.\n"
            "  Expected filenames:\n"
            "    Control LC TR DD.MM.YYYY.xlsx\n"
            "    AMC_Cashflow_DD.MM.YY.xlsx  (or 'Copy of ...')\n"
        )
        return

    print(f"\n[COPY] {len(matches)} file(s)")
    copied = 0
    for src, canonical in sorted(matches, key=lambda x: x[1]):
        msg = copy_to_bronze(src, canonical, args.dry_run)
        print(msg)
        if msg.startswith("  OK"):
            copied += 1

    print(f"\n{'Would copy' if args.dry_run else 'Copied'} {copied}/{len(matches)} file(s).")

    if args.run_etl and not args.dry_run:
        if copied == 0:
            print("\nNothing new copied — skipping ETL.")
        else:
            print("\n[ETL] Running Silver transform ...")
            run_etl()
            print("\nETL complete.")
    elif args.run_etl and args.dry_run:
        print("\n(--run-etl skipped in dry-run mode)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
