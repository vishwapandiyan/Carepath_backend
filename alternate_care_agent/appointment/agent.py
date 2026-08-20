"""
AppointmentService — the service layer between api/routes.py and
AppointmentAgentClient.

Responsibilities
----------------
- Wraps AppointmentAgentClient (the thin HTTP client).
- For operations that originate from the navigation workflow
  (check_availability, book_appointment), it enforces the
  recommendation-binding contract via RecommendationStore.
- For post-booking operations (reschedule, cancel, status) it does NOT
  require a live recommendation — those can legitimately happen after the
  30-min recommendation TTL expires.
- Derives care_type and specialty from the stored CareDecision; never
  trusts those values from the caller.
- Does NOT contain clinical logic, routing rules, or classification.

This class is NOT the external Appointment Agent — it is the service
layer in THIS project that mediates between our API and that external
service.  The external service is unreachable without a running
APPOINTMENT_AGENT_BASE_URL endpoint; in tests, AppointmentAgentClient
methods are mocked at the instance level.

Architecture position
---------------------
    api/routes.py
        │
        ▼
    AppointmentService        ← this file
        │
        ▼
    AppointmentAgentClient    ← appointment/client.py  (thin HTTP)
        │
        ▼
    External Appointment Agent  (teammate's service)
"""

from __future__ import annotations

from typing import List, Optional

from models.schemas import (
    AppointmentSlot,
    BookingConfirmation,
    BookingRequest,
)
from appointment.client import AppointmentAgentClient
from appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentStatusLiteral,
    AppointmentStatusResponse,
    AvailabilityWorkflowRequest,
    AvailabilityWorkflowResponse,
    BookingWorkflowRequest,
    CancellationRequest,
    RescheduleRequest,
)
from config.settings import APPOINTMENT_AGENT_BASE_URL


class AppointmentService:
    """Service layer mediating between our FastAPI routes and the external
    Appointment Agent.

    Instantiated once at module level (``appointment_service``) and imported
    by ``api/routes.py``.  All AppointmentAgentClient I/O goes through here.

    Parameters
    ----------
    client:
        Optional pre-constructed client; if None, a default client pointing
        at ``APPOINTMENT_AGENT_BASE_URL`` is created.  Pass a custom client
        in tests to avoid live HTTP.
    """

    def __init__(self, client: Optional[AppointmentAgentClient] = None) -> None:
        self._client = client or AppointmentAgentClient()

    # ------------------------------------------------------------------
    # CHECK_AVAILABILITY
    # ------------------------------------------------------------------

    def check_availability(
        self,
        request: AvailabilityWorkflowRequest,
    ) -> AvailabilityWorkflowResponse:
        """Return available slots for a validated provider/care-type combination.

        ``care_type`` and ``specialty`` are taken from ``request``, which the
        route layer must have already derived from the stored CareDecision.
        No clinical derivation happens here.

        Parameters
        ----------
        request:
            Availability request with server-derived care_type/specialty.

        Returns
        -------
        AvailabilityWorkflowResponse
            Slots list plus echo fields for the caller.
        """
        slots: List[AppointmentSlot] = self._client.get_availability(
            provider_id=request.provider_id,
            care_type=request.care_type,
            specialty=request.specialty,
            date_range=request.date_range,
        )
        return AvailabilityWorkflowResponse(
            available_slots=slots,
            provider_id=request.provider_id,
            care_type=request.care_type,
        )

    # ------------------------------------------------------------------
    # BOOK_APPOINTMENT
    # ------------------------------------------------------------------

    def book_appointment(
        self,
        request: BookingWorkflowRequest,
        care_type: Optional[str] = None,
        specialty: Optional[str] = None,
        provider_name: Optional[str] = None,
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> AppointmentConfirmation:
        """Book an appointment for a validated provider.

        Converts the internal ``BookingWorkflowRequest`` to the external
        ``BookingRequest`` (which excludes recommendation_id), calls the
        client, then up-casts the minimal ``BookingConfirmation`` response
        to the richer ``AppointmentConfirmation`` using the care-context
        values derived by the route layer.

        Parameters
        ----------
        request:
            Internal booking request (includes recommendation_id for
            audit/logging; stripped before the external HTTP call).
        care_type:
            Value derived by the route from the stored CareDecision.
            Carried into the confirmation for the caller's benefit.
        specialty:
            Value derived by the route from the stored CareDecision.
        provider_name:
            Optional display name from the stored ProviderCandidate.
        patient_context:
            Optional patient location reconstructed from the persisted
            PatientLocation in RecommendationStore.  Forwarded to the
            external Appointment Agent as patient_context.
        """
        # Build the external-facing BookingRequest (recommendation_id present
        # for internal audit; stripped to {patient_id, provider_id, slot_id}
        # by AppointmentAgentClient.book()).
        external_request = BookingRequest(
            patient_id=request.patient_id,
            recommendation_id=request.recommendation_id,
            provider_id=request.provider_id,
            slot_id=request.slot_id,
        )
        confirmation: BookingConfirmation = self._client.book(
            external_request,
            specialty=specialty,
            patient_context=patient_context,
        )

        return AppointmentConfirmation(
            appointment_id=confirmation.appointment_id,
            patient_id=request.patient_id,
            status="BOOKED",
            provider_id=confirmation.provider_id,
            provider_name=provider_name,
            care_type=care_type,
            specialty=specialty,
            slot=confirmation.slot,
            date=confirmation.slot.start_time[:10] if confirmation.slot else None,
            time=confirmation.slot.start_time[11:16] if confirmation.slot else None,
        )

    # ------------------------------------------------------------------
    # RESCHEDULE_APPOINTMENT
    # ------------------------------------------------------------------

    def reschedule_appointment(
        self,
        request: RescheduleRequest,
    ) -> AppointmentConfirmation:
        """Reschedule an existing appointment.

        Supports two workflows:
          A) ``new_slot_id`` supplied — direct reschedule.
          B) ``preferred_date`` / ``preferred_time`` supplied — the external
             agent finds the best matching slot and reschedules.

        ``recommendation_id`` is NOT required here because reschedules may
        occur after the 30-min RecommendationStore TTL expires.

        The patient/appointment relationship is the trust boundary for this
        operation, not the recommendation binding.

        Parameters
        ----------
        request:
            RescheduleRequest with appointment_id + either new_slot_id or
            preferred_date/preferred_time.

        Returns
        -------
        AppointmentConfirmation
            Rescheduled appointment confirmation with status RESCHEDULED.
        """
        confirmation: AppointmentConfirmation = self._client.reschedule(request)
        return confirmation

    # ------------------------------------------------------------------
    # CANCEL_APPOINTMENT
    # ------------------------------------------------------------------

    def cancel_appointment(
        self,
        request: CancellationRequest,
    ) -> AppointmentStatusResponse:
        """Cancel an existing appointment.

        The patient_id is sent to the external service so it can validate
        the patient/appointment relationship on its side.

        Parameters
        ----------
        request:
            CancellationRequest with patient_id and appointment_id.

        Returns
        -------
        AppointmentStatusResponse
            Cancellation status from the external service.
        """
        result: AppointmentStatusResponse = self._client.cancel_appointment(request)
        return result

    # ------------------------------------------------------------------
    # GET APPOINTMENT STATUS
    # ------------------------------------------------------------------

    def get_appointment_status(
        self,
        appointment_id: str,
        patient_id: Optional[str] = None,
    ) -> AppointmentStatusResponse:
        """Retrieve the current status of an appointment.

        Parameters
        ----------
        appointment_id:
            The ID of the appointment to query.
        patient_id:
            Optional patient identifier for caller context.

        Returns
        -------
        AppointmentStatusResponse
            Current appointment status.
        """
        return self._client.get_appointment(
            appointment_id=appointment_id,
            patient_id=patient_id,
        )


# Module-level singleton used by api/routes.py.
# Tests that need a custom client should patch this or construct a fresh
# AppointmentService(client=mock_client).
appointment_service = AppointmentService()
