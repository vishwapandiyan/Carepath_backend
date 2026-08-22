"""
Tests for OrchestratorRouter: Verify routing logic for agent sequencing.

Tests verify:
1. Initial routing to Care Plan Agent
2. Routing to END after Care Plan completes
3. Routing to END on error
4. No agent invocation (router is stateless)
5. set_next_agent helper updates state correctly
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.router import route_next_agent, set_next_agent
from orchestrator.state import OrchestratorState, create_initial_state
from agents.care_plan.schemas import CarePlanOutput, CareTask


def print_test_result(test_num: int, test_name: str, expected: str, actual: str, passed: bool) -> None:
    """Print test result in table format."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"TEST {test_num} | {test_name:<50} | Expected: {expected:<15} | Actual: {actual:<15} | {status}")


# ============================================================================
# TEST 1: INITIAL ROUTING - CARE PLAN AGENT
# ============================================================================

def test_initial_routing_to_care_plan():
    """Test: Initial state (no care_plan yet) routes to Care Plan Agent."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    result = route_next_agent(state)
    expected = "care_plan"
    passed = result == expected

    print_test_result(1, "Initial routing (care_plan=None)", expected, result, passed)
    assert passed, f"Expected '{expected}', got '{result}'"


# ============================================================================
# TEST 2: ROUTING AFTER CARE PLAN COMPLETES
# ============================================================================

def test_routing_after_care_plan_completion():
    """Test: State with valid CarePlanOutput routes to END (workflow complete)."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Simulate Care Plan Agent completing
    care_plan = CarePlanOutput(
        patient_id="P000003",
        care_plan_id="CP-001-P000003",
        risk_level="HIGH",
        intensity="INTENSIVE",
        status="ACTIVE",
        tasks=[
            CareTask(task_id="T1", task_type="EARLY_CHECKIN", status="PENDING"),
            CareTask(task_id="T2", task_type="FREQUENT_CHECKINS", status="PENDING"),
            CareTask(task_id="T3", task_type="FOLLOW_UP_APPOINTMENT", status="PENDING"),
            CareTask(task_id="T4", task_type="APPOINTMENT_MONITORING", status="PENDING"),
            CareTask(task_id="T5", task_type="CONCERN_ESCALATION", status="PENDING"),
        ]
    )
    state.care_plan = care_plan

    result = route_next_agent(state)
    expected = "END"
    passed = result == expected

    print_test_result(2, "Routing after Care Plan (care_plan exists)", expected, result, passed)
    assert passed, f"Expected '{expected}', got '{result}'"


# ============================================================================
# TEST 3: ROUTING ON ERROR
# ============================================================================

def test_routing_on_error():
    """Test: State with error routes to END (workflow stops)."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Simulate error
    state.error = "Patient not found in context database"

    result = route_next_agent(state)
    expected = "END"
    passed = result == expected

    print_test_result(3, "Routing on error (error set)", expected, result, passed)
    assert passed, f"Expected '{expected}', got '{result}'"


# ============================================================================
# TEST 4: ERROR TAKES PRECEDENCE OVER CARE PLAN
# ============================================================================

def test_error_precedence():
    """Test: Error takes precedence even if care_plan exists."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Both error and care_plan present (error occurred after care plan creation)
    state.care_plan = CarePlanOutput(
        patient_id="P000003",
        care_plan_id="CP-001",
        risk_level="HIGH",
        intensity="INTENSIVE",
        status="ACTIVE",
        tasks=[]
    )
    state.error = "Follow-up scheduling failed"

    result = route_next_agent(state)
    expected = "END"
    passed = result == expected

    print_test_result(4, "Error precedence (error + care_plan)", expected, result, passed)
    assert passed, f"Expected '{expected}', got '{result}'"


# ============================================================================
# TEST 5: SET NEXT AGENT - INITIAL STATE
# ============================================================================

def test_set_next_agent_to_care_plan():
    """Test: set_next_agent updates state for Care Plan Agent."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Before: current_agent and next_agent are None
    assert state.current_agent is None
    assert state.next_agent is None

    # Update via set_next_agent
    state = set_next_agent(state, "care_plan")

    # After: current_agent is "care_plan", next_agent is "END"
    passed = (state.current_agent == "care_plan" and state.next_agent == "END")

    print_test_result(5, "set_next_agent for Care Plan Agent", "care_plan→END", f"{state.current_agent}→{state.next_agent}", passed)
    assert passed, f"Expected 'care_plan' → 'END', got '{state.current_agent}' → '{state.next_agent}'"


# ============================================================================
# TEST 6: SET NEXT AGENT - END STATE
# ============================================================================

def test_set_next_agent_to_end():
    """Test: set_next_agent updates state for workflow end."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Set to END
    state = set_next_agent(state, "END")

    # After: current_agent is "END", next_agent is None
    passed = (state.current_agent == "END" and state.next_agent is None)

    print_test_result(6, "set_next_agent for END state", "END→None", f"{state.current_agent}→{state.next_agent}", passed)
    assert passed, f"Expected 'END' → None, got '{state.current_agent}' → '{state.next_agent}'"


# ============================================================================
# TEST 7: ROUTER IS STATELESS - NO SIDE EFFECTS
# ============================================================================

def test_router_stateless():
    """Test: Router makes no state changes, only returns routing decision."""
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Capture initial state values
    initial_patient_id = state.patient_id
    initial_prediction = state.prediction
    initial_probability = state.probability
    initial_patient_context = state.patient_context
    initial_care_plan = state.care_plan

    # Call router multiple times
    result1 = route_next_agent(state)
    result2 = route_next_agent(state)
    result3 = route_next_agent(state)

    # Verify state unchanged
    state_unchanged = (
        state.patient_id == initial_patient_id and
        state.prediction == initial_prediction and
        state.probability == initial_probability and
        state.patient_context == initial_patient_context and
        state.care_plan == initial_care_plan and
        result1 == result2 == result3 == "care_plan"
    )

    print_test_result(7, "Router is stateless (no side effects)", "Same result x3", f"{result1}=={result2}=={result3}", state_unchanged)
    assert state_unchanged, "Router modified state or produced different results"


# ============================================================================
# TEST 8: TYPE CHECKING
# ============================================================================

def test_route_next_agent_type_checking():
    """Test: route_next_agent validates input type."""
    try:
        # Pass invalid type
        route_next_agent("not a state")  # type: ignore
        raise AssertionError("Expected TypeError")
    except TypeError as e:
        passed = "Expected OrchestratorState" in str(e)
        print_test_result(8, "route_next_agent type checking", "TypeError", "TypeError", passed)
        assert passed, f"Expected type validation error, got: {e}"


def test_set_next_agent_type_checking():
    """Test: set_next_agent validates input types."""
    try:
        # Pass invalid state type
        set_next_agent("not a state", "care_plan")  # type: ignore
        raise AssertionError("Expected TypeError")
    except TypeError as e:
        passed = "Expected OrchestratorState" in str(e)
        print_test_result(9, "set_next_agent state type checking", "TypeError", "TypeError", passed)
        assert passed, f"Expected state type validation error, got: {e}"

    try:
        # Pass invalid agent name
        state = create_initial_state("P000003", 1, 0.86)
        set_next_agent(state, "invalid_agent")  # type: ignore
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        passed = "Invalid agent name" in str(e)
        print_test_result(10, "set_next_agent agent name validation", "ValueError", "ValueError", passed)
        assert passed, f"Expected agent name validation error, got: {e}"


# ============================================================================
# TEST 9: ROUTING SEQUENCE SIMULATION
# ============================================================================

def test_complete_routing_sequence():
    """Test: Simulate complete routing sequence from initial state to END."""
    # Step 1: Initial state
    state = create_initial_state(
        patient_id="P000003",
        prediction=1,
        probability=0.86
    )

    # Step 2: Route to Care Plan Agent
    result1 = route_next_agent(state)
    assert result1 == "care_plan", f"Step 1: Expected 'care_plan', got '{result1}'"

    # Step 3: Set Care Plan Agent as current
    state = set_next_agent(state, "care_plan")
    assert state.current_agent == "care_plan", "Step 2: current_agent not set"

    # Step 4: Simulate Care Plan Agent completing (in real workflow, agent would do this)
    state.care_plan = CarePlanOutput(
        patient_id="P000003",
        care_plan_id="CP-001",
        risk_level="HIGH",
        intensity="INTENSIVE",
        status="ACTIVE",
        tasks=[
            CareTask(task_id="T1", task_type="EARLY_CHECKIN", status="PENDING")
        ]
    )
    state.workflow_status = "RUNNING"

    # Step 5: Route again after Care Plan completion
    result2 = route_next_agent(state)
    assert result2 == "END", f"Step 3: Expected 'END', got '{result2}'"

    # Step 6: Set workflow to END
    state = set_next_agent(state, "END")
    assert state.current_agent == "END", "Step 4: current_agent not set to END"

    # Step 7: Verify final state
    state.workflow_status = "COMPLETED"

    print_test_result(11, "Complete routing sequence", "care_plan→END", "care_plan→END", True)


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*120)
    print("TESTING ORCHESTRATOR ROUTER")
    print("="*120 + "\n")

    # Run all tests
    test_initial_routing_to_care_plan()
    test_routing_after_care_plan_completion()
    test_routing_on_error()
    test_error_precedence()
    test_set_next_agent_to_care_plan()
    test_set_next_agent_to_end()
    test_router_stateless()
    test_route_next_agent_type_checking()
    test_set_next_agent_type_checking()
    test_complete_routing_sequence()

    print("\n" + "="*120)
    print("ALL ROUTER TESTS PASSED ✅")
    print("="*120 + "\n")
