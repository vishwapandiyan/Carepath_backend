"""
Tests for the recommendation-bound appointment workflow.

Scope:
    POST /navigate
        → RecommendationStore (real, not mocked)
        → POST /appointments/availability
        → POST /appointments/book
        → AppointmentAgentClient (mocked — no real HTTP)

External boundaries mocked:
    - location.provider_discovery.find_nearby_providers
        (avoids live Overpass/OSM requests)
    - agents.navigation_agent.NvidiaClient
        (avoids live NVIDIA API calls; drives deterministic tool-call sequences)
    - engine.explainer.explain_decision
        (kept for backward compatibility; no longer called by the new path —
         the Navigation Agent uses NVIDIA Llama for prose, not Google Gemini)
    - api.routes.appointment_client.get_availability
    - api.routes.appointment_service.book_appointment
        (avoids live external Appointment Agent HTTP)
    - requests.post inside AppointmentAgentClient
        (used in Test 8 to capture the outbound wire payload)

NOT mocked:
    - RecommendationStore  (exercises the real trust boundary)
    - CareClassifier       (exercises the real rule engine via classify_care tool)
    - find_nearby_providers (called by the discover_providers tool; mocked above)
    - rank_providers        (called by the rank_providers tool; deterministic)

Run with:
    python -m pytest tests/test_appointment_flow.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure the project root is on sys.path (matches test_rule_engine.py convention).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.services.alternate_care.models.schemas import (
    AppointmentSlot,
    BookingConfirmation,
    BookingRequest,
    CareDecision,
    ProviderCandidate,
    Recommendation,
)
from app.services.alternate_care.api.recommendation_store import recommendation_store


# ---------------------------------------------------------------------------
# Navigation Agent / NvidiaClient mock helpers
# ---------------------------------------------------------------------------
# The new /navigate path drives an LLM tool-calling loop via NvidiaClient.
# We mock NvidiaClient so no real NVIDIA API calls are made, while still
# exercising the real tool implementations (CareClassifier, find_nearby_providers,
# rank_providers) through the agent's execute_tool() dispatcher.
#
# Protocol: the mock drives a 3-turn sequence per /navigate call —
#   Turn 1: LLM requests classify_care  (real tool runs → real CareDecision)
#   Turn 2: LLM requests discover_providers (real tool runs → mocked discovery)
#   Turn 3: LLM requests rank_providers (real tool runs → real Haversine)
#   Turn 4: LLM emits final prose response (no tool call)
#
# The mock uses a stateful callable so each successive .chat() call in the
# same agent invocation gets the next response in the sequence.
# A fresh stateful callable is created per /navigate call.

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
    """Build a fake LLMResponse requesting one tool call."""
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
    """Build a fake LLMResponse that terminates the loop."""
    raw = _fake_completion(text, None, "stop")
    return _LLMResponse(
        content=text,
        model="meta/llama-3.3-70b-instruct",
        tool_calls=None,
        finish_reason="stop",
        raw=raw,
    )


def _make_nav_client(patient_features: dict, location_input: dict) -> MagicMock:
    """Return a mock NvidiaClient that drives the standard 4-turn tool sequence.

    A NEW stateful mock is returned each time this is called — i.e., each
    time NvidiaClient() is constructed inside run_navigation_agent().  This
    means every /navigate call gets a fresh sequence regardless of how many
    times the fixture session calls _navigate().
    """
    call_count = {"n": 0}
    classify_result_holder = {}
    discover_result_holder = {}

    def _chat_side_effect(**kwargs):
        turn = call_count["n"]
        call_count["n"] += 1
        messages = kwargs.get("messages", [])

        if turn == 0:
            # Turn 1: classify care
            return _llm_tool_response(
                "tc-classify-1",
                "classify_care",
                patient_features,
            )

        if turn == 1:
            # Turn 2: discover providers.
            # Extract classify_care result from the most recent tool message.
            tool_msgs = [
                m for m in messages
                if isinstance(m, dict) and m.get("role") == "tool"
            ]
            classify_result = _json.loads(tool_msgs[-1]["content"])
            classify_result_holder.update(classify_result)
            destination = classify_result.get("destination", "URGENT_CARE")
            specialty = classify_result.get("specialty")

            lat = location_input.get("latitude", 37.7749)
            lon = location_input.get("longitude", -122.4194)

            args = {
                "latitude": lat,
                "longitude": lon,
                "destination": destination,
            }
            if specialty:
                args["specialty"] = specialty

            return _llm_tool_response("tc-discover-2", "discover_providers", args)

        if turn == 2:
            # Turn 3: rank providers — but only when there are providers to rank.
            # Extract discover result from the most recent tool message.
            tool_msgs = [
                m for m in messages
                if isinstance(m, dict) and m.get("role") == "tool"
            ]
            discover_result = _json.loads(tool_msgs[-1]["content"])
            discover_result_holder.update(discover_result)
            providers = discover_result.get("providers", [])
            destination = classify_result_holder.get("destination", "URGENT_CARE")

            if not providers or destination == "TELEHEALTH":
                # No providers to rank — go straight to final answer.
                return _llm_final_response(
                    "Based on your symptoms, I recommend seeking care as directed."
                )

            lat = location_input.get("latitude", 37.7749)
            lon = location_input.get("longitude", -122.4194)
            has_pcp = patient_features.get("has_pcp_flag")
            args = {
                "patient_lat": lat,
                "patient_lon": lon,
                "providers": providers,
            }
            if has_pcp is not None:
                args["has_pcp_flag"] = has_pcp

            return _llm_tool_response("tc-rank-3", "rank_providers", args)

        # Turn 3 (when no ranking) or Turn 4 (after ranking): final answer.
        return _llm_final_response(
            "Based on your symptoms, I recommend seeking care as directed."
        )

    mock_client = MagicMock()
    mock_client.chat.side_effect = lambda *args, **kwargs: _chat_side_effect(**kwargs)
    return mock_client


def _nav_client_patch(patient_features: dict, location_input: dict):
    """Return a context manager that patches NvidiaClient construction in the agent.

    Each call to NvidiaClient() inside run_navigation_agent() returns a fresh
    stateful mock with its own call_count — so multiple _navigate() calls in
    the same test (or same fixture session) each get an independent sequence.
    """
    def _factory(*args, **kwargs):
        return _make_nav_client(patient_features, location_input)

    mock_class = MagicMock(side_effect=_factory)
    return patch("agents.navigation_agent.NvidiaClient", mock_class)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_recommendation_store():
    """Wipe the in-memory store before every test to prevent state leakage."""
    with recommendation_store._lock:
        recommendation_store._items.clear()
    yield
    with recommendation_store._lock:
        recommendation_store._items.clear()


# Two deterministic provider stubs returned by the mocked discovery layer.
_PROVIDER_A = ProviderCandidate(
    provider_id="test:provider:001",
    name="Test Urgent Care A",
    destination_type="URGENT_CARE",
    specialty=None,
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)

_PROVIDER_B = ProviderCandidate(
    provider_id="test:provider:002",
    name="Test Urgent Care B",
    destination_type="URGENT_CARE",
    specialty=None,
    latitude=37.7800,
    longitude=-122.4100,
    source="osm",
)

# Deterministic provider stub for a SPECIALIST test case.
_PROVIDER_SPEC = ProviderCandidate(
    provider_id="test:provider:spec:001",
    name="Test Ortho Specialist",
    destination_type="SPECIALIST",
    specialty="ORTHOPEDICS",
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)

# Minimal patient payload that reliably routes to URGENT_CARE (UC-001-INFECTION).
_URGENT_CARE_PATIENT = {
    "primary_symptom_category": "minor_infection",
    "symptom_trend": "worsening",
    "pain_level_self_reported": 6,
}

# Patient payload that routes to SPECIALIST / ORTHOPEDICS (SPEC-003-ORTHO).
_SPECIALIST_PATIENT = {
    "primary_symptom_category": "back_pain",
    "pain_onset": "gradual",
    "symptom_trend": "worsening",
    "ed_visits_past_year": 4,
}

_LOCATION = {"latitude": 37.7749, "longitude": -122.4194, "radius_km": 15.0}

# Stub availability slot returned by the mocked client.
_STUB_SLOT = AppointmentSlot(
    slot_id="slot_test_001",
    provider_id="test:provider:001",
    start_time="2026-08-19T09:00:00",
    end_time="2026-08-19T09:30:00",
)

# Stub booking confirmation returned by the mocked client.
_STUB_CONFIRMATION = BookingConfirmation(
    appointment_id="appt_test_001",
    status="confirmed",
    provider_id="test:provider:001",
    slot=_STUB_SLOT,
)


@pytest.fixture()
def client():
    """
    FastAPI TestClient with external boundaries patched:
      - provider discovery → deterministic list [_PROVIDER_A, _PROVIDER_B]
      - NvidiaClient       → deterministic tool-call sequence (no real NVIDIA API)
      - LLM explainer      → kept for compatibility (no longer called in new path)
    """
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[_PROVIDER_A, _PROVIDER_B],
        ),
        _nav_client_patch(_URGENT_CARE_PATIENT, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="Test explanation.",
        ),
    ):
        from api.routes import app
        yield TestClient(app)


@pytest.fixture()
def specialist_client():
    """TestClient that returns a SPECIALIST provider from discovery."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[_PROVIDER_SPEC],
        ),
        _nav_client_patch(_SPECIALIST_PATIENT, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="Test explanation.",
        ),
    ):
        from api.routes import app
        yield TestClient(app)


def _navigate(client: TestClient, patient: dict | None = None) -> dict:
    """Helper: POST /navigate and return the parsed JSON body."""
    resp = client.post(
        "/navigate",
        json={
            "patient": patient or _URGENT_CARE_PATIENT,
            "location": _LOCATION,
        },
    )
    assert resp.status_code == 200, f"/navigate failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1 — /navigate creates a valid, stored Recommendation
# ---------------------------------------------------------------------------

def test_navigate_returns_recommendation_with_id(client):
    """
    /navigate must return a Recommendation that:
      - has a non-empty recommendation_id
      - uses the server-generated format (rec_ prefix from token_urlsafe)
      - contains a decision
      - contains top_providers
    """
    body = _navigate(client)

    assert "recommendation_id" in body, "recommendation_id missing from response"
    rec_id = body["recommendation_id"]
    assert rec_id, "recommendation_id must not be empty"
    assert rec_id.startswith("rec_"), (
        f"Expected server-generated rec_ prefix, got: {rec_id!r}"
    )

    assert "decision" in body, "decision missing from response"
    decision = body["decision"]
    assert decision["destination"] in ("PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH")
    assert "rule_id" in decision

    assert "top_providers" in body, "top_providers missing from response"
    assert isinstance(body["top_providers"], list)


def test_navigate_stores_recommendation_in_store(client):
    """
    The recommendation_id returned by /navigate must resolve in
    RecommendationStore — proving it is stored server-side, not fabricated
    in the response without being persisted.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]

    stored = recommendation_store.get(rec_id)
    assert stored is not None, (
        f"recommendation_id {rec_id!r} not found in store after /navigate"
    )
    assert stored.recommendation_id == rec_id
    assert stored.decision.destination == body["decision"]["destination"]


def test_navigate_does_not_generate_id_in_route(client):
    """
    The recommendation_id in the store must match the one in the response
    exactly — it is generated by RecommendationStore.create(), not by
    route code.  Two separate /navigate calls must produce distinct IDs.
    """
    body1 = _navigate(client)
    body2 = _navigate(client)
    assert body1["recommendation_id"] != body2["recommendation_id"], (
        "Two /navigate calls must produce distinct recommendation IDs"
    )


# ---------------------------------------------------------------------------
# Test 2 — /appointments/availability uses the recommendation's provider
# ---------------------------------------------------------------------------

def test_availability_calls_client_with_stored_decision(client):
    """
    Availability must derive care_type and specialty from the stored
    CareDecision, not from anything the caller supplies.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]

    # Pick the first provider that actually belongs to the recommendation.
    assert body["top_providers"], "Need at least one provider to test availability"
    provider_id = body["top_providers"][0]["provider_id"]

    expected_care_type = body["decision"]["destination"]
    expected_specialty = body["decision"].get("specialty")  # may be None

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200, f"availability failed: {resp.text}"

    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args
    # Verify the values the route passed to the client.
    assert kwargs["care_type"] == expected_care_type, (
        f"care_type must come from stored decision ({expected_care_type!r}), "
        f"got {kwargs['care_type']!r}"
    )
    assert kwargs["specialty"] == expected_specialty, (
        f"specialty must come from stored decision ({expected_specialty!r}), "
        f"got {kwargs['specialty']!r}"
    )
    assert kwargs["provider_id"] == provider_id


def test_availability_specialist_specialty_derived_from_decision(specialist_client):
    """
    When the stored decision is SPECIALIST/ORTHOPEDICS, get_availability()
    must receive care_type='SPECIALIST' and specialty='ORTHOPEDICS'
    regardless of what the caller sends.
    """
    body = _navigate(specialist_client, patient=_SPECIALIST_PATIENT)
    rec_id = body["recommendation_id"]

    assert body["top_providers"], "Need at least one SPECIALIST provider"
    provider_id = body["top_providers"][0]["provider_id"]

    assert body["decision"]["destination"] == "SPECIALIST"
    assert body["decision"]["specialty"] == "ORTHOPEDICS"

    mock_get_avail = MagicMock(return_value=[])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = specialist_client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200, resp.text
    _, kwargs = mock_get_avail.call_args
    assert kwargs["care_type"] == "SPECIALIST"
    assert kwargs["specialty"] == "ORTHOPEDICS"


# ---------------------------------------------------------------------------
# Test 3 — provider from a different recommendation is rejected
# ---------------------------------------------------------------------------

def test_availability_rejects_provider_from_different_recommendation(client):
    """
    A provider_id that does not belong to the given recommendation_id
    must produce HTTP 404.  get_availability() must NOT be called.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]

    mock_get_avail = MagicMock()

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": "provider:from:another:recommendation",
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 404, (
        f"Expected 404 for unknown provider, got {resp.status_code}: {resp.text}"
    )
    mock_get_avail.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — nonexistent recommendation_id is rejected for availability
# ---------------------------------------------------------------------------

def test_availability_rejects_nonexistent_recommendation(client):
    """
    A nonexistent recommendation_id must produce HTTP 404.
    get_availability() must NOT be called.
    """
    mock_get_avail = MagicMock()

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": "rec_doesnotexist000000",
                "provider_id": "test:provider:001",
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 404, (
        f"Expected 404 for unknown recommendation, got {resp.status_code}: {resp.text}"
    )
    mock_get_avail.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — /appointments/book succeeds with valid recommendation binding
# ---------------------------------------------------------------------------

def test_book_succeeds_with_valid_recommendation_and_provider(client):
    """
    Booking with a valid recommendation_id and a provider that belongs to
    that recommendation must succeed.  appointment_service.book_appointment()
    must be called; the response must contain the expected appointment fields.

    After Step 9D the route calls appointment_service.book_appointment()
    (not appointment_client.book() directly) so provider_name is threaded
    through.
    """
    from appointment.schemas import AppointmentConfirmation as _AC

    body = _navigate(client)
    rec_id = body["recommendation_id"]
    assert body["top_providers"], "Need at least one provider"
    provider_id = body["top_providers"][0]["provider_id"]
    stored_provider_name = body["top_providers"][0]["name"]  # authoritative from store

    stub_appt_conf = _AC(
        appointment_id="appt_test_001",
        patient_id="test_patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=stored_provider_name,
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_appt_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "test_patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_test_001",
            },
        )

    assert resp.status_code == 200, f"book failed: {resp.text}"
    mock_book_appt.assert_called_once()

    # Verify the BookingWorkflowRequest passed to the service
    from appointment.schemas import BookingWorkflowRequest as _BWR
    (booking_req,), kwargs = mock_book_appt.call_args
    assert isinstance(booking_req, _BWR)
    assert booking_req.patient_id == "test_patient_001"
    assert booking_req.recommendation_id == rec_id
    assert booking_req.provider_id == provider_id
    assert booking_req.slot_id == "slot_test_001"

    # provider_name must come from the stored ProviderCandidate — Step 9D
    assert kwargs.get("provider_name") == stored_provider_name, (
        f"provider_name must be forwarded from the stored ProviderCandidate "
        f"({stored_provider_name!r}); got {kwargs.get('provider_name')!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — invalid provider cannot be booked
# ---------------------------------------------------------------------------

def test_book_rejects_provider_not_in_recommendation(client):
    """
    A provider_id not belonging to the recommendation must produce HTTP 404.
    appointment_service.book_appointment() must NOT be called.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]

    mock_book_appt = MagicMock()

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "test_patient_001",
                "recommendation_id": rec_id,
                "provider_id": "provider:not:in:recommendation",
                "slot_id": "slot_test_001",
            },
        )

    assert resp.status_code == 404, (
        f"Expected 404 for invalid provider, got {resp.status_code}: {resp.text}"
    )
    mock_book_appt.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7 — nonexistent recommendation_id cannot be booked
# ---------------------------------------------------------------------------

def test_book_rejects_nonexistent_recommendation(client):
    """
    A booking request with an unknown recommendation_id must produce HTTP 404.
    appointment_service.book_appointment() must NOT be called.
    """
    mock_book_appt = MagicMock()

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "test_patient_001",
                "recommendation_id": "rec_doesnotexist000000",
                "provider_id": "test:provider:001",
                "slot_id": "slot_test_001",
            },
        )

    assert resp.status_code == 404, (
        f"Expected 404 for unknown recommendation, got {resp.status_code}: {resp.text}"
    )
    mock_book_appt.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8 — external booking payload must not contain recommendation_id
# ---------------------------------------------------------------------------

def test_external_booking_payload_excludes_recommendation_id():
    """
    AppointmentAgentClient.book() must NOT include recommendation_id in the
    outbound HTTP payload.

    After Step 8, the adapter wraps the payload in the external envelope:
        {actor, patient_id, request:{intent, ...}, patient_context?}
    The stub response now uses the external nested format so parse_book_response
    can deserialise it.
    """
    from appointment.client import AppointmentAgentClient

    booking_request = BookingRequest(
        patient_id="patient_001",
        recommendation_id="rec_test123",
        provider_id="provider_001",
        slot_id="slot_001",
    )

    stub_response = MagicMock()
    stub_response.raise_for_status = MagicMock()
    # Nested response envelope — required after Step 8 adapter.
    stub_response.json.return_value = {
        "patient_id": "patient_001",
        "appointment": {
            "appointment_id": "appt_001",
            "provider_id": "provider_001",
            "date": "2026-08-19",
            "time": "09:00",
            "status": "BOOKED",
        },
    }

    captured_payloads: list = []

    def capture_post(url, json=None, timeout=None, **kwargs):
        captured_payloads.append(json)
        return stub_response

    with patch("appointment.client.requests.post", side_effect=capture_post):
        client = AppointmentAgentClient(base_url="http://test-appointment-agent")
        client.book(booking_request)

    assert len(captured_payloads) == 1, "requests.post must be called exactly once"
    payload = captured_payloads[0]

    # recommendation_id must NOT appear anywhere in the outbound payload.
    assert "recommendation_id" not in payload, (
        f"recommendation_id must not be sent to the external service; "
        f"got payload keys: {list(payload.keys())}"
    )
    assert "recommendation_id" not in str(payload), (
        "recommendation_id must not appear nested inside the payload"
    )


# ---------------------------------------------------------------------------
# Test 9 — availability must not trust caller-supplied care_type
# ---------------------------------------------------------------------------

def test_availability_ignores_caller_care_type(client):
    """
    Even if a caller somehow passes an extra care_type field, the value
    forwarded to get_availability() must be recommendation.decision.destination,
    not the caller-supplied value.

    AppointmentAvailabilityRequest has no care_type field, so FastAPI/Pydantic
    will silently ignore any extra field.  This test confirms the route
    derives the authoritative value from the store regardless.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]
    expected_care_type = body["decision"]["destination"]

    mock_get_avail = MagicMock(return_value=[])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        # Include a spurious care_type field that the caller might attempt to
        # inject.  Pydantic will drop it; the route must use the stored value.
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                "care_type": "TELEHEALTH",   # caller attempt to override
            },
        )

    assert resp.status_code == 200, resp.text
    _, kwargs = mock_get_avail.call_args
    assert kwargs["care_type"] == expected_care_type, (
        f"care_type must be {expected_care_type!r} from stored decision, "
        f"not the caller-supplied 'TELEHEALTH'; got {kwargs['care_type']!r}"
    )


# ---------------------------------------------------------------------------
# Test 10 — availability must not trust caller-supplied specialty
# ---------------------------------------------------------------------------

def test_availability_ignores_caller_specialty(specialist_client):
    """
    Even if a caller passes a specialty field in the request body, the value
    forwarded to get_availability() must be recommendation.decision.specialty,
    not the caller-supplied value.
    """
    body = _navigate(specialist_client, patient=_SPECIALIST_PATIENT)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]
    expected_specialty = body["decision"]["specialty"]  # "ORTHOPEDICS"

    mock_get_avail = MagicMock(return_value=[])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = specialist_client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                "specialty": "CARDIOLOGY",   # caller attempt to override
            },
        )

    assert resp.status_code == 200, resp.text
    _, kwargs = mock_get_avail.call_args
    assert kwargs["specialty"] == expected_specialty, (
        f"specialty must be {expected_specialty!r} from stored decision, "
        f"not caller-supplied 'CARDIOLOGY'; got {kwargs['specialty']!r}"
    )


# ---------------------------------------------------------------------------
# Step 9B — patient_id threading through availability
# ---------------------------------------------------------------------------
# Three focused tests per the Step 9B specification:
#
#   Test A — route forwards patient_id to appointment_client.get_availability()
#   Test B — patient_id reaches the external wire payload (real client/adapter)
#   Test C — backward compatibility: omitting patient_id still works
# ---------------------------------------------------------------------------

def test_9b_route_forwards_patient_id_to_client(client):
    """Test A — Step 9B regression.

    When the HTTP caller supplies patient_id in AppointmentAvailabilityRequest,
    the route must forward it to appointment_client.get_availability() as the
    patient_id keyword argument.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                "patient_id": "patient_001",
            },
        )

    assert resp.status_code == 200, f"availability failed: {resp.text}"
    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args
    assert kwargs.get("patient_id") == "patient_001", (
        f"Route must forward patient_id='patient_001' to get_availability(); "
        f"got patient_id={kwargs.get('patient_id')!r}"
    )


def test_9b_wire_payload_contains_patient_id():
    """Test B — Step 9B regression.

    Exercises the real AppointmentAgentClient / SharedAppointmentAdapter path
    (no mock on those layers — only requests.post is stubbed).

    When patient_id is supplied, the outbound JSON payload sent to the
    external Appointment Agent must contain:
        payload["patient_id"] == "patient_001"
    at the top level of the envelope.
    """
    from appointment.client import AppointmentAgentClient as _Client

    captured_payloads: list = []

    stub_response = MagicMock()
    stub_response.raise_for_status = MagicMock()
    stub_response.json.return_value = {"available_slots": []}

    def capture_post(url, json=None, timeout=None, **kwargs):
        captured_payloads.append(json)
        return stub_response

    with patch("appointment.client.requests.post", side_effect=capture_post):
        c = _Client(base_url="http://test-appointment-agent")
        c.get_availability(
            provider_id="test:provider:001",
            care_type="URGENT_CARE",
            specialty=None,
            date_range="next_7_days",
            patient_id="patient_001",
        )

    assert len(captured_payloads) == 1, "requests.post must be called exactly once"
    payload = captured_payloads[0]

    assert payload.get("patient_id") == "patient_001", (
        f"External availability payload must have patient_id='patient_001' "
        f"at the top level; got: {payload}"
    )
    # Confirm the envelope structure is intact
    assert payload.get("actor") == "PATIENT", (
        f"Envelope must contain actor='PATIENT'; got: {payload}"
    )
    assert "request" in payload, (
        f"Envelope must contain a 'request' sub-object; got: {payload}"
    )
    assert payload["request"].get("intent") == "CHECK_AVAILABILITY", (
        f"request.intent must be 'CHECK_AVAILABILITY'; got: {payload['request']}"
    )


def test_9b_backward_compat_omitting_patient_id(client):
    """Test C — Step 9B backward compatibility.

    Existing callers that omit patient_id entirely must continue to work.
    The route must still call get_availability() successfully, and the call
    must pass patient_id=None (preserving the client's existing '' fallback).
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                # patient_id intentionally omitted
            },
        )

    assert resp.status_code == 200, (
        f"Omitting patient_id must not break availability; got {resp.status_code}: {resp.text}"
    )
    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args
    assert kwargs.get("patient_id") is None, (
        f"Route must pass patient_id=None when caller omits it; "
        f"got patient_id={kwargs.get('patient_id')!r}"
    )


# ---------------------------------------------------------------------------
# Step 9C — Patient location persisted and threaded through availability
# ---------------------------------------------------------------------------
# Six focused tests per the Step 9C specification:
#
#   Test A — /navigate persists the patient's location in the store
#   Test B — recommendation_id can recover the exact location
#   Test C — availability receives persisted location as patient_context
#   Test D — external wire payload contains location in the adapter structure
#   Test E — backward compatibility: no location → patient_context=None
#   Test F — public /navigate response does NOT expose patient coordinates
# ---------------------------------------------------------------------------

# Known test location used across Step 9C tests.
_NYC_LOCATION = {"latitude": 40.7128, "longitude": -74.0060, "radius_km": 15.0}

# Fixture that navigates using the NYC location and returns (client, body, rec_id).
# Not a pytest fixture to keep the pattern consistent with the existing module style.

def _navigate_nyc(http_client) -> dict:
    """POST /navigate with the NYC test location and return the response body."""
    resp = http_client.post(
        "/navigate",
        json={
            "patient": _URGENT_CARE_PATIENT,
            "location": _NYC_LOCATION,
        },
    )
    assert resp.status_code == 200, f"/navigate (NYC) failed: {resp.text}"
    return resp.json()


def test_9c_navigate_persists_location_in_store(client):
    """Test A — Step 9C.

    After POST /navigate with a known PatientLocation, the store must
    retain the exact latitude and longitude under the returned
    recommendation_id.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]

    location = recommendation_store.get_patient_location(rec_id)

    assert location is not None, (
        f"Store must retain the patient location after /navigate; "
        f"got None for recommendation_id={rec_id!r}"
    )
    assert location.latitude == 40.7128, (
        f"Stored latitude must be 40.7128; got {location.latitude}"
    )
    assert location.longitude == -74.0060, (
        f"Stored longitude must be -74.0060; got {location.longitude}"
    )


def test_9c_store_recovers_location_from_recommendation_id():
    """Test B — Step 9C.

    Directly exercises the store: create a recommendation with a known
    PatientLocation, then verify get_patient_location() returns the exact
    coordinates.  Also confirms that get()/require() still return the public
    Recommendation, not the private _StoredRecommendation wrapper.
    """
    from models.schemas import PatientLocation, CareDecision, Recommendation

    loc = PatientLocation(latitude=40.7128, longitude=-74.0060, radius_km=15.0)
    decision = CareDecision(
        rule_id="TEST-001",
        priority=1,
        destination="URGENT_CARE",
        status="matched",
        explanation="test",
    )
    rec = Recommendation(
        recommendation_id="",
        decision=decision,
        top_providers=[],
    )

    rec_id = recommendation_store.create(rec, patient_location=loc)

    # Public interface returns a Recommendation, not _StoredRecommendation.
    stored_rec = recommendation_store.require(rec_id)
    assert isinstance(stored_rec, Recommendation), (
        "require() must return a Recommendation, not the private wrapper"
    )

    # Location is recoverable via get_patient_location().
    stored_loc = recommendation_store.get_patient_location(rec_id)
    assert stored_loc is not None, "get_patient_location() must return the stored location"
    assert stored_loc.latitude == 40.7128
    assert stored_loc.longitude == -74.0060


def test_9c_availability_receives_persisted_location_as_patient_context(client):
    """Test C — Step 9C (key regression test).

    After /navigate with a known PatientLocation, a subsequent
    /appointments/availability call must receive that location packaged
    as an AppointmentPatientContext with the correct coordinates.

    The caller does NOT provide location in the availability request —
    it is recovered internally from recommendation_id.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                "patient_id": "patient_001",
                # NO latitude/longitude in request — must come from store
            },
        )

    assert resp.status_code == 200, f"availability failed: {resp.text}"
    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args

    # patient_id still forwarded (Step 9B regression guard)
    assert kwargs.get("patient_id") == "patient_001"

    # patient_context must be populated from the stored location
    ctx = kwargs.get("patient_context")
    assert ctx is not None, (
        "get_availability() must receive a patient_context built from the "
        "persisted PatientLocation; got None"
    )
    assert ctx.latitude == 40.7128, (
        f"patient_context.latitude must be 40.7128; got {ctx.latitude}"
    )
    assert ctx.longitude == -74.0060, (
        f"patient_context.longitude must be -74.0060; got {ctx.longitude}"
    )


def test_9c_wire_payload_contains_location():
    """Test D — Step 9C.

    Exercises the real AppointmentAgentClient / SharedAppointmentAdapter path
    (only requests.post is stubbed).

    When patient_context with lat/lon is supplied, the outbound JSON payload
    must contain the location nested in the adapter's confirmed structure:
        payload["patient_context"]["location"]["latitude"]
        payload["patient_context"]["location"]["longitude"]
    """
    from appointment.client import AppointmentAgentClient as _Client
    from appointment.schemas import AppointmentPatientContext as _Ctx

    captured_payloads: list = []

    stub_response = MagicMock()
    stub_response.raise_for_status = MagicMock()
    stub_response.json.return_value = {"available_slots": []}

    def capture_post(url, json=None, timeout=None, **kwargs):
        captured_payloads.append(json)
        return stub_response

    patient_context = _Ctx(latitude=40.7128, longitude=-74.0060)

    with patch("appointment.client.requests.post", side_effect=capture_post):
        c = _Client(base_url="http://test-appointment-agent")
        c.get_availability(
            provider_id="test:provider:001",
            care_type="URGENT_CARE",
            specialty=None,
            date_range="next_7_days",
            patient_id="patient_001",
            patient_context=patient_context,
        )

    assert len(captured_payloads) == 1, "requests.post must be called exactly once"
    payload = captured_payloads[0]

    # Adapter envelope structure (CONFIRMED from spec / existing contract tests)
    assert "patient_context" in payload, (
        f"External payload must include patient_context; got keys: {list(payload.keys())}"
    )
    loc = payload["patient_context"].get("location")
    assert loc is not None, (
        f"patient_context must contain a 'location' sub-object; "
        f"got patient_context={payload['patient_context']}"
    )
    assert loc["latitude"] == 40.7128, (
        f"location.latitude must be 40.7128; got {loc['latitude']}"
    )
    assert loc["longitude"] == -74.0060, (
        f"location.longitude must be -74.0060; got {loc['longitude']}"
    )
    # Confirm radius_km is NOT sent (it's a navigation field, not appointment context)
    assert "radius_km" not in loc, (
        f"radius_km must not appear in the external location payload; got: {loc}"
    )


def test_9c_backward_compat_no_location(client):
    """Test E — Step 9C backward compatibility.

    A /navigate call followed by /appointments/availability must work
    correctly even when no patient location was associated with the
    recommendation (simulated by a store entry created without location).

    In this case patient_context must be None — the client's existing
    behavior is preserved and no error is raised.
    """
    # Use the standard _navigate helper (which uses _LOCATION, not _NYC_LOCATION)
    # but then directly create a recommendation WITHOUT location to test the
    # fallback path cleanly.
    from models.schemas import PatientLocation as _PL, CareDecision, Recommendation

    decision = CareDecision(
        rule_id="TEST-BC-001",
        priority=1,
        destination="URGENT_CARE",
        status="matched",
        explanation="backward compat test",
    )
    provider = _PROVIDER_A
    rec = Recommendation(
        recommendation_id="",
        decision=decision,
        top_providers=[provider],
    )
    # Create WITHOUT patient_location
    rec_id = recommendation_store.create(rec)

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider.provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200, (
        f"Availability without stored location must still succeed; "
        f"got {resp.status_code}: {resp.text}"
    )
    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args
    assert kwargs.get("patient_context") is None, (
        f"patient_context must be None when no location is stored; "
        f"got {kwargs.get('patient_context')!r}"
    )


def test_9c_navigate_response_does_not_expose_location(client):
    """Test F — Step 9C API contract guard (Option B verification).

    The public /navigate response must NOT expose patient GPS coordinates.
    PatientLocation must remain internal — stored in _StoredRecommendation
    but never serialised into the Recommendation response model.

    Checks both the HTTP response JSON and the stored Recommendation object
    to confirm location is absent from both.
    """
    body = _navigate_nyc(client)

    # 1. HTTP response JSON must not contain location fields.
    assert "latitude" not in body, (
        "Public /navigate response must not contain 'latitude'"
    )
    assert "longitude" not in body, (
        "Public /navigate response must not contain 'longitude'"
    )
    assert "patient_location" not in body, (
        "Public /navigate response must not contain 'patient_location'"
    )

    # 2. The public Recommendation retrieved from the store must also
    #    not carry location (the private _StoredRecommendation does, but
    #    require() returns only the Recommendation model).
    rec_id = body["recommendation_id"]
    stored_rec = recommendation_store.require(rec_id)

    assert not hasattr(stored_rec, "patient_location") or stored_rec.__class__.__name__ == "Recommendation", (
        "require() must return a Recommendation without a patient_location field"
    )
    # Pydantic model_fields / __fields__ check — location must not be in schema
    fields = (
        stored_rec.__class__.model_fields if hasattr(stored_rec.__class__, "model_fields")
        else stored_rec.__fields__
    )
    assert "patient_location" not in fields, (
        f"Recommendation schema must not have a patient_location field; "
        f"found in fields: {list(fields.keys())}"
    )
    assert "latitude" not in fields, (
        "Recommendation schema must not expose latitude directly"
    )

# ---------------------------------------------------------------------------
# Step 9D — provider_name propagation through the booking route
# ---------------------------------------------------------------------------
# Five focused tests:
#
#   Test A — URGENT_CARE booking: provider_name reaches AppointmentConfirmation
#   Test B — SPECIALIST booking: provider_name reaches AppointmentConfirmation
#   Test C — provider_name is NOT added to the external BOOK payload
#   Test D — provider_name comes from the stored recommendation, not the caller
#   Test E — backward compat: existing rejection behavior is unaffected
# ---------------------------------------------------------------------------

def test_9d_urgent_care_booking_populates_provider_name(client):
    """Test A — Step 9D.

    URGENT_CARE booking: provider_name from the stored ProviderCandidate
    must appear in the booking response via AppointmentConfirmation.provider_name.

    The route calls appointment_service.book_appointment(provider_name=provider.name).
    We verify the argument reaches the service call.
    """
    from appointment.schemas import AppointmentConfirmation as _AC, BookingWorkflowRequest as _BWR

    body = _navigate(client)
    rec_id = body["recommendation_id"]
    assert body["top_providers"], "Need at least one provider"
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]
    expected_provider_name = provider["name"]  # from Recommendation.top_providers

    stub_conf = _AC(
        appointment_id="appt_9d_uc_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=expected_provider_name,
        care_type="URGENT_CARE",
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_test_001",
            },
        )

    assert resp.status_code == 200, f"booking failed: {resp.text}"
    mock_book_appt.assert_called_once()

    # provider_name must be forwarded from the ProviderCandidate to the service
    _, kwargs = mock_book_appt.call_args
    assert kwargs.get("provider_name") == expected_provider_name, (
        f"Route must forward provider_name={expected_provider_name!r} "
        f"to appointment_service.book_appointment(); "
        f"got {kwargs.get('provider_name')!r}"
    )

    # Response must include provider_name
    body_resp = resp.json()
    assert body_resp.get("provider_name") == expected_provider_name, (
        f"Booking response must include provider_name={expected_provider_name!r}; "
        f"got {body_resp.get('provider_name')!r}"
    )


def test_9d_specialist_booking_populates_provider_name(specialist_client):
    """Test B — Step 9D.

    SPECIALIST booking: provider_name from the stored ProviderCandidate
    reaches AppointmentConfirmation.provider_name alongside specialty.
    """
    from appointment.schemas import AppointmentConfirmation as _AC

    body = _navigate(specialist_client, patient=_SPECIALIST_PATIENT)
    assert body["decision"]["destination"] == "SPECIALIST"
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]
    expected_provider_name = provider["name"]  # "Test Ortho Specialist"

    stub_conf = _AC(
        appointment_id="appt_9d_spec_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=expected_provider_name,
        care_type="SPECIALIST",
        specialty="ORTHOPEDICS",
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = specialist_client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_test_001",
            },
        )

    assert resp.status_code == 200, f"SPECIALIST booking failed: {resp.text}"
    _, kwargs = mock_book_appt.call_args

    # Both specialty (Step 9A) and provider_name (Step 9D) must be forwarded
    assert kwargs.get("specialty") == "ORTHOPEDICS", (
        f"SPECIALIST booking must forward specialty='ORTHOPEDICS'; "
        f"got {kwargs.get('specialty')!r}"
    )
    assert kwargs.get("provider_name") == expected_provider_name, (
        f"SPECIALIST booking must forward provider_name={expected_provider_name!r}; "
        f"got {kwargs.get('provider_name')!r}"
    )

    body_resp = resp.json()
    assert body_resp.get("provider_name") == expected_provider_name


def test_9d_provider_name_not_in_external_book_payload(specialist_client):
    """Test C — Step 9D wire contract guard.

    provider_name must NOT appear in the external BOOK_APPOINTMENT payload
    sent to the Appointment Agent. It is internal enrichment only.

    Exercises the real client/adapter path (only requests.post is stubbed).
    """
    body = _navigate(specialist_client, patient=_SPECIALIST_PATIENT)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    captured_payloads: list = []
    stub_response = MagicMock()
    stub_response.raise_for_status = MagicMock()
    stub_response.json.return_value = {
        "patient_id": "patient_001",
        "appointment": {
            "appointment_id": "appt_9d_wire_001",
            "provider_id": provider_id,
            "date": "2026-08-25",
            "time": "10:00",
            "status": "BOOKED",
        },
    }

    def capture_post(url, json=None, timeout=None, **kwargs):
        captured_payloads.append(json)
        return stub_response

    with patch("appointment.client.requests.post", side_effect=capture_post):
        resp = specialist_client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_001",
            },
        )

    assert resp.status_code == 200, resp.text
    assert len(captured_payloads) == 1, "requests.post must be called exactly once"
    payload = captured_payloads[0]

    # provider_name must NOT appear anywhere in the outbound payload
    assert "provider_name" not in payload, (
        f"provider_name must not be in the external BOOK request payload; "
        f"got keys: {list(payload.keys())}"
    )
    assert "provider_name" not in str(payload), (
        "provider_name must not appear nested inside the external payload"
    )
    # recommendation_id regression guard (from Steps 8/9A)
    assert "recommendation_id" not in str(payload)


def test_9d_provider_name_comes_from_recommendation_not_caller(client):
    """Test D — Step 9D trust boundary.

    The provider_name forwarded to appointment_service.book_appointment()
    must come from the stored ProviderCandidate in RecommendationStore,
    not from any caller-supplied value.

    Demonstrates that even if a caller sends extra fields, only the stored
    name is used. The caller cannot inject an arbitrary provider name.
    """
    from appointment.schemas import AppointmentConfirmation as _AC

    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]
    stored_name = provider["name"]  # authoritative name from ProviderCandidate

    stub_conf = _AC(
        appointment_id="appt_9d_trust_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=stored_name,
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        # BookingRequest has no provider_name field — Pydantic silently drops extras.
        # The route derives provider_name from the store, not from the request.
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_test_001",
                "provider_name": "INJECTED_NAME",  # extra field — must be ignored
            },
        )

    assert resp.status_code == 200
    _, kwargs = mock_book_appt.call_args
    assert kwargs.get("provider_name") == stored_name, (
        f"provider_name must come from the stored ProviderCandidate ({stored_name!r}), "
        f"not from the caller; got {kwargs.get('provider_name')!r}"
    )
    assert kwargs.get("provider_name") != "INJECTED_NAME", (
        "Caller must not be able to inject an arbitrary provider_name"
    )

# ---------------------------------------------------------------------------
# Step 9E — Availability response enrichment
# ---------------------------------------------------------------------------
# Eight focused tests per the Step 9E specification:
#
#   Test A — availability still succeeds for an existing valid recommendation
#   Test B — response contains care_type derived from stored recommendation
#   Test C — SPECIALIST response contains specialty from stored recommendation
#   Test D — provider_id in response matches the validated recommendation provider
#   Test E — patient location flows internally to the client (Step 9C regression)
#   Test F — public response does NOT expose patient latitude/longitude
#   Test G — slots are preserved in the structured response
#   Test H — backward compatibility: no patient location → same slots returned
# ---------------------------------------------------------------------------

def test_9e_availability_still_succeeds(client):
    """Test A — Step 9E.

    The availability endpoint must continue to return HTTP 200 after the
    response model change.  The response must be parseable as
    AvailabilityWorkflowResponse.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200, f"availability failed: {resp.text}"
    data = resp.json()
    assert "available_slots" in data, f"Response must contain 'available_slots'; got {list(data.keys())}"


def test_9e_response_contains_care_type_from_recommendation(client):
    """Test B — Step 9E.

    The HTTP response from /appointments/availability must include care_type
    derived from the stored CareDecision — NOT from caller-supplied values.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]
    expected_care_type = body["decision"]["destination"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("care_type") == expected_care_type, (
        f"Response care_type must be {expected_care_type!r} from stored CareDecision; "
        f"got {data.get('care_type')!r}"
    )


def test_9e_specialist_response_contains_specialty(specialist_client):
    """Test C — Step 9E.

    For SPECIALIST bookings, the availability response must include specialty
    derived from the stored CareDecision.
    """
    body = _navigate(specialist_client, patient=_SPECIALIST_PATIENT)
    rec_id = body["recommendation_id"]
    assert body["top_providers"], "Need at least one SPECIALIST provider"
    provider_id = body["top_providers"][0]["provider_id"]
    assert body["decision"]["destination"] == "SPECIALIST"
    assert body["decision"]["specialty"] == "ORTHOPEDICS"

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = specialist_client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("care_type") == "SPECIALIST", (
        f"care_type must be 'SPECIALIST'; got {data.get('care_type')!r}"
    )
    assert data.get("specialty") == "ORTHOPEDICS", (
        f"specialty must be 'ORTHOPEDICS' from stored CareDecision; "
        f"got {data.get('specialty')!r}"
    )


def test_9e_response_contains_provider_id(client):
    """Test D — Step 9E.

    The availability response must include provider_id echoed from the
    validated ProviderCandidate — not trusting a caller-supplied value.
    """
    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("provider_id") == provider_id, (
        f"Response provider_id must be {provider_id!r} from validated "
        f"ProviderCandidate; got {data.get('provider_id')!r}"
    )


def test_9e_patient_location_still_flows_to_client(client):
    """Test E — Step 9E / Step 9C regression guard.

    Patient location must still flow internally to appointment_client.get_availability()
    as an AppointmentPatientContext even after the response model change.
    The location must NOT appear in the public HTTP response.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
                "patient_id": "patient_001",
            },
        )

    assert resp.status_code == 200
    mock_get_avail.assert_called_once()
    _, kwargs = mock_get_avail.call_args

    # Step 9C regression: patient_context must still be populated from store
    ctx = kwargs.get("patient_context")
    assert ctx is not None, (
        "patient_context must still reach get_availability() after 9E response change"
    )
    assert ctx.latitude == 40.7128
    assert ctx.longitude == -74.0060


def test_9e_response_does_not_expose_patient_location(client):
    """Test F — Step 9E privacy guard.

    The public /appointments/availability HTTP response must NOT expose
    patient GPS coordinates regardless of what the store holds.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "latitude" not in data, "Response must not expose patient latitude"
    assert "longitude" not in data, "Response must not expose patient longitude"
    assert "patient_context" not in data, "Response must not expose patient_context"
    assert "patient_location" not in data, "Response must not expose patient_location"
    # Check that the AvailabilityWorkflowResponse model fields are correct
    assert set(data.keys()) <= {"available_slots", "provider_id", "care_type", "specialty"}, (
        f"Response must only contain known fields; got {set(data.keys())}"
    )


def test_9e_slots_preserved_in_structured_response(client):
    """Test G — Step 9E.

    The structured AvailabilityWorkflowResponse must preserve the complete
    list of AppointmentSlot objects returned by the external service.
    Callers that previously consumed available_slots must continue to work.
    """
    from appointment.schemas import AvailabilityWorkflowResponse as _AVR

    body = _navigate(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    # Two slots to verify list integrity
    slot_a = _STUB_SLOT
    slot_b = AppointmentSlot(
        slot_id="slot_test_002",
        provider_id=provider_id,
        start_time="2026-08-19T10:00:00",
        end_time="2026-08-19T10:30:00",
    )
    mock_get_avail = MagicMock(return_value=[slot_a, slot_b])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    slots = data.get("available_slots", [])
    assert len(slots) == 2, f"Both slots must be returned; got {len(slots)}"
    assert slots[0]["slot_id"] == "slot_test_001"
    assert slots[1]["slot_id"] == "slot_test_002"


def test_9e_backward_compat_no_location_still_returns_slots(client):
    """Test H — Step 9E backward compatibility.

    When no patient location is stored (older recommendation), the route must
    still return a valid AvailabilityWorkflowResponse with the correct slots
    and care context.
    """
    from models.schemas import CareDecision, Recommendation

    decision = CareDecision(
        rule_id="TEST-9E-BC",
        priority=1,
        destination="URGENT_CARE",
        status="matched",
        explanation="backward compat test",
    )
    provider = _PROVIDER_A
    rec = Recommendation(
        recommendation_id="",
        decision=decision,
        top_providers=[provider],
    )
    # Create WITHOUT patient_location
    rec_id = recommendation_store.create(rec)

    mock_get_avail = MagicMock(return_value=[_STUB_SLOT])

    with patch("api.routes.appointment_client.get_availability", mock_get_avail):
        resp = client.post(
            "/appointments/availability",
            json={
                "recommendation_id": rec_id,
                "provider_id": provider.provider_id,
                "date_range": "next_7_days",
            },
        )

    assert resp.status_code == 200, (
        f"Availability without stored location must still succeed: {resp.text}"
    )
    data = resp.json()
    assert len(data.get("available_slots", [])) == 1
    assert data.get("care_type") == "URGENT_CARE"
    assert data.get("specialty") is None
    assert data.get("provider_id") == provider.provider_id

# ---------------------------------------------------------------------------
# Step 9F — Booking preserves patient location context
# ---------------------------------------------------------------------------
# Six focused tests:
#
#   Test A — booking retrieves persisted location from recommendation
#   Test B — booking passes AppointmentPatientContext to the service
#   Test C — lat/lon reach the external BOOK payload via the adapter
#   Test D — booking without stored location remains backward compatible
#   Test E — patient location NOT exposed in booking HTTP response
#   Test F — reschedule/cancel routes are unchanged
# ---------------------------------------------------------------------------

def test_9f_booking_retrieves_persisted_location(client):
    """Test A — Step 9F.

    After /navigate with a known PatientLocation, the booking route must
    retrieve that location from the store and pass it to
    appointment_service.book_appointment() as patient_context.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]

    from appointment.schemas import AppointmentConfirmation as _AC
    stub_conf = _AC(
        appointment_id="appt_9f_a_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_001",
            },
        )

    assert resp.status_code == 200, f"booking failed: {resp.text}"
    mock_book_appt.assert_called_once()
    _, kwargs = mock_book_appt.call_args

    ctx = kwargs.get("patient_context")
    assert ctx is not None, (
        "booking route must pass patient_context built from persisted "
        "PatientLocation; got None"
    )
    assert ctx.latitude == 40.7128, f"patient_context.latitude must be 40.7128; got {ctx.latitude}"
    assert ctx.longitude == -74.0060, f"patient_context.longitude must be -74.0060; got {ctx.longitude}"


def test_9f_booking_passes_patient_context_to_service(client):
    """Test B — Step 9F (service-layer assertion).

    Verifies the AppointmentPatientContext with the correct coordinates
    reaches appointment_service.book_appointment() as a keyword argument.
    Also confirms that patient_id, provider_name, specialty are all still
    forwarded (Step 9B/9D regression guard).
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]
    stored_provider_name = provider["name"]
    expected_care_type = body["decision"]["destination"]

    from appointment.schemas import AppointmentConfirmation as _AC
    stub_conf = _AC(
        appointment_id="appt_9f_b_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=stored_provider_name,
        care_type=expected_care_type,
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_001",
            },
        )

    assert resp.status_code == 200
    _, kwargs = mock_book_appt.call_args

    # Step 9F: patient_context with correct coordinates
    ctx = kwargs.get("patient_context")
    assert ctx is not None
    assert ctx.latitude == 40.7128
    assert ctx.longitude == -74.0060

    # Step 9D regression: provider_name still forwarded
    assert kwargs.get("provider_name") == stored_provider_name

    # Step 9A regression: specialty still forwarded (None for URGENT_CARE)
    assert kwargs.get("specialty") == body["decision"].get("specialty")


def test_9f_booking_location_reaches_external_payload(client):
    """Test C — Step 9F wire contract.

    Exercises the real service → client → adapter chain (only requests.post
    is stubbed) to verify that the patient location stored at navigation
    time reaches the external BOOK_APPOINTMENT payload as:
        payload["patient_context"]["location"]["latitude"]
        payload["patient_context"]["location"]["longitude"]
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider_id = body["top_providers"][0]["provider_id"]

    captured: list = []
    stub_resp = MagicMock()
    stub_resp.raise_for_status = MagicMock()
    stub_resp.json.return_value = {
        "patient_id": "patient_001",
        "appointment": {
            "appointment_id": "appt_9f_wire_001",
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
        resp = client.post(
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

    assert "patient_context" in payload, (
        f"External BOOK payload must include patient_context; got keys: {list(payload.keys())}"
    )
    loc = payload["patient_context"].get("location")
    assert loc is not None, (
        f"patient_context must contain a 'location' sub-object; "
        f"got patient_context={payload['patient_context']}"
    )
    assert loc["latitude"] == 40.7128, f"location.latitude must be 40.7128; got {loc['latitude']}"
    assert loc["longitude"] == -74.0060, f"location.longitude must be -74.0060; got {loc['longitude']}"

    # recommendation_id must never appear in the external payload
    assert "recommendation_id" not in str(payload)


def test_9f_booking_without_location_remains_backward_compatible(client):
    """Test D — Step 9F backward compatibility.

    When the recommendation was created without a PatientLocation, the booking
    route must continue to work — patient_context must be None, not raise.
    """
    from models.schemas import CareDecision, Recommendation
    from appointment.schemas import AppointmentConfirmation as _AC

    decision = CareDecision(
        rule_id="TEST-9F-BC",
        priority=1,
        destination="URGENT_CARE",
        status="matched",
        explanation="9F backward compat",
    )
    provider = _PROVIDER_A
    rec = Recommendation(recommendation_id="", decision=decision, top_providers=[provider])
    rec_id = recommendation_store.create(rec)  # no patient_location

    stub_conf = _AC(
        appointment_id="appt_9f_bc_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider.provider_id,
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider.provider_id,
                "slot_id": "slot_001",
            },
        )

    assert resp.status_code == 200, f"booking without location must succeed: {resp.text}"
    mock_book_appt.assert_called_once()
    _, kwargs = mock_book_appt.call_args
    assert kwargs.get("patient_context") is None, (
        f"patient_context must be None when no location is stored; "
        f"got {kwargs.get('patient_context')!r}"
    )


def test_9f_booking_response_does_not_expose_patient_location(client):
    """Test E — Step 9F privacy guard.

    The HTTP booking response must NOT contain patient GPS coordinates.
    AppointmentConfirmation does not have location fields — this test
    confirms that no leakage occurs through the enrichment path.
    """
    body = _navigate_nyc(client)
    rec_id = body["recommendation_id"]
    provider = body["top_providers"][0]
    provider_id = provider["provider_id"]

    from appointment.schemas import AppointmentConfirmation as _AC
    stub_conf = _AC(
        appointment_id="appt_9f_priv_001",
        patient_id="patient_001",
        status="BOOKED",
        provider_id=provider_id,
        provider_name=provider["name"],
        slot=_STUB_SLOT,
    )
    mock_book_appt = MagicMock(return_value=stub_conf)

    with patch("api.routes.appointment_service.book_appointment", mock_book_appt):
        resp = client.post(
            "/appointments/book",
            json={
                "patient_id": "patient_001",
                "recommendation_id": rec_id,
                "provider_id": provider_id,
                "slot_id": "slot_001",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "latitude" not in data, "Booking response must not expose patient latitude"
    assert "longitude" not in data, "Booking response must not expose patient longitude"
    assert "patient_context" not in data, "Booking response must not expose patient_context"
    assert "patient_location" not in data, "Booking response must not expose patient_location"


def test_9f_reschedule_cancel_routes_unchanged(client):
    """Test F — Step 9F scope guard.

    Reschedule and cancel routes must remain completely unchanged by Step 9F.
    Neither route touches the recommendation store or patient location.
    """
    from appointment.schemas import AppointmentConfirmation as _AC, AppointmentStatusResponse as _ASR

    # Reschedule
    stub_reschedule = _AC(
        appointment_id="appt_resch_001",
        patient_id="patient_001",
        status="RESCHEDULED",
        provider_id="test:provider:001",
        slot=_STUB_SLOT,
    )
    with patch("api.routes.appointment_service.reschedule_appointment",
               MagicMock(return_value=stub_reschedule)):
        resp = client.post(
            "/appointments/reschedule",
            json={
                "patient_id": "patient_001",
                "appointment_id": "appt_001",
                "new_slot_id": "slot_002",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "RESCHEDULED"

    # Cancel
    stub_cancel = _ASR(
        appointment_id="appt_001",
        patient_id="patient_001",
        status="CANCELLED",
    )
    with patch("api.routes.appointment_service.cancel_appointment",
               MagicMock(return_value=stub_cancel)):
        resp = client.post(
            "/appointments/cancel",
            json={"patient_id": "patient_001", "appointment_id": "appt_001"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

# ---------------------------------------------------------------------------
# Step 10E — Dental → SPECIALIST/DENTISTRY navigation integration
# ---------------------------------------------------------------------------

_DENTAL_PATIENT = {
    "primary_symptom_category": "dental_pain",
}

_PROVIDER_DENTAL = ProviderCandidate(
    provider_id="osm:node:5001",
    name="City Dental Clinic",
    destination_type="DENTISTRY",
    specialty=None,
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)


@pytest.fixture()
def dental_client():
    """TestClient with a dental provider returned from discovery."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    _dental_patient = {
        "primary_symptom_category": "dental_pain",
        "pain_level_self_reported": 6,
    }
    with (
        patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[_PROVIDER_DENTAL],
        ),
        _nav_client_patch(_dental_patient, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="A dentist can help with this.",
        ),
    ):
        from api.routes import app
        yield TestClient(app)


def test_10e_dental_pain_routes_to_dentistry(dental_client):
    """Step 10E integration: dental_pain must produce destination=DENTISTRY with
    specialty=None (DENTISTRY is a first-class destination, not a specialty
    under SPECIALIST), and return the dental provider in top_providers."""
    body = _navigate(dental_client, patient=_DENTAL_PATIENT)

    assert body["decision"]["destination"] == "DENTISTRY", (
        f"dental_pain must route to DENTISTRY; got {body['decision']['destination']!r}"
    )
    assert body["decision"]["specialty"] is None, (
        f"DENTISTRY destination must have specialty=None; "
        f"got {body['decision']['specialty']!r}"
    )
    assert body["decision"]["rule_id"] == "SPEC-004-DENTAL", (
        f"dental_pain must match SPEC-004-DENTAL; got {body['decision']['rule_id']!r}"
    )
    assert len(body["top_providers"]) == 1
    assert body["top_providers"][0]["provider_id"] == "osm:node:5001"
    assert body["top_providers"][0]["name"] == "City Dental Clinic"

# ---------------------------------------------------------------------------
# Step 10F — Pulmonology → SPECIALIST/PULMONOLOGY navigation integration
# ---------------------------------------------------------------------------

_PULM_PATIENT = {
    "primary_symptom_category": "mild_breathing_difficulty",
    "copd_asthma_flag": 1,
    "chronic_condition_count": 3,
    "pain_duration": "days",
}

_PROVIDER_PULM = ProviderCandidate(
    provider_id="osm:node:6001",
    name="City Pulmonology Clinic",
    destination_type="SPECIALIST",
    specialty="PULMONOLOGY",
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)


@pytest.fixture()
def pulm_client():
    """TestClient with a pulmonology provider returned from discovery."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[_PROVIDER_PULM],
        ),
        _nav_client_patch(_PULM_PATIENT, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="A pulmonologist can help manage your breathing condition.",
        ),
    ):
        from api.routes import app
        yield TestClient(app)


def test_10f_breathing_copd_routes_to_specialist_pulmonology(pulm_client):
    """Step 10F integration: mild_breathing_difficulty + copd_asthma_flag=1
    + chronic_condition_count>=2 must produce SPECIALIST/PULMONOLOGY and
    return the pulmonology provider in top_providers."""
    body = _navigate(pulm_client, patient=_PULM_PATIENT)

    assert body["decision"]["destination"] == "SPECIALIST", (
        f"SPEC-002-PULM must route to SPECIALIST; "
        f"got {body['decision']['destination']!r}"
    )
    assert body["decision"]["specialty"] == "PULMONOLOGY", (
        f"SPEC-002-PULM must produce specialty=PULMONOLOGY; "
        f"got {body['decision']['specialty']!r}"
    )
    assert body["decision"]["rule_id"] == "SPEC-002-PULM", (
        f"mild_breathing_difficulty + copd + chronic conditions must match "
        f"SPEC-002-PULM; got {body['decision']['rule_id']!r}"
    )
    assert len(body["top_providers"]) == 1, (
        f"Expected 1 pulmonology provider; got {len(body['top_providers'])}"
    )
    assert body["top_providers"][0]["provider_id"] == "osm:node:6001", (
        f"Expected provider_id 'osm:node:6001'; "
        f"got {body['top_providers'][0]['provider_id']!r}"
    )
    assert body["top_providers"][0]["name"] == "City Pulmonology Clinic", (
        f"Expected provider name 'City Pulmonology Clinic'; "
        f"got {body['top_providers'][0]['name']!r}"
    )


# ---------------------------------------------------------------------------
# /navigate end-to-end flow — PCP and TELEHEALTH destination coverage
#
# These two tests close the remaining gaps in the required destination matrix:
#
#   PCP       — full pipeline: classify → geocoder no-op → discovery → rank
#   TELEHEALTH — full pipeline: classify → discovery SHORT-CIRCUITS (no OSM)
#
# All other required destinations are already covered above:
#   URGENT_CARE          → _URGENT_CARE_PATIENT / client fixture (Tests 1-9E)
#   SPECIALIST/ORTHOPEDICS → _SPECIALIST_PATIENT / specialist_client (many tests)
#   SPECIALIST/PULMONOLOGY → test_10f_breathing_copd_routes_to_specialist_pulmonology
#   DENTISTRY            → test_10e_dental_pain_routes_to_dentistry
# ---------------------------------------------------------------------------

_PCP_PATIENT = {
    "primary_symptom_category": "chronic_disease_flareup",
    "symptom_trend": "same",
    "pain_level_self_reported": 5,
    "charlson_comorbidity_index": 2,
}
"""Routes to PCP-001-FLAREUP: chronic flare-up, stable, doesn't meet the
SPEC-001-FLAREUP (CCI<7) or TELE-001-FLAREUP (pain>3) thresholds."""

_PCP_PROVIDER = ProviderCandidate(
    provider_id="osm:node:pcp:001",
    name="Family Health Clinic",
    destination_type="PCP",
    specialty=None,
    latitude=37.7749,
    longitude=-122.4194,
    source="osm",
)

_TELEHEALTH_PATIENT = {
    "primary_symptom_category": "mild_general_symptom",
    "symptom_trend": "improving",
    "pain_level_self_reported": 2,
}
"""Routes to TELE-003-GENERAL: mild, improving, low-pain — virtual follow-up."""


@pytest.fixture()
def pcp_client():
    """TestClient that returns a PCP provider from discovery."""
    _loc = {"latitude": 37.7749, "longitude": -122.4194}
    with (
        patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[_PCP_PROVIDER],
        ),
        _nav_client_patch(_PCP_PATIENT, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="Your primary care physician can manage this condition.",
        ),
    ):
        from api.routes import app
        yield TestClient(app)


def test_navigate_pcp_destination_full_pipeline(pcp_client):
    """PCP end-to-end flow through /navigate.

    Verifies:
    - destination is PCP, specialty is None
    - correct rule matched (PCP-001-FLAREUP)
    - location is passed to provider discovery (via mock)
    - provider returned and ranked in top_providers
    - Gemini explanation is present (mocked — not inventing provider data)
    - response is a valid Recommendation with recommendation_id
    - Gemini is NOT responsible for provider selection or distance
    """
    resp = pcp_client.post(
        "/navigate",
        json={"patient": _PCP_PATIENT, "location": _LOCATION},
    )
    assert resp.status_code == 200, f"/navigate PCP failed: {resp.text}"
    body = resp.json()

    # Destination and specialty
    decision = body["decision"]
    assert decision["destination"] == "PCP", (
        f"chronic_disease_flareup (stable, CCI=2) must route to PCP; "
        f"got {decision['destination']!r}"
    )
    assert decision["specialty"] is None, (
        f"PCP destination must have specialty=None; got {decision['specialty']!r}"
    )
    assert decision["rule_id"] == "PCP-001-FLAREUP", (
        f"Expected PCP-001-FLAREUP; got {decision['rule_id']!r}"
    )

    # Providers returned and ranked
    assert len(body["top_providers"]) == 1, (
        f"Expected 1 PCP provider; got {len(body['top_providers'])}"
    )
    provider = body["top_providers"][0]
    assert provider["provider_id"] == "osm:node:pcp:001"
    assert provider["name"] == "Family Health Clinic"
    assert provider["destination_type"] == "PCP"
    assert provider["specialty"] is None
    # distance_km set by haversine ranking (patient and provider share same
    # coords in the stub, so distance should be 0.0)
    assert provider["distance_km"] == 0.0, (
        f"Same-location PCP provider must have distance_km=0.0; "
        f"got {provider['distance_km']}"
    )
    assert provider["score"] is not None, "Provider must have a ranking score"

    # Recommendation stored with ID
    rec_id = body["recommendation_id"]
    assert rec_id.startswith("rec_"), f"Unexpected rec_id format: {rec_id!r}"
    stored = recommendation_store.get(rec_id)
    assert stored is not None, "Recommendation must be persisted in store"
    assert stored.decision.destination == "PCP"


def test_navigate_telehealth_destination_no_provider_lookup(monkeypatch):
    """TELEHEALTH end-to-end flow through /navigate.

    Verifies:
    - destination is TELEHEALTH, specialty is None
    - correct rule matched (TELE-003-GENERAL)
    - find_nearby_providers IS called by the agent's discover_providers tool,
      but returns [] immediately for TELEHEALTH (no Overpass/OSM API call made)
    - top_providers is empty []
    - response is a valid Recommendation with recommendation_id

    Behavior note vs. old LangGraph path:
      The old path skipped discovery entirely for TELEHEALTH (rank_node was
      bypassed via a conditional edge).  The new agentic path calls the
      discover_providers tool which calls find_nearby_providers; that function
      returns [] for TELEHEALTH without making any network request.
      The net result is identical (top_providers=[]) but find_nearby_providers
      is now invoked once.
    """
    discovery_call_count = {"n": 0}

    def track_discovery(location, destination, specialty):
        discovery_call_count["n"] += 1
        return []

    monkeypatch.setattr(
        "location.provider_discovery.find_nearby_providers",
        track_discovery,
    )

    _loc = {"latitude": 37.7749, "longitude": -122.4194}

    with (
        _nav_client_patch(_TELEHEALTH_PATIENT, _loc),
        patch(
            "engine.explainer.explain_decision",
            return_value="A telehealth visit is appropriate for this mild, improving symptom.",
        ),
    ):
        from api.routes import app
        client = TestClient(app)
        resp = client.post(
            "/navigate",
            json={"patient": _TELEHEALTH_PATIENT, "location": _LOCATION},
        )

    assert resp.status_code == 200, f"/navigate TELEHEALTH failed: {resp.text}"
    body = resp.json()

    # Destination and specialty
    decision = body["decision"]
    assert decision["destination"] == "TELEHEALTH", (
        f"mild_general_symptom (improving, pain=2) must route to TELEHEALTH; "
        f"got {decision['destination']!r}"
    )
    assert decision["specialty"] is None, (
        f"TELEHEALTH must have specialty=None; got {decision['specialty']!r}"
    )
    assert decision["rule_id"] == "TELE-003-GENERAL", (
        f"Expected TELE-003-GENERAL; got {decision['rule_id']!r}"
    )

    # The Navigation Agent's discover_providers tool calls find_nearby_providers
    # for TELEHEALTH (returning [] without an Overpass call).  Count must be 1.
    assert discovery_call_count["n"] == 1, (
        f"find_nearby_providers must be called exactly once by discover_providers; "
        f"was called {discovery_call_count['n']} time(s)"
    )
    assert body["top_providers"] == [], (
        f"TELEHEALTH must return empty top_providers; "
        f"got {body['top_providers']}"
    )

    # Recommendation still stored
    rec_id = body["recommendation_id"]
    assert rec_id.startswith("rec_")
    stored = recommendation_store.get(rec_id)
    assert stored is not None
    assert stored.decision.destination == "TELEHEALTH"
