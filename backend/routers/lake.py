from fastapi import APIRouter
from backend.services.duck_service import get_view_counts

router = APIRouter(prefix="/api/lake", tags=["Data Lake"])


@router.get("/status")
def lake_status():
    """Row counts for every DuckDB view — quick overview of data availability."""
    counts = get_view_counts()
    return {
        "status": "ok",
        "views":  counts,
        "total_rows": sum(counts.values()),
    }
