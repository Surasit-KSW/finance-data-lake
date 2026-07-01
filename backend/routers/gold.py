"""
routers/gold.py
===============
Gold layer read endpoints — /api/v1/gold/...

Serves aggregated Gold DataMart parquets via DuckDB views.
Consumers: fin-dashboard, main-dashboard, SAP Close Assistant
"""
from fastapi import APIRouter, Query
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/gold", tags=["Gold v1"])


@router.get("/leadsheet")
def gold_leadsheet(
    year: int = Query(..., description="ปี เช่น 2026"),
    quarter: str | None = Query(None, description="ไตรมาส เช่น Q1, Q2, Q3, Q4"),
):
    """Trial Balance leadsheet — Balance Sheet + P&L aggregated."""
    conditions = ["year = ?"]
    params: list = [year]
    if quarter:
        conditions.append("quarter = ?")
        params.append(quarter)
    where = " AND ".join(conditions)
    df = query_df(
        f"SELECT * FROM gold_leadsheet WHERE {where} ORDER BY statement, section_order, label_order",
        params,
    )
    return {"status": "ok", "year": year, "quarter": quarter, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/cashflow")
def gold_cashflow(
    year: int = Query(..., description="ปี เช่น 2026"),
    quarter: str | None = Query(None, description="ไตรมาส เช่น Q1"),
):
    """Cash Flow Statement (indirect method)."""
    conditions = ["year = ?"]
    params: list = [year]
    if quarter:
        conditions.append("quarter = ?")
        params.append(quarter)
    where = " AND ".join(conditions)
    df = query_df(
        f"SELECT * FROM gold_cashflow WHERE {where} ORDER BY section_order, label_order",
        params,
    )
    return {"status": "ok", "year": year, "quarter": quarter, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/ppe")
def gold_ppe(
    year: int = Query(..., description="ปี เช่น 2026"),
    quarter: str | None = Query(None, description="ไตรมาส เช่น Q1"),
):
    """PPE Roll-Forward Schedule."""
    conditions = ["year = ?"]
    params: list = [year]
    if quarter:
        conditions.append("quarter = ?")
        params.append(quarter)
    where = " AND ".join(conditions)
    df = query_df(
        f"SELECT * FROM gold_ppe WHERE {where} ORDER BY class_order, movement_order",
        params,
    )
    return {"status": "ok", "year": year, "quarter": quarter, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/elimination")
def gold_elimination(
    year: int = Query(..., description="ปี เช่น 2026"),
    quarter: str | None = Query(None, description="ไตรมาส เช่น Q1"),
):
    """Consolidation Elimination entries."""
    conditions = ["year = ?"]
    params: list = [year]
    if quarter:
        conditions.append("quarter = ?")
        params.append(quarter)
    where = " AND ".join(conditions)
    df = query_df(
        f"SELECT * FROM gold_elimination WHERE {where} ORDER BY elim_order",
        params,
    )
    return {"status": "ok", "year": year, "quarter": quarter, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/related-party")
def gold_related_party(
    year: int = Query(..., description="ปี เช่น 2026"),
    quarter: str | None = Query(None, description="ไตรมาส เช่น Q1"),
):
    """Related Party Transactions & Balances."""
    conditions = ["year = ?"]
    params: list = [year]
    if quarter:
        conditions.append("quarter = ?")
        params.append(quarter)
    where = " AND ".join(conditions)
    df = query_df(
        f"SELECT * FROM gold_related_party WHERE {where} ORDER BY category_order",
        params,
    )
    return {"status": "ok", "year": year, "quarter": quarter, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/gp-by-plant")
def gold_gp_by_plant(
    year: int = Query(..., description="ปี เช่น 2026"),
    month: int | None = Query(None, description="เดือน 1-12"),
    plant: str | None = Query(None, description="Plant เช่น 1100, 1200, 1300"),
):
    """Gross Profit by Plant — monthly."""
    conditions = ['"Year" = ?']
    params: list = [year]
    if month:
        conditions.append('"Month" = ?')
        params.append(month)
    if plant:
        conditions.append('"Plant" = ?')
        params.append(plant)
    where = " AND ".join(conditions)
    df = query_df(
        f'SELECT * FROM gold_gp_by_plant WHERE {where} ORDER BY "Year", "Month", "Plant"',
        params,
    )
    return {"status": "ok", "year": year, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/revenue")
def gold_revenue(
    year: int = Query(..., description="ปี เช่น 2026"),
    month: int | None = Query(None, description="เดือน 1-12"),
    plant: str | None = Query(None, description="Plant เช่น 1100"),
):
    """Monthly Revenue by Plant."""
    conditions = ['"Year" = ?']
    params: list = [year]
    if month:
        conditions.append('"Month" = ?')
        params.append(month)
    if plant:
        conditions.append('"Plant" = ?')
        params.append(plant)
    where = " AND ".join(conditions)
    df = query_df(
        f'SELECT * FROM gold_revenue_monthly WHERE {where} ORDER BY "Year", "Month", "Plant"',
        params,
    )
    return {"status": "ok", "year": year, "count": len(df), "data": df.to_dict(orient="records")}
