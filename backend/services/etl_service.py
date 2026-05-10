"""
services/etl_service.py — Run ETL pipeline and track results in operations.db
"""
import subprocess
import sys
import datetime
import threading
from sqlalchemy.orm import Session
from backend.core.config import settings
from backend.models.ops import ETLRun


def trigger_pipeline(
    db: Session,
    domain: str = "all",
    year: str | None = None,
) -> ETLRun:
    """
    สร้าง ETLRun record แล้ว spawn subprocess รัน run_pipeline.py
    Returns ETLRun ทันที (status='running') — pipeline รันใน background thread
    """
    run = ETLRun(
        started_at=datetime.datetime.utcnow(),
        status="running",
        domain=domain,
        year=year,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # รัน pipeline ใน background thread เพื่อไม่บล็อก API response
    thread = threading.Thread(
        target=_run_pipeline_bg,
        args=(run.id, domain, year),
        daemon=True,
    )
    thread.start()

    return run


def _run_pipeline_bg(run_id: int, domain: str, year: str | None) -> None:
    """Background thread: รัน run_pipeline.py แล้วอัพเดต ETLRun"""
    from backend.core.database import OpsSession
    from backend.models.ops import ETLRun

    db = OpsSession()
    try:
        # Build command
        cmd = [sys.executable, str(settings.PIPELINE_SCRIPT)]

        if domain == "all":
            cmd.append("--all")
        else:
            cmd += ["--layer", "silver", "--domain", domain]
            if year:
                cmd += ["--year", year]

        env = {"PYTHONUTF8": "1", "PATH": __import__("os").environ.get("PATH", "")}

        result = subprocess.run(
            cmd,
            cwd=str(settings.PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**__import__("os").environ, "PYTHONUTF8": "1"},
        )

        finished = datetime.datetime.utcnow()
        status = "success" if result.returncode == 0 else "failed"
        error_msg = result.stderr[:2000] if result.returncode != 0 else None

        db.query(ETLRun).filter(ETLRun.id == run_id).update({
            "finished_at": finished,
            "status":      status,
            "error_msg":   error_msg,
        })
        db.commit()

        # Refresh DuckDB views after successful ETL
        if status == "success":
            _refresh_duckdb()

    except Exception as e:
        db.query(ETLRun).filter(ETLRun.id == run_id).update({
            "finished_at": datetime.datetime.utcnow(),
            "status":      "failed",
            "error_msg":   str(e)[:2000],
        })
        db.commit()
    finally:
        db.close()


def _refresh_duckdb() -> None:
    """Re-run init_duckdb.py to refresh views after ETL."""
    init_script = settings.PROJECT_ROOT / "04_Data_Pipelines" / "init_duckdb.py"
    subprocess.run(
        [sys.executable, str(init_script)],
        cwd=str(settings.PROJECT_ROOT),
        env={**__import__("os").environ, "PYTHONUTF8": "1"},
        capture_output=True,
    )


def get_runs(db: Session, limit: int = 20) -> list[dict]:
    runs = (
        db.query(ETLRun)
        .order_by(ETLRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [r.to_dict() for r in runs]
