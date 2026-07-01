from fastapi import APIRouter, Query
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/sales", tags=["Sales"])


@router.get("/summary/{year}")
def sales_summary(year: int):
    """Monthly sales by product group (Mat Group Des.)"""
    df = query_df(
        """
        SELECT
            EXTRACT(MONTH FROM "Billing Date")::int  AS month,
            "Mat Group Des."                         AS product_group,
            SUM("Net Value(THB)")                    AS revenue,
            SUM("Billed Qty")                        AS qty_kg,
            COUNT(DISTINCT "Billing No")             AS invoices
        FROM v_sales
        WHERE company_code = ?
          AND EXTRACT(YEAR FROM "Billing Date")::int = ?
          AND "Net Value(THB)" > 0
        GROUP BY month, product_group
        ORDER BY month, revenue DESC
        """,
        ["1000", year],
    )
    return {"status": "ok", "year": year, "count": len(df),
            "data": df.to_dict(orient="records")}


@router.get("/customers")
def top_customers(
    year: int       = Query(...),
    top:  int       = Query(10, le=100),
):
    """Top customers by revenue"""
    df = query_df(
        """
        SELECT
            "Sold-to Name"                                      AS customer,
            SUM("Net Value(THB)")                               AS revenue,
            SUM("Billed Qty")                                   AS qty_kg,
            COUNT(DISTINCT "Billing No")                        AS invoices,
            COUNT(DISTINCT EXTRACT(MONTH FROM "Billing Date"))  AS active_months
        FROM v_sales
        WHERE company_code = ?
          AND EXTRACT(YEAR FROM "Billing Date")::int = ?
          AND "Net Value(THB)" > 0
        GROUP BY customer
        ORDER BY revenue DESC
        LIMIT ?
        """,
        ["1000", year, top],
    )
    return {"status": "ok", "year": year, "data": df.to_dict(orient="records")}


@router.get("/yoy")
def sales_yoy(
    year1: int = Query(..., description="ปีเปรียบเทียบ เช่น 2024"),
    year2: int = Query(..., description="ปีปัจจุบัน เช่น 2025"),
):
    """Year-over-year sales comparison by product group"""
    df = query_df(
        """
        SELECT
            EXTRACT(YEAR FROM "Billing Date")::int  AS year,
            "Mat Group Des."                        AS product_group,
            SUM("Net Value(THB)")                   AS revenue,
            SUM("Billed Qty")                       AS qty_kg
        FROM v_sales
        WHERE company_code = ?
          AND EXTRACT(YEAR FROM "Billing Date")::int IN (?, ?)
          AND "Net Value(THB)" > 0
        GROUP BY year, product_group
        ORDER BY product_group, year
        """,
        ["1000", year1, year2],
    )
    return {"status": "ok", "year1": year1, "year2": year2,
            "data": df.to_dict(orient="records")}


@router.get("/by-month")
def sales_by_month(
    year1: int = Query(...),
    year2: int = Query(...),
):
    """Monthly revenue totals for two years (สำหรับ chart)"""
    df = query_df(
        """
        SELECT
            EXTRACT(YEAR  FROM "Billing Date")::int  AS year,
            EXTRACT(MONTH FROM "Billing Date")::int  AS month,
            SUM("Net Value(THB)")                    AS revenue
        FROM v_sales
        WHERE company_code = ?
          AND EXTRACT(YEAR FROM "Billing Date")::int IN (?, ?)
          AND "Net Value(THB)" > 0
        GROUP BY year, month
        ORDER BY year, month
        """,
        ["1000", year1, year2],
    )
    return {"status": "ok", "data": df.to_dict(orient="records")}
