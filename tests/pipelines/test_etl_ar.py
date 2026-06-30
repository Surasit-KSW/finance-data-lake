import pandas as pd
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_Data_Pipelines" / "silver_transform"))
from etl_ar import ARTransformETL


@pytest.fixture
def raw_ar_df():
    return pd.DataFrame({
        "GL Account": ["1121010", "1121010"],
        "Customer": ["CUST001", "CUST002"],
        "Net Amount": ["50,000.00", "30,000.00"],
        "Due Date": ["31.01.2025", "28.02.2025"],
        "Source_File": ["AR_2025.XLSX", "AR_2025.XLSX"],
    })


@pytest.fixture
def etl(tmp_path):
    return ARTransformETL(
        company_code="1000",
        bronze_ar_path=tmp_path / "bronze_ar",
        silver_path=tmp_path / "silver",
    )


def test_transform_cleans_amount_column(etl, raw_ar_df):
    result = etl.transform(raw_ar_df)
    assert result["Net_Amount"].iloc[0] == pytest.approx(50000.0)


def test_transform_renames_gl_account_to_canonical(etl, raw_ar_df):
    """transform() must rename 'GL Account' → 'GL_Account' (canonical Silver schema name)"""
    result = etl.transform(raw_ar_df)
    assert "GL_Account" in result.columns
    assert "GL Account" not in result.columns


def test_output_path_uses_company_code(etl, tmp_path):
    assert etl._output_path().name == "master_ar_1000.parquet"


def test_run_skips_when_no_bronze(etl):
    result = etl.run()
    assert result["status"] == "skipped"
