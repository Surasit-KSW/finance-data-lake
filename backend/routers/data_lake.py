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

def _norm_cols(df):
    """Lowercase all column names except 'G/L Account' (contains slash)."""
    df.columns = [c.lower() if c != "G/L Account" else c for c in df.columns]
    return df


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

    Single batch query for each year — avoids 60 round-trips on cloud (Neon).
    Revenue  ← GL_Group = '4. Revenue' (negated — SAP credit convention)
    COGS     ← GL_Group = '5. COGS'
    Opex     ← GL_Group IN ('6. Selling Exp', '7. Admin Exp')
    Prior Yr ← same single query with year-1

    Cloud-compatible: v_gl_summary available on both DuckDB and Neon.
    Future months (month > today for current year) → all numeric fields null.
    """
    try:
        query_df("SELECT 1", [])
        today = date.today()

        # ── Single query for current year ────────────────────────────────────
        batch_sql = """
            SELECT
                month,
                gl_group,
                SUM(net_amount) AS total
            FROM v_gl_summary
            WHERE year = ?
              AND gl_group IN ('4. Revenue', '5. COGS', '6. Selling Exp', '7. Admin Exp')
            GROUP BY month, gl_group
            ORDER BY month
        """
        cur_df  = _norm_cols(query_df(batch_sql, [year]))
        py_df   = _norm_cols(query_df(batch_sql, [year - 1]))

        # Build lookup: (month, gl_group) → sum
        def _build_map(df):
            m = {}
            for _, row in df.iterrows():
                key = (int(row["month"]), str(row["gl_group"]))
                m[key] = _safe_float(row["total"])
            return m

        cur_map = _build_map(cur_df)
        py_map  = _build_map(py_df)

        def _get(lookup, month, group):
            return lookup.get((month, group), 0.0)

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
                revenue  = abs(_get(cur_map, month, "4. Revenue"))   # negate SAP credit
                cogs     = _get(cur_map, month, "5. COGS")
                opex     = (_get(cur_map, month, "6. Selling Exp")
                           + _get(cur_map, month, "7. Admin Exp"))

                py_revenue = abs(_get(py_map, month, "4. Revenue"))
                py_cogs    = _get(py_map, month, "5. COGS")

                gp    = revenue - cogs
                py_gp = py_revenue - py_cogs

                months_out.append({
                    "month":       month,
                    "revenue":     round(revenue, 2),
                    "cogs":        round(cogs, 2),
                    "grossProfit": round(gp, 2),
                    "gpMargin":    round(gp / revenue * 100, 2) if revenue > 0 else None,
                    "opex":        round(opex, 2),
                    "ebit":        round(gp - opex, 2),
                    "priorYear": {
                        "revenue":  round(py_revenue, 2),
                        "gpMargin": round(py_gp / py_revenue * 100, 2) if py_revenue > 0 else None,
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
        actual_df = _norm_cols(query_df(
            """
            SELECT
                "G/L Account"              AS gl_account,
                MAX(gl_name)               AS gl_name,
                SUM(net_amount)            AS actual
            FROM v_gl_summary
            WHERE year = ?
              AND month = ?
              AND gl_group = '5. COGS'
            GROUP BY "G/L Account"
            ORDER BY SUM(net_amount) DESC
            """,
            [year, month],
        ))

        baseline_df = _norm_cols(query_df(
            """
            SELECT
                "G/L Account"              AS gl_account,
                SUM(net_amount)            AS baseline
            FROM v_gl_summary
            WHERE year = ?
              AND month = ?
              AND gl_group = '5. COGS'
            GROUP BY "G/L Account"
            """,
            [year - 1, month],
        ))

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

        # ── Batch query 1: balance sheet accounts (11/12/21/22) by month ────
        # One query replaces 10+ individual prefix calls.
        bs_df = _norm_cols(query_df(
            """
            SELECT
                SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) AS prefix,
                month,
                SUM(net_amount) AS monthly
            FROM v_gl_summary
            WHERE year = ?
              AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) IN ('11','12','21','22')
            GROUP BY prefix, month
            ORDER BY prefix, month
            """,
            [year],
        ))

        # Build prefix → {month: monthly_amount} lookup
        prefix_monthly: dict = {}
        for _, row in bs_df.iterrows():
            pfx = str(row["prefix"])
            mo  = int(row["month"])
            prefix_monthly.setdefault(pfx, {})[mo] = _safe_float(row["monthly"])

        def _ytd(prefix: str, up_to_month: int) -> float:
            return sum(
                prefix_monthly.get(prefix, {}).get(m, 0.0)
                for m in range(1, up_to_month + 1)
            )

        # ── Batch query 2: P&L groups for current month ─────────────────────
        pl_df = _norm_cols(query_df(
            """
            SELECT gl_group, SUM(net_amount) AS total
            FROM v_gl_summary
            WHERE year = ?
              AND month = ?
              AND gl_group IN ('4. Revenue', '5. COGS', '6. Selling Exp', '7. Admin Exp')
            GROUP BY gl_group
            """,
            [year, month],
        ))
        pl_map = {str(row["gl_group"]): _safe_float(row["total"]) for _, row in pl_df.iterrows()}

        # ── Derived balances ─────────────────────────────────────────────────
        cash = abs(_ytd("11", month))
        ar   = abs(_ytd("12", month))
        ap   = abs(_ytd("21", month)) + abs(_ytd("22", month))
        nwc  = ar + cash - ap

        opex_monthly = (pl_map.get("6. Selling Exp", 0.0) + pl_map.get("7. Admin Exp", 0.0))
        nwc_runway   = round(nwc / opex_monthly, 1) if opex_monthly > 0 else None

        revenue_mtd  = abs(pl_map.get("4. Revenue", 0.0))
        daily_sales  = revenue_mtd / fiscal_day if fiscal_day > 0 and revenue_mtd > 0 else None
        dso          = round(ar / daily_sales, 1) if daily_sales else None

        cogs_mtd    = abs(pl_map.get("5. COGS", 0.0))
        daily_cogs  = cogs_mtd / fiscal_day if fiscal_day > 0 and cogs_mtd > 0 else None
        dpo         = round(ap / daily_cogs, 1) if daily_cogs else None

        # ── 6-month cash trend (no extra queries — use prefix_monthly) ───────
        trend6m = []
        y, m = year, month
        for _ in range(6):
            # YTD cash balance for month m in year y
            if y == year:
                bal = abs(_ytd("11", m))
            else:
                # Need prior-year data — fall back to point-in-time query
                bal_df = query_df(
                    """
                    SELECT SUM(net_amount) AS balance FROM v_gl_summary
                    WHERE year = ? AND month <= ?
                      AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) = '11'
                    """,
                    [y, m],
                )
                bal = abs(_safe_float(bal_df.iloc[0]["balance"])) if not bal_df.empty else 0.0
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
