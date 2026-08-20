"""
Shared data models for the Alternate Care Navigation Agent.

Scope:
This agent receives patients already classified as no-ED by the upstream
ED-avoidance component. ED/red-flag detection is outside this agent.
"""

from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, model_validator


Destination = Literal["PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH", "DENTISTRY"]


class PatientFeatures(BaseModel):
    """Patient features consumed by the alternate-care routing rules.

    ED/red-flag fields are intentionally not part of this model because
    ED classification is handled upstream.
    """

    primary_symptom_category: str
    pain_level_self_reported: Optional[int] = None
    pain_onset: Optional[str] = None
    pain_duration: Optional[str] = None
    pain_location: Optional[str] = None
    symptom_trend: Optional[str] = None

    # chronic disease context
    copd_asthma_flag: Optional[int] = 0
    cardiac_history_flag: Optional[int] = 0
    diabetes_flag: Optional[int] = 0
    ckd_flag: Optional[int] = 0
    cancer_flag: Optional[int] = 0
    immunocompromised_flag: Optional[int] = 0
    hypertension_flag: Optional[int] = 0
    chronic_condition_count: Optional[int] = 0
    charlson_comorbidity_index: Optional[int] = 0

    # utilization / continuity
    ed_visits_past_year: Optional[int] = 0
    admissions_past_year: Optional[int] = 0
    has_pcp_flag: Optional[int] = None

    # demographics (used cautiously — never as a primary router)
    age: Optional[int] = None
    gender: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class PatientLocation(BaseModel):
    """Patient location for provider search.

    The caller may supply coordinates directly, a U.S. address string, or
    both.  Supported address forms:
      - Street address: "123 Main St, Springfield, IL 62701"
      - City/state:     "Boston, MA"
      - ZIP code:       "10001"

    Resolution rules
    ----------------
    - If ``latitude`` and ``longitude`` are both provided they are used
      as-is; no geocoding is performed.
    - If only ``address`` is provided, the pipeline geocodes it via the
      location.geocoder module before the Overpass search runs.
    - Supplying both coordinates and an address is valid; coordinates take
      precedence and the address is stored for display purposes only.
    - At least one of (latitude + longitude) or address must be present.
    """

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = 15.0
    address: Optional[str] = None
    """Free-text U.S. location: street address, city/state, or ZIP code."""

    @model_validator(mode="after")
    def _require_coords_or_address(self) -> "PatientLocation":
        has_coords = self.latitude is not None and self.longitude is not None
        has_address = bool(self.address and self.address.strip())
        if not has_coords and not has_address:
            raise ValueError(
                "PatientLocation requires either (latitude + longitude) "
                "or a non-empty address string."
            )
        return self


class CareDecision(BaseModel):
    rule_id: str
    priority: int
    destination: Destination
    specialty: Optional[str] = None
    status: str
    explanation: str


class ProviderCandidate(BaseModel):
    provider_id: str
    name: str
    destination_type: Destination
    specialty: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    distance_km: Optional[float] = None
    score: Optional[float] = None
    source: str = "osm"


class Recommendation(BaseModel):
    """Trusted output connecting navigation/ranking to appointment actions."""
    recommendation_id: str
    decision: CareDecision
    top_providers: List[ProviderCandidate]


class AppointmentSlot(BaseModel):
    slot_id: str
    provider_id: str
    start_time: str
    end_time: str


class AppointmentAvailabilityRequest(BaseModel):
    """Request for availability tied to a previously issued recommendation.

    patient_id is optional for backward compatibility with existing callers
    that predate Step 9B.  When supplied it is forwarded to the external
    Shared Appointment Agent as the top-level patient identifier.
    """
    recommendation_id: str
    provider_id: str
    date_range: str = "next_7_days"
    patient_id: Optional[str] = None


class BookingRequest(BaseModel):
    """Booking request tied to the recommendation that authorized the provider."""
    patient_id: str
    recommendation_id: str
    provider_id: str
    slot_id: str


class BookingConfirmation(BaseModel):
    appointment_id: str
    status: str
    provider_id: str
    slot: AppointmentSlot