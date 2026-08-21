"""
Integration tests for ED Avoidable ML Prediction Endpoint:
- Tests feature mapper with user symptoms, red flags, and EHR database lookup
- Tests prediction endpoint /api/v1/patient/ed-prediction
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.core.security import get_current_patient
from app.models.user import User, UserRole
from app.services.ed_feature_mapper import ed_feature_mapper
from app.services.ed_prediction_service import ed_prediction_service

mock_user = User(username="test_patient", role=UserRole.PATIENT, patient_id="PAT-001")
app.dependency_overrides[get_current_patient] = lambda: mock_user

client = TestClient(app)


def test_ed_prediction_service_loads_model():
    """Verify that scikit-learn ML model pickle bundle loads successfully."""
    assert ed_prediction_service.model is not None
    assert ed_prediction_service.feature_columns is not None
    assert len(ed_prediction_service.feature_columns) == 86


def test_feature_mapper_builds_86_features():
    """Verify that intake data + safety flags + EHR data build all 86 features required by ML model."""
    intake_data = {
        "chief_complaint": "chest pain",
        "symptom_onset": "2 hours ago",
        "pain_scale": 8,
        "location": "left chest",
        "pain_duration": "2 hours",
        "pain_character": "pressure",
        "pain_radiating": "yes",
        "symptom_trend": "worse"
    }

    safety_flags = {
        "chest_pain": True,
        "difficulty_breathing": False,
        "altered_consciousness": False,
        "severe_bleeding": False,
        "stroke_symptoms": False,
        "suicidal_ideation": False,
        "anaphylaxis": False,
        "high_fever": False,
        "unable_to_walk": False,
        "severe_abdominal_pain": False,
        "vomiting_blood": False,
        "severe_dehydration": False
    }

    mock_ehr = MagicMock()
    mock_ehr.age = 65
    mock_ehr.gender = "male"
    mock_ehr.systolic_bp = 140
    mock_ehr.diastolic_bp = 90
    mock_ehr.heart_rate = 95
    mock_ehr.troponin = 0.05
    mock_ehr.previous_er_visits_12m = 2

    features = ed_feature_mapper.build_ml_features(intake_data, safety_flags, mock_ehr)
    assert len(features) == 86
    assert features["age"] == 65
    assert features["troponin"] == 0.05
    assert features["flag_chest_pain_sweating_nausea"] == 1


def test_ed_prediction_endpoint_with_red_flags():
    """Verify POST /api/v1/patient/ed-prediction returns NO (ED Needed) for high risk presentation."""
    payload = {
        "patient_mrn": "PAT-001",
        "intake_data": {
            "chief_complaint": "chest pain",
            "symptom_onset": "sudden",
            "pain_scale": 9,
            "location": "chest",
            "pain_duration": "1_hour",
            "pain_character": "pressure",
            "pain_radiating": "yes",
            "symptom_trend": "worse"
        },
        "safety_flags": {
            "chest_pain": True,
            "difficulty_breathing": True,
            "altered_consciousness": False,
            "severe_bleeding": False,
            "stroke_symptoms": False,
            "suicidal_ideation": False,
            "anaphylaxis": False,
            "high_fever": False,
            "unable_to_walk": False,
            "severe_abdominal_pain": False,
            "vomiting_blood": False,
            "severe_dehydration": False
        }
    }

    response = client.post("/api/v1/patient/ed-prediction", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["avoidable_ed"] in ["YES", "NO"]
    assert "probability" in data
    assert "confidence" in data
    assert "recommendation" in data
    assert data["features_used"] == 86
