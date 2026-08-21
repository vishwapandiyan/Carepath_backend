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

    if status_row is None:
        now = datetime.now(timezone.utc)
        next_checkin_dt = patient.follow_up_appointment_date or (now + timedelta(days=2))
        next_checkin_str = str(next_checkin_dt)

        # Generate realistic care plan tasks based on EHR condition flags & clinical notes
        tasks = []
        if patient.active_medication_count and patient.active_medication_count > 0:
            tasks.append({"task": f"Take prescribed medications ({patient.active_medication_count} active)", "status": "pending"})
        if patient.hypertension_flag or patient.systolic_bp > 140:
            tasks.append({"task": "Monitor blood pressure morning & evening", "status": "pending"})
        if patient.diabetes_flag or (patient.hba1c and patient.hba1c > 7.0):
            tasks.append({"task": "Check blood glucose levels daily", "status": "pending"})
        if patient.heart_failure_flag:
            tasks.append({"task": "Record daily weight & check for ankle swelling", "status": "pending"})
        if patient.copd_asthma_flag:
            tasks.append({"task": "Use maintenance inhaler as prescribed", "status": "pending"})
        
        # Add follow-up task
        tasks.append({"task": f"Attend post-discharge follow-up appointment ({patient.discharge_destination or 'home'})", "status": "pending"})

        # Determine Care Plan Status
        adherence = patient.medication_adherence_rate if patient.medication_adherence_rate is not None else 100.0
        comorbidities = patient.charlson_comorbidity_index or 0
        if adherence < 75.0 or comorbidities >= 5 or patient.prior_30_day_readmission_flag == 1:
            care_plan_status = "at_risk"
        else:
            care_plan_status = "on_track"

        care_plan_data = {
            "tasks": tasks,
            "status": care_plan_status,
        }
        
        follow_up_data = {
            "last_checkin": (patient.discharge_date or now.date()).isoformat(),
            "next_checkin": next_checkin_str,
            "is_scheduled": bool(patient.follow_up_within_7_days_flag or patient.follow_up_appointment_date),
        }
        
        # Triage flag assessment based on clinical metrics
        if patient.systolic_bp > 160 or patient.spo2 < 92 or patient.pain_score_clinical >= 7.0:
            triage_flag = "HIGH_RISK"
        elif care_plan_status == "at_risk":
            triage_flag = "ATTENTION_REQUIRED"
        else:
            triage_flag = "NORMAL"

        response_analyser_data = {
            "key_info": {
                "reported_symptoms": patient.clinical_notes or "Post-discharge recovery",
                "adherence_rate": f"{adherence:.0f}%",
                "triage_flag": triage_flag,
                "discharge_destination": patient.discharge_destination or "home",
                "readmission_history": f"{patient.previous_admissions_12m or 0} admissions in past 12m"
            }
        }
        
        appointment_data = {
            "is_appointment": bool(patient.follow_up_appointment_date or patient.follow_up_within_7_days_flag),
            "date": str(patient.follow_up_appointment_date) if patient.follow_up_appointment_date else next_checkin_str,
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
