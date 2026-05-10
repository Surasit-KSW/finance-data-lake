"""
core/database.py — Two-database setup
  1. finance_lake.duckdb  → OLAP read-only (DuckDB)
  2. operations.db        → Operational read-write (SQLite via SQLAlchemy)
"""
import duckdb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.core.config import settings

# ── DuckDB (Analytics) ───────────────────────────────────────────────────────
# ใช้ connection-per-request เพราะ DuckDB ไม่รองรับ multi-thread write
# แต่ read_only=True ปลอดภัยสำหรับ concurrent reads
def get_duck() -> duckdb.DuckDBPyConnection:
    """Open a read-only DuckDB connection. Close after use."""
    return duckdb.connect(str(settings.DUCK_DB), read_only=True)


# ── SQLite (Operations) ──────────────────────────────────────────────────────
_ops_engine = create_engine(
    f"sqlite:///{settings.OPS_DB}",
    connect_args={"check_same_thread": False},
)
OpsSession = sessionmaker(bind=_ops_engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_ops_db():
    """FastAPI dependency — yields SQLAlchemy session, closes on exit."""
    db = OpsSession()
    try:
        yield db
    finally:
        db.close()


def init_ops_db() -> None:
    """Create all operational tables if they don't exist."""
    from backend.models import ops  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=_ops_engine)
