from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.core.database import get_ops_db
from backend.services import etl_service

router = APIRouter(prefix="/api/etl", tags=["ETL Pipeline"])

VALID_DOMAINS = {"all", "sales", "production", "gl", "ar"}


@router.post("/run")
def run_etl(
    domain: str      = Query("all", description="all | sales | production | gl | ar"),
    year:   str | None = Query(None, description="ปี เช่น 2025 (ใช้กับ sales/production)"),
    db:     Session  = Depends(get_ops_db),
):
    """
    Trigger ETL pipeline ใน background.
    Returns ETLRun record ทันที — ตรวจสถานะผ่าน GET /api/etl/runs
    """
    if domain not in VALID_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"domain ไม่ถูกต้อง เลือกจาก: {sorted(VALID_DOMAINS)}",
        )

    run = etl_service.trigger_pipeline(db, domain=domain, year=year)
    return {
        "status":  "accepted",
        "message": f"ETL pipeline started (domain={domain}, year={year})",
        "run_id":  run.id,
        "check":   f"/api/etl/runs/{run.id}",
    }


@router.get("/runs")
def list_runs(
    limit: int     = Query(20, le=100),
    db:    Session = Depends(get_ops_db),
):
    """ETL run history — ล่าสุดก่อน"""
    return {"status": "ok", "data": etl_service.get_runs(db, limit=limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_ops_db)):
    """ดูสถานะ ETL run ตาม ID"""
    from backend.models.ops import ETLRun
    run = db.query(ETLRun).filter(ETLRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "ok", "data": run.to_dict()}
