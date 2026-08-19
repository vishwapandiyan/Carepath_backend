"""
Question Policy — pure function, zero I/O.
Determines which intake question to ask next based on what the LLM has extracted so far.
Unit-testable with no mocks required.
"""

from __future__ import annotations

from app.services.vocabulary import QUESTION_TEMPLATES, REQUIRED_FIELD_ORDER


def next_missing_field(extraction_dict: dict) -> str | None:
    """
    Iterate required fields in priority order.
    Return the question prompt for the first field that is still None.
    Return None when ALL required fields are populated — intake is complete.

    Args:
        extraction_dict: Plain dict from LLMExtraction.model_dump().

    Returns:
        str — question to present to the patient, or
        None — all required fields satisfied, intake complete.
    """
    for field in REQUIRED_FIELD_ORDER:
        value = extraction_dict.get(field)
        if value is None:
            return QUESTION_TEMPLATES.get(
                field, f"Please provide your {field.replace('_', ' ')}."
            )
    return None
