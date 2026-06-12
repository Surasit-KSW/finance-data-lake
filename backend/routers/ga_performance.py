"""
routers/ga_performance.py
=========================
GA Company Performance endpoints — /api/v1/ga/...

Consumers: fintech-command-center (Finance > GA Performance page)

Data sources:
  02_Silver_Cleaned/ga_performance_{year}.parquet  — P&L computed from GL
  02_Silver_Cleaned/ga_production_{year}.parquet   — Production metrics from PRD
  02_Silver_Cleaned/ga_tb_{year}.parquet           — Balance sheet from TB

Endpoints:
  GET /api/v1/ga/performance          ?year=YYYY         → all months for year
  GET /api/v1/ga/performance/{period}                    → single month YYYY-MM
  GET /api/v1/ga/production           ?year=YYYY         → production metrics
  GET /api/v1/ga/balance-sheet        ?year=YYYY         → TB balance sheet highlights
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
import pandas as pd

router = APIRouter(prefix="/api/v1/ga", tags=["GA Performance"])

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
            detail=f"Data not found for year {year}. Run ETL first: "
                   f"python 04_Data_Pipelines/silver_transform/etl_ga_performance.py --year {year}",
        )
    return pd.read_parquet(path)


def _month_meta(period: str) -> dict:
    """Return label and Thai label for a YYYY-MM period string."""
    parts = period.split("-")
    if len(parts) == 2:
        year, mm = parts
        label_en = f"{MONTH_LABELS.get(mm, mm)} {year}"
    else:
        label_en = period
    return {"period": period, "label": label_en}


# ── GET /api/v1/ga/performance ──────────────────────────────────────────────
@router.get("/performance")
def ga_performance_year(year: int = Query(2026, description="Fiscal year")):
    """
    GA P&L performance for all available months in a year.

    Returns the same data shape as gl_data_corrected.json (used by fintech-command-center).
    """
    df = _load_parquet("ga_performance_{year}.parquet", year)
    df = df.sort_values("period")

    months  = [p.split("-")[1] for p in df["period"]]
    labels  = [f"{MONTH_LABELS.get(m, m)} {year}" for m in months]
    data    = {row["period"].split("-")[1]: _row_to_dict(row)
               for _, row in df.iterrows()}

    return {
        "status":  "ok",
        "year":    year,
        "months":  months,
        "labels":  labels,
        "data":    data,
    }


# ── GET /api/v1/ga/performance/{period} ────────────────────────────────────
@router.get("/performance/{period}")
def ga_performance_period(period: str):
    """
    GA P&L for a single month.

    period format: YYYY-MM  (e.g. 2026-01)
    """
    try:
        year = int(period.split("-")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")

    df = _load_parquet("ga_performance_{year}.parquet", year)
    row = df[df["period"] == period]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"No data for period {period}")

    return {
        "status": "ok",
        **_month_meta(period),
        **_row_to_dict(row.iloc[0]),
    }


# ── GET /api/v1/ga/production ───────────────────────────────────────────────
@router.get("/production")
def ga_production_year(year: int = Query(2026, description="Fiscal year")):
    """
    GA production metrics (yield, volume, carryover orders) for all months.
    """
    df = _load_parquet("ga_production_{year}.parquet", year)
    df = df.sort_values("period")

    months = [p.split("-")[1] for p in df["period"]]
    labels = [f"{MONTH_LABELS.get(m, m)} {year}" for m in months]
    prd    = {row["period"].split("-")[1]: _prd_row_to_dict(row)
              for _, row in df.iterrows()}

    return {
        "status":  "ok",
        "year":    year,
        "months":  months,
        "labels":  labels,
        "prd":     prd,
    }


# ── GET /api/v1/ga/balance-sheet ───────────────────────────────────────────
@router.get("/balance-sheet")
def ga_balance_sheet(year: int = Query(2026, description="Fiscal year")):
    """
    GA Balance Sheet highlights (Working Capital) from Trial Balance.

    Returns monthly snapshots of Cash, AR Trade, Inventory, AP for all available months.
    Source: 02_Silver_Cleaned/ga_tb_{year}.parquet (run etl_ga_tb.py first).
    """
    df = _load_parquet("ga_tb_{year}.parquet", year)
    df = df.sort_values("period")

    months = [p.split("-")[1] for p in df["period"]]
    labels = [f"{MONTH_LABELS.get(m, m)} {year}" for m in months]
    data   = {row["period"].split("-")[1]: _row_to_dict(row)
              for _, row in df.iterrows()}

    return {
        "status":  "ok",
        "year":    year,
        "months":  months,
        "labels":  labels,
        "data":    data,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────
def _row_to_dict(row) -> dict:
    """Convert a parquet row (Series or row) to a plain dict, NaN → 0."""
    if hasattr(row, "to_dict"):
        d = row.to_dict()
    else:
        d = dict(row)
    return {k: (0.0 if pd.isna(v) else v) for k, v in d.items()}


def _prd_row_to_dict(row) -> dict:
    return _row_to_dict(row)
