"""
Shared state object threaded through every LangGraph node. Keep this the
single source of truth for "what the graph knows at each step" — nodes
read what they need and write only the keys they own.
"""

from __future__ import annotations
from typing import TypedDict, Optional, List

from app.services.alternate_care.models.schemas import PatientFeatures, PatientLocation, CareDecision, ProviderCandidate


class NavigationState(TypedDict, total=False):
    # inputs
    patient: PatientFeatures
    location: PatientLocation

    # written by classify_node
    decision: CareDecision

    # written by rank_node
    ranked_providers: List[ProviderCandidate]

    # written by explain_node (LLM)
    patient_facing_explanation: Optional[str]

    # error channel — nodes append here instead of raising, so the graph
    # can still return a partial/safe result (e.g. fall back to PCP
    # messaging if the LLM explanation call fails)
    errors: List[str]
