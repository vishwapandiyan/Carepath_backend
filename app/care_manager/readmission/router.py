"""
Care Manager — Module 2: Readmission Prediction Router (/patients/{patient_id}/readmission)
"""

from fastapi import APIRouter, Depends, status

from app.care_manager.readmission import schemas, service
from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

router = APIRouter(
    prefix="/patients/{patient_id}/readmission",
    tags=["Care Manager - Module 2: Readmission"],
)


@router.post(
    "/predict",
    response_model=schemas.ReadmissionPredictionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Compute & store readmission prediction",
    description="Runs the predictive risk model on current patient data (internally pulled from DB) and stores the resulting score.",
)
async def predict_readmission(
    patient_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.ReadmissionPredictionOut:
    return await service.predict_readmission(patient_id, db)


@router.get(
    "/",
    response_model=schemas.ReadmissionPredictionOut,
    summary="Get latest readmission prediction",
    description="Returns the most recently stored readmission score for this patient without recomputation.",
)
async def get_readmission_score(
    patient_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.ReadmissionPredictionOut:
    return await service.get_latest_prediction(patient_id, db)
