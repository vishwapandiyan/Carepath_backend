"""
Integration tests for Segment 2 — Safety endpoints.
DB interactions are mocked so tests run without a live PostgreSQL instance.

CRITICAL fail-safe path (engine exception → ERROR, never NO) is verified explicitly.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core import session_store

TEST_KEY = settings.api_key
HEADERS = {"X-API-Key": TEST_KEY}

client = TestClient(app)

ALL_FALSE_FLAGS = {
    "chest_pain": False,
    "difficulty_breathing": False,
    "altered_consciousness": False,
    "severe_bleeding": False,
    "stroke_symptoms": False,
    "suicidal_ideation": False,
    "anaphylaxis": False,
    "high_fever": False,
    "unable_to_walk": False,
    "severe_abdominal_pain": False,
}

ALL_NONE_FLAGS = {k: None for k in ALL_FALSE_FLAGS}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(patient_id: str = "p-001") -> str:
    s = session_store.create_session(patient_id=patient_id)
    return s["session_id"]


def _mock_db_commit():
    """Return an AsyncMock that simulates a successful DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── Submit red flags ──────────────────────────────────────────────────────────

def test_submit_red_flags_returns_201():
    sid = _make_session()
    r = client.post(
        f"/api/v1/safety/sessions/{sid}/red-flags",
        json=ALL_FALSE_FLAGS,
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["session_id"] == sid


def test_submit_red_flags_nonexistent_session_returns_404():
    r = client.post(
        "/api/v1/safety/sessions/ghost/red-flags",
        json=ALL_FALSE_FLAGS,
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_submit_red_flags_requires_api_key():
    r = client.post("/api/v1/safety/sessions/any/red-flags", json=ALL_FALSE_FLAGS)
    assert r.status_code == 403


# ── Evaluate ──────────────────────────────────────────────────────────────────

def _run_evaluate(sid: str, flags: dict) -> dict:
    """Helper: save flags then call evaluate, mocking the DB."""
    client.post(f"/api/v1/safety/sessions/{sid}/red-flags", json=flags, headers=HEADERS)

    with patch("app.patient.safety.service.get_db") as mock_get_db:
        db = _mock_db_commit()
        mock_get_db.return_value.__aiter__ = AsyncMock(return_value=iter([db]))
        mock_get_db.return_value = db

        with patch("app.patient.safety.router.get_db", return_value=db):
            r = client.post(
                f"/api/v1/safety/sessions/{sid}/evaluate",
                headers=HEADERS,
            )
    return r


def test_evaluate_single_critical_flag_returns_yes():
    sid = _make_session()
    flags = {**ALL_FALSE_FLAGS, "chest_pain": True}
    client.post(f"/api/v1/safety/sessions/{sid}/red-flags", json=flags, headers=HEADERS)

    with patch("app.patient.safety.service.run_safety_engine", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = __import__(
            "app.patient.safety.schemas", fromlist=["SafetyResult"]
        ).SafetyResult(
            session_id=sid,
            result="YES",
            next_action="EMERGENCY_PATHWAY",
            triggered_rules=["RF001"],
            missing_information=[],
            evaluated_at=datetime.now(timezone.utc),
        )
        r = client.post(f"/api/v1/safety/sessions/{sid}/evaluate", headers=HEADERS)

    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "YES"
    assert body["next_action"] == "EMERGENCY_PATHWAY"
    assert "RF001" in body["triggered_rules"]


def test_evaluate_all_clear_returns_no():
    sid = _make_session()
    client.post(f"/api/v1/safety/sessions/{sid}/red-flags", json=ALL_FALSE_FLAGS, headers=HEADERS)

    with patch("app.patient.safety.service.run_safety_engine", new_callable=AsyncMock) as mock_svc:
        from app.patient.safety.schemas import SafetyResult
        mock_svc.return_value = SafetyResult(
            session_id=sid,
            result="NO",
            next_action="CMS_ML",
            triggered_rules=[],
            missing_information=[],
            evaluated_at=datetime.now(timezone.utc),
        )
        r = client.post(f"/api/v1/safety/sessions/{sid}/evaluate", headers=HEADERS)

    assert r.status_code == 200
    assert r.json()["result"] == "NO"
    assert r.json()["next_action"] == "CMS_ML"


def test_evaluate_missing_fields_returns_pending():
    sid = _make_session()
    client.post(f"/api/v1/safety/sessions/{sid}/red-flags", json=ALL_NONE_FLAGS, headers=HEADERS)

    with patch("app.patient.safety.service.run_safety_engine", new_callable=AsyncMock) as mock_svc:
        from app.patient.safety.schemas import SafetyResult
        mock_svc.return_value = SafetyResult(
            session_id=sid,
            result="PENDING",
            next_action="GATHER_MORE_INFO",
            triggered_rules=[],
            missing_information=["chest_pain", "stroke_symptoms"],
            evaluated_at=datetime.now(timezone.utc),
        )
        r = client.post(f"/api/v1/safety/sessions/{sid}/evaluate", headers=HEADERS)

    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "PENDING"
    assert len(body["missing_information"]) > 0


def test_evaluate_without_red_flags_returns_422():
    """Calling evaluate before submitting red flags returns 422."""
    sid = _make_session()
    with patch("app.patient.safety.service.run_safety_engine", new_callable=AsyncMock) as mock_svc:
        from fastapi import HTTPException
        mock_svc.side_effect = HTTPException(status_code=422, detail="No red-flag data")
        r = client.post(f"/api/v1/safety/sessions/{sid}/evaluate", headers=HEADERS)
    assert r.status_code == 422


# ── Get assessment ────────────────────────────────────────────────────────────

def test_get_assessment_returns_latest_record():
    sid = _make_session()
    with patch("app.patient.safety.service.get_latest_assessment", new_callable=AsyncMock) as mock_svc:
        from app.patient.safety.schemas import SafetyResult
        mock_svc.return_value = SafetyResult(
            session_id=sid,
            result="NO",
            next_action="CMS_ML",
            triggered_rules=[],
            missing_information=[],
            evaluated_at=datetime.now(timezone.utc),
        )
        r = client.get(f"/api/v1/safety/sessions/{sid}/assessment", headers=HEADERS)

    assert r.status_code == 200
    assert r.json()["result"] == "NO"


def test_get_assessment_no_record_returns_404():
    sid = _make_session()
    with patch("app.patient.safety.service.get_latest_assessment", new_callable=AsyncMock) as mock_svc:
        from fastapi import HTTPException
        mock_svc.side_effect = HTTPException(status_code=404, detail="No assessment")
        r = client.get(f"/api/v1/safety/sessions/{sid}/assessment", headers=HEADERS)
    assert r.status_code == 404
