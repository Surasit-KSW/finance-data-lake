"""
etl_tb.py — Trial Balance Silver ETL
Reads: 01_Bronze_Raw/PRD_GI/AMC_TB_MM.YYYY.XLSX  (5 files per year so far)
Writes: 02_Silver_Cleaned/master_tb_1000.parquet

Usage:
  python 04_Data_Pipelines/silver_transform/etl_tb.py
  python 04_Data_Pipelines/silver_transform/etl_tb.py --year 2026
"""
import sys
import re
import argparse
from pathlib import Path
import pandas as pd
import openpyxl

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BRONZE_PATH = PROJECT_ROOT / "01_Bronze_Raw" / "PRD_GI"
SILVER_PATH = PROJECT_ROOT / "02_Silver_Cleaned"
COMPANY_CODE = "1000"
OUTPUT_FILE = SILVER_PATH / f"master_tb_{COMPANY_CODE}.parquet"


def parse_filename(fname: str):
    """Parse 'AMC_TB_MM.YYYY.XLSX' -> (month: int, year: int) or None."""
    m = re.match(r"AMC_TB_(\d{2})\.(\d{4})\.XLSX", fname, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def read_tb_file(fpath: Path, month: int, year: int) -> pd.DataFrame:
    """Read one TB Excel file, return cleaned DataFrame."""
    print(f"  Reading {fpath.name} ...", end=" ")
    try:
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        for row in ws.iter_rows(values_only=True):
            fs_item = str(row[0]).strip() if row[0] is not None else ""
            raw_name = str(row[1]).strip() if row[1] is not None else ""
            account_code = str(row[2]).strip() if row[2] is not None else ""
            balance = row[3]

            # Skip header row and section-summary rows (Account Number empty or non-numeric)
            if not account_code or not account_code.replace(" ", "").isdigit():
                continue
            if not isinstance(balance, (int, float)):
                try:
                    balance = float(balance)
                except (TypeError, ValueError):
                    continue

            # Extract account name by removing leading account code from raw text
            account_name = raw_name
            if raw_name.startswith(account_code):
                account_name = raw_name[len(account_code):].strip()

            rows.append({
                "company_code":    COMPANY_CODE,
                "year":            year,
                "month":           month,
                "account_code":    account_code,
                "account_name":    account_name,
                "fs_item":         fs_item,
                "closing_balance": float(balance),
            })

        wb.close()
        df = pd.DataFrame(rows)
        print(f"OK ({len(df):,} rows)")
        return df

    except Exception as e:
        print(f"ERROR: {e}")
        return pd.DataFrame()


def run(year_filter: int = None):
    print(f"\n{'='*55}")
    print("  Finance Data Lake -- TB Silver ETL")
    print(f"{'='*55}")

    all_frames = []
    files = sorted(BRONZE_PATH.glob("AMC_TB_*.XLSX"))
    if not files:
        # Try lowercase extension
        files = sorted(BRONZE_PATH.glob("AMC_TB_*.xlsx"))

    if not files:
        print(f"  WARNING: No TB files found in: {BRONZE_PATH}")
        return

    for fpath in files:
        parsed = parse_filename(fpath.name)
        if not parsed:
            continue
        month, year = parsed
        if year_filter and year != year_filter:
            continue
        df = read_tb_file(fpath, month, year)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        print("  WARNING: No data extracted.")
        return

    combined = pd.concat(all_frames, ignore_index=True)

    # Enforce types
    combined["year"] = combined["year"].astype(int)
    combined["month"] = combined["month"].astype(int)
    combined["closing_balance"] = combined["closing_balance"].astype(float)

    combined.to_parquet(OUTPUT_FILE, index=False)

    print(f"\n  Saved: {OUTPUT_FILE.name}  ({len(combined):,} rows, {len(all_frames)} months)")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TB Silver ETL")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    run(year_filter=args.year)
