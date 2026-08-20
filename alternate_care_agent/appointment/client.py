"""
Thin HTTP client for the SHARED Appointment Agent.

This module is responsible for HTTP I/O ONLY.
All request serialisation and response deserialisation is handled by:
    appointment/adapter.py  (SharedAppointmentAdapter)

External contract (as confirmed by the teammate's specification):

    POST /appointments/availability
        request:  SharedAppointmentAdapter.build_availability_request()
        response: {"available_slots": [{slot_id, provider_id, start_time, end_time}]}

    POST /appointments/book
        request:  SharedAppointmentAdapter.build_book_request()
        response: {"patient_id": "...", "appointment": {appointment_id, provider_id,
                   provider_name, specialty, hospital_id, hospital_name,
                   date, time, status}}

    POST /appointments/cancel
        request:  SharedAppointmentAdapter.build_cancel_request()
        response: same nested appointment envelope, status=CANCELLED

    POST /appointments/reschedule
        request:  SharedAppointmentAdapter.build_reschedule_request()
        response: same nested appointment envelope, status=RESCHEDULED

    GET /appointments/{appointment_id}?patient_id=...
        response: {appointment_id, patient_id, status, ...}
        CONTRACT GAP: exact shape not confirmed in spec.

Backward compatibility
----------------------
The legacy ``cancel(appointment_id: str) -> dict`` method is preserved
so existing callers that use it directly are not broken.  New code should
use ``cancel_appointment(CancellationRequest)``.
"""

from __future__ import annotations

from typing import List, Optional

import requests

from models.schemas import AppointmentSlot, BookingRequest, BookingConfirmation
from appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentStatusResponse,
    CancellationRequest,
    RescheduleRequest,
)
from appointment.adapter import SharedAppointmentAdapter
from config.settings import APPOINTMENT_AGENT_BASE_URL

TIMEOUT_SECONDS = 10


class AppointmentAgentClient:
    def __init__(self, base_url: str = APPOINTMENT_AGENT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # CHECK_AVAILABILITY
    # ------------------------------------------------------------------

    def get_availability(
        self,
        provider_id: str,
        care_type: str,
        specialty: Optional[str],
        date_range: str = "next_7_days",
        patient_id: Optional[str] = None,
        preferred_date: Optional[str] = None,
        preferred_time: Optional[str] = None,
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> List[AppointmentSlot]:
        """Request available appointment slots from the external service.

        The external payload is built by SharedAppointmentAdapter and uses
        the confirmed envelope: {actor, patient_id, request:{intent,...},
        patient_context?}.

        Parameters
        ----------
        provider_id:
            Internal identifier of the selected provider (NOT sent to the
            external service — CONTRACT GAP: placement unconfirmed in spec).
        care_type:
            Internal routing value derived from CareDecision.  NOT forwarded
            externally (CONTRACT GAP: no such field in spec).
        specialty:
            Forwarded inside request when non-None (SPECIALIST only).
        date_range:
            Scheduling hint included in the request sub-object.
        patient_id:
            Forwarded as top-level patient_id when supplied.
        preferred_date, preferred_time:
            Optional scheduling preferences.
        patient_context:
            Optional location + language; included when not None.
        """
        payload = SharedAppointmentAdapter.build_availability_request(
            patient_id=patient_id or "",
            specialty=specialty,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            date_range=date_range,
            patient_context=patient_context,
        )
        resp = requests.post(
            f"{self.base_url}/appointments/availability",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return SharedAppointmentAdapter.parse_availability_response(resp.json())

    # ------------------------------------------------------------------
    # BOOK_APPOINTMENT
    # ------------------------------------------------------------------

    def book(
        self,
        request: BookingRequest,
        specialty: Optional[str] = None,
        preferred_date: Optional[str] = None,
        preferred_time: Optional[str] = None,
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> BookingConfirmation:
        """Book an appointment through the external Shared Appointment Agent.

        The external payload is built by SharedAppointmentAdapter:
            {actor, patient_id, request:{intent, specialty?, preferred_date?,
             preferred_time?}, patient_context?}

        Critically:
          - recommendation_id is NEVER forwarded (INTERNAL field).
          - provider_id is NOT in the external request (CONTRACT GAP).
          - slot_id is NOT in the external request (CONTRACT GAP).
          - care_type/destination is NOT in the external request (CONTRACT GAP).

        The raw external response is parsed by the adapter, which reads the
        nested "appointment" envelope.  The result is then converted to the
        legacy BookingConfirmation for backward compatibility with existing
        callers (api/routes.py POST /appointments/book).

        Parameters
        ----------
        request:
            Internal BookingRequest (patient_id, recommendation_id,
            provider_id, slot_id).  recommendation_id is stripped here.
        specialty:
            Derived from the stored CareDecision by the service/route layer.
        preferred_date, preferred_time:
            Optional scheduling preferences.
        patient_context:
            Optional patient location + language.
        """
        payload = SharedAppointmentAdapter.build_book_request(
            patient_id=request.patient_id,
            specialty=specialty,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            patient_context=patient_context,
        )
        resp = requests.post(
            f"{self.base_url}/appointments/book",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()

        # Parse via adapter (handles the nested "appointment" envelope)
        confirmation: AppointmentConfirmation = (
            SharedAppointmentAdapter.parse_book_response(resp.json())
        )

        # Convert to legacy BookingConfirmation so existing routes continue
        # to work without modification.
        return BookingConfirmation(
            appointment_id=confirmation.appointment_id,
            status=confirmation.status,
            provider_id=confirmation.provider_id,
            slot=confirmation.slot,
        )

    # ------------------------------------------------------------------
    # CANCEL (legacy — backward compat)
    # ------------------------------------------------------------------

    def cancel(self, appointment_id: str) -> dict:
        """Legacy cancel method — preserved for backward compatibility.

        New code should use cancel_appointment(CancellationRequest) instead.
        This variant sends only appointment_id (no patient_id), which is
        the pre-adapter flat payload.
        """
        resp = requests.post(
            f"{self.base_url}/appointments/cancel",
            json={"appointment_id": appointment_id},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # CANCEL (typed — uses adapter)
    # ------------------------------------------------------------------

    def cancel_appointment(
        self,
        request: CancellationRequest,
    ) -> AppointmentStatusResponse:
        """Cancel an appointment, forwarding patient_id and appointment_id.

        External payload (via adapter):
            {actor, patient_id, request:{intent:CANCEL_APPOINTMENT,
             appointment_id}}
        """
        payload = SharedAppointmentAdapter.build_cancel_request(
            patient_id=request.patient_id,
            appointment_id=request.appointment_id,
        )
        resp = requests.post(
            f"{self.base_url}/appointments/cancel",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return SharedAppointmentAdapter.parse_cancel_response(resp.json())

    # ------------------------------------------------------------------
    # RESCHEDULE
    # ------------------------------------------------------------------

    def reschedule(
        self,
        request: RescheduleRequest,
    ) -> AppointmentConfirmation:
        """Reschedule an existing appointment.

        Workflow A — new_slot_id supplied:
            ASSUMPTION: "new_slot_id" is the accepted field name.
        Workflow B — preferred_date / preferred_time supplied.

        recommendation_id is NEVER forwarded.

        External payload (via adapter):
            {actor, patient_id, request:{intent:RESCHEDULE_APPOINTMENT,
             appointment_id, new_slot_id? | preferred_date? + preferred_time?}}
        """
        payload = SharedAppointmentAdapter.build_reschedule_request(
            patient_id=request.patient_id,
            appointment_id=request.appointment_id,
            new_slot_id=request.new_slot_id,
            preferred_date=request.preferred_date,
            preferred_time=request.preferred_time,
        )
        resp = requests.post(
            f"{self.base_url}/appointments/reschedule",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return SharedAppointmentAdapter.parse_reschedule_response(resp.json())

    # ------------------------------------------------------------------
    # GET APPOINTMENT STATUS
    # ------------------------------------------------------------------

    def get_appointment(
        self,
        appointment_id: str,
        patient_id: Optional[str] = None,
    ) -> AppointmentStatusResponse:
        """Retrieve the current status of an appointment.

        CONTRACT GAP: Exact status lookup endpoint contract is not confirmed
        in the specification.  Uses GET /appointments/{id}?patient_id=... as
        an ASSUMPTION.

        No envelope adapter is applied here — the response shape for this
        endpoint is unspecified; parse_cancel_response handles both flat and
        nested shapes when called.
        """
        params: dict = {}
        if patient_id:
            params["patient_id"] = patient_id

        resp = requests.get(
            f"{self.base_url}/appointments/{appointment_id}",
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        # Use the flexible cancel parser which handles both flat and nested shapes.
        return SharedAppointmentAdapter.parse_cancel_response(resp.json())
