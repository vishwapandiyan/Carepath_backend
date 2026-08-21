"""
Deterministic, explainable provider ranking (no ML — matches the V1
recommendation in the design doc: ranking = normal calculation, not a model).
"""

from __future__ import annotations
from math import radians, sin, cos, sqrt, atan2
from typing import List
from app.services.alternate_care.models.schemas import ProviderCandidate


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1 - a))


def rank_providers(
    patient_lat: float,
    patient_lon: float,
    candidates: List[ProviderCandidate],
    has_pcp_flag: int | None = None,
    top_n: int = 5,
) -> List[ProviderCandidate]:
    """Score = mostly distance, with a small continuity bonus if the
    destination is PCP and the patient already has a PCP relationship
    (per doc: has_pcp_flag matters for provider ranking, not the
    destination decision itself)."""
    for c in candidates:
        c.distance_km = round(haversine_km(patient_lat, patient_lon, c.latitude, c.longitude), 2)
        distance_score = max(0.0, 1 - (c.distance_km / 25))  # 0 at 25km+
        continuity_bonus = 0.05 if (c.destination_type == "PCP" and has_pcp_flag) else 0.0
        c.score = round(distance_score + continuity_bonus, 3)

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return ranked[:top_n]
