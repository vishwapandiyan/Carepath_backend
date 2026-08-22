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
from app.models.ehr import PatientEHR
from app.db.models import PostDischargeStatus

logger = logging.getLogger(__name__)


async def get_post_discharge_status(patient_id: str, db: AsyncSession) -> PostDischargeStatusOut:
    """
    Get 4-agent post discharge monitoring status for a patient.
    Care Plan, Follow-up, Response Analyser, Appointment agents.
    Resolves patient dynamically from Username, MRN, Patient ID, or Name.
    Initializes realistic baseline status from real EHR records if none exists.
    """
    from app.patient.safety.service import _get_ehr_for_patient
    patient = await _get_ehr_for_patient(patient_id, db)

    if patient is None or patient.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )

    pid = patient.patient_id

    status_query = select(PostDischargeStatus).where(
        PostDischargeStatus.patient_id == pid
    )
    status_row = (await db.execute(status_query)).scalars().first()

    # DO NOT auto-create baseline data — only show data after Generate Care Plan is clicked
    if status_row is None:
        # Return empty status indicating no care plan generated yet
        return PostDischargeStatusOut(
            patient_id=pid,
            care_plan=CarePlanAgentStatus(
                tasks=[],
                status="not_generated"
            ),
            follow_up=FollowUpAgentStatus(
                last_checkin=None,
                next_checkin=None,
                is_scheduled=False
            ),
            response_analyser=ResponseAnalyserAgentStatus(
                key_info={}
            ),
            appointment=AppointmentAgentStatus(
                is_appointment=False,
                date=None
            ),
        )

    return PostDischargeStatusOut(
        patient_id=pid,
        care_plan=CarePlanAgentStatus(**status_row.care_plan),
        follow_up=FollowUpAgentStatus(**status_row.follow_up),
        response_analyser=ResponseAnalyserAgentStatus(**status_row.response_analyser),
        appointment=AppointmentAgentStatus(**status_row.appointment),
    )
