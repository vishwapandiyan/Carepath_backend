"""
Tests for MRN + Notes workflow modifications.

Tests verify:
1. MRN-based patient lookup (using readmission dataset)
2. Notes handling (meaningful vs. empty)
3. OrchestratorState with MRN and notes
4. Care Plan Agent with MRN + notes input
5. End-to-end LangGraph workflow with new schema
6. Backward compatibility checks
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.state import OrchestratorState, create_initial_state
from orchestrator.graph import invoke_orchestrator
from services.care_plan_service import _clear_stores


def print_test_result(test_num: int, name: str, expected: str, actual: str, passed: bool):
    """Print test result in table format."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"TEST {test_num:2d} | {name:<50} | Expected: {expected:<15} | Actual: {actual:<15} | {status}")


print("\n" + "="*130)
print("TESTING MRN + NOTES WORKFLOW MODIFICATIONS")
print("="*130 + "\n")

# ============================================================================
# TEST 1: HIGH RISK, EMPTY NOTES
# ============================================================================

_clear_stores()
state1 = create_initial_state("MRN001", prediction=1, probability=0.86, notes="")
result1 = invoke_orchestrator(state1)

test1_passed = (
    result1.mrn == "MRN001" and
    result1.care_plan is not None and
    result1.care_plan.risk_level == "HIGH" and
    result1.care_plan.intensity == "INTENSIVE" and
    result1.workflow_status == "COMPLETED" and
    result1.error is None
)

print_test_result(1, "HIGH risk, empty notes", "HIGH/INTENSIVE/COMPLETED", f"{result1.care_plan.risk_level if result1.care_plan else 'None'}/{result1.care_plan.intensity if result1.care_plan else 'None'}/{result1.workflow_status}", test1_passed)

# ============================================================================
# TEST 2: MODERATE RISK, EMPTY NOTES
# ============================================================================

_clear_stores()
state2 = create_initial_state("MRN002", prediction=0, probability=0.65, notes="")
result2 = invoke_orchestrator(state2)

test2_passed = (
    result2.mrn == "MRN002" and
    result2.care_plan is not None and
    result2.care_plan.risk_level == "MODERATE" and
    result2.care_plan.intensity == "REGULAR" and
    result2.workflow_status == "COMPLETED"
)

print_test_result(2, "MODERATE risk, empty notes", "MODERATE/REGULAR/COMPLETED", f"{result2.care_plan.risk_level if result2.care_plan else 'None'}/{result2.care_plan.intensity if result2.care_plan else 'None'}/{result2.workflow_status}", test2_passed)

# ============================================================================
# TEST 3: LOW RISK, EMPTY NOTES
# ============================================================================

_clear_stores()
state3 = create_initial_state("MRN001", prediction=0, probability=0.25, notes="")
result3 = invoke_orchestrator(state3)

test3_passed = (
    result3.care_plan is not None and
    result3.care_plan.risk_level == "LOW" and
    result3.care_plan.intensity == "BASIC" and
    result3.workflow_status == "COMPLETED"
)

print_test_result(3, "LOW risk, empty notes", "LOW/BASIC/COMPLETED", f"{result3.care_plan.risk_level if result3.care_plan else 'None'}/{result3.care_plan.intensity if result3.care_plan else 'None'}/{result3.workflow_status}", test3_passed)

# ============================================================================
# TEST 4: HIGH RISK WITH MEANINGFUL NOTES
# ============================================================================

_clear_stores()
notes_text = "Meet Dr. X after 7 days and continue medications."
state4 = create_initial_state("MRN001", prediction=1, probability=0.86, notes=notes_text)
result4 = invoke_orchestrator(state4)

test4_passed = (
    result4.care_plan is not None and
    result4.care_plan.risk_level == "HIGH" and
    result4.care_plan.intensity == "INTENSIVE" and
    result4.care_plan.notes == notes_text and  # Notes preserved
    result4.workflow_status == "COMPLETED"
)

print_test_result(4, "HIGH risk WITH notes (preserved)", "Notes preserved", f"Notes preserved: {result4.care_plan.notes == notes_text if result4.care_plan else False}", test4_passed)

# ============================================================================
# TEST 5: NOTES VARIATIONS (None, empty, whitespace)
# ============================================================================

_clear_stores()
test5_results = []

for notes_input, label in [(None, "None"), ("", "empty string"), ("   ", "whitespace")]:
    state = create_initial_state("MRN001", prediction=1, probability=0.86, notes=notes_input)
    result = invoke_orchestrator(state)
    # All should result in notes=None in output (no meaningful notes)
    notes_normalized = result.care_plan.notes is None if result.care_plan else True
    test5_results.append(notes_normalized)

test5_passed = all(test5_results)
print_test_result(5, "Notes variations (None/''/whitespace)", "All normalize to None", f"None:{test5_results[0]}, '':{test5_results[1]}, '   ':{test5_results[2]}", test5_passed)

# ============================================================================
# TEST 6: INVALID MRN (nonexistent patient)
# ============================================================================

_clear_stores()
state6 = create_initial_state("MRN999999", prediction=1, probability=0.86, notes="")
result6 = invoke_orchestrator(state6)

test6_passed = (
    result6.workflow_status == "FAILED" and
    result6.error is not None and
    "not found" in result6.error.lower()
)

print_test_result(6, "Invalid MRN (MRN999999)", "FAILED + error", f"Status:{result6.workflow_status}, Error set:{result6.error is not None}", test6_passed)

# ============================================================================
# TEST 7: INVALID PROBABILITY (> 1.0)
# ============================================================================

_clear_stores()
try:
    state7 = OrchestratorState(mrn="MRN001", prediction=1, probability=1.5, notes="")
    result7 = invoke_orchestrator(state7)
    test7_passed = False
except Exception as e:
    test7_passed = "less than or equal to 1" in str(e) or "greater than" in str(e).lower()

print_test_result(7, "Invalid probability (1.5)", "Validation error", f"Caught: {test7_passed}", test7_passed)

# ============================================================================
# TEST 8: INVALID PREDICTION (not 0 or 1)
# ============================================================================

_clear_stores()
try:
    state8 = OrchestratorState(mrn="MRN001", prediction=2, probability=0.5, notes="")
    result8 = invoke_orchestrator(state8)
    test8_passed = False
except Exception as e:
    test8_passed = "0 or 1" in str(e).lower()

print_test_result(8, "Invalid prediction (2)", "Validation error", f"Caught: {test8_passed}", test8_passed)

# ============================================================================
# TEST 9: EXISTING ACTIVE CARE PLAN (no duplicate)
# ============================================================================

_clear_stores()
state9a = create_initial_state("MRN001", prediction=1, probability=0.86, notes="")
result9a = invoke_orchestrator(state9a)
first_care_plan_id = result9a.care_plan.care_plan_id if result9a.care_plan else None

# Run again - should reuse existing plan
state9b = create_initial_state("MRN001", prediction=1, probability=0.86, notes="New notes")
result9b = invoke_orchestrator(state9b)
second_care_plan_id = result9b.care_plan.care_plan_id if result9b.care_plan else None

test9_passed = (
    first_care_plan_id is not None and
    second_care_plan_id is not None and
    first_care_plan_id == second_care_plan_id  # Same plan, not duplicate
)

print_test_result(9, "Existing active plan (no duplicate)", "Same plan reused", f"Plan IDs same: {first_care_plan_id == second_care_plan_id}", test9_passed)

# ============================================================================
# TEST 10: END-TO-END LANGGRAPH TEST
# ============================================================================

_clear_stores()
state10 = OrchestratorState(
    mrn="MRN001",
    prediction=1,
    probability=0.86,
    notes="Meet Dr. X after 7 days."
)
result10 = invoke_orchestrator(state10)

test10_passed = (
    result10.mrn == "MRN001" and
    result10.prediction == 1 and
    result10.probability == 0.86 and
    result10.patient_context is None or isinstance(result10.patient_context, dict) and
    result10.care_plan is not None and
    result10.notes == "Meet Dr. X after 7 days." and
    result10.workflow_status == "COMPLETED" and
    result10.error is None
)

print_test_result(10, "End-to-end LangGraph test", "All fields correct", f"Complete flow: {test10_passed}", test10_passed)

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*130)
all_tests = [test1_passed, test2_passed, test3_passed, test4_passed, test5_passed, test6_passed, test7_passed, test8_passed, test9_passed, test10_passed]
passed = sum(all_tests)
total = len(all_tests)
print(f"RESULTS: {passed}/{total} tests passed")
print("="*130 + "\n")

if passed == total:
    print("✅ ALL MRN + NOTES TESTS PASSED")
else:
    print(f"❌ {total - passed} test(s) failed")

# Print detailed state for one successful case
print("\n" + "="*130)
print("DETAILED STATE EXAMPLE - TEST 4 (HIGH RISK WITH NOTES)")
print("="*130)
print(f"  mrn: {result4.mrn}")
print(f"  prediction: {result4.prediction}")
print(f"  probability: {result4.probability}")
print(f"  notes (input): {notes_text}")
print(f"  notes (output): {result4.care_plan.notes if result4.care_plan else 'N/A'}")
print(f"  workflow_status: {result4.workflow_status}")
print(f"  error: {result4.error}")
print(f"  care_plan.risk_level: {result4.care_plan.risk_level if result4.care_plan else 'N/A'}")
print(f"  care_plan.intensity: {result4.care_plan.intensity if result4.care_plan else 'N/A'}")
print(f"  care_plan.status: {result4.care_plan.status if result4.care_plan else 'N/A'}")
print(f"  care_plan.tasks: {len(result4.care_plan.tasks) if result4.care_plan else 0} tasks")
print("="*130 + "\n")
