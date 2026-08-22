"""
Evaluates the `conditions` block of a single rule from
rules/care_destination_rules.yaml against a patient feature dict.

Supported shape (matches the delivered rule file exactly):

conditions:
  all:            # or "any"
    - feature: primary_symptom_category
      operator: equals   # equals | in | gte | lte
      value: back_pain

Kept deliberately small — do not add operators the rule file doesn't use
without updating this module and getting the new rule reviewed, since an
operator silently doing the wrong thing is worse than a missing feature.
"""

from __future__ import annotations
from typing import Any, Dict


_OPERATORS = {
    "equals": lambda actual, value: actual == value,
    "in": lambda actual, value: actual in value,
    "gte": lambda actual, value: actual is not None and actual >= value,
    "lte": lambda actual, value: actual is not None and actual <= value,
}


class UnknownOperatorError(ValueError):
    pass


def _eval_single(condition: Dict[str, Any], patient: Dict[str, Any]) -> bool:
    feature = condition["feature"]
    operator = condition["operator"]
    expected = condition["value"]
    actual = patient.get(feature)

    if operator not in _OPERATORS:
        raise UnknownOperatorError(
            f"Rule uses operator '{operator}' which is not implemented. "
            f"Known operators: {list(_OPERATORS)}"
        )
    try:
        return _OPERATORS[operator](actual, expected)
    except TypeError:
        # e.g. comparing None with gte/lte on a feature the patient payload omitted
        return False


def evaluate_conditions(conditions: Dict[str, Any], patient: Dict[str, Any]) -> bool:
    """conditions is a dict with exactly one of 'all' or 'any', each a list
    of {feature, operator, value} dicts (FALLBACK-999 uses all: [] -> True)."""
    if "all" in conditions:
        return all(_eval_single(c, patient) for c in conditions["all"])
    if "any" in conditions:
        return any(_eval_single(c, patient) for c in conditions["any"])
    raise ValueError("conditions block must contain 'all' or 'any'")
