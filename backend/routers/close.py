"""
routers/close.py
=================
Close Orchestrator status endpoint — /api/v1/close/...

Consumers:
  - ai/finance-ops/workspace/monthend/close_orchestrator (producer, POST /tick)
  - fintech-command-center Close Control Tower page (consumer, GET /status)
  - fintech-command-center Daily Briefing closeTasks widget (consumer, via
    backend.routers.briefing._read_close_cache(), same JSON file)

Storage: 05_Ops_Status/close_status_current.json — single file, fully
overwritten on every tick (no history/versioning — matches the old Google
Sheet's "always reflects latest tick" behavior).
"""
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import settings

router = APIRouter(prefix="/api/v1/close", tags=["Close Orchestrator"])

NEVER_RUN_STATUS = {
    "never_run": True,
    "company": "1000", "year": None, "month": None,
    "blocked_reason": None,
    "checklist": {}, "readiness": {}, "extract_attempts": {},
    "anomalies": [], "tick_log": [], "tick_duration_sec": None,
    "synced_at": None, "close_tasks": [],
}


class Anomaly(BaseModel):
    source: str
    pattern: str
    auto_corrected: bool
    detail: str


class CloseTask(BaseModel):
    id: str
    name: str
    status: str
    time: str = "-"
    linkTo: str


class CloseTickRequest(BaseModel):
    company: str
    year: int
    month: int
    blocked_reason: str | None = None
    checklist: dict = {}
    readiness: dict = {}
    extract_attempts: dict = {}
    anomalies: list[Anomaly] = []
    tick_log: list[str] = []
    tick_duration_sec: float = 0.0
    synced_at: str
    close_tasks: list[CloseTask] = []


def _status_path():
    return settings.OPS_STATUS_DIR / "close_status_current.json"


@router.post("/tick")
def post_close_tick(req: CloseTickRequest):
    """Receive one tick's full state from the close orchestrator and persist it."""
    path = _status_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(req.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp_path, path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist close status: {e}")
    return {"status": "ok"}


@router.get("/status")
def get_close_status():
    """Return the latest tick's full state, or a safe placeholder if none exists yet."""
    path = _status_path()
    if not path.exists():
        return NEVER_RUN_STATUS
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return NEVER_RUN_STATUS
