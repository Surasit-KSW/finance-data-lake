"""
tests/test_dashboard.py
=======================
Tests for dashboard router endpoints.

Endpoints tested:
  GET /api/v1/financial-performance → get_financial_performance
  GET /api/v1/liquidity             → get_liquidity
  GET /api/v1/working-capital       → get_working_capital
  GET /api/v1/cash-flow             → get_cash_flow
  GET /api/v1/budget-actual         → get_budget_actual

Security note:
  Dashboard queries v_gl_summary — a Gold-layer aggregate that is already
  AMC-company-only (no multi-company data). There is NO company_code column
  in v_gl_summary, so asserting "1000" in params is NOT applicable here.
  Tests instead verify: response shape, period parsing, and 404/400 error handling.
"""
import pytest
from unittest.mock import patch
import pandas as pd
from fastapi import HTTPException
from backend.routers.dashboard import (
    get_financial_performance,
    get_liquidity,
    get_working_capital,
    get_cash_flow,
    get_budget_actual,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _gl_summary_monthly_df():
    """Minimal v_gl_summary monthly aggregation (one row per GL_Group)."""
    return pd.DataFrame({
        "gl_group": [
            "4. Revenue",
            "5. COGS",
            "6. Selling Exp",
            "7. Admin Exp",
            "8. Finance Cost",
            "9. Tax",
        ],
        "amount": [
            -285_000_000.0,   # revenue → credit → negative in SAP
             220_000_000.0,   # COGS
               8_000_000.0,   # selling
               5_000_000.0,   # admin
               3_000_000.0,   # finance
               2_000_000.0,   # tax
        ],
    })


def _gl_summary_prefix_df():
    """Minimal v_gl_summary cumulative by 2-char account prefix."""
    return pd.DataFrame({
        "prefix":  ["11", "12", "21", "22", "31", "33"],
        "balance": [
            50_000_000.0,    # 11* cash
            320_000_000.0,   # 12* AR
           -180_000_000.0,   # 21* AP (credit → negative)
            -20_000_000.0,   # 22* other payables
            30_000_000.0,    # 31* inventory
            200_000_000.0,   # 33* equity
        ],
    })


def _cash_ytd_df(ytd=50_000_000.0):
    return pd.DataFrame({"ytd_cash": [ytd]})


# ─── Tests: get_financial_performance ─────────────────────────────────────────

@patch("backend.routers.dashboard.query_df")
def test_financial_performance_response_shape(mock_query_df):
    """Verify get_financial_performance returns all expected P&L keys."""
    mock_query_df.return_value = _gl_summary_monthly_df()

    result = get_financial_performance(period="2026-05")

    assert result["period"] == "2026-05"
    assert "revenue" in result
    assert "cogs" in result
    assert "gross_profit" in result
    assert "selling_expense" in result
    assert "admin_expense" in result
    assert "ebit" in result
    assert "ebitda" in result
    assert "net_profit" in result
    assert "gross_margin_pct" in result
    assert "ebit_margin_pct" in result
    assert "net_margin_pct" in result

    # Revenue should be positive (SAP sign flip applied)
    assert result["revenue"] == 285_000_000.0
    # Gross profit = revenue - COGS
    assert result["gross_profit"] == round(285_000_000.0 - 220_000_000.0, 2)


@patch("backend.routers.dashboard.query_df")
def test_financial_performance_invalid_period_raises_400(mock_query_df):
    """An invalid period string must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_financial_performance(period="bad")
    assert exc_info.value.status_code == 400
    mock_query_df.assert_not_called()


@patch("backend.routers.dashboard.query_df")
def test_financial_performance_invalid_month_raises_400(mock_query_df):
    """A period with month > 12 must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_financial_performance(period="2026-13")
    assert exc_info.value.status_code == 400


@patch("backend.routers.dashboard.query_df")
def test_financial_performance_no_data_raises_404(mock_query_df):
    """An empty query result must raise HTTPException 404."""
    mock_query_df.return_value = pd.DataFrame(columns=["gl_group", "amount"])

    with pytest.raises(HTTPException) as exc_info:
        get_financial_performance(period="2020-01")
    assert exc_info.value.status_code == 404


# ─── Tests: get_liquidity ─────────────────────────────────────────────────────

@patch("backend.routers.dashboard.query_df")
def test_liquidity_response_shape(mock_query_df):
    """Verify get_liquidity returns balance sheet ratios and component keys."""
    mock_query_df.return_value = _gl_summary_prefix_df()

    result = get_liquidity(period="2026-05")

    assert result["period"] == "2026-05"
    assert "current_assets" in result
    assert "current_liabilities" in result
    assert "cash_and_equivalents" in result
    assert "accounts_receivable" in result
    assert "accounts_payable" in result
    assert "current_ratio" in result
    assert "quick_ratio" in result
    assert "cash_ratio" in result
    assert "debt_to_equity" in result


@patch("backend.routers.dashboard.query_df")
def test_liquidity_ratios_are_positive(mock_query_df):
    """All liquidity ratios should be non-negative numbers."""
    mock_query_df.return_value = _gl_summary_prefix_df()

    result = get_liquidity(period="2026-05")

    assert result["current_ratio"] >= 0
    assert result["quick_ratio"] >= 0
    assert result["cash_ratio"] >= 0


@patch("backend.routers.dashboard.query_df")
def test_liquidity_invalid_period_raises_400(mock_query_df):
    """An invalid period must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_liquidity(period="2026/05")
    assert exc_info.value.status_code == 400


# ─── Tests: get_working_capital ───────────────────────────────────────────────

@patch("backend.routers.dashboard.query_df")
def test_working_capital_response_shape(mock_query_df):
    """Verify get_working_capital returns efficiency ratios (DSO, DPO, DIO, CCC)."""
    # Two queries: cumulative prefix + trailing-12-month P&L
    mock_query_df.side_effect = [
        _gl_summary_prefix_df(),
        _gl_summary_monthly_df().rename(columns={"gl_group": "gl_group", "amount": "amount"}),
    ]

    result = get_working_capital(period="2026-05")

    assert result["period"] == "2026-05"
    assert "accounts_receivable" in result
    assert "accounts_payable" in result
    assert "inventory_value" in result
    assert "dso" in result
    assert "dpo" in result
    assert "dio" in result
    assert "cash_conversion_cycle" in result


@patch("backend.routers.dashboard.query_df")
def test_working_capital_invalid_period_raises_400(mock_query_df):
    """An invalid period must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_working_capital(period="not-valid")
    assert exc_info.value.status_code == 400


# ─── Tests: get_cash_flow ─────────────────────────────────────────────────────

@patch("backend.routers.dashboard.query_df")
def test_cash_flow_response_shape(mock_query_df):
    """Verify get_cash_flow returns all cash-flow statement keys."""
    # Call order: closing cash YTD, opening cash YTD (prev month), _pnl_for_period (monthly)
    mock_query_df.side_effect = [
        _cash_ytd_df(50_000_000.0),     # closing: Jan–May YTD cash
        _cash_ytd_df(40_000_000.0),     # opening: Jan–Apr YTD cash
        _gl_summary_monthly_df(),        # _pnl_for_period (monthly P&L for net_profit)
    ]

    result = get_cash_flow(period="2026-05")

    assert result["period"] == "2026-05"
    assert "opening_balance" in result
    assert "closing_balance" in result
    assert "net_change" in result
    assert "operating_cf" in result
    assert "investing_cf" in result
    assert "financing_cf" in result
    assert "free_cash_flow" in result

    # Net change should equal closing − opening
    assert result["net_change"] == round(
        result["closing_balance"] - result["opening_balance"], 2
    )


@patch("backend.routers.dashboard.query_df")
def test_cash_flow_january_no_opening_query(mock_query_df):
    """For January, opening balance = 0 (no prior-month query)."""
    # Only 2 query_df calls for January: closing cash + monthly P&L
    mock_query_df.side_effect = [
        _cash_ytd_df(30_000_000.0),    # closing: Jan YTD
        _gl_summary_monthly_df(),       # monthly P&L
    ]

    result = get_cash_flow(period="2026-01")

    assert result["opening_balance"] == 0.0
    assert result["closing_balance"] == 30_000_000.0
    assert result["net_change"] == 30_000_000.0
    # Should only have been called twice (no opening query)
    assert mock_query_df.call_count == 2


@patch("backend.routers.dashboard.query_df")
def test_cash_flow_invalid_period_raises_400(mock_query_df):
    """An invalid period must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_cash_flow(period="2026")
    assert exc_info.value.status_code == 400


# ─── Tests: get_budget_actual ─────────────────────────────────────────────────

@patch("backend.routers.dashboard.query_df")
def test_budget_actual_response_shape(mock_query_df):
    """Verify get_budget_actual returns BudgetItem[] with all required keys."""
    # Two calls: budget (prior year) + actual (current year)
    mock_query_df.side_effect = [
        _gl_summary_monthly_df(),   # prior-year same month (budget)
        _gl_summary_monthly_df(),   # current-year month (actual)
    ]

    result = get_budget_actual(period="2026-05")

    assert result["period"] == "2026-05"
    assert "items" in result
    assert "summary" in result
    assert "budget_label" in result
    assert "2025" in result["budget_label"]   # prior year reference

    # Check BudgetItem structure
    item = result["items"][0]
    assert "cost_center" in item
    assert "gl_account" in item
    assert "budget_amount" in item
    assert "actual_amount" in item
    assert "variance_amount" in item
    assert "variance_pct" in item

    # Check summary
    summary = result["summary"]
    assert "total_budget" in summary
    assert "total_actual" in summary
    assert "total_variance" in summary


@patch("backend.routers.dashboard.query_df")
def test_budget_actual_invalid_period_raises_400(mock_query_df):
    """An invalid period must raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_budget_actual(period="invalid-period")
    assert exc_info.value.status_code == 400


@patch("backend.routers.dashboard.query_df")
def test_budget_actual_no_data_raises_404(mock_query_df):
    """When both budget and actual are empty, must raise HTTPException 404."""
    mock_query_df.return_value = pd.DataFrame(columns=["gl_group", "amount"])

    with pytest.raises(HTTPException) as exc_info:
        get_budget_actual(period="2020-01")
    assert exc_info.value.status_code == 404
