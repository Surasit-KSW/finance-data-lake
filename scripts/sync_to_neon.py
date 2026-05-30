"""
sync_to_neon.py — Sync local Silver Parquet files to Neon PostgreSQL

Usage:
    python sync_to_neon.py                    # sync all domains
    python sync_to_neon.py --domain gl        # sync GL only
    python sync_to_neon.py --domain sales
    python sync_to_neon.py --domain production
    python sync_to_neon.py --domain gl_summary

Requires:
    DATABASE_URL env var pointing to Neon PostgreSQL
    e.g. DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require

Run this script locally whenever SAP data is updated (e.g. monthly GL extract).
Raw files NEVER leave your machine — only processed data goes to Neon.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parents[1]
SILVER  = ROOT / "02_Silver_Cleaned"

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL env var not set.")
    print("  export DATABASE_URL='postgresql://user:pass@host/db?sslmode=require'")
    sys.exit(1)


def get_engine():
    return create_engine(DATABASE_URL, connect_args={"connect_timeout": 30})


# ── Sync functions ─────────────────────────────────────────────────────────────

def sync_gl(engine):
    """Master_GL_24_25.parquet → table: v_gl"""
    path = SILVER / "Master_GL_24_25.parquet"
    print(f"[GL] Reading {path.name} ({path.stat().st_size / 1e6:.1f} MB)...")
    t = time.time()
    df = pd.read_parquet(path)
    print(f"[GL] Loaded {len(df):,} rows in {time.time()-t:.1f}s — pushing to Neon...")
    t = time.time()
    df.to_sql("v_gl", engine, if_exists="replace", index=False, chunksize=10_000, method="multi")
    print(f"[GL] Done in {time.time()-t:.1f}s")
    _add_index(engine, "v_gl", ["Year", "Month"])
    _add_index(engine, "v_gl", ['"G/L Account"'])


def sync_gl_summary(engine):
    """v_gl_summary.parquet → table: v_gl_summary"""
    path = SILVER / "v_gl_summary.parquet"
    if not path.exists():
        # Fallback: check Gold layer
        path = ROOT / "03_Gold_DataMarts" / "v_gl_summary.parquet"
    print(f"[GL_SUMMARY] Reading {path.name}...")
    df = pd.read_parquet(path)
    print(f"[GL_SUMMARY] {len(df):,} rows — pushing to Neon...")
    df.to_sql("v_gl_summary", engine, if_exists="replace", index=False, method="multi")
    print(f"[GL_SUMMARY] Done")
    _add_index(engine, "v_gl_summary", ["Year"])


def sync_sales(engine):
    """master_sales_*.parquet (all years) → table: v_sales"""
    files = sorted(SILVER.glob("master_sales_*.parquet"))
    if not files:
        print("[SALES] No master_sales_*.parquet files found — skip")
        return
    dfs = []
    for f in files:
        print(f"[SALES] Reading {f.name}...")
        dfs.append(pd.read_parquet(f))
    df = pd.concat(dfs, ignore_index=True)
    print(f"[SALES] {len(df):,} rows total — pushing to Neon...")
    df.to_sql("v_sales", engine, if_exists="replace", index=False, chunksize=5_000, method="multi")
    print(f"[SALES] Done")
    _add_index(engine, "v_sales", ['"Billing Date"'])


def sync_production(engine):
    """master_production_*.parquet (all years) → table: v_production"""
    files = sorted(SILVER.glob("master_production_*.parquet"))
    if not files:
        print("[PRODUCTION] No master_production_*.parquet files found — skip")
        return
    dfs = []
    for f in files:
        print(f"[PRODUCTION] Reading {f.name}...")
        dfs.append(pd.read_parquet(f))
    df = pd.concat(dfs, ignore_index=True)
    print(f"[PRODUCTION] {len(df):,} rows total — pushing to Neon...")
    df.to_sql("v_production", engine, if_exists="replace", index=False, method="multi")
    print(f"[PRODUCTION] Done")


def _add_index(engine, table: str, cols: list[str]):
    """Create index if not exists — silently skip if already there."""
    col_slug = "_".join(c.strip('"') for c in cols)
    idx_name = f"idx_{table}_{col_slug}"
    col_expr = ", ".join(cols)
    sql = f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ({col_expr})'
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        print(f"  index: {idx_name}")
    except Exception as e:
        print(f"  index {idx_name} skipped: {e}")


# ── Entry point ────────────────────────────────────────────────────────────────

DOMAINS = {
    "gl":         sync_gl,
    "gl_summary": sync_gl_summary,
    "sales":      sync_sales,
    "production": sync_production,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync local Parquet → Neon PostgreSQL")
    parser.add_argument("--domain", choices=[*DOMAINS.keys(), "all"], default="all")
    args = parser.parse_args()

    engine = get_engine()
    print(f"\nConnecting to Neon...\n")

    targets = list(DOMAINS.items()) if args.domain == "all" else [(args.domain, DOMAINS[args.domain])]

    total_start = time.time()
    for name, fn in targets:
        print(f"{'='*50}")
        fn(engine)

    print(f"\n{'='*50}")
    print(f"Sync complete in {time.time()-total_start:.1f}s")
    print(f"Web app will now use live data from Neon.")
