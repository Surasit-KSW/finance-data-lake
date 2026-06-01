from datetime import datetime

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


@router.get("/api/v1/pipeline/freshness", tags=["Health v1"])
def pipeline_freshness():
    """
    Latest data period ต่อ domain — ใช้ใน Dashboard แสดงว่าข้อมูลสดแค่ไหน
    Response: { gl: "2026-05", ar: "2026-04", sales: "2026-05", production: "2026-05" }
    """
    from backend.services.db_service import query_df

    def latest_period(view: str) -> str | None:
        try:
            df = query_df(
                f"""
                SELECT
                    MAX(CAST(Year AS INTEGER))  AS max_year,
                    MAX(CAST(Month AS INTEGER)) AS max_month
                FROM (
                    SELECT Year, Month FROM {view}
                    WHERE CAST(Year AS INTEGER) = (
                        SELECT MAX(CAST(Year AS INTEGER)) FROM {view}
                    )
                ) t
                """,
                [],
            )
            if df.empty or df["max_year"].iloc[0] is None:
                return None
            yr = int(df["max_year"].iloc[0])
            mo = int(df["max_month"].iloc[0])
            return f"{yr}-{mo:02d}"
        except Exception:
            return None

    domains = {
        "gl":         latest_period("v_gl"),
        "gl_summary": latest_period("v_gl_summary"),
        "sales":      latest_period("v_sales"),
        "production": latest_period("v_production"),
        "ar":         latest_period("v_ar"),
    }

    return {
        "status":   "ok",
        "freshness": domains,
        "as_of":    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
