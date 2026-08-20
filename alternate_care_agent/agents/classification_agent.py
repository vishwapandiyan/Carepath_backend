"""
THE MAIN ALTERNATE CARE AGENT.

This is the entry-point decision-maker: given patient features, it outputs
one of PCP / URGENT_CARE / SPECIALIST(+specialty) / TELEHEALTH. It is a
thin, named wrapper around engine/care_classifier.py — the wrapper exists
so this component has a clear identity as "the main agent" inside the
LangGraph graph and can be swapped/extended (e.g. add an LLM disambiguation
step for edge cases) without touching the underlying rule engine.
"""

from __future__ import annotations

from models.schemas import PatientFeatures, CareDecision
from engine.care_classifier import CareClassifier


class AlternateCareAgent:
    """The main agent. Deterministic rule-engine-backed (V1), per the
    reference doc's own recommendation not to put the core care decision
    behind an LLM. Swap in a hybrid rule+ML decision here later without
    changing the graph shape — this class's public interface (`decide`)
    is the only contract the rest of the system depends on."""

    def __init__(self):
        self._classifier = CareClassifier()

    def decide(self, patient: PatientFeatures) -> CareDecision:
        return self._classifier.classify(patient)
