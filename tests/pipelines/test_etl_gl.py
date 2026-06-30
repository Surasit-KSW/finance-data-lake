import pandas as pd
import pytest
from pathlib import Path
from core.base_etl import BaseSilverETL

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_Data_Pipelines" / "silver_transform"))
from etl_gl import GLTransformETL


@pytest.fixture
def raw_gl_df():
    """Minimal SAP FBL3N layout DataFrame"""
    return pd.DataFrame({
        "G/L Account": ["5411010", "5411010"],
        "G/L Account: Long Text": ["RM GI", "RM GI"],
        "Posting Date": ["01.01.2025", "15.02.2025"],
        "Amount in LC": ["1,234.56", "2,000.00"],
        "Cost Center": ["130001", "130001"],
        "Document Number": ["100001", "100002"],
        "Source_File": ["gl_2025_01.XLSX", "gl_2025_02.XLSX"],
    })


@pytest.fixture
def etl(tmp_path):
    return GLTransformETL(
        company_code="1000",
        bronze_gl_path=tmp_path / "bronze_gl",
        silver_path=tmp_path / "silver",
    )


def test_transform_derives_year_month(etl, raw_gl_df):
    result = etl.transform(raw_gl_df)
    assert "Year" in result.columns
    assert "Month" in result.columns
    assert result["Year"].iloc[0] == 2025
    assert result["Month"].iloc[0] == 1


def test_transform_maps_amount_in_lc_to_net_amount(etl, raw_gl_df):
    result = etl.transform(raw_gl_df)
    assert "Net_Amount" in result.columns
    assert result["Net_Amount"].iloc[0] == pytest.approx(1234.56)
    assert result["Net_Amount"].iloc[1] == pytest.approx(2000.00)


def test_transform_handles_amount_alias(etl):
    df = pd.DataFrame({
        "G/L Account": ["5411010"],
        "Posting Date": ["01.01.2025"],
        "Net Amount": ["500.00"],  # different alias
    })
    result = etl.transform(df)
    assert "Net_Amount" in result.columns
    assert result["Net_Amount"].iloc[0] == pytest.approx(500.00)


def test_transform_coerces_date_cols_to_str(etl, raw_gl_df):
    result = etl.transform(raw_gl_df)
    date_cols = [c for c in result.columns if "DATE" in c.upper()]
    for col in date_cols:
        assert result[col].dtype == object, f"{col} should be str"


def test_output_path_uses_company_code(etl, tmp_path):
    path = etl._output_path()
    assert path.name == "master_gl_1000.parquet"
    assert path.parent == tmp_path / "silver"


def test_run_skips_when_no_bronze_files(etl):
    result = etl.run()
    assert result["status"] == "skipped"
    assert result["rows_in"] == 0


def test_transform_preserves_gl_account_column_name(tmp_path):
    """transform() must keep 'G/L Account' as-is — routers use this column name in SQL."""
    etl = GLTransformETL(company_code="1000", bronze_gl_path=tmp_path, silver_path=tmp_path, year=None)
    df = pd.DataFrame({
        "G/L Account": ["5411010", "5411020"],
        "Text": ["Entry A", "Entry B"],
        "Net Amount": [1000.0, 2000.0],
        "Posting Date": ["01.01.2025", "15.01.2025"],
    })
    result = etl.transform(df)
    assert "G/L Account" in result.columns
    assert "GL_Account" not in result.columns
