"""
Care Manager — Module 3: Post Discharge Router (/patients/{patient_id}/post-discharge)
"""

from fastapi import APIRouter, Depends

from app.care_manager.post_discharge import schemas, service
from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

router = APIRouter(
    prefix="/patients/{patient_id}/post-discharge",
    tags=["Care Manager - Module 3: Post Discharge"],
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
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PostDischargeStatusOut:
    return await service.get_post_discharge_status(patient_id, db)
