"""
Patient Response API — Accepts optional free-text patient responses to care plan check-ins.

This endpoint does NOT block the main Care Plan → Follow-up workflow.
It is called asynchronously when a patient chooses to respond to a notification/check-in.

Flow:
    Patient notification received
        ↓
    Patient optionally types free-text
        ↓
    POST /patients/{patient_id}/care-plan-response
        ↓
    Load care plan / check-in context
        ↓
    Call Response Analyzer Agent (Groq LLM)
        ↓
    Return structured classification
        ↓
    (Care Continuity handled in a later step)
"""

import sys
import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_current_patient
from app.db.base import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response Models ────────────────────────────────────────────────────

class PatientResponseRequest(BaseModel):
    """Request body for patient care plan response."""
    patient_response: str = Field(
        ...,
        min_length=1,
        description="Patient's free-text response to a care plan check-in or notification"
    )
    checkin_id: Optional[str] = Field(
        default=None,
        description="Specific check-in ID being responded to (optional — will use latest if not provided)"
    )


class PatientResponseResult(BaseModel):
    """Response from the Response Analyzer + Care Continuity pipeline."""
    success: bool
    # Response Analyzer output
    classification: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
    symptoms: Optional[list] = None
    concerns: Optional[list] = None
    patient_sentiment: Optional[str] = None
    # Care Continuity output
    continuity_action: Optional[str] = None
    continuity_reason: Optional[str] = None
    requires_human_review: Optional[bool] = None
    requires_appointment: Optional[bool] = None
    # Context
    care_plan_id: Optional[str] = None
    task_id: Optional[str] = None
    checkin_id: Optional[str] = None
    error: Optional[str] = None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/patients/{patient_id}/care-plan-response",
    response_model=PatientResponseResult,
    tags=["Patient - Care Plan Response"],
    summary="Submit a response to a care plan check-in",
    description=(
        "Accepts a patient's free-text response to a care plan notification or check-in. "
        "The response is analyzed by the Response Analyzer Agent (Groq LLM) to classify "
        "severity and extract symptoms/concerns. This does NOT block the main workflow."
    ),
)
async def submit_patient_response(
    patient_id: str,
    request: PatientResponseRequest,
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> PatientResponseResult:
    """
    Submit a patient response and run the Response Analyzer.

    Steps:
    1. Verify patient identity
    2. Load active care plan and relevant check-in context
    3. Call Response Analyzer Agent with the patient's text
    4. Store the response in the check-in record
    5. Return the structured analysis
    """

    logger.info(f"Patient response received for patient_id={patient_id}")

    # ── 1. Verify patient identity ─────────────────────────────────────────
    if current_user.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Cannot respond for another patient")

    # ── 2. Load patient EHR and active care plan context ───────────────────
    try:
        from app.models.ehr import PatientEHR
        stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
        result = await db.execute(stmt)
        patient_ehr = result.scalar_one_or_none()

        if not patient_ehr:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        mrn = patient_ehr.mrn
        if not mrn:
            raise HTTPException(status_code=422, detail="Patient has no MRN assigned")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load patient EHR: {e}")
        raise HTTPException(status_code=500, detail="Failed to load patient data")

    # ── 3. Load care plan and check-in context from PostgreSQL ─────────────
    try:
        # Add post_care to path for imports
        POST_CARE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "post_care")
        if POST_CARE_PATH not in sys.path:
            sys.path.insert(0, POST_CARE_PATH)

        from database.connection import get_db_connection, close_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        # Find active care plan for this MRN
        cursor.execute(
            "SELECT care_plan_id, risk_level, intensity, doctor_instructions FROM care_plans WHERE mrn = %s AND status = 'ACTIVE' LIMIT 1",
            (mrn,)
        )
        plan_row = cursor.fetchone()

        if not plan_row:
            close_db_connection(conn)
            raise HTTPException(status_code=404, detail="No active care plan found for this patient")

        care_plan_id = plan_row[0]
        doctor_instructions = plan_row[3]

        # Find the relevant check-in
        if request.checkin_id:
            cursor.execute(
                "SELECT checkin_id, task_id, checkin_type, message FROM follow_up_checkins WHERE checkin_id = %s",
                (request.checkin_id,)
            )
        else:
            # Use the most recent scheduled check-in for this care plan's tasks
            cursor.execute(
                """
                SELECT fc.checkin_id, fc.task_id, fc.checkin_type, fc.message
                FROM follow_up_checkins fc
                JOIN care_plan_tasks cpt ON fc.task_id = cpt.task_id
                WHERE cpt.care_plan_id = %s AND fc.status IN ('SCHEDULED', 'SENT')
                ORDER BY fc.created_at DESC
                LIMIT 1
                """,
                (care_plan_id,)
            )

        checkin_row = cursor.fetchone()

        if checkin_row:
            checkin_id = checkin_row[0]
            task_id = checkin_row[1]
            task_type = checkin_row[2]
            checkin_message = checkin_row[3]
        else:
            # No check-in found — use first pending task as context
            cursor.execute(
                "SELECT task_id, task_type, description FROM care_plan_tasks WHERE care_plan_id = %s AND status IN ('PENDING', 'IN_PROGRESS') ORDER BY created_at LIMIT 1",
                (care_plan_id,)
            )
            task_row = cursor.fetchone()
            if task_row:
                task_id = task_row[0]
                task_type = task_row[1]
                checkin_id = "DIRECT_RESPONSE"
                checkin_message = task_row[2]
            else:
                task_id = "UNKNOWN"
                task_type = "GENERAL"
                checkin_id = "DIRECT_RESPONSE"
                checkin_message = None

        # Store patient response in the check-in record (if it exists)
        if checkin_id and checkin_id != "DIRECT_RESPONSE":
            cursor.execute(
                "UPDATE follow_up_checkins SET response = %s, status = 'RESPONSE_RECEIVED', response_received_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE checkin_id = %s",
                (request.patient_response, checkin_id)
            )
            conn.commit()

        close_db_connection(conn)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load care plan context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load care plan context: {str(e)}")

    # ── 4. Call Response Analyzer Agent ────────────────────────────────────
    try:
        from agents.response_analyzer.agent import orchestrate_response_analysis
        from agents.response_analyzer.schemas import ResponseAnalyzerInput

        analyzer_input = ResponseAnalyzerInput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=checkin_id,
            task_type=task_type,
            patient_response=request.patient_response,
            doctor_instruction=doctor_instructions,
            task_description=checkin_message,
        )

        logger.info(f"Calling Response Analyzer for patient {patient_id}, checkin {checkin_id}")
        analyzer_output = orchestrate_response_analysis(analyzer_input)

        logger.info(
            f"Response Analyzer result: classification={analyzer_output.classification}, "
            f"confidence={analyzer_output.confidence}"
        )

        # ── 5. Call Care Continuity Agent ──────────────────────────────────
        continuity_action = None
        continuity_reason = None
        requires_human_review = None
        requires_appointment = None

        try:
            from agents.care_continuity.agent import process_care_continuity
            from agents.care_continuity.schemas import CareContinuityInput

            continuity_input = CareContinuityInput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                task_id=task_id,
                checkin_id=checkin_id,
                classification=analyzer_output.classification,
                summary=analyzer_output.summary,
                symptoms=analyzer_output.symptoms or [],
                concerns=analyzer_output.concerns or [],
                confidence=analyzer_output.confidence,
                doctor_instruction=doctor_instructions,
                task_description=checkin_message,
            )

            logger.info(f"Calling Care Continuity for patient {patient_id}, classification={analyzer_output.classification}")
            continuity_output = process_care_continuity(continuity_input)

            continuity_action = continuity_output.continuity_action
            continuity_reason = continuity_output.reason
            requires_human_review = continuity_output.requires_human_review
            requires_appointment = continuity_output.requires_appointment

            logger.info(
                f"Care Continuity result: action={continuity_action}, "
                f"requires_appointment={requires_appointment}"
            )

            # ── 6. Care Plan Revision + Follow-up (if adjustment needed) ───
            if continuity_action in ("CLINICAL_REVIEW", "URGENT_REVIEW"):
                try:
                    from services.care_plan_service_postgresql import revise_care_plan, get_plan_tasks
                    from agents.follow_up.agent import orchestrate_follow_up
                    from agents.follow_up.schemas import FollowUpInput

                    # Revise the existing care plan (does NOT create a new one)
                    revised_plan = revise_care_plan(
                        care_plan_id=care_plan_id,
                        mrn=mrn,
                        continuity_action=continuity_action,
                        classification=analyzer_output.classification,
                        symptoms=analyzer_output.symptoms or [],
                        concerns=analyzer_output.concerns or [],
                        summary=analyzer_output.summary,
                        confidence=analyzer_output.confidence,
                    )
                    logger.info(f"Care plan {care_plan_id} revised successfully")

                    # Re-run Follow-up Agent with updated tasks
                    revised_tasks = revised_plan.get("tasks", [])
                    follow_up_input = FollowUpInput(
                        mrn=mrn,
                        care_plan_id=care_plan_id,
                        risk_level=revised_plan.get("risk_level", "HIGH"),
                        intensity=revised_plan.get("intensity", "INTENSIVE"),
                        tasks=[
                            {
                                "task_id": t.get("task_id"),
                                "task_type": t.get("task_type"),
                                "status": t.get("status", "PENDING"),
                                "description": t.get("description"),
                                "doctor_instruction": t.get("doctor_instruction"),
                            }
                            for t in revised_tasks
                        ],
                    )

                    follow_up_output = orchestrate_follow_up(follow_up_input)
                    logger.info(f"Follow-up re-executed: task={follow_up_output.follow_up.get('task_id') if follow_up_output.follow_up else None}")

                    # Trigger notification for the updated follow-up
                    try:
                        from app.services.notification_service import generate_task_reminder
                        # Notify about the new monitoring task
                        for idx, t in enumerate(revised_tasks):
                            if t.get("status") == "PENDING" and t.get("task_type") == "CONCERN_ESCALATION":
                                task_text = t.get("description") or t.get("task_type")
                                await generate_task_reminder(
                                    db=db,
                                    patient_id=patient_id,
                                    task_index=idx,
                                    task_text=task_text,
                                    scheduled_for=None,
                                )
                                logger.info(f"Notification sent for revised task: {t.get('task_id')}")
                                break
                    except Exception as notif_err:
                        logger.warning(f"Notification trigger failed (non-fatal): {notif_err}")

                except Exception as rev_err:
                    logger.error(f"Care plan revision failed (non-fatal): {rev_err}", exc_info=True)
                    # Revision failure is non-fatal — we still return the continuity result

            # ── 7. Appointment Handoff (Step 5A — if required) ─────────────
            if requires_appointment:
                try:
                    from post_care.services.appointment_handoff import handoff_to_appointment_agent
                    
                    appointment_result = handoff_to_appointment_agent(
                        mrn=mrn,
                        care_plan_id=care_plan_id,
                        classification=analyzer_output.classification,
                        symptoms=analyzer_output.symptoms or [],
                        concerns=analyzer_output.concerns or [],
                        summary=analyzer_output.summary,
                        confidence=analyzer_output.confidence,
                    )
                    logger.info(f"Appointment handoff result: success={appointment_result.get('success')}, session={appointment_result.get('session_id')}")
                except Exception as appt_err:
                    logger.error(f"Appointment handoff failed (non-fatal): {appt_err}", exc_info=True)
                    appointment_result = None

        except Exception as cc_err:
            logger.error(f"Care Continuity failed (non-fatal): {cc_err}", exc_info=True)
            # Care Continuity failure is non-fatal — we still return the analyzer result

        return PatientResponseResult(
            success=True,
            classification=analyzer_output.classification,
            confidence=analyzer_output.confidence,
            summary=analyzer_output.summary,
            symptoms=analyzer_output.symptoms,
            concerns=analyzer_output.concerns,
            patient_sentiment=analyzer_output.patient_sentiment,
            continuity_action=continuity_action,
            continuity_reason=continuity_reason,
            requires_human_review=requires_human_review,
            requires_appointment=requires_appointment,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=checkin_id,
            error=None,
        )

    except Exception as e:
        logger.error(f"Response Analyzer failed: {e}", exc_info=True)
        return PatientResponseResult(
            success=False,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=checkin_id,
            error=str(e),
        )
