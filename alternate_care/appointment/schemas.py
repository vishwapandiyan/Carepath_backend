"""
Appointment workflow schemas for the Shared Appointment Agent.

Scope
-----
These models describe the data contract for the Shared Appointment Agent
service — the external service that handles availability discovery,
booking, rescheduling, and cancellation.

Architectural boundary
----------------------
The Appointment Agent does NOT perform:
  - patient classification
  - ED classification
  - care-destination selection
  - provider ranking
  - clinical reasoning

Those are upstream responsibilities of the Alternate Care Navigation Agent.
By the time a request reaches the Appointment Agent, the CareDecision
(destination + specialty) and the authorised provider have already been
determined and stored in RecommendationStore.

Internal vs external split
---------------------------
``recommendation_id`` appears in several models here because the internal
API layer needs it to look up the trusted CareDecision from
RecommendationStore.  It must NOT be forwarded to the external Appointment
Agent HTTP payload (enforced by ``AppointmentAgentClient.book()``).

Reused from models.schemas
--------------------------
``Destination``, ``AppointmentSlot`` — imported directly; no duplicate
definitions.

Date/time convention
--------------------
All date and time fields are plain ``str`` to remain compatible with the
existing ``AppointmentAgentClient`` wire format and ``AppointmentSlot``
schema.  No ``datetime`` parsing is applied here.
"""

from __future__ import annotations

from typing import Optional, List, Literal

from pydantic import BaseModel, ConfigDict, model_validator

# Re-use the canonical types from the navigation layer so there is no
# divergence between what the navigation pipeline produces and what the
# appointment workflow consumes.
from app.services.alternate_care.models.schemas import Destination, AppointmentSlot  # noqa: F401 (re-exported)


# ---------------------------------------------------------------------------
# Group 1 — Common workflow context
# ---------------------------------------------------------------------------

AppointmentActor = Literal["PATIENT"]
"""The actor initiating the appointment request.

Currently only PATIENT is supported.  Future actors (e.g. PROVIDER,
CARE_COORDINATOR) can be added without breaking existing validators.
"""


class AppointmentPreferences(BaseModel):
    """Optional caller preferences carried through the appointment workflow."""

    model_config = ConfigDict(extra="ignore")

    language: Optional[str] = None
    """Preferred communication language (e.g. 'en', 'es')."""

    preferred_date: Optional[str] = None
    """ISO-8601 date string preferred by the patient (e.g. '2026-08-25')."""

    preferred_time: Optional[str] = None
    """Preferred time of day (e.g. 'morning', 'afternoon', '09:00')."""


class AppointmentPatientContext(BaseModel):
    """Contextual information about the patient relevant to appointment lookup.

    This is NOT clinical data — it carries logistical context (location,
    scheduling preferences) needed by the Appointment Agent to surface
    relevant slots.
    """

    model_config = ConfigDict(extra="ignore")

    latitude: Optional[float] = None
    """Patient's current latitude.  Used for proximity-aware slot surfacing."""

    longitude: Optional[float] = None
    """Patient's current longitude."""

    preferences: Optional[AppointmentPreferences] = None
    """Scheduling preferences supplied by the patient."""


# ---------------------------------------------------------------------------
# Group 2 — Intent and the unified workflow request
# ---------------------------------------------------------------------------

AppointmentIntent = Literal[
    "CHECK_AVAILABILITY",
    "BOOK_APPOINTMENT",
    "RESCHEDULE_APPOINTMENT",
    "CANCEL_APPOINTMENT",
]
"""The operation the caller wants to perform."""


class AppointmentWorkflowRequest(BaseModel):
    """Unified intake model for the Appointment Agent workflow.

    Carries all fields that any appointment-related intent may need.
    Validators enforce the minimum required fields per intent and per
    care type; optional fields are ignored when not applicable.

    Internal field
    --------------
    ``recommendation_id`` is an internal authorisation identifier.  It is
    used by the navigation layer to look up the trusted CareDecision from
    RecommendationStore.  It must NOT be included in the external HTTP
    payload sent to the Appointment Agent.
    """

    model_config = ConfigDict(extra="ignore")

    actor: AppointmentActor = "PATIENT"
    intent: AppointmentIntent

    # Identity
    patient_id: str
    recommendation_id: Optional[str] = None  # INTERNAL — not forwarded externally

    # Clinical context (derived from the stored CareDecision — not trusted
    # from the caller when a recommendation_id is present)
    care_type: Optional[Destination] = None
    specialty: Optional[str] = None

    # Provider selection
    provider_id: Optional[str] = None

    # Scheduling
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    date_range: str = "next_7_days"

    # Slot (required for BOOK_APPOINTMENT and RESCHEDULE_APPOINTMENT when
    # a specific slot has already been chosen)
    slot_id: Optional[str] = None

    # Appointment identity (required for RESCHEDULE and CANCEL)
    appointment_id: Optional[str] = None

    # Contextual information
    patient_context: Optional[AppointmentPatientContext] = None

    @model_validator(mode="after")
    def _validate_intent_requirements(self) -> "AppointmentWorkflowRequest":
        """Enforce minimum field requirements per intent."""
        if self.intent == "BOOK_APPOINTMENT":
            if not self.slot_id:
                raise ValueError(
                    "slot_id is required for BOOK_APPOINTMENT intent."
                )
            if not self.provider_id:
                raise ValueError(
                    "provider_id is required for BOOK_APPOINTMENT intent."
                )

        if self.intent in ("RESCHEDULE_APPOINTMENT", "CANCEL_APPOINTMENT"):
            if not self.appointment_id:
                raise ValueError(
                    f"appointment_id is required for {self.intent} intent."
                )

        if self.intent == "RESCHEDULE_APPOINTMENT":
            has_new_slot = bool(self.slot_id)
            has_preferred_time = bool(self.preferred_date or self.preferred_time)
            if not has_new_slot and not has_preferred_time:
                raise ValueError(
                    "RESCHEDULE_APPOINTMENT requires either new_slot_id "
                    "or preferred_date / preferred_time."
                )

        return self

    @model_validator(mode="after")
    def _validate_specialist_requires_specialty(self) -> "AppointmentWorkflowRequest":
        """SPECIALIST care type requires a specialty to be present."""
        if self.care_type == "SPECIALIST" and not self.specialty:
            raise ValueError(
                "care_type SPECIALIST requires specialty to be specified."
            )
        return self


# ---------------------------------------------------------------------------
# Group 3 — Availability
# ---------------------------------------------------------------------------

class AvailabilityWorkflowRequest(BaseModel):
    """Availability request sent from the navigation layer to the Appointment Agent.

    ``care_type`` and ``specialty`` are always derived from the stored
    CareDecision in RecommendationStore — they are not accepted from the
    end-user directly.

    ``recommendation_id`` is included for internal correlation but must
    NOT be forwarded in the external HTTP payload.
    """

    model_config = ConfigDict(extra="ignore")

    # Internal authorisation context (not forwarded externally)
    recommendation_id: str

    # Provider selected from the recommendation's ranked list
    provider_id: str

    # Derived from CareDecision — not from caller
    care_type: Destination
    specialty: Optional[str] = None

    # Scheduling parameters
    date_range: str = "next_7_days"
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None

    # Patient identity (informational)
    patient_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_specialist_specialty(self) -> "AvailabilityWorkflowRequest":
        if self.care_type == "SPECIALIST" and not self.specialty:
            raise ValueError(
                "care_type SPECIALIST requires specialty to be specified."
            )
        return self


class AvailabilityWorkflowResponse(BaseModel):
    """Availability response returned to the caller.

    Wraps the list of slots produced by the Appointment Agent so that the
    response envelope is stable and extensible.
    """

    model_config = ConfigDict(extra="ignore")

    available_slots: List[AppointmentSlot] = []
    """Zero or more available appointment slots."""

    provider_id: Optional[str] = None
    """Echo of the provider_id that was queried."""

    care_type: Optional[Destination] = None
    """Echo of the care_type used for the query (derived from CareDecision)."""

    specialty: Optional[str] = None
    """Echo of the specialty (derived from CareDecision; only present for
    SPECIALIST care type — None for PCP, URGENT_CARE, TELEHEALTH)."""


# ---------------------------------------------------------------------------
# Group 4 — Booking (internal workflow model)
# ---------------------------------------------------------------------------

class BookingWorkflowRequest(BaseModel):
    """Internal booking workflow request model.

    This is the model used by the navigation layer's /appointments/book
    route and passed (after validation) to AppointmentAgentClient.book().

    ``recommendation_id`` is present for server-side validation against
    RecommendationStore.  It is stripped before the outbound HTTP payload
    is constructed in AppointmentAgentClient.book().

    External payload sent to the Appointment Agent:
        { "patient_id": ..., "provider_id": ..., "slot_id": ... }
    """

    model_config = ConfigDict(extra="ignore")

    patient_id: str
    recommendation_id: str   # INTERNAL — stripped at client boundary
    provider_id: str
    slot_id: str


# ---------------------------------------------------------------------------
# Group 5 — Booking / appointment confirmation response
# ---------------------------------------------------------------------------

class AppointmentStatus(BaseModel):
    """Not used directly as a field type — see AppointmentStatusLiteral."""


AppointmentStatusLiteral = Literal[
    "BOOKED",
    "RESCHEDULED",
    "CANCELLED",
    "COMPLETED",
]
"""Lifecycle statuses for a booked appointment."""


class AppointmentConfirmation(BaseModel):
    """Rich appointment confirmation returned after a successful booking
    or reschedule.

    Extends the minimal ``BookingConfirmation`` in models/schemas.py with
    additional provider and care-type context useful for the patient-facing
    layer.

    Optional facility fields (``hospital_id``, ``hospital_name``) cover
    SPECIALIST and URGENT_CARE cases where the provider is facility-based.
    They are intentionally absent from PCP and TELEHEALTH responses.
    """

    model_config = ConfigDict(extra="ignore")

    appointment_id: str
    patient_id: str
    status: AppointmentStatusLiteral

    # Provider information
    provider_id: str
    provider_name: Optional[str] = None

    # Care context (echoed from the CareDecision that authorised the booking)
    care_type: Optional[Destination] = None
    specialty: Optional[str] = None

    # Facility information — only present when the provider is
    # facility-based (SPECIALIST, some URGENT_CARE)
    hospital_id: Optional[str] = None
    hospital_name: Optional[str] = None

    # Slot details
    slot: AppointmentSlot

    # Convenience top-level date/time fields mirroring slot.start_time
    # for callers that prefer a flatter structure
    date: Optional[str] = None
    time: Optional[str] = None


# ---------------------------------------------------------------------------
# Group 6 — Rescheduling
# ---------------------------------------------------------------------------

class RescheduleRequest(BaseModel):
    """Request to reschedule an existing appointment.

    Supports two workflows:

    Workflow A — direct slot selection:
        Supply ``new_slot_id``.  The Appointment Agent reschedules directly
        to the nominated slot (assumes caller already performed availability
        lookup and chose a slot).

    Workflow B — preference-based search:
        Supply ``preferred_date`` and/or ``preferred_time``.  The Appointment
        Agent finds available slots matching the preferences and presents
        them; the caller then selects and can invoke Workflow A.

    At least one of ``new_slot_id``, ``preferred_date``, or
    ``preferred_time`` must be present — the validator enforces this.

    ``recommendation_id`` is optional here because a reschedule may occur
    after the original recommendation has expired from RecommendationStore.
    """

    model_config = ConfigDict(extra="ignore")

    patient_id: str
    appointment_id: str
    recommendation_id: Optional[str] = None  # INTERNAL — may be absent post-TTL

    # Workflow A
    new_slot_id: Optional[str] = None

    # Workflow B
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None

    @model_validator(mode="after")
    def _require_slot_or_preference(self) -> "RescheduleRequest":
        has_slot = bool(self.new_slot_id)
        has_preference = bool(self.preferred_date or self.preferred_time)
        if not has_slot and not has_preference:
            raise ValueError(
                "RescheduleRequest requires either new_slot_id "
                "or preferred_date / preferred_time."
            )
        return self


# ---------------------------------------------------------------------------
# Group 7 — Cancellation
# ---------------------------------------------------------------------------

class CancellationRequest(BaseModel):
    """Request to cancel an existing appointment."""

    model_config = ConfigDict(extra="ignore")

    patient_id: str
    appointment_id: str


# ---------------------------------------------------------------------------
# Group 8 — Appointment status response
# ---------------------------------------------------------------------------

class AppointmentStatusResponse(BaseModel):
    """Current status of an appointment, returned by a status-query endpoint.

    Intentionally minimal — only what is needed to display appointment
    status to a patient or care coordinator.
    """

    model_config = ConfigDict(extra="ignore")

    appointment_id: str
    patient_id: str
    status: AppointmentStatusLiteral
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    care_type: Optional[Destination] = None
    slot: Optional[AppointmentSlot] = None
