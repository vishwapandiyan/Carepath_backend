"""
Appointment Agent — nearby provider search (Step 1 of the appointment
agentic build-out).

Scope of this step (ONLY)
--------------------------
This file currently implements exactly one capability: nearby healthcare
PROVIDER SEARCH for the Appointment Agent, using the database as the
primary source of provider data.

Explicitly OUT OF SCOPE here (not implemented in this step):
  - Appointment availability lookup (POST /appointments/availability)
  - Appointment booking (POST /appointments/book)
  - Any change to agents/navigation_agent.py, agents/tools/navigation_tools.py,
    or the rule-based /navigate pipeline. Those are untouched by this file.

Database-first approach
-----------------------
Provider search now queries the appointment_providers table directly
instead of calling external APIs. This ensures reliable, fast provider
lookup with controlled data quality.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.services.alternate_care.location.ranking import haversine_km
from app.services.alternate_care.models.schemas import ProviderCandidate

from app.services.alternate_care.appointment.client import AppointmentAgentClient  # noqa: F401
from app.services.alternate_care.llm.nvidia_client import ChatMessage, NvidiaClient, NvidiaClientError

logger = logging.getLogger(__name__)


# Presentation-only label for the "type" field in this tool's output.
# Does NOT affect the underlying OSM query — that mapping lives in
# location/osm_tag_map.py and is untouched here.
_DESTINATION_TYPE_LABEL: Dict[str, str] = {
    "PCP": "clinic",
    "URGENT_CARE": "urgent_care",
    "SPECIALIST": "specialist_clinic",
    "DENTISTRY": "dentist",
    "TELEHEALTH": "telehealth",
}


# ===========================================================================
# Provider search tool
# ===========================================================================

def search_nearby_providers(
    latitude: float,
    longitude: float,
    destination: str,
    specialty: Optional[str] = None,
    radius_km: float = 15.0,
) -> Dict[str, Any]:
    """Search the database for nearby healthcare providers matching a care
    destination, and compute each provider's distance from the patient.

    This purely answers "which facilities exist in our system for
    this type of care?". It does NOT check appointment availability and
    does NOT book anything.

    Parameters
    ----------
    latitude : float
        Patient latitude in decimal degrees (e.g. from the navigation
        recommendation's patient location).
    longitude : float
        Patient longitude in decimal degrees.
    destination : str
        Care destination, e.g. "PCP", "URGENT_CARE", "SPECIALIST",
        "DENTISTRY". Should come from the navigation recommendation's
        decision.destination field. "TELEHEALTH" returns an empty list —
        telehealth has no physical location.
    specialty : str | None
        Specialist sub-type (e.g. "CARDIOLOGY"). Only meaningful when
        destination == "SPECIALIST".
    radius_km : float
        Search radius in kilometres. Default 15.0. (Note: currently not
        used in database query but kept for API compatibility)

    Returns (success, providers found)
    -----------------------------------
    {
        "ok": True,
        "count": int,
        "providers": [
            {
                "provider_id": str,     # e.g. "osm:node:test001"
                "provider_name": str,
                "facility_name": str,
                "type": str,            # e.g. "clinic", "urgent_care", "dentist"
                "address": str | None,
                "latitude": float,
                "longitude": float,
                "distance_km": float,
            },
            ...
        ],
    }
    Sorted ascending by distance_km (nearest first).

    Returns (success, no results)
    ------------------------------
    {
        "ok": True,
        "count": 0,
        "providers": [],
        "message": "No providers available in the system for <destination>."
    }

    Returns (failure)
    ------------------
    {
        "ok": False,
        "error": "<descriptive message>"
    }

    Failure cases
    -------------
    - Invalid destination value → ValueError → error envelope
    - Database connection error → error envelope
    - No providers in database for destination → empty list with message
    """
    # Radius expansion sequence for SPECIALIST searches.
    # If no verified specialist providers are found at the requested radius,
    # automatically expand to wider radii before giving up.
    _SPECIALIST_EXPANSION_RADII = [25.0, 50.0]
    _MAX_SPECIALIST_RESULTS = 3

    try:
        # Determine radii to search. For SPECIALIST, expand if needed.
        if destination == "SPECIALIST" and specialty:
            radii_to_try = [radius_km] + [
                r for r in _SPECIALIST_EXPANSION_RADII if r > radius_km
            ]
        else:
            radii_to_try = [radius_km]

        candidates: List[ProviderCandidate] = []
        effective_radius_km = radius_km
        used_database_fallback = False

        for search_radius in radii_to_try:
            # Use database as primary source instead of Overpass API
            logger.info(
                "search_nearby_providers: fetching providers from database for %s",
                destination,
            )
            try:
                # Use psycopg2 (synchronous) to avoid async context issues
                import psycopg2
                from psycopg2.extras import RealDictCursor
                from app.config import settings
                
                # Get database URL and convert from async to sync format
                db_url = settings.DATABASE_URL
                if 'postgresql+asyncpg://' in db_url:
                    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
                
                # Connect using psycopg2 (synchronous)
                conn = psycopg2.connect(db_url)
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                try:
                    # Fetch providers from database that match the destination type
                    cursor.execute("""
                        SELECT provider_id, provider_name, destination, specialty, 
                               address, latitude, longitude
                        FROM appointment_providers
                        WHERE destination = %s
                        ORDER BY provider_id
                        LIMIT 10
                    """, (destination.upper(),))
                    
                    db_providers = cursor.fetchall()
                    
                    if db_providers:
                        candidates = []
                        for row in db_providers:
                            # Calculate distance from patient location
                            dist_km = haversine_km(latitude, longitude, row['latitude'], row['longitude'])
                            candidates.append(ProviderCandidate(
                                provider_id=row['provider_id'],
                                name=row['provider_name'],
                                destination_type=destination,  # type: ignore[arg-type]
                                specialty=row['specialty'],
                                latitude=row['latitude'],
                                longitude=row['longitude'],
                                address=row['address'],
                                distance_km=round(dist_km, 2),
                                source="database",
                            ))
                        used_database_fallback = True
                        logger.info(
                            "search_nearby_providers: loaded %d providers from database for %s",
                            len(candidates), destination,
                        )
                        break
                    else:
                        logger.error("No providers found in database for destination: %s", destination)
                        raise ValueError(f"No providers available for {destination}")
                finally:
                    cursor.close()
                    conn.close()
                    
            except Exception as db_exc:
                logger.error("Failed to fetch providers from database: %s", db_exc, exc_info=True)
                raise ValueError(f"Provider search failed: {db_exc}") from db_exc

            effective_radius_km = search_radius

            if candidates:
                logger.info(
                    "search_nearby_providers: found %d providers from database "
                    "(destination=%s specialty=%s)",
                    len(candidates), destination, specialty,
                )
                break

        if not candidates:
            logger.info(
                "search_nearby_providers: no providers in database for destination=%s "
                "specialty=%s",
                destination, specialty,
            )
            msg = (
                f"No {specialty.lower() + ' ' if specialty else ''}"
                f"providers available in the system."
            ) if destination == "SPECIALIST" and specialty else (
                f"No providers available in the system for destination={destination}."
            )
            return {
                "ok": True,
                "count": 0,
                "providers": [],
                "search_radius_km": effective_radius_km,
                "requested_radius_km": radius_km,
                "message": msg,
            }

        type_label = _DESTINATION_TYPE_LABEL.get(destination, "healthcare_facility")

        providers: List[Dict[str, Any]] = []
        for c in candidates:
            distance_km = round(
                haversine_km(latitude, longitude, c.latitude, c.longitude), 2
            )
            providers.append(
                {
                    "provider_id": c.provider_id,
                    "provider_name": c.name,
                    "facility_name": c.name,
                    "type": type_label,
                    "address": c.address,
                    "latitude": c.latitude,
                    "longitude": c.longitude,
                    "distance_km": distance_km,
                }
            )

        # Sort by distance ascending — nearest facility first.
        providers.sort(key=lambda p: p["distance_km"])

        # Cap SPECIALIST results at _MAX_SPECIALIST_RESULTS
        if destination == "SPECIALIST" and specialty:
            providers = providers[:_MAX_SPECIALIST_RESULTS]

        logger.info(
            "search_nearby_providers: destination=%s specialty=%s -> %d providers from database "
            "(nearest=%.2fkm)",
            destination, specialty, len(providers), providers[0]["distance_km"],
        )

        return {
            "ok": True,
            "count": len(providers),
            "providers": providers,
            "search_radius_km": effective_radius_km,
            "requested_radius_km": radius_km,
        }

    except ValueError as exc:
        logger.warning("search_nearby_providers failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("search_nearby_providers unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ===========================================================================
# OpenAI/NVIDIA-compatible tool definition
# ===========================================================================
# Makes search_nearby_providers callable by the Appointment Agent's future
# LLM tool-calling loop. Deliberately kept in its own registry, separate
# from agents/tools/navigation_tools.py, so the navigation agent's tool set
# (ALL_TOOLS / _TOOL_REGISTRY) is completely untouched by this step.

PROVIDER_SEARCH_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_nearby_providers",
        "description": (
            "Search the database for nearby healthcare provider "
            "facilities (clinics, doctors' offices, urgent care centers, "
            "dentists) matching a care destination, sorted by distance from "
            "the patient. Does NOT check appointment availability and does "
            "NOT book anything -- this only answers 'which facilities exist "
            "nearby for this type of care'. Use the destination/specialty "
            "from the navigation recommendation and the patient's coordinates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Patient latitude in decimal degrees.",
                },
                "longitude": {
                    "type": "number",
                    "description": "Patient longitude in decimal degrees.",
                },
                "destination": {
                    "type": "string",
                    "enum": ["PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH", "DENTISTRY"],
                    "description": (
                        "Care destination from the navigation recommendation "
                        "(decision.destination)."
                    ),
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "Specialist sub-type, required only when destination "
                        "is SPECIALIST (e.g. 'CARDIOLOGY')."
                    ),
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometres. Default 15.0.",
                },
            },
            "required": ["latitude", "longitude", "destination"],
        },
    },
}


# ===========================================================================
# Provider selection tool
# ===========================================================================
# Step 3 (persistence build-out): lets the LLM record which provider the
# patient chose, using the exact provider_id/provider_name from the list
# already presented (from search_nearby_providers). This keeps provider
# selection agentic — the LLM decides to call this tool and supplies the
# arguments after reasoning over the patient's free-text message and the
# provider list in its own context. No string-matching / hard-coded
# "if message == ..." logic is used anywhere in this flow.

def select_provider(provider_id: str, provider_name: str) -> Dict[str, Any]:
    """Record the provider the patient selected from a previously shown list.

    This tool does NOT search for or validate providers on its own — the
    caller (run_appointment_agent) cross-checks provider_id against the
    known provider list and rejects the call if it does not match, so the
    LLM must ground its selection in the real search results rather than
    inventing a provider_id.

    Returns
    -------
    {"ok": True, "provider_id": str, "provider_name": str}
    """
    return {"ok": True, "provider_id": provider_id, "provider_name": provider_name}


# ===========================================================================
# Availability checking tool
# ===========================================================================
# Step 4 (agentic availability): lets the LLM autonomously check availability
# for the selected provider by calling the existing external appointment
# availability service. The LLM decides when to call this based on the
# patient's message (e.g. "Show me available appointments").

def check_availability(
    provider_id: str,
    destination: str,
    specialty: Optional[str] = None,
    patient_id: Optional[str] = None,
    preferred_date: Optional[str] = None,
    preferred_time: Optional[str] = None,
    date_range: str = "next_7_days",
) -> Dict[str, Any]:
    """Check available appointment slots for a selected provider.

    MODIFIED: Now queries the local PostgreSQL database directly using
    psycopg2 (synchronous) instead of calling an external HTTP service.

    Parameters
    ----------
    provider_id : str
        The selected provider's ID (e.g. 'osm:node:9004757918').
    destination : str
        Care destination from the navigation recommendation.
    specialty : str | None
        Specialist sub-type when applicable.
    patient_id : str | None
        Patient identifier (MRN).
    preferred_date : str | None
        Preferred date (ISO-8601, e.g. '2026-08-25').
    preferred_time : str | None
        Preferred time (e.g. '09:00' or 'morning').
    date_range : str
        Date range hint (e.g. 'next_7_days'). Default 'next_7_days'.

    Returns (success)
    -------------------
    {
        "ok": True,
        "count": int,
        "slots": [
            {
                "slot_id": str,
                "provider_id": str,
                "start_time": str,  # ISO-8601
                "end_time": str,    # ISO-8601
            },
            ...
        ]
    }

    Returns (failure)
    ------------------
    {
        "ok": False,
        "error": "<descriptive message>"
    }
    """
    try:
        # Use psycopg2 (synchronous) to avoid event loop issues
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from datetime import datetime, timedelta
        
        # Get database URL from config
        from app.config import settings
        
        # Parse the async URL to get connection params
        db_url = settings.DATABASE_URL
        # Remove the async driver prefix
        if 'postgresql+asyncpg://' in db_url:
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        # Connect using psycopg2
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Build date filter based on date_range
            now = datetime.now()
            if date_range == "next_7_days":
                end_date = now + timedelta(days=7)
            elif date_range == "next_30_days":
                end_date = now + timedelta(days=30)
            else:
                end_date = now + timedelta(days=7)  # default
            
            # Query available slots
            cursor.execute("""
                SELECT slot_id, provider_id, start_time, end_time
                FROM provider_slots
                WHERE provider_id = %s 
                  AND status = 'AVAILABLE'
                  AND start_time >= %s
                  AND start_time <= %s
                ORDER BY start_time
                LIMIT 20
            """, (provider_id, now, end_date))
            
            rows = cursor.fetchall()
            
            # Convert to list of dicts
            slots = []
            for row in rows:
                slots.append({
                    "slot_id": row['slot_id'],
                    "provider_id": row['provider_id'],
                    "start_time": row['start_time'].isoformat(),
                    "end_time": row['end_time'].isoformat(),
                })
            
        finally:
            cursor.close()
            conn.close()

        logger.info(
            "check_availability: fetched %d slots for provider=%s destination=%s",
            len(slots), provider_id, destination,
        )
        
        # Build tool result
        tool_result = {
            "ok": True,
            "count": len(slots),
            "slots": slots,
        }
        logger.info("check_availability tool_result:")
        logger.info("  ok=%s count=%s", tool_result.get("ok"), tool_result.get("count"))
        if slots:
            logger.info("  First slot: %s", slots[0])

        return tool_result

    except Exception as exc:
        logger.warning("check_availability: database error: %s", exc)
        import traceback
        logger.warning("Traceback: %s", traceback.format_exc())
        return {
            "ok": False,
            "error": f"Database error: {str(exc)}",
        }


# ===========================================================================
# Slot selection tool
# ===========================================================================
# Step 4 (slot selection): lets the LLM record which appointment slot the
# patient chose from the list already returned by check_availability. This
# tool does NOT book anything — it only records the patient's choice so a
# later, separate booking step can act on it. Grounding against the known
# slot list (so the LLM cannot invent a slot_id) is enforced by the caller
# (the tool-calling loop), the same pattern used for select_provider.

def select_slot(slot_id: str) -> Dict[str, Any]:
    """Record the appointment slot the patient selected from a previously
    shown list of available slots.

    This tool does NOT validate the slot_id against the known slot list on
    its own — the caller (the tool-calling loop) cross-checks slot_id
    against the available_slots already returned by check_availability and
    rejects the call if it does not match, so the LLM must ground its
    selection in the real availability results rather than inventing a
    slot_id.

    Returns
    -------
    {"ok": True, "slot_id": str}
    """
    return {"ok": True, "slot_id": slot_id}


SELECT_PROVIDER_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "select_provider",
        "description": (
            "Record the patient's selected healthcare provider from the "
            "list of nearby providers already returned by "
            "search_nearby_providers. Call this tool as soon as the patient "
            "clearly indicates which provider they want (e.g. by name), "
            "using the EXACT provider_id and provider_name from that list. "
            "Do not invent a provider_id — match it against the providers "
            "already shown in this conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": (
                        "The exact provider_id (e.g. 'osm:way:594121613') "
                        "from the provider list already shown to the patient."
                    ),
                },
                "provider_name": {
                    "type": "string",
                    "description": (
                        "The exact provider_name from the provider list "
                        "already shown to the patient."
                    ),
                },
            },
            "required": ["provider_id", "provider_name"],
        },
    },
}


CHECK_AVAILABILITY_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_availability",
        "description": (
            "Check available appointment slots for the selected provider. "
            "Call this tool when the patient asks to see available times "
            "(e.g. 'Show me available appointments' or 'What times are open?'). "
            "Use the provider_id from the earlier select_provider call, and "
            "the care destination and specialty from the navigation recommendation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": (
                        "The selected provider's ID (e.g. 'osm:way:594121613'), "
                        "from the earlier select_provider call."
                    ),
                },
                "destination": {
                    "type": "string",
                    "description": (
                        "Care destination from the navigation recommendation "
                        "(e.g. 'SPECIALIST', 'PCP', 'URGENT_CARE')."
                    ),
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "Specialist sub-type when destination is SPECIALIST "
                        "(e.g. 'CARDIOLOGY'). May be null for other care types."
                    ),
                },
                "patient_id": {
                    "type": "string",
                    "description": (
                        "Patient identifier (MRN). Optional; passed to the "
                        "external appointment service if provided."
                    ),
                },
                "preferred_date": {
                    "type": "string",
                    "description": (
                        "Preferred date in ISO-8601 format (e.g. '2026-08-25'). "
                        "Optional; use only if the patient specified a date."
                    ),
                },
                "preferred_time": {
                    "type": "string",
                    "description": (
                        "Preferred time (e.g. '09:00', 'morning', 'afternoon'). "
                        "Optional; use only if the patient specified a time."
                    ),
                },
                "date_range": {
                    "type": "string",
                    "description": (
                        "Date range hint for the search (e.g. 'next_7_days', "
                        "'next_30_days'). Default 'next_7_days'."
                    ),
                },
            },
            "required": ["provider_id", "destination"],
        },
    },
}


# ===========================================================================
# Booking tool
# ===========================================================================
# Step 5 (booking): lets the LLM autonomously book the appointment once the
# patient confirms. Calls the existing real Appointment Service via
# AppointmentAgentClient.book() -- no mock data. Grounding against the
# known provider_id / slot_id (so the LLM cannot invent either) is enforced
# by the caller (the tool-calling loop), the same pattern used for
# select_provider / select_slot.

def book_appointment(
    provider_id: str,
    slot_id: str,
    patient_id: str,
    specialty: Optional[str] = None,
) -> Dict[str, Any]:
    """Book the appointment for the previously selected provider and slot.

    Calls the external/real Appointment Service's booking endpoint using
    the existing AppointmentAgentClient. This tool does NOT validate
    provider_id/slot_id against the known session state on its own — the
    caller (the tool-calling loop) cross-checks both against the persisted
    selected_provider_id and available_slots and rejects the call if they
    do not match, so the LLM must ground the booking in the real selections
    already recorded rather than inventing either ID.

    Parameters
    ----------
    provider_id : str
        The selected provider's ID (e.g. 'osm:way:594121613'), from the
        earlier select_provider call.
    slot_id : str
        The selected slot's ID, from the earlier select_slot call.
    patient_id : str
        Patient identifier (MRN) for this session.
    specialty : str | None
        Specialist sub-type when applicable.

    Returns (success)
    -------------------
    {
        "ok": True,
        "appointment_id": str,
        "provider_id": str,
        "status": "BOOKED",
        "slot": {
            "slot_id": str,
            "provider_id": str,
            "start_time": str,  # ISO-8601
            "end_time": str,    # ISO-8601
        },
    }

    Returns (failure)
    ------------------
    {
        "ok": False,
        "error": "<descriptive message>"
    }
    """
    try:
        from models.schemas import BookingRequest

        client = AppointmentAgentClient()

        booking_request = BookingRequest(
            patient_id=patient_id,
            recommendation_id="",  # internal field, stripped before the HTTP call
            provider_id=provider_id,
            slot_id=slot_id,
        )

        confirmation = client.book(
            booking_request,
            specialty=specialty,
            patient_context=None,
        )

        logger.info(
            "book_appointment: booked appointment_id=%s provider=%s slot=%s",
            confirmation.appointment_id, provider_id, slot_id,
        )

        return {
            "ok": True,
            "appointment_id": confirmation.appointment_id,
            "provider_id": confirmation.provider_id,
            "status": confirmation.status,
            "slot": confirmation.slot.model_dump(),
        }

    except requests.exceptions.HTTPError as exc:
        # Surface the real Appointment Service's error detail (e.g. slot no
        # longer available, provider mismatch) rather than a generic message.
        detail = None
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            pass
        logger.warning("book_appointment: booking failed: %s (%s)", exc, detail)
        return {
            "ok": False,
            "error": detail or f"Booking failed: {exc}",
        }
    except requests.exceptions.RequestException as exc:
        logger.warning("book_appointment: HTTP error: %s", exc)
        return {
            "ok": False,
            "error": f"Failed to book appointment: {exc}",
        }
    except Exception as exc:
        logger.warning("book_appointment: unexpected error: %s", exc)
        return {
            "ok": False,
            "error": f"Unexpected error: {exc}",
        }


SELECT_SLOT_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "select_slot",
        "description": (
            "Record the patient's selected appointment slot from the list "
            "of available slots already returned by check_availability. "
            "Call this tool as soon as the patient clearly indicates which "
            "time slot they want (e.g. 'the first one', '9:00 AM', 'the "
            "10:30 slot'), using the EXACT slot_id from that list. Do not "
            "invent a slot_id — match it against the slots already shown "
            "in this conversation. This only records the selection; it "
            "does NOT book the appointment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot_id": {
                    "type": "string",
                    "description": (
                        "The exact slot_id from the available_slots list "
                        "already shown to the patient."
                    ),
                },
            },
            "required": ["slot_id"],
        },
    },
}


BOOK_APPOINTMENT_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "book_appointment",
        "description": (
            "Book the appointment for the previously selected provider and "
            "slot. Call this tool ONLY after the patient has explicitly "
            "confirmed they want to book (e.g. 'Yes, book it', 'Confirm', "
            "'Go ahead'). Use the EXACT provider_id from the earlier "
            "select_provider call and the EXACT slot_id from the earlier "
            "select_slot call. Do not invent either ID. This performs a "
            "real booking against the Appointment Service — it cannot be "
            "undone by this conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": (
                        "The exact provider_id from the earlier "
                        "select_provider call."
                    ),
                },
                "slot_id": {
                    "type": "string",
                    "description": (
                        "The exact slot_id from the earlier select_slot call."
                    ),
                },
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier (MRN) for this session.",
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "Specialist sub-type when destination is SPECIALIST. "
                        "May be null for other care types."
                    ),
                },
            },
            "required": ["provider_id", "slot_id", "patient_id"],
        },
    },
}


# Tool registry scoped to the Appointment Agent only.
_APPOINTMENT_TOOL_REGISTRY: Dict[str, Any] = {
    "search_nearby_providers": search_nearby_providers,
    "select_provider": select_provider,
    "check_availability": check_availability,
    "select_slot": select_slot,
    "book_appointment": book_appointment,
}

APPOINTMENT_TOOLS: List[Dict[str, Any]] = [
    PROVIDER_SEARCH_TOOL_DEF,
    SELECT_PROVIDER_TOOL_DEF,
    CHECK_AVAILABILITY_TOOL_DEF,
    SELECT_SLOT_TOOL_DEF,
    BOOK_APPOINTMENT_TOOL_DEF,
]


def execute_appointment_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a tool call by name to the Appointment Agent's tool registry.

    Mirrors the dispatch pattern used by
    agents/tools/navigation_tools.py's execute_tool(), scoped to
    Appointment Agent tools only.
    """
    fn = _APPOINTMENT_TOOL_REGISTRY.get(name)
    if fn is None:
        return {"ok": False, "error": f"Unknown appointment tool: {name!r}"}
    try:
        return fn(**arguments)
    except TypeError as exc:
        logger.warning("execute_appointment_tool: bad arguments for %r: %s", name, exc)
        return {"ok": False, "error": f"Invalid arguments for {name}: {exc}"}


# ===========================================================================
# Appointment Agent LLM loop — provider search step
# ===========================================================================

_APPOINTMENT_SYSTEM_PROMPT = """\
You are a medical appointment assistant.

You have been given a navigation recommendation for a patient. Your job is to
find nearby healthcare providers that match the recommended care destination,
then help the patient pick one, and finally check appointment availability
for that provider.

STEP 1 — Provider search (only if no provider list exists yet in this
conversation):
  You MUST call the search_nearby_providers tool using the patient's
  coordinates and the recommended care destination. Do NOT invent provider
  information.

  After receiving the tool results:
  - If providers are found, present them to the patient as a numbered list
    showing: provider name, address (if available), and distance.
    Then ask: "Which provider would you like to choose?"
  - If the search_radius_km in the result is larger than the requested_radius_km,
    mention this: "I expanded the search to X km because no verified providers
    were found within the original Y km radius."
  - If no providers are found, inform the patient that no verified providers
    were found for the requested specialty/destination and suggest expanding
    the search or trying a different specialty.
  - If the tool returns an error, explain the issue to the patient and suggest
    trying again later.

STEP 2 — Provider selection (once a provider list already exists, whether
from earlier in this same conversation or restored from a previous turn):
  Do NOT call search_nearby_providers again — a provider list is already
  available in this conversation's context.
  Read the patient's message and determine which provider (from the list
  already shown) they are referring to. Match on name, partial name, or
  clear description — use your own judgement, not exact string matching.
  When you have identified the provider with reasonable confidence, call
  the select_provider tool with that provider's EXACT provider_id and
  provider_name as they appeared in the earlier provider list. Do not
  invent a provider_id that was not in the list.
  If the patient's message is ambiguous (matches multiple providers or
  none), ask a clarifying question instead of guessing.
  After select_provider succeeds, confirm the selection back to the patient
  in plain language (e.g. "Great, I've noted your preference for Dr. R
  Bhaskaran.").

STEP 3 — Availability checking (after a provider has been selected):
  Once the patient has selected a provider and confirmed it in Step 2,
  watch for requests to see available appointment times. Examples:
    - "Show me available appointments"
    - "What times are open?"
    - "When can I book?"
    - "Do you have any slots next week?"
  When the patient asks for availability, call the check_availability tool
  using:
    - provider_id: the EXACT provider_id from the select_provider call
    - destination: the care destination from the navigation recommendation
    - specialty: the specialist type if destination is SPECIALIST
    - preferred_date / preferred_time: if the patient mentioned a date or time
  After receiving the tool result with available slots:
    - If slots are found, present them as a numbered list with times.
      Example: "1. 2026-08-25 09:00 AM - 09:30 AM"
    - If no slots are found, inform the patient that no availability was found
      for this provider and suggest trying a different date or provider.
    - If the tool returns an error, explain the issue to the patient.

STEP 4 — Slot selection (once available slots have been shown in Step 3):
  Watch for the patient picking a specific time. Examples:
    - "I want the first available slot"
    - "9:00 AM works for me"
    - "The 10:30 one"
  Read the patient's message and determine which slot (from the
  available_slots list already shown) they are referring to. Match on
  position ("first", "second"), time of day, or a clear description — use
  your own judgement, not exact string matching.
  When you have identified the slot with reasonable confidence, call the
  select_slot tool with that slot's EXACT slot_id as it appeared in the
  earlier available_slots list. Do not invent a slot_id that was not in
  the list.
  If the patient's message is ambiguous (matches multiple slots or none),
  ask a clarifying question instead of guessing.
  After select_slot succeeds, confirm the selection back to the patient in
  plain language, restating the chosen time and provider, and ask if they
  would like to book it. Example: "Great, you've selected 9:00 AM - 9:30
  AM with Dr. R Bhaskaran. Would you like me to book this appointment?"
  Do NOT book the appointment yourself in this step — wait for explicit
  confirmation first (Step 5).

STEP 5 — Booking (once a slot has been selected in Step 4):
  Watch for the patient explicitly confirming they want to book. Examples:
    - "Yes, book it"
    - "Confirm"
    - "Go ahead and book that"
  Do NOT call book_appointment on a vague or ambiguous message — only when
  the patient clearly confirms.
  When confirmed, call the book_appointment tool using:
    - provider_id: the EXACT provider_id from the earlier select_provider call
    - slot_id: the EXACT slot_id from the earlier select_slot call
    - patient_id: the patient's MRN from this conversation
    - specialty: the specialist type if applicable
  After receiving the tool result:
    - If booking succeeded, confirm clearly to the patient, including the
      real appointment_id and the booked time/provider. Example: "Your
      appointment has been booked successfully with Dr. R Bhaskaran for
      9:00 AM - 9:30 AM. Confirmation ID: APT-xxxxxxxx."
    - If booking failed (e.g. the slot was taken by someone else), explain
      the actual error to the patient and suggest selecting a different
      slot. Do NOT claim the appointment was booked if the tool reports
      failure.

CRITICAL RULES:
- Do NOT label a provider as a specialist unless the tool result explicitly
  confirms it. The tool already filters by verified specialty from OSM data.
- Do NOT infer a provider's specialty from their name alone.
- Be concise and helpful. Do not add information not present in the tool result
  or the conversation so far.
- Once availability has been shown, wait for the patient to select a slot or
  ask for more options. Do NOT automatically book an appointment.
- Only call book_appointment after the patient has explicitly confirmed.
  Never call it proactively or on an ambiguous message.
"""

MAX_APPOINTMENT_ITERATIONS = 5


def _build_appointment_messages(
    recommendation_id: str,
    destination: str,
    latitude: float,
    longitude: float,
    radius_km: float = 15.0,
    specialty: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build initial messages for the appointment agent loop."""
    user_content = (
        f"I have a navigation recommendation (ID: {recommendation_id}).\n"
        f"Care destination: {destination}\n"
        f"{'Specialty: ' + specialty if specialty else ''}\n"
        f"Patient location: latitude={latitude}, longitude={longitude}\n"
        f"Search radius: {radius_km} km\n\n"
        f"Please find nearby providers for this care type."
    )
    return [
        {"role": "system", "content": _APPOINTMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _run_appointment_agent_loop(
    messages: List[Dict[str, Any]],
    *,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = MAX_APPOINTMENT_ITERATIONS,
    known_providers: Optional[List[Dict[str, Any]]] = None,
    known_slots: Optional[List[Dict[str, Any]]] = None,
    session_selected_provider_id: Optional[str] = None,
    session_selected_slot_id: Optional[str] = None,
    session_mrn: Optional[str] = None,
) -> Dict[str, Any]:
    """Shared LLM tool-calling loop for both a fresh start and a resumed
    conversation.

    This is the single place that talks to the LLM and executes tools —
    both run_appointment_agent() (Turn 1: fresh conversation) and
    continue_appointment_agent() (Turn 2+: resumed conversation) call this
    with a different initial `messages` list. The loop mechanics
    (LLM -> tool call -> tool result -> LLM observes -> repeat) are
    identical either way.

    Parameters
    ----------
    messages : list[dict]
        The full message history to send to the LLM. Callers are
        responsible for seeding this with the system prompt (+ prior
        conversation turns when resuming).
    client : NvidiaClient | None
        Optionally inject a pre-constructed NvidiaClient.
    max_iterations : int
        Max tool-calling loop iterations for THIS call.
    known_providers : list[dict] | None
        The provider list already known from a prior turn (if any). Used
        only to validate select_provider calls so the LLM cannot invent a
        provider_id that was never actually returned by OpenStreetMap.
    known_slots : list[dict] | None
        The available_slots list already known from a prior turn (if any).
        Used only to validate select_slot calls so the LLM cannot invent a
        slot_id that was never actually returned by check_availability.
    session_selected_provider_id : str | None
        The provider_id already persisted from a prior turn's
        select_provider call (if any). Used only to validate
        book_appointment calls so the LLM cannot book a provider that was
        never actually selected.
    session_selected_slot_id : str | None
        The slot_id already persisted from a prior turn's select_slot call
        (if any). Used only to validate book_appointment calls so the LLM
        cannot book a slot that was never actually selected.
    session_mrn : str | None
        The patient's MRN from the persisted session. The LLM is never
        shown this value in conversation history, so book_appointment's
        patient_id argument is always overridden with this authoritative
        value (when present) rather than trusted from the LLM.

    Returns
    -------
    dict
        {
            "ok": bool,
            "response": str | None,
            "tool_calls_made": int,
            "iterations": int,
            "providers": list | None,        # from search_nearby_providers
            "selected_provider_id": str | None,
            "selected_provider_name": str | None,
            "selected_slot_id": str | None,
            "appointment_id": str | None,
            "appointment_status": str | None,
            "messages": list[dict],          # full updated history — persist this
        }
    """
    import json

    if client is None:
        try:
            client = NvidiaClient()
        except NvidiaClientError as exc:
            logger.error("AppointmentAgent: failed to create NvidiaClient: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "response": None,
                "tool_calls_made": 0,
                "iterations": 0,
                "providers": None,
                "available_slots": None,
                "selected_provider_id": None,
                "selected_provider_name": None,
                "selected_slot_id": None,
                "appointment_id": None,
                "appointment_status": None,
                "messages": messages,
            }

    known_provider_ids = {
        p.get("provider_id") for p in (known_providers or []) if p.get("provider_id")
    }
    known_slot_ids = {
        s.get("slot_id") for s in (known_slots or []) if s.get("slot_id")
    }

    tool_calls_made = 0
    iterations = 0
    providers_result: Optional[List[Dict[str, Any]]] = None
    available_slots_result: Optional[List[Dict[str, Any]]] = None
    selected_provider_id: Optional[str] = None
    selected_provider_name: Optional[str] = None
    selected_slot_id: Optional[str] = None
    appointment_id: Optional[str] = None
    appointment_status: Optional[str] = None

    while iterations < max_iterations:
        iterations += 1

        try:
            response = client.chat(
                messages=messages,
                tools=APPOINTMENT_TOOLS,
                tool_choice="auto",
            )
        except NvidiaClientError as exc:
            logger.error("AppointmentAgent: LLM call failed at iteration %d: %s", iterations, exc)
            return {
                "ok": False,
                "error": f"LLM call failed: {exc}",
                "response": None,
                "tool_calls_made": tool_calls_made,
                "iterations": iterations,
                "providers": providers_result,
                "available_slots": available_slots_result,
                "selected_provider_id": selected_provider_id,
                "selected_provider_name": selected_provider_name,
                "selected_slot_id": selected_slot_id,
                "appointment_id": appointment_id,
                "appointment_status": appointment_status,
                "messages": messages,
            }

        # Final answer — no more tool calls
        if not response.has_tool_calls:
            final_text = response.content or ""
            logger.info(
                "AppointmentAgent: done after %d iterations, %d tool calls",
                iterations, tool_calls_made,
            )
            logger.info("DIAGNOSTIC TRACE 3 — Agent return value:")
            logger.info("  available_slots_result = %s", available_slots_result)
            logger.info("  selected_provider_id = %s", selected_provider_id)
            logger.info("  selected_provider_name = %s", selected_provider_name)
            
            messages.append({"role": "assistant", "content": final_text})
            result = {
                "ok": True,
                "response": final_text,
                "tool_calls_made": tool_calls_made,
                "iterations": iterations,
                "providers": providers_result,
                "available_slots": available_slots_result,
                "selected_provider_id": selected_provider_id,
                "selected_provider_name": selected_provider_name,
                "selected_slot_id": selected_slot_id,
                "appointment_id": appointment_id,
                "appointment_status": appointment_status,
                "messages": messages,
            }
            logger.info("DIAGNOSTIC TRACE 3.5 — Agent return dictionary:")
            logger.info("  result.keys() = %s", list(result.keys()))
            logger.info("  result['available_slots'] = %s", result.get("available_slots"))
            logger.info("  result['selected_provider_id'] = %s", result.get("selected_provider_id"))
            logger.info("  result['selected_provider_name'] = %s", result.get("selected_provider_name"))
            return result

        # Re-inject assistant's tool-call message into history
        choice_message = response.raw.choices[0].message
        tool_calls_raw = []
        if choice_message.tool_calls:
            for tc in choice_message.tool_calls:
                tool_calls_raw.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
        messages.append({
            "role": "assistant",
            "content": choice_message.content,
            "tool_calls": tool_calls_raw,
        })

        # Execute each tool call
        for tc in response.tool_calls:
            tool_calls_made += 1
            logger.info(
                "AppointmentAgent: executing tool %r with args %r",
                tc.name, tc.arguments,
            )

            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError as exc:
                tool_result = {"ok": False, "error": f"Invalid JSON arguments: {exc}"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result),
                })
                continue

            # Ground select_provider against the known provider list so the
            # LLM cannot fabricate a provider_id that was never returned by
            # search_nearby_providers.
            if tc.name == "select_provider" and known_provider_ids:
                candidate_id = args.get("provider_id")
                if candidate_id not in known_provider_ids:
                    tool_result = {
                        "ok": False,
                        "error": (
                            f"provider_id {candidate_id!r} does not match any "
                            "provider from the earlier search results. "
                            "Re-check the provider list and try again with "
                            "the exact provider_id."
                        ),
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })
                    continue

            # Ground select_slot against the known available_slots list so
            # the LLM cannot fabricate a slot_id that was never actually
            # returned by check_availability.
            if tc.name == "select_slot" and known_slot_ids:
                candidate_slot_id = args.get("slot_id")
                if candidate_slot_id not in known_slot_ids:
                    tool_result = {
                        "ok": False,
                        "error": (
                            f"slot_id {candidate_slot_id!r} does not match any "
                            "slot from the earlier availability results. "
                            "Re-check the available_slots list and try again "
                            "with the exact slot_id."
                        ),
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })
                    continue

            # Ground book_appointment against the persisted selection state
            # (this turn's selection OR the prior turn's persisted session
            # state) so the LLM cannot book a provider/slot that was never
            # actually selected via select_provider / select_slot.
            if tc.name == "book_appointment":
                effective_provider_id = selected_provider_id or session_selected_provider_id
                effective_slot_id = selected_slot_id or session_selected_slot_id

                candidate_provider_id = args.get("provider_id")
                candidate_slot_id = args.get("slot_id")

                if not effective_provider_id or candidate_provider_id != effective_provider_id:
                    tool_result = {
                        "ok": False,
                        "error": (
                            f"provider_id {candidate_provider_id!r} does not "
                            "match the provider already selected via "
                            "select_provider in this conversation. Booking "
                            "rejected."
                        ),
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })
                    continue

                if not effective_slot_id or candidate_slot_id != effective_slot_id:
                    tool_result = {
                        "ok": False,
                        "error": (
                            f"slot_id {candidate_slot_id!r} does not match "
                            "the slot already selected via select_slot in "
                            "this conversation. Booking rejected."
                        ),
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })
                    continue

                # The LLM is never shown the patient's MRN in conversation
                # history, so its patient_id guess is not trustworthy.
                # Override with the authoritative session MRN when present.
                if session_mrn:
                    args["patient_id"] = session_mrn

            tool_result = execute_appointment_tool(tc.name, args)

            # DIAGNOSTIC: Log tool_result for check_availability
            if tc.name == "check_availability":
                logger.info("DIAGNOSTIC TRACE 2 — check_availability tool_result:")
                logger.info("  tool_result keys: %s", list(tool_result.keys()))
                logger.info("  tool_result['ok'] = %s", tool_result.get("ok"))
                logger.info("  tool_result['count'] = %s", tool_result.get("count"))
                logger.info("  len(tool_result.get('slots')) = %s", len(tool_result.get("slots", [])))

            # Capture provider results
            if tc.name == "search_nearby_providers" and tool_result.get("ok"):
                providers_result = tool_result.get("providers")
                if providers_result:
                    known_provider_ids = {
                        p.get("provider_id") for p in providers_result if p.get("provider_id")
                    }

            # Capture provider selection
            if tc.name == "select_provider" and tool_result.get("ok"):
                selected_provider_id = tool_result.get("provider_id")
                selected_provider_name = tool_result.get("provider_name")

            # Capture availability results
            if tc.name == "check_availability" and tool_result.get("ok"):
                available_slots_result = tool_result.get("slots")
                if available_slots_result:
                    known_slot_ids = {
                        s.get("slot_id") for s in available_slots_result if s.get("slot_id")
                    }
                logger.info(
                    "AppointmentAgent: captured %d available slots",
                    len(available_slots_result) if available_slots_result else 0,
                )
                logger.info("DIAGNOSTIC TRACE 2.5 — available_slots_result assigned:")
                logger.info("  available_slots_result = %s", available_slots_result)

            # Capture slot selection
            if tc.name == "select_slot" and tool_result.get("ok"):
                selected_slot_id = tool_result.get("slot_id")

            # Capture booking result
            if tc.name == "book_appointment" and tool_result.get("ok"):
                appointment_id = tool_result.get("appointment_id")
                appointment_status = tool_result.get("status")
                logger.info(
                    "AppointmentAgent: booked appointment_id=%s status=%s",
                    appointment_id, appointment_status,
                )

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result),
            })

    # Max iterations reached
    logger.warning("AppointmentAgent: max iterations (%d) reached", max_iterations)
    return {
        "ok": False,
        "error": "Max iterations reached without final response",
        "response": None,
        "tool_calls_made": tool_calls_made,
        "iterations": iterations,
        "providers": providers_result,
        "available_slots": available_slots_result,
        "selected_provider_id": selected_provider_id,
        "selected_provider_name": selected_provider_name,
        "selected_slot_id": selected_slot_id,
        "appointment_id": appointment_id,
        "appointment_status": appointment_status,
        "messages": messages,
    }


def run_appointment_agent(
    recommendation_id: str,
    destination: str,
    latitude: float,
    longitude: float,
    radius_km: float = 15.0,
    specialty: Optional[str] = None,
    *,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = MAX_APPOINTMENT_ITERATIONS,
) -> Dict[str, Any]:
    """Run the Appointment Agent's LLM-driven tool-calling loop (Turn 1).

    This agent receives the navigation recommendation context and
    autonomously decides to call search_nearby_providers to find real
    nearby facilities from OpenStreetMap.

    Parameters
    ----------
    recommendation_id : str
        The recommendation ID from /navigate.
    destination : str
        Care destination (PCP, URGENT_CARE, SPECIALIST, etc.).
    latitude : float
        Patient latitude.
    longitude : float
        Patient longitude.
    radius_km : float
        Search radius in km. Default 15.0.
    specialty : str | None
        Specialist sub-type when destination is SPECIALIST.
    client : NvidiaClient | None
        Optionally inject a pre-constructed NvidiaClient. When None,
        a new instance is created from environment variables.
    max_iterations : int
        Max tool-calling loop iterations. Default 5.

    Returns
    -------
    dict
        {
            "ok": True/False,
            "response": str,           # conversational response to patient
            "tool_calls_made": int,
            "iterations": int,
            "providers": list | None,  # raw provider list from tool
            "selected_provider_id": None,     # never set on Turn 1
            "selected_provider_name": None,   # never set on Turn 1
            "messages": list[dict],    # full conversation history — persist this
        }
    """
    messages = _build_appointment_messages(
        recommendation_id=recommendation_id,
        destination=destination,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        specialty=specialty,
    )

    logger.info(
        "AppointmentAgent: starting loop (recommendation_id=%s destination=%s)",
        recommendation_id, destination,
    )

    return _run_appointment_agent_loop(
        messages,
        client=client,
        max_iterations=max_iterations,
    )


def continue_appointment_agent(
    conversation_state: List[Dict[str, Any]],
    patient_message: str,
    *,
    known_providers: Optional[List[Dict[str, Any]]] = None,
    known_slots: Optional[List[Dict[str, Any]]] = None,
    session_selected_provider_id: Optional[str] = None,
    session_selected_slot_id: Optional[str] = None,
    session_mrn: Optional[str] = None,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = MAX_APPOINTMENT_ITERATIONS,
) -> Dict[str, Any]:
    """Resume the Appointment Agent's LLM-driven tool-calling loop (Turn 2+).

    Restores the exact conversation history persisted from a prior turn
    (e.g. the provider list already presented to the patient in Turn 1),
    appends the patient's new message, and resumes the SAME tool-calling
    loop used in Turn 1 — the LLM reasons over the restored context and
    decides which tool (if any) to call next. No new conversation is
    started and no hard-coded string matching is used to pick a provider.

    Parameters
    ----------
    conversation_state : list[dict]
        The exact `messages` list persisted from a prior turn (as returned
        in the "messages" key of run_appointment_agent()/this function's
        own return value).
    patient_message : str
        The new message from the patient for this turn.
    known_providers : list[dict] | None
        The provider list already known from a prior turn, used to ground
        select_provider calls against real search results.
    known_slots : list[dict] | None
        The available_slots list already known from a prior turn, used to
        ground select_slot calls against real availability results.
    session_selected_provider_id : str | None
        The provider_id already persisted from a prior turn, used to
        ground book_appointment calls so the LLM cannot book a provider
        that was never actually selected.
    session_selected_slot_id : str | None
        The slot_id already persisted from a prior turn, used to ground
        book_appointment calls so the LLM cannot book a slot that was
        never actually selected.
    session_mrn : str | None
        The patient's MRN from the persisted session, used to override
        book_appointment's patient_id argument with the authoritative
        value rather than trusting the LLM's guess.
    client : NvidiaClient | None
        Optionally inject a pre-constructed NvidiaClient.
    max_iterations : int
        Max tool-calling loop iterations for THIS turn. Default 5.

    Returns
    -------
    dict
        Same shape as run_appointment_agent()'s return value.
    """
    messages: List[Dict[str, Any]] = list(conversation_state) + [
        {"role": "user", "content": patient_message},
    ]

    logger.info(
        "AppointmentAgent: resuming conversation (restored %d prior messages)",
        len(conversation_state),
    )

    return _run_appointment_agent_loop(
        messages,
        client=client,
        max_iterations=max_iterations,
        known_providers=known_providers,
        known_slots=known_slots,
        session_selected_provider_id=session_selected_provider_id,
        session_selected_slot_id=session_selected_slot_id,
        session_mrn=session_mrn,
    )
