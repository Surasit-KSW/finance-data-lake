import pandas as pd
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_Data_Pipelines" / "silver_transform"))
from etl_production import ProductionTransformETL


@pytest.fixture
def etl(tmp_path):
    return ProductionTransformETL(
        company_code="1000",
        bronze_prod_path=tmp_path / "bronze_prod",
        silver_path=tmp_path / "silver",
    )


def test_parse_plant_month_old_format(etl):
    plant, year, month = etl._parse_filename("1300_2025_07.XLSX")
    assert plant == "1300"
    assert year == 2025
    assert month == 7


def test_parse_plant_month_new_format(etl):
    plant, year, month = etl._parse_filename("1300.01.2026.XLSX")
    assert plant == "1300"
    assert year == 2026
    assert month == 1


def test_parse_plant_month_no_match(etl):
    assert etl._parse_filename("random_file.xlsx") == (None, None, None)


def test_output_path_uses_company_code(etl, tmp_path):
    assert etl._output_path().name == "master_production_1000.parquet"


def test_run_skips_when_no_bronze(etl):
    result = etl.run()
    assert result["status"] == "skipped"


def test_transform_renames_gr_qty_column(etl):
    """transform() must rename 'Actual GR QTY' to canonical 'GR_Qty'."""
    df = pd.DataFrame({
        "Actual GR QTY": [100.0, 200.0],
        "Plant": ["1300", "1300"],
        "Year": [2025, 2025],
        "Month": [1, 2],
    })
    result = etl.transform(df)
    assert "GR_Qty" in result.columns, "GR_Qty must be in output columns"
    assert "Actual GR QTY" not in result.columns, "Raw column name must be renamed"


def test_transform_renames_byproduct_columns(etl):
    """transform() must rename ByProduct Scrap, Grade B, Grade C to canonical names."""
    df = pd.DataFrame({
        "Actual GR QTY": [100.0],
        "Actual ByProduct Scrap QTY": [5.0],
        "Actual ByProduct Grade B QTY": [2.0],
        "Actual ByProduct Grade C QTY": [1.0],
        "Plant": ["1100"],
        "Year": [2025],
        "Month": [3],
    })
    result = etl.transform(df)
    assert "GR_Qty" in result.columns
    assert "ByProduct_Scrap" in result.columns
    assert "Grade_B" in result.columns
    assert "Grade_C" in result.columns


def test_save_deletes_old_per_year_files(etl, tmp_path):
    """_save() must delete master_production_20??.parquet files before writing."""
    silver = tmp_path / "silver"
    silver.mkdir()
    old_file = silver / "master_production_2024.parquet"
    # Create a dummy old file
    pd.DataFrame({"x": [1]}).to_parquet(old_file, index=False)
    assert old_file.exists()

    df = pd.DataFrame({
        "company_code": ["1000"],
        "Plant": ["1300"],
        "Year": [2025],
        "Month": [1],
        "GR_Qty": [100.0],
    })
    etl._save(df)
    assert not old_file.exists(), "Old per-year file must be deleted"
    assert etl._output_path().exists(), "New company_code file must be written"
