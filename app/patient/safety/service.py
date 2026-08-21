"""
Safety Service.
Orchestrates: red-flag persistence → safety engine → PostgreSQL audit log.

Isolation rule: NEVER import from intake/service.py.
Reads session patient_id from session_store (shared state). Writes only to
safety_assessments (owned by this segment).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.patient.safety.schemas import RedFlagsIn, RedFlagsOut, SafetyResult
from app.patient.pathway.service import run_pathway
from app.patient.pathway.schemas import PathwayRequest, PathwayResponse
from app.models.ehr import PatientEHR
from app.config import settings
from app.core import session_store
from app.db.models import SafetyAssessment
from app.services.safety_engine import SafetyEngineError, evaluate_safety

logger = logging.getLogger(__name__)

# ── Rule loader (cached after first read) ─────────────────────────────────────
_rules_cache: list[dict] | None = None


def _load_rules() -> list[dict]:
    global _rules_cache
    if _rules_cache is None:
        path = Path(settings.safety_rules_path)
        if not path.exists():
            raise FileNotFoundError(f"Safety rules file not found: {path}")
        _rules_cache = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded %d safety rules from %s", len(_rules_cache), path)
    return _rules_cache


def _get_session_or_404(session_id: str) -> dict:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return session


async def _get_ehr_for_patient(patient_id: str, db: AsyncSession) -> Optional[PatientEHR]:
    conds = [
        PatientEHR.patient_id == patient_id,
        PatientEHR.mrn == patient_id,
    ]
    if patient_id.isdigit():
        conds.append(PatientEHR.id == int(patient_id))

    query = select(PatientEHR).where(or_(*conds))
    result = await db.execute(query)
    return result.scalars().first()


# ── Service functions ─────────────────────────────────────────────────────────

async def save_red_flags(session_id: str, payload: RedFlagsIn) -> RedFlagsOut:
    """
    Persist red-flag answers to the in-memory session.
    """
    _get_session_or_404(session_id)
    session_store.update_session(session_id, red_flags=payload.model_dump())
    logger.info("Red flags saved | session=%s", session_id)
    return RedFlagsOut(session_id=session_id, saved_at=datetime.now(timezone.utc))


async def run_safety_engine(session_id: str, db: AsyncSession) -> SafetyResult:
    """
    Run the deterministic binary safety engine and write an immutable audit row.

    Output is always YES or NO:
      YES → EMERGENCY_PATHWAY  (any red flag triggered)
      NO  → CMS_ML             (no red flags triggered; route to best_avoidable ML model)

    Every call — including ERROR — produces a PostgreSQL audit record.
    """
    session = _get_session_or_404(session_id)
    patient_id: str = session["patient_id"]
    red_flags_raw: dict | None = session.get("red_flags")

    if red_flags_raw is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No red-flag data found for this session. Call /red-flags first.",
        )

    rules = _load_rules()
    now = datetime.now(timezone.utc)

    # ── Run engine (fail-safe) ────────────────────────────────────────────────
    result_dict: dict
    error_detail: str | None = None

    try:
        result_dict = evaluate_safety(
            session_id=session_id,
            red_flags=red_flags_raw,
            rules=rules,
        )
    except SafetyEngineError as exc:
        logger.error("Safety engine error | session=%s | %s", session_id, exc)
        error_detail = str(exc)
        result_dict = {
            "result": "ERROR",
            "next_action": "ERROR",
            "triggered_rules": [],
        }
    except Exception as exc:
        logger.exception("Unexpected safety engine failure | session=%s", session_id)
        error_detail = f"Unexpected error: {exc}"
        result_dict = {
            "result": "ERROR",
            "next_action": "ERROR",
            "triggered_rules": [],
        }

    # ── Write audit record (always, including ERROR) ──────────────────────────
    try:
        audit = SafetyAssessment(
            session_id=session_id,
            patient_id=patient_id,
            result=result_dict["result"],
            next_action=result_dict["next_action"],
            triggered_rules=result_dict["triggered_rules"],
            missing_information=[],
            red_flags_snapshot=red_flags_raw,
            error_detail=error_detail,
            evaluated_at=now,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(audit)
    except Exception as exc:
        logger.error("DB write failed for safety audit | session=%s | %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable — assessment not persisted.",
        ) from exc

    if result_dict["result"] == "ERROR":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Safety engine error: {error_detail}",
        )

    # ── Handoff to best_avoidable ML model when result is NO (CMS_ML) ──────────
    pathway_res: Optional[PathwayResponse] = None
    if result_dict["result"] == "NO":
        try:
            intake_features = session.get("features") or {}
            ehr_data = await _get_ehr_for_patient(patient_id, db)
            
            pathway_req = PathwayRequest(
                patient_id=patient_id,
                chief_complaint=intake_features.get("chief_complaint"),
                symptom_onset=intake_features.get("symptom_onset"),
                pain_scale=intake_features.get("pain_scale", 0),
                location=intake_features.get("location"),
                red_flag_answers=red_flags_raw,
            )
            pathway_res = run_pathway(
                patient_id=patient_id,
                request=pathway_req,
                ehr_data=ehr_data,
            )
            session_store.update_session(
                session_id,
                pathway=pathway_res.model_dump(),
                status="COMPLETE",
            )
            logger.info("Successfully executed ML best_avoidable_ed_model for session %s | Avoidable: %s | Score: %.1f%%",
                        session_id, pathway_res.decision, pathway_res.risk_score)
        except Exception as exc:
            logger.error("Failed to run ML best_avoidable pathway for session %s: %s", session_id, exc)

    return SafetyResult(
        session_id=session_id,
        evaluated_at=now,
        error_detail=error_detail,
        pathway=pathway_res,
        **result_dict,
    )


async def get_latest_assessment(session_id: str, db: AsyncSession) -> SafetyResult:
    """Return the most recent audit record for this session."""
    session = _get_session_or_404(session_id)

    stmt = (
        select(SafetyAssessment)
        .where(SafetyAssessment.session_id == session_id)
        .order_by(SafetyAssessment.evaluated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row: SafetyAssessment | None = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No safety assessment found for session '{session_id}'.",
        )

    pathway_data = session.get("pathway")
    pathway_res = PathwayResponse(**pathway_data) if pathway_data else None

    return SafetyResult(
        session_id=row.session_id,
        result=row.result,
        next_action=row.next_action,
        triggered_rules=row.triggered_rules,
        error_detail=row.error_detail,
        evaluated_at=row.evaluated_at,
        pathway=pathway_res,
    )
