"""
Care Manager — Module 4: Analytics Router (/analytics)
"""

from fastapi import APIRouter, Depends

from app.care_manager.analytics import schemas, service
from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

router = APIRouter(
    prefix="/analytics",
    tags=["Care Manager - Module 4: Analytics"],
)


@router.get(
    "/",
    response_model=schemas.AggregateAnalyticsOut,
    summary="Get aggregate platform analytics",
    description="Aggregate metrics across all patients for the Care Manager Dashboard (patient counts, readmission risk rates, emergency alerts, post-discharge stats).",
)
async def get_aggregate_analytics(
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.AggregateAnalyticsOut:
    return await service.get_aggregate_analytics(db)


@router.get(
    "/{patient_id}",
    response_model=schemas.PatientAnalyticsOut,
    summary="Get analytics for a single patient",
    description="Returns readmission prediction metrics, safety triage history, and post-discharge agent status scoped to one patient.",
)
async def get_patient_analytics(
    patient_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PatientAnalyticsOut:
    return await service.get_patient_analytics(patient_id, db)
