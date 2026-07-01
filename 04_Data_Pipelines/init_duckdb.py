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
    # Silver views — per-company files, wildcard across all companies
    # New naming: master_gl_1000.parquet, master_gl_2000.parquet, etc.
    "v_gl":         os.path.join(SILVER, "master_gl_*.parquet"),
    "v_sales":      os.path.join(SILVER, "master_sales_*.parquet"),
    "v_production": os.path.join(SILVER, "master_production_*.parquet"),
    "v_ar":         os.path.join(SILVER, "master_ar_*.parquet"),

    # Gold views — aggregated summaries
    "v_gl_summary":         os.path.join(GOLD, "Summary_GL_*.parquet"),
    "gold_revenue_monthly": os.path.join(GOLD, "gold_revenue_monthly.parquet"),
    "gold_gp_by_plant":     os.path.join(GOLD, "gold_gp_by_plant.parquet"),

    # Silver — standalone ETL scripts (not in main orchestrator Silver phase)
    "v_mb51": os.path.join(SILVER, "master_mb51_*.parquet"),
    "v_prd":  os.path.join(SILVER, "master_prd_*.parquet"),
    "v_tb":   os.path.join(SILVER, "master_tb_*.parquet"),

    # Gold — audit parquets (freshness depends on manual gold run or orchestrator --gold-only)
    "gold_leadsheet":     os.path.join(GOLD, "gold_leadsheet.parquet"),
    "gold_cashflow":      os.path.join(GOLD, "gold_cashflow.parquet"),
    "gold_ppe":           os.path.join(GOLD, "gold_ppe.parquet"),
    "gold_elimination":   os.path.join(GOLD, "gold_elimination.parquet"),
    "gold_related_party": os.path.join(GOLD, "gold_related_party.parquet"),
}

# Single-year views removed — use v_gl WHERE Year = YYYY instead
YEAR_VIEWS = {}

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

    # For glob patterns (contains *), use glob to find files
    # For single files, check existence directly
    import glob as glob_lib
    if "*" in parquet_glob:
        matches = glob_lib.glob(parquet_glob)
    else:
        matches = [parquet_glob] if os.path.exists(parquet_glob) else []
    if not matches:
        print(f"  ⏭️  {view_name:<25} ข้ามเพราะไม่พบไฟล์: {os.path.basename(parquet_glob)}")
        return False

    con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{parquet_path}')")
    row_count = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
    print(f"  ✅ {view_name:<25} {row_count:>12,} rows  ← {os.path.basename(parquet_glob)}")
    return True

print("📋 สร้าง Multi-company views:")
for name, path in VIEWS.items():
    if create_view(name, path):
        created += 1
    else:
        skipped += 1

if YEAR_VIEWS:
    print("\n📋 สร้าง Additional views:")
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
