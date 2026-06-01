"""
upload_to_neon.py — Upload Silver/Gold parquet data to Neon PostgreSQL
=======================================================================
สร้าง tables v_gl, v_gl_summary ใน Neon แล้ว upsert ข้อมูลจาก parquet files

รัน: python upload_to_neon.py
     python upload_to_neon.py --domain gl          # GL only
     python upload_to_neon.py --domain gl_summary  # Gold summary only
     python upload_to_neon.py --domain all         # ทั้งหมด (default)

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

BATCH_SIZE = 5000  # rows per INSERT batch


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


def truncate_table(table: str):
    execute_ddl(f'TRUNCATE TABLE "{table}"')
    print(f"   🗑️  Truncated: {table}")


def insert_batch(conn, table: str, columns: list[str], rows: list[tuple]):
    placeholders = ", ".join(["%s"] * len(columns))
    col_names    = ", ".join([f'"{c}"' for c in columns])
    sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=BATCH_SIZE)
    conn.commit()


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
# Column naming rules:
#   - lowercase (unquoted) for valid identifiers: year, month, net_amount, source_file
#     → SQL can use any case — Postgres normalizes unquoted to lowercase → matches
#   - quoted for special-char columns: "G/L Account", "Posting Date", etc.

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


# ─── Upload: v_gl ─────────────────────────────────────────────────────────────

def upload_gl():
    files = sorted(glob.glob(os.path.join(SILVER, "Master_GL_*.parquet")))
    if not files:
        print("❌ ไม่พบ Master_GL_*.parquet ใน Silver layer")
        return

    src = files[-1]
    print(f"\n📂 อ่าน: {os.path.basename(src)}")
    df = pd.read_parquet(src)

    # ── Normalize columns ────────────────────────────────────────────────────
    def clean_str(s):
        if pd.isna(s): return None
        s = str(s)
        return None if s in ("nan", "None", "") else s

    def clean_float_as_str(v):
        """Convert 4111010.0 → '4111010'"""
        if pd.isna(v): return None
        try:
            return str(int(float(v)))
        except Exception:
            return clean_str(v)

    def clean_int(v):
        if pd.isna(v): return None
        try: return int(float(v))
        except Exception: return None

    def clean_date(v):
        if pd.isna(v): return None
        try: return pd.Timestamp(v).date()
        except Exception: return None

    def clean_float(v):
        if pd.isna(v): return None
        try: return float(v)
        except Exception: return None

    print(f"   📊 {len(df):,} rows — normalizing...")

    records = []
    for _, row in df.iterrows():
        records.append((
            clean_float_as_str(row.get("G/L Account")),
            clean_str(row.get("G/L Account: Long Text")),
            clean_float(row.get("Net_Amount")),
            clean_int(row.get("Year")),
            clean_int(row.get("Month")),
            clean_date(row.get("Posting Date")),
            clean_float_as_str(row.get("Document Number")),
            clean_str(row.get("Text")),
            clean_float_as_str(row.get("Cost Center")),
            clean_str(row.get("Cost Center: Long Text")),
            clean_str(row.get("Cost Center: Short Text")),
            clean_str(row.get("Source_File")),
            clean_float_as_str(row.get("Company Code")),
            clean_str(row.get("Document type")),
            clean_str(row.get("Reference")),
            clean_str(row.get("Assignment")),
        ))

    cols = [
        "G/L Account", "G/L Account: Long Text", "net_amount",
        "year", "month", "Posting Date", "Document Number", "Text",
        "Cost Center", "Cost Center: Long Text", "Cost Center: Short Text",
        "source_file", "Company Code", "Document type", "Reference", "Assignment",
    ]

    print("   🏗️  สร้าง/recreate table v_gl...")
    execute_ddl(DDL_V_GL)

    print(f"   ⬆️  Uploading {len(records):,} rows in batches of {BATCH_SIZE}...")
    conn = get_conn()
    try:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i+BATCH_SIZE]
            insert_batch(conn, "v_gl", cols, batch)
            pct = min(100, int((i + len(batch)) / len(records) * 100))
            print(f"      {pct:3d}% ({i + len(batch):,}/{len(records):,})", end="\r")
    finally:
        conn.close()

    print(f"\n   ✅ v_gl uploaded: {len(records):,} rows")


# ─── Upload: v_gl_summary ────────────────────────────────────────────────────

def upload_gl_summary():
    files = sorted(glob.glob(os.path.join(GOLD, "Summary_GL_*.parquet")))
    if not files:
        print("❌ ไม่พบ Summary_GL_*.parquet ใน Gold layer")
        return

    src = files[-1]
    print(f"\n📂 อ่าน: {os.path.basename(src)}")
    df = pd.read_parquet(src)
    print(f"   📊 {len(df):,} rows")

    def clean_int(v):
        if pd.isna(v): return None
        try: return int(float(v))
        except Exception: return None

    def clean_str(s):
        if pd.isna(s): return None
        s = str(s)
        return None if s in ("nan", "None", "") else s

    def clean_float_as_str(v):
        if pd.isna(v): return None
        try: return str(int(float(v)))
        except Exception: return clean_str(v)

    def clean_float(v):
        if pd.isna(v): return None
        try: return float(v)
        except Exception: return None

    records = [
        (
            clean_int(row.get("Year")),
            clean_int(row.get("Month")),
            clean_str(row.get("GL_Group")),
            clean_float_as_str(row.get("G/L Account")),
            clean_float(row.get("Net_Amount")),
            clean_str(row.get("GL_Name")),
        )
        for _, row in df.iterrows()
    ]

    cols = ["year", "month", "gl_group", "G/L Account", "net_amount", "gl_name"]

    print("   🏗️  สร้าง/recreate table v_gl_summary...")
    execute_ddl(DDL_V_GL_SUMMARY)

    print(f"   ⬆️  Uploading {len(records):,} rows...")
    conn = get_conn()
    try:
        insert_batch(conn, "v_gl_summary", cols, records)
    finally:
        conn.close()

    print(f"   ✅ v_gl_summary uploaded: {len(records):,} rows")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload parquet → Neon PostgreSQL")
    parser.add_argument("--domain", choices=["gl", "gl_summary", "all"], default="all")
    args = parser.parse_args()

    print("=" * 55)
    print("  Upload to Neon PostgreSQL")
    print(f"  Target: {DATABASE_URL.split('@')[-1][:50]}")
    print("=" * 55)

    if args.domain in ("gl", "all"):
        upload_gl()

    if args.domain in ("gl_summary", "all"):
        upload_gl_summary()

    print("\n✅ เสร็จสิ้น — ข้อมูลพร้อมใช้งานบน Render/Vercel")


if __name__ == "__main__":
    main()
