"""
tests/test_monitor.py
=====================
Tests for monitor router endpoints to verify company_code='1000' filter is applied.

Endpoints tested:
  GET /api/v1/monitor/cost-ledger → get_cost_ledger
  GET /api/v1/monitor/overview    → get_overview
  GET /api/v1/monitor/pnl         → get_pnl

The monitor router uses _query_gl_by_account (v_gl), _query_production_volume
(v_production), and _query_tb_amounts (v_gl) — all must include company_code='1000'.
The pnl endpoint also calls query_df directly for v_gl cost aggregation.

Gold-layer tables (gold_revenue_monthly, gold_gp_by_plant) do NOT have company_code
because they are already AMC-only aggregates — we do not assert company_code for those.
"""
import pytest
from unittest.mock import patch
import pandas as pd
from backend.routers.monitor import get_cost_ledger, get_overview, get_pnl


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _empty_df(*cols):
    return pd.DataFrame(columns=list(cols))


def _gl_records_df():
    """Minimal v_gl aggregate for _query_gl_by_account."""
    return pd.DataFrame({
        "account_code": ["5411010", "5611010"],
        "account_name": ["Raw Material", "Electricity"],
        "cost_center":  ["1387120", "1387120"],
        "gl_amount":    [5_000_000.0, 800_000.0],
    })


def _prod_vol_df():
    """Minimal v_production aggregate for _query_production_volume."""
    return pd.DataFrame({
        "Plant":        ["1300"],
        "total_qty_mt": [11_000.0],
    })


def _tb_amounts_df():
    """Minimal v_gl aggregate for _query_tb_amounts (no GL_EXCLUSION)."""
    return pd.DataFrame({
        "account_code": ["5411010", "5611010"],
        "tb_amount":    [5_000_000.0, 800_000.0],
    })


def _mb51_total_df():
    """v_mb51 total DM."""
    return pd.DataFrame({"total_dm": [4_950_000.0]})


def _mb51_breakdown_df():
    """v_mb51 RM breakdown."""
    return pd.DataFrame({
        "hrc": [4_500_000.0], "gic": [0.0], "crc": [0.0],
        "chem": [450_000.0], "other_amt": [0.0],
        "dm_total": [4_950_000.0], "grand_total": [5_800_000.0],
    })


def _mb51_itype_df():
    """v_mb51 GROUP BY input_type (for _build_rm_material_rows)."""
    return pd.DataFrame({
        "itype":    ["HRC"],
        "hrc":      [4_500_000.0],
        "gic":      [0.0],
        "crc":      [0.0],
        "chem":     [450_000.0],
        "other_amt":[0.0],
        "dm_total": [4_950_000.0],
    })


def _gold_gp_df():
    """gold_gp_by_plant aggregate per plant."""
    return pd.DataFrame({
        "plant_code":  ["1300", "1100", "1200"],
        "revenue":     [285_000_000.0, 200_000_000.0, 550_000_000.0],
        "cogs_std":    [220_000_000.0, 160_000_000.0, 450_000_000.0],
        "cogs_ml":     [1_000_000.0, 800_000.0, 2_000_000.0],
        "cogs_other":  [0.0, 0.0, 0.0],
        "cogs_total":  [221_000_000.0, 160_800_000.0, 452_000_000.0],
        "gp_actual":   [64_000_000.0, 39_200_000.0, 98_000_000.0],
    })


def _gold_revenue_df():
    """gold_revenue_monthly per plant."""
    return pd.DataFrame({
        "plant_code": ["1300"],
        "revenue":    [285_000_000.0],
    })


def _pnl_gold_df():
    """gold_gp_by_plant for the pnl endpoint monthly query."""
    return pd.DataFrame({
        "month":      [1, 2, 3],
        "plant_int":  [1300, 1300, 1300],
        "revenue":    [285_000_000.0, 280_000_000.0, 290_000_000.0],
        "gp_actual":  [52_000_000.0, 51_000_000.0, 53_000_000.0],
        "qty_sold_st":[10_000.0, 9_800.0, 10_200.0],
    })


def _pnl_cost_df():
    """v_gl monthly cost aggregation for the pnl endpoint."""
    return pd.DataFrame({
        "month":     [1, 2, 3],
        "rm_cost":   [220_000_000.0, 218_000_000.0, 222_000_000.0],
        "conv_cost": [12_000_000.0, 11_500_000.0, 12_500_000.0],
    })


# ─── Tests: get_cost_ledger ────────────────────────────────────────────────────

@patch("backend.routers.monitor.query_df")
def test_cost_ledger_gl_query_includes_company_code(mock_query_df):
    """
    _query_gl_by_account (called by get_cost_ledger) must pass company_code='1000'
    as the first parameter in v_gl WHERE clause.
    """
    # Call order for get_cost_ledger (plant=1300, year=2026, quarter=1):
    # 1. _query_gl_by_account (cc_prefix="13")     → v_gl
    # 2. _query_production_volume                   → v_production
    # 3. _query_tb_amounts (cc_prefix="13")         → v_gl (no exclusion)
    # 4. _query_mb51_total_dm                       → v_mb51
    # 5. _query_mb51_rm_breakdown                   → v_mb51
    # 6. _build_rm_material_rows → _query (v_mb51)  → v_mb51
    mock_query_df.side_effect = [
        _gl_records_df(),
        _prod_vol_df(),
        _tb_amounts_df(),
        _mb51_total_df(),
        _mb51_breakdown_df(),
        _mb51_itype_df(),
    ]

    result = get_cost_ledger(plant="1300", year=2026, quarter=1, month=None)

    assert mock_query_df.called

    # GL query is call index 0
    gl_call = mock_query_df.call_args_list[0]
    sql    = gl_call[0][0]
    params = gl_call[0][1]

    assert "v_gl" in sql, "cost-ledger should query v_gl"
    assert "company_code" in sql, "v_gl query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"
    assert params[0] == "1000", "company_code '1000' should be the first param"


@patch("backend.routers.monitor.query_df")
def test_cost_ledger_production_volume_includes_company_code(mock_query_df):
    """
    _query_production_volume (called by get_cost_ledger) must include company_code='1000'.
    """
    mock_query_df.side_effect = [
        _gl_records_df(),
        _prod_vol_df(),
        _tb_amounts_df(),
        _mb51_total_df(),
        _mb51_breakdown_df(),
        _mb51_itype_df(),
    ]

    get_cost_ledger(plant="1300", year=2026, quarter=1, month=None)

    # Production volume is call index 1
    prod_call = mock_query_df.call_args_list[1]
    sql    = prod_call[0][0]
    params = prod_call[0][1]

    assert "v_production" in sql, "Should query v_production for volume"
    assert "company_code" in sql, "v_production query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.monitor.query_df")
def test_cost_ledger_response_shape(mock_query_df):
    """Verify get_cost_ledger returns the required response structure."""
    mock_query_df.side_effect = [
        _gl_records_df(),
        _prod_vol_df(),
        _tb_amounts_df(),
        _mb51_total_df(),
        _mb51_breakdown_df(),
        _mb51_itype_df(),
    ]

    result = get_cost_ledger(plant="1300", year=2026, quarter=1, month=None)

    assert result["status"] == "ok"
    assert result["plant"] == "1300"
    assert result["year"] == 2026
    assert result["quarter"] == 1
    assert "data" in result
    assert isinstance(result["data"], list)
    assert "count" in result
    assert result["count"] == len(result["data"])
    assert "meta" in result
    assert "volume" in result["meta"]


# ─── Tests: get_overview ───────────────────────────────────────────────────────

@patch("backend.routers.monitor.query_df")
def test_overview_production_volume_includes_company_code(mock_query_df):
    """
    _query_production_volume (called by get_overview, no plant filter) must include
    company_code='1000'.

    Call order within get_overview (3 plants — 1300, 1100, 1200):
      0. _query_production_volume (all plants)         → v_production
      1. _query_gp_by_plant (all plants)               → gold_gp_by_plant (no company_code)
      2. plant 1300: _query_gl_by_account              → v_gl
      3. plant 1300: _query_tb_amounts (_check_tb_data)→ v_gl
      4. plant 1100: _query_gl_by_account              → v_gl
      5. plant 1100: _query_tb_amounts                 → v_gl
      6. plant 1200: _query_gl_by_account              → v_gl
      7. plant 1200: _query_tb_amounts                 → v_gl
    """
    mock_query_df.side_effect = [
        _prod_vol_df(),             # 0: all-plant volume
        _gold_gp_df(),              # 1: gold_gp_by_plant
        _gl_records_df(),           # 2: plant 1300 GL
        _tb_amounts_df(),           # 3: plant 1300 TB
        _gl_records_df(),           # 4: plant 1100 GL
        _tb_amounts_df(),           # 5: plant 1100 TB
        _gl_records_df(),           # 6: plant 1200 GL
        _tb_amounts_df(),           # 7: plant 1200 TB
    ]

    result = get_overview(year=2026, quarter=1)

    # Production volume call (index 0)
    prod_call = mock_query_df.call_args_list[0]
    sql    = prod_call[0][0]
    params = prod_call[0][1]

    assert "v_production" in sql, "overview should query v_production"
    assert "company_code" in sql, "v_production query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.monitor.query_df")
def test_overview_gl_query_includes_company_code(mock_query_df):
    """
    _query_gl_by_account (called per-plant in get_overview) must include company_code='1000'.
    """
    mock_query_df.side_effect = [
        _prod_vol_df(),
        _gold_gp_df(),
        _gl_records_df(),   # plant 1300 GL (index 2)
        _tb_amounts_df(),   # plant 1300 TB
        _gl_records_df(),   # plant 1100 GL
        _tb_amounts_df(),   # plant 1100 TB
        _gl_records_df(),   # plant 1200 GL
        _tb_amounts_df(),   # plant 1200 TB
    ]

    result = get_overview(year=2026, quarter=1)

    # First GL query is call index 2 (after volume + gp)
    gl_call = mock_query_df.call_args_list[2]
    sql    = gl_call[0][0]
    params = gl_call[0][1]

    assert "v_gl" in sql, "overview should query v_gl per plant"
    assert "company_code" in sql, "v_gl query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.monitor.query_df")
def test_overview_response_shape(mock_query_df):
    """Verify get_overview returns the required response structure."""
    mock_query_df.side_effect = [
        _prod_vol_df(),
        _gold_gp_df(),
        _gl_records_df(),   # plant 1300 GL
        _tb_amounts_df(),   # plant 1300 TB
        _gl_records_df(),   # plant 1100 GL
        _tb_amounts_df(),   # plant 1100 TB
        _gl_records_df(),   # plant 1200 GL
        _tb_amounts_df(),   # plant 1200 TB
    ]

    result = get_overview(year=2026, quarter=1)

    assert result["status"] == "ok"
    assert result["year"] == 2026
    assert result["quarter"] == 1
    assert "plants" in result
    assert isinstance(result["plants"], list)
    assert len(result["plants"]) == 3   # Always 3 plants (1300, 1100, 1200)
    assert "alerts" in result

    # Check per-plant keys
    plant_row = result["plants"][0]
    assert "plant" in plant_row
    assert "rmCost" in plant_row
    assert "convCost" in plant_row
    assert "volume" in plant_row


# ─── Tests: get_pnl ───────────────────────────────────────────────────────────

@patch("backend.routers.monitor.query_df")
def test_pnl_gl_cost_includes_company_code(mock_query_df):
    """
    The direct query_df call in get_pnl for monthly GL cost aggregation must include
    company_code='1000' as the first parameter.
    """
    # Call order for get_pnl (year=2026, quarter=1):
    # 1. gold_gp_by_plant (direct SELECT)         → no company_code (Gold layer)
    # 2. v_gl monthly cost aggregation (direct)   → company_code REQUIRED
    # 3. _query_gp_by_plant (all plants)          → gold_gp_by_plant (no company_code)
    # 4. _query_production_volume (all plants)    → v_production (company_code REQUIRED)
    # 5-7. _query_gl_by_account per plant         → v_gl (company_code REQUIRED)
    mock_query_df.side_effect = [
        _pnl_gold_df(),                                                # gold_gp_by_plant monthly
        _pnl_cost_df(),                                                # v_gl monthly cost
        _gold_gp_df(),                                                 # _query_gp_by_plant all plants
        pd.DataFrame({"Plant": ["1300","1100","1200"],                 # _query_production_volume
                      "total_qty_mt": [11_000.0, 8_000.0, 22_000.0]}),
        _gl_records_df(),   # _query_gl_by_account plant 1300
        _gl_records_df(),   # _query_gl_by_account plant 1100
        _gl_records_df(),   # _query_gl_by_account plant 1200
    ]

    result = get_pnl(year=2026, quarter=1)

    # v_gl cost call is index 1
    cost_call = mock_query_df.call_args_list[1]
    sql    = cost_call[0][0]
    params = cost_call[0][1]

    assert "v_gl" in sql, "pnl should query v_gl for monthly costs"
    assert "company_code" in sql, "v_gl query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"
    assert params[0] == "1000", "company_code '1000' should be the first param in v_gl cost query"


@patch("backend.routers.monitor.query_df")
def test_pnl_production_volume_includes_company_code(mock_query_df):
    """
    _query_production_volume inside get_pnl must include company_code='1000'.
    """
    mock_query_df.side_effect = [
        _pnl_gold_df(),
        _pnl_cost_df(),
        _gold_gp_df(),
        pd.DataFrame({"Plant": ["1300"], "total_qty_mt": [11_000.0]}),
        _gl_records_df(),
        _gl_records_df(),
        _gl_records_df(),
    ]

    get_pnl(year=2026, quarter=1)

    # Production volume call is index 3
    prod_call = mock_query_df.call_args_list[3]
    sql    = prod_call[0][0]
    params = prod_call[0][1]

    assert "v_production" in sql, "pnl should query v_production for volume"
    assert "company_code" in sql, "v_production query should have company_code filter"
    assert "1000" in params, "Params should contain '1000' for company_code"


@patch("backend.routers.monitor.query_df")
def test_pnl_response_shape(mock_query_df):
    """Verify get_pnl returns the required response structure."""
    mock_query_df.side_effect = [
        _pnl_gold_df(),
        _pnl_cost_df(),
        _gold_gp_df(),
        pd.DataFrame({"Plant": ["1300"], "total_qty_mt": [11_000.0]}),
        _gl_records_df(),
        _gl_records_df(),
        _gl_records_df(),
    ]

    result = get_pnl(year=2026, quarter=1)

    assert result["status"] == "ok"
    assert result["year"] == 2026
    assert result["quarter"] == 1
    assert "monthlyPnl" in result
    assert "products" in result
    assert isinstance(result["monthlyPnl"], list)
    assert len(result["monthlyPnl"]) == 3   # Q1 = Jan, Feb, Mar

    # Check monthly P&L row keys
    row = result["monthlyPnl"][0]
    assert "label" in row
    assert "month" in row
    assert "revenue" in row
    assert "rmCost" in row
    assert "convCost" in row
    assert "gp" in row
