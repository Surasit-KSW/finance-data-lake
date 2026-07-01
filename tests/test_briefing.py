"""
tests/test_briefing.py
======================
Tests for briefing router endpoints to verify company_code='1000' filter is applied.

Endpoints tested:
  GET /api/v1/briefing/cfo-kpis    → get_cfo_kpis
  GET /api/v1/briefing/finance-ops → get_finance_ops
  GET /api/v1/briefing/alerts      → get_alerts

The briefing router uses private helper functions (_query_gl_balance,
_query_gl_entry_count, _query_prod_volume_mtd, _query_plant_unit_costs)
that each call query_df internally. We patch query_df at the module level
and verify that at least one call includes company_code='1000' in params.
"""
import pytest
from unittest.mock import patch, call
import pandas as pd
from fastapi import HTTPException
from backend.routers.briefing import get_cfo_kpis, get_finance_ops, get_alerts


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _empty_df(*cols):
    """Return an empty DataFrame with the given columns."""
    return pd.DataFrame(columns=list(cols))


def _revenue_df(total=285_000_000.0):
    return pd.DataFrame({"total": [total]})


def _gp_df(rev=285_000_000.0, gp=52_725_000.0):
    return pd.DataFrame({"rev": [rev], "gp": [gp]})


def _prod_df(total_mt=41_000.0):
    return pd.DataFrame({"total_mt": [total_mt]})


def _gl_balance_df(balance=100_000_000.0):
    return pd.DataFrame({"balance": [balance]})


def _gl_count_df(cnt=1500):
    return pd.DataFrame({"cnt": [cnt]})


def _plant_cost_df():
    """Return realistic v_production aggregate for _query_plant_unit_costs."""
    return pd.DataFrame({
        "plant":      ["1300", "1100", "1200"],
        "vol_mt":     [11_000.0, 8_000.0, 22_000.0],
        "total_cost": [291_995_000.0, 254_240_000.0, 732_380_000.0],
    })


def _gp_by_plant_df():
    """Return negative-GP row to trigger the GP alert in get_alerts."""
    return pd.DataFrame({
        "plant": ["1300"],
        "rev":   [100_000_000.0],
        "gp":    [-5_000_000.0],
    })


# ─── Tests: get_cfo_kpis ───────────────────────────────────────────────────────

@patch("backend.routers.briefing.query_df")
def test_cfo_kpis_prod_volume_includes_company_code(mock_query_df):
    """
    _query_prod_volume_mtd (called by get_cfo_kpis) must pass company_code='1000'
    to the v_production query.
    """
    # Each helper calls query_df once. We return simple mocks for each call.
    # Call order: revenue, gp, production-volume, ar-balance, cash-balance
    mock_query_df.side_effect = [
        _revenue_df(),       # _query_revenue_mtd  → gold_revenue_monthly
        _gp_df(),            # _query_gp_mtd        → gold_gp_by_plant
        _prod_df(),          # _query_prod_volume_mtd → v_production
        _gl_balance_df(),    # _query_gl_balance AR  → v_gl (ytd 12*)
        _gl_balance_df(50_000_000.0),  # _query_gl_balance Cash → v_gl (ytd 11*)
    ]

    result = get_cfo_kpis(asOf="2026-05-31")

    # Verify overall call
    assert mock_query_df.called

    # Find the v_production call (3rd call, index 2)
    prod_call = mock_query_df.call_args_list[2]
    sql    = prod_call[0][0]
    params = prod_call[0][1]

    assert "v_production" in sql, "Should query v_production"
    assert "company_code" in sql, "v_production query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.briefing.query_df")
def test_cfo_kpis_gl_balance_includes_company_code(mock_query_df):
    """
    _query_gl_balance (AR + Cash) called by get_cfo_kpis must pass company_code='1000'.
    """
    mock_query_df.side_effect = [
        _revenue_df(),
        _gp_df(),
        _prod_df(),
        _gl_balance_df(350_000_000.0),   # AR balance
        _gl_balance_df(80_000_000.0),    # Cash balance
    ]

    result = get_cfo_kpis(asOf="2026-05-31")
    assert result["status"] == "ok"

    # AR balance call (index 3) and Cash call (index 4) both go to v_gl
    for idx in [3, 4]:
        call_args = mock_query_df.call_args_list[idx]
        sql    = call_args[0][0]
        params = call_args[0][1]
        assert "company_code" in sql, f"v_gl call {idx} should include company_code filter"
        assert "1000" in params, f"v_gl call {idx} params should contain '1000'"


@patch("backend.routers.briefing.query_df")
def test_cfo_kpis_response_shape(mock_query_df):
    """Verify get_cfo_kpis returns all required top-level keys."""
    mock_query_df.side_effect = [
        _revenue_df(),
        _gp_df(),
        _prod_df(),
        _gl_balance_df(200_000_000.0),
        _gl_balance_df(60_000_000.0),
    ]

    result = get_cfo_kpis(asOf="2026-05-31")

    assert result["status"] == "ok"
    assert result["asOf"] == "2026-05-31"
    assert "revenueMtd" in result
    assert "grossMargin" in result
    assert "ebitdaRunRate" in result
    assert "arOutstanding" in result
    assert "cashToday" in result
    assert "productionVolumeMtd" in result

    # Check nested keys
    assert "value" in result["revenueMtd"]
    assert "target" in result["revenueMtd"]
    assert "pctOfTarget" in result["revenueMtd"]


# ─── Tests: get_finance_ops ────────────────────────────────────────────────────

@patch("backend.routers.briefing.query_df")
def test_finance_ops_gl_count_includes_company_code(mock_query_df):
    """
    _query_gl_entry_count (called by get_finance_ops) must pass company_code='1000'
    to the v_gl COUNT query.
    """
    # Call order: gl_count (v_gl), ap_balance (v_gl)
    mock_query_df.side_effect = [
        _gl_count_df(1500),     # _query_gl_entry_count → v_gl COUNT(*)
        _gl_balance_df(180_000_000.0),  # _query_gl_balance AP (21*)
    ]

    result = get_finance_ops(asOf="2026-05-31")

    assert mock_query_df.called

    # GL count call (index 0)
    gl_call = mock_query_df.call_args_list[0]
    sql    = gl_call[0][0]
    params = gl_call[0][1]

    assert "v_gl" in sql, "Should query v_gl for GL entry count"
    assert "company_code" in sql, "v_gl query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.briefing.query_df")
def test_finance_ops_ap_balance_includes_company_code(mock_query_df):
    """
    _query_gl_balance (AP = 21*) called by get_finance_ops must pass company_code='1000'.
    """
    mock_query_df.side_effect = [
        _gl_count_df(1200),
        _gl_balance_df(-180_000_000.0),   # AP credit → negative
    ]

    result = get_finance_ops(asOf="2026-05-31")

    # AP balance call (index 1)
    ap_call = mock_query_df.call_args_list[1]
    sql    = ap_call[0][0]
    params = ap_call[0][1]

    assert "company_code" in sql, "AP balance query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.briefing.query_df")
def test_finance_ops_response_shape(mock_query_df):
    """Verify get_finance_ops returns the required structure."""
    mock_query_df.side_effect = [
        _gl_count_df(800),
        _gl_balance_df(120_000_000.0),
    ]

    result = get_finance_ops(asOf="2026-01-15")

    assert result["status"] == "ok"
    assert result["asOf"] == "2026-01-15"
    assert "monthEndClose" in result
    assert "glStatus" in result
    assert "apOutstanding" in result
    assert "closeTasks" in result

    # Structural sub-keys
    assert "progressPct" in result["monthEndClose"]
    assert "daysLeft" in result["monthEndClose"]
    assert "totalEntries" in result["glStatus"]


# ─── Tests: get_alerts ─────────────────────────────────────────────────────────

@patch("backend.routers.briefing.query_df")
def test_alerts_production_cost_includes_company_code(mock_query_df):
    """
    _query_plant_unit_costs (called by get_alerts) must pass company_code='1000'
    to the v_production query.
    """
    # Call order in get_alerts:
    # 1. _query_plant_unit_costs → v_production GROUP BY Plant
    # 2. For each plant with 0 volume: _query_prod_volume_mtd (3 calls)
    #    + v_gl zero-volume check (up to 3 calls)
    # 3. gp_df for negative GP check → gold_gp_by_plant
    # 4. AR balance check → v_gl
    # 5. Revenue for AR % → gold_revenue_monthly

    # Return non-zero plant costs to trigger cost-deviation alert logic,
    # then return empty for subsequent calls to keep side_effect manageable.
    plant_cost_df = _plant_cost_df()

    mock_query_df.side_effect = [
        plant_cost_df,                    # _query_plant_unit_costs (v_production)
        pd.DataFrame({"total_mt": [11_000.0]}),  # prod_volume plant 1300
        pd.DataFrame({"total_mt": [8_000.0]}),   # prod_volume plant 1100
        pd.DataFrame({"total_mt": [22_000.0]}),  # prod_volume plant 1200
        _empty_df("plant", "rev", "gp"),  # gp_df (gold_gp_by_plant)
        _gl_balance_df(250_000_000.0),    # AR balance (v_gl)
        _revenue_df(285_000_000.0),       # revenue for AR % (gold_revenue_monthly)
    ]

    result = get_alerts(date_param="2026-05-31")

    # plant unit cost call is index 0
    uc_call = mock_query_df.call_args_list[0]
    sql    = uc_call[0][0]
    params = uc_call[0][1]

    assert "v_production" in sql, "Should query v_production for unit costs"
    assert "company_code" in sql, "v_production query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.briefing.query_df")
def test_alerts_gl_zero_volume_includes_company_code(mock_query_df):
    """
    The zero-production GL check in get_alerts (direct query_df call) must include
    company_code='1000' in the v_gl WHERE clause.
    """
    # Return zero production volume to trigger the zero-volume GL cost check.
    # plant_cost_df: empty → no unit-cost deviation alerts
    # prod_volume for each plant: 0 → triggers zero-volume branch
    # v_gl cost check: return some GL cost > 0 to confirm company_code path is exercised

    zero_prod_df = pd.DataFrame({"total_mt": [0.0]})
    gl_cost_df   = pd.DataFrame({"total": [5_000_000.0]})
    empty_gp     = _empty_df("plant", "rev", "gp")

    mock_query_df.side_effect = [
        pd.DataFrame({"plant": [], "vol_mt": [], "total_cost": []}),  # no unit cost data
        zero_prod_df,   # plant 1300 volume = 0
        gl_cost_df,     # GL cost for plant 1300 → warning alert
        zero_prod_df,   # plant 1100 volume = 0
        gl_cost_df,     # GL cost for plant 1100
        zero_prod_df,   # plant 1200 volume = 0
        gl_cost_df,     # GL cost for plant 1200
        empty_gp,       # no negative GP
        _gl_balance_df(100_000_000.0),  # AR below threshold → no AR alert
        _revenue_df(),  # revenue for AR %
    ]

    result = get_alerts(date_param="2026-05-31")

    # Find the first v_gl zero-volume cost check call (index 2)
    # It's a direct query_df call (not via helper): SELECT SUM(net_amount) FROM v_gl WHERE ...
    gl_zero_call = mock_query_df.call_args_list[2]
    sql    = gl_zero_call[0][0]
    params = gl_zero_call[0][1]

    assert "v_gl" in sql, "Zero-volume GL check should query v_gl"
    assert "company_code" in sql, "v_gl zero-volume query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.briefing.query_df")
def test_alerts_response_shape(mock_query_df):
    """Verify get_alerts returns the required structure with alerts list."""
    # All queries return empty → no alerts generated
    mock_query_df.return_value = pd.DataFrame()

    result = get_alerts(date_param="2026-05-31")

    assert result["status"] == "ok"
    assert result["date"] == "2026-05-31"
    assert "count" in result
    assert "alerts" in result
    assert isinstance(result["alerts"], list)
    assert result["count"] == len(result["alerts"])


@patch("backend.routers.briefing.query_df")
def test_cfo_kpis_invalid_date_raises_400(mock_query_df):
    """Verify that an invalid asOf date raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        get_cfo_kpis(asOf="not-a-date")
    assert exc_info.value.status_code == 400
