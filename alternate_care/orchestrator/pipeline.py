"""
SUPERSEDED by orchestrator/graph.py (LangGraph) as of the LangChain/LangGraph
migration — api/routes.py now calls the graph, not this module. Kept here
as a dependency-free fallback: use this directly if you ever need
classify+discover+rank with zero LangChain/LangGraph/LLM involvement
(e.g. a CI test environment, or if the LLM explanation step is down).

Orchestrator for the 3-stage scope you actually described:

    1. Classify: PCP / URGENT_CARE / SPECIALIST(+specialty) / TELEHEALTH
    2. Match nearby providers using patient location (already collected upstream)
    3. Hand off to the shared Appointment Agent for slots/booking

Kept as a plain function pipeline rather than a LangGraph graph. With only
three stages and no branching that needs an LLM to decide, LangGraph would
add orchestration overhead without buying anything — reach for
orchestrator/graph.py (stub included) only if your team standardizes on
LangGraph across agents for consistency, or once this pipeline grows
branches/retries that benefit from a graph's state handling.
"""

from __future__ import annotations

from app.services.alternate_care.models.schemas import PatientFeatures, PatientLocation, Recommendation
from app.services.alternate_care.engine.care_classifier import CareClassifier
from app.services.alternate_care.location.provider_discovery import find_nearby_providers
from app.services.alternate_care.location.ranking import rank_providers

_classifier = CareClassifier()  # loads rules once per process


def build_recommendation(
    patient: PatientFeatures,
    location: PatientLocation,
) -> Recommendation:
    # Stage 1 — classify (destination + specialty in one pass)
    decision = _classifier.classify(patient)

    # Stage 2 — discover + rank nearby providers (skipped for TELEHEALTH,
    # which has no physical location — see provider_discovery.py)
    candidates = find_nearby_providers(location, decision.destination, decision.specialty)
    top_providers = rank_providers(
        location.latitude,
        location.longitude,
        candidates,
        has_pcp_flag=patient.has_pcp_flag,
    )

    # Stage 3 (booking) is intentionally NOT called here — that's the
    # shared Appointment Agent's job (appointment/client.py), invoked by
    # the API layer once the patient picks a provider from top_providers.
    return Recommendation(decision=decision, top_providers=top_providers)
