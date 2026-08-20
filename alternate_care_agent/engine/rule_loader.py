"""
Loads rules/care_destination_rules.yaml and returns rules sorted by
priority (descending) — the file's own convention: "Evaluated in
descending priority order. First matching rule wins."
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import yaml

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "care_destination_rules.yaml"

VALID_DESTINATIONS = {"PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH", "DENTISTRY"}


class RuleFileError(ValueError):
    pass


def load_rules(path: Path = DEFAULT_RULES_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    rules = raw.get("rules", [])
    if not rules:
        raise RuleFileError(f"No rules found in {path}")

    for r in rules:
        for required in ("rule_id", "priority", "destination", "conditions", "status"):
            if required not in r:
                raise RuleFileError(f"Rule missing '{required}': {r.get('rule_id', '?')}")
        if r["destination"] not in VALID_DESTINATIONS:
            raise RuleFileError(
                f"Rule {r['rule_id']} has destination '{r['destination']}' "
                f"outside the 4-destination V1 spec {VALID_DESTINATIONS}."
            )

    # descending priority; ties broken by original file order (stable sort)
    return sorted(rules, key=lambda r: r["priority"], reverse=True)
