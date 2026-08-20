"""
Unit and integration tests for Patient-Side pipeline segments:
- Pathway
- Care Options
- Navigation
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_trigger_pathway_returns_success():
    response = client.post("/api/v1/patients/PAT_000001/pathway/", json={"patient_id": "PAT_000001"})
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == "PAT_000001"
    assert "risk_score" in data
    assert "decision" in data


def test_trigger_care_options_returns_501_not_implemented():
    response = client.post("/api/v1/patients/PAT_000001/care-options/")
    assert response.status_code == 501
    assert "Wire this up to the teammate's care-options agent" in response.json()["detail"]


def test_trigger_navigation_returns_501_not_implemented():
    payload = {"category": "pcp"}
    response = client.post("/api/v1/patients/PAT_000001/navigation/", json=payload)
    assert response.status_code == 501
    assert "Wire this up to the teammate's navigation agent" in response.json()["detail"]
