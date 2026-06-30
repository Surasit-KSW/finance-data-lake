"""
tests/test_gl_detail.py
=======================
Tests for GL detail endpoints to verify company_code filter is applied.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from backend.routers.gl_detail import (
    gl_transactions,
    gl_account_balance,
    list_gl_accounts,
)


@pytest.fixture
def mock_df():
    """Create a mock DataFrame response."""
    return pd.DataFrame({
        "posting_date": ["2025-01-15"],
        "account_code": ["4111010"],
        "account_name": ["Revenue"],
        "amount": [10000.0],
        "description": ["Sale"],
        "doc_number": ["1000123"],
        "cost_center": ["CC001"],
        "source_file": ["file.xlsx"],
        "Month": [1],
        "Year": [2025],
    })


@patch("backend.routers.gl_detail.query_df")
def test_gl_transactions_includes_company_code(mock_query_df, mock_df):
    """Verify gl_transactions adds company_code = '1000' to SQL conditions."""
    mock_query_df.return_value = mock_df

    # Call the endpoint with year only
    result = gl_transactions(year=2025, month=None, account=None, limit=500)

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    # Extract the SQL and params from the call
    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code filter is in the SQL WHERE clause
    assert "company_code" in sql, "SQL should contain company_code filter"
    assert "WHERE" in sql, "SQL should have WHERE clause"

    # Verify '1000' is in params
    assert "1000" in params, "Params should contain '1000' company code"
    assert 2025 in params, "Params should contain year"


@patch("backend.routers.gl_detail.query_df")
def test_gl_transactions_with_month_and_account(mock_query_df, mock_df):
    """Verify gl_transactions with month and account also includes company_code."""
    mock_query_df.return_value = mock_df

    result = gl_transactions(year=2025, month=3, account="4111010", limit=500)

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code is in params and is first
    assert "1000" in params, "Params should contain '1000' company code"
    assert params[0] == "1000", "First param should be '1000' company code"


@patch("backend.routers.gl_detail.query_df")
def test_gl_account_balance_includes_company_code(mock_query_df, mock_df):
    """Verify gl_account_balance adds company_code = '1000' to SQL conditions."""
    # Create a mock with Year and Month columns for balance endpoint
    mock_balance_df = pd.DataFrame({
        "Year": [2025],
        "Month": [1],
        "account_code": ["4111010"],
        "account_name": ["Revenue"],
        "period_balance": [10000.0],
        "transaction_count": [5],
    })
    mock_query_df.return_value = mock_balance_df

    result = gl_account_balance(account="4111010", year=2025)

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code filter is in the SQL
    assert "company_code" in sql, "SQL should contain company_code filter"
    assert "1000" in params, "Params should contain '1000' company code"


@patch("backend.routers.gl_detail.query_df")
def test_gl_account_balance_without_year(mock_query_df, mock_df):
    """Verify gl_account_balance works without year filter."""
    mock_balance_df = pd.DataFrame({
        "Year": [2024, 2025],
        "Month": [12, 1],
        "account_code": ["4111010", "4111010"],
        "account_name": ["Revenue", "Revenue"],
        "period_balance": [5000.0, 10000.0],
        "transaction_count": [3, 5],
    })
    mock_query_df.return_value = mock_balance_df

    result = gl_account_balance(account="4111010", year=None)

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code is present and account is in params
    assert "company_code" in sql, "SQL should contain company_code filter"
    assert "1000" in params, "Params should contain '1000' company code"
    assert "4111010" in params, "Params should contain account"


@patch("backend.routers.gl_detail.query_df")
def test_list_gl_accounts_includes_company_code(mock_query_df, mock_df):
    """Verify list_gl_accounts adds company_code = '1000' to SQL conditions."""
    mock_accounts_df = pd.DataFrame({
        "account_code": ["4111010", "4121010"],
        "account_name": ["Revenue", "Other Income"],
        "total_balance": [100000.0, 5000.0],
        "transactions": [50, 10],
    })
    mock_query_df.return_value = mock_accounts_df

    result = list_gl_accounts(year=2025, search=None)

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code filter is in the SQL
    assert "company_code" in sql, "SQL should contain company_code filter"
    assert "1000" in params, "Params should contain '1000' company code"
    assert 2025 in params, "Params should contain year"


@patch("backend.routers.gl_detail.query_df")
def test_list_gl_accounts_with_search(mock_query_df, mock_df):
    """Verify list_gl_accounts with search includes company_code."""
    mock_accounts_df = pd.DataFrame({
        "account_code": ["4111010"],
        "account_name": ["Revenue"],
        "total_balance": [100000.0],
        "transactions": [50],
    })
    mock_query_df.return_value = mock_accounts_df

    result = list_gl_accounts(year=2025, search="Revenue")

    # Verify query_df was called
    assert mock_query_df.called
    call_args = mock_query_df.call_args

    sql = call_args[0][0]
    params = call_args[0][1]

    # Verify company_code is in params
    assert "1000" in params, "Params should contain '1000' company code"
    # Verify search parameter is also in params
    assert "%Revenue%" in params or any("Revenue" in str(p) for p in params), "Search param should be in params"


@patch("backend.routers.gl_detail.query_df")
def test_response_format_gl_transactions(mock_query_df, mock_df):
    """Verify gl_transactions response format is correct."""
    mock_query_df.return_value = mock_df

    result = gl_transactions(year=2025, month=None, account=None, limit=500)

    # Check response structure
    assert result["status"] == "ok"
    assert result["year"] == 2025
    assert result["count"] == 1
    assert "data" in result
    assert isinstance(result["data"], list)
    assert len(result["data"]) == 1


@patch("backend.routers.gl_detail.query_df")
def test_response_format_gl_account_balance(mock_query_df):
    """Verify gl_account_balance response format is correct."""
    mock_balance_df = pd.DataFrame({
        "Year": [2025],
        "Month": [1],
        "account_code": ["4111010"],
        "account_name": ["Revenue"],
        "period_balance": [10000.0],
        "transaction_count": [5],
    })
    mock_query_df.return_value = mock_balance_df

    result = gl_account_balance(account="4111010", year=2025)

    # Check response structure
    assert result["status"] == "ok"
    assert result["account"] == "4111010"
    assert "total_balance" in result
    assert result["total_balance"] == 10000.0
    assert result["count"] == 1
    assert "data" in result


@patch("backend.routers.gl_detail.query_df")
def test_response_format_list_gl_accounts(mock_query_df):
    """Verify list_gl_accounts response format is correct."""
    mock_accounts_df = pd.DataFrame({
        "account_code": ["4111010"],
        "account_name": ["Revenue"],
        "total_balance": [100000.0],
        "transactions": [50],
    })
    mock_query_df.return_value = mock_accounts_df

    result = list_gl_accounts(year=2025, search=None)

    # Check response structure
    assert result["status"] == "ok"
    assert result["year"] == 2025
    assert result["count"] == 1
    assert "data" in result
    assert isinstance(result["data"], list)
