"""
routers/data_lake.py
====================
Finance Data Lake — FP&A + Treasury endpoints.
Dual-mode: local DuckDB (v_gl / v_sales) or cloud Neon (v_gl_summary only).

Cloud-compatible: all queries fall back to v_gl_summary when v_gl / v_sales
are not available (T2 aggregates only — no raw transactions in Neon).

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


def _gl_summary_amount(year: int, month: int, gl_group) -> float:
    """
    Sum net_amount from v_gl_summary for given gl_group(s) in a single month.
    gl_group may be a str or list[str].
    Works on both DuckDB and Neon (column names are lowercase in Neon).
    """
    try:
        if isinstance(gl_group, list):
            placeholders = ",".join("?" * len(gl_group))
            params = gl_group + [year, month]
            df = query_df(
                f"""
                SELECT SUM(net_amount) AS total
                FROM v_gl_summary
                WHERE gl_group IN ({placeholders})
                  AND year = ?
                  AND month = ?
                """,
                params,
            )
        else:
            df = query_df(
                """
                SELECT SUM(net_amount) AS total
                FROM v_gl_summary
                WHERE gl_group = ?
                  AND year = ?
                  AND month = ?
                """,
                [gl_group, year, month],
            )
        return _safe_float(df.iloc[0]["total"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _gl_summary_prefix(year: int, month: int, account_prefix: str, ytd: bool = True) -> float:
    """
    Sum net_amount from v_gl_summary for accounts matching account_prefix (first 2 chars).
    ytd=True  → cumulative Jan–month (balance sheet items).
    ytd=False → single month only.

    Replaces _gl_balance() which used v_gl T1 raw transactions.
    Works on both DuckDB (G/L Account stored as DOUBLE) and Neon (TEXT).
    CAST to VARCHAR is a no-op on Neon text but required on DuckDB float.
    """
    try:
        if ytd:
            df = query_df(
                """
                SELECT SUM(net_amount) AS balance
                FROM v_gl_summary
                WHERE year = ?
                  AND month <= ?
                  AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) = ?
                """,
                [year, month, account_prefix],
            )
        else:
            df = query_df(
                """
                SELECT SUM(net_amount) AS balance
                FROM v_gl_summary
                WHERE year = ?
                  AND month = ?
                  AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) = ?
                """,
                [year, month, account_prefix],
            )
        return _safe_float(df.iloc[0]["balance"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _revenue(year: int, month: int) -> float:
    """
    Revenue for a single month.
    SAP convention: Revenue (4.*) is credit → Net_Amount is NEGATIVE → negate for display.
    Uses v_gl_summary (cloud-compatible). Works on DuckDB and Neon.
    """
    raw = _gl_summary_amount(year, month, "4. Revenue")
    return abs(raw)   # flip credit sign → positive revenue figure


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/fpa-summary")
def get_fpa_summary(year: int = Query(2026)):
    """
    12-month Actual vs Prior Year P&L for FP&A page top section.

    Revenue  ← v_gl_summary GL_Group = '4. Revenue' (negated — SAP credit convention)
    COGS     ← v_gl_summary GL_Group = '5. COGS'
    Opex     ← v_gl_summary GL_Group IN ('6. Selling Exp', '7. Admin Exp')
    Prior Yr ← same queries with year-1

    Cloud-compatible: v_gl_summary available on both DuckDB and Neon.
    Future months (month > today for current year) → all numeric fields null.
    """
    try:
        query_df("SELECT 1", [])
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
                revenue      = _revenue(year, month)
                cogs         = _gl_summary_amount(year, month, "5. COGS")
                opex         = _gl_summary_amount(year, month, ["6. Selling Exp", "7. Admin Exp"])
                py_revenue   = _revenue(year - 1, month)
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
    except HTTPException:
        raise
    except Exception as e:
        return {"year": year, "months": [], "usingMock": True, "error": str(e)}


@router.get("/fpa-variance")
def get_fpa_variance(year: int = Query(2026), month: int = Query(7)):
    """
    GL-level cost variance vs prior-year same month for FP&A drill-down.

    Actual   ← v_gl_summary GROUP BY G/L Account, GL_Group LIKE '5.*' for year/month
    Baseline ← v_gl_summary same query for year-1/month
    Variance = actual - baseline
    Flag     = 'over' if variancePct > 5%, 'under' if < -5%, else 'ok'

    Cloud-compatible: uses v_gl_summary (Neon OK).
    """
    period = f"{year:04d}-{month:02d}"
    try:
        actual_df = query_df(
            """
            SELECT
                "G/L Account"              AS gl_account,
                MAX("GL_Name")             AS gl_name,
                SUM("Net_Amount")          AS actual
            FROM v_gl_summary
            WHERE CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND "GL_Group" = '5. COGS'
            GROUP BY "G/L Account"
            ORDER BY SUM("Net_Amount") DESC
            """,
            [year, month],
        )

        baseline_df = query_df(
            """
            SELECT
                "G/L Account"              AS gl_account,
                SUM("Net_Amount")          AS baseline
            FROM v_gl_summary
            WHERE CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND "GL_Group" = '5. COGS'
            GROUP BY "G/L Account"
            """,
            [year - 1, month],
        )

        baseline_map = {}
        for _, row in baseline_df.iterrows():
            baseline_map[str(row["gl_account"])] = _safe_float(row["baseline"])

        categories = []
        for _, row in actual_df.iterrows():
            gl_acct  = str(row["gl_account"])
            gl_name  = str(row.get("gl_name", gl_acct))
            actual   = _safe_float(row["actual"])
            baseline = baseline_map.get(gl_acct, 0.0)
            variance = round(actual - baseline, 2)
            var_pct  = round(variance / baseline * 100, 2) if baseline != 0 else None

            flag = "ok"
            if var_pct is not None and var_pct > 5.0:
                flag = "over"
            elif var_pct is not None and var_pct < -5.0:
                flag = "under"

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

    Cash  ← v_gl_summary accounts starting '11' (YTD cumulative)
    AR    ← v_gl_summary accounts starting '12' (YTD cumulative)
    AP    ← v_gl_summary accounts starting '21' + '22' (YTD cumulative)
    NWC   = AR + Cash - AP
    Runway= NWC / monthly opex

    Revenue for DSO ← v_gl_summary GL_Group = '4. Revenue' (negated)

    Cloud-compatible: all queries use v_gl_summary (Neon OK).
    AR overdue >60d not available in T2 aggregates — returns null.
    """
    try:
        d = _parse_date(asOf)
        year, month = d.year, d.month
        fiscal_day = d.day

        query_df("SELECT 1", [])

        # Cash (accounts 11*, YTD cumulative)
        cash = abs(_gl_summary_prefix(year, month, "11", ytd=True))

        # AR (accounts 12*, YTD cumulative)
        ar = abs(_gl_summary_prefix(year, month, "12", ytd=True))

        # AP (accounts 21* + 22*, YTD cumulative)
        ap = (
            abs(_gl_summary_prefix(year, month, "21", ytd=True))
            + abs(_gl_summary_prefix(year, month, "22", ytd=True))
        )

        # NWC = AR + Cash - AP
        nwc = ar + cash - ap

        # Monthly opex for burn rate / runway
        opex_monthly = _gl_summary_amount(year, month, ["6. Selling Exp", "7. Admin Exp"])
        nwc_runway = round(nwc / opex_monthly, 1) if opex_monthly > 0 else None

        # DSO = AR / daily sales
        revenue_mtd = _revenue(year, month)
        daily_sales = revenue_mtd / fiscal_day if fiscal_day > 0 and revenue_mtd > 0 else None
        dso = round(ar / daily_sales, 1) if daily_sales else None

        # DPO = AP / daily COGS
        cogs_mtd = abs(_gl_summary_amount(year, month, "5. COGS"))
        daily_cogs = cogs_mtd / fiscal_day if fiscal_day > 0 and cogs_mtd > 0 else None
        dpo = round(ap / daily_cogs, 1) if daily_cogs else None

        # 6-month cash trend
        trend6m = []
        y, m = year, month
        for _ in range(6):
            bal = abs(_gl_summary_prefix(y, m, "11", ytd=True))
            trend6m.append({"month": f"{y:04d}-{m:02d}", "balance": round(bal, 2)})
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        trend6m.reverse()

        return {
            "asOf": asOf,
            "cash": {
                "balance": round(cash, 2),
                "trend6m": trend6m,
            },
            "ar": {
                "total":    round(ar, 2),
                "overdue60": None,   # T2 aggregates only — aging detail not available in cloud
                "dso":      dso,
            },
            "ap": {
                "total":  round(ap, 2),
                "due30d": None,
                "dpo":    dpo,
            },
            "nwcRunway": {
                "netWorkingCapital": round(nwc, 2),
                "monthlyBurnRate":   round(opex_monthly, 2),
                "runwayMonths":      nwc_runway,
            },
            "usingMock": False,
        }

    except Exception:
        return {"asOf": asOf, "cash": {}, "ar": {}, "ap": {}, "nwcRunway": None, "usingMock": True}
