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


# ── Router Tests ─────────────────────────────────────────────────────────────

import pandas as pd
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

TODAY = date.today().isoformat()
FROM_DATE = TODAY
TO_DATE   = TODAY


def _ar_df():
    return pd.DataFrame([{
        "customer":       "CUST001",
        "customer_name":  "บ.ABC จำกัด",
        "due_date":        pd.Timestamp(TODAY),
        "amount":          12_500_000.0,
        "doc_no":          "1800000001",
        "clearing_date":   pd.Timestamp(TODAY),
        "company_code":    "1000",
    }])


def _ap_df():
    return pd.DataFrame([{
        "vendor":         "VEND001",
        "vendor_name":    "บ.XYZ จำกัด",
        "posting_date":   pd.Timestamp(TODAY),
        "amount":         -8_200_000.0,
        "doc_no":         "1900000001",
        "company_code":   "1000",
    }])


def test_cashflow_plan_returns_items():
    """Router returns items list + opening_balance with correct types."""
    with patch("backend.routers.cashflow.query_df") as mock_qdf, \
         patch("backend.routers.cashflow._load_parquet_safe", return_value=pd.DataFrame()):
        mock_qdf.side_effect = lambda sql, *a, **kw: (
            _ar_df() if "v_ar" in sql else _ap_df()
        )
        resp = client.get(f"/api/v1/cashflow/plan?from={FROM_DATE}&to={TO_DATE}")

    assert resp.status_code == 200
    body = resp.json()
    assert "opening_balance" in body
    assert "items" in body
    assert isinstance(body["items"], list)
    assert body["usingMock"] is False


def test_cashflow_plan_ar_status_actual():
    """AR item with Clearing Date ≤ today → status='actual'."""
    with patch("backend.routers.cashflow.query_df") as mock_qdf, \
         patch("backend.routers.cashflow._load_parquet_safe", return_value=pd.DataFrame()):
        mock_qdf.side_effect = lambda sql, *a, **kw: (
            _ar_df() if "v_ar" in sql else pd.DataFrame()
        )
        resp = client.get(f"/api/v1/cashflow/plan?from={FROM_DATE}&to={TO_DATE}")

    items = resp.json()["items"]
    ar_items = [i for i in items if i["type"] == "ar"]
    assert len(ar_items) == 1
    assert ar_items[0]["status"] == "actual"
    assert ar_items[0]["amount_thb"] > 0


def test_cashflow_plan_ap_always_plan():
    """AP items from v_ap (no clearing info) → status='plan'."""
    with patch("backend.routers.cashflow.query_df") as mock_qdf, \
         patch("backend.routers.cashflow._load_parquet_safe", return_value=pd.DataFrame()):
        mock_qdf.side_effect = lambda sql, *a, **kw: (
            pd.DataFrame() if "v_ar" in sql else _ap_df()
        )
        resp = client.get(f"/api/v1/cashflow/plan?from={FROM_DATE}&to={TO_DATE}")

    items = resp.json()["items"]
    ap_items = [i for i in items if i["type"] == "ap"]
    assert len(ap_items) == 1
    assert ap_items[0]["status"] == "plan"
    assert ap_items[0]["amount_thb"] < 0
