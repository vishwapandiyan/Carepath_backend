"""
Safety Engine — pure function, zero I/O.
Evaluates patient red flags against an externalized JSON rule set.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL FAIL-SAFE — READ BEFORE MODIFYING                                 ║
║  This function MUST raise SafetyEngineError on any internal failure.        ║
║  It MUST NEVER silently return result='NO' when an exception has occurred.  ║
║  A silent NO is a patient safety defect, not just a code bug.               ║
║  The caller catches SafetyEngineError and writes result='ERROR'.            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Design Intent
─────────────
This engine is for EMERGENCY TRIAGE ONLY.
Output is binary: YES (→ Emergency Room) or NO (→ downstream ML pathway).
Unanswered fields (None) are treated as False — the patient did not report
the symptom, so it does not trigger. The checklist wording in safety_rules.json
is already severity-encoded, so a patient who checks YES is self-declaring a
severe, emergency-level presentation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SafetyEngineError(Exception):
    """Raised on any internal error in the safety engine. Caller writes ERROR, never NO."""


def evaluate_safety(
    session_id: str,
    red_flags: dict,
    rules: list[dict],
) -> dict:
    """
    Evaluate red_flags dict against the rules list.

    Args:
        session_id: Used only for structured logging.
        red_flags:  dict representation of RedFlagsIn (call .model_dump()).
        rules:      Loaded list of rule dicts from safety_rules.json.

    Returns:
        {
            "result":          "YES" | "NO",
            "next_action":     "EMERGENCY_PATHWAY" | "CMS_ML",
            "triggered_rules": [rule_id, ...],
        }

    Raises:
        SafetyEngineError — on malformed rules or any unexpected error.
        NEVER returns result='NO' if an exception has occurred.

    None-handling:
        A field value of None means the patient did not answer that question.
        None is treated as False — absence of a self-reported severe symptom
        does not trigger the emergency pathway.
    """
    if not isinstance(rules, list):
        raise SafetyEngineError("Rules must be a non-empty list of rule dicts.")

    triggered: list[str] = []

    for rule in rules:
        try:
            field: str = rule["field"]
            trigger_value: bool = rule["trigger_value"]
            rule_id: str = rule["rule_id"]
        except KeyError as exc:
            raise SafetyEngineError(
                f"Malformed rule — missing required key {exc}: {rule}"
            ) from exc

        # None → treat as False (not reported = not triggered)
        field_value = red_flags.get(field) or False

        if field_value == trigger_value:
            triggered.append(rule_id)

    # ── Determine outcome ──────────────────────────────────────────────────────
    if triggered:
        logger.info(
            "Safety | session=%s | result=YES | triggered=%s", session_id, triggered
        )
        return {
            "result": "YES",
            "next_action": "EMERGENCY_PATHWAY",
            "triggered_rules": triggered,
        }

    logger.info("Safety | session=%s | result=NO", session_id)
    return {
        "result": "NO",
        "next_action": "CMS_ML",
        "triggered_rules": [],
    }
