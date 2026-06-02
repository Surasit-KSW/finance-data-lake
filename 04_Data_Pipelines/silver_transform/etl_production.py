"""
etl_production.py — Bronze → Silver: Production Data ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_production.py [year]
ตัวอย่าง: python 04_Data_Pipelines/silver_transform/etl_production.py 2025

รวมไฟล์ Production รายเดือนจาก Bronze layer → master_production_YYYY.parquet ใน Silver layer
รูปแบบไฟล์: PLANT_YYYY_MM.XLSX เช่น 1100_2025_01.XLSX
"""

import pandas as pd
import os
import sys

# ============================================================
# 1. กำหนด paths (relative จาก project root)
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BRONZE_PROD = os.path.join(PROJECT_ROOT, "01_Bronze_Raw", "Production")
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")

# ============================================================
# 2. รับ year จาก argument หรือ process ทุกปีที่มีโฟลเดอร์
# ============================================================
if len(sys.argv) > 1:
    years_to_process = [sys.argv[1]]
else:
    available_years = sorted([
        d for d in os.listdir(BRONZE_PROD)
        if os.path.isdir(os.path.join(BRONZE_PROD, d)) and d.isdigit()
    ])
    years_to_process = available_years
    print(f"📅 พบข้อมูลปี: {', '.join(years_to_process)}")

# ============================================================
# 3. Process แต่ละปี
# ============================================================
for year in years_to_process:
    source_folder = os.path.join(BRONZE_PROD, str(year))
    target_file = os.path.join(SILVER, f"master_production_{year}.parquet")

    if not os.path.isdir(source_folder):
        print(f"\n⚠️  ไม่พบโฟลเดอร์: {source_folder} — ข้าม")
        continue

    print(f"\n{'='*50}")
    print(f"🚀 ประมวลผล Production ปี {year}")
    print(f"{'='*50}")

    # Discover all XLSX files and parse plant/month from filename
    # Supports two naming conventions:
    #   Old: PLANT_YEAR_MONTH.XLSX   e.g. 1300_2025_07.XLSX
    #   New: PLANT.MONTH.YEAR.XLSX   e.g. 1300.01.2026.XLSX
    all_filenames = os.listdir(source_folder)
    all_dataframes = []
    total_files_found = 0
    plants_found = set()

    import re
    for filename in sorted(all_filenames):
        if not filename.upper().endswith(".XLSX"):
            continue

        plant = month_num = None

        # Pattern 1: PLANT_YEAR_MONTH.XLSX  (e.g. 1300_2025_07.XLSX)
        m = re.match(r'^(\d{4})_(\d{4})_(\d{2})\.xlsx$', filename, re.IGNORECASE)
        if m:
            plant, yr_str, month_str = m.group(1), m.group(2), m.group(3)
            if yr_str == str(year):
                month_num = int(month_str)

        # Pattern 2: PLANT.MONTH.YEAR.XLSX  (e.g. 1300.01.2026.XLSX)
        if plant is None:
            m = re.match(r'^(\d{4})\.(\d{2})\.(\d{4})\.xlsx$', filename, re.IGNORECASE)
            if m:
                plant, month_str, yr_str = m.group(1), m.group(2), m.group(3)
                if yr_str == str(year):
                    month_num = int(month_str)

        if plant is None or month_num is None:
            continue  # ไม่ตรง pattern ใดเลย

        plants_found.add(plant)
        file_path = os.path.join(source_folder, filename)
        print(f"  ⏳ {filename} ...", end=" ")
        try:
            df = pd.read_excel(file_path, engine="openpyxl")
            df["Source_File"] = filename
            df["Plant"] = plant
            df["Year"] = int(year)
            df["Month"] = month_num
            all_dataframes.append(df)
            total_files_found += 1
            print(f"✅ {len(df):,} rows")
        except Exception as e:
            print(f"❌ Error: {e}")

    if plants_found:
        print(f"  🏭 พบ Plants: {', '.join(sorted(plants_found))}")

    if not all_dataframes:
        print(f"❌ ไม่พบไฟล์ Production ปี {year} เลย")
        continue

    # Concat และ clean
    master_df = pd.concat(all_dataframes, ignore_index=True)
    master_df.columns = master_df.columns.str.strip()

    # Clean data types
    for col in master_df.columns:
        if any(kw in col.upper() for kw in ["AMOUNT", "QTY", "QUANTITY", "COST", "KG"]):
            if master_df[col].dtype == object:
                master_df[col] = master_df[col].astype(str).str.replace(",", "", regex=False)
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
        elif master_df[col].dtype == object:
            master_df[col] = master_df[col].astype(str)

    os.makedirs(SILVER, exist_ok=True)
    master_df.to_parquet(target_file, engine="pyarrow", index=False)
    print(f"\n💾 บันทึกสำเร็จ: {target_file}")
    print(f"   📊 {len(master_df):,} rows จาก {total_files_found} ไฟล์, {len(master_df.columns)} columns")

print(f"\n✨ etl_production เสร็จสิ้น")
