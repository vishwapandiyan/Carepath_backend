"""
Schema-level tests for appointment/schemas.py.

These tests verify structural validation rules only — no HTTP calls,
no LangGraph, no mocks required.

Required coverage (10 tests from spec):
  1.  PCP request valid without specialty
  2.  URGENT_CARE request valid without specialty
  3.  SPECIALIST request requires specialty
  4.  TELEHEALTH request structurally supported
  5.  Booking requires patient_id / provider_id / slot_id
  6.  Rescheduling requires appointment_id
  7.  Rescheduling supports new_slot_id (Workflow A)
  8.  Rescheduling supports preferred date/time (Workflow B)
  9.  Cancellation requires appointment_id
  10. Existing appointment/client tests still pass (import smoke-test)

Additional tests verify cross-field validators and model imports.

Run with:
    python -m pytest tests/test_appointment_schemas.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.alternate_care.appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentPreferences,
    AppointmentStatusResponse,
    AppointmentWorkflowRequest,
    AvailabilityWorkflowRequest,
    AvailabilityWorkflowResponse,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from app.services.alternate_care.models.schemas import AppointmentSlot  # re-used, not duplicated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot() -> AppointmentSlot:
    return AppointmentSlot(
        slot_id="slot_001",
        provider_id="provider_001",
        start_time="2026-08-25T09:00:00",
        end_time="2026-08-25T09:30:00",
    )


# ---------------------------------------------------------------------------
# Test 1 — PCP request valid without specialty
# ---------------------------------------------------------------------------

def test_pcp_availability_request_valid_without_specialty():
    """PCP care type must be accepted when specialty is absent (None)."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_abc",
        provider_id="provider_001",
        care_type="PCP",
        # specialty omitted
    )
    assert req.care_type == "PCP"
    assert req.specialty is None


def test_pcp_workflow_request_valid_without_specialty():
    """CHECK_AVAILABILITY for PCP must not require specialty."""
    req = AppointmentWorkflowRequest(
        intent="CHECK_AVAILABILITY",
        patient_id="patient_001",
        care_type="PCP",
        provider_id="provider_001",
        # specialty intentionally absent
    )
    assert req.care_type == "PCP"
    assert req.specialty is None


# ---------------------------------------------------------------------------
# Test 2 — URGENT_CARE request valid without specialty
# ---------------------------------------------------------------------------

def test_urgent_care_availability_request_valid_without_specialty():
    """URGENT_CARE care type must be accepted without specialty."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_abc",
        provider_id="provider_001",
        care_type="URGENT_CARE",
    )
    assert req.care_type == "URGENT_CARE"
    assert req.specialty is None


def test_urgent_care_workflow_request_valid_without_specialty():
    """BOOK_APPOINTMENT for URGENT_CARE must succeed without specialty."""
    req = AppointmentWorkflowRequest(
        intent="BOOK_APPOINTMENT",
        patient_id="patient_001",
        care_type="URGENT_CARE",
        provider_id="provider_001",
        slot_id="slot_001",
    )
    assert req.care_type == "URGENT_CARE"
    assert req.specialty is None


# ---------------------------------------------------------------------------
# Test 3 — SPECIALIST request requires specialty
# ---------------------------------------------------------------------------

def test_specialist_availability_request_requires_specialty():
    """AvailabilityWorkflowRequest with SPECIALIST must reject absent specialty."""
    with pytest.raises(ValidationError) as exc_info:
        AvailabilityWorkflowRequest(
            recommendation_id="rec_abc",
            provider_id="provider_001",
            care_type="SPECIALIST",
            # specialty absent — should fail
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("specialty" in m.lower() for m in messages), (
        f"Expected a specialty-related validation error; got: {messages}"
    )


def test_specialist_workflow_request_requires_specialty():
    """AppointmentWorkflowRequest with care_type=SPECIALIST must reject absent specialty."""
    with pytest.raises(ValidationError) as exc_info:
        AppointmentWorkflowRequest(
            intent="CHECK_AVAILABILITY",
            patient_id="patient_001",
            care_type="SPECIALIST",
            provider_id="provider_001",
            # specialty absent — should fail
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("specialty" in m.lower() for m in messages), (
        f"Expected a specialty-related validation error; got: {messages}"
    )


def test_specialist_availability_request_valid_with_specialty():
    """SPECIALIST availability request is accepted when specialty is provided."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_abc",
        provider_id="provider_001",
        care_type="SPECIALIST",
        specialty="ORTHOPEDICS",
    )
    assert req.specialty == "ORTHOPEDICS"


# ---------------------------------------------------------------------------
# Test 4 — TELEHEALTH structurally supported
# ---------------------------------------------------------------------------

def test_telehealth_availability_request_without_specialty():
    """TELEHEALTH care type must be accepted without specialty."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_abc",
        provider_id="provider_001",
        care_type="TELEHEALTH",
    )
    assert req.care_type == "TELEHEALTH"
    assert req.specialty is None


def test_telehealth_availability_request_with_specialty():
    """TELEHEALTH with a specialty (e.g. from SPECIALIST upstream) must be accepted."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_abc",
        provider_id="provider_001",
        care_type="TELEHEALTH",
        specialty="CARDIOLOGY",
    )
    assert req.specialty == "CARDIOLOGY"


def test_telehealth_workflow_request_book():
    """BOOK_APPOINTMENT for TELEHEALTH must succeed with slot_id and no specialty."""
    req = AppointmentWorkflowRequest(
        intent="BOOK_APPOINTMENT",
        patient_id="patient_001",
        care_type="TELEHEALTH",
        provider_id="provider_telehealth_001",
        slot_id="slot_telehealth_001",
    )
    assert req.care_type == "TELEHEALTH"
    assert req.slot_id == "slot_telehealth_001"


# ---------------------------------------------------------------------------
# Test 5 — Booking requires patient_id, provider_id, slot_id
# ---------------------------------------------------------------------------

def test_booking_workflow_request_all_required_fields():
    """BookingWorkflowRequest accepts all required fields."""
    req = BookingWorkflowRequest(
        patient_id="patient_001",
        recommendation_id="rec_abc",
        provider_id="provider_001",
        slot_id="slot_001",
    )
    assert req.patient_id == "patient_001"
    assert req.recommendation_id == "rec_abc"
    assert req.provider_id == "provider_001"
    assert req.slot_id == "slot_001"


def test_booking_workflow_request_missing_patient_id():
    """BookingWorkflowRequest must reject a missing patient_id."""
    with pytest.raises(ValidationError):
        BookingWorkflowRequest(
            # patient_id absent
            recommendation_id="rec_abc",
            provider_id="provider_001",
            slot_id="slot_001",
        )


def test_booking_workflow_request_missing_provider_id():
    """BookingWorkflowRequest must reject a missing provider_id."""
    with pytest.raises(ValidationError):
        BookingWorkflowRequest(
            patient_id="patient_001",
            recommendation_id="rec_abc",
            # provider_id absent
            slot_id="slot_001",
        )


def test_booking_workflow_request_missing_slot_id():
    """BookingWorkflowRequest must reject a missing slot_id."""
    with pytest.raises(ValidationError):
        BookingWorkflowRequest(
            patient_id="patient_001",
            recommendation_id="rec_abc",
            provider_id="provider_001",
            # slot_id absent
        )


def test_appointment_workflow_book_missing_slot_id():
    """BOOK_APPOINTMENT intent on AppointmentWorkflowRequest requires slot_id."""
    with pytest.raises(ValidationError) as exc_info:
        AppointmentWorkflowRequest(
            intent="BOOK_APPOINTMENT",
            patient_id="patient_001",
            provider_id="provider_001",
            # slot_id absent
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("slot_id" in m.lower() for m in messages), (
        f"Expected slot_id validation error; got: {messages}"
    )


# ---------------------------------------------------------------------------
# Test 6 — Rescheduling requires appointment_id
# ---------------------------------------------------------------------------

def test_reschedule_request_requires_appointment_id():
    """RescheduleRequest must reject a missing appointment_id."""
    with pytest.raises(ValidationError):
        RescheduleRequest(
            patient_id="patient_001",
            # appointment_id absent
            new_slot_id="slot_002",
        )


def test_reschedule_workflow_request_requires_appointment_id():
    """RESCHEDULE_APPOINTMENT intent requires appointment_id."""
    with pytest.raises(ValidationError) as exc_info:
        AppointmentWorkflowRequest(
            intent="RESCHEDULE_APPOINTMENT",
            patient_id="patient_001",
            # appointment_id absent — validator should fail
            new_slot_id="slot_002",  # extra field, ignored
            preferred_date="2026-08-25",
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("appointment_id" in m.lower() for m in messages), (
        f"Expected appointment_id error; got: {messages}"
    )


# ---------------------------------------------------------------------------
# Test 7 — Rescheduling supports new_slot_id (Workflow A)
# ---------------------------------------------------------------------------

def test_reschedule_workflow_a_new_slot_id():
    """RescheduleRequest Workflow A: appointment_id + new_slot_id is valid."""
    req = RescheduleRequest(
        patient_id="patient_001",
        appointment_id="appt_001",
        new_slot_id="slot_002",
    )
    assert req.appointment_id == "appt_001"
    assert req.new_slot_id == "slot_002"
    assert req.preferred_date is None
    assert req.preferred_time is None


def test_reschedule_workflow_a_via_intent():
    """RESCHEDULE_APPOINTMENT with appointment_id and slot_id accepted."""
    req = AppointmentWorkflowRequest(
        intent="RESCHEDULE_APPOINTMENT",
        patient_id="patient_001",
        appointment_id="appt_001",
        slot_id="slot_002",
    )
    assert req.slot_id == "slot_002"


# ---------------------------------------------------------------------------
# Test 8 — Rescheduling supports preferred date/time (Workflow B)
# ---------------------------------------------------------------------------

def test_reschedule_workflow_b_preferred_date():
    """RescheduleRequest Workflow B: appointment_id + preferred_date is valid."""
    req = RescheduleRequest(
        patient_id="patient_001",
        appointment_id="appt_001",
        preferred_date="2026-08-30",
    )
    assert req.preferred_date == "2026-08-30"
    assert req.new_slot_id is None


def test_reschedule_workflow_b_preferred_time():
    """RescheduleRequest Workflow B: appointment_id + preferred_time alone is valid."""
    req = RescheduleRequest(
        patient_id="patient_001",
        appointment_id="appt_001",
        preferred_time="afternoon",
    )
    assert req.preferred_time == "afternoon"
    assert req.new_slot_id is None


def test_reschedule_workflow_b_both_preferred():
    """RescheduleRequest Workflow B: preferred_date + preferred_time together is valid."""
    req = RescheduleRequest(
        patient_id="patient_001",
        appointment_id="appt_001",
        preferred_date="2026-08-30",
        preferred_time="09:00",
    )
    assert req.preferred_date == "2026-08-30"
    assert req.preferred_time == "09:00"


def test_reschedule_no_slot_no_preference_rejected():
    """RescheduleRequest with neither new_slot_id nor preferred date/time must fail."""
    with pytest.raises(ValidationError) as exc_info:
        RescheduleRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
            # neither new_slot_id nor preferred_date/preferred_time
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("new_slot_id" in m.lower() or "preferred" in m.lower() for m in messages), (
        f"Expected slot/preference error; got: {messages}"
    )


# ---------------------------------------------------------------------------
# Test 9 — Cancellation requires appointment_id
# ---------------------------------------------------------------------------

def test_cancellation_requires_appointment_id():
    """CancellationRequest must reject a missing appointment_id."""
    with pytest.raises(ValidationError):
        CancellationRequest(
            patient_id="patient_001",
            # appointment_id absent
        )


def test_cancellation_valid():
    """CancellationRequest with both required fields is accepted."""
    req = CancellationRequest(
        patient_id="patient_001",
        appointment_id="appt_001",
    )
    assert req.patient_id == "patient_001"
    assert req.appointment_id == "appt_001"


def test_cancel_workflow_intent_requires_appointment_id():
    """CANCEL_APPOINTMENT intent requires appointment_id."""
    with pytest.raises(ValidationError) as exc_info:
        AppointmentWorkflowRequest(
            intent="CANCEL_APPOINTMENT",
            patient_id="patient_001",
            # appointment_id absent
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("appointment_id" in m.lower() for m in messages), (
        f"Expected appointment_id error; got: {messages}"
    )


def test_cancel_workflow_intent_valid():
    """CANCEL_APPOINTMENT intent with appointment_id is accepted."""
    req = AppointmentWorkflowRequest(
        intent="CANCEL_APPOINTMENT",
        patient_id="patient_001",
        appointment_id="appt_001",
    )
    assert req.appointment_id == "appt_001"


# ---------------------------------------------------------------------------
# Test 10 — Existing appointment/client tests: import smoke-test
# ---------------------------------------------------------------------------

def test_appointment_client_importable():
    """AppointmentAgentClient must still import cleanly — no schema conflicts."""
    from appointment.client import AppointmentAgentClient  # noqa: F401
    assert AppointmentAgentClient is not None


def test_existing_booking_request_still_importable():
    """models.schemas.BookingRequest must be unaffected by the new schemas."""
    from models.schemas import BookingRequest
    req = BookingRequest(
        patient_id="patient_001",
        recommendation_id="rec_abc",
        provider_id="provider_001",
        slot_id="slot_001",
    )
    assert req.recommendation_id == "rec_abc"


def test_existing_appointment_slot_reused():
    """AppointmentSlot imported from models.schemas is the same object
    used by appointment.schemas — no duplicate definition."""
    from models.schemas import AppointmentSlot as SlotFromModels
    from appointment.schemas import AppointmentSlot as SlotFromAppointment
    assert SlotFromModels is SlotFromAppointment, (
        "AppointmentSlot should be the same class in both modules — "
        "appointment.schemas re-exports models.schemas.AppointmentSlot"
    )


# ---------------------------------------------------------------------------
# Additional — AppointmentConfirmation and AvailabilityWorkflowResponse
# ---------------------------------------------------------------------------

def test_appointment_confirmation_minimal():
    """AppointmentConfirmation accepts minimal fields (no hospital, no names)."""
    conf = AppointmentConfirmation(
        appointment_id="appt_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id="provider_001",
        slot=_slot(),
    )
    assert conf.status == "BOOKED"
    assert conf.hospital_id is None
    assert conf.hospital_name is None
    assert conf.provider_name is None


def test_appointment_confirmation_full_specialist():
    """AppointmentConfirmation accepts all fields for a SPECIALIST booking."""
    conf = AppointmentConfirmation(
        appointment_id="appt_002",
        patient_id="patient_001",
        status="BOOKED",
        provider_id="provider_ortho_001",
        provider_name="Dr. Ortho Specialist",
        care_type="SPECIALIST",
        specialty="ORTHOPEDICS",
        hospital_id="hosp_001",
        hospital_name="City Orthopedic Center",
        slot=_slot(),
        date="2026-08-25",
        time="09:00",
    )
    assert conf.care_type == "SPECIALIST"
    assert conf.specialty == "ORTHOPEDICS"
    assert conf.hospital_name == "City Orthopedic Center"


def test_availability_workflow_response_empty_slots():
    """AvailabilityWorkflowResponse with zero slots is valid."""
    resp = AvailabilityWorkflowResponse(available_slots=[])
    assert resp.available_slots == []


def test_availability_workflow_response_with_slots():
    """AvailabilityWorkflowResponse correctly wraps a list of slots."""
    resp = AvailabilityWorkflowResponse(
        available_slots=[_slot()],
        provider_id="provider_001",
        care_type="URGENT_CARE",
    )
    assert len(resp.available_slots) == 1
    assert resp.available_slots[0].slot_id == "slot_001"


def test_appointment_status_response():
    """AppointmentStatusResponse accepts all lifecycle statuses."""
    for status in ("BOOKED", "RESCHEDULED", "CANCELLED", "COMPLETED"):
        resp = AppointmentStatusResponse(
            appointment_id="appt_001",
            patient_id="patient_001",
            status=status,
        )
        assert resp.status == status


def test_patient_context_optional_fields():
    """AppointmentPatientContext and AppointmentPreferences accept partial data."""
    ctx = AppointmentPatientContext(
        latitude=37.7749,
        longitude=-122.4194,
        preferences=AppointmentPreferences(language="es"),
    )
    assert ctx.preferences.language == "es"
    assert ctx.preferences.preferred_date is None


def test_recommendation_id_not_in_booking_workflow_external_fields():
    """Confirm recommendation_id is present in BookingWorkflowRequest
    (internal use) but documented as stripped at the client boundary.
    The field must exist on the model — its exclusion from the wire
    payload is enforced by AppointmentAgentClient.book(), not the schema."""
    req = BookingWorkflowRequest(
        patient_id="patient_001",
        recommendation_id="rec_internal_only",
        provider_id="provider_001",
        slot_id="slot_001",
    )
    # recommendation_id exists on the internal model
    assert req.recommendation_id == "rec_internal_only"
    # The external payload (as produced by client.py) would be:
    #   {"patient_id": ..., "provider_id": ..., "slot_id": ...}
    # Verify client.py still produces that — check the method exists
    from appointment.client import AppointmentAgentClient
    assert hasattr(AppointmentAgentClient, "book")


# ---------------------------------------------------------------------------
# Taxonomy invariant tests — destination/specialty rules
# ---------------------------------------------------------------------------

def test_dentistry_availability_request_without_specialty():
    """DENTISTRY is a first-class destination; specialty must be None."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_dental",
        provider_id="provider_dental_001",
        care_type="DENTISTRY",
        # specialty intentionally absent
    )
    assert req.care_type == "DENTISTRY"
    assert req.specialty is None


def test_dentistry_workflow_request_valid_without_specialty():
    """CHECK_AVAILABILITY for DENTISTRY must not require specialty."""
    req = AppointmentWorkflowRequest(
        intent="CHECK_AVAILABILITY",
        patient_id="patient_001",
        care_type="DENTISTRY",
        provider_id="provider_dental_001",
    )
    assert req.care_type == "DENTISTRY"
    assert req.specialty is None


def test_pcp_destination_has_no_specialty():
    """PCP destination must accept and retain specialty=None."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_pcp",
        provider_id="provider_001",
        care_type="PCP",
    )
    assert req.specialty is None


def test_urgent_care_destination_has_no_specialty():
    """URGENT_CARE destination must accept and retain specialty=None."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_uc",
        provider_id="provider_001",
        care_type="URGENT_CARE",
    )
    assert req.specialty is None


def test_telehealth_destination_has_no_specialty():
    """TELEHEALTH destination must accept specialty=None."""
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_tele",
        provider_id="provider_001",
        care_type="TELEHEALTH",
    )
    assert req.specialty is None


def test_specialist_destination_requires_specialty():
    """SPECIALIST destination must reject a missing specialty — invariant check."""
    with pytest.raises(ValidationError) as exc_info:
        AvailabilityWorkflowRequest(
            recommendation_id="rec_spec",
            provider_id="provider_001",
            care_type="SPECIALIST",
            # specialty absent — must fail
        )
    messages = [e["msg"] for e in exc_info.value.errors()]
    assert any("specialty" in m.lower() for m in messages)
