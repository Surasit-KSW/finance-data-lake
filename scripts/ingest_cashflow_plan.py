"""
ingest_cashflow_plan.py — Copy cashflow plan Excel from Downloads to Bronze.

Source filename: cashflow_plan_YYYY.xlsx  (e.g. cashflow_plan_2026.xlsx)
Target: 01_Bronze_Raw/cashflow_plan/cashflow_plan_YYYY.xlsx

Usage:
    python scripts/ingest_cashflow_plan.py
    python scripts/ingest_cashflow_plan.py --src "C:/Users/me/Downloads" --run-etl
    python scripts/ingest_cashflow_plan.py --dry-run
"""
import sys
import re
import shutil
import argparse
import subprocess
from pathlib import Path

LAKE_ROOT = Path(__file__).resolve().parents[1]
BRONZE    = LAKE_ROOT / "01_Bronze_Raw" / "cashflow_plan"
PATTERN   = re.compile(r"cashflow_plan_(\d{4})\.xlsx", re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=None)
    parser.add_argument("--run-etl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src_dir = Path(args.src) if args.src else Path.home() / "Downloads"
    if not src_dir.exists():
        print(f"ERROR: {src_dir} not found"); sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Scanning: {src_dir}")
    matches = [(f, f.name) for f in src_dir.iterdir()
               if f.is_file() and PATTERN.match(f.name)]

    if not matches:
        print("  No matching files (expected: cashflow_plan_YYYY.xlsx)"); return

    BRONZE.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src, name in sorted(matches):
        dst = BRONZE / name
        if dst.exists():
            print(f"  SKIP  (exists) {name}")
        elif args.dry_run:
            print(f"  DRY   {name}")
        else:
            shutil.copy2(src, dst)
            print(f"  OK    {name}")
            copied += 1

    if args.run_etl and not args.dry_run and copied > 0:
        etl = LAKE_ROOT / "04_Data_Pipelines" / "silver_transform" / "etl_cashflow_plan.py"
        subprocess.run([sys.executable, str(etl)], cwd=str(LAKE_ROOT), check=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
