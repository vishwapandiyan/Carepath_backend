"""
Unit tests for safety_engine.py — pure function, no mocks required.

CRITICAL: The fail-safe path (engine exception → raises, never returns NO)
          is explicitly verified in test_engine_exception_raises.
"""

import pytest
from app.services.safety_engine import SafetyEngineError, evaluate_safety


SESSION = "test-session-001"

RULES = [
    {"rule_id": "RF001", "field": "chest_pain",            "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF002", "field": "difficulty_breathing",  "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF003", "field": "altered_consciousness", "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF004", "field": "severe_bleeding",       "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF005", "field": "stroke_symptoms",       "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF006", "field": "suicidal_ideation",     "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF007", "field": "anaphylaxis",           "trigger_value": True, "severity": "CRITICAL"},
    {"rule_id": "RF008", "field": "high_fever",            "trigger_value": True, "severity": "HIGH"},
    {"rule_id": "RF009", "field": "unable_to_walk",        "trigger_value": True, "severity": "HIGH"},
    {"rule_id": "RF010", "field": "severe_abdominal_pain", "trigger_value": True, "severity": "HIGH"},
]

ALL_CLEAR = {f["field"]: False for f in RULES}
ALL_NONE  = {f["field"]: None  for f in RULES}


# ── YES path ──────────────────────────────────────────────────────────────────

def test_single_critical_flag_yields_yes():
    flags = {**ALL_CLEAR, "chest_pain": True}
    result = evaluate_safety(SESSION, flags, RULES)
    assert result["result"] == "YES"
    assert result["next_action"] == "EMERGENCY_PATHWAY"
    assert "RF001" in result["triggered_rules"]
    assert result["missing_information"] == []


def test_multiple_flags_all_reported_in_triggered_rules():
    flags = {**ALL_CLEAR, "chest_pain": True, "stroke_symptoms": True}
    result = evaluate_safety(SESSION, flags, RULES)
    assert result["result"] == "YES"
    assert set(result["triggered_rules"]) == {"RF001", "RF005"}


def test_high_severity_flag_also_yields_yes():
    flags = {**ALL_CLEAR, "severe_abdominal_pain": True}
    result = evaluate_safety(SESSION, flags, RULES)
    assert result["result"] == "YES"
    assert "RF010" in result["triggered_rules"]


# ── NO path ───────────────────────────────────────────────────────────────────

def test_all_flags_false_yields_no():
    result = evaluate_safety(SESSION, ALL_CLEAR, RULES)
    assert result["result"] == "NO"
    assert result["next_action"] == "CMS_ML"
    assert result["triggered_rules"] == []
    assert result["missing_information"] == []


# ── PENDING path ──────────────────────────────────────────────────────────────

def test_all_none_fields_yield_pending():
    result = evaluate_safety(SESSION, ALL_NONE, RULES)
    assert result["result"] == "PENDING"
    assert result["next_action"] == "GATHER_MORE_INFO"
    assert len(result["missing_information"]) == len(RULES)


def test_partial_none_fields_yield_pending():
    flags = {**ALL_CLEAR, "chest_pain": None, "stroke_symptoms": None}
    result = evaluate_safety(SESSION, flags, RULES)
    assert result["result"] == "PENDING"
    assert "chest_pain" in result["missing_information"]
    assert "stroke_symptoms" in result["missing_information"]


# ── CRITICAL FAIL-SAFE path ───────────────────────────────────────────────────

def test_malformed_rule_raises_safety_engine_error():
    """
    FAIL-SAFE: A malformed rule must raise SafetyEngineError.
    The engine must NEVER silently return NO on internal error.
    """
    bad_rules = [{"rule_id": "BAD", "trigger_value": True}]   # missing 'field'
    with pytest.raises(SafetyEngineError):
        evaluate_safety(SESSION, ALL_CLEAR, bad_rules)


def test_non_list_rules_raises_safety_engine_error():
    """Rules must be a list — anything else raises SafetyEngineError."""
    with pytest.raises(SafetyEngineError):
        evaluate_safety(SESSION, ALL_CLEAR, rules="not-a-list")  # type: ignore


def test_engine_never_returns_no_when_exception_would_occur():
    """
    Verify the fail-safe directly: if rules is malformed, we get an exception —
    not a silent NO. This is the most critical test in the safety suite.
    """
    try:
        evaluate_safety(SESSION, ALL_CLEAR, rules=None)  # type: ignore
        pytest.fail("Expected SafetyEngineError but no exception was raised")
    except SafetyEngineError:
        pass   # correct — engine raised, caller will write ERROR
    except Exception as exc:
        pytest.fail(f"Unexpected exception type: {type(exc).__name__}: {exc}")
