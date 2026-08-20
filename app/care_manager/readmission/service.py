"""
Readmission Prediction Service.
Decoupled internal data pull function to allow smooth future migration to live EHR APIs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.readmission.schemas import ReadmissionPredictionOut
from app.models.ehr import PatientEHR
from app.db.models import ReadmissionPrediction, SafetyAssessment

logger = logging.getLogger(__name__)


async def get_patient_data_from_db(patient_id: str, db: AsyncSession) -> dict:
    """
    Decoupled internal data-pull logic.
    Pull patient demographic profile & historical triage assessments from database.
    """
    query = select(PatientEHR).where(
        (PatientEHR.patient_id == patient_id) | (PatientEHR.mrn == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )

    pid = patient.patient_id

    # Fetch latest safety triage assessment if available
    safety_query = (
        select(SafetyAssessment)
        .where(SafetyAssessment.patient_id == pid)
        .order_by(SafetyAssessment.evaluated_at.desc())
        .limit(1)
    )
    latest_safety = (await db.execute(safety_query)).scalars().first()

    return {
        "patient_id": pid,
        "mrn": patient.mrn or pid,
        "name": patient.name or patient.full_name,
        "dob": patient.dob,
        "insurance_id": patient.insurance_id,
        "has_safety_emergency": latest_safety.result == "YES" if latest_safety else False,
        "safety_triggered_count": len(latest_safety.triggered_rules) if latest_safety else 0,
    }


async def predict_readmission(patient_id: str, db: AsyncSession) -> ReadmissionPredictionOut:
    """
    Run prediction model on current patient data and persist the prediction score.
    """
    data = await get_patient_data_from_db(patient_id, db)

    base_risk = 0.25
    if data["has_safety_emergency"]:
        base_risk += 0.45
    if data["safety_triggered_count"] > 0:
        base_risk += min(0.20, data["safety_triggered_count"] * 0.10)

    risk_score = round(min(0.95, max(0.05, base_risk)), 2)

    if risk_score >= 0.70:
        risk_level = "high"
    elif risk_score >= 0.40:
        risk_level = "medium"
    else:
        risk_level = "low"

    prediction = ReadmissionPrediction(
        patient_id=data["patient_id"],
        risk_score=risk_score,
        risk_level=risk_level,
        predicted_at=datetime.now(timezone.utc),
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)

    logger.info(
        "Computed readmission risk | patient_id=%s | score=%.2f | level=%s",
        data["patient_id"], risk_score, risk_level,
    )
    return ReadmissionPredictionOut(
        patient_id=data["patient_id"],
        risk_score=risk_score,
        risk_level=risk_level,
        predicted_at=prediction.predicted_at,
    )


async def get_latest_prediction(patient_id: str, db: AsyncSession) -> ReadmissionPredictionOut:
    """
    Retrieve most recently computed score without recomputing.
    """
    data = await get_patient_data_from_db(patient_id, db)

    query = (
        select(ReadmissionPrediction)
        .where(ReadmissionPrediction.patient_id == data["patient_id"])
        .order_by(ReadmissionPrediction.predicted_at.desc())
        .limit(1)
    )
    prediction = (await db.execute(query)).scalars().first()

    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No readmission prediction score has been computed for patient '{patient_id}' yet. Run /predict first.",
        )

    return ReadmissionPredictionOut.model_validate(prediction)
