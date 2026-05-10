"""
etl_gl.py — Bronze → Silver: GL Transactions ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_gl.py

รวมไฟล์ GL (sap_fbl3n.XLSX) จาก Bronze layer → Master_GL_24_25.parquet ใน Silver layer
"""

import pandas as pd
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BRONZE_GL = os.path.join(PROJECT_ROOT, "01_Bronze_Raw", "GL_Transactions")
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
TARGET_FILE = os.path.join(SILVER, "Master_GL_24_25.parquet")

print(f"\n{'='*50}")
print(f"🚀 ETL: GL Transactions → Silver Layer")
print(f"{'='*50}")

# รองรับทั้ง .XLSX และ .xlsx
gl_files = [f for f in os.listdir(BRONZE_GL) if f.lower().endswith(".xlsx")]
if not gl_files:
    print(f"❌ ไม่พบไฟล์ GL ใน: {BRONZE_GL}")
    raise SystemExit(1)

all_dfs = []
for fname in sorted(gl_files):
    fpath = os.path.join(BRONZE_GL, fname)
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
    if any(kw in col.upper() for kw in ["AMOUNT", "AMT", "VALUE", "NET", "DEBIT", "CREDIT"]):
        if master_df[col].dtype == object:
            master_df[col] = master_df[col].astype(str).str.replace(",", "", regex=False)
        master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
    elif master_df[col].dtype == object:
        master_df[col] = master_df[col].astype(str)

os.makedirs(SILVER, exist_ok=True)
master_df.to_parquet(TARGET_FILE, engine="pyarrow", index=False)
print(f"\n💾 บันทึกสำเร็จ: {TARGET_FILE}")
print(f"   📊 {len(master_df):,} rows, {len(master_df.columns)} columns")
print(f"\n✨ etl_gl เสร็จสิ้น")
