"""
Care Manager — Module 4: Analytics Router (/analytics)
"""

from fastapi import APIRouter, Depends, Security

from app.care_manager.analytics import schemas, service
from app.core.security import verify_api_key
from app.db.base import get_db

router = APIRouter(
    prefix="/analytics",
    tags=["Care Manager - Module 4: Analytics"],
    dependencies=[Security(verify_api_key)],
)


@router.get(
    "/",
    response_model=schemas.AggregateAnalyticsOut,
    summary="Get aggregate platform analytics",
    description="Aggregate metrics across all patients for the Care Manager Dashboard (patient counts, readmission risk rates, emergency alerts, post-discharge stats).",
)
async def get_aggregate_analytics(
    db=Depends(get_db),
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
) -> schemas.PatientAnalyticsOut:
    return await service.get_patient_analytics(patient_id, db)
