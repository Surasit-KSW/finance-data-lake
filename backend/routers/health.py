from fastapi import APIRouter
from backend.core.config import settings

router = APIRouter(tags=["Health"])


def _health_data() -> dict:
    from backend.services.db_service import db_info

    db = db_info()
    status = "ok" if "error" not in db else "degraded"

    # DuckDB view list (local only)
    views = []
    if not settings.use_postgres:
        try:
            from backend.core.database import get_duck
            con = get_duck()
            rows = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' ORDER BY table_name"
            ).fetchall()
            views = [r[0] for r in rows]
            con.close()
        except Exception:
            pass

    return {
        "status":       status,
        "api_version":  settings.API_VERSION,
        "api_prefix":   settings.API_PREFIX,
        "database":     db,
        "duckdb_views": views,
        "project_root": str(settings.PROJECT_ROOT),
        "docs":         "/docs",
    }


@router.get("/health")
def health_check():
    return _health_data()


@router.get("/api/v1/health", tags=["Health v1"])
def health_v1():
    """Health check — returns API version, DB backend, available views."""
    return _health_data()
