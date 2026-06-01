"""
etl_gl.py — Bronze → Silver: GL Transactions ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_gl.py
     python 04_Data_Pipelines/silver_transform/etl_gl.py 2026

รวมไฟล์ GL รายเดือนจาก Bronze layer → Master_GL_YY_YY.parquet ใน Silver layer

โครงสร้าง Bronze ที่คาดหวัง:
  01_Bronze_Raw/GL_Transactions/
    2024/
      gl_2024_01.XLSX
      gl_2024_02.XLSX
      ...
    2025/
      gl_2025_01.XLSX
      ...
    2026/
      gl_2026_01.XLSX
      ...

Column ที่ต้องมีใน Excel (FBL3N layout):
  - G/L Account (รหัสบัญชี)
  - G/L Account: Long Text (ชื่อบัญชี) — optional
  - Posting Date (วันที่ posting) — ใช้ derive Year/Month
  - Amount in LC หรือ Net Amount (ยอดเงิน)
  - Document Number, Text, Cost Center — optional แต่แนะนำ
"""

import glob
import os
import sys

import pandas as pd

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

BRONZE_GL = os.path.join(PROJECT_ROOT, "01_Bronze_Raw", "GL_Transactions")
SILVER    = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")

# ── Amount column aliases (ลำดับความสำคัญ) ────────────────────────────────
AMT_ALIASES = [
    "Amount in LC",
    "Amount in local currency",
    "Net Amount",
    "Amt.in loc.cur.",
    "Net_Amount",
    "Company Code Currency Value",   # FBL3N layout variant
    "CCode Curr Value",
    "Amount",
]

GL_ACCOUNT_ALIASES = ["G/L Acct", "GL Account", "Account", "Saknr"]


# ============================================================
# 1. หา years ที่ต้อง process
# ============================================================
if len(sys.argv) > 1:
    years_to_process = [sys.argv[1]]
else:
    available_years = sorted([
        d for d in os.listdir(BRONZE_GL)
        if os.path.isdir(os.path.join(BRONZE_GL, d)) and d.isdigit()
    ])
    years_to_process = available_years
    if years_to_process:
        print(f"📅 พบข้อมูลปี: {', '.join(years_to_process)}")
    else:
        print(f"❌ ไม่พบ year subfolders ใน: {BRONZE_GL}")
        print("   สร้างโฟลเดอร์ เช่น GL_Transactions/2024/ แล้ววางไฟล์ gl_2024_01.XLSX")
        raise SystemExit(1)


# ============================================================
# 2. อ่านไฟล์ monthly ทุกปี
# ============================================================
all_dfs = []

for year in years_to_process:
    source_folder = os.path.join(BRONZE_GL, str(year))
    if not os.path.isdir(source_folder):
        print(f"\n⚠️  ไม่พบโฟลเดอร์: {source_folder} — ข้าม")
        continue

    print(f"\n{'='*50}")
    print(f"🚀 ประมวลผล GL ปี {year}")
    print(f"{'='*50}")

    year_dfs = []
    months = [f"{i:02d}" for i in range(1, 13)]

    for month in months:
        found = False
        for ext in [".XLSX", ".xlsx"]:
            fname = f"gl_{year}_{month}{ext}"
            fpath = os.path.join(source_folder, fname)
            if os.path.exists(fpath):
                print(f"  ⏳ {fname} ...", end=" ")
                try:
                    df = pd.read_excel(fpath, engine="openpyxl")
                    df["Source_File"] = fname
                    year_dfs.append(df)
                    print(f"✅ {len(df):,} rows")
                    found = True
                    break
                except Exception as e:
                    print(f"❌ {e}")
                    found = True
                    break
        if not found:
            print(f"  ⏭️  ไม่พบ gl_{year}_{month}.xlsx")

    if not year_dfs:
        print(f"❌ ไม่พบไฟล์ GL ปี {year} เลย")
    else:
        all_dfs.extend(year_dfs)
        print(f"  ✅ รวม {sum(len(d) for d in year_dfs):,} rows จากปี {year}")

if not all_dfs:
    print("\n❌ ไม่มีข้อมูลเลย — ไม่สร้างไฟล์")
    raise SystemExit(1)

master_df = pd.concat(all_dfs, ignore_index=True)
master_df.columns = master_df.columns.str.strip()


# ============================================================
# 3. Column normalization
# ============================================================

# 3a. Derive Year / Month จาก Posting Date
date_col = next((c for c in master_df.columns if "POSTING DATE" in c.upper()), None)
if "Year" not in master_df.columns and date_col:
    master_df["Year"]  = pd.to_datetime(master_df[date_col], errors="coerce").dt.year
    master_df["Month"] = pd.to_datetime(master_df[date_col], errors="coerce").dt.month
    print(f"\n   ℹ️  Derived Year/Month from '{date_col}'")
elif "Year" not in master_df.columns:
    # ถ้าไม่มี Posting Date เลย — derive จาก filename
    print("\n   ⚠️  ไม่พบ Posting Date — Year/Month จะว่างเปล่า")

# 3b. Map Net_Amount
if "Net_Amount" not in master_df.columns:
    for alias in AMT_ALIASES:
        if alias in master_df.columns:
            master_df["Net_Amount"] = pd.to_numeric(
                master_df[alias].astype(str).str.replace(",", "", regex=False),
                errors="coerce"
            ).fillna(0)
            print(f"   ℹ️  Mapped '{alias}' → Net_Amount")
            break

# 3c. Warn / rename G/L Account
if "G/L Account" not in master_df.columns:
    for alias in GL_ACCOUNT_ALIASES:
        if alias in master_df.columns:
            master_df.rename(columns={alias: "G/L Account"}, inplace=True)
            print(f"   ℹ️  Renamed '{alias}' → G/L Account")
            break
    else:
        print("\n   ⚠️  WARNING: 'G/L Account' column not found.")
        print("      กรุณาตรวจสอบ SAP FBL3N layout ให้รวม G/L Account field")

# 3d. Clean numeric columns
for col in master_df.columns:
    if any(kw in col.upper() for kw in ["AMOUNT", "AMT", "VALUE"]):
        if master_df[col].dtype == object:
            master_df[col] = pd.to_numeric(
                master_df[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce"
            ).fillna(0)


# ============================================================
# 4. ตั้งชื่อ output ตามช่วงปีจริงในข้อมูล
# ============================================================
os.makedirs(SILVER, exist_ok=True)

year_col = "Year" if "Year" in master_df.columns else None
if year_col:
    years_found = sorted(master_df[year_col].dropna().astype(str).str[:4].unique())
    years_found = [y for y in years_found if y.isdigit() and 2000 < int(y) < 2100]
else:
    years_found = []

if len(years_found) >= 2:
    year_suffix = f"{years_found[0][-2:]}_{years_found[-1][-2:]}"
elif len(years_found) == 1:
    y = years_found[0][-2:]
    year_suffix = f"{y}_{y}"
else:
    year_suffix = "_".join(str(y)[-2:] for y in years_to_process) or "all"

TARGET_FILE = os.path.join(SILVER, f"Master_GL_{year_suffix}.parquet")

# ลบไฟล์เก่า
for old in glob.glob(os.path.join(SILVER, "Master_GL_*.parquet")):
    if os.path.normpath(old) != os.path.normpath(TARGET_FILE):
        os.remove(old)
        print(f"🗑️  ลบไฟล์เก่า: {os.path.basename(old)}")

master_df.to_parquet(TARGET_FILE, engine="pyarrow", index=False)
print(f"\n💾 บันทึกสำเร็จ: {os.path.basename(TARGET_FILE)}  (ปี: {years_found})")
print(f"   📊 {len(master_df):,} rows, {len(master_df.columns)} columns")
print(f"\n✨ etl_gl เสร็จสิ้น")
