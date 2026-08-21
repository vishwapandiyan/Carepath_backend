"""
Navigation tool wrappers — adapters between LLM tool calls and
existing deterministic capabilities.

PURPOSE
-------
These wrappers do NOT contain any new medical logic, geocoding logic,
ranking logic, or OSM query logic.  Every wrapper calls an existing
function from the production codebase and converts its inputs/outputs to
JSON-serializable dicts so the LLM agent loop can send tool results back
in a `role="tool"` message.

UNDERLYING FUNCTIONS (exact signatures from source)
----------------------------------------------------
CareClassifier.classify(patient: PatientFeatures) -> CareDecision
    engine/care_classifier.py

geocode(address: str) -> Tuple[float, float]
    location/geocoder.py
    Raises: InvalidLocationError, GeocodingRateLimitError, GeocodingNetworkError

find_nearby_providers(
    location: PatientLocation,
    destination: Destination,      # Literal["PCP","URGENT_CARE","SPECIALIST","TELEHEALTH","DENTISTRY"]
    specialty: str | None,
) -> List[ProviderCandidate]
    location/provider_discovery.py
    Raises: ValueError (no coords), ProviderDiscoveryNetworkError, ProviderDiscoveryRateLimitError

rank_providers(
    patient_lat: float,
    patient_lon: float,
    candidates: List[ProviderCandidate],
    has_pcp_flag: int | None = None,
    top_n: int = 5,
) -> List[ProviderCandidate]
    location/ranking.py

TOOL NAMES (must match the "name" keys in ALL_TOOLS)
-----------------------------------------------------
  classify_care
  geocode_location
  discover_providers
  rank_providers

TOOL CALL PROTOCOL
------------------
The LLM sends a tool call like:
    {"name": "classify_care", "arguments": '{"primary_symptom_category":"back_pain",...}'}

`execute_tool(name, arguments)` receives the name and the already-parsed
arguments dict (not the raw JSON string), dispatches to the correct wrapper,
and returns a JSON-serializable dict.

ERROR CONTRACT
--------------
All wrappers return a dict with key "error" on failure rather than
re-raising.  This lets the LLM agent loop read the error as a tool result
and decide how to proceed (retry with corrected arguments, surface the
error, etc.) rather than crashing the Python process.

Success responses always include "ok": True.
Error responses always include "ok": False and "error": <message string>.
"""

from __future__ import annotations

import json
import logging
import requests
from typing import Any, Dict, List, Optional

from app.services.alternate_care.engine.care_classifier import CareClassifier
from app.services.alternate_care.location.geocoder import (
    GeocodingError,
    InvalidLocationError,
    GeocodingNetworkError,
    geocode,
)
from app.services.alternate_care.location.provider_discovery import (
    ProviderDiscoveryError,
    find_nearby_providers,
)
from app.services.alternate_care.location.ranking import rank_providers as _rank_providers
from app.services.alternate_care.models.schemas import (
    CareDecision,
    PatientFeatures,
    PatientLocation,
    ProviderCandidate,
)
from app.services.alternate_care.appointment.client import AppointmentAgentClient
from app.services.alternate_care.appointment.schemas import RescheduleRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton so CareClassifier does not re-parse the YAML on
# every tool call.  Tests replace this with a fixture if needed.
# ---------------------------------------------------------------------------
_classifier = CareClassifier()

# ---------------------------------------------------------------------------
# Module-level AppointmentAgentClient instance for appointment tool executors.
# Tests can replace this with a mock if needed.
# ---------------------------------------------------------------------------
_appointment_client = AppointmentAgentClient()


# ===========================================================================
# 1. classify_care
# ===========================================================================

def classify_care(patient_features: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a patient's care destination using the deterministic rule engine.

    Calls: CareClassifier.classify(PatientFeatures)
    File:  engine/care_classifier.py

    Parameters
    ----------
    patient_features : dict
        Fields matching PatientFeatures.  Only ``primary_symptom_category``
        is required; all other fields are optional and default to their
        Pydantic defaults.  Extra fields are silently allowed
        (PatientFeatures has model_config extra="allow").

    Returns (success)
    -----------------
    {
        "ok": True,
        "rule_id": str,
        "priority": int,
        "destination": str,   # PCP | URGENT_CARE | SPECIALIST | TELEHEALTH | DENTISTRY
        "specialty": str | None,
        "status": str,
        "explanation": str
    }

    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }

    Failure cases
    -------------
    - "primary_symptom_category" missing → Pydantic ValidationError → "error"
    - FALLBACK-999 not in rules (should never happen) → RuntimeError → "error"
    """
    try:
        patient = PatientFeatures(**patient_features)
        decision: CareDecision = _classifier.classify(patient)
        return {
            "ok": True,
            "rule_id": decision.rule_id,
            "priority": decision.priority,
            "destination": decision.destination,
            "specialty": decision.specialty,
            "status": decision.status,
            "explanation": decision.explanation,
        }
    except Exception as exc:
        logger.warning("classify_care failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# OpenAI/NVIDIA-compatible tool definition for classify_care
# ---------------------------------------------------------------------------

CLASSIFY_CARE_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "classify_care",
        "description": (
            "Classify a patient's care destination using the deterministic "
            "clinical rule engine.  Returns the recommended destination "
            "(PCP, URGENT_CARE, SPECIALIST, TELEHEALTH, or DENTISTRY), the "
            "matched rule ID, and the specialty when destination is SPECIALIST. "
            "This tool must be called before discover_providers because provider "
            "search requires a destination and optional specialty."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "primary_symptom_category": {
                    "type": "string",
                    "description": (
                        "Required.  Patient's primary symptom category.  "
                        "Examples: 'minor_infection', 'back_pain', "
                        "'mild_breathing_difficulty', 'dental_pain', "
                        "'mild_general_symptom', 'chronic_disease_flareup'."
                    ),
                },
                "pain_level_self_reported": {
                    "type": "integer",
                    "description": "Self-reported pain level 0–10.  Optional.",
                },
                "pain_onset": {
                    "type": "string",
                    "description": "'gradual' or 'sudden'.  Optional.",
                },
                "pain_duration": {
                    "type": "string",
                    "description": "'hours' or 'days'.  Optional.",
                },
                "symptom_trend": {
                    "type": "string",
                    "description": "'improving', 'same', or 'worsening'.  Optional.",
                },
                "copd_asthma_flag": {
                    "type": "integer",
                    "description": "1 if patient has COPD/asthma, 0 otherwise.  Default 0.",
                },
                "chronic_condition_count": {
                    "type": "integer",
                    "description": "Number of chronic conditions.  Default 0.",
                },
                "charlson_comorbidity_index": {
                    "type": "integer",
                    "description": "Charlson Comorbidity Index score.  Default 0.",
                },
                "ed_visits_past_year": {
                    "type": "integer",
                    "description": "ED visits in the past 12 months.  Default 0.",
                },
                "has_pcp_flag": {
                    "type": "integer",
                    "description": "1 if patient has an established PCP, 0 or null otherwise.",
                },
            },
            "required": ["primary_symptom_category"],
        },
    },
}


# ===========================================================================
# 2. geocode_location
# ===========================================================================

def geocode_location(address: str) -> Dict[str, Any]:
    """Convert a U.S. address, city/state, or ZIP code to coordinates.

    Calls: geocode(address)  →  Tuple[float, float]
    File:  location/geocoder.py

    This tool is only needed when the patient supplied a text address rather
    than explicit latitude/longitude.  If the agent already has coordinates,
    it should skip this tool and call discover_providers directly.

    Parameters
    ----------
    address : str
        Any of: street address, city/state, or ZIP code.
        Example: "Austin, TX 78701" or "90210" or "123 Main St, Boston, MA"

    Returns (success)
    -----------------
    {
        "ok": True,
        "latitude": float,
        "longitude": float,
        "address": str        # echoes the input address
    }

    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }

    Failure cases
    -------------
    - Empty/whitespace address → InvalidLocationError → "error"
    - Address not found by Nominatim → InvalidLocationError → "error"
    - HTTP 429 from Nominatim → GeocodingRateLimitError → "error"
    - Network timeout / connection error → GeocodingNetworkError → "error"
    """
    try:
        lat, lon = geocode(address)
        return {
            "ok": True,
            "latitude": lat,
            "longitude": lon,
            "address": address,
        }
    except InvalidLocationError as exc:
        logger.warning("geocode_location: invalid address %r: %s", address, exc)
        return {"ok": False, "error": str(exc)}
    except GeocodingError as exc:
        logger.warning("geocode_location: geocoding error for %r: %s", address, exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("geocode_location: unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# OpenAI/NVIDIA-compatible tool definition for geocode_location
# ---------------------------------------------------------------------------

GEOCODE_LOCATION_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "geocode_location",
        "description": (
            "Convert a U.S. address string, city/state name, or ZIP code to "
            "latitude and longitude coordinates.  Only call this tool when the "
            "patient's location is given as a text string rather than explicit "
            "coordinates.  If latitude and longitude are already known, skip "
            "this tool and call discover_providers directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": (
                        "Required.  A U.S. location in any of these forms: "
                        "street address ('123 Main St, Austin, TX 78701'), "
                        "city/state ('Austin, TX'), or ZIP code ('78701')."
                    ),
                }
            },
            "required": ["address"],
        },
    },
}


# ===========================================================================
# 3. discover_providers
# ===========================================================================

def discover_providers(
    latitude: float,
    longitude: float,
    destination: str,
    specialty: Optional[str] = None,
    radius_km: float = 15.0,
) -> Dict[str, Any]:
    """Find nearby healthcare facilities via OpenStreetMap / Overpass API.

    Calls: find_nearby_providers(PatientLocation, destination, specialty)
    File:  location/provider_discovery.py

    The destination and specialty must come from the classify_care tool
    result.  Do NOT invent or guess destination/specialty values.

    Parameters
    ----------
    latitude : float
        Patient latitude (from geocode_location or directly supplied).
    longitude : float
        Patient longitude.
    destination : str
        Care destination from classify_care result.
        One of: PCP, URGENT_CARE, SPECIALIST, TELEHEALTH, DENTISTRY.
    specialty : str | None
        Specialist sub-type from classify_care result.
        Required when destination is SPECIALIST (e.g. "PULMONOLOGY").
        Must be None for all other destinations.
    radius_km : float
        Search radius in kilometres.  Default 15.0.

    Returns (success)
    -----------------
    {
        "ok": True,
        "destination": str,
        "specialty": str | None,
        "count": int,
        "providers": [
            {
                "provider_id": str,    # e.g. "osm:node:123456"
                "name": str,
                "destination_type": str,
                "specialty": str | None,
                "latitude": float,
                "longitude": float,
                "address": str | None,
                "distance_km": None,   # set to null here; rank_providers fills it
                "score": None,
                "source": str          # always "osm"
            },
            ...
        ]
    }

    For TELEHEALTH, returns count=0 and providers=[] without any API call
    (telehealth providers come from the Appointment Agent, not OSM).

    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }

    Failure cases
    -------------
    - Invalid destination value → ValueError from tags_for → "error"
    - No coordinates (should not happen if geocode_location was called) → ValueError → "error"
    - Overpass HTTP 429 → ProviderDiscoveryRateLimitError → "error"
    - Overpass network error → ProviderDiscoveryNetworkError → "error"
    """
    try:
        location = PatientLocation(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )
        candidates: List[ProviderCandidate] = find_nearby_providers(
            location=location,
            destination=destination,  # type: ignore[arg-type]  # validated by tags_for
            specialty=specialty,
        )
        return {
            "ok": True,
            "destination": destination,
            "specialty": specialty,
            "count": len(candidates),
            "providers": [c.model_dump() for c in candidates],
        }
    except (ProviderDiscoveryError, ValueError) as exc:
        logger.warning("discover_providers failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("discover_providers unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# OpenAI/NVIDIA-compatible tool definition for discover_providers
# ---------------------------------------------------------------------------

DISCOVER_PROVIDERS_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "discover_providers",
        "description": (
            "Search for nearby healthcare facilities using OpenStreetMap data "
            "via the Overpass API.  Returns a list of raw provider candidates "
            "with location information but without distance scores — call "
            "rank_providers afterwards to sort them by distance.  "
            "The destination and specialty arguments must come directly from "
            "the classify_care tool result; do not guess or invent these values."
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
                        "Care destination from the classify_care result.  "
                        "Must be one of the exact enum values."
                    ),
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "Specialist sub-type from the classify_care result.  "
                        "Required when destination is SPECIALIST "
                        "(e.g. 'PULMONOLOGY', 'ORTHOPEDICS').  "
                        "Must be null/omitted for all other destinations."
                    ),
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometres.  Default 15.0.",
                },
            },
            "required": ["latitude", "longitude", "destination"],
        },
    },
}


# ===========================================================================
# 4. rank_providers
# ===========================================================================

def rank_providers(
    patient_lat: float,
    patient_lon: float,
    providers: List[Dict[str, Any]],
    has_pcp_flag: Optional[int] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Score and sort provider candidates by distance using the Haversine formula.

    Calls: rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag, top_n)
    File:  location/ranking.py

    Parameters
    ----------
    patient_lat : float
        Patient latitude.
    patient_lon : float
        Patient longitude.
    providers : list[dict]
        Provider candidate dicts as returned by discover_providers
        (i.e. the "providers" list from a successful discover_providers result).
        Each dict must contain at minimum: provider_id, name, destination_type,
        latitude, longitude, source.
    has_pcp_flag : int | None
        1 if the patient has an established PCP relationship, 0 or null otherwise.
        Used to add a small continuity bonus (0.05) when destination is PCP.
    top_n : int
        Maximum number of providers to return.  Default 5.

    Returns (success)
    -----------------
    {
        "ok": True,
        "count": int,
        "providers": [
            {
                "provider_id": str,
                "name": str,
                "destination_type": str,
                "specialty": str | None,
                "latitude": float,
                "longitude": float,
                "address": str | None,
                "distance_km": float,   # now populated by ranking
                "score": float,         # 0.0–1.05 (higher = closer + continuity)
                "source": str
            },
            ...
        ]
    }

    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }

    Failure cases
    -------------
    - providers list contains dicts with missing required fields → "error"
    - patient_lat / patient_lon are None → downstream arithmetic error → "error"
    """
    try:
        candidate_objects: List[ProviderCandidate] = [
            ProviderCandidate(**p) for p in providers
        ]
        ranked: List[ProviderCandidate] = _rank_providers(
            patient_lat=patient_lat,
            patient_lon=patient_lon,
            candidates=candidate_objects,
            has_pcp_flag=has_pcp_flag,
            top_n=top_n,
        )
        return {
            "ok": True,
            "count": len(ranked),
            "providers": [p.model_dump() for p in ranked],
        }
    except Exception as exc:
        logger.warning("rank_providers failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# OpenAI/NVIDIA-compatible tool definition for rank_providers
# ---------------------------------------------------------------------------

RANK_PROVIDERS_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "rank_providers",
        "description": (
            "Score and sort provider candidates by straight-line distance "
            "from the patient using the Haversine formula.  Returns up to "
            "top_n providers ordered closest-first.  Call this after "
            "discover_providers — pass the 'providers' list from the "
            "discover_providers result as the 'providers' argument here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_lat": {
                    "type": "number",
                    "description": "Patient latitude in decimal degrees.",
                },
                "patient_lon": {
                    "type": "number",
                    "description": "Patient longitude in decimal degrees.",
                },
                "providers": {
                    "type": "array",
                    "description": (
                        "Provider candidate list from discover_providers result "
                        "('providers' field).  Each item must be a provider dict."
                    ),
                    "items": {"type": "object"},
                },
                "has_pcp_flag": {
                    "type": "integer",
                    "description": (
                        "1 if patient has an established PCP, 0 or omit otherwise.  "
                        "Adds a small continuity bonus when ranking PCP providers."
                    ),
                },
                "top_n": {
                    "type": "integer",
                    "description": "Maximum providers to return.  Default 5.",
                },
            },
            "required": ["patient_lat", "patient_lon", "providers"],
        },
    },
}


# ===========================================================================
# 5. reschedule_appointment
# ===========================================================================

# ---------------------------------------------------------------------------
# OpenAI/NVIDIA-compatible tool definition for reschedule_appointment
# ---------------------------------------------------------------------------

RESCHEDULE_APPOINTMENT_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "reschedule_appointment",
        "description": (
            "Reschedule an existing appointment to a new time slot. "
            "Supports two workflows: (A) direct slot selection with new_slot_id, "
            "or (B) preference-based search with preferred_date/preferred_time. "
            "For workflow B, call check_availability first to show options."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Required. The patient's unique identifier.",
                },
                "appointment_id": {
                    "type": "string",
                    "description": (
                        "Required. The appointment_id of the existing "
                        "appointment to reschedule."
                    ),
                },
                "recommendation_id": {
                    "type": "string",
                    "description": (
                        "Optional. The recommendation ID if available. "
                        "May be absent if the original recommendation expired."
                    ),
                },
                "new_slot_id": {
                    "type": "string",
                    "description": (
                        "Optional (Workflow A). The slot_id of the new slot "
                        "chosen from check_availability results."
                    ),
                },
                "preferred_date": {
                    "type": "string",
                    "description": (
                        "Optional (Workflow B). ISO-8601 date string for "
                        "the patient's preferred new appointment date."
                    ),
                },
                "preferred_time": {
                    "type": "string",
                    "description": (
                        "Optional (Workflow B). Preferred time of day for "
                        "the rescheduled appointment."
                    ),
                },
            },
            "required": ["patient_id", "appointment_id"],
        },
    },
}


# ===========================================================================
# 5. book_appointment (NEW - Appointment Agentic Tool)
# ===========================================================================

BOOK_APPOINTMENT_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "book_appointment",
        "description": (
            "Book a specific appointment slot that was returned by "
            "check_availability. Call this tool after the patient has chosen "
            "a slot from the available options. Requires the recommendation_id "
            "to validate the provider is from the authorized ranked list. "
            "The slot_id must come from a check_availability result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": (
                        "Required. The recommendation ID from the navigation "
                        "workflow. Used to validate the provider and retrieve "
                        "the care_type and specialty."
                    ),
                },
                "patient_id": {
                    "type": "string",
                    "description": "Required. The patient's unique identifier.",
                },
                "provider_id": {
                    "type": "string",
                    "description": (
                        "Required. The provider_id from check_availability. "
                        "Must match a provider in the recommendation."
                    ),
                },
                "slot_id": {
                    "type": "string",
                    "description": (
                        "Required. The slot_id from the check_availability "
                        "result that the patient selected."
                    ),
                },
            },
            "required": ["recommendation_id", "patient_id", "provider_id", "slot_id"],
        },
    },
}


# ===========================================================================
# 5. check_availability (NEW — Appointment Tool)
# ===========================================================================

CHECK_AVAILABILITY_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_availability",
        "description": (
            "Check available appointment slots for a specific provider from "
            "the ranked provider list. Call this tool after rank_providers "
            "completes to discover when a chosen provider has open appointments. "
            "Requires a valid recommendation_id from the navigation workflow "
            "to authorize the provider lookup. This tool should ONLY be called "
            "when the patient explicitly requests appointment scheduling assistance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": (
                        "Required. The recommendation ID from the navigation "
                        "workflow that authorized this provider selection. "
                        "Used to retrieve the trusted CareDecision and validate "
                        "the provider is from the authorized ranked list."
                    ),
                },
                "provider_id": {
                    "type": "string",
                    "description": (
                        "Required. The provider_id from the rank_providers "
                        "result. Must be one of the providers in the ranked list "
                        "returned by the navigation workflow."
                    ),
                },
                "patient_id": {
                    "type": "string",
                    "description": "Required. The patient's unique identifier.",
                },
                "date_range": {
                    "type": "string",
                    "description": (
                        "Optional. Date range for availability search. "
                        "Default: 'next_7_days'. Examples: 'next_7_days', "
                        "'next_14_days', 'next_30_days'."
                    ),
                },
                "preferred_date": {
                    "type": "string",
                    "description": (
                        "Optional. ISO-8601 date string (e.g. '2026-08-25') "
                        "for patient's preferred appointment date."
                    ),
                },
                "preferred_time": {
                    "type": "string",
                    "description": (
                        "Optional. Preferred time of day. Examples: 'morning', "
                        "'afternoon', '09:00', '14:30'."
                    ),
                },
            },
            "required": ["recommendation_id", "provider_id", "patient_id"],
        },
    },
}


# ===========================================================================
# 5. cancel_appointment
# ===========================================================================

CANCEL_APPOINTMENT_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "cancel_appointment",
        "description": (
            "Cancel an existing appointment. The patient will lose the "
            "booked slot and it will become available to other patients. "
            "Use this tool when the patient explicitly requests cancellation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Required. The patient's unique identifier.",
                },
                "appointment_id": {
                    "type": "string",
                    "description": (
                        "Required. The appointment_id of the appointment "
                        "to cancel."
                    ),
                },
            },
            "required": ["patient_id", "appointment_id"],
        },
    },
}


# ===========================================================================
# ALL_TOOLS — pass directly to NvidiaClient.chat(tools=ALL_TOOLS)
# ===========================================================================

ALL_TOOLS: List[Dict[str, Any]] = [
    # Navigation tools (existing)
    CLASSIFY_CARE_TOOL_DEF,
    GEOCODE_LOCATION_TOOL_DEF,
    DISCOVER_PROVIDERS_TOOL_DEF,
    RANK_PROVIDERS_TOOL_DEF,
    # Appointment tools (NEW)
    CHECK_AVAILABILITY_TOOL_DEF,
    BOOK_APPOINTMENT_TOOL_DEF,
    RESCHEDULE_APPOINTMENT_TOOL_DEF,
    CANCEL_APPOINTMENT_TOOL_DEF,
]


# ===========================================================================
# Appointment tool executor functions
# ===========================================================================

def execute_check_availability(
    recommendation_id: str,
    provider_id: str,
    patient_id: str,
    date_range: str = "next_7_days",
    preferred_date: Optional[str] = None,
    preferred_time: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute availability check tool.
    
    Steps:
    1. Retrieve CareDecision from RecommendationStore using recommendation_id
    2. Validate provider_id is in the recommendation's ranked provider list
    3. Extract care_type and specialty from CareDecision
    4. Build patient_context with location and preferences if available
    5. Call AppointmentAgentClient.get_availability() with extracted context
    6. Return slots as {"ok": true, "slots": [...]} or error envelope
    
    Parameters
    ----------
    recommendation_id : str
        The recommendation ID from the navigation workflow that authorized
        this provider selection. Used to retrieve the trusted CareDecision.
    provider_id : str
        The provider_id from the rank_providers result. Must be one of the
        providers in the ranked list.
    patient_id : str
        The patient's unique identifier.
    date_range : str
        Date range for availability search. Default: 'next_7_days'.
    preferred_date : str | None
        Optional ISO-8601 date string (e.g. '2026-08-25') for patient's
        preferred appointment date.
    preferred_time : str | None
        Optional preferred time of day. Examples: 'morning', 'afternoon',
        '09:00', '14:30'.
    
    Returns
    -------
    dict
        Success envelope: {"ok": true, "provider_id": "...", "provider_name": "...",
                          "care_type": "...", "specialty": "...", "count": N,
                          "slots": [...]}
        Error envelope: {"ok": false, "error": "<descriptive_message>"}
    
    Error cases
    -----------
    - recommendation_id not found or expired → {"ok": false, "error": "..."}
    - provider_id not in recommendation → {"ok": false, "error": "..."}
    - HTTP errors from AppointmentAgentClient → {"ok": false, "error": "..."}
    """
    try:
        # Import here to avoid circular dependency at module level
        from api.recommendation_store import recommendation_store
        from appointment.client import AppointmentAgentClient
        from appointment.schemas import (
            AppointmentPatientContext,
            AppointmentPreferences,
        )
        
        # Retrieve trusted recommendation
        recommendation = recommendation_store.require(recommendation_id)
        
        # Validate provider is authorized
        provider = None
        for p in recommendation.top_providers:
            if p.provider_id == provider_id:
                provider = p
                break
        
        if provider is None:
            logger.warning(
                "check_availability: provider %s not found in recommendation %s",
                provider_id,
                recommendation_id,
            )
            return {
                "ok": False,
                "error": (
                    f"Provider {provider_id} not found in recommendation "
                    f"{recommendation_id}"
                ),
            }
        
        # Extract care context from CareDecision
        care_type = recommendation.decision.destination
        specialty = recommendation.decision.specialty
        
        # Retrieve patient location context if available
        patient_location = recommendation_store.get_patient_location(recommendation_id)
        patient_context = None
        if patient_location:
            patient_context = AppointmentPatientContext(
                latitude=patient_location.latitude,
                longitude=patient_location.longitude,
                preferences=AppointmentPreferences(
                    preferred_date=preferred_date,
                    preferred_time=preferred_time,
                ),
            )
        
        # Call external appointment service
        appointment_client = AppointmentAgentClient()
        slots = appointment_client.get_availability(
            provider_id=provider_id,
            care_type=care_type,
            specialty=specialty,
            date_range=date_range,
            patient_id=patient_id,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            patient_context=patient_context,
        )
        
        logger.info(
            "check_availability: recommendation_id=%s provider_id=%s result=success count=%d",
            recommendation_id,
            provider_id,
            len(slots),
        )
        
        return {
            "ok": True,
            "provider_id": provider_id,
            "provider_name": provider.name,
            "care_type": care_type,
            "specialty": specialty,
            "count": len(slots),
            "slots": [s.model_dump() for s in slots],
        }
        
    except KeyError as exc:
        logger.warning("check_availability: recommendation lookup failed: %s", exc)
        return {
            "ok": False,
            "error": "Recommendation not found or expired",
        }
    except requests.HTTPError as exc:
        logger.warning("check_availability: HTTP error: %s", exc)
        status_code = exc.response.status_code if exc.response else "unknown"
        return {
            "ok": False,
            "error": f"Appointment service unavailable: {status_code}",
        }
    except Exception as exc:
        logger.warning("check_availability: unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


def execute_book_appointment(
    recommendation_id: str,
    patient_id: str,
    provider_id: str,
    slot_id: str,
) -> Dict[str, Any]:
    """Execute appointment booking tool.
    
    Steps:
    1. Retrieve CareDecision from RecommendationStore using recommendation_id
    2. Validate provider_id is authorized (in recommendation's provider list)
    3. Extract specialty from CareDecision
    4. Build BookingRequest with all internal fields (includes recommendation_id)
    5. Call AppointmentAgentClient.book() which strips recommendation_id before HTTP call
    6. Return confirmation as {"ok": true, "appointment_id": "...", "status": "...", ...}
    
    Contract gap handling:
    - provider_id and slot_id are NOT forwarded to external service
    - Only patient_id, specialty, preferred_date/time go in the envelope
    - AppointmentAgentClient.book() handles stripping recommendation_id before HTTP call
    
    Parameters
    ----------
    recommendation_id : str
        Required. The recommendation ID from the navigation workflow. Used to
        validate the provider and retrieve the care_type and specialty.
    patient_id : str
        Required. The patient's unique identifier.
    provider_id : str
        Required. The provider_id from check_availability. Must match a provider
        in the recommendation.
    slot_id : str
        Required. The slot_id from the check_availability result that the patient
        selected.
    
    Returns
    -------
    dict
        Success envelope: {"ok": true, "appointment_id": "...", "status": "BOOKED",
                          "provider_id": "...", "slot": {...}}
        Error envelope: {"ok": false, "error": "<descriptive_message>"}
    
    Error cases
    -----------
    - recommendation_id not found → {"ok": false, "error": "Recommendation not found or expired"}
    - provider_id not authorized → {"ok": false, "error": "Provider X not authorized"}
    - HTTP errors from AppointmentAgentClient → {"ok": false, "error": "Booking failed: <status>"}
    """
    try:
        # Import here to avoid circular dependency at module level
        from api.recommendation_store import recommendation_store
        from appointment.client import AppointmentAgentClient
        from models.schemas import BookingRequest
        import requests
        
        logger.info(
            "book_appointment: recommendation_id=%s patient_id=%s provider_id=%s slot_id=%s",
            recommendation_id,
            patient_id,
            provider_id,
            slot_id,
        )
        
        # Retrieve and validate authorization
        recommendation = recommendation_store.require(recommendation_id)
        provider = recommendation_store.require_provider(recommendation_id, provider_id)
        
        # Extract care context
        specialty = recommendation.decision.specialty
        
        # Build internal request (recommendation_id stays internal)
        request = BookingRequest(
            patient_id=patient_id,
            recommendation_id=recommendation_id,
            provider_id=provider_id,
            slot_id=slot_id,
        )
        
        # Call AppointmentAgentClient
        # Note: client.book() strips recommendation_id before HTTP call
        appointment_client = AppointmentAgentClient()
        confirmation = appointment_client.book(
            request=request,
            specialty=specialty,
        )
        
        logger.info(
            "book_appointment: success - appointment_id=%s status=%s provider_id=%s",
            confirmation.appointment_id,
            confirmation.status,
            confirmation.provider_id,
        )
        
        return {
            "ok": True,
            "appointment_id": confirmation.appointment_id,
            "status": confirmation.status,
            "provider_id": confirmation.provider_id,
            "slot": confirmation.slot.model_dump(),
        }
        
    except KeyError as exc:
        logger.warning("book_appointment: authorization failed: %s", exc)
        # Extract more specific error message
        error_msg = str(exc)
        if "not part of recommendation" in error_msg:
            return {"ok": False, "error": f"Provider {provider_id} not authorized"}
        return {"ok": False, "error": "Recommendation not found or expired"}
    except requests.HTTPError as exc:
        logger.warning("book_appointment: HTTP error: %s", exc)
        status_code = exc.response.status_code if exc.response else "unknown"
        return {
            "ok": False,
            "error": f"Booking failed: {status_code}",
        }
    except Exception as exc:
        logger.warning("book_appointment: unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


def execute_reschedule_appointment(
    patient_id: str,
    appointment_id: str,
    recommendation_id: Optional[str] = None,
    new_slot_id: Optional[str] = None,
    preferred_date: Optional[str] = None,
    preferred_time: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute appointment rescheduling tool.
    
    Supports two workflows:
    A. Direct slot selection: new_slot_id provided
    B. Preference-based: preferred_date/preferred_time provided
    
    Steps:
    1. Validate at least one of new_slot_id or preferred_date/time present
    2. Build RescheduleRequest
    3. Call AppointmentAgentClient.reschedule()
    4. Return updated appointment confirmation
    
    Parameters
    ----------
    patient_id : str
        Required. The patient's unique identifier.
    appointment_id : str
        Required. The appointment_id of the existing appointment to reschedule.
    recommendation_id : str | None
        Optional. The recommendation ID if available. May be absent if the
        original recommendation expired.
    new_slot_id : str | None
        Optional (Workflow A). The slot_id of the new slot chosen from
        check_availability results.
    preferred_date : str | None
        Optional (Workflow B). ISO-8601 date string for the patient's preferred
        new appointment date.
    preferred_time : str | None
        Optional (Workflow B). Preferred time of day for the rescheduled appointment.
    
    Returns (success)
    -----------------
    {
        "ok": True,
        "appointment_id": str,
        "status": "RESCHEDULED",
        "provider_id": str,
        "slot": {...}
    }
    
    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }
    
    Failure cases
    -------------
    - Neither new_slot_id nor preferences provided → "error"
    - HTTP errors from AppointmentAgentClient → "error"
    
    Note
    ----
    recommendation_id is optional because it may have expired from
    RecommendationStore after the initial booking.
    """
    try:
        # Validate workflow parameters
        has_slot = bool(new_slot_id)
        has_preference = bool(preferred_date or preferred_time)
        if not has_slot and not has_preference:
            logger.warning(
                "reschedule_appointment: neither new_slot_id nor preferences provided "
                "for appointment_id=%s",
                appointment_id,
            )
            return {
                "ok": False,
                "error": (
                    "reschedule_appointment requires either new_slot_id "
                    "or preferred_date/preferred_time"
                )
            }
        
        logger.info(
            "reschedule_appointment: patient_id=%s appointment_id=%s recommendation_id=%s "
            "new_slot_id=%s preferred_date=%s preferred_time=%s",
            patient_id,
            appointment_id,
            recommendation_id,
            new_slot_id,
            preferred_date,
            preferred_time,
        )
        
        # Build request
        request = RescheduleRequest(
            patient_id=patient_id,
            appointment_id=appointment_id,
            recommendation_id=recommendation_id,
            new_slot_id=new_slot_id,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
        )
        
        # Call external service
        confirmation = _appointment_client.reschedule(request)
        
        logger.info(
            "reschedule_appointment: success for appointment_id=%s status=%s",
            confirmation.appointment_id,
            confirmation.status,
        )
        
        return {
            "ok": True,
            "appointment_id": confirmation.appointment_id,
            "status": confirmation.status,
            "provider_id": confirmation.provider_id,
            "slot": confirmation.slot.model_dump(),
        }
        
    except requests.HTTPError as exc:
        logger.warning(
            "reschedule_appointment: HTTP error for appointment_id=%s: %s",
            appointment_id,
            exc,
        )
        status_code = exc.response.status_code if exc.response else "unknown"
        return {
            "ok": False,
            "error": f"Rescheduling failed: {status_code}"
        }
    except Exception as exc:
        logger.warning(
            "reschedule_appointment: unexpected error for appointment_id=%s: %s",
            appointment_id,
            exc,
        )
        return {"ok": False, "error": str(exc)}


def execute_cancel_appointment(
    patient_id: str,
    appointment_id: str,
) -> Dict[str, Any]:
    """Execute appointment cancellation tool.
    
    Steps:
    1. Build CancellationRequest with patient_id and appointment_id
    2. Call AppointmentAgentClient.cancel_appointment()
    3. Return status confirmation as {"ok": true, "appointment_id": "...", 
       "status": "CANCELLED", "patient_id": "..."}
    
    Error cases:
    - HTTP errors from AppointmentAgentClient → {"ok": false, "error": "..."}
    - Any other exception → {"ok": false, "error": "..."}
    
    Parameters
    ----------
    patient_id : str
        Required. The patient's unique identifier.
    appointment_id : str
        Required. The appointment_id of the appointment to cancel.
    
    Returns (success)
    -----------------
    {
        "ok": True,
        "appointment_id": str,
        "status": "CANCELLED",
        "patient_id": str
    }
    
    Returns (failure)
    -----------------
    {
        "ok": False,
        "error": str
    }
    """
    try:
        from appointment.client import AppointmentAgentClient
        from appointment.schemas import CancellationRequest
        import requests
        
        logger.info(
            "cancel_appointment: patient_id=%s, appointment_id=%s",
            patient_id,
            appointment_id
        )
        
        # Build cancellation request
        request = CancellationRequest(
            patient_id=patient_id,
            appointment_id=appointment_id,
        )
        
        # Call external appointment service
        appointment_client = AppointmentAgentClient()
        status = appointment_client.cancel_appointment(request)
        
        logger.info(
            "cancel_appointment: success - appointment_id=%s, status=%s",
            status.appointment_id,
            status.status
        )
        
        return {
            "ok": True,
            "appointment_id": status.appointment_id,
            "status": status.status,
            "patient_id": status.patient_id,
        }
        
    except requests.HTTPError as exc:
        error_msg = f"Cancellation failed: {exc.response.status_code}"
        logger.warning("cancel_appointment: HTTP error: %s", exc)
        return {
            "ok": False,
            "error": error_msg
        }
    except Exception as exc:
        logger.warning("cancel_appointment: unexpected error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ===========================================================================
# execute_tool — dispatcher for the agent loop
# ===========================================================================

# Maps tool name → callable.  Both the callable and the name in this dict
# must match the "name" key in the corresponding *_TOOL_DEF exactly.
_TOOL_REGISTRY: Dict[str, Any] = {
    # Navigation tools (existing)
    # classify_care takes a single `patient_features` dict — the LLM sends the
    # patient fields as top-level arguments, so we pack them back into the
    # expected parameter rather than unpacking them onto the function signature.
    "classify_care":           lambda **kwargs: classify_care(kwargs),
    "geocode_location":        geocode_location,
    "discover_providers":      discover_providers,
    "rank_providers":          rank_providers,
    
    # Appointment tools (NEW)
    "check_availability":      execute_check_availability,
    "book_appointment":        execute_book_appointment,
    "reschedule_appointment":  execute_reschedule_appointment,
    "cancel_appointment":      execute_cancel_appointment,
}


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a tool call from the LLM agent loop.

    The agent loop receives a ToolCall with a name and a JSON arguments
    string.  After parsing the JSON string to a dict, it calls this
    function to execute the appropriate tool.

    Parameters
    ----------
    name : str
        Tool name exactly as it appears in ALL_TOOLS ("classify_care",
        "geocode_location", "discover_providers", "rank_providers").
    arguments : dict
        Already-parsed arguments dict (not the raw JSON string).

    Returns
    -------
    dict
        Always a JSON-serializable dict.  On success: {"ok": True, ...}.
        On unknown tool name: {"ok": False, "error": "Unknown tool: <name>"}.
        On individual tool failure: {"ok": False, "error": <message>}.

    Example
    -------
        import json
        from llm.nvidia_client import ToolCall
        from agents.tools.navigation_tools import execute_tool

        tc: ToolCall = ...   # from LLMResponse.tool_calls
        result = execute_tool(tc.name, json.loads(tc.arguments))
    """
    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        logger.warning("execute_tool: unknown tool name %r", name)
        return {"ok": False, "error": f"Unknown tool: {name!r}"}

    logger.debug("execute_tool: calling %s with args %s", name, arguments)
    return fn(**arguments)
