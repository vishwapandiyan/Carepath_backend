"""
Care Classification + Specialty Routing — fused into ONE engine.

Design note (read this before "fixing" the architecture):
Generic advice on building this kind of agent often suggests two separate
stages — a Care Type Classifier, then a Specialty Router that only runs
when destination == SPECIALIST. That's a reasonable *default* pattern, but
it is not how rules/care_destination_rules.yaml is actually written: every
rule in that file already sets `destination` AND `specialty` together
(specialty is simply null for non-specialist rules), evaluated as one
flat, priority-ordered, first-match-wins list. Splitting that into two
passes here would just re-implement the same lookup twice and risk the
two passes disagreeing. So: one classifier, one pass, matching the rule
file's own evaluation contract exactly.

Known inconsistency to flag to your team (not silently "fixed" here):
`routing_rule_matrix.md` describes SAFETY-000 conceptually as
`ESCALATE_TO_ED`, but the actual YAML (the file this code runs against)
sets `destination: URGENT_CARE` for SAFETY-000. This code follows the
YAML, since that's the executable source of truth — but your team should
resolve which one is intended before this rule is ever activated for real
patients (it's tagged RECOMMENDED_REQUIRES_VALIDATION either way, and per
the file's own scope_note, red-flag patients should never reach this
agent at all if the upstream filter is doing its job).
"""

from __future__ import annotations
from typing import Any, Dict, List

from models.schemas import CareDecision, PatientFeatures
from engine.rule_loader import load_rules
from engine.condition_evaluator import evaluate_conditions


class CareClassifier:
    def __init__(self, rules: List[Dict[str, Any]] | None = None):
        self.rules = rules if rules is not None else load_rules()

    def classify(self, patient: PatientFeatures) -> CareDecision:
        patient_dict = patient.model_dump()
        for rule in self.rules:  # already sorted, highest priority first
            if evaluate_conditions(rule["conditions"], patient_dict):
                return CareDecision(
                    rule_id=rule["rule_id"],
                    priority=rule["priority"],
                    destination=rule["destination"],
                    specialty=rule.get("specialty"),
                    status=rule["status"],
                    explanation=rule["explanation"].strip(),
                )
        # Should be unreachable — FALLBACK-999 (conditions: all: []) always
        # matches — but fail loudly instead of returning a fabricated default.
        raise RuntimeError(
            "No rule matched, including FALLBACK-999. Check rules/care_destination_rules.yaml."
        )
