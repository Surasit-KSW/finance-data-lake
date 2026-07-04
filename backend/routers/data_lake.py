"""
routers/data_lake.py
====================
Finance Data Lake — consolidated DuckDB endpoints for Phase 3 wiring.
All endpoints source from local DuckDB views.

/api/v1/data-lake/fpa-summary   — 12-month Actual vs Prior Year P&L
/api/v1/data-lake/fpa-variance  — GL-level cost variance vs prior-year same month
/api/v1/data-lake/treasury      — Cash + AR + AP + NWC runway snapshot
"""
import math
from datetime import date
from fastapi import APIRouter, Query, HTTPException
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/data-lake", tags=["Data Lake v1"])


# ─── Shared Helpers ───────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    """Convert val to float; return default for None/NaN/Inf."""
    try:
        v = float(val) if val is not None else default
        return default if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return default


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date '{s}'. Use YYYY-MM-DD.")


def _gl_balance(year: int, month: int, account_prefix: str, ytd: bool = True) -> float:
    """
    Sum Net_Amount from v_gl for accounts matching account_prefix%.
    ytd=True → cumulative Jan–month; ytd=False → single month.
    Sign: Assets (1.*) = positive, Liabilities (2.*) = negative — caller applies abs() as needed.
    """
    month_cond = 'CAST("Month" AS INTEGER) <= ?' if ytd else 'CAST("Month" AS INTEGER) = ?'
    try:
        df = query_df(
            f"""
            SELECT SUM("Net_Amount") AS balance
            FROM v_gl
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND {month_cond}
              AND CAST("G/L Account" AS VARCHAR) LIKE ?
            """,
            ["1000", year, month, f"{account_prefix}%"],
        )
        return _safe_float(df.iloc[0]["balance"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _gl_summary_amount(year: int, month: int, gl_group) -> float:
    """
    Sum Net_Amount from v_gl_summary for given GL_Group(s) in a single month.
    gl_group may be a str or list[str].
    Note: v_gl_summary has no company_code column (single-entity, 1000 only).
    """
    try:
        if isinstance(gl_group, list):
            placeholders = ",".join("?" * len(gl_group))
            params = gl_group + [year, month]
            df = query_df(
                f"""
                SELECT SUM("Net_Amount") AS total
                FROM v_gl_summary
                WHERE "GL_Group" IN ({placeholders})
                  AND CAST("Year" AS INTEGER) = ?
                  AND CAST("Month" AS INTEGER) = ?
                """,
                params,
            )
        else:
            df = query_df(
                """
                SELECT SUM("Net_Amount") AS total
                FROM v_gl_summary
                WHERE "GL_Group" = ?
                  AND CAST("Year" AS INTEGER) = ?
                  AND CAST("Month" AS INTEGER) = ?
                """,
                [gl_group, year, month],
            )
        return _safe_float(df.iloc[0]["total"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _sales_revenue(year: int, month: int) -> float:
    """Revenue from v_sales (Net_Value_THB, company 1000, non-cancelled rows)."""
    try:
        df = query_df(
            """
            SELECT SUM("Net_Value_THB") AS revenue
            FROM v_sales
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND ("Cancelled" IS NULL OR TRIM("Cancelled") = '')
            """,
            ["1000", year, month],
        )
        return _safe_float(df.iloc[0]["revenue"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _ar_overdue_gt60(year: int) -> float:
    """Open AR items overdue >60 days from v_ar. Returns 0.0 if v_ar not ready."""
    try:
        df = query_df(
            """
            SELECT SUM("Company Code Currency Value") AS overdue_amt
            FROM v_ar
            WHERE company_code = ?
              AND "Fiscal Year" = ?
              AND CAST("Days 1" AS DOUBLE) > 60
              AND "Company Code Currency Value" > 0
            """,
            ["1000", year],
        )
        return round(_safe_float(df.iloc[0]["overdue_amt"]) if not df.empty else 0.0, 2)
    except Exception:
        return 0.0


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/fpa-summary")
def get_fpa_summary(year: int = Query(2026)):
    """
    12-month Actual vs Prior Year P&L for FP&A page top section.

    Revenue     ← v_sales (Net_Value_THB, company 1000, non-cancelled)
    COGS        ← v_gl_summary GL_Group = '5. COGS'
    Opex        ← v_gl_summary GL_Group IN ('6. Selling Exp', '7. Admin Exp')
    Prior Year  ← same queries with year-1

    Future months (month > today for current year) → all numeric fields null.
    """
    today = date.today()
    months_out = []

    for month in range(1, 13):
        is_future = year > today.year or (year == today.year and month > today.month)
        if is_future:
            months_out.append({
                "month": month, "revenue": None, "cogs": None,
                "grossProfit": None, "gpMargin": None,
                "opex": None, "ebit": None, "priorYear": None,
            })
            continue

        try:
            revenue      = _sales_revenue(year, month)
            cogs         = _gl_summary_amount(year, month, "5. COGS")
            opex         = _gl_summary_amount(year, month, ["6. Selling Exp", "7. Admin Exp"])
            py_revenue   = _sales_revenue(year - 1, month)
            py_cogs      = _gl_summary_amount(year - 1, month, "5. COGS")

            gross_profit    = revenue - cogs
            py_gross_profit = py_revenue - py_cogs

            months_out.append({
                "month":       month,
                "revenue":     round(revenue, 2),
                "cogs":        round(cogs, 2),
                "grossProfit": round(gross_profit, 2),
                "gpMargin":    round(gross_profit / revenue * 100, 2) if revenue > 0 else None,
                "opex":        round(opex, 2),
                "ebit":        round(gross_profit - opex, 2),
                "priorYear": {
                    "revenue":  round(py_revenue, 2),
                    "gpMargin": round(py_gross_profit / py_revenue * 100, 2) if py_revenue > 0 else None,
                },
            })
        except Exception:
            months_out.append({
                "month": month, "revenue": None, "cogs": None,
                "grossProfit": None, "gpMargin": None,
                "opex": None, "ebit": None, "priorYear": None,
            })

    return {"year": year, "months": months_out}


@router.get("/fpa-variance")
def get_fpa_variance(year: int = Query(2026), month: int = Query(7)):
    """
    GL-level cost variance vs prior-year same month for FP&A drill-down.

    Actual  ← v_gl GROUP BY G/L Account for year/month (company 1000, cost accounts 5*)
    Baseline← v_gl GROUP BY G/L Account for year-1/month (prior year same month)
    Variance= actual - baseline
    Flag    = 'over' if variancePct > 5%, 'under' if variancePct < -5%, else 'ok'
    """
    period = f"{year:04d}-{month:02d}"
    try:
        # Current period: actual GL amounts per account (cost accounts 5*)
        actual_df = query_df(
            """
            SELECT
                CAST("G/L Account" AS VARCHAR) AS gl_account,
                MAX("G/L Account") AS gl_name,
                SUM("Net_Amount") AS actual
            FROM v_gl
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND CAST("G/L Account" AS VARCHAR) LIKE '5%'
            GROUP BY CAST("G/L Account" AS VARCHAR)
            ORDER BY gl_account
            """,
            ["1000", year, month],
        )

        # Baseline: prior year same month
        baseline_df = query_df(
            """
            SELECT
                CAST("G/L Account" AS VARCHAR) AS gl_account,
                SUM("Net_Amount") AS baseline
            FROM v_gl
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND CAST("G/L Account" AS VARCHAR) LIKE '5%'
            GROUP BY CAST("G/L Account" AS VARCHAR)
            """,
            ["1000", year - 1, month],
        )

        # Merge on gl_account
        baseline_map = {}
        for _, row in baseline_df.iterrows():
            baseline_map[str(row["gl_account"])] = _safe_float(row["baseline"])

        categories = []
        for _, row in actual_df.iterrows():
            gl_acct   = str(row["gl_account"])
            gl_name   = str(row.get("gl_name", gl_acct))
            actual    = _safe_float(row["actual"])
            baseline  = baseline_map.get(gl_acct, 0.0)
            variance  = round(actual - baseline, 2)
            var_pct   = round(variance / baseline * 100, 2) if baseline != 0 else None

            if var_pct is not None and var_pct > 5.0:
                flag = "over"
            elif var_pct is not None and var_pct < -5.0:
                flag = "under"
            else:
                flag = "ok"

            categories.append({
                "glAccount":   gl_acct,
                "glName":      gl_name,
                "actual":      round(actual, 2),
                "baseline":    round(baseline, 2),
                "variance":    variance,
                "variancePct": var_pct,
                "flag":        flag,
            })

        return {"period": period, "categories": categories}

    except Exception:
        return {"period": period, "categories": [], "usingMock": True}


@router.get("/treasury")
def get_treasury(asOf: str = Query(..., description="Snapshot date: YYYY-MM-DD")):
    """
    Cash + AR + AP + NWC runway snapshot for Treasury page.

    Cash    ← v_gl accounts 11* (YTD cumulative, company 1000)
    AR      ← v_gl accounts 12* (YTD cumulative, company 1000)
    AP      ← v_gl accounts 21* (YTD cumulative, company 1000)
    NWC     = AR + Cash - AP
    Runway  = NWC / (monthly opex estimate from v_gl_summary)
    trend6m = last 6 months cash balances
    """
    try:
        d = _parse_date(asOf)
        year, month = d.year, d.month

        # Probe query to detect DB availability — raises if DuckDB offline.
        # This allows the outer except to catch it and return usingMock=True.
        probe_df = query_df(
            """
            SELECT SUM("Net_Amount") AS balance
            FROM v_gl
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND CAST("G/L Account" AS VARCHAR) LIKE ?
            """,
            ["1000", year, month, "11%"],
        )
        cash_display = abs(_safe_float(probe_df.iloc[0]["balance"]) if not probe_df.empty else 0.0)

        # AR (GL 12*, debit positive)
        ar = abs(_gl_balance(year, month, "12", ytd=True))

        # AP (GL 21*, credit negative → abs)
        ap = abs(_gl_balance(year, month, "21", ytd=True))

        # NWC = AR + Cash - AP
        nwc = ar + cash_display - ap

        # Opex estimate for runway (last month's opex from v_gl_summary)
        opex_monthly = _gl_summary_amount(year, month, ["6. Selling Exp", "7. Admin Exp"])
        nwc_runway = round(nwc / opex_monthly, 1) if opex_monthly > 0 else None

        # 6-month cash trend (current month + 5 prior months)
        trend6m = []
        y, m = year, month
        for _ in range(6):
            bal = abs(_gl_balance(y, m, "11", ytd=True))
            trend6m.append({"month": f"{y:04d}-{m:02d}", "balance": round(bal, 2)})
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        trend6m.reverse()   # oldest → newest

        # AR overdue >60 days
        ar_overdue = _ar_overdue_gt60(year)

        return {
            "asOf": asOf,
            "cash": {
                "balance":  round(cash_display, 2),
                "trend6m":  trend6m,
            },
            "ar": {
                "balance":    round(ar, 2),
                "overdueGt60": ar_overdue if ar_overdue > 0 else None,
            },
            "ap": {
                "balance": round(ap, 2),
            },
            "nwc":       round(nwc, 2),
            "nwcRunway": nwc_runway,
        }

    except Exception:
        return {"asOf": asOf, "cash": {}, "ar": {}, "ap": {}, "nwcRunway": None, "usingMock": True}
