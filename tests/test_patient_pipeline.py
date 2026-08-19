"""
Unit and integration tests for Patient-Side pipeline segments:
- Pathway
- Care Options
- Navigation
- Follow-up
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_trigger_pathway_returns_501_not_implemented():
    response = client.post("/api/v1/patients/PAT_000001/pathway/")
    assert response.status_code == 501
    assert "Wire this up to the teammate's pathway/risk-scoring agent" in response.json()["detail"]


def test_trigger_care_options_returns_501_not_implemented():
    response = client.post("/api/v1/patients/PAT_000001/care-options/")
    assert response.status_code == 501
    assert "Wire this up to the teammate's care-options agent" in response.json()["detail"]


def test_trigger_navigation_returns_501_not_implemented():
    payload = {"category": "pcp"}
    response = client.post("/api/v1/patients/PAT_000001/navigation/", json=payload)
    assert response.status_code == 501
    assert "Wire this up to the teammate's navigation agent" in response.json()["detail"]


def test_trigger_followup_returns_501_not_implemented():
    response = client.post("/api/v1/patients/PAT_000001/follow-up/")
    assert response.status_code == 501
    assert "Wire this up to the teammate's follow-up agent" in response.json()["detail"]


def test_get_followup_status_returns_501_not_implemented():
    response = client.get("/api/v1/patients/PAT_000001/follow-up/")
    assert response.status_code == 501
    assert "Not yet implemented — read stored follow-up state" in response.json()["detail"]
