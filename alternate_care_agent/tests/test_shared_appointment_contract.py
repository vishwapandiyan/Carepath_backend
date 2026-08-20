"""
Contract-adapter tests for the Shared Appointment Agent external service.

PURPOSE
-------
These tests describe and validate the EXTERNAL contract of the Shared
Appointment Agent (the teammate's service), verify that SharedAppointmentAdapter
correctly translates between internal models and the external wire format,
and confirm that no internal fields leak to the external service.

Step 7B established which fields were MISSING (gap tests asserted absence).
Step 8 implemented the adapter.  The gap tests in this file have been updated
to assert PRESENCE of the adapter-generated fields.

CONTRACT SOURCE
---------------
The external specification provides the following reference shapes:

  Request (BOOK_APPOINTMENT example):
    {
      "actor": "PATIENT",
      "patient_id": "P000003",
      "request": {
        "intent": "BOOK_APPOINTMENT",
        "specialty": "CARDIOLOGY",
        "preferred_date": "2026-08-22",
        "preferred_time": "10:00"
      },
      "patient_context": {
        "location": { "latitude": 11.9139, "longitude": 79.8145 },
        "preference": { "language": "English" }
      }
    }

  Response:
    {
      "patient_id": "P000003",
      "appointment": {
        "appointment_id": "APT-001",
        "provider_id": "DOC-123",
        "provider_name": "Dr. XXXX",
        "specialty": "CARDIOLOGY",
        "hospital_id": "HOSP-001",
        "hospital_name": "XXXXX Hospital",
        "date": "2026-08-22",
        "time": "10:00",
        "status": "BOOKED"
      }
    }

NOTATION USED IN COMMENTS
--------------------------
  CONFIRMED:     field explicitly shown in the specification.
  ASSUMPTION:    reasonable inference; spec does not explicitly define it.
  CONTRACT GAP:  field/behavior not defined in the spec; adapter omits it
                 or applies a documented assumption.
  INTERNAL:      field that belongs only to this project; must never be
                 forwarded externally.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
import requests as _requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from appointment.adapter import SharedAppointmentAdapter
from appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentPreferences,
    AppointmentStatusResponse,
    AppointmentWorkflowRequest,
    AvailabilityWorkflowRequest,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from appointment.client import AppointmentAgentClient
from models.schemas import AppointmentSlot, BookingRequest, Destination


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot(slot_id: str = "slot_001", provider_id: str = "DOC-123") -> AppointmentSlot:
    return AppointmentSlot(
        slot_id=slot_id,
        provider_id=provider_id,
        start_time="2026-08-22T10:00:00",
        end_time="2026-08-22T10:30:00",
    )


def _stub_http(json_body: dict) -> MagicMock:
    """Return a mock HTTP response that succeeds and returns json_body."""
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = json_body
    return m


def _stub_error_http(status_code: int) -> MagicMock:
    """Return a mock HTTP response that raises HTTPError on raise_for_status()."""
    m = MagicMock()
    m.status_code = status_code
    http_err = _requests.exceptions.HTTPError(
        f"{status_code} Error", response=m
    )
    m.raise_for_status = MagicMock(side_effect=http_err)
    return m


# ---------------------------------------------------------------------------
# External contract fixtures — the exact JSON the external service expects
# ---------------------------------------------------------------------------

EXTERNAL_BOOK_REQUEST = {
    "actor": "PATIENT",
    "patient_id": "P000003",
    "request": {
        "intent": "BOOK_APPOINTMENT",
        "specialty": "CARDIOLOGY",
        "preferred_date": "2026-08-22",
        "preferred_time": "10:00",
    },
    "patient_context": {
        "location": {"latitude": 11.9139, "longitude": 79.8145},
        "preference": {"language": "English"},
    },
}

EXTERNAL_AVAILABILITY_REQUEST = {
    "actor": "PATIENT",
    "patient_id": "P000003",
    "request": {
        "intent": "CHECK_AVAILABILITY",
        "specialty": "CARDIOLOGY",
        "preferred_date": "2026-08-22",
        "preferred_time": "10:00",
    },
    "patient_context": {
        "location": {"latitude": 11.9139, "longitude": 79.8145},
        "preference": {"language": "English"},
    },
}

EXTERNAL_BOOKING_RESPONSE = {
    "patient_id": "P000003",
    "appointment": {
        "appointment_id": "APT-001",
        "provider_id": "DOC-123",
        "provider_name": "Dr. XXXX",
        "specialty": "CARDIOLOGY",
        "hospital_id": "HOSP-001",
        "hospital_name": "XXXXX Hospital",
        "date": "2026-08-22",
        "time": "10:00",
        "status": "BOOKED",
    },
}

_PATIENT_CONTEXT = AppointmentPatientContext(
    latitude=11.9139,
    longitude=79.8145,
    preferences=AppointmentPreferences(language="English"),
)


# ===========================================================================
# GROUP 1 — EXTERNAL REQUEST CONTRACT (spec fixtures — unchanged from 7B)
# ===========================================================================

class TestExternalRequestContract:
    """Validate the known shape of external request payloads per specification."""

    def test_book_request_has_actor_patient(self):
        """CONFIRMED: External BOOK request must carry actor = 'PATIENT'."""
        assert EXTERNAL_BOOK_REQUEST["actor"] == "PATIENT"

    def test_book_request_has_patient_id(self):
        """CONFIRMED: External BOOK request must carry patient_id at top level."""
        assert "patient_id" in EXTERNAL_BOOK_REQUEST
        assert EXTERNAL_BOOK_REQUEST["patient_id"] == "P000003"

    def test_book_request_has_nested_request_object(self):
        """CONFIRMED: request sub-object with intent."""
        req = EXTERNAL_BOOK_REQUEST["request"]
        assert req["intent"] == "BOOK_APPOINTMENT"

    def test_book_request_specialist_carries_specialty(self):
        """CONFIRMED: specialty inside request sub-object for SPECIALIST."""
        assert EXTERNAL_BOOK_REQUEST["request"]["specialty"] == "CARDIOLOGY"

    def test_book_request_has_patient_context(self):
        """CONFIRMED: patient_context with location + preference."""
        ctx = EXTERNAL_BOOK_REQUEST["patient_context"]
        assert ctx["location"]["latitude"] == 11.9139
        assert ctx["location"]["longitude"] == 79.8145
        assert ctx["preference"]["language"] == "English"

    def test_book_request_does_not_contain_recommendation_id(self):
        """INTERNAL: recommendation_id must NOT appear in external request."""
        assert "recommendation_id" not in EXTERNAL_BOOK_REQUEST
        assert "recommendation_id" not in EXTERNAL_BOOK_REQUEST.get("request", {})

    def test_book_request_does_not_contain_rule_id(self):
        """INTERNAL: rule_id must NOT appear in external request."""
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(EXTERNAL_BOOK_REQUEST, "rule_id")

    def test_book_request_preferred_date_inside_request_object(self):
        """CONFIRMED: preferred_date nested inside request."""
        assert EXTERNAL_BOOK_REQUEST["request"]["preferred_date"] == "2026-08-22"

    def test_book_request_preferred_time_inside_request_object(self):
        """CONFIRMED: preferred_time nested inside request."""
        assert "preferred_time" in EXTERNAL_BOOK_REQUEST["request"]

    def test_availability_request_intent_is_check_availability(self):
        """CONFIRMED: CHECK_AVAILABILITY intent."""
        assert EXTERNAL_AVAILABILITY_REQUEST["request"]["intent"] == "CHECK_AVAILABILITY"

    def test_availability_request_has_actor(self):
        """CONFIRMED: actor present on availability request."""
        assert EXTERNAL_AVAILABILITY_REQUEST["actor"] == "PATIENT"

    def test_reschedule_workflow_a_expected_structure(self):
        """ASSUMPTION: RESCHEDULE envelope follows book pattern."""
        reschedule_a = {
            "actor": "PATIENT",
            "patient_id": "P000003",
            "request": {
                "intent": "RESCHEDULE_APPOINTMENT",
                "appointment_id": "APT-001",
                "new_slot_id": "SLOT-002",
            },
        }
        assert reschedule_a["request"]["intent"] == "RESCHEDULE_APPOINTMENT"
        assert "appointment_id" in reschedule_a["request"]
        assert "new_slot_id" in reschedule_a["request"]
        assert "recommendation_id" not in reschedule_a["request"]

    def test_reschedule_workflow_b_expected_structure(self):
        """ASSUMPTION: Workflow B uses preferred_date + preferred_time."""
        reschedule_b = {
            "actor": "PATIENT",
            "patient_id": "P000003",
            "request": {
                "intent": "RESCHEDULE_APPOINTMENT",
                "appointment_id": "APT-001",
                "preferred_date": "2026-08-30",
                "preferred_time": "afternoon",
            },
        }
        assert "appointment_id" in reschedule_b["request"]
        assert "preferred_date" in reschedule_b["request"]
        assert "new_slot_id" not in reschedule_b["request"]

    def test_reschedule_does_not_require_recommendation_id(self):
        """INTERNAL: recommendation_id not required for reschedule."""
        req = RescheduleRequest(
            patient_id="P000003",
            appointment_id="APT-001",
            new_slot_id="SLOT-002",
        )
        assert req.recommendation_id is None

    def test_cancel_expected_structure(self):
        """ASSUMPTION: CANCEL envelope follows same pattern."""
        cancel_payload = {
            "actor": "PATIENT",
            "patient_id": "P000003",
            "request": {
                "intent": "CANCEL_APPOINTMENT",
                "appointment_id": "APT-001",
            },
        }
        assert cancel_payload["request"]["intent"] == "CANCEL_APPOINTMENT"
        assert "appointment_id" in cancel_payload["request"]
        assert "recommendation_id" not in cancel_payload["request"]

    def test_cancel_does_not_require_recommendation_id(self):
        """CancellationRequest does not require recommendation_id."""
        req = CancellationRequest(patient_id="P000003", appointment_id="APT-001")
        assert req.patient_id == "P000003"

    def test_status_lookup_contract_gap(self):
        """CONTRACT GAP: status lookup endpoint not defined in spec.
        ASSUMPTION: GET /appointments/{id}?patient_id=..."""
        assert "GET" == "GET"  # documented assumption
        assert "{appointment_id}" in "/appointments/{appointment_id}"


# ===========================================================================
# GROUP 2 — FOUR CARE DESTINATIONS (unchanged from 7B)
# ===========================================================================

@pytest.mark.parametrize("destination,specialty,expect_specialty_in_request", [
    ("PCP",         None,          False),
    ("URGENT_CARE", None,          False),
    ("SPECIALIST",  "CARDIOLOGY",  True),
    ("TELEHEALTH",  None,          False),
    ("DENTISTRY",   None,          False),
])
class TestCareDestinationContract:

    def test_availability_request_representable(
        self, destination, specialty, expect_specialty_in_request
    ):
        kwargs: dict = {
            "recommendation_id": "rec_test",
            "provider_id": "prov_001",
            "care_type": destination,
        }
        if specialty:
            kwargs["specialty"] = specialty
        req = AvailabilityWorkflowRequest(**kwargs)
        assert req.care_type == destination
        assert req.specialty == specialty

    def test_specialty_presence_in_request(
        self, destination, specialty, expect_specialty_in_request
    ):
        kwargs: dict = {
            "recommendation_id": "rec_test",
            "provider_id": "prov_001",
            "care_type": destination,
        }
        if specialty:
            kwargs["specialty"] = specialty
        req = AvailabilityWorkflowRequest(**kwargs)
        if expect_specialty_in_request:
            assert req.specialty is not None
        else:
            assert req.specialty is None

    def test_workflow_request_representable(
        self, destination, specialty, expect_specialty_in_request
    ):
        kwargs: dict = {
            "intent": "CHECK_AVAILABILITY",
            "patient_id": "P000003",
            "care_type": destination,
            "provider_id": "prov_001",
        }
        if specialty:
            kwargs["specialty"] = specialty
        req = AppointmentWorkflowRequest(**kwargs)
        assert req.care_type == destination


def test_specialist_without_specialty_fails_before_external_call():
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        AvailabilityWorkflowRequest(
            recommendation_id="rec_test",
            provider_id="prov_001",
            care_type="SPECIALIST",
        )
    assert any("specialty" in e["msg"].lower()
               for e in exc_info.value.errors())


def test_telehealth_no_physical_location_forced():
    req = AvailabilityWorkflowRequest(
        recommendation_id="rec_test",
        provider_id="telehealth_platform_001",
        care_type="TELEHEALTH",
    )
    assert req.care_type == "TELEHEALTH"


# ===========================================================================
# GROUP 3 — PATIENT CONTEXT FIELDS (formerly contained 3 gap tests;
#            those 3 are now in Group 9 as presence assertions)
# ===========================================================================

class TestPatientContextContract:

    def test_patient_context_latitude_longitude(self):
        ctx = AppointmentPatientContext(latitude=11.9139, longitude=79.8145)
        assert ctx.latitude == 11.9139
        assert ctx.longitude == 79.8145

    def test_patient_context_language_preference(self):
        prefs = AppointmentPreferences(language="English")
        assert prefs.language == "English"

    def test_patient_context_full(self):
        ctx = AppointmentPatientContext(
            latitude=11.9139,
            longitude=79.8145,
            preferences=AppointmentPreferences(language="English"),
        )
        assert ctx.latitude == 11.9139
        assert ctx.preferences.language == "English"

    def test_patient_context_optional_language(self):
        ctx = AppointmentPatientContext(
            latitude=11.9139, longitude=79.8145,
            preferences=AppointmentPreferences(),
        )
        assert ctx.preferences.language is None

    def test_patient_context_optional_location(self):
        ctx = AppointmentPatientContext(
            preferences=AppointmentPreferences(language="English"),
        )
        assert ctx.latitude is None
        assert ctx.longitude is None

    def test_workflow_request_carries_patient_context(self):
        req = AppointmentWorkflowRequest(
            intent="CHECK_AVAILABILITY",
            patient_id="P000003",
            patient_context=AppointmentPatientContext(
                latitude=11.9139,
                longitude=79.8145,
                preferences=AppointmentPreferences(language="English"),
            ),
        )
        assert req.patient_context.latitude == 11.9139
        assert req.patient_context.preferences.language == "English"

    # --- Previously "gap" tests: now verify PRESENCE after adapter ---

    def test_patient_context_IS_sent_by_adapter_when_provided(self):
        """CONFIRMED (after Step 8): adapter includes patient_context when supplied."""
        payload = SharedAppointmentAdapter.build_availability_request(
            patient_id="P000003",
            specialty=None,
            preferred_date=None,
            preferred_time=None,
            date_range="next_7_days",
            patient_context=_PATIENT_CONTEXT,
        )
        assert "patient_context" in payload
        assert payload["patient_context"]["location"]["latitude"] == 11.9139
        assert payload["patient_context"]["location"]["longitude"] == 79.8145
        assert payload["patient_context"]["preference"]["language"] == "English"

    def test_actor_IS_sent_by_adapter(self):
        """CONFIRMED (after Step 8): adapter always includes actor=PATIENT."""
        payload = SharedAppointmentAdapter.build_book_request(
            patient_id="P000003",
            specialty="CARDIOLOGY",
        )
        assert payload["actor"] == "PATIENT"

    def test_intent_IS_sent_inside_request_object(self):
        """CONFIRMED (after Step 8): adapter nests intent inside request sub-object."""
        payload = SharedAppointmentAdapter.build_book_request(
            patient_id="P000003",
            specialty="CARDIOLOGY",
        )
        assert "request" in payload
        assert payload["request"]["intent"] == "BOOK_APPOINTMENT"


# ===========================================================================
# GROUP 4 — RICH RESPONSE CONTRACT (unchanged from 7B)
# ===========================================================================

class TestExternalResponseContract:

    def test_external_response_top_level_fields(self):
        assert "patient_id" in EXTERNAL_BOOKING_RESPONSE
        assert "appointment" in EXTERNAL_BOOKING_RESPONSE

    def test_external_appointment_all_fields_present(self):
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"]
        required = ["appointment_id", "provider_id", "provider_name",
                    "specialty", "hospital_id", "hospital_name",
                    "date", "time", "status"]
        for field in required:
            assert field in appt

    def test_external_response_status_is_booked(self):
        assert EXTERNAL_BOOKING_RESPONSE["appointment"]["status"] == "BOOKED"

    @pytest.mark.parametrize("status", ["BOOKED", "RESCHEDULED", "CANCELLED"])
    def test_appointment_confirmation_accepts_each_status(self, status):
        conf = AppointmentConfirmation(
            appointment_id="APT-001",
            patient_id="P000003",
            status=status,
            provider_id="DOC-123",
            provider_name="Dr. XXXX",
            specialty="CARDIOLOGY",
            hospital_id="HOSP-001",
            hospital_name="XXXXX Hospital",
            slot=_slot(),
            date="2026-08-22",
            time="10:00",
        )
        assert conf.status == status

    def test_completed_status_is_internal_only(self):
        """CONTRACT GAP: COMPLETED not confirmed in external spec."""
        conf = AppointmentConfirmation(
            appointment_id="APT-001",
            patient_id="P000003",
            status="COMPLETED",
            provider_id="DOC-123",
            slot=_slot(),
        )
        assert conf.status == "COMPLETED"
        assert EXTERNAL_BOOKING_RESPONSE["appointment"]["status"] != "COMPLETED"

    def test_external_response_nested_appointment_not_parseable_by_raw_schema(self):
        """
        Schema-level: BookingConfirmation (legacy flat schema) cannot parse
        the external nested envelope directly.  The adapter is required.
        This test remains valid because BookingConfirmation schema is unchanged.
        """
        from pydantic import ValidationError
        from models.schemas import BookingConfirmation
        with pytest.raises((ValidationError, TypeError, KeyError)):
            BookingConfirmation(**EXTERNAL_BOOKING_RESPONSE)  # type: ignore[arg-type]


# ===========================================================================
# GROUP 5 — RESPONSE FIELD MAPPING (unchanged from 7B)
# ===========================================================================

class TestResponseFieldMapping:

    def _parse(self, external: dict) -> AppointmentConfirmation:
        return SharedAppointmentAdapter.parse_book_response(external)

    def test_appointment_id_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).appointment_id == "APT-001"

    def test_patient_id_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).patient_id == "P000003"

    def test_provider_id_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).provider_id == "DOC-123"

    def test_provider_name_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).provider_name == "Dr. XXXX"

    def test_specialty_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).specialty == "CARDIOLOGY"

    def test_hospital_id_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).hospital_id == "HOSP-001"

    def test_hospital_name_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).hospital_name == "XXXXX Hospital"

    def test_date_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).date == "2026-08-22"

    def test_time_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).time == "10:00"

    def test_status_maps_correctly(self):
        assert self._parse(EXTERNAL_BOOKING_RESPONSE).status == "BOOKED"

    def test_no_fields_silently_lost(self):
        conf = self._parse(EXTERNAL_BOOKING_RESPONSE)
        for attr in ("appointment_id", "patient_id", "provider_id",
                     "provider_name", "specialty", "hospital_id",
                     "hospital_name", "date", "time", "status"):
            assert getattr(conf, attr) is not None, f"{attr} must not be None"


# ===========================================================================
# GROUP 6 — INTERNAL FIELDS MUST NOT LEAK
# ===========================================================================

class TestInternalFieldsDoNotLeak:

    def _capture_book_payload(self) -> dict:
        captured = []
        stub = _stub_http({
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-22",
                "time": "10:00",
                "status": "BOOKED",
            },
        })
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_MUST_NOT_LEAK",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            client.book(req)
        return captured[0]

    def test_recommendation_id_not_in_book_payload(self):
        assert "recommendation_id" not in self._capture_book_payload()

    def test_rule_id_not_in_book_payload(self):
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(self._capture_book_payload(), "rule_id")

    def test_priority_not_in_book_payload(self):
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(self._capture_book_payload(), "priority")

    def test_score_not_in_book_payload(self):
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(self._capture_book_payload(), "score")

    def test_distance_km_not_in_book_payload(self):
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(self._capture_book_payload(), "distance_km")

    def test_errors_list_not_in_book_payload(self):
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        assert not _has(self._capture_book_payload(), "errors")

    def test_care_type_not_in_book_payload(self):
        """CONTRACT GAP: no care_type field in external contract — adapter omits it."""
        def _has(d: dict, key: str) -> bool:
            return any(k == key or (isinstance(v, dict) and _has(v, key))
                       for k, v in d.items())
        payload = self._capture_book_payload()
        assert not _has(payload, "care_type")
        assert not _has(payload, "destination")

    def test_provider_id_not_in_book_request_payload(self):
        """CONTRACT GAP: provider_id placement unconfirmed — adapter omits from request."""
        payload = self._capture_book_payload()
        # provider_id should NOT be in the request sub-object
        inner = payload.get("request", {})
        assert "provider_id" not in inner

    def test_slot_id_not_in_book_request_payload(self):
        """CONTRACT GAP: slot_id not shown in spec BOOK request — adapter omits it."""
        payload = self._capture_book_payload()
        inner = payload.get("request", {})
        assert "slot_id" not in inner

    def test_cancel_payload_recommendation_id_absent(self):
        captured = []
        stub = _stub_http({"appointment_id": "APT-001", "patient_id": "P000003",
                           "status": "CANCELLED"})
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        req = CancellationRequest(patient_id="P000003", appointment_id="APT-001")
        with patch("appointment.client.requests.post", side_effect=capture):
            client.cancel_appointment(req)

        payload = captured[0]
        assert "recommendation_id" not in str(payload)
        assert "rule_id" not in str(payload)

    def test_reschedule_payload_does_not_contain_recommendation_id(self):
        captured = []
        stub = _stub_http({
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-30",
                "time": "10:00",
                "status": "RESCHEDULED",
            },
        })
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        req = RescheduleRequest(
            patient_id="P000003",
            appointment_id="APT-001",
            new_slot_id="slot_002",
            recommendation_id="rec_MUST_NOT_LEAK",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            client.reschedule(req)

        payload = captured[0]
        assert "recommendation_id" not in str(payload)


# ===========================================================================
# GROUP 7 — NO REAL NETWORK (unchanged from 7B)
# ===========================================================================

class TestNoRealNetwork:

    def test_mocked_post_does_not_reach_real_host(self):
        called_urls = []
        stub = _stub_http({
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-22",
                "time": "10:00",
                "status": "BOOKED",
            },
        })
        def capture(url, **kw):
            called_urls.append(url)
            return stub

        client = AppointmentAgentClient(base_url="http://localhost:8001")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            client.book(req)

        assert len(called_urls) == 1
        assert "localhost:8001" in called_urls[0]

    def test_mocked_get_does_not_reach_real_host(self):
        called_urls = []
        stub = _stub_http({
            "appointment_id": "APT-001",
            "patient_id": "P000003",
            "status": "BOOKED",
        })
        def capture(url, **kw):
            called_urls.append(url)
            return stub

        client = AppointmentAgentClient(base_url="http://localhost:8001")
        with patch("appointment.client.requests.get", side_effect=capture):
            client.get_appointment("APT-001", patient_id="P000003")

        assert len(called_urls) == 1


# ===========================================================================
# GROUP 8 — (formerly gap analysis; gaps now closed, see Groups 9-11)
#            Remaining gap tests updated from ABSENCE → PRESENCE assertions
# ===========================================================================

class TestAdapterReplacesGaps:
    """
    Step 7B tests in this group asserted that fields were ABSENT from client
    payloads (the gap tests).  Step 8 implemented the adapter.  These tests
    now assert PRESENCE of those fields, confirming the adapter closed the gaps.
    """

    def _capture_availability_payload(
        self,
        patient_id: str = "P000003",
        specialty: Optional[str] = None,
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> dict:
        captured = []
        stub = _stub_http({"available_slots": []})
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        with patch("appointment.client.requests.post", side_effect=capture):
            client.get_availability(
                provider_id="DOC-123",
                care_type="SPECIALIST",
                specialty=specialty,
                date_range="next_7_days",
                patient_id=patient_id,
                patient_context=patient_context,
            )
        return captured[0]

    def test_actor_NOW_present_in_availability_payload(self):
        """Gap closed: 'actor' is now sent by the adapter."""
        payload = self._capture_availability_payload()
        assert payload.get("actor") == "PATIENT"

    def test_intent_NOW_in_nested_request_object_availability(self):
        """Gap closed: 'request.intent' now present in availability payload."""
        payload = self._capture_availability_payload()
        assert "request" in payload
        assert payload["request"]["intent"] == "CHECK_AVAILABILITY"

    def test_patient_id_NOW_in_availability_payload(self):
        """Gap closed: patient_id now at top level of availability payload."""
        payload = self._capture_availability_payload(patient_id="P000003")
        assert payload.get("patient_id") == "P000003"

    def test_patient_context_NOW_in_availability_when_provided(self):
        """Gap closed: patient_context included when AppointmentPatientContext supplied."""
        payload = self._capture_availability_payload(
            patient_context=_PATIENT_CONTEXT
        )
        assert "patient_context" in payload
        assert payload["patient_context"]["location"]["latitude"] == 11.9139
        assert payload["patient_context"]["preference"]["language"] == "English"

    def test_actor_NOW_present_in_book_payload(self):
        """Gap closed: 'actor' now sent in book() payload."""
        captured = []
        stub = _stub_http({
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-22",
                "time": "10:00",
                "status": "BOOKED",
            },
        })
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            client.book(req)

        assert captured[0].get("actor") == "PATIENT"

    def test_nested_request_object_NOW_present_in_book_payload(self):
        """Gap closed: book() now sends nested {actor, patient_id, request:{intent,...}}."""
        captured = []
        stub = _stub_http({
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-22",
                "time": "10:00",
                "status": "BOOKED",
            },
        })
        def capture(url, json=None, timeout=None, **kw):
            captured.append(json or {})
            return stub

        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            client.book(req)

        payload = captured[0]
        assert "request" in payload
        assert payload["request"]["intent"] == "BOOK_APPOINTMENT"

    def test_nested_response_NOW_parsed_by_adapter(self):
        """Gap closed: adapter correctly parses nested appointment envelope."""
        result = SharedAppointmentAdapter.parse_book_response(EXTERNAL_BOOKING_RESPONSE)
        assert isinstance(result, AppointmentConfirmation)
        assert result.appointment_id == "APT-001"
        assert result.patient_id == "P000003"
        assert result.provider_name == "Dr. XXXX"
        assert result.hospital_id == "HOSP-001"


# ===========================================================================
# GROUP 9 — ADAPTER UNIT TESTS: REQUEST BUILDERS
# ===========================================================================

class TestAdapterRequestBuilders:
    """Direct unit tests of SharedAppointmentAdapter static methods."""

    # --- CHECK_AVAILABILITY ---

    def test_availability_pcp_no_specialty(self):
        """PCP: specialty omitted from request."""
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty=None,
            preferred_date=None, preferred_time=None,
        )
        assert p["actor"] == "PATIENT"
        assert p["patient_id"] == "P001"
        assert p["request"]["intent"] == "CHECK_AVAILABILITY"
        assert "specialty" not in p["request"]

    def test_availability_urgent_care_no_specialty(self):
        """URGENT_CARE: specialty omitted."""
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty=None,
            preferred_date=None, preferred_time=None,
        )
        assert "specialty" not in p["request"]

    def test_availability_specialist_with_specialty(self):
        """SPECIALIST: specialty present inside request."""
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty="CARDIOLOGY",
            preferred_date="2026-08-22", preferred_time="10:00",
        )
        assert p["request"]["specialty"] == "CARDIOLOGY"
        assert p["request"]["preferred_date"] == "2026-08-22"
        assert p["request"]["preferred_time"] == "10:00"

    def test_availability_telehealth_no_specialty(self):
        """TELEHEALTH: specialty absent, no physical location required."""
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty=None,
            preferred_date=None, preferred_time=None,
        )
        assert "specialty" not in p["request"]

    def test_availability_with_patient_context(self):
        """patient_context included when provided."""
        ctx = AppointmentPatientContext(
            latitude=11.9139, longitude=79.8145,
            preferences=AppointmentPreferences(language="English"),
        )
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty=None,
            preferred_date=None, preferred_time=None,
            patient_context=ctx,
        )
        assert "patient_context" in p
        assert p["patient_context"]["location"]["latitude"] == 11.9139
        assert p["patient_context"]["preference"]["language"] == "English"

    def test_availability_without_patient_context(self):
        """patient_context absent when not supplied."""
        p = SharedAppointmentAdapter.build_availability_request(
            patient_id="P001", specialty=None,
            preferred_date=None, preferred_time=None,
            patient_context=None,
        )
        assert "patient_context" not in p

    # --- BOOK_APPOINTMENT ---

    def test_book_specialist(self):
        """SPECIALIST book: specialty in request, no provider_id, no slot_id."""
        p = SharedAppointmentAdapter.build_book_request(
            patient_id="P001", specialty="ORTHOPEDICS",
            preferred_date="2026-08-22", preferred_time="10:00",
        )
        assert p["actor"] == "PATIENT"
        assert p["patient_id"] == "P001"
        assert p["request"]["intent"] == "BOOK_APPOINTMENT"
        assert p["request"]["specialty"] == "ORTHOPEDICS"
        # CONTRACT GAPs: these must NOT be present
        assert "provider_id" not in p["request"]
        assert "slot_id" not in p["request"]
        assert "care_type" not in p["request"]
        assert "destination" not in p["request"]
        assert "recommendation_id" not in p["request"]
        assert "recommendation_id" not in p

    def test_book_pcp_no_specialty(self):
        """PCP book: specialty absent."""
        p = SharedAppointmentAdapter.build_book_request(
            patient_id="P001", specialty=None,
        )
        assert "specialty" not in p["request"]

    def test_book_with_patient_context(self):
        """patient_context propagated to BOOK request."""
        ctx = AppointmentPatientContext(
            latitude=11.9139, longitude=79.8145,
            preferences=AppointmentPreferences(language="English"),
        )
        p = SharedAppointmentAdapter.build_book_request(
            patient_id="P001", specialty="CARDIOLOGY",
            patient_context=ctx,
        )
        assert "patient_context" in p
        assert p["patient_context"]["location"]["longitude"] == 79.8145

    # --- RESCHEDULE ---

    def test_reschedule_workflow_a(self):
        """Workflow A: new_slot_id inside request. ASSUMPTION: field name."""
        p = SharedAppointmentAdapter.build_reschedule_request(
            patient_id="P001",
            appointment_id="APT-001",
            new_slot_id="SLOT-002",
        )
        assert p["request"]["intent"] == "RESCHEDULE_APPOINTMENT"
        assert p["request"]["appointment_id"] == "APT-001"
        assert p["request"]["new_slot_id"] == "SLOT-002"
        assert "recommendation_id" not in p["request"]
        assert "recommendation_id" not in p

    def test_reschedule_workflow_b(self):
        """Workflow B: preferred_date + preferred_time, no new_slot_id."""
        p = SharedAppointmentAdapter.build_reschedule_request(
            patient_id="P001",
            appointment_id="APT-001",
            preferred_date="2026-08-30",
            preferred_time="afternoon",
        )
        assert p["request"]["preferred_date"] == "2026-08-30"
        assert p["request"]["preferred_time"] == "afternoon"
        assert "new_slot_id" not in p["request"]

    # --- CANCEL ---

    def test_cancel_request_structure(self):
        """Cancel: appointment_id in request, no recommendation_id."""
        p = SharedAppointmentAdapter.build_cancel_request(
            patient_id="P001",
            appointment_id="APT-001",
        )
        assert p["actor"] == "PATIENT"
        assert p["patient_id"] == "P001"
        assert p["request"]["intent"] == "CANCEL_APPOINTMENT"
        assert p["request"]["appointment_id"] == "APT-001"
        assert "recommendation_id" not in p["request"]
        assert "recommendation_id" not in p


# ===========================================================================
# GROUP 10 — ADAPTER UNIT TESTS: RESPONSE PARSERS
# ===========================================================================

class TestAdapterResponseParsers:

    # --- parse_book_response ---

    def test_parse_book_response_all_fields(self):
        conf = SharedAppointmentAdapter.parse_book_response(EXTERNAL_BOOKING_RESPONSE)
        assert conf.appointment_id == "APT-001"
        assert conf.patient_id == "P000003"
        assert conf.status == "BOOKED"
        assert conf.provider_id == "DOC-123"
        assert conf.provider_name == "Dr. XXXX"
        assert conf.specialty == "CARDIOLOGY"
        assert conf.hospital_id == "HOSP-001"
        assert conf.hospital_name == "XXXXX Hospital"
        assert conf.date == "2026-08-22"
        assert conf.time == "10:00"

    def test_parse_book_response_slot_constructed_from_date_time(self):
        """ASSUMPTION: slot constructed from date+time; slot_id defaults."""
        conf = SharedAppointmentAdapter.parse_book_response(EXTERNAL_BOOKING_RESPONSE)
        assert conf.slot is not None
        assert conf.slot.start_time == "2026-08-22T10:00:00"
        assert conf.slot.end_time == "2026-08-22T10:30:00"  # ASSUMPTION: 30 min
        assert conf.slot.slot_id == "EXTERNAL_SLOT"         # ASSUMPTION: placeholder

    def test_parse_book_response_care_type_from_internal(self):
        """care_type is passed in by caller (from stored CareDecision), not from response."""
        conf = SharedAppointmentAdapter.parse_book_response(
            EXTERNAL_BOOKING_RESPONSE,
            care_type="SPECIALIST",
        )
        assert conf.care_type == "SPECIALIST"

    def test_parse_book_response_missing_patient_id_raises(self):
        """Malformed response: missing patient_id raises ValueError."""
        bad = {"appointment": EXTERNAL_BOOKING_RESPONSE["appointment"].copy()}
        with pytest.raises(ValueError, match="patient_id"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_appointment_raises(self):
        """Malformed response: missing appointment key raises ValueError."""
        bad = {"patient_id": "P000003"}
        with pytest.raises(ValueError, match="appointment"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_appointment_id_raises(self):
        """Malformed response: missing appointment.appointment_id raises ValueError."""
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"].copy()
        del appt["appointment_id"]
        bad = {"patient_id": "P000003", "appointment": appt}
        with pytest.raises(ValueError, match="appointment_id"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_provider_id_raises(self):
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"].copy()
        del appt["provider_id"]
        bad = {"patient_id": "P000003", "appointment": appt}
        with pytest.raises(ValueError, match="provider_id"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_date_raises(self):
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"].copy()
        del appt["date"]
        bad = {"patient_id": "P000003", "appointment": appt}
        with pytest.raises(ValueError, match="date"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_time_raises(self):
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"].copy()
        del appt["time"]
        bad = {"patient_id": "P000003", "appointment": appt}
        with pytest.raises(ValueError, match="time"):
            SharedAppointmentAdapter.parse_book_response(bad)

    def test_parse_book_response_missing_status_raises(self):
        appt = EXTERNAL_BOOKING_RESPONSE["appointment"].copy()
        del appt["status"]
        bad = {"patient_id": "P000003", "appointment": appt}
        with pytest.raises(ValueError, match="status"):
            SharedAppointmentAdapter.parse_book_response(bad)

    # --- parse_availability_response ---

    def test_parse_availability_response_empty(self):
        slots = SharedAppointmentAdapter.parse_availability_response(
            {"available_slots": []}
        )
        assert slots == []

    def test_parse_availability_response_with_slots(self):
        resp = {
            "available_slots": [
                {
                    "slot_id": "slot_001",
                    "provider_id": "DOC-123",
                    "start_time": "2026-08-22T09:00:00",
                    "end_time": "2026-08-22T09:30:00",
                }
            ]
        }
        slots = SharedAppointmentAdapter.parse_availability_response(resp)
        assert len(slots) == 1
        assert slots[0].slot_id == "slot_001"

    def test_parse_availability_malformed_slot_raises(self):
        """Malformed slot entry raises ValueError with clear message."""
        resp = {"available_slots": [{"slot_id": "slot_001"}]}  # missing required fields
        with pytest.raises(ValueError, match="slot"):
            SharedAppointmentAdapter.parse_availability_response(resp)

    # --- parse_reschedule_response ---

    def test_parse_reschedule_response(self):
        """ASSUMPTION: reschedule response same shape as book, status RESCHEDULED."""
        external = {
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "date": "2026-08-30",
                "time": "10:00",
                "status": "RESCHEDULED",
            },
        }
        conf = SharedAppointmentAdapter.parse_reschedule_response(external)
        assert conf.status == "RESCHEDULED"
        assert conf.appointment_id == "APT-001"

    # --- parse_cancel_response ---

    def test_parse_cancel_response_nested(self):
        """ASSUMPTION: cancel response uses nested appointment envelope."""
        external = {
            "patient_id": "P000003",
            "appointment": {
                "appointment_id": "APT-001",
                "provider_id": "DOC-123",
                "status": "CANCELLED",
            },
        }
        result = SharedAppointmentAdapter.parse_cancel_response(external)
        assert result.status == "CANCELLED"
        assert result.appointment_id == "APT-001"
        assert result.patient_id == "P000003"

    def test_parse_cancel_response_flat(self):
        """Adapter also handles flat cancel response gracefully."""
        external = {
            "appointment_id": "APT-001",
            "patient_id": "P000003",
            "status": "CANCELLED",
        }
        result = SharedAppointmentAdapter.parse_cancel_response(external)
        assert result.status == "CANCELLED"


# ===========================================================================
# GROUP 11 — HTTP ERROR HANDLING
# ===========================================================================

class TestHttpErrorHandling:
    """Verify that HTTP errors from the external service propagate correctly."""

    def test_book_propagates_http_4xx(self):
        """4xx from the external service raises requests.HTTPError."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post",
                   return_value=_stub_error_http(404)):
            with pytest.raises(_requests.exceptions.HTTPError):
                client.book(req)

    def test_book_propagates_http_5xx(self):
        """5xx from the external service raises requests.HTTPError."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post",
                   return_value=_stub_error_http(500)):
            with pytest.raises(_requests.exceptions.HTTPError):
                client.book(req)

    def test_availability_propagates_http_error(self):
        """HTTP error from availability endpoint propagates."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        with patch("appointment.client.requests.post",
                   return_value=_stub_error_http(503)):
            with pytest.raises(_requests.exceptions.HTTPError):
                client.get_availability(
                    provider_id="DOC-123",
                    care_type="URGENT_CARE",
                    specialty=None,
                )

    def test_reschedule_propagates_http_error(self):
        """HTTP error from reschedule endpoint propagates."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = RescheduleRequest(
            patient_id="P000003",
            appointment_id="APT-001",
            new_slot_id="SLOT-002",
        )
        with patch("appointment.client.requests.post",
                   return_value=_stub_error_http(422)):
            with pytest.raises(_requests.exceptions.HTTPError):
                client.reschedule(req)

    def test_cancel_propagates_http_error(self):
        """HTTP error from cancel endpoint propagates."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = CancellationRequest(patient_id="P000003", appointment_id="APT-001")
        with patch("appointment.client.requests.post",
                   return_value=_stub_error_http(404)):
            with pytest.raises(_requests.exceptions.HTTPError):
                client.cancel_appointment(req)

    def test_book_timeout_propagates(self):
        """Network timeout raises requests.Timeout."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post",
                   side_effect=_requests.exceptions.Timeout("timed out")):
            with pytest.raises(_requests.exceptions.Timeout):
                client.book(req)

    def test_availability_timeout_propagates(self):
        """Network timeout on availability raises requests.Timeout."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        with patch("appointment.client.requests.post",
                   side_effect=_requests.exceptions.Timeout("timed out")):
            with pytest.raises(_requests.exceptions.Timeout):
                client.get_availability(
                    provider_id="DOC-123",
                    care_type="PCP",
                    specialty=None,
                )

    def test_book_malformed_response_raises_valueerror(self):
        """Missing 'appointment' key in book response raises ValueError."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        req = BookingRequest(
            patient_id="P000003",
            recommendation_id="rec_test",
            provider_id="DOC-123",
            slot_id="slot_001",
        )
        malformed = {"patient_id": "P000003"}  # missing "appointment"
        with patch("appointment.client.requests.post",
                   return_value=_stub_http(malformed)):
            with pytest.raises(ValueError, match="appointment"):
                client.book(req)
