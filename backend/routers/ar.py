from fastapi import APIRouter, Query
from backend.services.duck_service import query_df, query_scalar

router = APIRouter(prefix="/api/ar", tags=["Accounts Receivable"])


@router.get("/summary")
def ar_summary(year: int = Query(...)):
    """
    AR summary จาก GL accounts 12* (Receivable accounts)
    ใช้ v_gl เพราะ master_ar.parquet ยังไม่ได้สร้าง (Bronze AR ยังเป็น Excel)
    """
    df = query_df(
        """
        SELECT
            CAST(Month AS INTEGER)          AS month,
            "G/L Account"                   AS gl_account,
            "G/L Account: Long Text"        AS gl_name,
            SUM("Net_Amount")               AS net_movement,
            COUNT(*)                        AS transactions
        FROM v_gl
        WHERE CAST(Year AS INTEGER) = ?
          AND "G/L Account" LIKE '12%'
        GROUP BY month, gl_account, gl_name
        ORDER BY month, gl_account
        """,
        [year],
    )

    total = float(df["net_movement"].sum()) if not df.empty else 0.0

    return {
        "status":          "ok",
        "year":            year,
        "total_ar_balance": round(total, 2),
        "note":            "AR balance from GL accounts 12* (v_gl). Run etl_ar.py for full AR aging.",
        "monthly_data":    df.to_dict(orient="records"),
    }


@router.get("/by-account")
def ar_by_account(year: int = Query(...)):
    """AR balance breakdown by GL account"""
    df = query_df(
        """
        SELECT
            "G/L Account"                   AS gl_account,
            "G/L Account: Long Text"        AS gl_name,
            SUM("Net_Amount")               AS balance,
            COUNT(*)                        AS transactions
        FROM v_gl
        WHERE CAST(Year AS INTEGER) = ?
          AND "G/L Account" LIKE '12%'
        GROUP BY gl_account, gl_name
        ORDER BY balance
        """,
        [year],
    )
    return {"status": "ok", "data": df.to_dict(orient="records")}
