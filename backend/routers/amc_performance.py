"""
routers/amc_performance.py
==========================
AMC Company (1000) Performance endpoints — /api/v1/amc/...

Consumers: fintech-command-center (Finance > AMC Performance page)

Data sources:
  02_Silver_Cleaned/amc_performance_{year}.parquet  — consolidated P&L from v_gl_summary
  02_Silver_Cleaned/ga_tb_{year}.parquet            — Balance sheet (shared with GA for now)

Endpoints:
  GET /api/v1/amc/performance   ?year=YYYY   → all months for year
  GET /api/v1/amc/production    ?year=YYYY   → production metrics (reuse GA)
  GET /api/v1/amc/balance-sheet ?year=YYYY   → balance sheet highlights
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
import pandas as pd

router = APIRouter(prefix="/api/v1/amc", tags=["AMC Performance"])

LAKE_ROOT = Path(__file__).resolve().parents[2]
SILVER    = LAKE_ROOT / "02_Silver_Cleaned"

MONTH_LABELS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def _load_parquet(name: str, year: int) -> pd.DataFrame:
    path = SILVER / name.format(year=year)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"AMC data not found for year {year}. Path: {path}",
        )
    return pd.read_parquet(path)


def _month_meta(period: str) -> dict:
    parts = period.split("-")
    if len(parts) == 2:
        year, mm = parts
        label_en = f"{MONTH_LABELS.get(mm, mm)} {year}"
    else:
        label_en = period
    return {"period": period, "label": label_en}


def _safe(val):
    """Convert numpy types to plain Python for JSON serialization."""
    try:
        if val != val:  # NaN
            return None
        return float(val)
    except (TypeError, ValueError):
        return val


# ── GET /api/v1/amc/performance ────────────────────────────────────────────────
@router.get("/performance")
def amc_performance_year(year: int = Query(2026, description="Fiscal year")):
    """AMC consolidated P&L performance for all available months in a year."""
    df = _load_parquet("amc_performance_{year}.parquet", year)
    df = df.sort_values("period")

    months = [p.split("-")[1] for p in df["period"]]
    labels = [f"{MONTH_LABELS.get(m, m)} {year}" for m in months]
    data   = {
        row["period"].split("-")[1]: {k: _safe(v) for k, v in row.items()}
        for _, row in df.iterrows()
    }

    return {
        "status": "ok",
        "year":   year,
        "months": months,
        "labels": labels,
        "data":   data,
    }


# ── GET /api/v1/amc/balance-sheet ─────────────────────────────────────────────
@router.get("/balance-sheet")
def amc_balance_sheet(year: int = Query(2026, description="Fiscal year")):
    """AMC balance sheet highlights — reuses GA TB file for now."""
    df = _load_parquet("ga_tb_{year}.parquet", year)
    df = df.sort_values("period")

    months = [p.split("-")[1] for p in df["period"]]
    labels = [f"{MONTH_LABELS.get(m, m)} {year}" for m in months]
    data   = {
        row["period"].split("-")[1]: {k: _safe(v) for k, v in row.items()}
        for _, row in df.iterrows()
    }

    return {
        "status": "ok",
        "year":   year,
        "months": months,
        "labels": labels,
        "data":   data,
    }
