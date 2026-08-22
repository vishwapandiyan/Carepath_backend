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

    # ED Avoidability Risk metrics (from ml_predictions table)
    from app.models.ml_predictions import MLPrediction
    
    # Get latest ED prediction per patient
    latest_ed_predictions_subq = (
        select(
            MLPrediction.patient_id,
            func.max(MLPrediction.predicted_at).label("max_predicted_at")
        )
        .where(MLPrediction.model_type == "ed_avoidable")
        .group_by(MLPrediction.patient_id)
        .subquery()
    )
    
    ed_predictions = (
        await db.execute(
            select(MLPrediction.risk_score)
            .join(
                latest_ed_predictions_subq,
                (MLPrediction.patient_id == latest_ed_predictions_subq.c.patient_id) &
                (MLPrediction.predicted_at == latest_ed_predictions_subq.c.max_predicted_at)
            )
            .where(MLPrediction.model_type == "ed_avoidable")
        )
    ).scalars().all()
    
    high_ed_risk = sum(1 for score in ed_predictions if score >= 0.7)
    medium_ed_risk = sum(1 for score in ed_predictions if 0.4 <= score < 0.7)
    low_ed_risk = sum(1 for score in ed_predictions if score < 0.4)
    total_ed_predictions = len(ed_predictions)
    ed_rate_pct = round((high_ed_risk / total_ed_predictions * 100), 1) if total_ed_predictions > 0 else 0.0

    # ED Visit metrics (from patient_ehr table)
    ed_30d_sum = (
        await db.execute(
            select(func.coalesce(func.sum(PatientEHR.ed_visits_30d), 0))
            .where(PatientEHR.is_active == 1)
        )
    ).scalar() or 0
    
    ed_90d_sum = (
        await db.execute(
            select(func.coalesce(func.sum(PatientEHR.ed_visits_90d), 0))
            .where(PatientEHR.is_active == 1)
        )
    ).scalar() or 0
    
    er_12m_sum = (
        await db.execute(
            select(func.coalesce(func.sum(PatientEHR.previous_er_visits_12m), 0))
            .where(PatientEHR.is_active == 1)
        )
    ).scalar() or 0
    
    avg_ed_per_patient = round((er_12m_sum / active_patients), 2) if active_patients > 0 else 0.0

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
        high_ed_risk_patients=high_ed_risk,
        medium_ed_risk_patients=medium_ed_risk,
        low_ed_risk_patients=low_ed_risk,
        ed_high_risk_rate_pct=ed_rate_pct,
        total_ed_visits_30d=ed_30d_sum,
        total_ed_visits_90d=ed_90d_sum,
        avg_ed_visits_per_patient=avg_ed_per_patient,
        total_safety_evaluations=total_safety,
        emergency_alerts_triggered=emergency_alerts,
        post_discharge_active_monitors=post_discharge_count,
        timestamp=now,
    )


async def get_patient_analytics(patient_id: str, db: AsyncSession) -> PatientAnalyticsOut:
    """
    Compute analytics scoped to a single patient.
    Dynamically resolves patient by Username, MRN, Patient ID, or Name.
    """
    from app.patient.safety.service import _get_ehr_for_patient
    patient = await _get_ehr_for_patient(patient_id, db)

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )

    pid = patient.patient_id

    # Readmission prediction
    pred_stmt = (
        select(ReadmissionPrediction)
        .where(ReadmissionPrediction.patient_id == pid)
        .order_by(ReadmissionPrediction.predicted_at.desc())
        .limit(1)
    )
    pred = (await db.execute(pred_stmt)).scalars().first()

    # ED Avoidability prediction
    from app.models.ml_predictions import MLPrediction
    ed_pred_stmt = (
        select(MLPrediction)
        .where(
            (MLPrediction.patient_id == pid) &
            (MLPrediction.model_type == "ed_avoidable")
        )
        .order_by(MLPrediction.predicted_at.desc())
        .limit(1)
    )
    ed_pred = (await db.execute(ed_pred_stmt)).scalars().first()
    
    # Determine ED risk level from score
    ed_risk_level = None
    if ed_pred:
        if ed_pred.risk_score >= 0.7:
            ed_risk_level = "high"
        elif ed_pred.risk_score >= 0.4:
            ed_risk_level = "medium"
        else:
            ed_risk_level = "low"

    # Safety assessments
    triage_count = (
        await db.execute(
            select(func.count(SafetyAssessment.id)).where(SafetyAssessment.patient_id == pid)
        )
    ).scalar() or 0

    emergency_triggers = (
        await db.execute(
            select(func.count(SafetyAssessment.id)).where(
                (SafetyAssessment.patient_id == pid) & (SafetyAssessment.result == "YES")
            )
        )
    ).scalar() or 0

    # Post discharge
    pd_stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == pid)
    pd_row = (await db.execute(pd_stmt)).scalars().first()

    care_plan_status = pd_row.care_plan.get("status") if pd_row and pd_row.care_plan else "not_started"

    return PatientAnalyticsOut(
        patient_id=pid,
        mrn=patient.mrn or "—",
        name=patient.name,
        readmission_risk_score=pred.risk_score if pred else None,
        readmission_risk_level=pred.risk_level if pred else None,
        ed_risk_score=ed_pred.risk_score if ed_pred else None,
        ed_risk_level=ed_risk_level,
        ed_visits_30d=patient.ed_visits_30d or 0,
        ed_visits_90d=patient.ed_visits_90d or 0,
        total_triage_sessions=triage_count,
        emergency_triage_triggers=emergency_triggers,
        post_discharge_status=care_plan_status,
        last_activity_at=patient.updated_at or patient.created_at,
    )
