"""
Tests for Follow-up Agent schemas.

Verifies that all Follow-up Agent schema models work correctly,
including validation rules and error handling.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.follow_up.schemas import (
    FollowUpTask,
    PatientPreferences,
    FollowUpInput,
    CheckIn,
    FollowUpOutput,
)


def print_test_result(test_num: int, name: str, expected: str, actual: str, passed: bool):
    """Print test result in table format."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"TEST {test_num:2d} | {name:<50} | Expected: {expected:<15} | Actual: {actual:<15} | {status}")


print("\n" + "="*130)
print("TESTING FOLLOW-UP AGENT SCHEMAS")
print("="*130 + "\n")

# ============================================================================
# TEST 1: Valid HIGH/INTENSIVE input with 5 tasks
# ============================================================================

test1_passed = False
try:
    tasks_1 = [
        FollowUpTask(task_id="T-001", task_type="EARLY_CHECKIN", status="PENDING"),
        FollowUpTask(task_id="T-002", task_type="FREQUENT_CHECKINS", status="PENDING"),
        FollowUpTask(task_id="T-003", task_type="FOLLOW_UP_APPOINTMENT", status="PENDING"),
        FollowUpTask(task_id="T-004", task_type="APPOINTMENT_MONITORING", status="PENDING"),
        FollowUpTask(task_id="T-005", task_type="CONCERN_ESCALATION", status="PENDING"),
    ]

    input_1 = FollowUpInput(
        mrn="MRN001",
        care_plan_id="CP-001",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_1,
        notes="Meet Dr. X after 7 days"
    )

    test1_passed = (
        input_1.mrn == "MRN001" and
        input_1.care_plan_id == "CP-001" and
        input_1.risk_level == "HIGH" and
        input_1.intensity == "INTENSIVE" and
        len(input_1.tasks) == 5 and
        all(t.status == "PENDING" for t in input_1.tasks)
    )
except Exception as e:
    print(f"TEST 1 Error: {e}")

print_test_result(1, "Valid HIGH/INTENSIVE input with 5 tasks", "PASS", "PASS" if test1_passed else "FAIL", test1_passed)

# ============================================================================
# TEST 2: Valid MODERATE/REGULAR input
# ============================================================================

test2_passed = False
try:
    tasks_2 = [
        FollowUpTask(task_id="T-101", task_type="CHECKIN", status="PENDING"),
        FollowUpTask(task_id="T-102", task_type="FOLLOW_UP_APPOINTMENT", status="PENDING"),
        FollowUpTask(task_id="T-103", task_type="APPOINTMENT_REMINDER", status="PENDING"),
        FollowUpTask(task_id="T-104", task_type="RESPONSE_MONITORING", status="PENDING"),
    ]

    input_2 = FollowUpInput(
        mrn="MRN002",
        care_plan_id="CP-002",
        risk_level="MODERATE",
        intensity="REGULAR",
        tasks=tasks_2,
    )

    test2_passed = (
        input_2.risk_level == "MODERATE" and
        input_2.intensity == "REGULAR" and
        len(input_2.tasks) == 4
    )
except Exception as e:
    print(f"TEST 2 Error: {e}")

print_test_result(2, "Valid MODERATE/REGULAR input", "PASS", "PASS" if test2_passed else "FAIL", test2_passed)

# ============================================================================
# TEST 3: Valid LOW/BASIC input
# ============================================================================

test3_passed = False
try:
    tasks_3 = [
        FollowUpTask(task_id="T-201", task_type="BASIC_CHECKIN", status="PENDING"),
        FollowUpTask(task_id="T-202", task_type="FOLLOW_UP_REMINDER", status="PENDING"),
        FollowUpTask(task_id="T-203", task_type="PATIENT_SUPPORT", status="PENDING"),
    ]

    input_3 = FollowUpInput(
        mrn="MRN003",
        care_plan_id="CP-003",
        risk_level="LOW",
        intensity="BASIC",
        tasks=tasks_3,
    )

    test3_passed = (
        input_3.risk_level == "LOW" and
        input_3.intensity == "BASIC" and
        len(input_3.tasks) == 3
    )
except Exception as e:
    print(f"TEST 3 Error: {e}")

print_test_result(3, "Valid LOW/BASIC input", "PASS", "PASS" if test3_passed else "FAIL", test3_passed)

# ============================================================================
# TEST 4: Empty MRN → validation error
# ============================================================================

test4_passed = False
try:
    tasks_4 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_4 = FollowUpInput(
        mrn="",
        care_plan_id="CP-004",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_4,
    )
    test4_passed = False
except ValueError as e:
    test4_passed = "MRN cannot be empty" in str(e)

print_test_result(4, "Empty MRN → validation error", "ValidationError", "ValidationError" if test4_passed else "PASS", test4_passed)

# ============================================================================
# TEST 5: Empty care_plan_id → validation error
# ============================================================================

test5_passed = False
try:
    tasks_5 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_5 = FollowUpInput(
        mrn="MRN005",
        care_plan_id="",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_5,
    )
    test5_passed = False
except ValueError as e:
    test5_passed = "care_plan_id cannot be empty" in str(e)

print_test_result(5, "Empty care_plan_id → validation error", "ValidationError", "ValidationError" if test5_passed else "PASS", test5_passed)

# ============================================================================
# TEST 6: Invalid risk_level → validation error
# ============================================================================

test6_passed = False
try:
    tasks_6 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_6 = FollowUpInput(
        mrn="MRN006",
        care_plan_id="CP-006",
        risk_level="INVALID",
        intensity="INTENSIVE",
        tasks=tasks_6,
    )
    test6_passed = False
except ValueError as e:
    test6_passed = "Invalid risk_level" in str(e)

print_test_result(6, "Invalid risk_level → validation error", "ValidationError", "ValidationError" if test6_passed else "PASS", test6_passed)

# ============================================================================
# TEST 7: Invalid intensity → validation error
# ============================================================================

test7_passed = False
try:
    tasks_7 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_7 = FollowUpInput(
        mrn="MRN007",
        care_plan_id="CP-007",
        risk_level="HIGH",
        intensity="INVALID",
        tasks=tasks_7,
    )
    test7_passed = False
except ValueError as e:
    test7_passed = "Invalid intensity" in str(e)

print_test_result(7, "Invalid intensity → validation error", "ValidationError", "ValidationError" if test7_passed else "PASS", test7_passed)

# ============================================================================
# TEST 8: Invalid task status → validation error
# ============================================================================

test8_passed = False
try:
    task_8 = FollowUpTask(task_id="T-001", task_type="CHECKIN", status="INVALID_STATUS")
    test8_passed = False
except ValueError as e:
    test8_passed = "Input should be 'PENDING'" in str(e) or "status" in str(e).lower()

print_test_result(8, "Invalid task status → validation error", "ValidationError", "ValidationError" if test8_passed else "PASS", test8_passed)

# ============================================================================
# TEST 9: Valid patient preferences
# ============================================================================

test9_passed = False
try:
    prefs_9 = PatientPreferences(
        language="en",
        preferred_checkin_time="09:00",
        preferred_channel="sms"
    )

    tasks_9 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_9 = FollowUpInput(
        mrn="MRN009",
        care_plan_id="CP-009",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_9,
        patient_preferences=prefs_9
    )

    test9_passed = (
        input_9.patient_preferences is not None and
        input_9.patient_preferences.language == "en" and
        input_9.patient_preferences.preferred_checkin_time == "09:00"
    )
except Exception as e:
    print(f"TEST 9 Error: {e}")

print_test_result(9, "Valid patient preferences", "PASS", "PASS" if test9_passed else "FAIL", test9_passed)

# ============================================================================
# TEST 10: Missing patient preferences (optional)
# ============================================================================

test10_passed = False
try:
    tasks_10 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_10 = FollowUpInput(
        mrn="MRN010",
        care_plan_id="CP-010",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_10,
    )

    test10_passed = input_10.patient_preferences is None
except Exception as e:
    print(f"TEST 10 Error: {e}")

print_test_result(10, "Missing patient preferences (optional)", "PASS", "PASS" if test10_passed else "FAIL", test10_passed)

# ============================================================================
# TEST 11: Notes provided
# ============================================================================

test11_passed = False
try:
    notes_text = "Continue medications. See Dr. X in one week."
    tasks_11 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_11 = FollowUpInput(
        mrn="MRN011",
        care_plan_id="CP-011",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_11,
        notes=notes_text
    )

    test11_passed = input_11.notes == notes_text
except Exception as e:
    print(f"TEST 11 Error: {e}")

print_test_result(11, "Notes provided", "PASS", "PASS" if test11_passed else "FAIL", test11_passed)

# ============================================================================
# TEST 12: Notes omitted → None
# ============================================================================

test12_passed = False
try:
    tasks_12 = [FollowUpTask(task_id="T-001", task_type="CHECKIN", status="PENDING")]
    input_12 = FollowUpInput(
        mrn="MRN012",
        care_plan_id="CP-012",
        risk_level="HIGH",
        intensity="INTENSIVE",
        tasks=tasks_12,
    )

    test12_passed = input_12.notes is None
except Exception as e:
    print(f"TEST 12 Error: {e}")

print_test_result(12, "Notes omitted → None", "PASS", "PASS" if test12_passed else "FAIL", test12_passed)

# ============================================================================
# TEST 13: Valid FollowUpOutput
# ============================================================================

test13_passed = False
try:
    output_13 = FollowUpOutput(
        mrn="MRN013",
        care_plan_id="CP-013",
        follow_up={"checkins": [{"checkin_id": "CHK-001", "status": "SENT"}]},
        next_action="WAIT_FOR_PATIENT_RESPONSE",
        error=None
    )

    test13_passed = (
        output_13.mrn == "MRN013" and
        output_13.care_plan_id == "CP-013" and
        output_13.next_action == "WAIT_FOR_PATIENT_RESPONSE" and
        output_13.error is None
    )
except Exception as e:
    print(f"TEST 13 Error: {e}")

print_test_result(13, "Valid FollowUpOutput", "PASS", "PASS" if test13_passed else "FAIL", test13_passed)

# ============================================================================
# TEST 14: Invalid next_action → validation error
# ============================================================================

test14_passed = False
try:
    output_14 = FollowUpOutput(
        mrn="MRN014",
        care_plan_id="CP-014",
        next_action="INVALID_ACTION",
        error=None
    )
    test14_passed = False
except ValueError as e:
    test14_passed = "Invalid next_action" in str(e)

print_test_result(14, "Invalid next_action → validation error", "ValidationError", "ValidationError" if test14_passed else "PASS", test14_passed)

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*130)
all_tests = [
    test1_passed, test2_passed, test3_passed, test4_passed, test5_passed,
    test6_passed, test7_passed, test8_passed, test9_passed, test10_passed,
    test11_passed, test12_passed, test13_passed, test14_passed
]
passed = sum(all_tests)
total = len(all_tests)
print(f"RESULTS: {passed}/{total} tests passed")
print("="*130 + "\n")

if passed == total:
    print("✅ ALL FOLLOW-UP SCHEMAS TESTS PASSED")
else:
    print(f"❌ {total - passed} test(s) failed")
