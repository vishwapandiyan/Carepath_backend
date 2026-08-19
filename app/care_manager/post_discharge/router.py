"""
Care Manager — Module 3: Post Discharge Router (/patients/{patient_id}/post-discharge)
"""

from fastapi import APIRouter, Depends, Security

from app.care_manager.post_discharge import schemas, service
from app.core.security import verify_api_key
from app.db.base import get_db

router = APIRouter(
    prefix="/patients/{patient_id}/post-discharge",
    tags=["Care Manager - Module 3: Post Discharge"],
    dependencies=[Security(verify_api_key)],
)


@router.get(
    "/",
    response_model=schemas.PostDischargeStatusOut,
    summary="Get 4-agent post-discharge status",
    description="Read-only view into the 4 background monitoring agents (Care Plan, Follow-up, Response Analyser, Appointment) for a single patient.",
)
async def get_post_discharge_status(
    patient_id: str,
    db=Depends(get_db),
) -> schemas.PostDischargeStatusOut:
    return await service.get_post_discharge_status(patient_id, db)
