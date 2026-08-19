"""
Integration tests for Care Manager API — Modules 1 to 4.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.base import get_db
from app.main import app

TEST_KEY = settings.api_key
HEADERS = {"X-API-Key": TEST_KEY}

client = TestClient(app)


# ── Module 1: Patient CRUD & MRN Generation ───────────────────────────────────

def test_care_manager_health():
    r = client.get("/api/v1/care-manager/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_patient_auto_generates_mrn():
    db = AsyncMock()

    count_mock = AsyncMock()
    count_mock.scalar = MagicMock(return_value=40000)

    check_mock = AsyncMock()
    check_mock.scalar_one_or_none = MagicMock(return_value=None)

    db.execute = AsyncMock(side_effect=[count_mock, check_mock, None])
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def mock_get_db_override():
        yield db

    app.dependency_overrides[get_db] = mock_get_db_override

    try:
        payload = {"name": "John Doe", "dob": "1980-05-12"}
        r = client.post("/api/v1/care-manager/patients/", json=payload, headers=HEADERS)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "John Doe"
        assert body["mrn"] == "MRN40001"
    finally:
        app.dependency_overrides.clear()


def test_list_patients_returns_paginated_response():
    db = AsyncMock()

    count_mock = AsyncMock()
    count_mock.scalar = MagicMock(return_value=1)

    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=[])
    rows_mock = AsyncMock()
    rows_mock.scalars = MagicMock(return_value=scalars_mock)

    db.execute = AsyncMock(side_effect=[count_mock, rows_mock])

    async def mock_get_db_override():
        yield db

    app.dependency_overrides[get_db] = mock_get_db_override

    try:
        r = client.get("/api/v1/care-manager/patients/?skip=0&limit=10", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert "patients" in body
    finally:
        app.dependency_overrides.clear()


# ── Module 4: Aggregate Analytics ────────────────────────────────────────────

def test_get_aggregate_analytics():
    db = AsyncMock()

    mock_val = AsyncMock()
    mock_val.scalar = MagicMock(return_value=10)
    db.execute = AsyncMock(return_value=mock_val)

    async def mock_get_db_override():
        yield db

    app.dependency_overrides[get_db] = mock_get_db_override

    try:
        r = client.get("/api/v1/care-manager/analytics/", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert "total_patients" in body
        assert "readmission_rate_pct" in body
    finally:
        app.dependency_overrides.clear()
