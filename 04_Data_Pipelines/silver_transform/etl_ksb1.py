"""
etl_ksb1.py — KSB1 Cost Center Line Items Silver ETL
Reads: 01_Bronze_Raw/cost_center/amc/{plant}/{year}/ksb1_{YYYYMM}.xlsx
Writes: 02_Silver_Cleaned/master_ksb1_1000.parquet

Usage:
  python 04_Data_Pipelines/silver_transform/etl_ksb1.py
  python 04_Data_Pipelines/silver_transform/etl_ksb1.py --year 2026
"""
import sys
import re
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import openpyxl

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BRONZE_PATH = PROJECT_ROOT / "01_Bronze_Raw" / "cost_center" / "amc"
SILVER_PATH = PROJECT_ROOT / "02_Silver_Cleaned"
COMPANY_CODE = "1000"
OUTPUT_FILE = SILVER_PATH / f"master_ksb1_{COMPANY_CODE}.parquet"

# Only process these plant codes (skip _all_, _probe_, __ variants)
VALID_PLANTS = {"1100", "1200", "1300"}

# Derive plant from first 2 digits of cost_center (e.g. "1387110" → "13" → "1300")
CC_PREFIX_TO_PLANT = {"11": "1100", "12": "1200", "13": "1300"}


def derive_plant(cost_center: str) -> str:
    """Map cost_center prefix to plant code. Returns '' if unknown."""
    return CC_PREFIX_TO_PLANT.get(str(cost_center)[:2], "")


def parse_filename(fname: str, parent_dir: str = None):
    """Parse 'ksb1_{YYYYMM}.xlsx' or 'ksb1_all_{YYYYMM}.xlsx' → (source, month, year) or None.
    source = plant code (e.g. '1300') or 'all' for all-plant aggregate files."""
    # Per-plant file: ksb1_YYYYMM.xlsx
    m = re.match(r"ksb1_(\d{4})(\d{2})\.xlsx", fname, re.IGNORECASE)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        plant = str(parent_dir) if parent_dir else ""
        if plant in VALID_PLANTS:
            return plant, month, year
        if plant == "all":
            return "all", month, year
        return None

    # All-plant aggregate file: ksb1_all_YYYYMM.xlsx
    m2 = re.match(r"ksb1_all_(\d{4})(\d{2})\.xlsx", fname, re.IGNORECASE)
    if m2:
        year, month = int(m2.group(1)), int(m2.group(2))
        return "all", month, year

    return None


def _str(v) -> str:
    """Safely convert value to string, empty string if None."""
    return str(v).strip() if v is not None else ""


def read_ksb1_file(fpath: Path, source: str, month: int, year: int) -> pd.DataFrame:
    """Read one KSB1 Excel file, return cleaned DataFrame.
    source = plant code ('1100'/'1200'/'1300') or 'all' (all-plant file).
    When source='all', plant is derived per-row from cost_center prefix."""
    print(f"  ⏳ {fpath.name} ...", end=" ")
    try:
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        first_row = True
        for row in ws.iter_rows(values_only=True):
            if first_row:
                first_row = False
                continue  # skip header
            if row[0] is None:
                continue  # skip empty rows

            try:
                amount = float(row[3]) if row[3] is not None else 0.0
                quantity = float(row[4]) if row[4] is not None else 0.0
            except (TypeError, ValueError):
                amount = 0.0
                quantity = 0.0

            cc = _str(row[0])
            plant = derive_plant(cc) if source == "all" else source

            rows.append({
                "company_code":        COMPANY_CODE,
                "year":                year,
                "month":               month,
                "plant":               plant,
                "cost_center":         cc,
                "co_account":          _str(row[1]),
                "account_name":        _str(row[2]),
                "amount":              amount,
                "quantity":            quantity,
                "unit":                _str(row[5]),
                "doc_number":          _str(row[6]),
                "offsetting_account":  _str(row[8]),
                "offsetting_acct_name": _str(row[9]),
                "material":            _str(row[10]),
                "material_desc":       _str(row[11]),
                "ref_doc_number":      _str(row[12]),
                "source_file":         fpath.name,
            })

        wb.close()
        df = pd.DataFrame(rows)
        print(f"✅ {len(df):,} rows")
        return df

    except Exception as e:
        print(f"❌ {e}")
        return pd.DataFrame()


def run(year_filter: int = None):
    print(f"\n{'='*55}")
    print("  Finance Data Lake — KSB1 Silver ETL")
    print(f"{'='*55}")

    all_frames = []
    # New structure: cost_center/amc/{plant}/{year}/ksb1_{YYYYMM}.xlsx
    files = sorted(BRONZE_PATH.rglob("ksb1_*.xlsx"))
    if not files:
        files = sorted(BRONZE_PATH.rglob("ksb1_*.XLSX"))

    if not files:
        print(f"  ⚠️  No KSB1 files found in: {BRONZE_PATH}")
        return

    for fpath in files:
        # Plant is the first subdirectory under BRONZE_PATH (e.g. 1100, 1200, 1300)
        try:
            rel = fpath.relative_to(BRONZE_PATH)
            plant_dir = rel.parts[0]
        except (ValueError, IndexError):
            plant_dir = ""
        parsed = parse_filename(fpath.name, parent_dir=plant_dir)
        if not parsed:
            print(f"  ⏭  {fpath.name} — skipped (unrecognised filename)")
            continue
        source, month, year = parsed
        if year_filter and year != year_filter:
            continue
        df = read_ksb1_file(fpath, source, month, year)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        print("  ⚠️  No data extracted.")
        return

    combined = pd.concat(all_frames, ignore_index=True)

    # Drop rows where plant could not be derived (unknown CC prefix)
    unknown = combined["plant"] == ""
    if unknown.any():
        print(f"  ⏭  {unknown.sum():,} rows skipped — unknown plant (CC prefix not in mapping)")
    combined = combined[~unknown].copy()

    # Enforce types
    combined["year"] = combined["year"].astype(int)
    combined["month"] = combined["month"].astype(int)
    combined["amount"] = combined["amount"].astype(float)
    combined["quantity"] = combined["quantity"].astype(float)

    combined["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")
    combined.to_parquet(OUTPUT_FILE, index=False)

    plants = sorted(combined["plant"].unique())
    months = sorted(combined["month"].unique())
    print(f"\n  💾 Saved: {OUTPUT_FILE.name}  ({len(combined):,} rows)")
    print(f"     Plants: {plants} | Months: {months}")
    print(f"{'='*55}\n")


def upsert_file(file_path: Path) -> None:
    """Upsert เฉพาะไฟล์เดียว — ลบ rows เดิมของเดือนนั้น แล้ว append ใหม่"""
    try:
        rel = file_path.relative_to(BRONZE_PATH)
        plant_dir = rel.parts[0]
    except (ValueError, IndexError):
        plant_dir = ""
    parsed = parse_filename(file_path.name, parent_dir=plant_dir)
    if not parsed:
        print(f"  ❌ ไม่รู้จักชื่อไฟล์: {file_path.name}")
        return
    source, month, year = parsed
    print(f"  📄 Upsert: {file_path.name} (month={month} year={year})")

    df_new = read_ksb1_file(file_path, source, month, year)
    if df_new.empty:
        print(f"  ⚠️  ไม่มีข้อมูลใน {file_path.name}")
        return

    if OUTPUT_FILE.exists():
        df_existing = pd.read_parquet(OUTPUT_FILE)
        mask = (df_existing["year"].astype(int) == year) & (df_existing["month"].astype(int) == month)
        dropped = mask.sum()
        df_existing = df_existing[~mask]
        if dropped:
            print(f"  🗑  ลบ {dropped:,} rows เดิม (month={month} year={year})")
    else:
        df_existing = pd.DataFrame()

    combined = pd.concat([df_existing, df_new], ignore_index=True)
    unknown = combined["plant"] == ""
    combined = combined[~unknown].copy()
    combined["year"]     = combined["year"].astype(int)
    combined["month"]    = combined["month"].astype(int)
    combined["amount"]   = combined["amount"].astype(float)
    combined["quantity"] = combined["quantity"].astype(float)
    combined["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")
    combined.to_parquet(OUTPUT_FILE, index=False)
    print(f"  💾 Saved: {OUTPUT_FILE.name} ({len(combined):,} rows total)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KSB1 Silver ETL")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--file", type=Path, default=None, help="Upsert เฉพาะไฟล์นี้ (ไม่ rebuild ทั้งหมด)")
    args = parser.parse_args()
    if args.file:
        upsert_file(args.file)
    else:
        run(year_filter=args.year)
