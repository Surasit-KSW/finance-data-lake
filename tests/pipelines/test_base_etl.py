import pandas as pd
import pytest
from pathlib import Path
from core.base_etl import BaseSilverETL


class ConcreteETL(BaseSilverETL):
    """Minimal concrete subclass for testing BaseSilverETL"""
    def extract(self) -> pd.DataFrame:
        return pd.DataFrame({
            "G/L Account": ["5411010"],
            "Amount in LC": ["1,234.56"],
            "  Posting Date  ": ["01.01.2025"],
        })

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.normalize_columns(df)
        df = self.map_amount_column(df)
        df = self.clean_numeric(df, ["AMOUNT"])
        return df

    def _output_path(self) -> Path:
        return Path("/tmp/test_output.parquet")


@pytest.fixture
def etl(tmp_path):
    return ConcreteETL(
        company_code="1000",
        domain="gl",
        silver_path=tmp_path,
    )


def test_normalize_columns_strips_whitespace(etl):
    df = pd.DataFrame({"  Col A  ": [1], " Col B": [2]})
    result = etl.normalize_columns(df)
    assert list(result.columns) == ["Col A", "Col B"]


def test_clean_numeric_removes_commas(etl):
    df = pd.DataFrame({"Net_Amount": ["1,234.56", "2,000.00"]})
    result = etl.clean_numeric(df, ["AMOUNT"])
    assert result["Net_Amount"].iloc[0] == pytest.approx(1234.56)
    assert result["Net_Amount"].iloc[1] == pytest.approx(2000.00)


def test_clean_numeric_coerces_invalid_to_nan(etl):
    df = pd.DataFrame({"Net_Amount": ["N/A", ""]})
    result = etl.clean_numeric(df, ["AMOUNT"])
    assert result["Net_Amount"].isna().all()


def test_map_amount_column_renames_alias(etl):
    df = pd.DataFrame({"Amount in LC": [100.0], "Other": ["x"]})
    result = etl.map_amount_column(df)
    assert "Net_Amount" in result.columns
    assert "Amount in LC" not in result.columns


def test_map_amount_column_no_match_leaves_df_unchanged(etl):
    df = pd.DataFrame({"SomeOtherCol": [100.0]})
    result = etl.map_amount_column(df)
    assert "Net_Amount" not in result.columns
    assert "SomeOtherCol" in result.columns


def test_add_company_code_inserts_first(etl):
    df = pd.DataFrame({"Year": [2025], "Month": [1]})
    result = etl.add_company_code(df)
    assert result.columns[0] == "company_code"
    assert result["company_code"].iloc[0] == "1000"


def test_run_returns_result_dict(etl):
    result = etl.run()
    assert result["company_code"] == "1000"
    assert result["domain"] == "gl"
    assert isinstance(result["rows_in"], int)
    assert isinstance(result["rows_out"], int)
    assert isinstance(result["warnings"], list)
    assert result["status"] in ("success", "warning", "skipped")


def test_run_skipped_when_extract_returns_empty(tmp_path):
    class EmptyETL(BaseSilverETL):
        def extract(self): return pd.DataFrame()
        def transform(self, df): return df
        def _output_path(self): return tmp_path / "empty.parquet"

    etl = EmptyETL("1000", "gl", tmp_path)
    result = etl.run()
    assert result["status"] == "skipped"
    assert result["rows_in"] == 0
