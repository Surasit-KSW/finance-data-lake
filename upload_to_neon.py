"""
upload_to_neon.py — Upload Silver/Gold parquet data to Neon PostgreSQL
=======================================================================
สร้าง tables v_gl, v_gl_summary ใน Neon แล้ว upsert ข้อมูลจาก parquet files

Mode การทำงาน:
  Full rebuild (default):   DROP TABLE → CREATE → INSERT ทั้งหมด
  Upsert month (--month):   DELETE WHERE month+year → INSERT เฉพาะเดือนนั้น

รัน:
  python upload_to_neon.py                              # full rebuild ทุก domain
  python upload_to_neon.py --domain gl                 # full rebuild GL only
  python upload_to_neon.py --domain gl --month 6 --year 2026   # upsert เดือน 6
  python upload_to_neon.py --domain all --month 6 --year 2026  # upsert ทุก domain

ต้องการ DATABASE_URL ใน .env (Neon connection string)
"""
import argparse
import glob
import os
import sys

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set — ใส่ใน .env ก่อน")
    sys.exit(1)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
GOLD   = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")

BATCH_SIZE = 5000


# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL, connect_timeout=30)


def execute_ddl(sql: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def table_exists(table: str) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                (table,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def delete_month(conn, table: str, year_col: str, month_col: str, year: int, month: int):
    """ลบ rows ของเดือนนั้นออกก่อน insert ใหม่"""
    sql = f'DELETE FROM "{table}" WHERE "{year_col}" = %s AND "{month_col}" = %s'
    with conn.cursor() as cur:
        cur.execute(sql, (year, month))
        deleted = cur.rowcount
    conn.commit()
    if deleted:
        print(f"   🗑️  ลบ {deleted:,} rows เดิม ({table} month={month} year={year})")


def insert_batch(conn, table: str, columns: list[str], rows: list[tuple]):
    placeholders = ", ".join(["%s"] * len(columns))
    col_names    = ", ".join([f'"{c}"' for c in columns])
    sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=BATCH_SIZE)
    conn.commit()


def upload_rows(conn, table: str, cols: list[str], records: list[tuple], label: str = ""):
    total = len(records)
    tag   = f" [{label}]" if label else ""
    print(f"   ⬆️  Uploading {total:,} rows{tag}...")
    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        insert_batch(conn, table, cols, batch)
        pct = min(100, int((i + len(batch)) / total * 100))
        print(f"      {pct:3d}% ({i + len(batch):,}/{total:,})", end="\r")
    print()


# ─── Schema ───────────────────────────────────────────────────────────────────

DDL_V_GL = """
DROP TABLE IF EXISTS v_gl;
CREATE TABLE v_gl (
    "G/L Account"              TEXT,
    "G/L Account: Long Text"   TEXT,
    net_amount                 DOUBLE PRECISION,
    year                       INTEGER,
    month                      INTEGER,
    "Posting Date"             DATE,
    "Document Number"          TEXT,
    "Text"                     TEXT,
    "Cost Center"              TEXT,
    "Cost Center: Long Text"   TEXT,
    "Cost Center: Short Text"  TEXT,
    source_file                TEXT,
    "Company Code"             TEXT,
    "Document type"            TEXT,
    "Reference"                TEXT,
    "Assignment"               TEXT
);
"""

DDL_V_GL_SUMMARY = """
DROP TABLE IF EXISTS v_gl_summary;
CREATE TABLE v_gl_summary (
    year         INTEGER,
    month        INTEGER,
    gl_group     TEXT,
    "G/L Account" TEXT,
    net_amount   DOUBLE PRECISION,
    gl_name      TEXT
);
"""

DDL_V_PRODUCTION = """
DROP TABLE IF EXISTS v_production;
CREATE TABLE v_production (
    "Material"         TEXT,
    "Description (EN)" TEXT,
    "Plant"            TEXT,
    "Year"             INTEGER,
    "Month"            INTEGER,
    "Actual GR QTY"    DOUBLE PRECISION,
    "Actual GR Amount" DOUBLE PRECISION,
    "Source_File"      TEXT
);
"""


# ─── Row builders ─────────────────────────────────────────────────────────────

def _clean_str(s):
    if pd.isna(s): return None
    s = str(s)
    return None if s in ("nan", "None", "") else s

def _clean_float_as_str(v):
    if pd.isna(v): return None
    try: return str(int(float(v)))
    except Exception: return _clean_str(v)

def _clean_int(v):
    if pd.isna(v): return None
    try: return int(float(v))
    except Exception: return None

def _clean_date(v):
    if pd.isna(v): return None
    try: return pd.Timestamp(v).date()
    except Exception: return None

def _clean_float(v):
    if pd.isna(v): return None
    try: return float(v)
    except Exception: return None


def _build_gl_records(df: pd.DataFrame) -> tuple[list, list[str]]:
    cols = [
        "G/L Account", "G/L Account: Long Text", "net_amount",
        "year", "month", "Posting Date", "Document Number", "Text",
        "Cost Center", "Cost Center: Long Text", "Cost Center: Short Text",
        "source_file", "Company Code", "Document type", "Reference", "Assignment",
    ]
    records = [
        (
            _clean_float_as_str(row.get("G/L Account")),
            _clean_str(row.get("G/L Account: Long Text")),
            _clean_float(row.get("Net_Amount")),
            _clean_int(row.get("Year")),
            _clean_int(row.get("Month")),
            _clean_date(row.get("Posting Date")),
            _clean_float_as_str(row.get("Document Number")),
            _clean_str(row.get("Text")),
            _clean_float_as_str(row.get("Cost Center")),
            _clean_str(row.get("Cost Center: Long Text")),
            _clean_str(row.get("Cost Center: Short Text")),
            _clean_str(row.get("Source_File")),
            _clean_float_as_str(row.get("Company Code")),
            _clean_str(row.get("Document type")),
            _clean_str(row.get("Reference")),
            _clean_str(row.get("Assignment")),
        )
        for _, row in df.iterrows()
    ]
    return records, cols


def _build_gl_summary_records(df: pd.DataFrame) -> tuple[list, list[str]]:
    cols = ["year", "month", "gl_group", "G/L Account", "net_amount", "gl_name"]
    records = [
        (
            _clean_int(row.get("Year")),
            _clean_int(row.get("Month")),
            _clean_str(row.get("GL_Group")),
            _clean_float_as_str(row.get("G/L Account")),
            _clean_float(row.get("Net_Amount")),
            _clean_str(row.get("GL_Name")),
        )
        for _, row in df.iterrows()
    ]
    return records, cols


def _build_production_records(df: pd.DataFrame) -> tuple[list, list[str]]:
    cols = [
        "Material", "Description (EN)", "Plant", "Year", "Month",
        "Actual GR QTY", "Actual GR Amount", "Source_File",
    ]
    records = [
        (
            _clean_str(row.get("Material")),
            _clean_str(row.get("Description (EN)")),
            _clean_str(row.get("Plant")),
            _clean_int(row.get("Year")),
            _clean_int(row.get("Month")),
            _clean_float(row.get("Actual GR QTY")),
            _clean_float(row.get("Actual GR Amount")),
            _clean_str(row.get("Source_File")),
        )
        for _, row in df.iterrows()
    ]
    return records, cols


# ─── Upload: v_gl ─────────────────────────────────────────────────────────────

def upload_gl(month: int = None, year: int = None):
    files = sorted(glob.glob(os.path.join(SILVER, "master_gl_*.parquet")))
    if not files:
        # fallback legacy name
        files = sorted(glob.glob(os.path.join(SILVER, "Master_GL_*.parquet")))
    if not files:
        print("❌ ไม่พบ master_gl_*.parquet ใน Silver layer")
        return

    src = files[-1]
    print(f"\n📂 อ่าน: {os.path.basename(src)}")
    df = pd.read_parquet(src)

    if month and year:
        # Upsert mode
        m_col = pd.to_numeric(df["Month"], errors="coerce").fillna(0).astype(int)
        y_col = pd.to_numeric(df["Year"],  errors="coerce").fillna(0).astype(int)
        df = df[(m_col == month) & (y_col == year)]
        print(f"   📊 {len(df):,} rows (month={month} year={year})")
        if df.empty:
            print("   ⚠️  ไม่มีข้อมูลสำหรับเดือนนี้")
            return
        records, cols = _build_gl_records(df)
        conn = get_conn()
        try:
            if table_exists("v_gl"):
                delete_month(conn, "v_gl", "year", "month", year, month)
            else:
                print("   🏗️  สร้าง table v_gl ใหม่ (ยังไม่มี)...")
                execute_ddl(DDL_V_GL)
            upload_rows(conn, "v_gl", cols, records, label=f"month={month}/{year}")
        finally:
            conn.close()
    else:
        # Full rebuild
        print(f"   📊 {len(df):,} rows — full rebuild")
        records, cols = _build_gl_records(df)
        print("   🏗️  DROP + CREATE table v_gl...")
        execute_ddl(DDL_V_GL)
        conn = get_conn()
        try:
            upload_rows(conn, "v_gl", cols, records)
        finally:
            conn.close()

    print(f"   ✅ v_gl: {len(records):,} rows {'upserted' if month else 'uploaded'}")


# ─── Upload: v_gl_summary ─────────────────────────────────────────────────────

def upload_gl_summary(month: int = None, year: int = None):
    files = sorted(glob.glob(os.path.join(GOLD, "Summary_GL_*.parquet")))
    if not files:
        print("❌ ไม่พบ Summary_GL_*.parquet ใน Gold layer")
        return

    src = files[-1]
    print(f"\n📂 อ่าน: {os.path.basename(src)}")
    df = pd.read_parquet(src)

    if month and year:
        m_col = pd.to_numeric(df["Month"], errors="coerce").fillna(0).astype(int)
        y_col = pd.to_numeric(df["Year"],  errors="coerce").fillna(0).astype(int)
        df = df[(m_col == month) & (y_col == year)]
        print(f"   📊 {len(df):,} rows (month={month} year={year})")
        if df.empty:
            print("   ⚠️  ไม่มีข้อมูลสำหรับเดือนนี้")
            return
        records, cols = _build_gl_summary_records(df)
        conn = get_conn()
        try:
            if table_exists("v_gl_summary"):
                delete_month(conn, "v_gl_summary", "year", "month", year, month)
            else:
                execute_ddl(DDL_V_GL_SUMMARY)
            upload_rows(conn, "v_gl_summary", cols, records, label=f"month={month}/{year}")
        finally:
            conn.close()
    else:
        print(f"   📊 {len(df):,} rows — full rebuild")
        records, cols = _build_gl_summary_records(df)
        print("   🏗️  DROP + CREATE table v_gl_summary...")
        execute_ddl(DDL_V_GL_SUMMARY)
        conn = get_conn()
        try:
            upload_rows(conn, "v_gl_summary", cols, records)
        finally:
            conn.close()

    print(f"   ✅ v_gl_summary: {len(records):,} rows {'upserted' if month else 'uploaded'}")


# ─── Upload: v_production ─────────────────────────────────────────────────────

def upload_production(month: int = None, year: int = None):
    files = sorted(glob.glob(os.path.join(SILVER, "master_production_*.parquet")))
    if not files:
        print("❌ ไม่พบ master_production_*.parquet ใน Silver layer")
        return

    SLIM_COLS = [
        "Material", "Description (EN)", "Plant", "Year", "Month",
        "Actual GR QTY", "Actual GR Amount", "Source_File",
    ]

    all_dfs = []
    for f in files:
        _df = pd.read_parquet(f)
        avail = [c for c in SLIM_COLS if c in _df.columns]
        all_dfs.append(_df[avail])

    df = pd.concat(all_dfs, ignore_index=True)

    if month and year:
        m_col = pd.to_numeric(df["Month"], errors="coerce").fillna(0).astype(int)
        y_col = pd.to_numeric(df["Year"],  errors="coerce").fillna(0).astype(int)
        df = df[(m_col == month) & (y_col == year)]
        print(f"\n   📊 {len(df):,} rows (month={month} year={year})")
        if df.empty:
            print("   ⚠️  ไม่มีข้อมูลสำหรับเดือนนี้")
            return
        records, cols = _build_production_records(df)
        conn = get_conn()
        try:
            if table_exists("v_production"):
                delete_month(conn, "v_production", "Year", "Month", year, month)
            else:
                execute_ddl(DDL_V_PRODUCTION)
            upload_rows(conn, "v_production", cols, records, label=f"month={month}/{year}")
        finally:
            conn.close()
    else:
        print(f"\n   📊 {len(df):,} rows — full rebuild")
        records, cols = _build_production_records(df)
        print("   🏗️  DROP + CREATE table v_production...")
        execute_ddl(DDL_V_PRODUCTION)
        conn = get_conn()
        try:
            upload_rows(conn, "v_production", cols, records)
        finally:
            conn.close()

    print(f"   ✅ v_production: {len(records):,} rows {'upserted' if month else 'uploaded'}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload parquet → Neon PostgreSQL")
    parser.add_argument("--domain", choices=["gl", "gl_summary", "production", "all"], default="all")
    parser.add_argument("--month", type=int, default=None, help="Upsert เฉพาะเดือนนี้ (1-12)")
    parser.add_argument("--year",  type=int, default=None, help="ปี เช่น 2026 (ใช้คู่กับ --month)")
    args = parser.parse_args()

    if args.month and not args.year:
        print("❌ ต้องระบุ --year ด้วยเมื่อใช้ --month")
        sys.exit(1)

    mode = f"upsert month={args.month}/{args.year}" if args.month else "full rebuild"

    print("=" * 55)
    print("  Upload to Neon PostgreSQL")
    print(f"  Target : {DATABASE_URL.split('@')[-1][:50]}")
    print(f"  Mode   : {mode}")
    print(f"  Domain : {args.domain}")
    print("=" * 55)

    if args.domain in ("gl", "all"):
        upload_gl(month=args.month, year=args.year)

    if args.domain in ("gl_summary", "all"):
        upload_gl_summary(month=args.month, year=args.year)

    if args.domain in ("production", "all"):
        upload_production(month=args.month, year=args.year)

    print("\n✅ เสร็จสิ้น — ข้อมูลพร้อมใช้งานบน Render/Vercel")


if __name__ == "__main__":
    main()
