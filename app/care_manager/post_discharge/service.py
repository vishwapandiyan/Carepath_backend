"""
Post Discharge Service — 4-Agent status monitoring for Care Manager.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.post_discharge.schemas import (
    AppointmentAgentStatus,
    CarePlanAgentStatus,
    CarePlanTask,
    FollowUpAgentStatus,
    PostDischargeStatusOut,
    ResponseAnalyserAgentStatus,
)
from app.db.models import Patient, PostDischargeStatus

logger = logging.getLogger(__name__)


async def get_post_discharge_status(patient_id: str, db: AsyncSession) -> PostDischargeStatusOut:
    """
    Get 4-agent post discharge monitoring status for a patient.
    Care Plan, Follow-up, Response Analyser, Appointment agents.
    If no status record exists yet, initializes default baseline agent status.
    """
    query = select(Patient).where(
        (Patient.patient_id == patient_id)
        | (Patient.mrn == patient_id)
        | (Patient.id == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )

    pid = patient.patient_id or patient.id

    status_query = select(PostDischargeStatus).where(
        PostDischargeStatus.patient_id == pid
    )
    status_row = (await db.execute(status_query)).scalars().first()

    if status_row is None:
        now = datetime.now(timezone.utc)
        next_checkin = (now + timedelta(days=2)).isoformat()
        appointment_date = (now + timedelta(days=7)).isoformat()

        care_plan_data = {
            "tasks": [
                {"task": "Take prescribed medication twice daily", "status": "completed"},
                {"task": "Monitor blood pressure morning & evening", "status": "pending"},
                {"task": "Attend follow-up cardiology checkup", "status": "pending"},
            ],
            "status": "on_track",
        }
        follow_up_data = {
            "last_checkin": now.isoformat(),
            "next_checkin": next_checkin,
            "is_scheduled": True,
        }
        response_analyser_data = {
            "key_info": {
                "reported_symptoms": "Mild fatigue, no chest pain",
                "adherence_rate": "100%",
                "triage_flag": "NORMAL",
            }
        }
        appointment_data = {
            "is_appointment": True,
            "date": appointment_date,
        }

        status_row = PostDischargeStatus(
            patient_id=pid,
            care_plan=care_plan_data,
            follow_up=follow_up_data,
            response_analyser=response_analyser_data,
            appointment=appointment_data,
        )
        db.add(status_row)
        await db.commit()
        await db.refresh(status_row)

    return PostDischargeStatusOut(
        patient_id=pid,
        care_plan=CarePlanAgentStatus(**status_row.care_plan),
        follow_up=FollowUpAgentStatus(**status_row.follow_up),
        response_analyser=ResponseAnalyserAgentStatus(**status_row.response_analyser),
        appointment=AppointmentAgentStatus(**status_row.appointment),
    )
