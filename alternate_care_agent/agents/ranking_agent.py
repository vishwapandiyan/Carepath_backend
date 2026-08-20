"""
THE RANKING AGENT.

Runs after the Main Alternate Care Agent. Takes the care decision
(destination + specialty) plus the patient's already-known location, and
produces a ranked shortlist of nearby providers. Internally this is two
steps (discover, then score) but they're one agent/one node from the
graph's point of view — discovery without ranking isn't useful output,
so there's no reason to expose them as two separate LangGraph nodes.

Deterministic (OSM/Overpass lookup + haversine distance scoring) — see
location/provider_discovery.py and location/ranking.py for the mechanics.
No LLM involved here; "ranking agent" refers to its role in the pipeline,
not an LLM-reasoning agent.

Geocoding
---------
If the PatientLocation contains only an address (no coordinates), this
agent resolves it to lat/lon via location.geocoder.resolve_location()
before running discovery or scoring.  This is the single call-site for
geocoding — neither find_nearby_providers nor rank_providers need to know
about it.  Geocoding errors propagate up as GeocodingError subclasses;
the graph's rank_node catches them and records them in state["errors"].
"""

from __future__ import annotations
from typing import List, Tuple

from models.schemas import PatientLocation, CareDecision, ProviderCandidate
import location.provider_discovery as _discovery  # module-attribute lookup keeps patch target stable
import location.geocoder as _geocoder              # module-attribute lookup keeps patch target stable
from location.ranking import rank_providers


class RankingAgent:
    def rank(
        self,
        location: PatientLocation,
        decision: CareDecision,
        has_pcp_flag: int | None = None,
    ) -> Tuple[List[ProviderCandidate], PatientLocation]:
        """Discover and rank nearby providers for the given care decision.

        Returns
        -------
        (ranked_providers, resolved_location)
            resolved_location is the same object as ``location`` when
            coordinates were already present, or a new PatientLocation with
            lat/lon populated after geocoding an address-only input.
        """
        # Resolve address → coordinates if needed.  No-op when lat/lon are
        # already set.  Raises GeocodingError subclasses on failure.
        resolved = _geocoder.resolve_location(location)

        candidates = _discovery.find_nearby_providers(
            resolved, decision.destination, decision.specialty
        )
        ranked = rank_providers(
            resolved.latitude,
            resolved.longitude,
            candidates,
            has_pcp_flag=has_pcp_flag,
        )
        return ranked, resolved
