"""
routers/audit_data.py
======================
Audit & reconciliation endpoints — /api/v1/audit/...

Consumers: audit-reconcile project, main-dashboard

SQL is written to be compatible with both DuckDB (local) and PostgreSQL (Vercel).
  - EXTRACT(YEAR FROM col) works on both — do NOT use strftime()
  - ? params (db_service converts to %s for PostgreSQL automatically)
"""
from fastapi import APIRouter, HTTPException, Query
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/audit", tags=["Audit v1"])


@router.get("/ar-aging")
def ar_aging(
    as_of_year:  int       = Query(2025),
    as_of_month: int       = Query(12),
    customer:    str | None = Query(None, description="Filter by customer name"),
):
    """
    AR Aging report — buckets: current, 30, 60, 90, 90+ days
    Source: v_ar (Silver layer or PostgreSQL table)
    """
    conditions = [
        "EXTRACT(YEAR  FROM \"Invoice Date\")::int <= ?",
        "EXTRACT(MONTH FROM \"Invoice Date\")::int <= ?",
    ]
    params: list = [as_of_year, as_of_month]

    if customer:
        conditions.append('"Customer Name" ILIKE ?')
        params.append(f"%{customer}%")

    where = " AND ".join(conditions)
    df = query_df(
        f"""
        SELECT
            "Customer Code"  AS customer_code,
            "Customer Name"  AS customer_name,
            "Invoice No"     AS invoice_no,
            "Invoice Date"   AS invoice_date,
            "Due Date"       AS due_date,
            "Outstanding"    AS outstanding_amount,
            "Aging Bucket"   AS aging_bucket
        FROM v_ar
        WHERE {where}
        ORDER BY "Outstanding" DESC
        LIMIT 2000
        """,
        params,
    )
    return {
        "status": "ok",
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }


@router.get("/ar-summary")
def ar_summary(year: int = Query(2025)):
    """AR aging summary by customer — top 20 overdue"""
    df = query_df(
        """
        SELECT
            "Customer Name"     AS customer,
            SUM("Outstanding")  AS total_outstanding,
            COUNT(*)            AS invoice_count
        FROM v_ar
        WHERE EXTRACT(YEAR FROM "Invoice Date")::int = ?
        GROUP BY "Customer Name"
        ORDER BY total_outstanding DESC
        LIMIT 20
        """,
        [year],
    )
    return {
        "status": "ok",
        "year":   year,
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }


@router.get("/gl-reconcile")
def gl_reconcile(
    account: str = Query(..., description="GL Account to reconcile"),
    year:    int = Query(2025),
):
    """
    GL reconciliation: monthly cumulative balance for an account.
    Compare against TB balance to verify consistency.
    """
    df = query_df(
        """
        SELECT
            year, month,
            SUM(net_amount)          AS period_amount,
            SUM(SUM(net_amount)) OVER (
                PARTITION BY year ORDER BY month
            )                        AS cumulative_balance,
            COUNT(*)                 AS transactions
        FROM v_gl
        WHERE "G/L Account" = ?
          AND year = ?
        GROUP BY year, month
        ORDER BY year, month
        """,
        [account, year],
    )
    return {
        "status":   "ok",
        "account":  account,
        "year":     year,
        "count":    len(df),
        "data":     df.to_dict(orient="records"),
    }
