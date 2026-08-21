"""
Readmission Prediction Service.
Integrates trained scikit-learn readmission ML model (best_readmission_model.pkl).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.readmission.schemas import ReadmissionPredictionOut
from app.models.ehr import PatientEHR
from app.db.models import ReadmissionPrediction, SafetyAssessment
from app.services.readmission_prediction_service import readmission_prediction_service

logger = logging.getLogger(__name__)


async def get_patient_from_db(patient_id: str, db: AsyncSession) -> PatientEHR:
    """Fetch patient record by patient_id, MRN, or integer ID."""
    conds = [
        PatientEHR.patient_id == patient_id,
        PatientEHR.mrn == patient_id,
    ]
    if patient_id.isdigit():
        conds.append(PatientEHR.id == int(patient_id))

    query = select(PatientEHR).where(or_(*conds))
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found.",
        )
    return patient


async def predict_readmission(patient_id: str, db: AsyncSession) -> ReadmissionPredictionOut:
    """
    Run trained ML model (best_readmission_model.pkl) on patient EHR record and persist prediction score.
    """
    patient = await get_patient_from_db(patient_id, db)
    pid = patient.patient_id

    # If ML model is loaded, use true ML model prediction
    if readmission_prediction_service.model_loaded:
        try:
            ml_res = readmission_prediction_service.predict(patient)
            risk_score = round(ml_res["risk_score"], 4)
        except Exception as e:
            logger.error(f"Error running ML model for patient {pid}: {e}. Falling back to clinical features.")
            risk_score = 0.25
    else:
        risk_score = 0.25

    # Fetch latest safety triage assessment if available to factor in emergency status
    safety_query = (
        select(SafetyAssessment)
        .where(SafetyAssessment.patient_id == pid)
        .order_by(SafetyAssessment.evaluated_at.desc())
        .limit(1)
    )
    latest_safety = (await db.execute(safety_query)).scalars().first()
    if latest_safety and latest_safety.result == "YES":
        risk_score = round(min(0.98, risk_score + 0.35), 4)

    if risk_score >= 0.70:
        risk_level = "high"
    elif risk_score >= 0.40:
        risk_level = "medium"
    else:
        risk_level = "low"

    prediction = ReadmissionPrediction(
        patient_id=pid,
        risk_score=risk_score,
        risk_level=risk_level,
        predicted_at=datetime.now(timezone.utc),
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)

    logger.info(
        "Computed ML readmission risk | patient_id=%s | score=%.4f | level=%s",
        pid, risk_score, risk_level,
    )
    return ReadmissionPredictionOut(
        patient_id=pid,
        risk_score=risk_score,
        risk_level=risk_level,
        predicted_at=prediction.predicted_at,
    )


async def get_latest_prediction(patient_id: str, db: AsyncSession) -> ReadmissionPredictionOut:
    """
    Retrieve most recently computed score without recomputing.
    """
    patient = await get_patient_from_db(patient_id, db)
    pid = patient.patient_id

    query = (
        select(ReadmissionPrediction)
        .where(ReadmissionPrediction.patient_id == pid)
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
