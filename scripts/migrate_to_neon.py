"""
scripts/migrate_to_neon.py
===========================
Migrate Finance Data Lake Gold layer (processed/aggregated data) to Neon PostgreSQL.

Architecture:
  Local: SAP → Bronze → Silver → Gold (processed) ──► Neon PostgreSQL ──► Vercel API
  Raw data never leaves local machine. Only Gold aggregates go to cloud.

Run after any Gold rebuild:
    python scripts/migrate_to_neon.py

Prerequisites:
    DATABASE_URL or DATABASE_URL_UNPOOLED in .env
"""

import sys
import os
import math
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except ImportError:
    pass

# Prefer unpooled connection — no timeout issues for bulk inserts
MIGRATION_URL = (
    os.environ.get("DATABASE_URL_UNPOOLED")
    or os.environ.get("DATABASE_URL")
    or ""
)
if not MIGRATION_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

GOLD = ROOT / "03_Gold_DataMarts"


# ── Pandas dtype → PostgreSQL type ───────────────────────────────────────────

def pg_type(dtype) -> str:
    s = str(dtype)
    if "int" in s:    return "BIGINT"
    if "float" in s:  return "DOUBLE PRECISION"
    if "bool" in s:   return "BOOLEAN"
    if "datetime" in s or "timestamp" in s: return "TIMESTAMP"
    if "date" in s:   return "DATE"
    return "TEXT"


# ── Clean NaT / NaN / inf before insert ──────────────────────────────────────

def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    try:
        if pd.isnull(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ── Create table from DataFrame schema, then load ────────────────────────────

def load_gold_table(conn, table_name: str, df: pd.DataFrame, source: str):
    """Drop-and-recreate table from Gold parquet, then bulk-insert."""
    col_defs = ", ".join(
        f'"{col}" {pg_type(df[col].dtype)}' for col in df.columns
    )
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        cur.execute(f'CREATE TABLE "{table_name}" (id SERIAL PRIMARY KEY, {col_defs})')
    conn.commit()

    col_names = ", ".join(f'"{c}"' for c in df.columns)
    rows = [tuple(clean(v) for v in r) for r in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        execute_values(
            cur,
            f'INSERT INTO "{table_name}" ({col_names}) VALUES %s',
            rows,
            page_size=1000,
        )
    conn.commit()

    # Update meta
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO _lake_meta (table_name, row_count, loaded_at, source_file)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (table_name) DO UPDATE
              SET row_count   = EXCLUDED.row_count,
                  loaded_at   = EXCLUDED.loaded_at,
                  source_file = EXCLUDED.source_file
            """,
            (table_name, len(df), datetime.now(), source),
        )
    conn.commit()
    print(f"  [{table_name:<30}] {len(df):>6,} rows  <- {source}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Finance Data Lake — Gold Layer → Neon PostgreSQL")
    print("=" * 60)
    host = MIGRATION_URL.split("@")[-1] if "@" in MIGRATION_URL else MIGRATION_URL
    conn_type = "unpooled" if "DATABASE_URL_UNPOOLED" in os.environ and os.environ["DATABASE_URL_UNPOOLED"] else "pooled"
    print(f"\n  Target : {host} ({conn_type})")
    print(f"  Source : {GOLD}\n")

    conn = psycopg2.connect(
        MIGRATION_URL,
        connect_timeout=60,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    print("  Connected to Neon PostgreSQL.\n")

    # Ensure _lake_meta exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _lake_meta (
                table_name  VARCHAR(50) PRIMARY KEY,
                row_count   INTEGER,
                loaded_at   TIMESTAMP DEFAULT NOW(),
                source_file TEXT
            )
        """)
    conn.commit()

    # Load every Gold parquet as its own table (table name = filename without .parquet)
    gold_files = sorted(GOLD.glob("*.parquet"))
    if not gold_files:
        print("  No Gold parquet files found in 03_Gold_DataMarts/")
        sys.exit(1)

    print("Loading Gold tables:")
    for f in gold_files:
        table_name = f.stem.lower()   # e.g. gold_cashflow, summary_gl_24_25
        df = pd.read_parquet(f)
        load_gold_table(conn, table_name, df, f.name)

    # Summary
    with conn.cursor() as cur:
        cur.execute("SELECT table_name, row_count, loaded_at FROM _lake_meta ORDER BY table_name")
        meta = cur.fetchall()

    print("\n" + "=" * 60)
    print("  Migration complete!")
    print("=" * 60)
    total_rows = 0
    for table, count, ts in meta:
        print(f"  {table:<32} {count:>8,} rows  ({ts:%Y-%m-%d %H:%M})")
        total_rows += (count or 0)
    print(f"\n  Total: {total_rows:,} rows across {len(meta)} tables")
    print(f"  Raw data stayed local — only processed Gold layer is in Neon.\n")

    conn.close()


if __name__ == "__main__":
    main()
