from fastapi import APIRouter, Query, HTTPException
from backend.services.finance_calc import get_pnl, get_pnl_yoy, get_kpi
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/finance", tags=["Finance"])


@router.get("/pnl/{year}")
def pnl_statement(year: int):
    """P&L statement จากข้อมูล GL จริง (ไม่มี dummy numbers)"""
    result = get_pnl(year)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "ok", "data": result}


@router.get("/pnl/compare/{year1}/{year2}")
def pnl_yoy(year1: int, year2: int):
    """เปรียบเทียบ P&L 2 ปี พร้อม variance"""
    result = get_pnl_yoy(year1, year2)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "ok", "data": result}


@router.get("/kpi/{year}")
def kpi(year: int):
    """KPI dashboard: margins, growth, DSO"""
    result = get_kpi(year)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "ok", "data": result}


@router.get("/gl")
def gl_transactions(
    year:     int            = Query(..., description="ปี เช่น 2025"),
    month:    int | None     = Query(None, description="เดือน 1-12"),
    gl_group: str | None     = Query(None, description="เช่น '4. Revenue'"),
    account:  str | None     = Query(None, description="GL account เช่น '4111010'"),
    limit:    int            = Query(500, le=5000),
):
    """GL transactions drill-down จาก v_gl (2.7M rows)"""
    conditions = ["company_code = ?", "CAST(Year AS INTEGER) = ?"]
    params: list = ["1000", year]

    if month is not None:
        conditions.append("CAST(Month AS INTEGER) = ?")
        params.append(month)
    if gl_group:
        conditions.append('"G/L Account" LIKE ?')
        params.append(f"{gl_group[0]}%")   # match first char e.g. "4%"
    if account:
        conditions.append('"G/L Account" = ?')
        params.append(account)

    where = " AND ".join(conditions)
    df = query_df(
        f"""
        SELECT "Posting Date", "G/L Account", "G/L Account: Long Text",
               net_amount, "Text", "Document Number", "Cost Center: Short Text",
               "Vendor Account: Name 1", Month, Year
        FROM v_gl
        WHERE {where}
        ORDER BY "Posting Date" DESC
        LIMIT ?
        """,
        params + [limit],
    )

    return {
        "status": "ok",
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }


@router.get("/gl/summary")
def gl_summary(year: int = Query(...)):
    """GL summary by GL_Group and account — from Gold layer"""
    df = query_df(
        """
        SELECT GL_Group AS gl_group, "G/L Account", GL_Name AS gl_name,
               SUM(Net_Amount) AS total,
               COUNT(*) AS periods
        FROM v_gl_summary
        WHERE year = ?
        GROUP BY GL_Group, "G/L Account", GL_Name
        ORDER BY GL_Group, "G/L Account"
        """,
        [year],
    )
    return {"status": "ok", "count": len(df), "data": df.to_dict(orient="records")}
