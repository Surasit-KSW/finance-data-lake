"""
routers/cost_closing.py
========================
SAP Cost Closing data endpoints — /api/v1/cost-closing/...

Consumers: sap_cost_closing_app (Streamlit)

Note: sap_cost_closing_app currently reads CSV files from its local data/processed/.
      These endpoints expose the same data via API so the app can optionally
      read from the Data Lake instead of maintaining its own copies.

# TODO (tech-debt): /zreport and /fi-co-diff read CSV from sap_cost_closing_app/data/processed/
#   which is outside the Bronze→Silver→Gold pipeline.
#   Future: add ETL for cost closing data → 02_Silver_Cleaned/master_cost_closing.parquet
#   then route queries through db_service.query_df() like /production-cost does.
#   Tracked in: _Finance-Vault/08-Context/Standards/data-lake-organization.md
"""
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from backend.services.db_service import query_df
from backend.core.config import settings

router = APIRouter(prefix="/api/v1/cost-closing", tags=["Cost Closing v1"])

# sap_cost_closing_app lives next to _Finance_Data_Lake
COST_CLOSING_DIR = settings.PROJECT_ROOT.parent / "sap_cost_closing_app" / "data" / "processed"


def _read_local_csv(filename: str):
    """Read a CSV from sap_cost_closing_app processed data folder."""
    import pandas as pd
    f = COST_CLOSING_DIR / filename
    if not f.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Cost closing file not found: {filename}. "
                   "Run the cost closing pipeline first.",
        )
    return pd.read_csv(f, encoding="utf-8-sig")


@router.get("/zreport")
def get_zreport(
    period: str | None = Query(None, description="Period YYYY-MM (e.g. 2026-03)"),
):
    """
    Z-Report overview — cost center actual vs plan.
    Reads from sap_cost_closing_app/data/processed/ CSV files.
    """
    try:
        df = _read_local_csv("zreport_summary.csv")
        if period:
            if "period" in df.columns:
                df = df[df["period"] == period]
            elif "Period" in df.columns:
                df = df[df["Period"] == period]
        return {
            "status": "ok",
            "period": period,
            "count":  len(df),
            "data":   df.to_dict(orient="records"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to read zreport: {e}")


@router.get("/fi-co-diff")
def get_fi_co_diff(
    period: str | None = Query(None, description="Period YYYY-MM"),
    threshold: float    = Query(0.01, description="Min difference to show (THB)"),
):
    """
    FI-CO mismatch report — accounts where GL balance != CO balance.
    Used by sap_cost_closing_app for reconciliation alerts.
    """
    try:
        df = _read_local_csv("fi_co_diff.csv")
        if period and "period" in df.columns:
            df = df[df["period"] == period]
        if "difference" in df.columns:
            df = df[df["difference"].abs() >= threshold]
        return {
            "status":    "ok",
            "period":    period,
            "threshold": threshold,
            "count":     len(df),
            "data":      df.to_dict(orient="records"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to read fi_co_diff: {e}")


@router.get("/production-cost")
def get_production_cost(
    year:  int       = Query(2026),
    month: int | None = Query(None),
    plant: str | None = Query(None, description="Plant: 1100, 1200, 1300"),
):
    """
    Production cost summary from Silver layer (v_production).
    Alternative source to CSV for sap_cost_closing_app.
    """
    conditions = ['CAST("Year" AS INTEGER) = ?']
    params: list = [year]

    if month:
        conditions.append('CAST("Month" AS INTEGER) = ?')
        params.append(month)
    if plant:
        conditions.append('"Plant" = ?')
        params.append(plant)

    where = " AND ".join(conditions)
    try:
        df = query_df(
            f"""
            SELECT
                "Year", "Month", "Plant",
                SUM("Production Qty")  AS total_qty,
                SUM("Total Cost")      AS total_cost,
                COUNT(DISTINCT "Order No") AS orders
            FROM v_production
            WHERE {where}
            GROUP BY "Year", "Month", "Plant"
            ORDER BY "Year", "Month", "Plant"
            """,
            params,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Production data unavailable: {e}")

    return {
        "status": "ok",
        "year":   year,
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }
