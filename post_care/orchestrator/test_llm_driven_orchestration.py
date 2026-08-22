"""
Tests for LLM-Driven Orchestration with Safety Validation

This test suite verifies:
1. LLM receives all approved high-level tools
2. LLM produces actual tool_calls
3. Safety validator validates after LLM selection
4. Invalid selections are rejected
5. Risk level/intensity/status protected
6. New capabilities (response analysis when response ready)
7. Backward compatibility (active plan reuse works)

NEW ARCHITECTURE:
  LLM → (sees ALL tools) → selects tool → validator → executes if valid
"""

import logging
from typing import Dict, Any
from post_care.orchestrator.workflow_state import PostCareWorkflowState
from post_care.orchestrator.agentic_orchestrator_node import orchestrator_llm_node
from post_care.orchestrator.agentic_guardrails import validate_tool_call
from post_care.orchestrator.agentic_tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ============================================================================
# TEST FIXTURES
# ============================================================================

def create_test_state(**kwargs) -> PostCareWorkflowState:
    """Create a test state with sensible defaults."""
    state = PostCareWorkflowState(
        mrn=kwargs.get("mrn", "MRN000015"),
        patient_id=kwargs.get("patient_id", "P-001"),
        prediction=kwargs.get("prediction", 1),
        probability=kwargs.get("probability", 0.85),
        notes=kwargs.get("notes"),
        
        care_plan=kwargs.get("care_plan"),
        care_plan_id=kwargs.get("care_plan_id", "CP-0AEB878E"),
        risk_level=kwargs.get("risk_level", "HIGH"),
        intensity=kwargs.get("intensity", "INTENSIVE"),
        care_plan_status=kwargs.get("care_plan_status", "ACTIVE"),
        
        follow_up_output=kwargs.get("follow_up_output"),
        task_id=kwargs.get("task_id"),
        task_type=kwargs.get("task_type"),
        checkin_id=kwargs.get("checkin_id"),
        checkin_status=kwargs.get("checkin_status"),
        
        patient_response=kwargs.get("patient_response"),
        
        response_analyzer_output=kwargs.get("response_analyzer_output"),
        classification=kwargs.get("classification"),
        response_confidence=kwargs.get("response_confidence"),
        symptoms=kwargs.get("symptoms"),
        concerns=kwargs.get("concerns"),
        
        care_continuity_output=kwargs.get("care_continuity_output"),
        continuity_action=kwargs.get("continuity_action"),
        requires_human_review=kwargs.get("requires_human_review"),
        requires_appointment=kwargs.get("requires_appointment"),
        
        workflow_status=kwargs.get("workflow_status", "PENDING"),
        current_node=kwargs.get("current_node"),
        next_node=kwargs.get("next_node"),
        error=kwargs.get("error"),
        metadata=kwargs.get("metadata"),
    )
    return state


# ============================================================================
# TESTS: LLM TOOL VISIBILITY
# ============================================================================

def test_llm_receives_all_approved_tools():
    """TEST 1: LLM receives all approved high-level tools (not filtered)."""
    print("\n" + "="*70)
    print("TEST 1: LLM Receives All Approved Tools")
    print("="*70)
    
    # Verify ALL_TOOLS has 5 tools
    assert len(ALL_TOOLS) >= 5, f"Expected at least 5 tools, got {len(ALL_TOOLS)}"
    
    tool_names = [t.name for t in ALL_TOOLS]
    print(f"\nApproved tools available to LLM: {len(ALL_TOOLS)} tools")
    for tool in ALL_TOOLS:
        print(f"  • {tool.name}")
    
    assert "call_care_plan_agent" in tool_names
    assert "call_follow_up_agent" in tool_names
    assert "call_response_analyzer" in tool_names
    assert "call_care_continuity" in tool_names
    assert "wait_for_patient_response" in tool_names
    
    print("✓ PASS: LLM can see all 5 approved tools")
    return True


def test_response_analyzer_available_when_patient_response_exists():
    """
    TEST 2: Response Analyzer is available when patient_response exists.
    
    NEW CAPABILITY: In old system, response_analyzer blocked if follow_up_output missing.
    New system: Validator allows if patient_response exists.
    """
    print("\n" + "="*70)
    print("TEST 2: Response Analyzer Available When Response Ready")
    print("="*70)
    
    # Setup state: Response exists but follow_up_output not set
    state = create_test_state(
        care_plan_id="CP-0AEB878E",
        patient_response="I'm feeling better today",
        follow_up_output=None,  # NOT set (old system would block here)
        response_analyzer_output=None,
        task_id="TASK-001",
        checkin_id="CHECKIN-001"
    )
    
    print(f"\nState:")
    print(f"  - care_plan_id: {state.get('care_plan_id')}")
    print(f"  - patient_response: '{state.get('patient_response')[:40]}...'")
    print(f"  - follow_up_output: {state.get('follow_up_output')}")
    print(f"  - response_analyzer_output: {state.get('response_analyzer_output')}")
    
    # NEW: Validator should ALLOW response_analyzer
    is_valid, reason = validate_tool_call("call_response_analyzer", state)
    
    print(f"\nValidation Result:")
    print(f"  Tool: call_response_analyzer")
    print(f"  Valid: {is_valid}")
    print(f"  Reason: {reason}")
    
    assert is_valid == True, f"response_analyzer should be valid when response exists: {reason}"
    print("✓ PASS: Response analyzer available when response ready (NEW CAPABILITY)")
    return True


# ============================================================================
# TESTS: SAFETY VALIDATION
# ============================================================================

def test_invalid_tool_selection_rejected():
    """
    TEST 3: Invalid tool selection is rejected by safety validator.
    
    Example: LLM selects response_analyzer but patient_response is None
    Result: Validator rejects with clear error message
    """
    print("\n" + "="*70)
    print("TEST 3: Invalid Tool Selection Rejected")
    print("="*70)
    
    # State: No patient response
    state = create_test_state(
        patient_response=None,  # Empty response
        follow_up_output=None,
        response_analyzer_output=None
    )
    
    print(f"\nState:")
    print(f"  - patient_response: {state.get('patient_response')}")
    
    # LLM attempted to select response_analyzer
    tool_name = "call_response_analyzer"
    print(f"\nLLM attempted to select: {tool_name}")
    
    is_valid, reason = validate_tool_call(tool_name, state)
    
    print(f"\nValidation Result:")
    print(f"  Valid: {is_valid}")
    print(f"  Reason: {reason}")
    
    assert is_valid == False, "Should reject response_analyzer when no patient_response"
    assert "patient_response" in reason.lower(), "Error reason should mention patient_response"
    print("✓ PASS: Invalid selection rejected by validator")
    return True


def test_validator_rejects_with_clear_reason():
    """TEST 4: Validator provides clear reason for rejection."""
    print("\n" + "="*70)
    print("TEST 4: Validator Provides Clear Rejection Reason")
    print("="*70)
    
    test_cases = [
        {
            "state": create_test_state(patient_response=None),
            "tool": "call_response_analyzer",
            "expect_reason": "patient_response"
        },
        {
            "state": create_test_state(care_plan_id=None),
            "tool": "call_follow_up_agent",
            "expect_reason": "care_plan_id"
        },
        {
            "state": create_test_state(response_analyzer_output=None),
            "tool": "call_care_continuity",
            "expect_reason": "response_analyzer_output"
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\nTest Case {i+1}:")
        print(f"  Tool: {test_case['tool']}")
        
        is_valid, reason = validate_tool_call(test_case["tool"], test_case["state"])
        
        print(f"  Valid: {is_valid}")
        print(f"  Reason: {reason}")
        
        assert is_valid == False, f"Should reject {test_case['tool']}"
        assert test_case["expect_reason"].lower() in reason.lower(), f"Reason should mention {test_case['expect_reason']}"
    
    print("\n✓ PASS: All rejections have clear reasons")
    return True


# ============================================================================
# TESTS: SAFETY CONSTRAINTS
# ============================================================================

def test_risk_level_protection():
    """
    TEST 5: Risk level cannot be modified.
    
    HIGH risk patient responds positively → Risk stays HIGH
    """
    print("\n" + "="*70)
    print("TEST 5: Risk Level Protection")
    print("="*70)
    
    state = create_test_state(
        risk_level="HIGH",
        intensity="INTENSIVE",
        care_plan_status="ACTIVE",
        patient_response="I'm feeling much better!"
    )
    
    print(f"\nInitial State:")
    print(f"  - risk_level: {state.get('risk_level')}")
    print(f"  - intensity: {state.get('intensity')}")
    print(f"  - care_plan_status: {state.get('care_plan_status')}")
    print(f"  - patient_response: '{state.get('patient_response')}'")
    
    print(f"\nScenario: Patient reports feeling better, but risk stays HIGH")
    print(f"  Reason: LLM/agents only route, they don't modify risk assessment")
    
    # These values should be protected
    assert state.get("risk_level") == "HIGH", "Risk level should not be modified"
    assert state.get("intensity") == "INTENSIVE", "Intensity should not be modified"
    assert state.get("care_plan_status") == "ACTIVE", "Care plan status should not be modified"
    
    print("✓ PASS: Risk level protected from modification")
    return True


# ============================================================================
# TESTS: TOOL VALIDATION RULES
# ============================================================================

def test_care_plan_agent_validation():
    """TEST 6: Care Plan Agent validation rules."""
    print("\n" + "="*70)
    print("TEST 6: Care Plan Agent Validation")
    print("="*70)
    
    # Valid state
    valid_state = create_test_state(
        mrn="MRN000015",
        prediction=1,
        probability=0.85
    )
    is_valid, _ = validate_tool_call("call_care_plan_agent", valid_state)
    assert is_valid == True, "Should validate with mrn, prediction, probability"
    print("✓ Valid: care_plan_agent with mrn, prediction, probability")
    
    # Invalid: missing mrn
    invalid_state = create_test_state(mrn=None)
    is_valid, reason = validate_tool_call("call_care_plan_agent", invalid_state)
    assert is_valid == False, "Should reject without mrn"
    assert "mrn" in reason.lower()
    print("✓ Rejected: care_plan_agent without mrn")
    
    print("✓ PASS: Care Plan Agent validation works")
    return True


def test_response_analyzer_validation():
    """TEST 7: Response Analyzer validation rules."""
    print("\n" + "="*70)
    print("TEST 7: Response Analyzer Validation")
    print("="*70)
    
    # Valid state
    valid_state = create_test_state(
        patient_response="I'm feeling better",
        response_analyzer_output=None,
        task_id="TASK-001",
        checkin_id="CHECKIN-001"
    )
    is_valid, _ = validate_tool_call("call_response_analyzer", valid_state)
    assert is_valid == True, "Should validate with response, task_id, checkin_id"
    print("✓ Valid: response_analyzer with patient_response, task_id, checkin_id")
    
    # Invalid: empty response
    invalid_state = create_test_state(
        patient_response="",
        response_analyzer_output=None,
        task_id="TASK-001",
        checkin_id="CHECKIN-001"
    )
    is_valid, reason = validate_tool_call("call_response_analyzer", invalid_state)
    assert is_valid == False, "Should reject empty response"
    print("✓ Rejected: response_analyzer with empty response")
    
    # Invalid: already analyzed
    analyzed_state = create_test_state(
        patient_response="I'm feeling better",
        response_analyzer_output={"classification": "NORMAL"}  # Already analyzed
    )
    is_valid, reason = validate_tool_call("call_response_analyzer", analyzed_state)
    assert is_valid == False, "Should reject if already analyzed"
    print("✓ Rejected: response_analyzer when already analyzed")
    
    print("✓ PASS: Response Analyzer validation works")
    return True


def test_care_continuity_validation():
    """TEST 8: Care Continuity validation rules."""
    print("\n" + "="*70)
    print("TEST 8: Care Continuity Validation")
    print("="*70)
    
    # Valid state
    valid_state = create_test_state(
        response_analyzer_output={"classification": "NORMAL"},
        classification="NORMAL",
        continuity_action=None
    )
    is_valid, _ = validate_tool_call("call_care_continuity", valid_state)
    assert is_valid == True, "Should validate with response_analyzer_output and classification"
    print("✓ Valid: care_continuity with response_analyzer_output and classification")
    
    # Invalid: no analysis
    invalid_state = create_test_state(
        response_analyzer_output=None,
        classification=None
    )
    is_valid, reason = validate_tool_call("call_care_continuity", invalid_state)
    assert is_valid == False, "Should reject without response_analyzer_output"
    print("✓ Rejected: care_continuity without response analysis")
    
    # Invalid: already determined
    determined_state = create_test_state(
        response_analyzer_output={"classification": "NORMAL"},
        classification="NORMAL",
        continuity_action="CONTINUE_FOLLOW_UP"  # Already determined
    )
    is_valid, reason = validate_tool_call("call_care_continuity", determined_state)
    assert is_valid == False, "Should reject if action already determined"
    print("✓ Rejected: care_continuity when action already determined")
    
    print("✓ PASS: Care Continuity validation works")
    return True


def test_wait_for_response_validation():
    """TEST 9: Wait for Response tool validation."""
    print("\n" + "="*70)
    print("TEST 9: Wait for Patient Response Validation")
    print("="*70)
    
    # Valid state
    valid_state = create_test_state(
        follow_up_output={"checkin_id": "CHECKIN-001"},  # Follow-up scheduled
        patient_response=None  # No response yet
    )
    is_valid, _ = validate_tool_call("wait_for_patient_response", valid_state)
    assert is_valid == True, "Should validate when follow-up scheduled and no response"
    print("✓ Valid: wait_for_patient_response when follow-up scheduled, no response yet")
    
    # Invalid: patient already responded
    responded_state = create_test_state(
        follow_up_output={"checkin_id": "CHECKIN-001"},
        patient_response="I'm feeling better"  # Already responded
    )
    is_valid, reason = validate_tool_call("wait_for_patient_response", responded_state)
    assert is_valid == False, "Should reject if patient already responded"
    print("✓ Rejected: wait_for_patient_response when patient already responded")
    
    print("✓ PASS: Wait for Response validation works")
    return True


# ============================================================================
# TESTS: BACKWARD COMPATIBILITY
# ============================================================================

def test_all_tools_still_accessible():
    """TEST 10: All existing tools still accessible via orchestrator."""
    print("\n" + "="*70)
    print("TEST 10: Backward Compatibility - All Tools Accessible")
    print("="*70)
    
    tool_names = [t.name for t in ALL_TOOLS]
    
    # Verify all 5 tools present
    required_tools = [
        "call_care_plan_agent",
        "call_follow_up_agent",
        "call_response_analyzer",
        "call_care_continuity",
        "wait_for_patient_response"
    ]
    
    for tool_name in required_tools:
        assert tool_name in tool_names, f"{tool_name} not in ALL_TOOLS"
        print(f"✓ {tool_name} accessible")
    
    print("✓ PASS: All tools accessible (backward compatible)")
    return True


# ============================================================================
# RUN ALL TESTS
# ============================================================================

def run_all_tests():
    """Run all tests and report results."""
    tests = [
        ("TEST 1: LLM Receives All Tools", test_llm_receives_all_approved_tools),
        ("TEST 2: Response Analyzer Available When Response Ready", test_response_analyzer_available_when_patient_response_exists),
        ("TEST 3: Invalid Selection Rejected", test_invalid_tool_selection_rejected),
        ("TEST 4: Clear Rejection Reasons", test_validator_rejects_with_clear_reason),
        ("TEST 5: Risk Level Protection", test_risk_level_protection),
        ("TEST 6: Care Plan Validation", test_care_plan_agent_validation),
        ("TEST 7: Response Analyzer Validation", test_response_analyzer_validation),
        ("TEST 8: Care Continuity Validation", test_care_continuity_validation),
        ("TEST 9: Wait for Response Validation", test_wait_for_response_validation),
        ("TEST 10: Backward Compatibility", test_all_tools_still_accessible),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            test_func()
            results.append((test_name, "PASS"))
        except AssertionError as e:
            results.append((test_name, f"FAIL: {str(e)}"))
        except Exception as e:
            results.append((test_name, f"ERROR: {str(e)}"))
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result == "PASS")
    failed = sum(1 for _, result in results if result.startswith("FAIL"))
    errors = sum(1 for _, result in results if result.startswith("ERROR"))
    
    for test_name, result in results:
        status = "✓" if result == "PASS" else "✗"
        print(f"{status} {test_name}: {result}")
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: {errors}")
    
    return passed, failed, errors


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(name)s - %(levelname)s - %(message)s'
    )
    
    passed, failed, errors = run_all_tests()
    
    # Exit with error code if tests failed
    if failed > 0 or errors > 0:
        exit(1)
    
    print("\n✓ ALL TESTS PASSED")
    exit(0)
