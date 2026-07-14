"""
tests/test_close.py
====================
Tests for the close orchestrator status endpoint (/api/v1/close/...).

POST /tick persists the full tick payload to a JSON cache file (atomic
write); GET /status reads it back verbatim, or returns a safe placeholder
if no tick has ever run.
"""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import close as close_router

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_status_file(tmp_path, monkeypatch):
    """Point _status_path() at a temp file so tests never touch the real cache."""
    fake_path = tmp_path / "close_status_current.json"
    monkeypatch.setattr(close_router, "_status_path", lambda: fake_path)
    return fake_path


def _sample_payload():
    return {
        "company": "1000",
        "year": 2026,
        "month": 6,
        "blocked_reason": None,
        "checklist": {"tb_balanced": True},
        "readiness": {"gl": True, "ksb1": False},
        "extract_attempts": {"ksb1": 1},
        "anomalies": [
            {"source": "GL", "pattern": "x", "auto_corrected": False, "detail": "d"},
        ],
        "tick_log": ["[check_readiness] ok"],
        "tick_duration_sec": 12.3,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "close_tasks": [
            {"id": "tb_balanced", "name": "Trial Balance สมดุล", "status": "done",
             "time": "13:00", "linkTo": "/finance/close-control-tower"},
        ],
    }


def test_status_returns_never_run_placeholder_before_any_tick():
    resp = client.get("/api/v1/close/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["never_run"] is True
    assert body["close_tasks"] == []
    assert body["year"] is None


def test_post_tick_then_get_status_round_trips_same_data():
    payload = _sample_payload()
    post_resp = client.post("/api/v1/close/tick", json=payload)
    assert post_resp.status_code == 200
    assert post_resp.json() == {"status": "ok"}

    get_resp = client.get("/api/v1/close/status")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["year"] == 2026
    assert body["month"] == 6
    assert body["checklist"] == {"tb_balanced": True}
    assert body["close_tasks"][0]["name"] == "Trial Balance สมดุล"


def test_post_tick_malformed_body_returns_422():
    resp = client.post("/api/v1/close/tick", json={"company": "1000"})  # missing required fields
    assert resp.status_code == 422


def test_post_tick_writes_atomically(isolated_status_file):
    payload = _sample_payload()
    client.post("/api/v1/close/tick", json=payload)
    assert isolated_status_file.exists()
    on_disk = json.loads(isolated_status_file.read_text(encoding="utf-8"))
    assert on_disk["year"] == 2026
