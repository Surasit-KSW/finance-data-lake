"""
services/db_service.py — Unified Database Query Layer
======================================================
Routes queries to DuckDB (local dev) or PostgreSQL (Vercel/cloud)
based on the DATABASE_URL environment variable.

Usage (in routers — replaces duck_service imports):
    from backend.services.db_service import query_df, query_one, query_scalar

DuckDB SQL is mostly PostgreSQL-compatible. Key rules for cross-DB SQL:
  - Use EXTRACT(YEAR FROM col) NOT strftime('%Y', col)
  - Use EXTRACT(MONTH FROM col) NOT strftime('%m', col)
  - Params: always use ? (this module converts to %s for psycopg2)
  - ILIKE works in both DuckDB and PostgreSQL
  - Window functions work in both
"""
import pandas as pd
from typing import Any
from backend.core.config import settings


# ── Public API ───────────────────────────────────────────────────────────────

def query_df(sql: str, params: list | None = None) -> pd.DataFrame:
    """Execute SQL, return DataFrame. Works on DuckDB (local) and PostgreSQL (cloud)."""
    if settings.use_postgres:
        return _pg_query_df(sql, params)
    from backend.services.duck_service import query_df as _duck
    return _duck(sql, params)


def query_one(sql: str, params: list | None = None) -> tuple | None:
    """Execute SQL, return first row as tuple."""
    if settings.use_postgres:
        return _pg_query_one(sql, params)
    from backend.services.duck_service import query_one as _duck
    return _duck(sql, params)


def query_scalar(sql: str, params: list | None = None) -> Any:
    """Execute SQL, return single scalar value."""
    row = query_one(sql, params)
    return row[0] if row else None


def execute(sql: str, params: list | None = None) -> None:
    """Execute a write statement (INSERT/UPDATE/DELETE). PostgreSQL only."""
    if not settings.use_postgres:
        raise RuntimeError("execute() is only available with DATABASE_URL (PostgreSQL)")
    _pg_execute(sql, params)


# ── PostgreSQL Implementation ─────────────────────────────────────────────────

def _get_pg_conn():
    """Open psycopg2 connection using DATABASE_URL."""
    try:
        import psycopg2
    except ImportError:
        raise ImportError("Install psycopg2: pip install psycopg2-binary")
    return psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)


def _normalize_sql(sql: str) -> str:
    """Convert DuckDB-style ? params to PostgreSQL %s params.
    Also escapes literal % signs (e.g. LIKE '5%') as %% so psycopg2
    doesn't interpret them as format specifiers.
    """
    sql = sql.replace("%", "%%")   # escape LIKE wildcards first
    sql = sql.replace("?", "%s")   # then convert param placeholders
    return sql


def _pg_query_df(sql: str, params: list | None = None) -> pd.DataFrame:
    import psycopg2.extras
    pg_sql = _normalize_sql(sql)
    conn = _get_pg_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(pg_sql, params or [])
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


def _pg_query_one(sql: str, params: list | None = None) -> tuple | None:
    pg_sql = _normalize_sql(sql)
    conn = _get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(pg_sql, params or [])
            return cur.fetchone()
    finally:
        conn.close()


def _pg_execute(sql: str, params: list | None = None) -> None:
    pg_sql = _normalize_sql(sql)
    conn = _get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(pg_sql, params or [])
        conn.commit()
    finally:
        conn.close()


# ── Health check helper ───────────────────────────────────────────────────────

def db_info() -> dict:
    """Return DB backend info for health endpoint."""
    if settings.use_postgres:
        try:
            row = query_one("SELECT version()")
            return {
                "backend": "postgresql",
                "version": str(row[0])[:50] if row else "unknown",
                "url":     settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "neon",
            }
        except Exception as e:
            return {"backend": "postgresql", "error": str(e)}
    else:
        return {
            "backend": "duckdb",
            "path":    str(settings.DUCK_DB),
        }
