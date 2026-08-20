from fastapi import FastAPI, HTTPException, Query

from models.schemas import (
    PatientFeatures,
    PatientLocation,
    Recommendation,
    AppointmentAvailabilityRequest,
    BookingRequest,
    BookingConfirmation,
)
from orchestrator.graph import navigation_graph
from appointment.client import AppointmentAgentClient
from appointment.agent import AppointmentService
from appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentStatusResponse,
    AvailabilityWorkflowResponse,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from api.recommendation_store import recommendation_store

app = FastAPI(title="Alternate Care Navigation Agent")
appointment_client = AppointmentAgentClient()
appointment_service = AppointmentService(client=appointment_client)

# Prefix written by rank_node when geocoding fails (see orchestrator/graph.py).
# We match on this prefix so the route can distinguish a location error from
# other rank_node failures (e.g. Overpass network error) and return 422.
_GEOCODING_ERROR_PREFIX = "rank_node failed: "
_GEOCODING_ERROR_TYPES = (
    "InvalidLocationError",
    "GeocodingNetworkError",
    "GeocodingRateLimitError",
    "GeocodingError",
)


def _find_location_error(errors: list[str]) -> str | None:
    """Return the first geocoding-related error message, or None.

    rank_node stores exceptions as ``"rank_node failed: <ExceptionType>: <msg>"``
    when geocoding raises.  We detect the error type by name so the route can
    raise a 422 (unprocessable location) instead of silently returning HTTP 200
    with no providers.
    """
    for err in errors:
        if err.startswith(_GEOCODING_ERROR_PREFIX):
            remainder = err[len(_GEOCODING_ERROR_PREFIX):]
            for exc_type in _GEOCODING_ERROR_TYPES:
                if remainder.startswith(exc_type):
                    return remainder  # e.g. "InvalidLocationError: No geocoding results ..."
    return None


@app.post("/navigate", response_model=Recommendation)
def navigate(patient: PatientFeatures, location: PatientLocation) -> Recommendation:
    """Stage 1+2 (+LLM explanation): runs the LangGraph pipeline —
    classify -> discover -> rank -> explain.

    Stores the result in recommendation_store and returns the
    server-assigned recommendation_id for subsequent appointment calls.

    Returns HTTP 422 when the supplied location cannot be geocoded so the
    caller receives a clear, actionable error rather than a silent HTTP 200
    with no providers.
    """
    try:
        result = navigation_graph.invoke(
            {"patient": patient, "location": location, "errors": []}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If geocoding failed, the graph still ran to completion (rank_node
    # catches all exceptions), but the location was unusable.  Raise 422
    # before storing an unusable recommendation.
    location_error = _find_location_error(result.get("errors", []))
    if location_error:
        raise HTTPException(
            status_code=422,
            detail=f"Location could not be resolved: {location_error}",
        )

    # Build a bare Recommendation; recommendation_store.create() generates
    # and stamps the authoritative recommendation_id.
    rec = Recommendation(
        recommendation_id="",  # placeholder — overwritten by store.create()
        decision=result["decision"],
        top_providers=result.get("ranked_providers", []),
    )
    # Use the location from the graph result — rank_node may have geocoded an
    # address-only PatientLocation into one with real coordinates.  Fall back
    # to the originally supplied location for TELEHEALTH paths (rank_node is
    # skipped) or when the key is absent.
    stored_location = result.get("location") or location
    recommendation_id = recommendation_store.create(rec, patient_location=stored_location)

    # Return the stored copy so recommendation_id is the server-assigned value.
    return recommendation_store.require(recommendation_id)


@app.post("/appointments/availability", response_model=AvailabilityWorkflowResponse)
def availability(request: AppointmentAvailabilityRequest) -> AvailabilityWorkflowResponse:
    """Return available slots for a provider that belongs to an existing
    recommendation.

    care_type and specialty are derived from the stored CareDecision —
    the client must NOT supply them independently.

    Response includes:
      - available_slots  — list of appointment slots from the external service
      - provider_id      — echoed from the validated recommendation
      - care_type        — derived from the stored CareDecision (authoritative)
      - specialty        — derived from the stored CareDecision (SPECIALIST only)
    """
    try:
        provider = recommendation_store.require_provider(
            request.recommendation_id, request.provider_id
        )
        recommendation = recommendation_store.require(request.recommendation_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    care_type = recommendation.decision.destination
    specialty = recommendation.decision.specialty

    # Reconstruct patient context from the location persisted at navigation
    # time.  Falls back to None when location is absent (older callers or
    # tests that omit location) — the client treats None as no context.
    patient_location = recommendation_store.get_patient_location(
        request.recommendation_id
    )
    if patient_location is not None:
        patient_context = AppointmentPatientContext(
            latitude=patient_location.latitude,
            longitude=patient_location.longitude,
        )
    else:
        patient_context = None

    slots = appointment_client.get_availability(
        provider_id=provider.provider_id,
        care_type=care_type,
        specialty=specialty,
        date_range=request.date_range,
        patient_id=request.patient_id,
        patient_context=patient_context,
    )
    return AvailabilityWorkflowResponse(
        available_slots=slots,
        provider_id=provider.provider_id,
        care_type=care_type,
        specialty=specialty,
    )


@app.post("/appointments/book", response_model=AppointmentConfirmation)
def book(request: BookingRequest) -> AppointmentConfirmation:
    """Stage 3: validate the provider against the stored recommendation,
    then hand off booking to the shared Appointment Agent.

    Validation flow:
      1. recommendation_store.require_provider() confirms the recommendation
         exists, has not expired, and that provider_id belongs to it.
         The returned ProviderCandidate carries the authoritative provider
         name from the navigation pipeline.
      2. recommendation_store.require() retrieves the stored Recommendation
         so that care_type and specialty are derived from the trusted
         CareDecision — not supplied by the caller.
      3. appointment_service.book_appointment() is called with the
         BookingWorkflowRequest plus the specialty and provider_name derived
         from the stored CareDecision and ProviderCandidate respectively.

    The derived care_type, specialty, and provider_name are authoritative;
    the caller cannot override them.
    """
    try:
        provider = recommendation_store.require_provider(
            request.recommendation_id, request.provider_id
        )
        recommendation = recommendation_store.require(request.recommendation_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Derive from the stored CareDecision — not from the request.
    care_type = recommendation.decision.destination
    specialty = recommendation.decision.specialty

    # Reconstruct patient context from the location persisted at navigation
    # time.  Falls back to None when location is absent (older callers or
    # tests that omit location) — the client treats None as no context.
    patient_location = recommendation_store.get_patient_location(
        request.recommendation_id
    )
    if patient_location is not None:
        book_patient_context = AppointmentPatientContext(
            latitude=patient_location.latitude,
            longitude=patient_location.longitude,
        )
    else:
        book_patient_context = None

    return appointment_service.book_appointment(
        BookingWorkflowRequest(
            patient_id=request.patient_id,
            recommendation_id=request.recommendation_id,
            provider_id=request.provider_id,
            slot_id=request.slot_id,
        ),
        care_type=care_type,
        specialty=specialty,
        provider_name=provider.name,
        patient_context=book_patient_context,
    )


@app.post("/appointments/reschedule", response_model=AppointmentConfirmation)
def reschedule(request: RescheduleRequest) -> AppointmentConfirmation:
    """Reschedule an existing appointment.

    Supports two workflows:
      A) Direct slot selection — supply new_slot_id.
      B) Preference-based — supply preferred_date and/or preferred_time;
         the external Appointment Agent finds and assigns the best slot.

    recommendation_id is NOT required for rescheduling — the original
    recommendation may have expired from the 30-minute RecommendationStore
    TTL by the time the patient reschedules.

    The patient/appointment relationship is validated by the external
    Appointment Agent (patient_id + appointment_id are both forwarded).

    Request body:
        {
            "patient_id":       "...",
            "appointment_id":   "...",
            "new_slot_id":      "..."          // Workflow A
        }
        OR:
        {
            "patient_id":       "...",
            "appointment_id":   "...",
            "preferred_date":   "...",         // Workflow B
            "preferred_time":   "..."
        }
    """
    try:
        return appointment_service.reschedule_appointment(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")


@app.post("/appointments/cancel", response_model=AppointmentStatusResponse)
def cancel(request: CancellationRequest) -> AppointmentStatusResponse:
    """Cancel an existing appointment.

    Both patient_id and appointment_id are required and are forwarded to
    the external Appointment Agent so it can validate the patient/appointment
    relationship on its side.

    Request body:
        {
            "patient_id":     "...",
            "appointment_id": "..."
        }
    """
    try:
        return appointment_service.cancel_appointment(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")


@app.get("/appointments/{appointment_id}", response_model=AppointmentStatusResponse)
def get_appointment_status(
    appointment_id: str,
    patient_id: str = Query(default=None, description="Patient identifier for context"),
) -> AppointmentStatusResponse:
    """Retrieve the current status of an appointment.

    Path parameter:
        appointment_id — the ID of the appointment to query.

    Query parameter:
        patient_id — optional patient identifier forwarded to the
                     external Appointment Agent for caller context.
    """
    try:
        return appointment_service.get_appointment_status(
            appointment_id=appointment_id,
            patient_id=patient_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")
