"""
tests/test_data_lake.py
=======================
Tests for data_lake router: fpa-summary, fpa-variance, treasury.
Each endpoint: (1) returns expected shape, (2) filters company_code='1000' where applicable,
(3) returns graceful fallback on DB error.
"""
import pytest
from unittest.mock import patch
import pandas as pd
from backend.routers.data_lake import get_fpa_summary, get_fpa_variance, get_treasury


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _revenue_df(revenue=285_000_000.0):
    return pd.DataFrame({"revenue": [revenue]})


def _total_df(total=50_000_000.0):
    return pd.DataFrame({"total": [total]})


def _balance_df(balance=100_000_000.0):
    return pd.DataFrame({"balance": [balance]})


def _overdue_df(overdue_amt=0.0):
    return pd.DataFrame({"overdue_amt": [overdue_amt]})


def _variance_gl_df():
    return pd.DataFrame({
        "gl_account": ["5410010", "5510010"],
        "gl_name":    ["HRC Steel", "Direct Labor"],
        "actual":     [18_500_000.0, 4_200_000.0],
    })


def _baseline_gl_df():
    return pd.DataFrame({
        "gl_account": ["5410010", "5510010"],
        "baseline":   [17_200_000.0, 4_000_000.0],
    })


# ─── /fpa-summary ─────────────────────────────────────────────────────────────

@patch("backend.routers.data_lake.query_df")
def test_fpa_summary_returns_12_months(mock_qdf):
    """Response must have exactly 12 month entries for a past year."""
    mock_qdf.return_value = _revenue_df()
    result = get_fpa_summary(year=2025)
    assert result["year"] == 2025
    assert len(result["months"]) == 12


@patch("backend.routers.data_lake.query_df")
def test_fpa_summary_has_required_keys(mock_qdf):
    """Each month entry must contain all required response keys."""
    mock_qdf.return_value = _total_df()
    result = get_fpa_summary(year=2025)
    required = {"month", "revenue", "cogs", "grossProfit", "gpMargin", "opex", "ebit", "priorYear"}
    for m in result["months"]:
        assert required.issubset(m.keys()), f"Month {m['month']} missing keys: {required - m.keys()}"


@patch("backend.routers.data_lake.query_df")
def test_fpa_summary_revenue_filters_company_1000(mock_qdf):
    """Revenue query (v_sales) must include company_code='1000' in params."""
    mock_qdf.return_value = _revenue_df()
    get_fpa_summary(year=2025)
    # call_args_list[0] is the DB probe (SELECT 1); call_args_list[1] is v_sales for month=1
    v_sales_params = mock_qdf.call_args_list[1][0][1]
    assert "1000" in v_sales_params, f"Missing company_code='1000' in v_sales params: {v_sales_params}"


@patch("backend.routers.data_lake.query_df")
def test_fpa_summary_returns_graceful_on_error(mock_qdf):
    """Full DB outage must return usingMock=True, not 12 months of nulls."""
    mock_qdf.side_effect = Exception("DuckDB offline")
    result = get_fpa_summary(year=2025)
    assert result.get("usingMock") is True
    assert result.get("months") == []


# ─── /fpa-variance ────────────────────────────────────────────────────────────

@patch("backend.routers.data_lake.query_df")
def test_fpa_variance_returns_expected_shape(mock_qdf):
    """Response must have 'period' and 'categories' list."""
    mock_qdf.side_effect = [_variance_gl_df(), _baseline_gl_df()]
    result = get_fpa_variance(year=2026, month=7)
    assert result["period"] == "2026-07"
    assert isinstance(result["categories"], list)
    assert len(result["categories"]) == 2


@patch("backend.routers.data_lake.query_df")
def test_fpa_variance_flag_over_when_above_5pct(mock_qdf):
    """Category with variancePct > 5% must be flagged 'over'."""
    # HRC: actual 18.5M vs baseline 17.2M → variance 7.6% → flag 'over'
    mock_qdf.side_effect = [_variance_gl_df(), _baseline_gl_df()]
    result = get_fpa_variance(year=2026, month=7)
    hrc = next(c for c in result["categories"] if c["glAccount"] == "5410010")
    assert hrc["flag"] == "over", f"Expected 'over', got '{hrc['flag']}'"
    assert hrc["variance"] == pytest.approx(1_300_000.0, abs=1.0)


@patch("backend.routers.data_lake.query_df")
def test_fpa_variance_filters_company_1000(mock_qdf):
    """Both GL queries (current + prior year) must include company_code='1000'."""
    mock_qdf.side_effect = [_variance_gl_df(), _baseline_gl_df()]
    get_fpa_variance(year=2026, month=7)
    for i, call_args in enumerate(mock_qdf.call_args_list):
        params = call_args[0][1]
        assert "1000" in params, f"Query {i} missing company_code='1000': {params}"


@patch("backend.routers.data_lake.query_df")
def test_fpa_variance_returns_graceful_on_error(mock_qdf):
    """Exception during query must return categories=[] and usingMock=True."""
    mock_qdf.side_effect = Exception("DuckDB offline")
    result = get_fpa_variance(year=2026, month=7)
    assert result.get("usingMock") is True
    assert result.get("categories") == []


# ─── /treasury ────────────────────────────────────────────────────────────────

@patch("backend.routers.data_lake.query_df")
def test_treasury_returns_expected_shape(mock_qdf):
    """Response must have cash, ar, ap, nwcRunway top-level keys."""
    mock_qdf.return_value = _balance_df()
    result = get_treasury(asOf="2026-07-04")
    assert "cash" in result
    assert "ar" in result
    assert "ap" in result
    assert "nwcRunway" in result


@patch("backend.routers.data_lake.query_df")
def test_treasury_cash_trend_has_6_entries(mock_qdf):
    """cash.trend6m must contain exactly 6 entries with month + balance keys."""
    mock_qdf.return_value = _balance_df()
    result = get_treasury(asOf="2026-07-04")
    trend = result["cash"]["trend6m"]
    assert len(trend) == 6
    assert all("month" in e and "balance" in e for e in trend)


@patch("backend.routers.data_lake.query_df")
def test_treasury_gl_queries_filter_company_1000(mock_qdf):
    """At least one GL query must use company_code='1000' in positional params."""
    mock_qdf.return_value = _balance_df()
    get_treasury(asOf="2026-07-04")
    company_filtered = [c for c in mock_qdf.call_args_list if "1000" in (c[0][1] or [])]
    assert len(company_filtered) > 0, "No query used company_code='1000'"


@patch("backend.routers.data_lake.query_df")
def test_treasury_returns_graceful_on_error(mock_qdf):
    """Exception during query must return usingMock=True without raising."""
    mock_qdf.side_effect = Exception("DuckDB offline")
    result = get_treasury(asOf="2026-07-04")
    assert result.get("usingMock") is True
