"""
Unit tests for question_policy.py — pure function, no mocks required.
"""

import pytest
from app.services.question_policy import next_missing_field
from app.services.vocabulary import QUESTION_TEMPLATES, REQUIRED_FIELD_ORDER


def _full_extraction() -> dict:
    """A complete extraction dict with all required fields populated."""
    return {
        "chief_complaint": "Chest tightness",
        "symptom_onset": "2 hours ago",
        "pain_scale": 7,
        "location": "left chest",
        "duration": "2 hours",
        "medications": ["aspirin"],
        "allergies": ["penicillin"],
        "prior_conditions": [],
        "relevant_history": None,
        "worsening_factors": None,
        "relieving_factors": None,
    }


def test_empty_extraction_returns_chief_complaint_question():
    """First call with no data should ask for chief_complaint."""
    result = next_missing_field({})
    assert result == QUESTION_TEMPLATES["chief_complaint"]


def test_missing_symptom_onset_returns_correct_question():
    d = _full_extraction()
    d["symptom_onset"] = None
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["symptom_onset"]


def test_missing_pain_scale_returns_correct_question():
    d = _full_extraction()
    d["symptom_onset"] = "yesterday"
    d["pain_scale"] = None
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["pain_scale"]


def test_missing_location_returns_correct_question():
    d = _full_extraction()
    d["location"] = None
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["location"]


def test_missing_medications_returns_correct_question():
    d = _full_extraction()
    d["medications"] = None
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["medications"]


def test_missing_allergies_returns_correct_question():
    d = _full_extraction()
    d["allergies"] = None
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["allergies"]


def test_all_required_fields_present_returns_none():
    """When all required fields are populated, intake is complete → return None."""
    result = next_missing_field(_full_extraction())
    assert result is None


def test_priority_order_chief_complaint_first():
    """chief_complaint is always asked before any other field."""
    d = _full_extraction()
    d["chief_complaint"] = None
    d["symptom_onset"] = None   # also missing, but lower priority
    result = next_missing_field(d)
    assert result == QUESTION_TEMPLATES["chief_complaint"]


def test_required_field_order_matches_vocabulary():
    """REQUIRED_FIELD_ORDER must reference only fields defined in QUESTION_TEMPLATES."""
    for field in REQUIRED_FIELD_ORDER:
        assert field in QUESTION_TEMPLATES, f"Field '{field}' has no template"
