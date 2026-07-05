"""
routers/briefing.py
===================
Morning Briefing API — /api/v1/briefing/...

Consumers: fintech-command-center (Daily Briefing module)

Endpoints:
  GET /api/v1/briefing/cfo-kpis?asOf=YYYY-MM-DD
  GET /api/v1/briefing/finance-ops?asOf=YYYY-MM-DD
  GET /api/v1/briefing/alerts?date=YYYY-MM-DD

Data sources (what is available in DuckDB analytics layer):
  - gold_revenue_monthly : pre-aggregated revenue by plant/month
  - gold_gp_by_plant     : GP + margin by plant/month (company-pool COGS)
  - v_production         : production volume (MB52 actual GR qty in KG → /1000 = MT)
  - v_gl                 : GL transactions — AR (12*), AP (21*), cash/bank (11*)

SAP sign convention (v_gl):
  Revenue  (4.*)  → credit → Net_Amount NEGATIVE → flip for display
  Assets   (1.*)  → debit  → Net_Amount POSITIVE  (AR, cash)
  Liabilities (2.*) → credit → Net_Amount NEGATIVE (AP)
  Cost     (5.*)  → debit  → Net_Amount POSITIVE

Limitations / Phase 2 roadmap:
  - cashToday.change (Δ vs yesterday): monthly GL can't give daily delta → null
  - AR overdueGt60 / DSO: needs AR aging detail table → null in Phase 1
  - glStatus.errors / pendingApproval: SAP operational status, not in analytics → null
  - bankMatching: needs bank statement table → null
  - closeTasks: SAP workflow status → static template
  - Finance Calendar: static config (Phase 2: Google Calendar API)
"""
import calendar
import math
from datetime import date
from fastapi import APIRouter, Query, HTTPException
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/briefing", tags=["Briefing v1"])


# ─── Business Constants ────────────────────────────────────────────────────────
# Monthly targets — update when annual budget is confirmed

REVENUE_TARGET_MONTHLY = 285_000_000   # 285M THB / month
GM_TARGET_PCT          = 18.5          # gross margin % target
AR_WATCH_THRESHOLD     = 300_000_000   # AR above this → "watch"
AR_ALERT_THRESHOLD     = 400_000_000   # AR above this → "alert"
CASH_SAFE_THRESHOLD    = 50_000_000    # cash below this → "watch"

# Per-plant monthly production targets (MT/month)
# Derived from actual Q1 2026 averages: 1300~11K, 1100~8K, 1200~22K
# Update when annual budget is confirmed.
PLANT_MONTHLY_TARGET_MT: dict[str, float] = {
    "1300": 11_000.0,   # GI — Plant 1300
    "1100":  8_000.0,   # Pipe A1 — Plant 1100
    "1200": 22_000.0,   # Pipe A2 — Plant 1200
}

# Per-plant standard unit cost targets (THB/MT)
PLANT_UNIT_COST_TARGET: dict[str, float] = {
    "1300": 26_545.0,
    "1100": 31_780.0,
    "1200": 33_290.0,
}

# Cost-center prefix per plant (SAP 7-digit codes)
PLANT_CC_PREFIX: dict[str, str] = {
    "1300": "13",
    "1100": "11",
    "1200": "12",
}

ALL_PLANTS = ["1300", "1100", "1200"]

PLANT_LABELS: dict[str, str] = {
    "1300": "Plant 1300 — GI",
    "1100": "Plant 1100 — Pipe A1",
    "1200": "Plant 1200 — Pipe A2",
}

PLANT_PRODUCTS: dict[str, str] = {
    "1300": "GI (Galvanized Iron)",
    "1100": "Steel Pipe A1",
    "1200": "Steel Pipe A2 / C-Channel",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date '{s}'. Use YYYY-MM-DD.")


def _safe_float(val, default: float = 0.0) -> float:
    """Convert val to float, returning default for None / NaN / Inf."""
    try:
        v = float(val) if val is not None else default
        return default if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return default


def _query_revenue_mtd(year: int, month: int) -> float:
    """
    Total revenue THB for year/month.
    Primary: gold_revenue_monthly (local DuckDB, most accurate).
    Fallback: v_gl_summary gl_group='4. Revenue' (Neon/cloud-compatible).
    SAP convention: Revenue is credit → net_amount negative → abs().
    """
    try:
        df = query_df(
            "SELECT SUM(revenue_thb) AS total FROM gold_revenue_monthly WHERE year = ? AND month = ?",
            [year, month],
        )
        val = _safe_float(df.iloc[0]["total"]) if not df.empty else 0.0
        if val > 0:
            return val
    except Exception:
        pass
    # Fallback: v_gl_summary (cloud-compatible)
    try:
        df = query_df(
            """SELECT SUM(net_amount) AS total FROM v_gl_summary
               WHERE year = ? AND month = ? AND gl_group = '4. Revenue'""",
            [year, month],
        )
        val = _safe_float(df.iloc[0]["total"]) if not df.empty else 0.0
        return abs(val)   # credit → negative → flip for display
    except Exception:
        return 0.0


def _query_gp_mtd(year: int, month: int) -> dict:
    """
    GP amount + margin % for year/month.
    Primary: gold_gp_by_plant (local DuckDB).
    Fallback: v_gl_summary Revenue - COGS (Neon/cloud-compatible).
    """
    try:
        df = query_df(
            """
            SELECT SUM(revenue_thb) AS rev, SUM(gp_actual) AS gp
            FROM gold_gp_by_plant
            WHERE "Year" = ? AND "Month" = ?
            """,
            [year, month],
        )
        if not df.empty:
            rev = _safe_float(df.iloc[0]["rev"])
            gp  = _safe_float(df.iloc[0]["gp"])
            if rev > 0:
                margin = round(gp / rev * 100, 2)
                return {"rev": rev, "gp": gp, "margin": margin}
    except Exception:
        pass
    # Fallback: v_gl_summary (cloud-compatible)
    try:
        df = query_df(
            """
            SELECT gl_group, SUM(net_amount) AS total
            FROM v_gl_summary
            WHERE year = ? AND month = ?
              AND gl_group IN ('4. Revenue', '5. COGS')
            GROUP BY gl_group
            """,
            [year, month],
        )
        gl_map = {str(row["gl_group"]): _safe_float(row["total"]) for _, row in df.iterrows()}
        rev  = abs(gl_map.get("4. Revenue", 0.0))   # credit → flip
        cogs = gl_map.get("5. COGS", 0.0)
        gp   = rev - cogs
        margin = round(gp / rev * 100, 2) if rev > 0 else None
        return {"rev": rev, "gp": gp, "margin": margin}
    except Exception:
        return {"rev": 0.0, "gp": 0.0, "margin": None}


def _query_prod_volume_mtd(year: int, month: int, plant: str | None = None) -> float:
    """Total finished-goods production volume in MT for year/month."""
    conds = [
        'company_code = ?',
        'CAST("Year" AS INTEGER) = ?',
        'CAST("Month" AS INTEGER) = ?',
        '"Material" NOT LIKE \'20CRC%\'',   # exclude semi-finished CRC
    ]
    params: list = ["1000", year, month]
    if plant:
        conds.append('"Plant" = ?')
        params.append(plant)

    try:
        df = query_df(
            f"""
            SELECT SUM("GR_Qty") / 1000.0 AS total_mt
            FROM v_production
            WHERE {' AND '.join(conds)}
            """,
            params,
        )
        return round(_safe_float(df.iloc[0]["total_mt"]) if not df.empty else 0.0, 1)
    except Exception:
        return 0.0


def _query_gl_balance(year: int, month: int, account_prefix: str, ytd: bool = True) -> float:
    """
    Sum net_amount for accounts matching `account_prefix` (first 2 chars).
    ytd=True → cumulative Jan–month; ytd=False → single month only.
    Primary: v_gl T1 raw (local DuckDB).
    Fallback: v_gl_summary with SUBSTRING prefix (Neon/cloud-compatible).
    """
    # Primary: v_gl (local DuckDB raw transactions)
    month_cond = "CAST(Month AS INTEGER) <= ?" if ytd else "CAST(Month AS INTEGER) = ?"
    try:
        df = query_df(
            f"""
            SELECT SUM(net_amount) AS balance
            FROM v_gl
            WHERE company_code = ?
              AND CAST(Year AS INTEGER) = ?
              AND {month_cond}
              AND CAST("G/L Account" AS VARCHAR) LIKE ?
            """,
            ["1000", year, month, f"{account_prefix}%"],
        )
        val = _safe_float(df.iloc[0]["balance"]) if not df.empty else 0.0
        if val != 0.0:
            return val
    except Exception:
        pass
    # Fallback: v_gl_summary (Neon/cloud-compatible)
    prefix2 = account_prefix[:2]
    try:
        if ytd:
            df = query_df(
                """
                SELECT SUM(net_amount) AS balance
                FROM v_gl_summary
                WHERE year = ? AND month <= ?
                  AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) = ?
                """,
                [year, month, prefix2],
            )
        else:
            df = query_df(
                """
                SELECT SUM(net_amount) AS balance
                FROM v_gl_summary
                WHERE year = ? AND month = ?
                  AND SUBSTRING(CAST("G/L Account" AS VARCHAR) FROM 1 FOR 2) = ?
                """,
                [year, month, prefix2],
            )
        return _safe_float(df.iloc[0]["balance"]) if not df.empty else 0.0
    except Exception:
        return 0.0


def _query_gl_entry_count(year: int, month: int) -> int:
    """
    Count of GL entries for year/month.
    Primary: v_gl T1 raw (local DuckDB).
    Fallback: v_gl_summary row count (Neon/cloud-compatible).
    """
    try:
        df = query_df(
            "SELECT COUNT(*) AS cnt FROM v_gl WHERE company_code = ? AND CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) = ?",
            ["1000", year, month],
        )
        val = int(_safe_float(df.iloc[0]["cnt"])) if not df.empty else 0
        if val > 0:
            return val
    except Exception:
        pass
    # Fallback: v_gl_summary (Neon/cloud-compatible)
    try:
        df = query_df(
            "SELECT COUNT(*) AS cnt FROM v_gl_summary WHERE year = ? AND month = ?",
            [year, month],
        )
        return int(_safe_float(df.iloc[0]["cnt"])) if not df.empty else 0
    except Exception:
        return 0


def _query_ar_overdue_gt60(year: int) -> float:
    """
    Sum open AR items overdue > 60 days from v_ar (FBL5N data).

    v_ar columns:
      "Company Code Currency Value" — open amount in THB
      "Days 1"                      — days outstanding (positive = overdue, BIGINT)
      "Fiscal Year"                 — fiscal year (BIGINT)
      company_code                  — company filter

    Note: brief specified "Year" column but actual v_ar schema uses "Fiscal Year".

    Returns 0.0 if v_ar has no data or query fails.
    """
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


def _compute_dso(ar_balance: float, revenue_mtd: float, fiscal_day: int) -> float | None:
    """
    Simple DSO = AR balance / (annualised daily revenue).

    Uses revenue_mtd / fiscal_day as proxy for daily revenue rate.
    Returns None when revenue_mtd is 0 (avoid division by zero).
    """
    if revenue_mtd <= 0 or fiscal_day <= 0:
        return None
    daily_revenue = revenue_mtd / fiscal_day
    if daily_revenue <= 0:
        return None
    return round(ar_balance / daily_revenue, 1)


def _resolve_data_month(year: int, month: int) -> tuple[int, int]:
    """
    Return the latest (year, month) that has actual revenue data.
    Walks back up to 6 months to find the most recent month with data.
    Prevents endpoints from returning usingMock=True just because the current
    calendar month hasn't been loaded yet (e.g., July 4 but June is latest).

    Priority: v_gl_summary (more up-to-date, Neon/cloud-compatible)
              then gold_revenue_monthly (local DuckDB enrichment).
    """
    for m_offset in range(7):
        y, m = year, month - m_offset
        while m <= 0:
            m += 12
            y -= 1
        # Check v_gl_summary first — available on both DuckDB and Neon, more recent data
        try:
            df = query_df(
                "SELECT COUNT(*) AS cnt FROM v_gl_summary WHERE year = ? AND month = ? AND gl_group = '4. Revenue'",
                [y, m],
            )
            if not df.empty and int(_safe_float(df.iloc[0]["cnt"])) > 0:
                return y, m
        except Exception:
            pass
        # Also try gold_revenue_monthly (local DuckDB)
        try:
            df = query_df(
                "SELECT COUNT(*) AS cnt FROM gold_revenue_monthly WHERE year = ? AND month = ?",
                [y, m],
            )
            if not df.empty and int(_safe_float(df.iloc[0]["cnt"])) > 0:
                return y, m
        except Exception:
            pass
    return year, month  # fallback: caller will get 0s and handle accordingly


def _query_plant_unit_costs(year: int, month: int) -> dict[str, dict]:
    """
    Compute per-plant unit cost (THB/MT) from v_production Actual GR Amount.

    Note: "Actual GR Amount" = SAP standard cost at time of production order GR.
    This gives a per-plant standard unit cost snapshot; actual cost (with ML variance)
    is available only after period-end cost closing.
    Returns {plant: {volume_mt, total_cost, unit_cost}}.
    """
    try:
        df = query_df(
            """
            SELECT
                "Plant"                              AS plant,
                SUM("GR_Qty")  / 1000.0      AS vol_mt,
                SUM("Actual GR Amount")              AS total_cost
            FROM v_production
            WHERE company_code = ?
              AND CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) = ?
              AND "Material" NOT LIKE '20CRC%'
            GROUP BY "Plant"
            """,
            ["1000", year, month],
        )
    except Exception:
        return {}

    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        plant     = str(row["plant"]).replace(".0", "")
        vol       = _safe_float(row["vol_mt"])
        total     = _safe_float(row["total_cost"])
        if vol <= 0 or total <= 0:
            continue
        result[plant] = {
            "volume_mt":  round(vol, 1),
            "total_cost": round(total, 2),
            "unit_cost":  round(total / vol, 2),
        }

    return result


def _query_prod_trend(year: int, month: int, n_months: int = 6) -> list[dict]:
    """
    Return per-plant unit cost for the last n_months months ending at year/month.
    Each entry: {"month": "YYYY-MM", "plant": str, "unit_cost": float}

    Builds the trend by calling _query_plant_unit_costs for each month window.
    Cheaper than a self-join; n_months is small (6).
    """
    results = []
    y, m = year, month
    for _ in range(n_months):
        costs = _query_plant_unit_costs(y, m)
        for plant, data in costs.items():
            results.append({
                "month":     f"{y:04d}-{m:02d}",
                "plant":     plant,
                "unit_cost": data["unit_cost"],
            })
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return results


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/cfo-kpis")
def get_cfo_kpis(asOf: str = Query(..., description="Snapshot date: YYYY-MM-DD")):
    """
    CFO-level KPI snapshot for Morning Briefing Section 1.

    Live data:
      - Revenue MTD      ← gold_revenue_monthly
      - Gross Margin %   ← gold_gp_by_plant
      - EBITDA run-rate  ← GP × 12 (approximation; D&A not split in current GL mapping)
      - Production Vol   ← v_production (finished goods, all plants)
      - AR Outstanding   ← v_gl accounts 12* (YTD cumulative)
      - Cash Today       ← v_gl accounts 11* (YTD cumulative)

    Null fields (Phase 2):
      - cashToday.change  (Δ vs yesterday — needs daily GL snapshot)
      - arOutstanding.overdueGt60, dso  (needs AR aging detail table)
    """
    d = _parse_date(asOf)
    req_year, req_month = d.year, d.month

    # Resolve to latest month with actual data (handles "today is Jul 4 but data is Jun")
    year, month = _resolve_data_month(req_year, req_month)
    data_as_of  = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"

    fiscal_day    = d.day if (year == req_year and month == req_month) else calendar.monthrange(year, month)[1]
    days_in_month = calendar.monthrange(year, month)[1]

    # Revenue MTD
    revenue_mtd    = _query_revenue_mtd(year, month)
    rev_pct        = round(revenue_mtd / REVENUE_TARGET_MONTHLY * 100, 1) if REVENUE_TARGET_MONTHLY > 0 else 0.0
    pace_pct       = round(fiscal_day / days_in_month * 100, 1)
    rev_trend      = "up" if rev_pct >= pace_pct else "down"

    # GP / Gross Margin
    gp_data        = _query_gp_mtd(year, month)
    gm_pct         = gp_data["margin"]
    gm_delta       = round(gm_pct - GM_TARGET_PCT, 2) if gm_pct is not None else None
    gm_trend       = "up" if (gm_pct or 0) >= GM_TARGET_PCT else "down"

    # EBITDA run-rate (annual basis: current month GP × 12)
    gp_month       = gp_data["gp"]
    ebitda_rr      = round(gp_month * 12, 2) if gp_month > 0 else None
    ebitda_target  = round(REVENUE_TARGET_MONTHLY * 12 * (GM_TARGET_PCT / 100), 2)
    ebitda_pct     = round(ebitda_rr / ebitda_target * 100, 1) if (ebitda_rr and ebitda_target) else None

    # Production Volume MTD
    prod_target    = round(sum(PLANT_MONTHLY_TARGET_MT.values()), 1)   # 41,000 MT/month
    prod_vol       = _query_prod_volume_mtd(year, month)
    prod_pct       = round(prod_vol / prod_target * 100, 1) if prod_target > 0 else 0.0
    prod_trend     = "up" if prod_pct >= pace_pct else "down" if prod_pct < pace_pct - 5 else "neutral"

    # AR Outstanding (GL 12*, YTD cumulative, debit = positive)
    ar_balance     = abs(_query_gl_balance(year, month, "12", ytd=True))
    ar_status      = ("alert" if ar_balance >= AR_ALERT_THRESHOLD
                      else "watch" if ar_balance >= AR_WATCH_THRESHOLD
                      else "safe")

    # Cash Today (GL 11*, YTD cumulative, debit = positive)
    cash_balance   = _query_gl_balance(year, month, "11", ytd=True)
    # Cash accounts can net to negative if payments exceeded receipts
    cash_display   = abs(cash_balance)
    cash_status    = "safe" if cash_display >= CASH_SAFE_THRESHOLD else "watch"

    # AR Overdue >60 days (v_ar FBL5N data)
    ar_overdue_gt60 = _query_ar_overdue_gt60(year)
    ar_dso          = _compute_dso(ar_balance, revenue_mtd, fiscal_day)

    has_live_data  = revenue_mtd > 0 or prod_vol > 0

    return {
        "status":       "ok",
        "asOf":         asOf,
        "dataAsOf":     data_as_of,        # actual data period used (may be prior month)
        "fiscalDay":    fiscal_day,
        "daysInMonth":  days_in_month,
        "usingMock":    not has_live_data,

        "cashToday": {
            "value":   round(cash_display, 2),
            "change":  None,          # Δ vs yesterday: needs daily snapshot (Phase 2)
            "vs":      "YTD GL balance",
            "status":  cash_status,
            "linkTo":  "/finance/treasury",
        },
        "revenueMtd": {
            "value":       round(revenue_mtd, 2),
            "target":      REVENUE_TARGET_MONTHLY,
            "pctOfTarget": rev_pct,
            "trend":       rev_trend,
            "linkTo":      "/finance/performance",
        },
        "grossMargin": {
            "value":  gm_pct,
            "target": GM_TARGET_PCT,
            "delta":  gm_delta,
            "trend":  gm_trend,
            "linkTo": "/finance/performance",
        },
        "ebitdaRunRate": {
            "value":       ebitda_rr,
            "target":      ebitda_target,
            "pctOfTarget": ebitda_pct,
            "trend":       "up" if (ebitda_rr or 0) >= ebitda_target else "down",
            "note":        "Approx GP × 12 — D&A not split in current GL mapping",
            "linkTo":      "/finance/performance",
        },
        "arOutstanding": {
            "value":       round(ar_balance, 2),
            "overdueGt60": ar_overdue_gt60 if ar_overdue_gt60 > 0 else None,
            "dso":         ar_dso,
            "status":      ar_status,
            "linkTo":      "/finance/working-capital",
        },
        "productionVolumeMtd": {
            "value":       prod_vol,
            "target":      prod_target,
            "pctOfTarget": prod_pct,
            "unit":        "MT",
            "trend":       prod_trend,
            "linkTo":      "/monitor/overview",
        },
    }


@router.get("/finance-ops")
def get_finance_ops(asOf: str = Query(..., description="Snapshot date: YYYY-MM-DD")):
    """
    Finance Operations daily status for Morning Briefing Section 2.

    Live data (from analytics DuckDB):
      - glStatus.totalEntries  ← COUNT(*) from v_gl for the month
      - glStatus.posted        ← same (v_gl only contains posted entries)
      - apOutstanding.value    ← v_gl accounts 21* (YTD cumulative)
      - monthEndClose.progressPct ← estimated from day-of-month

    Null fields (needs live SAP connection — Phase 2):
      - glStatus.errors, pendingApproval (SAP workflow status)
      - sapReconciliation fields
      - bankMatching fields
      - apOutstanding.overdueCount, dueTodayCount, dueTodayValue
      - closeTasks (SAP process statuses)
    """
    d = _parse_date(asOf)
    req_year, req_month = d.year, d.month
    year, month   = _resolve_data_month(req_year, req_month)
    fiscal_day    = d.day if (year == req_year and month == req_month) else calendar.monthrange(year, month)[1]
    days_in_month = calendar.monthrange(year, month)[1]

    # Month-end close progress: estimate from fiscal day
    # Days 1-10  → data collection phase    ~20-40%
    # Days 11-20 → posting + review phase   ~40-70%
    # Days 21-25 → close activities         ~70-90%
    # Days 26+   → final close              ~90-100%
    if fiscal_day <= 10:
        close_pct  = round(15 + (fiscal_day / 10) * 25, 0)   # 15–40%
    elif fiscal_day <= 20:
        close_pct  = round(40 + ((fiscal_day - 10) / 10) * 30, 0)   # 40–70%
    elif fiscal_day <= 25:
        close_pct  = round(70 + ((fiscal_day - 20) / 5) * 20, 0)    # 70–90%
    else:
        close_pct  = round(90 + ((fiscal_day - 25) / (days_in_month - 25 or 1)) * 10, 0)
    close_pct  = min(100, int(close_pct))
    days_left  = days_in_month - fiscal_day

    close_status = ("done" if close_pct >= 100
                    else "in-progress" if close_pct >= 40
                    else "pending")

    # GL entry count for the month (all accounts)
    gl_count   = _query_gl_entry_count(year, month)
    # All entries in v_gl are "posted" (analytics layer only stores successful postings)
    gl_posted  = gl_count

    # AP Outstanding (GL 21*, YTD cumulative, credit = negative → abs)
    ap_balance = abs(_query_gl_balance(year, month, "21", ytd=True))
    ap_status  = "watch" if ap_balance > 200_000_000 else "safe"

    has_live_data = gl_count > 0

    return {
        "status":    "ok",
        "asOf":      asOf,
        "usingMock": not has_live_data,

        "monthEndClose": {
            "progressPct": close_pct,
            "daysLeft":    days_left,
            "status":      close_status,
        },

        "glStatus": {
            "totalEntries":    gl_count,
            "posted":          gl_posted,
            "pendingApproval": None,   # SAP workflow — not in analytics DB
            "errors":          None,   # SAP error log — not in analytics DB
            "sapLastSync":     None,   # ETL run timestamp — not tracked here
            "linkTo":          "/monitor/ledger",
        },

        # SAP recon + bank matching: need live SAP / bank data (Phase 2)
        "sapReconciliation": {
            "matchedPct":   None,
            "openItems":    None,
            "criticalItems": None,
            "lastRun":      None,
            "status":       None,
            "linkTo":       "/monitor/overview",
        },

        "bankMatching": {
            "matchedPct":        None,
            "unmatchedCount":    None,
            "totalTransactions": None,
            "status":            None,
            "linkTo":            "/finance/liquidity",
        },

        "apOutstanding": {
            "value":         round(ap_balance, 2),
            "overdueCount":  None,   # needs AP aging (Phase 2)
            "dueTodayCount": None,
            "dueTodayValue": None,
            "status":        ap_status,
            "linkTo":        "/finance/working-capital",
        },

        # Close task statuses require live SAP connection — return empty for now
        # Phase 2: wire to SAP process monitoring or a dedicated task-tracking table
        "closeTasks": [],
    }


@router.get("/alerts")
def get_alerts(date_param: str = Query(..., alias="date", description="Alert date: YYYY-MM-DD")):
    """
    Auto-generated daily alerts from threshold rules on analytics data.

    Alert sources:
      - Production cost deviation (unit cost vs standard)  ← v_gl + v_production
      - Zero production volume with GL costs present       ← v_production
      - Negative GP margin per plant                       ← gold_gp_by_plant
      - High AR balance                                    ← v_gl accounts 12*

    Severity: critical > warning > info
    Returns: { alerts: AlertItem[] }
    """
    d = _parse_date(date_param)
    year, month = d.year, d.month

    alerts: list[dict] = []
    alert_id = 1

    # ── 1. Production cost deviation per plant ───────────────────────────────
    try:
        unit_costs = _query_plant_unit_costs(year, month)
        for plant, data in unit_costs.items():
            target = PLANT_UNIT_COST_TARGET.get(plant)
            if target is None:
                continue
            uc     = data["unit_cost"]
            delta  = uc - target
            pct    = round(delta / target * 100, 1)
            label  = PLANT_LABELS.get(plant, f"Plant {plant}")

            if abs(pct) < 1.0:
                continue   # within ±1% — no alert

            severity = "critical" if pct > 5.0 else "warning" if pct > 2.0 else "info"
            direction = "above" if delta > 0 else "below"

            alerts.append({
                "id":          f"prod-cost-{plant}-{alert_id}",
                "severity":    severity,
                "category":    "Production",
                "message":     (
                    f"{label}: Unit cost {direction} standard by {abs(pct):.1f}% "
                    f"(฿{uc:,.0f} vs target ฿{target:,.0f}/MT)"
                ),
                "actionLabel": "Cost Monitor",
                "actionTo":    "/monitor/overview",
                "timestamp":   f"{date_param}T06:00:00+07:00",
            })
            alert_id += 1
    except Exception:
        pass

    # ── 2. Zero production volume with GL costs → SAP posting lag ────────────
    try:
        for plant in ALL_PLANTS:
            volume = _query_prod_volume_mtd(year, month, plant)
            if volume > 0:
                continue

            # Check if there are any GL cost entries for this plant
            cc_prefix = PLANT_CC_PREFIX.get(plant)
            conds = [
                "company_code = ?",
                "CAST(Year AS INTEGER) = ?",
                "CAST(Month AS INTEGER) = ?",
                "CAST(\"G/L Account\" AS VARCHAR) LIKE '5%'",
            ]
            params: list = ["1000", year, month]
            if cc_prefix:
                conds.append("CAST(\"Cost Center\" AS VARCHAR) LIKE ?")
                params.append(f"{cc_prefix}%")

            try:
                df = query_df(
                    f"SELECT SUM(net_amount) AS total FROM v_gl WHERE {' AND '.join(conds)}",
                    params,
                )
                gl_cost = _safe_float(df.iloc[0]["total"]) if not df.empty else 0.0
            except Exception:
                gl_cost = 0.0

            if gl_cost > 0:
                label = PLANT_LABELS.get(plant, f"Plant {plant}")
                alerts.append({
                    "id":          f"prod-zero-{plant}-{alert_id}",
                    "severity":    "warning",
                    "category":    "Production",
                    "message":     (
                        f"{label}: GL cost ฿{gl_cost/1e6:.1f}M recorded "
                        f"but no production volume in MB52 — SAP GR pending?"
                    ),
                    "actionLabel": "Cost Monitor",
                    "actionTo":    "/monitor/overview",
                    "timestamp":   f"{date_param}T06:00:00+07:00",
                })
                alert_id += 1
    except Exception:
        pass

    # ── 3. Negative GP margin per plant ──────────────────────────────────────
    try:
        gp_df = query_df(
            """
            SELECT
                "Plant"              AS plant,
                SUM(revenue_thb)     AS rev,
                SUM(gp_actual)       AS gp
            FROM gold_gp_by_plant
            WHERE "Year" = ? AND "Month" = ?
            GROUP BY "Plant"
            """,
            [year, month],
        )
        for _, row in gp_df.iterrows():
            rev = _safe_float(row["rev"])
            gp  = _safe_float(row["gp"])
            if rev <= 0:
                continue
            margin = gp / rev * 100
            if margin >= 0:
                continue
            plant_code = str(row["plant"]).replace(".0", "")
            label = PLANT_LABELS.get(plant_code, f"Plant {plant_code}")
            alerts.append({
                "id":          f"gp-neg-{plant_code}-{alert_id}",
                "severity":    "critical",
                "category":    "Finance",
                "message":     (
                    f"{label}: GP margin ติดลบ ({margin:.1f}%) "
                    f"— ตรวจสอบ cost allocation และ revenue posting"
                ),
                "actionLabel": "P&L Summary",
                "actionTo":    "/monitor/pnl-summary",
                "timestamp":   f"{date_param}T06:00:00+07:00",
            })
            alert_id += 1
    except Exception:
        pass

    # ── 4. High AR balance ────────────────────────────────────────────────────
    try:
        ar_balance = abs(_query_gl_balance(year, month, "12", ytd=True))
        if ar_balance >= AR_WATCH_THRESHOLD:
            severity = "critical" if ar_balance >= AR_ALERT_THRESHOLD else "warning"
            pct_of_rev = round(ar_balance / max(_query_revenue_mtd(year, month), 1) * 100, 1)
            alerts.append({
                "id":          f"ar-high-{alert_id}",
                "severity":    severity,
                "category":    "AR",
                "message":     (
                    f"AR outstanding ฿{ar_balance/1e6:.1f}M "
                    f"({pct_of_rev:.1f}% of MTD revenue) — ติดตาม collection"
                ),
                "actionLabel": "Working Capital",
                "actionTo":    "/finance/working-capital",
                "timestamp":   f"{date_param}T08:00:00+07:00",
            })
            alert_id += 1
    except Exception:
        pass

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a.get("severity", "info"), 3))

    return {
        "status": "ok",
        "date":   date_param,
        "count":  len(alerts),
        "alerts": alerts,
    }


@router.get("/production-pulse")
def get_production_pulse(asOf: str = Query(..., description="Snapshot date: YYYY-MM-DD")):
    """
    Per-plant production KPI snapshot for Morning Briefing Section 4.

    Returns current-month volume + unit cost + 6-month cost sparkline per plant.
    Data source: v_production (Silver layer, monthly MB52 data).

    Status rules:
      critical  — unitCostDelta > 1500 THB/MT  OR  volume < 90% of target
      watch     — unitCostDelta > 500  THB/MT  OR  volume < 97% of target
      on-track  — otherwise
    """
    d = _parse_date(asOf)
    req_year, req_month = d.year, d.month
    year, month = _resolve_data_month(req_year, req_month)

    # Current month per-plant data
    current_costs = _query_plant_unit_costs(year, month)

    # 6-month trend (current month + 5 prior months)
    trend_raw = _query_prod_trend(year, month, n_months=6)

    # Group trend by plant: {plant: [{month, cost}, ...]} sorted oldest → newest
    trend_by_plant: dict[str, list[dict]] = {}
    for entry in trend_raw:
        p = entry["plant"]
        trend_by_plant.setdefault(p, []).append({
            "month": entry["month"],
            "cost":  entry["unit_cost"],
        })
    for p in trend_by_plant:
        trend_by_plant[p].sort(key=lambda x: x["month"])

    plants_out = []
    for plant in ALL_PLANTS:
        data       = current_costs.get(plant, {})
        vol_mt     = data.get("volume_mt", 0.0)
        unit_cost  = data.get("unit_cost", 0.0)
        cost_target = PLANT_UNIT_COST_TARGET.get(plant, 0.0)
        vol_target  = PLANT_MONTHLY_TARGET_MT.get(plant, 0.0)
        cost_delta  = round(unit_cost - cost_target, 2) if unit_cost > 0 else 0.0
        pct_vol     = round(vol_mt / vol_target * 100, 1) if vol_target > 0 else 0.0

        if cost_delta > 1_500 or (vol_mt > 0 and pct_vol < 90):
            status = "critical"
        elif cost_delta > 500 or (vol_mt > 0 and pct_vol < 97):
            status = "watch"
        else:
            status = "on-track"

        plants_out.append({
            "id":             plant,
            "label":          PLANT_LABELS.get(plant, f"Plant {plant}"),
            "product":        PLANT_PRODUCTS.get(plant, ""),
            "todayVolume":    vol_mt,
            "targetVolume":   vol_target,
            "pctOfTarget":    pct_vol,
            "unit":           "MT",
            "unitCostToday":  unit_cost,
            "unitCostTarget": cost_target,
            "unitCostDelta":  cost_delta,
            "status":         status,
            "costTrend":      trend_by_plant.get(plant, []),
            "linkTo":         "/monitor/overview",
        })

    return {
        "status": "ok",
        "date":   asOf,
        "plants": plants_out,
    }


@router.get("/all")
def get_all_briefing(asOf: str = Query(..., description="Snapshot date: YYYY-MM-DD")):
    """
    Composite Morning Briefing endpoint — returns all 4 sections in one request.

    Runs all 4 handlers in parallel threads so total latency ≈ max(handler_time),
    not sum(handler_time). Reduces total time from ~22s (4 serialised requests) to
    ~10-12s (single request, 4 parallel threads).

    Returns: { cfoKpis, financeOps, alerts, productionPulse }
    Each section mirrors its individual endpoint response exactly.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sections = {
        "cfoKpis":         (get_cfo_kpis,         asOf),
        "financeOps":      (get_finance_ops,       asOf),
        "alerts":          (get_alerts,            asOf),
        "productionPulse": (get_production_pulse,  asOf),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn, arg): key for key, (fn, arg) in sections.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {"usingMock": True, "error": str(exc)}

    return {
        "status":          "ok",
        "asOf":            asOf,
        "cfoKpis":         results.get("cfoKpis",         {}),
        "financeOps":      results.get("financeOps",      {}),
        "alerts":          results.get("alerts",          {}),
        "productionPulse": results.get("productionPulse", {}),
    }
