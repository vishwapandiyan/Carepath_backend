"""
Analytics Service — metrics computation for Care Manager Dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.analytics.schemas import AggregateAnalyticsOut, PatientAnalyticsOut
from app.models.ehr import PatientEHR
from app.db.models import PostDischargeStatus, ReadmissionPrediction, SafetyAssessment

logger = logging.getLogger(__name__)


async def get_aggregate_analytics(db: AsyncSession) -> AggregateAnalyticsOut:
    """
    Compute aggregate platform analytics across all patients for Care Manager Dashboard.
    """
    now = datetime.now(timezone.utc)

    # Patients count
    total_patients = (await db.execute(select(func.count(PatientEHR.id)))).scalar() or 0
    active_patients = (
        await db.execute(select(func.count(PatientEHR.id)).where(PatientEHR.is_active == 1))
    ).scalar() or 0

    # Readmission Risk metrics
    high_risk = (
        await db.execute(
            select(func.count(ReadmissionPrediction.id)).where(ReadmissionPrediction.risk_level == "high")
        )
    ).scalar() or 0

    medium_risk = (
        await db.execute(
            select(func.count(ReadmissionPrediction.id)).where(ReadmissionPrediction.risk_level == "medium")
        )
    ).scalar() or 0

    low_risk = (
        await db.execute(
            select(func.count(ReadmissionPrediction.id)).where(ReadmissionPrediction.risk_level == "low")
        )
    ).scalar() or 0

    total_predictions = high_risk + medium_risk + low_risk
    rate_pct = round((high_risk / total_predictions * 100), 1) if total_predictions > 0 else 0.0

    # Safety Triage metrics
    total_safety = (await db.execute(select(func.count(SafetyAssessment.id)))).scalar() or 0
    emergency_alerts = (
        await db.execute(
            select(func.count(SafetyAssessment.id)).where(SafetyAssessment.result == "YES")
        )
    ).scalar() or 0

    # Post Discharge metrics
    post_discharge_count = (
        await db.execute(select(func.count(PostDischargeStatus.id)))
    ).scalar() or 0

    return AggregateAnalyticsOut(
        total_patients=total_patients,
        active_patients=active_patients,
        high_risk_patients=high_risk,
        medium_risk_patients=medium_risk,
        low_risk_patients=low_risk,
        readmission_rate_pct=rate_pct,
        total_safety_evaluations=total_safety,
        emergency_alerts_triggered=emergency_alerts,
        post_discharge_active_monitors=post_discharge_count,
        timestamp=now,
    )


async def get_patient_analytics(patient_id: str, db: AsyncSession) -> PatientAnalyticsOut:
    """
    Compute analytics scoped to a single patient.
    """
    query = select(PatientEHR).where(
        (PatientEHR.patient_id == patient_id) | (PatientEHR.mrn == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or not patient.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )

    # Readmission prediction
    pred_stmt = (
        select(ReadmissionPrediction)
        .where(ReadmissionPrediction.patient_id == patient.id)
        .order_by(ReadmissionPrediction.predicted_at.desc())
        .limit(1)
    )
    pred = (await db.execute(pred_stmt)).scalars().first()

    # Safety assessments
    triage_count = (
        await db.execute(
            select(func.count(SafetyAssessment.id)).where(SafetyAssessment.patient_id == patient.id)
        )
    ).scalar() or 0

    emergency_triggers = (
        await db.execute(
            select(func.count(SafetyAssessment.id)).where(
                (SafetyAssessment.patient_id == patient.id) & (SafetyAssessment.result == "YES")
            )
        )
    ).scalar() or 0

    # Post discharge
    pd_stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient.id)
    pd_row = (await db.execute(pd_stmt)).scalars().first()

    care_plan_status = pd_row.care_plan.get("status") if pd_row and pd_row.care_plan else "not_started"

    return PatientAnalyticsOut(
        patient_id=patient.id,
        mrn=patient.mrn or "—",
        name=patient.name,
        readmission_risk_score=pred.risk_score if pred else None,
        readmission_risk_level=pred.risk_level if pred else None,
        total_triage_sessions=triage_count,
        emergency_triage_triggers=emergency_triggers,
        post_discharge_status=care_plan_status,
        last_activity_at=patient.updated_at or patient.created_at,
    )
