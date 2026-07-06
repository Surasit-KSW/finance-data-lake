"""tests/test_cashflow.py — ETL + router tests for cashflow plan."""
import pytest
import pandas as pd
import openpyxl
from pathlib import Path
from datetime import date
from silver_transform.etl_cashflow_plan import CashflowPlanETL

# ── ETL Tests ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_bronze(tmp_path):
    """Create a minimal Bronze Excel in a temp dir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["date", "type", "amount", "note"])
    ws.append(["04/07/2026", "receipt", 12500000, "AR test"])
    ws.append(["07/07/2026", "payment", 8200000,  "AP test"])
    ws.append(["bad-date",   "receipt", 9999,      "skip me"])   # invalid row
    p = tmp_path / "cashflow_plan_2026.xlsx"
    wb.save(str(p))
    return tmp_path


def test_etl_cashflow_plan_happy_path(tmp_bronze, tmp_path):
    """ETL converts valid Excel rows to parquet with correct schema."""
    silver = tmp_path / "silver"
    silver.mkdir()
    etl = CashflowPlanETL(bronze_path=tmp_bronze, silver_path=silver, year=2026)
    result = etl.run()

    assert result["status"] == "ok"
    assert result["rows"] == 2   # bad-date row skipped

    out = silver / "cashflow_plan_2026.parquet"
    assert out.exists()
    df = pd.read_parquet(out)
    assert list(df.columns) == ["date", "type", "amount_thb", "note", "year"]
    assert df["amount_thb"].iloc[0] == 12_500_000.0
    assert df["amount_thb"].iloc[1] == -8_200_000.0   # payment → negative


def test_etl_cashflow_plan_missing_file(tmp_path):
    """ETL returns status='skipped' and 0 rows when Bronze file absent."""
    silver = tmp_path / "silver"
    silver.mkdir()
    bronze = tmp_path / "empty_bronze"
    bronze.mkdir()
    etl = CashflowPlanETL(bronze_path=bronze, silver_path=silver, year=2026)
    result = etl.run()
    assert result["status"] == "skipped"
    assert result["rows"] == 0
