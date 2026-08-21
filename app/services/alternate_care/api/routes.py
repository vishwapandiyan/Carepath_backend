"""
API routes for the Alternate Care Navigation Agent.

POST /navigate  — now powered by the agentic Navigation Agent (NVIDIA Llama
via NvidiaClient tool-calling loop) instead of the LangGraph fixed pipeline.

All other routes (/appointments/*) are unchanged.

Execution path for POST /navigate
-----------------------------------
Old path (removed):
    navigation_graph.invoke(...)     ← LangGraph: validate → classify →
                                        rank → explain (Google Gemini)

New path:
    run_navigation_agent(...)        ← NVIDIA Llama tool-calling loop
      LLM decides → classify_care    ← CareClassifier (deterministic)
      LLM decides → geocode_location ← geocode() Nominatim (if needed)
      LLM decides → discover_providers ← find_nearby_providers() Overpass
      LLM decides → rank_providers   ← rank_providers() Haversine
      LLM produces final_response prose
    _adapt_agent_result(...)         ← converts dicts → schema objects
    RecommendationStore.create()     ← unchanged

The response schema (Recommendation) is identical.  The RecommendationStore
contract is identical.  All downstream appointment routes are unchanged.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

import logging
from typing import List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, APIRouter

from app.services.alternate_care.models.schemas import (
    PatientFeatures,
    PatientLocation,
    CareDecision,
    ProviderCandidate,
    Recommendation,
    AppointmentAvailabilityRequest,
    BookingRequest,
    BookingConfirmation,
    AppointmentSlot,
)
from pydantic import BaseModel, Field
from typing import Any, Dict
from app.services.alternate_care.agents.navigation_agent import run_navigation_agent
from app.services.alternate_care.agents.appointment_agent import run_appointment_agent, continue_appointment_agent
from app.services.alternate_care.database.session_bridge import AppointmentSessionRepository
# Import CarePath's async DB dependency
from app.db.base import get_db
from app.services.alternate_care.appointment.client import AppointmentAgentClient
from app.services.alternate_care.appointment.agent import AppointmentService
from app.services.alternate_care.appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentStatusResponse,
    AvailabilityWorkflowResponse,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from app.services.alternate_care.api.recommendation_store import recommendation_store

logger = logging.getLogger(__name__)

app = APIRouter()
appointment_client = AppointmentAgentClient()
appointment_service = AppointmentService(client=appointment_client)


# ---------------------------------------------------------------------------
# Navigation Agent result adapter
# ---------------------------------------------------------------------------

def _adapt_agent_result(
    agent_result: dict,
    original_location: PatientLocation,
) -> Tuple[CareDecision, List[ProviderCandidate], PatientLocation]:
    """Convert a successful run_navigation_agent() result into typed schema objects.

    Parameters
    ----------
    agent_result:
        The dict returned by run_navigation_agent() when ok=True.
    original_location:
        The PatientLocation passed into /navigate.  Used as the resolved
        location when the agent did not need to geocode (coords were
        already present), and as a fallback if geocoding failed.

    Returns
    -------
    (decision, top_providers, resolved_location)
        All three are typed schema objects ready for Recommendation construction
        and RecommendationStore storage.

    Raises
    ------
    HTTPException(422)
        When no care_decision was obtained from the agent (the LLM never
        successfully called classify_care).
    """
    # --- 1. CareDecision ---------------------------------------------------
    raw_decision = agent_result.get("care_decision")
    if not raw_decision:
        raise HTTPException(
            status_code=422,
            detail=(
                "Navigation agent did not produce a care classification. "
                "Ensure primary_symptom_category is provided and valid."
            ),
        )
    # Strip the 'ok' key (not a CareDecision field) before constructing.
    decision = CareDecision(**{k: v for k, v in raw_decision.items() if k != "ok"})

    # --- 2. ProviderCandidate list -----------------------------------------
    raw_providers: list = agent_result.get("ranked_providers") or []
    top_providers: List[ProviderCandidate] = [
        ProviderCandidate(**p) for p in raw_providers
    ]

    # --- 3. Resolved PatientLocation ---------------------------------------
    # Preference order:
    #   a) geocoded_location from agent (set when geocode_location tool ran)
    #   b) original location as-is (already had coordinates)
    geo = agent_result.get("geocoded_location")
    if geo and geo.get("ok") and geo.get("latitude") is not None:
        resolved_location = PatientLocation(
            latitude=geo["latitude"],
            longitude=geo["longitude"],
            radius_km=original_location.radius_km,
            address=geo.get("address") or original_location.address,
        )
    else:
        resolved_location = original_location

    return decision, top_providers, resolved_location


# ---------------------------------------------------------------------------
# POST /navigate
# ---------------------------------------------------------------------------

class NavigateRequest(BaseModel):
    """Request body for POST /navigate.
    
    Wraps patient clinical features and location with a required MRN
    from the upstream Patient/Hospital System.
    """
    mrn: str = Field(
        ...,
        description=(
            "Medical Record Number from the upstream Patient/Hospital System. "
            "Required. Passed through unchanged; never generated or modified by this service."
        ),
    )
    patient: PatientFeatures
    location: PatientLocation


@app.post("/navigate", response_model=Recommendation)
async def navigate(
    request: NavigateRequest,
    db: AsyncSession = Depends(get_db)
) -> Recommendation:
    """Run the Navigation Agent to classify care and find nearby providers.

    The Navigation Agent drives a bounded LLM tool-calling loop (NVIDIA
    meta/llama-3.3-70b-instruct).  The LLM decides which tools to call;
    all medical routing, geocoding, provider discovery, and distance ranking
    are performed by the deterministic tool implementations — never by the LLM
    directly.

    Stores the result in recommendation_store and returns the server-assigned
    recommendation_id for subsequent appointment calls.
    
    If appointment tools were invoked during execution, the response includes
    appointment_operations_performed: true and appointment_results with the
    operation history. These fields maintain backward compatibility.

    Returns
    -------
    HTTP 200 — Recommendation with recommendation_id, decision, top_providers,
               and optional appointment fields if appointment tools were used
    HTTP 400 — Invalid input (malformed PatientFeatures / PatientLocation)
    HTTP 422 — Agent ran but failed to produce a care classification
    HTTP 500 — Agent loop error (max iterations, unexpected failure)
    HTTP 502 — NVIDIA LLM API unreachable or returned an error
    """
    # Build the location_input dict for the agent from the Pydantic model.
    patient = request.patient
    location = request.location
    mrn = request.mrn

    patient_features = patient.model_dump(exclude_none=False)

    # ------------------------------------------------------------------
    # Stage 1: Deterministic care classification (rule engine)
    # ------------------------------------------------------------------
    # Classification is deterministic (YAML rule engine) — no LLM needed.
    # This avoids LLM token-budget issues and is faster + more reliable.
    from app.services.alternate_care.agents.tools.navigation_tools import classify_care

    care_result = classify_care(patient_features)
    if not care_result.get("ok"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Care classification failed. "
                "Ensure primary_symptom_category is provided and valid. "
                f"Error: {care_result.get('error', 'Unknown')}"
            ),
        )

    # Build CareDecision from the deterministic result
    decision = CareDecision(**{k: v for k, v in care_result.items() if k != "ok"})

    # Resolve the patient location (coordinates already provided)
    resolved_location = location

    # No providers from navigation agent (Appointment Agent handles this now)
    top_providers: List[ProviderCandidate] = []

    # Build Recommendation; store assigns the authoritative recommendation_id.
    rec = Recommendation(
        recommendation_id="",   # placeholder — overwritten by store.create()
        mrn=mrn,
        decision=decision,
        top_providers=top_providers,
    )
    recommendation_id = recommendation_store.create(
        rec, patient_location=resolved_location
    )

    # Get the stored recommendation with the authoritative ID
    stored_rec = recommendation_store.require(recommendation_id)

    logger.info(
        "navigate: classification complete (mrn=%s recommendation_id=%s destination=%s)",
        mrn, recommendation_id, decision.destination,
    )

    # ------------------------------------------------------------------
    # AUTOMATIC HANDOFF: Navigation → Appointment Agent
    # ------------------------------------------------------------------
    # After navigation completes, automatically invoke the Appointment Agent
    # to search for nearby providers and present them to the patient.
    # No manual client-side orchestration required.
    appointment_agent_response = None
    nearby_providers = None

    try:
        # Resolve the patient's coordinates for the handoff
        handoff_lat = resolved_location.latitude
        handoff_lon = resolved_location.longitude
        handoff_radius = resolved_location.radius_km if resolved_location.radius_km else 15.0

        logger.info(
            "navigate: automatic handoff to Appointment Agent "
            "(mrn=%s recommendation_id=%s destination=%s)",
            mrn, recommendation_id, decision.destination,
        )

        appt_result = run_appointment_agent(
            recommendation_id=recommendation_id,
            destination=decision.destination,
            latitude=handoff_lat,
            longitude=handoff_lon,
            radius_km=handoff_radius,
            specialty=decision.specialty,
        )

        if appt_result.get("ok"):
            appointment_agent_response = appt_result.get("response")
            nearby_providers = appt_result.get("providers")

            # Convert nearby_providers list into ProviderCandidate schema objects for top_providers
            top_prov_list: List[ProviderCandidate] = []
            if nearby_providers:
                for p in nearby_providers:
                    try:
                        top_prov_list.append(ProviderCandidate(
                            provider_id=p.get("provider_id"),
                            name=p.get("provider_name") or p.get("facility_name") or "Healthcare Provider",
                            destination_type=decision.destination,
                            specialty=decision.specialty,
                            latitude=float(p.get("latitude") or 0.0),
                            longitude=float(p.get("longitude") or 0.0),
                            address=p.get("address"),
                            distance_km=p.get("distance_km"),
                            source=p.get("source", "osm")
                        ))
                    except Exception:
                        pass

            recommendation_store.update(
                recommendation_id,
                {
                    "nearby_providers": nearby_providers,
                    "top_providers": top_prov_list,
                    "appointment_agent_response": appointment_agent_response,
                }
            )

            logger.info(
                "navigate: Appointment Agent completed (providers=%d)",
                len(nearby_providers) if nearby_providers else 0,
            )
        else:
            logger.warning(
                "navigate: Appointment Agent returned ok=False: %s",
                appt_result.get("error"),
            )
            appointment_agent_response = appt_result.get("response") or appt_result.get("error")

        # ------------------------------------------------------------
        # PERSIST: save the appointment session to PostgreSQL (POST_CARE's
        # existing carepath_db) so Turn 2 (/chat) can resume this exact
        # conversation. recommendation_id is reused as the session_id —
        # no second identifier is minted.
        # ------------------------------------------------------------
        workflow_stage = "PROVIDERS_SEARCHED" if nearby_providers else "NAVIGATION_COMPLETE"
        try:
            await AppointmentSessionRepository.create_session(
                db=db,
                mrn=mrn,
                destination=decision.destination,
                specialty=decision.specialty,
                rule_id=decision.rule_id,
                latitude=handoff_lat,
                longitude=handoff_lon,
                radius_km=handoff_radius,
                source="PATIENT",
                session_id=recommendation_id,
                conversation_state=appt_result.get("messages"),
            )
            await AppointmentSessionRepository.update_session(
                db=db,
                session_id=recommendation_id,
                updates={
                    "provider_candidates": nearby_providers,
                    "workflow_stage": workflow_stage,
                },
            )
            logger.info(
                "navigate: appointment session persisted "
                "(session_id=%s workflow_stage=%s providers=%d)",
                recommendation_id, workflow_stage,
                len(nearby_providers) if nearby_providers else 0,
            )
        except Exception as persist_exc:
            # Persistence failure must not break the patient-facing response;
            # the recommendation itself is still valid and returned below.
            logger.warning(
                "navigate: failed to persist appointment session for %s: %s",
                recommendation_id, persist_exc,
            )

    except Exception as exc:
        logger.warning("navigate: Appointment Agent handoff failed: %s", exc)
        appointment_agent_response = f"Provider search unavailable: {exc}"

    # Build response with optional appointment fields
    return Recommendation(
        recommendation_id=stored_rec.recommendation_id,
        mrn=mrn,
        decision=stored_rec.decision,
        top_providers=stored_rec.top_providers,
        appointment_agent_response=appointment_agent_response,
        nearby_providers=nearby_providers,
    )


# ---------------------------------------------------------------------------
# POST /appointments/availability
# ---------------------------------------------------------------------------

@app.post("/appointments/availability", response_model=AvailabilityWorkflowResponse)
def availability(request: AppointmentAvailabilityRequest) -> AvailabilityWorkflowResponse:
    """Return available slots for a provider that belongs to an existing
    recommendation.

    care_type and specialty are derived from the stored CareDecision —
    the client must NOT supply them independently.
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


# ---------------------------------------------------------------------------
# POST /appointments/book
# ---------------------------------------------------------------------------

@app.post("/appointments/book", response_model=AppointmentConfirmation)
def book(request: BookingRequest) -> AppointmentConfirmation:
    """Validate the provider against the stored recommendation, then hand off
    booking to the shared Appointment Agent.
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


# ---------------------------------------------------------------------------
# POST /appointments/reschedule
# ---------------------------------------------------------------------------

@app.post("/appointments/reschedule", response_model=AppointmentConfirmation)
def reschedule(request: RescheduleRequest) -> AppointmentConfirmation:
    """Reschedule an existing appointment."""
    try:
        return appointment_service.reschedule_appointment(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")


# ---------------------------------------------------------------------------
# POST /appointments/cancel
# ---------------------------------------------------------------------------

@app.post("/appointments/cancel", response_model=AppointmentStatusResponse)
def cancel(request: CancellationRequest) -> AppointmentStatusResponse:
    """Cancel an existing appointment."""
    try:
        return appointment_service.cancel_appointment(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")


# ---------------------------------------------------------------------------
# GET /appointments/{appointment_id}
# ---------------------------------------------------------------------------

@app.get("/appointments/{appointment_id}", response_model=AppointmentStatusResponse)
def get_appointment_status(
    appointment_id: str,
    patient_id: str = Query(default=None, description="Patient identifier for context"),
) -> AppointmentStatusResponse:
    """Retrieve the current status of an appointment."""
    try:
        return appointment_service.get_appointment_status(
            appointment_id=appointment_id,
            patient_id=patient_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {e}")


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Request body for POST /chat — continues an Appointment Agent
    conversation that was started automatically by /navigate."""

    recommendation_id: str = Field(
        ...,
        description=(
            "The recommendation_id returned by /navigate. Used as the "
            "appointment session identifier — no separate session ID exists."
        ),
    )
    message: str = Field(
        ...,
        description="The patient's free-text message for this turn.",
    )


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    recommendation_id: str
    mrn: str
    response: str
    workflow_stage: str
    selected_provider_id: Optional[str] = None
    selected_provider_name: Optional[str] = None
    available_slots: Optional[List[AppointmentSlot]] = None
    selected_slot_id: Optional[str] = None
    appointment_id: Optional[str] = None
    appointment_status: Optional[str] = None


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    """Continue an Appointment Agent conversation across HTTP requests.

    Turn 1 (/navigate) automatically invokes the Appointment Agent, which
    persists its conversation state (message history + provider results)
    to the appointment_sessions table in POST_CARE's existing carepath_db,
    keyed by recommendation_id.

    This endpoint:
      1. Retrieves that session from PostgreSQL by recommendation_id.
      2. Rejects the request if the session is missing or expired.
      3. Restores the exact prior conversation (system prompt, provider
         search results, assistant turns) and the known provider list.
      4. Appends the patient's new message.
      5. Resumes the SAME LLM tool-calling loop used in Turn 1 — the LLM
         decides whether to call select_provider (or any other available
         tool) based on the restored context, not a hard-coded rule.
      6. Persists the updated conversation state and any newly selected
         provider back to PostgreSQL.

    Returns
    -------
    HTTP 200 — ChatResponse with the agent's reply and updated workflow_stage
    HTTP 404 — Unknown or expired recommendation_id
    HTTP 502 — NVIDIA LLM API unreachable or returned an error
    """
    session = await AppointmentSessionRepository.get_session(db, request.recommendation_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown or expired recommendation_id: "
                f"{request.recommendation_id!r}"
            ),
        )

    conversation_state = session.get("conversation_state")
    if not conversation_state:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Appointment Agent conversation found for "
                f"recommendation_id={request.recommendation_id!r}. "
                "The session exists but has no prior conversation to resume."
            ),
        )

    known_providers = session.get("provider_candidates") or []
    known_slots = session.get("available_slots") or []

    try:
        result = continue_appointment_agent(
            conversation_state=conversation_state,
            patient_message=request.message,
            known_providers=known_providers,
            known_slots=known_slots,
            session_selected_provider_id=session.get("selected_provider_id"),
            session_selected_slot_id=session.get("selected_slot_id"),
            session_mrn=session.get("mrn"),
        )
    except Exception as exc:
        logger.error("chat: Appointment Agent resume failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Appointment Agent error: {exc}")

    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Appointment Agent error: {result.get('error', 'unknown error')}",
        )

    # DIAGNOSTIC TRACE 4 — /chat route agent_result
    logger.info("DIAGNOSTIC TRACE 4 — /chat route agent_result:")
    logger.info("  agent_result.keys() = %s", list(result.keys()))
    logger.info("  agent_result.get('available_slots') = %s", result.get("available_slots"))
    logger.info("  agent_result.get('selected_provider_id') = %s", result.get("selected_provider_id"))
    logger.info("  agent_result.get('selected_provider_name') = %s", result.get("selected_provider_name"))
    
    # Merge current-turn agent result with persisted PostgreSQL session state.
    # This ensures accumulated state (provider selection, availability from prior turns)
    # survives when the agent doesn't call the corresponding tool this turn.
    # Rule: Use new agent value if present; otherwise preserve existing session value.
    selected_provider_id = (
        result.get("selected_provider_id")
        if result.get("selected_provider_id") is not None
        else session.get("selected_provider_id")
    )
    selected_provider_name = (
        result.get("selected_provider_name")
        if result.get("selected_provider_name") is not None
        else session.get("selected_provider_name")
    )
    # appointment_sessions has no selected_provider_name column, so when a
    # prior turn's selection is being carried forward (not this turn's fresh
    # agent result), derive the name from the persisted provider_candidates
    # list instead. Falls back to None if the provider_id isn't found there.
    if selected_provider_name is None and selected_provider_id:
        for candidate in (session.get("provider_candidates") or []):
            if candidate.get("provider_id") == selected_provider_id:
                selected_provider_name = candidate.get("provider_name")
                break
    available_slots = (
        result.get("available_slots")
        if result.get("available_slots") is not None
        else session.get("available_slots")
    )
    selected_slot_id = (
        result.get("selected_slot_id")
        if result.get("selected_slot_id") is not None
        else session.get("selected_slot_id")
    )
    appointment_id = (
        result.get("appointment_id")
        if result.get("appointment_id") is not None
        else session.get("appointment_id")
    )
    appointment_status = (
        result.get("appointment_status")
        if result.get("appointment_status") is not None
        else session.get("appointment_status")
    )
    
    # Determine the new workflow_stage. A provider selection this turn moves
    # the stage forward; availability check moves it further; slot selection
    # moves it further still; a successful booking moves it to BOOKED.
    # Otherwise the stage is unchanged.
    
    workflow_stage = session.get("workflow_stage") or "PROVIDERS_SEARCHED"
    
    # Only transition workflow_stage forward if THIS TURN produced new state.
    # Use agent result (not merged state) to detect new actions.
    if result.get("selected_provider_id") is not None:
        workflow_stage = "PROVIDER_SELECTED"
    if result.get("available_slots") is not None:
        workflow_stage = "AVAILABILITY_CHECKED"
    if result.get("selected_slot_id") is not None:
        workflow_stage = "SLOT_SELECTED"
    if result.get("appointment_id") is not None and result.get("appointment_status") == "BOOKED":
        workflow_stage = "BOOKED"

    updates: Dict[str, Any] = {
        "conversation_state": result.get("messages"),
        "workflow_stage": workflow_stage,
    }
    if selected_provider_id:
        updates["selected_provider_id"] = selected_provider_id
    if available_slots is not None:
        updates["available_slots"] = available_slots
    if selected_slot_id:
        updates["selected_slot_id"] = selected_slot_id
    if appointment_id:
        updates["appointment_id"] = appointment_id
    if appointment_status:
        updates["appointment_status"] = appointment_status

    try:
        await AppointmentSessionRepository.update_session(
            db=db,
            session_id=request.recommendation_id,
            updates=updates
        )
    except Exception as persist_exc:
        logger.warning(
            "chat: failed to persist updated session for %s: %s",
            request.recommendation_id, persist_exc,
        )

    logger.info(
        "chat: recommendation_id=%s mrn=%s workflow_stage=%s "
        "selected_provider_id=%s available_slots=%s",
        request.recommendation_id, session.get("mrn"), workflow_stage,
        selected_provider_id, len(available_slots) if available_slots else 0,
    )

    # DIAGNOSTIC TRACE 5 — ChatResponse construction
    logger.info("DIAGNOSTIC TRACE 5 — ChatResponse variables before construction:")
    logger.info("  selected_provider_id = %s (type: %s)", selected_provider_id, type(selected_provider_id).__name__)
    logger.info("  selected_provider_name = %s (type: %s)", selected_provider_name, type(selected_provider_name).__name__)
    logger.info("  available_slots = %s (type: %s)", available_slots, type(available_slots).__name__)
    if available_slots:
        logger.info("  len(available_slots) = %s", len(available_slots))
    
    chat_response = ChatResponse(
        recommendation_id=request.recommendation_id,
        mrn=session.get("mrn"),
        response=result.get("response") or "",
        workflow_stage=workflow_stage,
        appointment_id=appointment_id,
        appointment_status=appointment_status,
        selected_provider_id=selected_provider_id,
        selected_provider_name=selected_provider_name,
        available_slots=available_slots,
        selected_slot_id=selected_slot_id,
    )
    
    logger.info("DIAGNOSTIC TRACE 5.5 — ChatResponse after construction:")
    logger.info("  ChatResponse.available_slots = %s", chat_response.available_slots)
    logger.info("  ChatResponse.selected_provider_id = %s", chat_response.selected_provider_id)
    logger.info("  ChatResponse.selected_provider_name = %s", chat_response.selected_provider_name)
    
    return chat_response
