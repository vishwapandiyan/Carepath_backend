"""
Care Plan Generation API - REAL LangGraph Integration with Appointment Bridge
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User
# UPDATED: Import real post-care adapter
from app.integrations.post_care_adapter import stream_real_post_care_workflow
from app.integrations.appointment_bridge import appointment_bridge
from app.services.notification_service import generate_task_reminder
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models for appointment endpoints
class AppointmentBookingRequest(BaseModel):
    provider_id: str
    slot_id: str
    care_type: str
    specialty: Optional[str] = None


class AppointmentResponse(BaseModel):
    success: bool
    appointment: Optional[dict] = None
    error: Optional[str] = None


@router.post("/patients/{patient_id}/generate-care-plan-stream")
async def generate_care_plan_with_stream(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate care plan using REAL LangGraph post-care orchestrator.
    
    **NEW:** This now calls the actual 4-agent system with LLM orchestration.
    
    **Agents:**
    1. Care Plan Agent - Risk classification + task generation (Groq LLM)
    2. Follow-Up Agent - Check-in scheduling (deterministic)
    3. Response Analyzer - NLP patient response analysis (Groq LLM)
    4. Care Continuity - Routing logic (deterministic)
    
    **Orchestrator:** NVIDIA Nemotron 30B (decides which agent to call next)
    
    **Events emitted:**
    - init: Generation started
    - loading: Starting agentic workflow
    - agent_start: Agent started working
    - tool_call: Agent calling a tool
    - llm_chunk: LLM reasoning text
    - agent_complete: Agent finished
    - saving: Saving to database
    - complete: Generation complete with final care plan
    - error: Error occurred
    
    **Returns:** Server-Sent Events stream (text/event-stream)
    """
    
    logger.info(f"🤖 REAL care plan generation requested by {current_user.username} for patient {patient_id}")
    
    try:
        # Get patient EHR data
        from app.models.ehr import PatientEHR
        from sqlalchemy import select
        
        stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
        result = await db.execute(stmt)
        patient_ehr = result.scalar_one_or_none()
        
        if not patient_ehr:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found in EHR"
            )
        
        # Calculate readmission prediction
        # TODO: Replace with actual ML model
        prediction = 1 if patient_ehr.prior_30_day_readmission_flag else 0
        
        # Calculate probability based on risk factors
        risk_score = 0.0
        if patient_ehr.diabetes_flag:
            risk_score += 0.15
        if patient_ehr.heart_failure_flag:
            risk_score += 0.20
        if patient_ehr.hypertension_flag:
            risk_score += 0.10
        if patient_ehr.prior_30_day_readmission_flag:
            risk_score += 0.25
        if patient_ehr.icu_stay_flag:
            risk_score += 0.15
        
        probability = min(risk_score, 1.0)
        
        logger.info(f"📊 Patient {patient_id}: prediction={prediction}, probability={probability:.2f}")
        
        # Stream real LangGraph workflow
        return StreamingResponse(
            stream_real_post_care_workflow(
                patient_id=patient_id,
                mrn=patient_ehr.mrn,
                prediction=prediction,
                probability=probability,
                notes=patient_ehr.clinical_notes or "Post-discharge monitoring required",
                db=db
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start REAL care plan generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate care plan: {str(e)}"
        )


@router.post("/patients/{patient_id}/send-care-plan")
async def send_care_plan_to_patient(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Send generated care plan to patient and create task reminders.
    
    **Purpose:** After care manager reviews generated plan, send it to patient.
    
    **Flow:**
    1. Care manager reviews generated care plan in modal
    2. Clicks "Send to Patient" button
    3. This endpoint creates notifications for all tasks
    4. Patient sees care plan in their Care Plans page
    
    **Returns:** Success message with notification count
    """
    
    logger.info(f"Sending care plan to patient {patient_id} by {current_user.username}")
    
    try:
        from app.db.models import PostDischargeStatus
        from sqlalchemy import select
        
        # Get the care plan
        stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient_id)
        result = await db.execute(stmt)
        status = result.scalar_one_or_none()
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"No care plan found for patient {patient_id}"
            )
        
        # Create task reminders for each task
        care_plan = status.care_plan
        tasks = care_plan.get("tasks", [])
        
        notification_count = 0
        for idx, task in enumerate(tasks):
            if task.get("status") == "pending":
                # Create initial reminder notification
                await generate_task_reminder(
                    db=db,
                    patient_id=patient_id,
                    task_index=idx,
                    task_text=task["task"],
                    scheduled_for=None  # Immediate notification
                )
                notification_count += 1
        
        logger.info(f"✓ Sent care plan to patient {patient_id}: {notification_count} task reminders created")
        
        return {
            "success": True,
            "message": f"Care plan sent to patient successfully",
            "notifications_created": notification_count,
            "tasks_count": len(tasks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send care plan to patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send care plan: {str(e)}"
        )


@router.get("/patients/{patient_id}/appointment-context")
async def get_appointment_context(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Get appointment context for a patient based on their post-discharge status.
    
    Used by care manager to review appointment recommendations before booking.
    
    **Returns:**
    - Appointment context if appointment is required
    - Patient clinical information
    - Urgency level
    - Recommended next steps
    """
    
    logger.info(f"Getting appointment context for patient {patient_id}")
    
    try:
        from app.db.models import PostDischargeStatus
        from sqlalchemy import select
        
        # Get the post-discharge status
        stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient_id)
        result = await db.execute(stmt)
        status = result.scalar_one_or_none()
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"No post-discharge status found for patient {patient_id}"
            )
        
        # Check if appointment is required based on care continuity
        care_continuity = status.response_analyser.get("care_continuity", {})
        requires_appointment = care_continuity.get("requires_appointment", False)
        
        if not requires_appointment:
            return {
                "requires_appointment": False,
                "message": "No appointment currently required for this patient"
            }
        
        # Get appointment context from bridge
        appointment_context = await appointment_bridge.trigger_appointment_workflow(
            patient_id=patient_id,
            care_continuity_output=care_continuity,
            db=db
        )
        
        return appointment_context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get appointment context for patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get appointment context: {str(e)}"
        )


@router.post("/patients/{patient_id}/book-appointment", response_model=AppointmentResponse)
async def book_patient_appointment(
    patient_id: str,
    booking_request: AppointmentBookingRequest,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Book an appointment for a patient through the appointment bridge.
    
    Used by care manager after reviewing appointment recommendations.
    
    **Flow:**
    1. Care manager reviews appointment context
    2. Care manager selects provider and time slot
    3. This endpoint books the appointment via alternate care agent
    4. Updates post-discharge status with appointment info
    
    **Returns:** Appointment confirmation
    """
    
    logger.info(f"Booking appointment for patient {patient_id} by {current_user.username}")
    
    try:
        result = await appointment_bridge.book_appointment_from_recommendation(
            patient_id=patient_id,
            provider_id=booking_request.provider_id,
            slot_id=booking_request.slot_id,
            care_type=booking_request.care_type,
            specialty=booking_request.specialty,
            db=db
        )
        
        return AppointmentResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to book appointment for patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to book appointment: {str(e)}"
        )
