import pandas as pd
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_Data_Pipelines" / "silver_transform"))
from etl_sales import SalesTransformETL


@pytest.fixture
def raw_sales_df():
    return pd.DataFrame({
        "Billing Document": ["5000001", "5000002"],
        "Net Value(THB)": ["100,000.00", "200,000.00"],
        "Quantity": ["10.0", "20.0"],
        "Material Description": ["Product A", "Product B"],
        "Source_File": ["sale_2025_01.XLSX", "sale_2025_01.XLSX"],
        "Year": [2025, 2025],
        "Month": [1, 1],
    })


@pytest.fixture
def etl(tmp_path):
    return SalesTransformETL(
        company_code="1000",
        bronze_sales_path=tmp_path / "bronze_sales",
        silver_path=tmp_path / "silver",
    )


def test_transform_cleans_numeric_columns(etl, raw_sales_df):
    result = etl.transform(raw_sales_df)
    assert result["Net_Value_THB"].iloc[0] == pytest.approx(100000.0)


def test_transform_renames_net_value_to_canonical(etl, raw_sales_df):
    result = etl.transform(raw_sales_df)
    assert "Net_Value_THB" in result.columns
    assert "Net Value(THB)" not in result.columns
    assert result["Net_Value_THB"].iloc[0] == pytest.approx(100000.0)


def test_output_path_uses_company_code(etl, tmp_path):
    assert etl._output_path().name == "master_sales_1000.parquet"


def test_run_skips_when_no_bronze(etl):
    result = etl.run()
    assert result["status"] == "skipped"
