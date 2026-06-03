"""
etl_sales.py — Bronze → Silver: Sales Data ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_sales.py [year]
ตัวอย่าง: python 04_Data_Pipelines/silver_transform/etl_sales.py 2025

รวมไฟล์ Sales รายเดือนจาก Bronze layer → master_sales_YYYY.parquet ใน Silver layer
"""

import pandas as pd
import os
import sys

# ============================================================
# 1. กำหนด paths (relative จาก project root)
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BRONZE_SALES = os.path.join(PROJECT_ROOT, "01_Bronze_Raw", "Sales_Reports")
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")

# ============================================================
# 2. รับ year จาก argument หรือถามผู้ใช้
# ============================================================
if len(sys.argv) > 1:
    years_to_process = [sys.argv[1]]
else:
    # Default: process ทุกปีที่มีโฟลเดอร์ใน Bronze
    available_years = sorted([
        d for d in os.listdir(BRONZE_SALES)
        if os.path.isdir(os.path.join(BRONZE_SALES, d)) and d.isdigit()
    ])
    years_to_process = available_years
    print(f"📅 พบข้อมูลปี: {', '.join(years_to_process)}")

# ============================================================
# 3. Process แต่ละปี
# ============================================================
for year in years_to_process:
    source_folder = os.path.join(BRONZE_SALES, str(year))
    target_file = os.path.join(SILVER, f"master_sales_{year}.parquet")

    if not os.path.isdir(source_folder):
        print(f"\n⚠️  ไม่พบโฟลเดอร์: {source_folder} — ข้าม")
        continue

    print(f"\n{'='*50}")
    print(f"🚀 ประมวลผล Sales ปี {year}")
    print(f"{'='*50}")

    all_dataframes = []
    months = [f"{i:02d}" for i in range(1, 13)]

    for month in months:
        # รองรับ 2 รูปแบบ filename:
        #   sale_YYYY_MM.XLSX  (รูปแบบเก่า 2023-2025)
        #   sale_MM.YYYY.XLSX  (รูปแบบใหม่ 2026+)
        candidates = [
            f"sale_{year}_{month}.XLSX",
            f"sale_{year}_{month}.xlsx",
            f"sale_{month}.{year}.XLSX",
            f"sale_{month}.{year}.xlsx",
        ]
        found = False
        for filename in candidates:
            file_path = os.path.join(source_folder, filename)
            if os.path.exists(file_path):
                print(f"  ⏳ {filename} ...", end=" ")
                try:
                    df = pd.read_excel(file_path, engine="openpyxl")
                    df["Source_File"] = filename
                    df["Year"] = int(year)
                    df["Month"] = int(month)
                    all_dataframes.append(df)
                    print(f"✅ {len(df):,} rows")
                except Exception as e:
                    print(f"❌ Error: {e}")
                found = True
                break
        if not found:
            print(f"  ⏭️  ไม่พบ sale_{year}_{month}.xlsx")

    if not all_dataframes:
        print(f"❌ ไม่พบไฟล์ Sales ปี {year} เลย")
        continue

    # Concat และ clean
    master_df = pd.concat(all_dataframes, ignore_index=True)
    master_df.columns = master_df.columns.str.strip()

    # Clean data types
    for col in master_df.columns:
        if any(kw in col.upper() for kw in ["AMOUNT", "QTY", "QUANTITY", "VALUE", "NET"]):
            if master_df[col].dtype == object:
                master_df[col] = master_df[col].astype(str).str.replace(",", "", regex=False)
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
        elif master_df[col].dtype == object:
            master_df[col] = master_df[col].astype(str)

    os.makedirs(SILVER, exist_ok=True)
    master_df.to_parquet(target_file, engine="pyarrow", index=False)
    print(f"\n💾 บันทึกสำเร็จ: {target_file}")
    print(f"   📊 {len(master_df):,} rows, {len(master_df.columns)} columns")

print(f"\n✨ etl_sales เสร็จสิ้น")
