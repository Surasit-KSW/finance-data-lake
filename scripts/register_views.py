"""
scripts/register_views.py
=========================
Register additional parquet files as DuckDB views in finance_lake.duckdb.

Run once (or re-run anytime to refresh view definitions):
    python scripts/register_views.py

Views registered:
  v_mb51      → 02_Silver_Cleaned/master_mb51_*.parquet  (all years)
  gold_ppe    → 03_Gold_DataMarts/gold_ppe.parquet
  gold_elimination → 03_Gold_DataMarts/gold_elimination.parquet
"""
import os
import sys
import duckdb
from pathlib import Path

# ── Resolve paths ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH   = REPO_ROOT / "finance_lake.duckdb"
SILVER    = REPO_ROOT / "02_Silver_Cleaned"
GOLD      = REPO_ROOT / "03_Gold_DataMarts"

if not DB_PATH.exists():
    print(f"ERROR: DuckDB not found at {DB_PATH}")
    sys.exit(1)

# Forward-slash paths for DuckDB (works on Windows too)
def dpath(p: Path) -> str:
    return p.as_posix()


VIEWS: list[tuple[str, str]] = [
    # (view_name, parquet_glob)  — ใช้ wildcard เพื่อรวมทุกปี
    ("v_mb51",           dpath(SILVER / "master_mb51_*.parquet")),
    ("gold_ppe",         dpath(GOLD   / "gold_ppe.parquet")),
    ("gold_elimination", dpath(GOLD   / "gold_elimination.parquet")),
]

# ── Register ──────────────────────────────────────────────────────────────────
con = duckdb.connect(str(DB_PATH), read_only=False)
try:
    for view_name, parquet_path in VIEWS:
        # glob pattern: check ถ้าไม่มี * ให้เช็ค file exists ก่อน
        if "*" not in parquet_path and not Path(parquet_path).exists():
            print(f"  SKIP {view_name} — file not found: {parquet_path}")
            continue

        sql = f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{parquet_path}')"
        con.execute(sql)
        cnt = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
        print(f"  OK   {view_name} = {cnt:,} rows")

    con.commit()
    print("\nDone. Views registered in", DB_PATH)
finally:
    con.close()
