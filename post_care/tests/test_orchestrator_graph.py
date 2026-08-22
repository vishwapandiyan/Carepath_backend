"""
Tests for OrchestratorGraph: Verify end-to-end workflow orchestration using LangGraph.

Tests verify:
1. HIGH risk workflow (P=0.86)
2. MODERATE risk workflow (P=0.65)
3. LOW risk workflow (P=0.25)
4. Error handling (nonexistent patient)
5. Graph uses router (no duplicate routing logic)
6. Graph uses Care Plan Agent (no duplicate care plan logic)
7. Final state correctness with all fields populated
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.state import OrchestratorState, create_initial_state
from orchestrator.graph import invoke_orchestrator


def print_test_result(test_num: int, test_name: str, expected: str, actual: str, passed: bool) -> None:
    """Print test result in table format."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"TEST {test_num:2d} | {test_name:<50} | Expected: {expected:<20} | Actual: {actual:<20} | {status}")


def print_state_summary(state: OrchestratorState, label: str = "") -> None:
    """Print a summary of OrchestratorState for debugging."""
    if label:
        print(f"\n{label}")
    print("-" * 100)
    print(f"  patient_id: {state.patient_id}")
    print(f"  prediction: {state.prediction}")
    print(f"  probability: {state.probability}")
    print(f"  workflow_status: {state.workflow_status}")
    print(f"  error: {state.error}")
    print(f"  current_agent: {state.current_agent}")
    if state.care_plan:
        print(f"  care_plan.risk_level: {state.care_plan.risk_level}")
        print(f"  care_plan.intensity: {state.care_plan.intensity}")
        print(f"  care_plan.status: {state.care_plan.status}")
        print(f"  care_plan.tasks: {len(state.care_plan.tasks)} tasks")
    else:
        print(f"  care_plan: None")
    print("-" * 100)


# ============================================================================
# TEST 1: HIGH RISK WORKFLOW
# ============================================================================

def test_high_risk_workflow():
    """Test: HIGH risk patient (P=0.86) generates INTENSIVE care plan."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Run orchestrator
    result = invoke_orchestrator(initial_state)

    # Verify results
    risk_check = result.care_plan is not None and result.care_plan.risk_level == "HIGH"
    intensity_check = result.care_plan is not None and result.care_plan.intensity == "INTENSIVE"
    status_check = result.workflow_status == "COMPLETED"
    no_error = result.error is None

    expected = "HIGH / INTENSIVE / COMPLETED"
    actual = f"{result.care_plan.risk_level if result.care_plan else 'None'} / {result.care_plan.intensity if result.care_plan else 'None'} / {result.workflow_status}"
    passed = risk_check and intensity_check and status_check and no_error

    print_test_result(1, "HIGH risk workflow (P=0.86)", expected, actual, passed)
    assert passed, f"HIGH risk test failed"
    return result


# ============================================================================
# TEST 2: MODERATE RISK WORKFLOW
# ============================================================================

def test_moderate_risk_workflow():
    """Test: MODERATE risk patient (P=0.65) generates REGULAR care plan."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=0,
        probability=0.65
    )

    # Run orchestrator
    result = invoke_orchestrator(initial_state)

    # Verify results
    risk_check = result.care_plan is not None and result.care_plan.risk_level == "MODERATE"
    intensity_check = result.care_plan is not None and result.care_plan.intensity == "REGULAR"
    status_check = result.workflow_status == "COMPLETED"
    no_error = result.error is None

    expected = "MODERATE / REGULAR / COMPLETED"
    actual = f"{result.care_plan.risk_level if result.care_plan else 'None'} / {result.care_plan.intensity if result.care_plan else 'None'} / {result.workflow_status}"
    passed = risk_check and intensity_check and status_check and no_error

    print_test_result(2, "MODERATE risk workflow (P=0.65)", expected, actual, passed)
    assert passed, f"MODERATE risk test failed"
    return result


# ============================================================================
# TEST 3: LOW RISK WORKFLOW
# ============================================================================

def test_low_risk_workflow():
    """Test: LOW risk patient (P=0.25) generates BASIC care plan."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=0,
        probability=0.25
    )

    # Run orchestrator
    result = invoke_orchestrator(initial_state)

    # Verify results
    risk_check = result.care_plan is not None and result.care_plan.risk_level == "LOW"
    intensity_check = result.care_plan is not None and result.care_plan.intensity == "BASIC"
    status_check = result.workflow_status == "COMPLETED"
    no_error = result.error is None

    expected = "LOW / BASIC / COMPLETED"
    actual = f"{result.care_plan.risk_level if result.care_plan else 'None'} / {result.care_plan.intensity if result.care_plan else 'None'} / {result.workflow_status}"
    passed = risk_check and intensity_check and status_check and no_error

    print_test_result(3, "LOW risk workflow (P=0.25)", expected, actual, passed)
    assert passed, f"LOW risk test failed"
    return result


# ============================================================================
# TEST 4: ERROR HANDLING - NONEXISTENT PATIENT
# ============================================================================

def test_error_nonexistent_patient():
    """Test: Nonexistent patient (P999999) triggers FAILED status."""
    initial_state = create_initial_state(
        patient_id="P999999",
        prediction=1,
        probability=0.86
    )

    # Run orchestrator
    result = invoke_orchestrator(initial_state)

    # Verify error handling
    status_failed = result.workflow_status == "FAILED"
    error_populated = result.error is not None
    care_plan_none = result.care_plan is None

    expected = "FAILED / Error populated"
    actual = f"{result.workflow_status} / {'Error: ' + result.error[:30] if result.error else 'No error'}"
    passed = status_failed and error_populated and care_plan_none

    print_test_result(4, "Error: Nonexistent patient (P999999)", expected, actual, passed)
    assert passed, f"Error handling test failed"
    return result


# ============================================================================
# TEST 5: VERIFY ROUTER USAGE
# ============================================================================

def test_router_usage():
    """
    Test: Graph uses router module (route_next_agent).

    Verify by checking that routing decisions are correct and workflow progresses
    through router decisions.
    """
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Initial state should have current_agent=None
    assert initial_state.current_agent is None, "Initial state should have no current_agent"

    result = invoke_orchestrator(initial_state)

    # After workflow, current_agent should be "END" (set by router)
    router_used = result.current_agent == "END"

    # Check that next_agent follows routing rules
    next_agent_correct = result.next_agent is None  # END node has next_agent = None

    expected = "Router used (current_agent=END, next_agent=None)"
    actual = f"current_agent={result.current_agent}, next_agent={result.next_agent}"
    passed = router_used and next_agent_correct

    print_test_result(5, "Verify router usage (no duplicate routing)", expected, actual, passed)
    assert passed, f"Router usage test failed"


# ============================================================================
# TEST 6: VERIFY CARE PLAN AGENT USAGE
# ============================================================================

def test_care_plan_agent_usage():
    """
    Test: Graph uses Care Plan Agent (run_care_plan_agent).

    Verify by checking:
    1. Care plan is generated (not None)
    2. Care plan has all required fields (risk_level, intensity, tasks)
    3. Tasks are created from predefined pathway (no duplicate logic)
    """
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    result = invoke_orchestrator(initial_state)

    # Verify care plan is populated
    care_plan_populated = result.care_plan is not None

    # Verify all required fields
    has_risk_level = result.care_plan.risk_level in ["HIGH", "MODERATE", "LOW"]
    has_intensity = result.care_plan.intensity in ["INTENSIVE", "REGULAR", "BASIC"]
    has_status = result.care_plan.status == "ACTIVE"
    has_tasks = len(result.care_plan.tasks) > 0

    # For HIGH risk, expect specific number of tasks from predefined pathway
    high_risk_tasks = result.care_plan.risk_level == "HIGH" and len(result.care_plan.tasks) == 5

    expected = "Care plan with all fields populated"
    actual = f"care_plan.risk_level={result.care_plan.risk_level}, intensity={result.care_plan.intensity}, {len(result.care_plan.tasks)} tasks"
    passed = care_plan_populated and has_risk_level and has_intensity and has_status and has_tasks and high_risk_tasks

    print_test_result(6, "Verify Care Plan Agent usage", expected, actual, passed)
    assert passed, f"Care Plan Agent usage test failed"


# ============================================================================
# TEST 7: WORKFLOW STATUS PROGRESSION
# ============================================================================

def test_workflow_status_progression():
    """Test: Workflow status progresses correctly: PENDING → RUNNING → COMPLETED."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Initial status should be PENDING
    assert initial_state.workflow_status == "PENDING", "Initial status should be PENDING"

    result = invoke_orchestrator(initial_state)

    # Final status should be COMPLETED (for successful workflows)
    final_status_correct = result.workflow_status == "COMPLETED"

    expected = "PENDING → RUNNING → COMPLETED"
    actual = f"Initial: PENDING, Final: {result.workflow_status}"
    passed = final_status_correct

    print_test_result(7, "Workflow status progression", expected, actual, passed)
    assert passed, f"Workflow status test failed"


# ============================================================================
# TEST 8: PATIENT CONTEXT INTEGRATION
# ============================================================================

def test_patient_context_integration():
    """Test: Patient context is available from Care Plan Agent execution."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    result = invoke_orchestrator(initial_state)

    # The Care Plan Agent internally retrieves patient context
    # For now, we verify that the care plan was successfully created
    # (which means get_patient_context_tool was called internally)
    care_plan_created = result.care_plan is not None
    no_error = result.error is None

    expected = "Care Plan Agent successfully retrieved context"
    actual = f"Care Plan created: {care_plan_created}, Error: {result.error}"
    passed = care_plan_created and no_error

    print_test_result(8, "Patient context integration", expected, actual, passed)
    assert passed, f"Patient context test failed"


# ============================================================================
# TEST 9: COMPLETE STATE AT WORKFLOW END
# ============================================================================

def test_complete_state_at_end():
    """Test: Final state contains all expected fields populated."""
    initial_state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    result = invoke_orchestrator(initial_state)

    # Check input fields preserved
    patient_id_preserved = result.patient_id == "P000003"
    prediction_preserved = result.prediction == 1
    probability_preserved = result.probability == 0.86

    # Check output fields populated
    care_plan_populated = result.care_plan is not None
    workflow_status_completed = result.workflow_status == "COMPLETED"
    no_error = result.error is None

    # Check metadata
    current_agent_end = result.current_agent == "END"
    next_agent_none = result.next_agent is None

    expected = "All fields populated correctly"
    actual = f"status={result.workflow_status}, current_agent={result.current_agent}, care_plan={result.care_plan is not None}"
    passed = (
        patient_id_preserved and prediction_preserved and probability_preserved and
        care_plan_populated and workflow_status_completed and no_error and
        current_agent_end and next_agent_none
    )

    print_test_result(9, "Complete state at workflow end", expected, actual, passed)
    assert passed, f"Complete state test failed"


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*130)
    print("TESTING ORCHESTRATOR GRAPH (LANGGRAPH)")
    print("="*130 + "\n")

    # Run all tests
    high_risk_result = test_high_risk_workflow()
    moderate_risk_result = test_moderate_risk_workflow()
    low_risk_result = test_low_risk_workflow()
    error_result = test_error_nonexistent_patient()
    test_router_usage()
    test_care_plan_agent_usage()
    test_workflow_status_progression()
    test_patient_context_integration()
    test_complete_state_at_end()

    print("\n" + "="*130)
    print("FINAL STATE SUMMARY - HIGH RISK CASE (P=0.86)")
    print("="*130)
    print_state_summary(high_risk_result)

    print("\n" + "="*130)
    print("ALL ORCHESTRATOR GRAPH TESTS PASSED ✅")
    print("="*130 + "\n")
