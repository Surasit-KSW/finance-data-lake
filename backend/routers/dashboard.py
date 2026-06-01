"""
routers/dashboard.py
====================
Executive Financial Dashboard — /api/v1/* endpoints

Serves the 5 dashboard modules with the same response shape as the
original dashboard backend, so the frontend works without changes.

Data sources:
  - v_gl_summary : monthly GL amounts by GL_Group (P&L + BS account movements)
  - v_gl         : raw GL transactions (fallback / drill-down)

Modules:
  GET /api/v1/financial-performance?period=YYYY-MM
  GET /api/v1/liquidity?period=YYYY-MM
  GET /api/v1/working-capital?period=YYYY-MM
  GET /api/v1/cash-flow?period=YYYY-MM
  GET /api/v1/budget-actual?period=YYYY-MM   (stub — no budget data yet)

SAP sign convention (stored in v_gl_summary):
  Revenue (4.*)  → credit posting → Net_Amount is NEGATIVE → flip sign for display
  COGS   (5.*)  → debit  posting → Net_Amount is POSITIVE
  Assets (1.*)  → debit  posting → Net_Amount is POSITIVE (AR, cash in)
  Liabilities (2.*) → credit posting → Net_Amount is NEGATIVE (AP owes)

Limitations:
  - Balance sheet figures are cumulative movements from Jan 2024 (no Dec-2023 opening balance)
  - EBITDA = EBIT (D&A not separately tagged in current GL_Group mapping)
  - Cash flow: operating_cf = net_profit; investing_cf/financing_cf are approximations
"""

from fastapi import APIRouter, Query, HTTPException
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_period(period: str) -> tuple[int, int]:
    try:
        year_str, month_str = period.split("-")
        year, month = int(year_str), int(month_str)
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM (e.g. 2025-03)")


def _gl_monthly(year: int, month: int) -> dict[str, float]:
    """Return {GL_Group: net_amount} for a single year/month from v_gl_summary."""
    df = query_df(
        """
        SELECT GL_Group, SUM(Net_Amount) AS amount
        FROM v_gl_summary
        WHERE CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) = ?
        GROUP BY GL_Group
        """,
        [year, month],
    )
    if df.empty:
        return {}
    return df.set_index("GL_Group")["amount"].to_dict()


def _gl_prefix_cumulative(year: int, month: int) -> dict[str, float]:
    """
    Return {account_prefix_2char: cumulative_net_amount} for all months
    up to and including year-month.
    Used for balance sheet approximation (no opening balance available).
    Uses SUBSTRING (PostgreSQL-compatible alias for SUBSTR).
    """
    df = query_df(
        """
        SELECT SUBSTRING("G/L Account" FROM 1 FOR 2) AS prefix, SUM(Net_Amount) AS balance
        FROM v_gl_summary
        WHERE (CAST(Year AS INTEGER) < ?)
           OR (CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) <= ?)
        GROUP BY prefix
        """,
        [year, year, month],
    )
    if df.empty:
        return {}
    return df.set_index("prefix")["balance"].to_dict()


def _pnl_for_period(year: int, month: int) -> dict | None:
    """Compute monthly P&L dict. Returns None if no GL data."""
    totals = _gl_monthly(year, month)
    if not totals:
        return None

    revenue_raw  = totals.get("4. Revenue", 0.0)
    revenue      = round(-revenue_raw, 2)        # flip: SAP credit = negative
    cogs         = round(totals.get("5. COGS", 0.0), 2)
    selling      = round(totals.get("6. Selling Exp", 0.0), 2)
    admin        = round(totals.get("7. Admin Exp", 0.0), 2)
    finance_cost = round(totals.get("8. Finance Cost", 0.0), 2)
    tax          = round(totals.get("9. Tax", 0.0), 2)

    gross_profit = round(revenue - cogs, 2)
    opex         = round(selling + admin, 2)
    ebit         = round(gross_profit - opex, 2)
    ebt          = round(ebit - finance_cost, 2)
    net_profit   = round(ebt - tax, 2)
    ebitda       = ebit   # D&A not separately tagged — EBITDA ≈ EBIT

    safe_rev = revenue if revenue != 0 else 1
    return {
        "revenue":            revenue,
        "cogs":               cogs,
        "gross_profit":       gross_profit,
        "selling_expense":    selling,
        "admin_expense":      admin,
        "operating_expense":  opex,
        "ebit":               ebit,
        "finance_cost":       finance_cost,
        "ebt":                ebt,
        "tax":                tax,
        "net_profit":         net_profit,
        "ebitda":             ebitda,   # currently EBITDA ≈ EBIT (D&A not separately tagged)
        "gross_margin_pct":   round(gross_profit / safe_rev * 100, 2),
        "ebit_margin_pct":    round(ebit          / safe_rev * 100, 2),
        "net_margin_pct":     round(net_profit    / safe_rev * 100, 2),
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/financial-performance")
def get_financial_performance(
    period: str = Query(..., description="Period YYYY-MM (e.g. 2025-03)"),
):
    """
    Monthly P&L from v_gl_summary.
    Revenue / COGS / Gross Profit / OPEX / EBITDA / Net Profit / Margins.
    """
    year, month = _parse_period(period)
    data = _pnl_for_period(year, month)
    if not data:
        raise HTTPException(status_code=404, detail=f"No GL data for period {period}")
    return {"period": period, **data}


@router.get("/liquidity")
def get_liquidity(
    period: str = Query(..., description="Period YYYY-MM"),
):
    """
    Balance sheet ratios approximated from cumulative GL movements.
    Accuracy note: opening balance (pre-Jan 2024) not included.

    Account mapping (SAP):
      11* = Cash & cash equivalents
      12* = Accounts receivable
      21* = Accounts payable
      22* = Other short-term payables
      33* = Equity / retained earnings (used as proxy for D/E)
    """
    year, month = _parse_period(period)
    by_prefix = _gl_prefix_cumulative(year, month)

    if not by_prefix:
        raise HTTPException(status_code=404, detail=f"No GL data for period {period}")

    # Balance sheet positions (abs: SAP credit-side entries are stored negative)
    cash = abs(by_prefix.get("11", 0.0))
    ar   = abs(by_prefix.get("12", 0.0))
    inv  = abs(by_prefix.get("31", 0.0)) + abs(by_prefix.get("32", 0.0))

    ap       = abs(by_prefix.get("21", 0.0)) + abs(by_prefix.get("22", 0.0))
    equity   = abs(by_prefix.get("33", 0.0))

    current_assets      = round(cash + ar + inv, 2)
    current_liabilities = round(ap, 2)

    safe_cl     = current_liabilities if current_liabilities > 0 else 1
    safe_equity = equity              if equity              > 0 else 1

    return {
        "period":               period,
        "current_assets":       current_assets,
        "current_liabilities":  current_liabilities,
        "cash_and_equivalents": round(cash, 2),
        "accounts_receivable":  round(ar, 2),
        "inventory":            round(inv, 2),
        "equity":               round(equity, 2),
        "net_assets":           round(equity, 2),   # proxy: equity ≈ net assets from GL 33*
        "current_ratio":        round(current_assets / safe_cl, 2),
        "quick_ratio":          round((current_assets - inv) / safe_cl, 2),
        "cash_ratio":           round(cash / safe_cl, 2),
        "debt_to_equity":       round(current_liabilities / safe_equity, 4),
    }


@router.get("/working-capital")
def get_working_capital(
    period: str = Query(..., description="Period YYYY-MM"),
):
    """
    Working capital components + efficiency ratios (DSO, DPO, DIO, CCC).
    AR / AP / Inventory from cumulative GL; DSO/DPO/DIO from trailing 12-month P&L.
    """
    year, month = _parse_period(period)
    by_prefix   = _gl_prefix_cumulative(year, month)

    if not by_prefix:
        raise HTTPException(status_code=404, detail=f"No GL data for period {period}")

    ar  = abs(by_prefix.get("12", 0.0))
    ap  = abs(by_prefix.get("21", 0.0)) + abs(by_prefix.get("22", 0.0))
    inv = abs(by_prefix.get("31", 0.0)) + abs(by_prefix.get("32", 0.0))

    # Trailing 12-month P&L for ratio denominators
    t12_start_month = month - 11
    t12_start_year  = year
    while t12_start_month <= 0:
        t12_start_month += 12
        t12_start_year  -= 1

    df_t12 = query_df(
        """
        SELECT GL_Group, SUM(Net_Amount) AS amount
        FROM v_gl_summary
        WHERE (CAST(Year AS INTEGER) > ? OR (CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) >= ?))
          AND (CAST(Year AS INTEGER) < ? OR (CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) <= ?))
        GROUP BY GL_Group
        """,
        [t12_start_year, t12_start_year, t12_start_month, year, year, month],
    )
    t12: dict = df_t12.set_index("GL_Group")["amount"].to_dict() if not df_t12.empty else {}

    annual_revenue = abs(t12.get("4. Revenue", 0.0))
    annual_cogs    = abs(t12.get("5. COGS", 0.0))

    safe_rev  = annual_revenue if annual_revenue > 0 else 1
    safe_cogs = annual_cogs    if annual_cogs    > 0 else 1

    dso = round(ar  / safe_rev  * 365, 1)
    dpo = round(ap  / safe_cogs * 365, 1)
    dio = round(inv / safe_cogs * 365, 1)
    ccc = round(dso + dio - dpo, 1)

    return {
        "period":             period,
        "accounts_receivable": round(ar, 2),
        "accounts_payable":    round(ap, 2),
        "inventory_value":     round(inv, 2),
        "dso":                 dso,
        "dpo":                 dpo,
        "dio":                 dio,
        "cash_conversion_cycle": ccc,
    }


@router.get("/cash-flow")
def get_cash_flow(
    period: str = Query(..., description="Period YYYY-MM"),
):
    """
    Cash flow approximation from GL.
    - opening/closing: YTD cumulative movement in 11* (cash) accounts from Jan 1 of same year
    - net_change     = closing - opening (monthly cash movement)
    - operating_cf   = net_profit (indirect method base)
    - financing_cf   = net_change - operating_cf (residual)
    - investing_cf   = 0 (capex not separately tracked in current GL grouping)

    Note: balances represent net GL movements within the year, not absolute cash balances.
    """
    year, month = _parse_period(period)

    # Closing = YTD cumulative 11* from Jan of same year to this month
    # Use parameterized LIKE to avoid psycopg2 % escaping issues
    df_close = query_df(
        """
        SELECT SUM(Net_Amount) AS ytd_cash
        FROM v_gl_summary
        WHERE CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) <= ?
          AND "G/L Account" LIKE ?
        """,
        [year, month, "11%"],
    )
    closing_raw = float(df_close["ytd_cash"].iloc[0] or 0.0) if not df_close.empty else 0.0

    # Opening = YTD cumulative 11* from Jan to previous month (0 if Jan)
    if month == 1:
        opening_raw = 0.0
    else:
        df_open = query_df(
            """
            SELECT SUM(Net_Amount) AS ytd_cash
            FROM v_gl_summary
            WHERE CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) <= ?
              AND "G/L Account" LIKE ?
            """,
            [year, month - 1, "11%"],
        )
        opening_raw = float(df_open["ytd_cash"].iloc[0] or 0.0) if not df_open.empty else 0.0

    # SAP 11* sign: positive Net_Amount = debit = cash increase
    # Keep raw sign: positive opening/closing = net cash inflow YTD
    opening    = round(opening_raw, 2)
    closing    = round(closing_raw, 2)
    net_change = round(closing - opening, 2)

    # P&L for operating CF split
    pnl          = _pnl_for_period(year, month)
    net_profit   = pnl["net_profit"] if pnl else 0.0
    operating_cf = round(net_profit, 2)
    financing_cf = round(net_change - operating_cf, 2)
    investing_cf = 0.0
    free_cash_flow = round(operating_cf, 2)

    return {
        "period":          period,
        "opening_balance": opening,
        "operating_cf":    operating_cf,
        "investing_cf":    investing_cf,
        "financing_cf":    financing_cf,
        "net_change":      net_change,
        "closing_balance": closing,
        "free_cash_flow":  free_cash_flow,
    }


@router.get("/budget-actual")
def get_budget_actual(
    period: str = Query(..., description="Period YYYY-MM"),
):
    """Budget vs Actual — ยังไม่มีข้อมูล budget ใน Data Lake."""
    _parse_period(period)  # validate format
    raise HTTPException(
        status_code=404,
        detail=(
            "Budget data not yet loaded into Data Lake. "
            "Upload a budget Excel file and run the budget ETL script to enable this module."
        ),
    )
