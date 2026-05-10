"""
etl_ar.py — Bronze → Silver: Accounts Receivable ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_ar.py

รวมไฟล์ AR (AR_2023.XLSX, AR_2024.XLSX, ...) จาก Bronze → master_ar_ALL.parquet ใน Silver
"""

import pandas as pd
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BRONZE_AR = os.path.join(PROJECT_ROOT, "01_Bronze_Raw", "AR_Data")
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
TARGET_FILE = os.path.join(SILVER, "master_ar.parquet")

print(f"\n{'='*50}")
print(f"🚀 ETL: AR Data → Silver Layer")
print(f"{'='*50}")

ar_files = [f for f in os.listdir(BRONZE_AR) if f.lower().endswith(".xlsx")]
if not ar_files:
    print(f"❌ ไม่พบไฟล์ AR ใน: {BRONZE_AR}")
    raise SystemExit(1)

all_dfs = []
for fname in sorted(ar_files):
    fpath = os.path.join(BRONZE_AR, fname)
    print(f"  ⏳ อ่าน {fname} ...", end=" ")
    try:
        df = pd.read_excel(fpath, engine="openpyxl")
        df["Source_File"] = fname
        all_dfs.append(df)
        print(f"✅ {len(df):,} rows")
    except Exception as e:
        print(f"❌ {e}")

if not all_dfs:
    print("❌ ไม่สามารถอ่านไฟล์ได้เลย")
    raise SystemExit(1)

master_df = pd.concat(all_dfs, ignore_index=True)
master_df.columns = master_df.columns.str.strip()

# Clean data types
for col in master_df.columns:
    if any(kw in col.upper() for kw in ["AMOUNT", "AMT", "BALANCE", "VALUE", "NET"]):
        if master_df[col].dtype == object:
            master_df[col] = master_df[col].astype(str).str.replace(",", "", regex=False)
        master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
    elif master_df[col].dtype == object:
        master_df[col] = master_df[col].astype(str)

os.makedirs(SILVER, exist_ok=True)
master_df.to_parquet(TARGET_FILE, engine="pyarrow", index=False)
print(f"\n💾 บันทึกสำเร็จ: {TARGET_FILE}")
print(f"   📊 {len(master_df):,} rows, {len(master_df.columns)} columns")
print(f"\n✨ etl_ar เสร็จสิ้น")
