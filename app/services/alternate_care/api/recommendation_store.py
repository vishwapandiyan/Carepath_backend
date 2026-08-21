"""
Short-lived server-side store for navigation recommendations.

The store binds a recommendation_id to the exact CareDecision and ranked
providers produced by the navigation pipeline. Appointment operations use
this binding instead of trusting care_type/specialty/provider_id supplied by
a client as independent values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import Lock
from typing import Dict, Optional

from app.services.alternate_care.models.schemas import Recommendation, ProviderCandidate, PatientLocation


@dataclass
class _StoredRecommendation:
    recommendation: Recommendation
    expires_at: datetime
    patient_location: Optional[PatientLocation] = None


class RecommendationStore:
    """In-memory recommendation store suitable for development/hackathon use."""

    def __init__(self, ttl_minutes: int = 30) -> None:
        if ttl_minutes <= 0:
            raise ValueError("ttl_minutes must be greater than 0")

        self._ttl = timedelta(minutes=ttl_minutes)
        self._items: Dict[str, _StoredRecommendation] = {}
        self._lock = Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _cleanup_expired(self) -> None:
        now = self._now()

        expired = [
            recommendation_id
            for recommendation_id, item in self._items.items()
            if item.expires_at <= now
        ]

        for recommendation_id in expired:
            del self._items[recommendation_id]

    def create(self, recommendation: Recommendation, patient_location: Optional[PatientLocation] = None) -> str:
        """Store a recommendation and return its server-generated ID."""

        recommendation_id = f"rec_{token_urlsafe(12)}"

        if hasattr(recommendation, "model_copy"):
            stored = recommendation.model_copy(
                update={"recommendation_id": recommendation_id}
            )
        else:
            stored = recommendation.copy(
                update={"recommendation_id": recommendation_id}
            )

        with self._lock:
            self._cleanup_expired()

            self._items[recommendation_id] = _StoredRecommendation(
                recommendation=stored,
                expires_at=self._now() + self._ttl,
                patient_location=patient_location,
            )

        return recommendation_id

    def get(self, recommendation_id: str) -> Recommendation | None:
        """Return a valid recommendation, or None when missing/expired."""

        with self._lock:
            self._cleanup_expired()

            item = self._items.get(recommendation_id)

            return item.recommendation if item else None

    def require(self, recommendation_id: str) -> Recommendation:
        """Return a recommendation or raise a clear lookup error."""

        recommendation = self.get(recommendation_id)

        if recommendation is None:
            raise KeyError(
                f"Unknown or expired recommendation_id: {recommendation_id}"
            )

        return recommendation

    def get_patient_location(
        self,
        recommendation_id: str,
    ) -> Optional[PatientLocation]:
        """Return the PatientLocation stored with this recommendation, or None.

        Returns None when:
          - the recommendation_id is unknown or expired (same TTL logic as get())
          - the recommendation was created without a patient_location
            (e.g. by an older caller or a test that omits location)

        Does NOT raise — absence of location is not an error condition.
        Callers should treat None as "no location context available" and
        fall back to the existing appointment behavior.
        """
        with self._lock:
            self._cleanup_expired()
            item = self._items.get(recommendation_id)
            if item is None:
                return None
            return item.patient_location

    def update(self, recommendation_id: str, updates: Dict[str, Any]) -> None:
        """Update an existing recommendation in the store."""
        with self._lock:
            if recommendation_id in self._items:
                stored = self._items[recommendation_id].recommendation
                if hasattr(stored, "model_copy"):
                    updated_rec = stored.model_copy(update=updates)
                else:
                    updated_rec = stored.copy(update=updates)
                self._items[recommendation_id].recommendation = updated_rec

    def get_provider(
        self,
        recommendation_id: str,
        provider_id: str,
    ) -> ProviderCandidate | None:
        """Return provider only if it belongs to the stored recommendation."""

        recommendation = self.get(recommendation_id)

        if recommendation is None:
            return None

        for provider in recommendation.top_providers:
            if provider.provider_id == provider_id:
                return provider

        if recommendation.nearby_providers:
            for p in recommendation.nearby_providers:
                p_id = p.get("provider_id") or p.get("id")
                if p_id == provider_id:
                    return ProviderCandidate(
                        provider_id=p_id,
                        name=p.get("provider_name") or p.get("facility_name") or p.get("name") or "Healthcare Provider",
                        destination_type=recommendation.decision.destination,
                        specialty=recommendation.decision.specialty,
                        latitude=float(p.get("latitude") or 0.0),
                        longitude=float(p.get("longitude") or 0.0),
                        address=p.get("address"),
                        distance_km=p.get("distance_km"),
                        source=p.get("source", "osm")
                    )

        return None

    def require_provider(
        self,
        recommendation_id: str,
        provider_id: str,
    ) -> ProviderCandidate:
        """Validate recommendation existence and provider membership."""

        provider = self.get_provider(recommendation_id, provider_id)
        if provider:
            return provider

        raise KeyError(
            f"Provider '{provider_id}' is not part of recommendation "
            f"'{recommendation_id}'"
        )



recommendation_store = RecommendationStore(ttl_minutes=30)