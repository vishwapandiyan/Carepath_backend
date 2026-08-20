"""
SharedAppointmentAdapter — pure translation layer between this project's
internal appointment models and the external Shared Appointment Agent
HTTP contract.

RESPONSIBILITY
--------------
This module owns ONLY the transformation between internal Python objects
and external JSON dicts.  It contains NO:
  - clinical logic
  - classification
  - ranking
  - recommendation lookup
  - LangGraph or LLM calls
  - business decisions
  - HTTP I/O  (that belongs in appointment/client.py)

EXTERNAL CONTRACT (source: teammate's specification)
-----------------------------------------------------
Request envelope (all operations share this top-level shape):

    {
      "actor": "PATIENT",
      "patient_id": "<string>",
      "request": {
        "intent": "<CHECK_AVAILABILITY|BOOK_APPOINTMENT|
                    RESCHEDULE_APPOINTMENT|CANCEL_APPOINTMENT>",
        <intent-specific fields>
      },
      "patient_context": {            <- optional
        "location": { "latitude": ..., "longitude": ... },
        "preference": { "language": "..." }
      }
    }

Response envelope (all booking/reschedule/cancel operations):

    {
      "patient_id": "<string>",
      "appointment": {
        "appointment_id": "<string>",
        "provider_id":    "<string>",
        "provider_name":  "<string>",
        "specialty":      "<string>",
        "hospital_id":    "<string>",
        "hospital_name":  "<string>",
        "date":           "YYYY-MM-DD",
        "time":           "HH:MM",
        "status":         "BOOKED | RESCHEDULED | CANCELLED"
      }
    }

FIELD-LEVEL DECISIONS (from Step 7B / 8C)
------------------------------------------
CONFIRMED: actor, patient_id, request.intent, request.specialty,
           request.preferred_date, request.preferred_time,
           patient_context.location.{latitude,longitude},
           patient_context.preference.language,
           response.patient_id, response.appointment.*

ASSUMPTION: Reschedule Workflow A uses request.new_slot_id.
            Reschedule/cancel follow the same envelope as book.
            Availability response is {"available_slots": [...]}.
            slot_id defaults to "EXTERNAL_SLOT" when not in response.
            Slot duration defaults to 30 min from date+time.

CONTRACT GAP:
  - No explicit care_type/destination field in external contract.
    -> Adapter omits it entirely.
  - provider_id placement in request not shown in spec.
    -> Adapter omits provider_id from the external request.
  - slot_id in BOOK request not shown in spec.
    -> Adapter omits slot_id from book request.
  - COMPLETED status not confirmed by spec.
  - Status lookup endpoint contract not defined.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any

from models.schemas import AppointmentSlot
from appointment.schemas import (
    AppointmentConfirmation,
    AppointmentPatientContext,
    AppointmentStatusResponse,
)

# Default slot duration (minutes) used when constructing AppointmentSlot
# from the external response's date + time fields.
# ASSUMPTION: 30-minute appointments unless the response supplies end_time.
_DEFAULT_SLOT_DURATION_MINUTES = 30


class SharedAppointmentAdapter:
    """Stateless adapter.  All methods are static — instantiation is not required.

    The only public API surfaces are the ``build_*`` (internal → external)
    and ``parse_*`` (external → internal) static methods.
    """

    # ------------------------------------------------------------------
    # INTERNAL → EXTERNAL  (request builders)
    # ------------------------------------------------------------------

    @staticmethod
    def build_availability_request(
        patient_id: str,
        specialty: Optional[str],
        preferred_date: Optional[str],
        preferred_time: Optional[str],
        date_range: str = "next_7_days",
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> dict:
        """Build the external CHECK_AVAILABILITY payload.

        Parameters
        ----------
        patient_id:
            The patient's identifier.
        specialty:
            Required for SPECIALIST care; None/omitted for PCP,
            URGENT_CARE, TELEHEALTH.
        preferred_date:
            ISO-8601 date preferred by the patient (optional).
        preferred_time:
            Time-of-day preference, e.g. "morning", "10:00" (optional).
        date_range:
            Informational date-range hint, e.g. "next_7_days".
            Included in the request sub-object when present.
        patient_context:
            Optional location + language preference; included when not None.

        Returns
        -------
        dict
            Ready-to-serialise external JSON payload.
        """
        inner: dict = {"intent": "CHECK_AVAILABILITY"}
        # CONFIRMED: specialty present only when supplied
        if specialty:
            inner["specialty"] = specialty
        if preferred_date:
            inner["preferred_date"] = preferred_date
        if preferred_time:
            inner["preferred_time"] = preferred_time
        # date_range is useful context for the external service; include it.
        if date_range:
            inner["date_range"] = date_range

        payload: dict = {
            "actor": "PATIENT",         # CONFIRMED: always PATIENT
            "patient_id": patient_id,   # CONFIRMED: top-level
            "request": inner,
        }
        ctx = SharedAppointmentAdapter._build_patient_context_dict(patient_context)
        if ctx is not None:
            payload["patient_context"] = ctx
        return payload

    @staticmethod
    def build_book_request(
        patient_id: str,
        specialty: Optional[str],
        preferred_date: Optional[str] = None,
        preferred_time: Optional[str] = None,
        patient_context: Optional[AppointmentPatientContext] = None,
    ) -> dict:
        """Build the external BOOK_APPOINTMENT payload.

        CONTRACT DECISIONS:
          - provider_id: NOT included (CONTRACT GAP — placement unconfirmed)
          - slot_id:     NOT included (CONTRACT GAP — not shown in spec)
          - care_type:   NOT included (CONTRACT GAP — no such field in spec)
          - recommendation_id: NEVER forwarded (INTERNAL field)
        """
        inner: dict = {"intent": "BOOK_APPOINTMENT"}
        if specialty:
            inner["specialty"] = specialty
        if preferred_date:
            inner["preferred_date"] = preferred_date
        if preferred_time:
            inner["preferred_time"] = preferred_time

        payload: dict = {
            "actor": "PATIENT",
            "patient_id": patient_id,
            "request": inner,
        }
        ctx = SharedAppointmentAdapter._build_patient_context_dict(patient_context)
        if ctx is not None:
            payload["patient_context"] = ctx
        return payload

    @staticmethod
    def build_reschedule_request(
        patient_id: str,
        appointment_id: str,
        new_slot_id: Optional[str] = None,
        preferred_date: Optional[str] = None,
        preferred_time: Optional[str] = None,
    ) -> dict:
        """Build the external RESCHEDULE_APPOINTMENT payload.

        Supports two workflows:
          Workflow A — direct slot: supply new_slot_id.
            ASSUMPTION: field name "new_slot_id" is used inside request.
          Workflow B — preference-based: supply preferred_date / preferred_time.

        At least one of new_slot_id / preferred_date / preferred_time must
        be present; the caller (RescheduleRequest validator) enforces this
        before reaching the adapter.

        recommendation_id is NEVER forwarded.
        """
        inner: dict = {
            "intent": "RESCHEDULE_APPOINTMENT",
            "appointment_id": appointment_id,
        }
        if new_slot_id:
            # ASSUMPTION: field name confirmed via team convention
            inner["new_slot_id"] = new_slot_id
        if preferred_date:
            inner["preferred_date"] = preferred_date
        if preferred_time:
            inner["preferred_time"] = preferred_time

        return {
            "actor": "PATIENT",
            "patient_id": patient_id,
            "request": inner,
        }

    @staticmethod
    def build_cancel_request(
        patient_id: str,
        appointment_id: str,
    ) -> dict:
        """Build the external CANCEL_APPOINTMENT payload.

        recommendation_id is NEVER forwarded.
        """
        return {
            "actor": "PATIENT",
            "patient_id": patient_id,
            "request": {
                "intent": "CANCEL_APPOINTMENT",
                "appointment_id": appointment_id,
            },
        }

    # ------------------------------------------------------------------
    # EXTERNAL → INTERNAL  (response parsers)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_book_response(
        response_json: dict,
        care_type: Optional[str] = None,
    ) -> AppointmentConfirmation:
        """Parse the external booking response into AppointmentConfirmation.

        Expected shape:
            {
              "patient_id": "...",
              "appointment": {
                "appointment_id": "...",
                "provider_id": "...",
                "provider_name": "...",
                "specialty": "...",
                "hospital_id": "...",
                "hospital_name": "...",
                "date": "YYYY-MM-DD",
                "time": "HH:MM",
                "status": "BOOKED"
              }
            }

        Parameters
        ----------
        response_json:
            Raw JSON dict returned by the external service.
        care_type:
            Internal care-type value derived from the stored CareDecision.
            Carried into the confirmation for the caller's benefit.
            NEVER read from the external response (that field does not exist).

        Raises
        ------
        ValueError
            On missing required fields in the external response.
        """
        SharedAppointmentAdapter._validate_appointment_response(response_json)
        appt = response_json["appointment"]
        patient_id = response_json["patient_id"]

        slot = SharedAppointmentAdapter._build_appointment_slot_from_date_time(
            date=appt["date"],
            time=appt["time"],
            provider_id=appt["provider_id"],
            slot_id=appt.get("slot_id", "EXTERNAL_SLOT"),
        )

        # Normalise external status; the spec confirms BOOKED/RESCHEDULED/CANCELLED.
        # COMPLETED is accepted internally (CONTRACT GAP for external contract).
        status = appt["status"]
        if status not in ("BOOKED", "RESCHEDULED", "CANCELLED", "COMPLETED"):
            # Unknown status — use as-is and let Pydantic validation catch it.
            pass

        return AppointmentConfirmation(
            appointment_id=appt["appointment_id"],
            patient_id=patient_id,
            status=status,
            provider_id=appt["provider_id"],
            provider_name=appt.get("provider_name"),
            care_type=care_type,                # from internal CareDecision — not external
            specialty=appt.get("specialty"),
            hospital_id=appt.get("hospital_id"),
            hospital_name=appt.get("hospital_name"),
            slot=slot,
            date=appt.get("date"),
            time=appt.get("time"),
        )

    @staticmethod
    def parse_reschedule_response(
        response_json: dict,
    ) -> AppointmentConfirmation:
        """Parse the external reschedule response.

        ASSUMPTION: same envelope shape as booking response, status=RESCHEDULED.
        """
        SharedAppointmentAdapter._validate_appointment_response(response_json)
        return SharedAppointmentAdapter.parse_book_response(response_json)

    @staticmethod
    def parse_cancel_response(
        response_json: dict,
    ) -> AppointmentStatusResponse:
        """Parse the external cancellation response into AppointmentStatusResponse.

        ASSUMPTION: same envelope shape as booking response, status=CANCELLED.
        Handles both the nested appointment envelope and a flat response
        (e.g. { appointment_id, patient_id, status }) gracefully.
        """
        # The spec shows a nested envelope for booking; we assume cancellation
        # follows the same pattern. But if the external service returns a flat
        # response for cancel, handle that too.
        if "appointment" in response_json:
            appt = response_json["appointment"]
            patient_id = response_json.get("patient_id", "")
            slot_raw = appt.get("slot")
            slot = None
            if slot_raw:
                slot = AppointmentSlot(**slot_raw)
            elif appt.get("date") and appt.get("time"):
                slot = SharedAppointmentAdapter._build_appointment_slot_from_date_time(
                    date=appt["date"],
                    time=appt["time"],
                    provider_id=appt.get("provider_id", ""),
                )
            return AppointmentStatusResponse(
                appointment_id=appt.get("appointment_id", ""),
                patient_id=patient_id,
                status=appt.get("status", "CANCELLED"),
                provider_id=appt.get("provider_id"),
                provider_name=appt.get("provider_name"),
                slot=slot,
            )
        else:
            # Flat response shape (alternative format)
            return AppointmentStatusResponse(**response_json)

    @staticmethod
    def parse_availability_response(
        response_json: dict,
    ) -> List[AppointmentSlot]:
        """Parse the availability response into a list of AppointmentSlot objects.

        ASSUMPTION: response shape is {"available_slots": [...]}.
        Each slot must contain at minimum slot_id, provider_id,
        start_time, end_time.
        """
        slots_raw = response_json.get("available_slots", [])
        if not isinstance(slots_raw, list):
            raise ValueError(
                f"availability response 'available_slots' must be a list; "
                f"got {type(slots_raw).__name__}"
            )
        result: List[AppointmentSlot] = []
        for i, s in enumerate(slots_raw):
            if not isinstance(s, dict):
                raise ValueError(
                    f"availability response slot[{i}] must be a dict; "
                    f"got {type(s).__name__}"
                )
            try:
                result.append(AppointmentSlot(**s))
            except Exception as exc:
                raise ValueError(
                    f"availability response slot[{i}] is malformed: {exc}"
                ) from exc
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_patient_context_dict(
        ctx: Optional[AppointmentPatientContext],
    ) -> Optional[dict]:
        """Convert AppointmentPatientContext into the external JSON structure.

        Returns None when ctx is None or carries no meaningful data,
        so the caller can omit patient_context rather than sending nulls.
        """
        if ctx is None:
            return None

        location: Optional[dict] = None
        if ctx.latitude is not None and ctx.longitude is not None:
            location = {"latitude": ctx.latitude, "longitude": ctx.longitude}

        preference: Optional[dict] = None
        if ctx.preferences and ctx.preferences.language:
            preference = {"language": ctx.preferences.language}

        if location is None and preference is None:
            return None     # nothing meaningful to send

        result: dict = {}
        if location is not None:
            result["location"] = location
        if preference is not None:
            result["preference"] = preference
        return result

    @staticmethod
    def _build_appointment_slot_from_date_time(
        date: str,
        time: str,
        provider_id: str,
        slot_id: str = "EXTERNAL_SLOT",
    ) -> AppointmentSlot:
        """Construct an AppointmentSlot from external date + time strings.

        ASSUMPTION: slot_id defaults to "EXTERNAL_SLOT" when not returned.
        ASSUMPTION: slot duration defaults to 30 minutes.

        start_time and end_time are plain strings to match the existing
        AppointmentSlot schema convention (no datetime parsing).
        """
        # Parse HH:MM to compute end_time (plain string arithmetic)
        start_time = f"{date}T{time}:00"
        try:
            h, m = (int(x) for x in time.split(":")[:2])
            total = h * 60 + m + _DEFAULT_SLOT_DURATION_MINUTES
            end_h, end_m = divmod(total, 60)
            end_time = f"{date}T{end_h:02d}:{end_m:02d}:00"
        except (ValueError, AttributeError):
            # Malformed time string — use start_time as end_time rather than
            # crashing; caller can detect end == start if needed.
            end_time = start_time

        return AppointmentSlot(
            slot_id=slot_id,
            provider_id=provider_id,
            start_time=start_time,
            end_time=end_time,
        )

    @staticmethod
    def _validate_appointment_response(response_json: dict) -> None:
        """Validate the external booking/reschedule response envelope.

        Raises ValueError with a descriptive message on any missing field.
        """
        required_top = ("patient_id", "appointment")
        for field in required_top:
            if field not in response_json:
                raise ValueError(
                    f"External Appointment Agent response is missing required "
                    f"top-level field: '{field}'. "
                    f"Got keys: {list(response_json.keys())}"
                )

        appt = response_json["appointment"]
        if not isinstance(appt, dict):
            raise ValueError(
                f"External response 'appointment' must be a dict; "
                f"got {type(appt).__name__}"
            )

        required_appt = ("appointment_id", "provider_id", "date", "time", "status")
        for field in required_appt:
            if field not in appt:
                raise ValueError(
                    f"External Appointment Agent response 'appointment' object "
                    f"is missing required field: '{field}'. "
                    f"Got keys: {list(appt.keys())}"
                )
