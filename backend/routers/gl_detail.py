"""
routers/gl_detail.py
====================
GL account detail endpoints — /api/v1/gl/...
(Extends existing /api/finance/gl with versioned endpoints and balance summaries)

Consumers: audit-reconcile, main-dashboard
"""
from fastapi import APIRouter, Query
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/gl", tags=["GL v1"])


@router.get("/transactions")
def gl_transactions(
    year:    int       = Query(..., description="ปี เช่น 2025"),
    month:   int | None = Query(None, description="เดือน 1-12"),
    account: str | None = Query(None, description="GL Account เช่น '4111010'"),
    limit:   int        = Query(500, le=5000),
):
    """
    GL line-item transactions จาก Silver layer (v_gl).
    ใช้สำหรับ audit-reconcile ดึงรายการ GL ของบัญชีที่ระบุ
    """
    conditions = ["company_code = ?", "CAST(Year AS INTEGER) = ?"]
    params: list = ["1000", year]

    if month is not None:
        conditions.append("CAST(Month AS INTEGER) = ?")
        params.append(month)
    if account:
        conditions.append('"G/L Account" = ?')
        params.append(account)

    where = " AND ".join(conditions)
    df = query_df(
        f"""
        SELECT
            "Posting Date"               AS posting_date,
            "G/L Account"                AS account_code,
            "G/L Account: Long Text"     AS account_name,
            net_amount                   AS amount,
            "Text"                       AS description,
            "Document Number"            AS doc_number,
            "Cost Center: Short Text"    AS cost_center,
            source_file,
            Month, Year
        FROM v_gl
        WHERE {where}
        ORDER BY "Posting Date" DESC
        LIMIT ?
        """,
        params + [limit],
    )
    return {
        "status":  "ok",
        "year":    year,
        "count":   len(df),
        "data":    df.to_dict(orient="records"),
    }


@router.get("/accounts-by-group")
def gl_accounts_by_group(
    year:     int = Query(..., description="ปี เช่น 2026"),
    month:    int = Query(..., description="เดือน 1-12"),
    gl_group: str = Query(..., description="เช่น '4. Revenue', '5. COGS'"),
):
    """
    GL accounts ที่ประกอบกันเป็น GL Group สำหรับ period ที่ระบุ
    ใช้สำหรับ Lineage Drawer — Level 1: แสดง account breakdown ของ KPI
    """
    df = query_df(
        """
        SELECT
            "G/L Account"  AS account_code,
            GL_Name        AS account_name,
            SUM(Net_Amount) AS period_amount,
            COUNT(*)        AS transaction_count
        FROM v_gl_summary
        WHERE CAST(Year AS INTEGER) = ?
          AND CAST(Month AS INTEGER) = ?
          AND GL_Group = ?
        GROUP BY "G/L Account", GL_Name
        ORDER BY ABS(SUM(Net_Amount)) DESC
        """,
        [year, month, gl_group],
    )
    return {
        "status":   "ok",
        "year":     year,
        "month":    month,
        "gl_group": gl_group,
        "count":    len(df),
        "data":     df.to_dict(orient="records"),
    }


@router.get("/balance/{account}")
def gl_account_balance(
    account: str,
    year:    int | None = Query(None, description="ถ้าไม่ระบุ = ทุกปี"),
):
    """
    Cumulative balance ของ GL Account ที่ระบุ
    ใช้สำหรับ reconcile balance ระหว่างระบบกับ TB
    """
    conditions = ["company_code = ?", '"G/L Account" = ?']
    params: list = ["1000", account]

    if year:
        conditions.append("CAST(Year AS INTEGER) = ?")
        params.append(year)

    where = " AND ".join(conditions)
    df = query_df(
        f"""
        SELECT
            Year,
            Month,
            "G/L Account"            AS account_code,
            "G/L Account: Long Text" AS account_name,
            SUM(net_amount)          AS period_balance,
            COUNT(*)                 AS transaction_count
        FROM v_gl
        WHERE {where}
        GROUP BY Year, Month, "G/L Account", "G/L Account: Long Text"
        ORDER BY Year, Month
        """,
        params,
    )

    total = float(df["period_balance"].sum()) if not df.empty else 0.0
    return {
        "status":        "ok",
        "account":       account,
        "total_balance": round(total, 2),
        "count":         len(df),
        "data":          df.to_dict(orient="records"),
    }


@router.get("/accounts")
def list_gl_accounts(
    year: int = Query(2025, description="ปีสำหรับ filter"),
    search: str | None = Query(None, description="ค้นหาตาม account name"),
):
    """รายการ GL accounts ทั้งหมดพร้อมยอดรวม"""
    conditions = ["company_code = ?", "CAST(Year AS INTEGER) = ?"]
    params: list = ["1000", year]

    if search:
        conditions.append('"G/L Account: Long Text" ILIKE ?')
        params.append(f"%{search}%")

    where = " AND ".join(conditions)
    df = query_df(
        f"""
        SELECT
            "G/L Account"            AS account_code,
            "G/L Account: Long Text" AS account_name,
            SUM(net_amount)          AS total_balance,
            COUNT(*)                 AS transactions
        FROM v_gl
        WHERE {where}
        GROUP BY "G/L Account", "G/L Account: Long Text"
        ORDER BY "G/L Account"
        """,
        params,
    )
    return {
        "status": "ok",
        "year":   year,
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }
