"""
init_duckdb.py — Finance Data Lake: DuckDB View Initialization
รัน: python 04_Data_Pipelines/init_duckdb.py
สร้างหรืออัพเดต finance_lake.duckdb ที่ root ของ project
"""

import duckdb
import os
import sys

# UTF-8 output สำหรับ Windows console (cp874)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# 1. กำหนด paths
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

DB_PATH = os.path.join(PROJECT_ROOT, "finance_lake.duckdb")

SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
GOLD = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")

# ============================================================
# 2. ตรวจสอบ Parquet files ที่มีอยู่
# ============================================================
VIEWS = {
    # Silver views — raw cleaned data (multi-year wildcard)
    "v_sales": os.path.join(SILVER, "master_sales_*.parquet"),
    "v_production": os.path.join(SILVER, "master_production_*.parquet"),
    # GL: wildcard รองรับทุกช่วงปี เช่น Master_GL_24_25.parquet, Master_GL_24_26.parquet
    "v_gl": os.path.join(SILVER, "Master_GL_*.parquet"),
    "v_ar": os.path.join(SILVER, "master_ar.parquet"),

    # Gold views — aggregated summaries
    # wildcard รองรับ Summary_GL_24_25.parquet, Summary_GL_24_26.parquet ฯลฯ
    "v_gl_summary": os.path.join(GOLD, "Summary_GL_*.parquet"),
}

# Single-year views for explicit year access
YEAR_VIEWS = {
    "v_sales_2023": os.path.join(SILVER, "master_sales_2023.parquet"),
    "v_sales_2024": os.path.join(SILVER, "master_sales_2024.parquet"),
    "v_sales_2025": os.path.join(SILVER, "master_sales_2025.parquet"),
    "v_sales_2026": os.path.join(SILVER, "master_sales_2026.parquet"),
    "v_production_2023": os.path.join(SILVER, "master_production_2023.parquet"),
    "v_production_2024": os.path.join(SILVER, "master_production_2024.parquet"),
    "v_production_2025": os.path.join(SILVER, "master_production_2025.parquet"),
    "v_production_2026": os.path.join(SILVER, "master_production_2026.parquet"),
}

# ============================================================
# 3. สร้างหรือเปิด DuckDB และสร้าง views
# ============================================================
print(f"\n{'='*55}")
print(f"  Finance Data Lake — DuckDB Initialization")
print(f"{'='*55}")
print(f"\n📂 Project root : {PROJECT_ROOT}")
print(f"💾 Database     : {DB_PATH}\n")

con = duckdb.connect(DB_PATH)

created = 0
skipped = 0

def create_view(view_name: str, parquet_glob: str) -> bool:
    """สร้าง view และ return True ถ้าสำเร็จ"""
    # normalize path separators สำหรับ DuckDB (ต้องใช้ forward slashes)
    parquet_path = parquet_glob.replace("\\", "/")

    # ตรวจสอบว่ามีไฟล์จริงไหม (glob หรือ single file)
    import glob as glob_lib
    matches = glob_lib.glob(parquet_glob)
    if not matches:
        print(f"  ⏭️  {view_name:<25} ข้ามเพราะไม่พบไฟล์: {os.path.basename(parquet_glob)}")
        return False

    con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{parquet_path}')")
    row_count = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
    print(f"  ✅ {view_name:<25} {row_count:>12,} rows  ← {os.path.basename(parquet_glob)}")
    return True

print("📋 สร้าง Multi-year views:")
for name, path in VIEWS.items():
    if create_view(name, path):
        created += 1
    else:
        skipped += 1

print("\n📋 สร้าง Single-year views:")
for name, path in YEAR_VIEWS.items():
    if create_view(name, path):
        created += 1
    else:
        skipped += 1

# ============================================================
# 4. สรุปผล
# ============================================================
print(f"\n{'='*55}")
print(f"  ✅ สร้าง views สำเร็จ : {created}")
print(f"  ⏭️  ข้ามเพราะไม่พบไฟล์: {skipped}")
print(f"{'='*55}")

# แสดงรายการ views ทั้งหมดที่มีใน DB
print("\n📊 Views ที่ใช้งานได้ทั้งหมด:")
views_list = con.execute(
    "SELECT table_name, table_type FROM information_schema.tables "
    "WHERE table_schema = 'main' ORDER BY table_name"
).fetchall()
for row in views_list:
    print(f"   - {row[0]}")

print(f"\n💡 ตัวอย่างการใช้งาน:")
print(f"   import duckdb")
print(f"   con = duckdb.connect(r'{DB_PATH}')")
print(f"   df = con.execute('SELECT * FROM v_sales LIMIT 10').df()")
print(f"\n✨ DuckDB พร้อมใช้งาน: {DB_PATH}\n")

con.close()
