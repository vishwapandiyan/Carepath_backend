"""
Integration tests for Segment 1 — Intake endpoints.
Uses FastAPI TestClient with mocked LLM to avoid real API calls.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.security import get_current_patient
from app.db.models import User, UserRole

mock_user = User(username="test_patient", role=UserRole.PATIENT, patient_id="PAT-TEST-001")
app.dependency_overrides[get_current_patient] = lambda: mock_user

HEADERS = {}

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_session(patient_id: str = "patient-001") -> dict:
    r = client.post("/api/v1/intake/sessions", json={"patient_id": patient_id}, headers=HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


def _mock_extraction(overrides: dict = None) -> dict:
    base = {
        "chief_complaint": None,
        "symptom_onset": None,
        "pain_scale": None,
        "location": None,
        "pain_duration": None,
        "pain_character": None,
        "pain_radiating": None,
        "symptom_trend": None,
        "user_query_answer": None,
        "medications": [],
        "allergies": [],
    }
    if overrides:
        base.update(overrides)
    return base


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_create_session_returns_session_id_and_first_question():
    data = _create_session()
    assert "session_id" in data
    assert data["status"] == "IN_PROGRESS"
    assert data["patient_id"] == "patient-001"
    assert data["next_question"] is not None   # chief_complaint question


def test_create_session_requires_auth():
    app.dependency_overrides.pop(get_current_patient, None)
    r = client.post("/api/v1/intake/sessions", json={"patient_id": "p-1"})
    assert r.status_code == 401
    app.dependency_overrides[get_current_patient] = lambda: mock_user


def test_get_session_returns_current_state():
    session = _create_session()
    sid = session["session_id"]
    r = client.get(f"/api/v1/intake/sessions/{sid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["session_id"] == sid


def test_get_nonexistent_session_returns_404():
    r = client.get("/api/v1/intake/sessions/does-not-exist", headers=HEADERS)
    assert r.status_code == 404


def test_send_message_llm_failure_returns_error_status():
    """Fail-safe: LLM failure → status=ERROR, never a partial extraction."""
    session = _create_session()
    sid = session["session_id"]

    with patch(
        "app.patient.intake.service.extract_from_message",
        new_callable=AsyncMock,
        side_effect=Exception("LLM timeout"),
    ):
        r = client.post(
            f"/api/v1/intake/sessions/{sid}/messages",
            json={"content": "I have chest pain"},
            headers=HEADERS,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ERROR"
    assert body["extracted"] is None


def test_send_message_extracts_chief_complaint_and_returns_next_question():
    session = _create_session()
    sid = session["session_id"]

    extracted = _mock_extraction({"chief_complaint": "chest tightness"})

    with patch(
        "app.patient.intake.service.extract_from_message",
        new_callable=AsyncMock,
        return_value=__import__(
            "app.patient.intake.schemas", fromlist=["LLMExtraction"]
        ).LLMExtraction(**extracted),
    ):
        r = client.post(
            f"/api/v1/intake/sessions/{sid}/messages",
            json={"content": "I have chest tightness"},
            headers=HEADERS,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["extracted"]["chief_complaint"] == "chest tightness"
    assert body["next_question"] is not None


def test_send_message_complete_when_all_required_fields_present():
    """When all required fields are filled, status transitions to COMPLETE."""
    session = _create_session()
    sid = session["session_id"]

    full = _mock_extraction({
        "chief_complaint": "chest pain",
        "symptom_onset": "2 hours ago",
        "pain_scale": 8,
        "location": "left chest",
        "pain_duration": "2 hours",
        "pain_character": "sharp",
        "pain_radiating": "no",
        "symptom_trend": "stable",
        "medications": ["aspirin"],
        "allergies": ["penicillin"],
    })

    from app.patient.intake.schemas import LLMExtraction

    with patch(
        "app.patient.intake.service.extract_from_message",
        new_callable=AsyncMock,
        return_value=LLMExtraction(**full),
    ):
        r = client.post(
            f"/api/v1/intake/sessions/{sid}/messages",
            json={"content": "I have chest pain..."},
            headers=HEADERS,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETE"
    assert body["next_question"] is None


def test_send_message_to_nonexistent_session_returns_404():
    r = client.post(
        "/api/v1/intake/sessions/ghost/messages",
        json={"content": "hello"},
        headers=HEADERS,
    )
    assert r.status_code == 404
