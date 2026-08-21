"""
Integration tests for the Step 7 Shared Appointment Agent layer.

Coverage
--------
All 4 care types:
  - PCP
  - URGENT_CARE
  - SPECIALIST + specialty
  - TELEHEALTH

All 4 workflows (via the new routes):
  - CHECK_AVAILABILITY  -> POST /appointments/availability  (existing route)
  - BOOK_APPOINTMENT    -> POST /appointments/book           (existing route)
  - RESCHEDULE_APPOINTMENT -> POST /appointments/reschedule (new)
  - CANCEL_APPOINTMENT  -> POST /appointments/cancel        (new)

Status retrieval:
  - GET /appointments/{appointment_id}                      (new)

AppointmentService unit tests:
  - check_availability delegates correctly to client
  - book_appointment builds AppointmentConfirmation from BookingConfirmation
  - reschedule_appointment delegates correctly to client
  - cancel_appointment delegates correctly to client
  - get_appointment_status delegates correctly to client

External payload guards:
  - recommendation_id never in reschedule payload
  - recommendation_id never in cancel payload
  - reschedule Workflow A payload: {appointment_id, patient_id, new_slot_id}
  - reschedule Workflow B payload: {appointment_id, patient_id, preferred_date, preferred_time}
  - cancel payload: {appointment_id, patient_id}

Regression guards:
  - existing /navigate still works
  - existing /appointments/availability still works
  - existing /appointments/book still works
  - recommendation_id still excluded from /appointments/book external payload

Mocking strategy
----------------
- location.provider_discovery.find_nearby_providers  -> deterministic list
- agents.navigation_agent.NvidiaClient               -> deterministic tool-call sequence
- engine.explainer.explain_decision                  -> kept for compatibility (no longer called)
- api.routes.appointment_client.*                    -> MagicMock (no live HTTP)
- appointment.client.requests.post / .get            -> captured for payload assertions
- RecommendationStore is NOT mocked (real trust boundary)

Run with:
    python -m pytest tests/test_appointment_agent.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.services.alternate_care.models.schemas import (
    AppointmentSlot,
    BookingConfirmation,
    BookingRequest,
    ProviderCandidate,
)
from app.services.alternate_care.appointment.schemas import (
    AppointmentConfirmation,
    AppointmentStatusResponse,
    AvailabilityWorkflowRequest,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from app.services.alternate_care.appointment.agent import AppointmentService
from app.services.alternate_care.appointment.client import AppointmentAgentClient
from app.services.alternate_care.api.recommendation_store import recommendation_store

# ---------------------------------------------------------------------------
# Navigation Agent / NvidiaClient mock helpers (same pattern as test_appointment_flow)
# ---------------------------------------------------------------------------
# Import the helpers directly from test_appointment_flow to avoid duplication.
# Both test files share the same sys.path setup and helpers are module-level.

import json as _json
from types import SimpleNamespace as _NS
from app.services.alternate_care.llm.nvidia_client import LLMResponse as _LLMResponse, ToolCall as _ToolCall


def _fake_tool_call_raw(id_: str, name: str, arguments: str) -> object:
    fn = _NS(name=name, arguments=arguments)
    return _NS(id=id_, function=fn, type="function")


def _fake_completion(content, tool_calls_raw, finish_reason="stop"):
    message = _NS(content=content, tool_calls=tool_calls_raw)
    choice = _NS(message=message, finish_reason=finish_reason)
    return _NS(choices=[choice], model="meta/llama-3.3-70b-instruct")


def _llm_tool_response(tc_id: str, name: str, args: dict) -> _LLMResponse:
    tc = _ToolCall(id=tc_id, name=name, arguments=_json.dumps(args))
    raw_tc = _fake_tool_call_raw(tc_id, name, _json.dumps(args))
    raw = _fake_completion(None, [raw_tc], "tool_calls")
    return _LLMResponse(
        content=None,
        model="meta/llama-3.3-70b-instruct",
        tool_calls=[tc],
        finish_reason="tool_calls",
        raw=raw,
    )


def _llm_final_response(text: str) -> _LLMResponse:
    raw = _fake_completion(text, None, "stop")
    return _LLMResponse(
        content=text,
        model="meta/llama-3.3-70b-instruct",
        tool_calls=None,
        finish_reason="stop",
        raw=raw,
    )


def _make_nav_client(patient_features: dict, location_input: dict) -> MagicMock:
    """Return a fresh stateful mock NvidiaClient for one agent invocation."""
    call_count = {"n": 0}
    classify_result_holder = {}

    def _chat_side_effect(**kwargs):
        turn = call_count["n"]
        call_count["n"] += 1
        messages = kwargs.get("messages", [])

        if turn == 0:
            return _llm_tool_response("tc-classify-1", "classify_care", patient_features)

        if turn == 1:
            tool_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "tool"]
            classify_result = _json.loads(tool_msgs[-1]["content"])
            classify_result_holder.update(classify_result)
            destination = classify_result.get("destination", "URGENT_CARE")
            specialty = classify_result.get("specialty")
            lat = location_input.get("latitude", 37.7749)
            lon = location_input.get("longitude", -122.4194)
            args = {"latitude": lat, "longitude": lon, "destination": destination}
            if specialty:
                args["specialty"] = specialty
            return _llm_tool_response("tc-discover-2", "discover_providers", args)

        if turn == 2:
            tool_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "tool"]
            discover_result = _json.loads(tool_msgs[-1]["content"])
            providers = discover_result.get("providers", [])
            destination = classify_result_holder.get("destination", "URGENT_CARE")
            if not providers or destination == "TELEHEALTH":
                return _llm_final_response("Based on your symptoms, seek care as directed.")
            lat = location_input.get("latitude", 37.7749)
            lon = location_input.get("longitude", -122.4194)
            has_pcp = patient_features.get("has_pcp_flag")
            args = {"patient_lat": lat, "patient_lon": lon, "providers": providers}
            if has_pcp is not None:
                args["has_pcp_flag"] = has_pcp
            return _llm_tool_response("tc-rank-3", "rank_providers", args)

        return _llm_final_response("Based on your symptoms, seek care as directed.")

    mock_client = MagicMock()
    mock_client.chat.side_effect = lambda *args, **kwargs: _chat_side_effect(**kwargs)
    return mock_client


def _nav_client_patch(patient_features: dict, location_input: dict):
    """Patch NvidiaClient so each construction returns a fresh stateful mock."""
    def _factory(*args, **kwargs):
        return _make_nav_client(patient_features, location_input)
    mock_class = MagicMock(side_effect=_factory)
    return patch("agents.navigation_agent.NvidiaClient", mock_class)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_LOCATION = {"latitude": 37.7749, "longitude": -122.4194, "radius_km": 15.0}

_URGENT_CARE_PATIENT = {
    "primary_symptom_category": "minor_infection",
    "symptom_trend": "worsening",
    "pain_level_self_reported": 6,
}
_SPECIALIST_PATIENT = {
    "primary_symptom_category": "back_pain",
    "pain_onset": "gradual",
    "symptom_trend": "worsening",
    "ed_visits_past_year": 4,
}
_TELEHEALTH_PATIENT = {
    "primary_symptom_category": "mild_general_symptom",
    "symptom_trend": "improving",
    "pain_level_self_reported": 2,
}

_PROVIDER_UC = ProviderCandidate(
    provider_id="test:uc:001",
    name="Test Urgent Care",
    destination_type="URGENT_CARE",
    specialty=None,
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)
_PROVIDER_SPEC = ProviderCandidate(
    provider_id="test:spec:001",
    name="Test Ortho Clinic",
    destination_type="SPECIALIST",
    specialty="ORTHOPEDICS",
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)
_PROVIDER_PCP = ProviderCandidate(
    provider_id="test:pcp:001",
    name="Test PCP",
    destination_type="PCP",
    specialty=None,
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)

_STUB_SLOT = AppointmentSlot(
    slot_id="slot_001",
    provider_id="test:uc:001",
    start_time="2026-08-25T09:00:00",
    end_time="2026-08-25T09:30:00",
)
_STUB_SLOT_2 = AppointmentSlot(
    slot_id="slot_002",
    provider_id="test:uc:001",
    start_time="2026-08-26T10:00:00",
    end_time="2026-08-26T10:30:00",
)
_STUB_BOOKING_CONF = BookingConfirmation(
    appointment_id="appt_001",
    status="confirmed",
    provider_id="test:uc:001",
    slot=_STUB_SLOT,
)
_STUB_APPT_CONF = AppointmentConfirmation(
    appointment_id="appt_001",
    patient_id="patient_001",
    status="BOOKED",
    provider_id="test:uc:001",
    slot=_STUB_SLOT,
)
_STUB_RESCHEDULE_CONF = AppointmentConfirmation(
    appointment_id="appt_001",
    patient_id="patient_001",
    status="RESCHEDULED",
    provider_id="test:uc:001",
    slot=_STUB_SLOT_2,
)
_STUB_CANCEL_STATUS = AppointmentStatusResponse(
    appointment_id="appt_001",
    patient_id="patient_001",
    status="CANCELLED",
    provider_id="test:uc:001",
)
_STUB_STATUS_RESPONSE = AppointmentStatusResponse(
    appointment_id="appt_001",
    patient_id="patient_001",
    status="BOOKED",
    provider_id="test:uc:001",
    slot=_STUB_SLOT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    """Wipe the in-memory recommendation store before/after every test."""
    with recommendation_store._lock:
        recommendation_store._items.clear()
    yield
    with recommendation_store._lock:
        recommendation_store._items.clear()


@pytest.fixture()
def uc_client():
    """TestClient with URGENT_CARE provider discovery mocked."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch("location.provider_discovery.find_nearby_providers",
              return_value=[_PROVIDER_UC]),
        _nav_client_patch(_URGENT_CARE_PATIENT, _loc),
        patch("engine.explainer.explain_decision",
              return_value="Test explanation."),
    ):
        from api.routes import app
        yield TestClient(app)


@pytest.fixture()
def spec_client():
    """TestClient with SPECIALIST/ORTHOPEDICS provider discovery mocked."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch("location.provider_discovery.find_nearby_providers",
              return_value=[_PROVIDER_SPEC]),
        _nav_client_patch(_SPECIALIST_PATIENT, _loc),
        patch("engine.explainer.explain_decision",
              return_value="Test explanation."),
    ):
        from api.routes import app
        yield TestClient(app)


@pytest.fixture()
def pcp_client():
    """TestClient with PCP provider discovery mocked."""
    _pcp_patient = {
        "primary_symptom_category": "chronic_disease_flareup",
        "symptom_trend": "same",
        "pain_level_self_reported": 5,
        "charlson_comorbidity_index": 2,
    }
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch("location.provider_discovery.find_nearby_providers",
              return_value=[_PROVIDER_PCP]),
        _nav_client_patch(_pcp_patient, _loc),
        patch("engine.explainer.explain_decision",
              return_value="Test explanation."),
    ):
        from api.routes import app
        yield TestClient(app)


@pytest.fixture()
def telehealth_client():
    """TestClient for TELEHEALTH — discovery returns empty list."""
    _telehealth_patient = {
        "primary_symptom_category": "mild_general_symptom",
        "symptom_trend": "improving",
        "pain_level_self_reported": 2,
    }
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch("location.provider_discovery.find_nearby_providers",
              return_value=[]),
        _nav_client_patch(_telehealth_patient, _loc),
        patch("engine.explainer.explain_decision",
              return_value="Test explanation."),
    ):
        from api.routes import app
        yield TestClient(app)


def _navigate(http_client: TestClient, patient: dict) -> dict:
    resp = http_client.post(
        "/navigate",
        json={"patient": patient, "location": _LOCATION},
    )
    assert resp.status_code == 200, f"/navigate failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# AppointmentService unit tests (no HTTP routes, direct service calls)
# ---------------------------------------------------------------------------

class TestAppointmentServiceUnit:
    """Tests for AppointmentService in isolation — mock only the client."""

    def _make_service(self):
        mock_client = MagicMock(spec=AppointmentAgentClient)
        service = AppointmentService(client=mock_client)
        return service, mock_client

    # CHECK_AVAILABILITY

    def test_check_availability_delegates_to_client(self):
        """check_availability calls client.get_availability with derived fields."""
        service, mock_client = self._make_service()
        mock_client.get_availability.return_value = [_STUB_SLOT]

        req = AvailabilityWorkflowRequest(
            recommendation_id="rec_test",
            provider_id="test:uc:001",
            care_type="URGENT_CARE",
            date_range="next_7_days",
        )
        resp = service.check_availability(req)

        mock_client.get_availability.assert_called_once_with(
            provider_id="test:uc:001",
            care_type="URGENT_CARE",
            specialty=None,
            date_range="next_7_days",
        )
        assert len(resp.available_slots) == 1
        assert resp.care_type == "URGENT_CARE"
        assert resp.provider_id == "test:uc:001"

    def test_check_availability_specialist_passes_specialty(self):
        """check_availability passes specialty=ORTHOPEDICS for SPECIALIST."""
        service, mock_client = self._make_service()
        mock_client.get_availability.return_value = []

        req = AvailabilityWorkflowRequest(
            recommendation_id="rec_test",
            provider_id="test:spec:001",
            care_type="SPECIALIST",
            specialty="ORTHOPEDICS",
        )
        service.check_availability(req)

        _, kwargs = mock_client.get_availability.call_args
        assert kwargs["care_type"] == "SPECIALIST"
        assert kwargs["specialty"] == "ORTHOPEDICS"

    def test_check_availability_pcp_no_specialty(self):
        """check_availability passes specialty=None for PCP."""
        service, mock_client = self._make_service()
        mock_client.get_availability.return_value = []

        req = AvailabilityWorkflowRequest(
            recommendation_id="rec_test",
            provider_id="test:pcp:001",
            care_type="PCP",
        )
        service.check_availability(req)

        _, kwargs = mock_client.get_availability.call_args
        assert kwargs["specialty"] is None

    def test_check_availability_telehealth_no_specialty(self):
        """check_availability passes specialty=None for TELEHEALTH."""
        service, mock_client = self._make_service()
        mock_client.get_availability.return_value = []

        req = AvailabilityWorkflowRequest(
            recommendation_id="rec_test",
            provider_id="test:telehealth:001",
            care_type="TELEHEALTH",
        )
        service.check_availability(req)

        _, kwargs = mock_client.get_availability.call_args
        assert kwargs["care_type"] == "TELEHEALTH"
        assert kwargs["specialty"] is None

    # BOOK_APPOINTMENT

    def test_book_appointment_returns_rich_confirmation(self):
        """book_appointment up-casts BookingConfirmation to AppointmentConfirmation."""
        service, mock_client = self._make_service()
        mock_client.book.return_value = _STUB_BOOKING_CONF

        req = BookingWorkflowRequest(
            patient_id="patient_001",
            recommendation_id="rec_test",
            provider_id="test:uc:001",
            slot_id="slot_001",
        )
        conf = service.book_appointment(
            req,
            care_type="URGENT_CARE",
            specialty=None,
            provider_name="Test Urgent Care",
        )

        assert isinstance(conf, AppointmentConfirmation)
        assert conf.appointment_id == "appt_001"
        assert conf.patient_id == "patient_001"
        assert conf.status == "BOOKED"
        assert conf.care_type == "URGENT_CARE"
        assert conf.specialty is None
        assert conf.provider_name == "Test Urgent Care"
        assert conf.slot.slot_id == "slot_001"

    def test_book_appointment_specialist_confirmation(self):
        """book_appointment propagates care_type=SPECIALIST and specialty."""
        service, mock_client = self._make_service()
        spec_conf = BookingConfirmation(
            appointment_id="appt_spec_001",
            status="confirmed",
            provider_id="test:spec:001",
            slot=_STUB_SLOT,
        )
        mock_client.book.return_value = spec_conf

        req = BookingWorkflowRequest(
            patient_id="patient_001",
            recommendation_id="rec_spec",
            provider_id="test:spec:001",
            slot_id="slot_001",
        )
        conf = service.book_appointment(
            req,
            care_type="SPECIALIST",
            specialty="ORTHOPEDICS",
        )

        assert conf.care_type == "SPECIALIST"
        assert conf.specialty == "ORTHOPEDICS"

    def test_book_appointment_recommendation_id_not_in_external_call(self):
        """book_appointment must NOT leak recommendation_id to client.book()."""
        service, mock_client = self._make_service()
        mock_client.book.return_value = _STUB_BOOKING_CONF

        req = BookingWorkflowRequest(
            patient_id="patient_001",
            recommendation_id="rec_internal_only",
            provider_id="test:uc:001",
            slot_id="slot_001",
        )
        service.book_appointment(req)

        # client.book() receives a BookingRequest; check its fields
        (booking_request,), _ = mock_client.book.call_args
        assert isinstance(booking_request, BookingRequest)
        # recommendation_id is present on the internal model but client.py
        # strips it from the wire payload — confirmed by test_external_booking_payload
        # in test_appointment_flow.py; here we just confirm it was passed as a
        # BookingRequest with the correct identity fields
        assert booking_request.patient_id == "patient_001"
        assert booking_request.provider_id == "test:uc:001"
        assert booking_request.slot_id == "slot_001"

    # RESCHEDULE_APPOINTMENT

    def test_reschedule_delegates_to_client(self):
        """reschedule_appointment calls client.reschedule with the request."""
        service, mock_client = self._make_service()
        mock_client.reschedule.return_value = _STUB_RESCHEDULE_CONF

        req = RescheduleRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
            new_slot_id="slot_002",
        )
        conf = service.reschedule_appointment(req)

        mock_client.reschedule.assert_called_once_with(req)
        assert conf.status == "RESCHEDULED"
        assert conf.slot.slot_id == "slot_002"

    # CANCEL_APPOINTMENT

    def test_cancel_delegates_to_client(self):
        """cancel_appointment calls client.cancel_appointment with the request."""
        service, mock_client = self._make_service()
        mock_client.cancel_appointment.return_value = _STUB_CANCEL_STATUS

        req = CancellationRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
        )
        result = service.cancel_appointment(req)

        mock_client.cancel_appointment.assert_called_once_with(req)
        assert result.status == "CANCELLED"

    # GET STATUS

    def test_get_status_delegates_to_client(self):
        """get_appointment_status calls client.get_appointment."""
        service, mock_client = self._make_service()
        mock_client.get_appointment.return_value = _STUB_STATUS_RESPONSE

        result = service.get_appointment_status("appt_001", patient_id="patient_001")

        mock_client.get_appointment.assert_called_once_with(
            appointment_id="appt_001",
            patient_id="patient_001",
        )
        assert result.appointment_id == "appt_001"
        assert result.status == "BOOKED"


# ---------------------------------------------------------------------------
# Route-level integration tests — all 4 care types via /navigate + new routes
# ---------------------------------------------------------------------------

class TestRescheduleRoute:
    """POST /appointments/reschedule — both workflows, all care types."""

    def test_reschedule_workflow_a_urgent_care(self, uc_client):
        """Workflow A (new_slot_id) succeeds for URGENT_CARE."""
        mock_reschedule = MagicMock(return_value=_STUB_RESCHEDULE_CONF)

        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = uc_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                    "new_slot_id": "slot_002",
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "RESCHEDULED"
        mock_reschedule.assert_called_once()

    def test_reschedule_workflow_b_preferred_date(self, uc_client):
        """Workflow B (preferred_date) succeeds for URGENT_CARE."""
        mock_reschedule = MagicMock(return_value=_STUB_RESCHEDULE_CONF)

        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = uc_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                    "preferred_date": "2026-08-26",
                    "preferred_time": "morning",
                },
            )

        assert resp.status_code == 200, resp.text
        args, _ = mock_reschedule.call_args
        rr: RescheduleRequest = args[0]
        assert rr.preferred_date == "2026-08-26"
        assert rr.preferred_time == "morning"
        assert rr.new_slot_id is None

    def test_reschedule_workflow_b_preferred_time_only(self, uc_client):
        """Workflow B with only preferred_time is accepted."""
        mock_reschedule = MagicMock(return_value=_STUB_RESCHEDULE_CONF)

        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = uc_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                    "preferred_time": "afternoon",
                },
            )

        assert resp.status_code == 200, resp.text

    def test_reschedule_specialist_workflow_a(self, spec_client):
        """Workflow A for SPECIALIST appointment reschedule."""
        stub = AppointmentConfirmation(
            appointment_id="appt_spec_001",
            patient_id="patient_001",
            status="RESCHEDULED",
            provider_id="test:spec:001",
            slot=_STUB_SLOT_2,
        )
        mock_reschedule = MagicMock(return_value=stub)

        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = spec_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_spec_001",
                    "new_slot_id": "slot_002",
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "RESCHEDULED"

    def test_reschedule_missing_appointment_id_rejected(self, uc_client):
        """Reschedule without appointment_id must fail schema validation (422)."""
        resp = uc_client.post(
            "/appointments/reschedule",
            json={
                "patient_id": "patient_001",
                # appointment_id absent
                "new_slot_id": "slot_002",
            },
        )
        assert resp.status_code == 422

    def test_reschedule_missing_slot_and_preference_rejected(self, uc_client):
        """Reschedule without new_slot_id or preferred date/time must fail (422)."""
        resp = uc_client.post(
            "/appointments/reschedule",
            json={
                "patient_id": "patient_001",
                "appointment_id": "appt_001",
                # neither new_slot_id nor preferred_date/preferred_time
            },
        )
        assert resp.status_code == 422

    def test_reschedule_recommendation_id_not_required(self, uc_client):
        """recommendation_id is optional for reschedule (may be post-TTL)."""
        mock_reschedule = MagicMock(return_value=_STUB_RESCHEDULE_CONF)

        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = uc_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                    "new_slot_id": "slot_002",
                    # recommendation_id intentionally absent
                },
            )

        assert resp.status_code == 200, resp.text


class TestCancelRoute:
    """POST /appointments/cancel — all care types."""

    def test_cancel_urgent_care_succeeds(self, uc_client):
        """Cancel succeeds for URGENT_CARE appointment."""
        mock_cancel = MagicMock(return_value=_STUB_CANCEL_STATUS)

        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            resp = uc_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "CANCELLED"
        mock_cancel.assert_called_once()

    def test_cancel_specialist_succeeds(self, spec_client):
        """Cancel succeeds for SPECIALIST appointment."""
        stub = AppointmentStatusResponse(
            appointment_id="appt_spec_001",
            patient_id="patient_001",
            status="CANCELLED",
            provider_id="test:spec:001",
        )
        mock_cancel = MagicMock(return_value=stub)

        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            resp = spec_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_spec_001",
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "CANCELLED"

    def test_cancel_telehealth_succeeds(self, telehealth_client):
        """Cancel succeeds for TELEHEALTH appointment."""
        stub = AppointmentStatusResponse(
            appointment_id="appt_tele_001",
            patient_id="patient_001",
            status="CANCELLED",
            provider_id="test:telehealth:001",
        )
        mock_cancel = MagicMock(return_value=stub)

        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            resp = telehealth_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_tele_001",
                },
            )

        assert resp.status_code == 200, resp.text

    def test_cancel_missing_appointment_id_rejected(self, uc_client):
        """Cancel without appointment_id must fail schema validation (422)."""
        resp = uc_client.post(
            "/appointments/cancel",
            json={"patient_id": "patient_001"},
        )
        assert resp.status_code == 422

    def test_cancel_missing_patient_id_rejected(self, uc_client):
        """Cancel without patient_id must fail schema validation (422)."""
        resp = uc_client.post(
            "/appointments/cancel",
            json={"appointment_id": "appt_001"},
        )
        assert resp.status_code == 422

    def test_cancel_passes_both_ids_to_service(self, uc_client):
        """Cancel route must forward both patient_id and appointment_id."""
        mock_cancel = MagicMock(return_value=_STUB_CANCEL_STATUS)

        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            uc_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_unique_99",
                    "appointment_id": "appt_unique_99",
                },
            )

        args, _ = mock_cancel.call_args
        cr: CancellationRequest = args[0]
        assert cr.patient_id == "patient_unique_99"
        assert cr.appointment_id == "appt_unique_99"


class TestStatusRoute:
    """GET /appointments/{appointment_id}."""

    def test_get_status_urgent_care(self, uc_client):
        """Status retrieval returns BOOKED for URGENT_CARE appointment."""
        mock_status = MagicMock(
            return_value=_STUB_STATUS_RESPONSE
        )

        with patch("api.routes.appointment_service.get_appointment_status",
                   mock_status):
            resp = uc_client.get("/appointments/appt_001?patient_id=patient_001")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["appointment_id"] == "appt_001"
        assert body["status"] == "BOOKED"

    def test_get_status_passes_patient_id_query_param(self, uc_client):
        """GET /appointments/{id} forwards patient_id query param to service."""
        mock_status = MagicMock(return_value=_STUB_STATUS_RESPONSE)

        with patch("api.routes.appointment_service.get_appointment_status",
                   mock_status):
            uc_client.get("/appointments/appt_abc?patient_id=patient_xyz")

        mock_status.assert_called_once_with(
            appointment_id="appt_abc",
            patient_id="patient_xyz",
        )

    def test_get_status_without_patient_id(self, uc_client):
        """GET /appointments/{id} without patient_id still succeeds."""
        mock_status = MagicMock(return_value=_STUB_STATUS_RESPONSE)

        with patch("api.routes.appointment_service.get_appointment_status",
                   mock_status):
            resp = uc_client.get("/appointments/appt_001")

        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# External payload guard tests — client wire format
# ---------------------------------------------------------------------------

class TestClientWirePayloads:
    """Verify exact outbound HTTP payloads from AppointmentAgentClient."""

    def _make_stub_response(self, body: dict):
        stub = MagicMock()
        stub.raise_for_status = MagicMock()
        stub.json.return_value = body
        return stub

    def test_reschedule_workflow_a_payload(self):
        """Workflow A: adapter wraps payload in {actor, patient_id, request:{intent,
        appointment_id, new_slot_id}}.  recommendation_id must not appear."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        # Stub now uses the external nested response envelope.
        stub_resp = self._make_stub_response({
            "patient_id": "patient_001",
            "appointment": {
                "appointment_id": "appt_001",
                "provider_id": "prov_001",
                "date": "2026-08-26",
                "time": "10:00",
                "status": "RESCHEDULED",
            },
        })

        captured = []

        def capture(url, json=None, timeout=None, **kw):
            captured.append(json)
            return stub_resp

        req = RescheduleRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
            new_slot_id="slot_002",
        )

        with patch("appointment.client.requests.post", side_effect=capture):
            client.reschedule(req)

        assert len(captured) == 1
        payload = captured[0]
        # Adapter envelope: top-level fields
        assert payload["actor"] == "PATIENT"
        assert payload["patient_id"] == "patient_001"
        # Nested request sub-object
        inner = payload["request"]
        assert inner["intent"] == "RESCHEDULE_APPOINTMENT"
        assert inner["appointment_id"] == "appt_001"
        assert inner["new_slot_id"] == "slot_002"
        assert "recommendation_id" not in payload, (
            f"recommendation_id must not appear in reschedule payload; got {payload}"
        )
        assert "recommendation_id" not in inner
        assert "preferred_date" not in inner
        assert "preferred_time" not in inner

    def test_reschedule_workflow_b_payload(self):
        """Workflow B: adapter wraps payload in {actor, patient_id, request:{intent,
        appointment_id, preferred_date, preferred_time}}."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        # Stub now uses the external nested response envelope.
        stub_resp = self._make_stub_response({
            "patient_id": "patient_001",
            "appointment": {
                "appointment_id": "appt_001",
                "provider_id": "prov_001",
                "date": "2026-08-27",
                "time": "14:00",
                "status": "RESCHEDULED",
            },
        })

        captured = []

        def capture(url, json=None, timeout=None, **kw):
            captured.append(json)
            return stub_resp

        req = RescheduleRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
            preferred_date="2026-08-27",
            preferred_time="afternoon",
        )

        with patch("appointment.client.requests.post", side_effect=capture):
            client.reschedule(req)

        payload = captured[0]
        inner = payload["request"]
        assert inner["preferred_date"] == "2026-08-27"
        assert inner["preferred_time"] == "afternoon"
        assert "new_slot_id" not in inner
        assert "recommendation_id" not in payload
        assert "recommendation_id" not in inner

    def test_cancel_payload_contains_patient_id(self):
        """cancel_appointment: adapter wraps payload in {actor, patient_id,
        request:{intent, appointment_id}}.  patient_id and appointment_id
        must both be forwarded; recommendation_id must not appear."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        stub_resp = self._make_stub_response({
            "appointment_id": "appt_001",
            "patient_id": "patient_001",
            "status": "CANCELLED",
        })

        captured = []

        def capture(url, json=None, timeout=None, **kw):
            captured.append(json)
            return stub_resp

        req = CancellationRequest(
            patient_id="patient_001",
            appointment_id="appt_001",
        )

        with patch("appointment.client.requests.post", side_effect=capture):
            client.cancel_appointment(req)

        payload = captured[0]
        # Adapter envelope
        assert payload["actor"] == "PATIENT"
        assert payload["patient_id"] == "patient_001"
        inner = payload["request"]
        assert inner["intent"] == "CANCEL_APPOINTMENT"
        assert inner["appointment_id"] == "appt_001"
        assert "recommendation_id" not in payload
        assert "recommendation_id" not in inner

    def test_get_appointment_uses_get_method(self):
        """get_appointment uses GET (not POST) to /appointments/{id}."""
        client = AppointmentAgentClient(base_url="http://test-svc")
        stub_resp = self._make_stub_response({
            "appointment_id": "appt_001",
            "patient_id": "patient_001",
            "status": "BOOKED",
        })

        get_calls = []

        def capture_get(url, params=None, timeout=None, **kw):
            get_calls.append({"url": url, "params": params})
            return stub_resp

        with patch("appointment.client.requests.get", side_effect=capture_get):
            client.get_appointment("appt_001", patient_id="patient_001")

        assert len(get_calls) == 1
        assert "appt_001" in get_calls[0]["url"]
        assert get_calls[0]["params"]["patient_id"] == "patient_001"


# ---------------------------------------------------------------------------
# Care-type focused route tests — availability and booking for each type
# ---------------------------------------------------------------------------

class TestPCPWorkflow:
    """PCP availability and booking via navigation flow."""

    # Patient data that reliably routes to PCP-001-FLAREUP.
    _PCP_PATIENT = {
        "primary_symptom_category": "chronic_disease_flareup",
        "symptom_trend": "same",
        "pain_level_self_reported": 5,
        "charlson_comorbidity_index": 2,
    }

    def test_pcp_availability_derives_care_type_from_decision(self, pcp_client):
        """Availability for PCP derives care_type=PCP and specialty=None from stored decision."""
        body = _navigate(pcp_client, self._PCP_PATIENT)

        assert body["decision"]["destination"] == "PCP", (
            f"Expected PCP destination, got {body['decision']['destination']}"
        )
        assert body["decision"]["specialty"] is None

        rec_id = body["recommendation_id"]
        if not body["top_providers"]:
            pytest.skip("No providers returned for PCP fixture")

        provider_id = body["top_providers"][0]["provider_id"]

        mock_avail = MagicMock(return_value=[_STUB_SLOT])
        with patch("api.routes.appointment_client.get_availability", mock_avail):
            resp = pcp_client.post(
                "/appointments/availability",
                json={
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "date_range": "next_7_days",
                },
            )

        assert resp.status_code == 200, resp.text
        _, kwargs = mock_avail.call_args
        assert kwargs["care_type"] == "PCP"
        assert kwargs["specialty"] is None

    def test_pcp_booking_succeeds(self, pcp_client):
        """Booking for PCP succeeds with recommendation binding.
        specialty must be None for PCP — Step 9A must not break this.
        After Step 9D the route uses appointment_service.book_appointment()."""
        body = _navigate(pcp_client, self._PCP_PATIENT)
        assert body["decision"]["destination"] == "PCP"

        rec_id = body["recommendation_id"]
        if not body["top_providers"]:
            pytest.skip("No providers returned for PCP fixture")

        provider_id = body["top_providers"][0]["provider_id"]
        stored_provider_name = body["top_providers"][0]["name"]  # from navigation response

        stub_conf = AppointmentConfirmation(
            appointment_id="appt_pcp_001",
            patient_id="patient_001",
            status="BOOKED",
            provider_id=provider_id,
            provider_name=stored_provider_name,
            care_type="PCP",
            specialty=None,
            slot=_STUB_SLOT,
        )
        mock_book_appt = MagicMock(return_value=stub_conf)
        with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
            resp = pcp_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "slot_id": "slot_001",
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["appointment_id"] == "appt_pcp_001"

        # Step 9A regression guard: PCP booking must forward specialty=None
        _, kwargs = mock_book_appt.call_args
        assert kwargs.get("specialty") is None, (
            f"PCP booking must forward specialty=None; got {kwargs.get('specialty')!r}"
        )
        # Step 9D: provider_name from stored ProviderCandidate must be forwarded
        assert kwargs.get("provider_name") == stored_provider_name, (
            f"PCP booking must forward provider_name={stored_provider_name!r} "
            f"from stored ProviderCandidate; got {kwargs.get('provider_name')!r}"
        )


class TestUrgentCareWorkflow:
    """URGENT_CARE: availability, booking, reschedule, cancel."""

    def test_urgent_care_availability(self, uc_client):
        """Availability for URGENT_CARE derives care_type=URGENT_CARE, specialty=None."""
        body = _navigate(uc_client, _URGENT_CARE_PATIENT)
        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        mock_avail = MagicMock(return_value=[_STUB_SLOT])
        with patch("api.routes.appointment_client.get_availability", mock_avail):
            resp = uc_client.post(
                "/appointments/availability",
                json={
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "date_range": "next_7_days",
                },
            )

        assert resp.status_code == 200
        _, kwargs = mock_avail.call_args
        assert kwargs["care_type"] == "URGENT_CARE"
        assert kwargs["specialty"] is None

    def test_urgent_care_booking(self, uc_client):
        """Booking for URGENT_CARE succeeds. After Step 9D the route uses
        appointment_service.book_appointment()."""
        body = _navigate(uc_client, _URGENT_CARE_PATIENT)
        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        stub_conf = AppointmentConfirmation(
            appointment_id="appt_001",
            patient_id="patient_001",
            status="BOOKED",
            provider_id=provider_id,
            provider_name="Test Urgent Care",
            care_type="URGENT_CARE",
            slot=_STUB_SLOT,
        )
        mock_book_appt = MagicMock(return_value=stub_conf)
        with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
            resp = uc_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "slot_id": "slot_001",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["appointment_id"] == "appt_001"

    def test_urgent_care_reschedule(self, uc_client):
        """Reschedule route is reachable for URGENT_CARE context."""
        mock_reschedule = MagicMock(return_value=_STUB_RESCHEDULE_CONF)
        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = uc_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                    "new_slot_id": "slot_002",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "RESCHEDULED"

    def test_urgent_care_cancel(self, uc_client):
        """Cancel route is reachable for URGENT_CARE context."""
        mock_cancel = MagicMock(return_value=_STUB_CANCEL_STATUS)
        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            resp = uc_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_001",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"


class TestSpecialistWorkflow:
    """SPECIALIST + ORTHOPEDICS: availability derives specialty from decision."""

    def test_specialist_availability_derives_specialty(self, spec_client):
        """Availability for SPECIALIST uses specialty=ORTHOPEDICS from stored decision."""
        body = _navigate(spec_client, _SPECIALIST_PATIENT)

        assert body["decision"]["destination"] == "SPECIALIST"
        assert body["decision"]["specialty"] == "ORTHOPEDICS"

        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        mock_avail = MagicMock(return_value=[_STUB_SLOT])
        with patch("api.routes.appointment_client.get_availability", mock_avail):
            resp = spec_client.post(
                "/appointments/availability",
                json={
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "date_range": "next_7_days",
                },
            )

        assert resp.status_code == 200
        _, kwargs = mock_avail.call_args
        assert kwargs["care_type"] == "SPECIALIST"
        assert kwargs["specialty"] == "ORTHOPEDICS"

    def test_specialist_booking(self, spec_client):
        """Booking for SPECIALIST succeeds with recommendation binding.
        After Step 9D the route uses appointment_service.book_appointment()."""
        body = _navigate(spec_client, _SPECIALIST_PATIENT)
        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        stub_conf = AppointmentConfirmation(
            appointment_id="appt_spec_001",
            patient_id="patient_001",
            status="BOOKED",
            provider_id=provider_id,
            provider_name="Test Ortho Clinic",
            care_type="SPECIALIST",
            specialty="ORTHOPEDICS",
            slot=_STUB_SLOT,
        )
        mock_book_appt = MagicMock(return_value=stub_conf)
        with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
            resp = spec_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "slot_id": "slot_001",
                },
            )

        assert resp.status_code == 200

    def test_specialist_booking_forwards_specialty_to_client(self, spec_client):
        """Step 9A + 9D: SPECIALIST booking must forward specialty and provider_name
        to appointment_service.book_appointment().

        After Step 9D the route calls appointment_service.book_appointment(),
        not appointment_client.book() directly, so assertions target the service.
        """
        body = _navigate(spec_client, _SPECIALIST_PATIENT)
        assert body["decision"]["destination"] == "SPECIALIST"
        assert body["decision"]["specialty"] == "ORTHOPEDICS"

        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]
        stored_provider_name = body["top_providers"][0]["name"]  # from navigation response

        stub_conf = AppointmentConfirmation(
            appointment_id="appt_spec_001",
            patient_id="patient_001",
            status="BOOKED",
            provider_id=provider_id,
            provider_name=stored_provider_name,
            care_type="SPECIALIST",
            specialty="ORTHOPEDICS",
            slot=_STUB_SLOT,
        )
        mock_book_appt = MagicMock(return_value=stub_conf)
        with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
            spec_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "slot_id": "slot_001",
                },
            )

        mock_book_appt.assert_called_once()
        _, kwargs = mock_book_appt.call_args
        # Step 9A: specialty derived from stored CareDecision must be forwarded
        assert kwargs.get("specialty") == "ORTHOPEDICS", (
            f"Expected specialty='ORTHOPEDICS' forwarded to service.book_appointment(); "
            f"got {kwargs.get('specialty')!r}"
        )
        # Step 9D: provider_name from stored ProviderCandidate must be forwarded
        assert kwargs.get("provider_name") == stored_provider_name, (
            f"Expected provider_name={stored_provider_name!r} forwarded to service; "
            f"got {kwargs.get('provider_name')!r}"
        )

    def test_specialist_book_external_payload_contains_specialty(self, spec_client):
        """Step 9A: SPECIALIST BOOK_APPOINTMENT wire payload must include specialty.

        Traces all the way to the external HTTP payload captured at
        requests.post — confirms specialty flows from stored CareDecision
        through routes.py → client.book() → adapter → external JSON.
        """
        body = _navigate(spec_client, _SPECIALIST_PATIENT)
        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        captured = []
        stub_resp = MagicMock()
        stub_resp.raise_for_status = MagicMock()
        stub_resp.json.return_value = {
            "patient_id": "patient_001",
            "appointment": {
                "appointment_id": "appt_spec_ext_001",
                "provider_id": provider_id,
                "date": "2026-08-25",
                "time": "10:00",
                "status": "BOOKED",
            },
        }

        def capture_post(url, json=None, timeout=None, **kw):
            captured.append(json)
            return stub_resp

        with patch("appointment.client.requests.post", side_effect=capture_post):
            resp = spec_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "slot_id": "slot_001",
                },
            )

        assert resp.status_code == 200, resp.text
        assert len(captured) == 1, "requests.post must be called exactly once"
        payload = captured[0]

        # Envelope check
        assert payload["actor"] == "PATIENT"
        assert payload["patient_id"] == "patient_001"
        assert payload["request"]["intent"] == "BOOK_APPOINTMENT"

        # Specialty must be present in the external payload
        assert payload["request"]["specialty"] == "ORTHOPEDICS", (
            f"Expected specialty='ORTHOPEDICS' in external payload; "
            f"got: {payload['request']}"
        )

        # Internal fields must never leak
        assert "recommendation_id" not in payload
        assert "recommendation_id" not in str(payload)

    def test_specialist_reschedule(self, spec_client):
        """Reschedule for SPECIALIST uses new_slot_id (Workflow A)."""
        stub = AppointmentConfirmation(
            appointment_id="appt_spec_001",
            patient_id="patient_001",
            status="RESCHEDULED",
            provider_id="test:spec:001",
            care_type="SPECIALIST",
            specialty="ORTHOPEDICS",
            slot=_STUB_SLOT_2,
        )
        mock_reschedule = MagicMock(return_value=stub)
        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = spec_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_spec_001",
                    "new_slot_id": "slot_002",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "RESCHEDULED"


class TestTelehealthWorkflow:
    """TELEHEALTH: no physical providers, still reachable for reschedule/cancel."""

    def test_telehealth_navigate_produces_decision(self, telehealth_client):
        """TELEHEALTH /navigate produces a decision with destination=TELEHEALTH."""
        body = _navigate(telehealth_client, _TELEHEALTH_PATIENT)
        assert body["decision"]["destination"] == "TELEHEALTH"
        assert body["decision"]["specialty"] is None
        # TELEHEALTH skips rank_node — top_providers may be empty
        assert isinstance(body["top_providers"], list)

    def test_telehealth_reschedule_workflow_a(self, telehealth_client):
        """TELEHEALTH appointment reschedule via Workflow A."""
        stub = AppointmentConfirmation(
            appointment_id="appt_tele_001",
            patient_id="patient_001",
            status="RESCHEDULED",
            provider_id="test:telehealth:001",
            care_type="TELEHEALTH",
            slot=_STUB_SLOT_2,
        )
        mock_reschedule = MagicMock(return_value=stub)
        with patch("api.routes.appointment_service.reschedule_appointment",
                   mock_reschedule):
            resp = telehealth_client.post(
                "/appointments/reschedule",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_tele_001",
                    "new_slot_id": "slot_002",
                },
            )

        assert resp.status_code == 200

    def test_telehealth_cancel(self, telehealth_client):
        """TELEHEALTH appointment cancel."""
        stub = AppointmentStatusResponse(
            appointment_id="appt_tele_001",
            patient_id="patient_001",
            status="CANCELLED",
        )
        mock_cancel = MagicMock(return_value=stub)
        with patch("api.routes.appointment_service.cancel_appointment", mock_cancel):
            resp = telehealth_client.post(
                "/appointments/cancel",
                json={
                    "patient_id": "patient_001",
                    "appointment_id": "appt_tele_001",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# Regression guards — existing 3 routes must be unaffected
# ---------------------------------------------------------------------------

class TestExistingRoutesUnchanged:
    """Verify the 3 routes from Steps 1-3 continue to work exactly as before."""

    def test_navigate_still_returns_recommendation_with_id(self, uc_client):
        body = _navigate(uc_client, _URGENT_CARE_PATIENT)
        assert body["recommendation_id"].startswith("rec_")
        assert "decision" in body
        assert "top_providers" in body

    def test_availability_still_derives_care_type_from_store(self, uc_client):
        body = _navigate(uc_client, _URGENT_CARE_PATIENT)
        rec_id = body["recommendation_id"]
        provider_id = body["top_providers"][0]["provider_id"]

        mock_avail = MagicMock(return_value=[_STUB_SLOT])
        with patch("api.routes.appointment_client.get_availability", mock_avail):
            resp = uc_client.post(
                "/appointments/availability",
                json={
                    "recommendation_id": rec_id,
                    "provider_id": provider_id,
                    "date_range": "next_7_days",
                },
            )

        assert resp.status_code == 200
        _, kwargs = mock_avail.call_args
        assert kwargs["care_type"] == body["decision"]["destination"]

    def test_book_still_validates_provider_against_recommendation(self, uc_client):
        body = _navigate(uc_client, _URGENT_CARE_PATIENT)
        rec_id = body["recommendation_id"]

        mock_book_appt = MagicMock()
        with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
            resp = uc_client.post(
                "/appointments/book",
                json={
                    "patient_id": "patient_001",
                    "recommendation_id": rec_id,
                    "provider_id": "provider:not:in:recommendation",
                    "slot_id": "slot_001",
                },
            )

        assert resp.status_code == 404
        mock_book_appt.assert_not_called()

    def test_book_external_payload_still_excludes_recommendation_id(self):
        """regression: recommendation_id must not appear in /appointments/book
        wire payload.  Stub now uses the external nested response envelope."""
        from appointment.client import AppointmentAgentClient as _C

        stub_resp = MagicMock()
        stub_resp.raise_for_status = MagicMock()
        # Nested envelope — the adapter now expects this shape.
        stub_resp.json.return_value = {
            "patient_id": "patient_001",
            "appointment": {
                "appointment_id": "appt_reg_001",
                "provider_id": "prov_001",
                "date": "2026-08-19",
                "time": "09:00",
                "status": "BOOKED",
            },
        }
        captured = []

        def capture(url, json=None, timeout=None, **kw):
            captured.append(json)
            return stub_resp

        booking_req = BookingRequest(
            patient_id="patient_001",
            recommendation_id="rec_must_not_leak",
            provider_id="prov_001",
            slot_id="slot_001",
        )
        with patch("appointment.client.requests.post", side_effect=capture):
            c = _C(base_url="http://test-svc")
            c.book(booking_req)

        payload = captured[0]
        # recommendation_id must not appear anywhere in the outbound payload.
        assert "recommendation_id" not in payload
        assert "recommendation_id" not in str(payload)
