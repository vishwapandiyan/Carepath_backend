"""
Intake Service.
Orchestrates: session creation → LLM extraction → feature merge → question policy.

Isolation rule: NEVER import from safety/service.py (or any downstream segment).
Cross-segment communication happens exclusively through the shared session store.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.patient.intake.schemas import (
    LLMExtraction,
    MessageIn,
    MessageResponse,
    SessionCreate,
    SessionOut,
)
from app.core import session_store
from app.services.llm_service import LLMExtractionError, extract_from_message
from app.services.question_policy import next_missing_field

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge_extractions(base: LLMExtraction, incoming: LLMExtraction) -> LLMExtraction:
    """
    Merge incoming extraction into the cumulative base.
    - Scalar fields: incoming non-None value overwrites base.
    - List fields: union (deduplicated, insertion-order preserved).
    """
    base_dict = base.model_dump()
    inc_dict = incoming.model_dump()
    merged: dict = {}
    for field, base_val in base_dict.items():
        inc_val = inc_dict.get(field)
        if isinstance(base_val, list):
            merged[field] = list(dict.fromkeys(base_val + (inc_val or [])))
        else:
            merged[field] = inc_val if inc_val is not None else base_val
    return LLMExtraction(**merged)


def _get_session_or_404(session_id: str) -> dict:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return session


def _build_session_out(session: dict) -> SessionOut:
    s = dict(session)
    raw_features = s.get("features")
    s["features"] = LLMExtraction(**(raw_features or {})) if raw_features else None
    return SessionOut(**s)


# ── Service functions ─────────────────────────────────────────────────────────

async def create_intake_session(payload: SessionCreate) -> SessionOut:
    session = session_store.create_session(patient_id=payload.patient_id)
    # Pre-populate the first question (always chief_complaint)
    first_q = next_missing_field({})
    session_store.update_session(session["session_id"], next_question=first_q)
    session["next_question"] = first_q
    logger.info("Intake session created | session_id=%s | patient_id=%s",
                session["session_id"], payload.patient_id)
    return _build_session_out(session)


async def handle_message(session_id: str, payload: MessageIn) -> MessageResponse:
    session = _get_session_or_404(session_id)

    # Idempotent: return final state if already done
    if session["status"] == "COMPLETE":
        raw = session.get("features") or {}
        return MessageResponse(
            session_id=session_id,
            extracted=LLMExtraction(**raw),
            next_question=None,
            status="COMPLETE",
        )

    # Append patient message to in-memory history
    session_store.append_message(session_id, role="user", content=payload.content)
    history = session_store.get_session(session_id)["messages"]

    # ── LLM extraction (fail-safe) ────────────────────────────────────────────
    try:
        extraction = await extract_from_message(
            session_history=history[:-1],   # exclude the message we just appended
            new_message=payload.content,
        )
    except LLMExtractionError as exc:
        logger.error("LLM failure | session=%s | %s", session_id, exc)
        session_store.update_session(session_id, status="ERROR")
        return MessageResponse(
            session_id=session_id,
            status="ERROR",
            error_detail=str(exc),
        )

    # ── Merge extracted fields into cumulative session features ───────────────
    raw_existing = session.get("features") or {}
    existing = LLMExtraction(**raw_existing) if raw_existing else LLMExtraction()
    merged = _merge_extractions(existing, extraction)
    merged_dict = merged.model_dump()

    next_q = next_missing_field(merged_dict)
    new_status = "COMPLETE" if next_q is None else "IN_PROGRESS"

    session_store.update_session(
        session_id,
        features=merged_dict,
        next_question=next_q,
        status=new_status,
    )

    if next_q:
        session_store.append_message(session_id, role="assistant", content=next_q)

    logger.info(
        "Message handled | session=%s | status=%s | next_q=%s",
        session_id, new_status, next_q,
    )
    return MessageResponse(
        session_id=session_id,
        extracted=merged,
        next_question=next_q,
        status=new_status,
    )


async def get_intake_session(session_id: str) -> SessionOut:
    session = _get_session_or_404(session_id)
    return _build_session_out(session)
