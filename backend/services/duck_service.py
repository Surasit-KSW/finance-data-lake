"""
services/duck_service.py — Reusable DuckDB query helper
ทุก router ใช้ผ่าน helper นี้ (ไม่ต้องจัดการ connection เอง)
"""
import pandas as pd
from typing import Any
from backend.core.database import get_duck


def query_df(sql: str, params: list | None = None) -> pd.DataFrame:
    """Execute SQL and return DataFrame. Raises on error."""
    con = get_duck()
    try:
        if params:
            return con.execute(sql, params).df()
        return con.execute(sql).df()
    finally:
        con.close()


def query_one(sql: str, params: list | None = None) -> tuple | None:
    """Execute SQL and return first row as tuple."""
    con = get_duck()
    try:
        if params:
            return con.execute(sql, params).fetchone()
        return con.execute(sql).fetchone()
    finally:
        con.close()


def query_scalar(sql: str, params: list | None = None) -> Any:
    """Execute SQL and return single scalar value."""
    row = query_one(sql, params)
    return row[0] if row else None


def get_view_counts() -> dict[str, int]:
    """Return row count for every view in finance_lake.duckdb."""
    con = get_duck()
    try:
        views = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        counts = {}
        for (name,) in views:
            cnt = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            counts[name] = cnt
        return counts
    finally:
        con.close()
