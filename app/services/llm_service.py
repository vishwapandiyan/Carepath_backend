"""
LLM Service — wraps Google Gemini API for structured medical information extraction.

Fail-safe contract (enforced, not optional):
  - Invalid / partial JSON   → raises LLMExtractionError
  - Schema validation fails  → raises LLMExtractionError
  - Any API error            → raises LLMExtractionError
  NEVER returns partial data. Callers catch and return status=ERROR.
"""

from __future__ import annotations

import json
import logging

import google.generativeai as genai

from app.config import settings
from app.services.vocabulary import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Configure the Gemini client once at module load
genai.configure(api_key=settings.google_api_key)


class LLMExtractionError(Exception):
    """Raised on any LLM failure — invalid JSON, schema mismatch, or API error."""


def _build_prompt(session_history: list[dict], new_message: str) -> str:
    """
    Flatten session history + new message into a single Gemini prompt string.
    Gemini's generate_content accepts a plain string or a list of Parts.
    """
    lines: list[str] = [SYSTEM_PROMPT, ""]
    for msg in session_history:
        role_label = "Patient" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['content']}")
    lines.append(f"Patient: {new_message}")
    lines.append("\nExtracted JSON:")
    return "\n".join(lines)


async def extract_from_message(
    session_history: list[dict],
    new_message: str,
) -> "LLMExtraction":  # noqa: F821 — imported locally to avoid circular import
    """
    Call Google Gemini with session history + the new patient message.
    Returns a validated LLMExtraction instance.
    Raises LLMExtractionError on any failure — caller must handle.
    """
    # Local import breaks the circular dependency between services and schemas
    from app.patient.intake.schemas import LLMExtraction

    prompt = _build_prompt(session_history, new_message)
    raw: str = ""

    try:
        model = genai.GenerativeModel(
            model_name=settings.llm_model,
            generation_config=genai.GenerationConfig(
                temperature=0,                      # deterministic for clinical use
                response_mime_type="application/json",
            ),
        )
        response = await model.generate_content_async(prompt)
        raw = response.text or ""
        if not raw.strip():
            raise LLMExtractionError("Gemini returned an empty response.")
        data: dict = json.loads(raw)

    except json.JSONDecodeError as exc:
        logger.error("Gemini JSON parse error | raw=%r | err=%s", raw, exc)
        raise LLMExtractionError(f"Gemini returned invalid JSON: {exc}") from exc
    except LLMExtractionError:
        raise
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        raise LLMExtractionError(f"Gemini API error: {exc}") from exc

    try:
        return LLMExtraction(**data)
    except Exception as exc:
        logger.error("Schema validation failed | data=%s | err=%s", data, exc)
        raise LLMExtractionError(f"LLM output failed schema validation: {exc}") from exc
