import pandas as pd
import pytest
from core.validators import SilverValidator


@pytest.fixture
def validator():
    return SilverValidator()


def _gl_df(**overrides):
    data = {
        "company_code": ["1000"],
        "Year": [2025],
        "Month": [1],
        "GL_Account": ["5411010"],
        "Net_Amount": [1000.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_valid_gl_returns_no_warnings(validator):
    df = _gl_df()
    assert validator.validate(df, "gl") == []


def test_missing_required_column_returns_warning(validator):
    df = _gl_df()
    df = df.drop(columns=["Net_Amount"])
    warnings = validator.validate(df, "gl")
    assert any("Net_Amount" in w for w in warnings)


def test_null_key_column_returns_warning(validator):
    df = _gl_df()
    df.loc[0, "Year"] = None
    warnings = validator.validate(df, "gl")
    assert any("Year" in w for w in warnings)


def test_empty_df_returns_warning(validator):
    df = pd.DataFrame()
    warnings = validator.validate(df, "gl")
    assert any("Row count" in w for w in warnings)


def test_valid_sales_df(validator):
    df = pd.DataFrame({
        "company_code": ["1000"],
        "Year": [2025],
        "Month": [3],
        "Net_Value_THB": [50000.0],
    })
    assert validator.validate(df, "sales") == []


def test_valid_production_df(validator):
    df = pd.DataFrame({
        "company_code": ["1000"],
        "Year": [2025],
        "Month": [3],
        "Plant": ["1300"],
        "GR_Qty": [100.0],
    })
    assert validator.validate(df, "production") == []


def test_valid_ar_df(validator):
    df = pd.DataFrame({
        "company_code": ["1000"],
        "GL_Account": ["1121010"],
        "Net_Amount": [5000.0],
    })
    assert validator.validate(df, "ar") == []
