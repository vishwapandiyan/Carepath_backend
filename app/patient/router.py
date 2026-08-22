"""
Patient Domain Router — registers all patient-facing segment routers.

Contains all working patient segments:
  - Intake (Seg 1)
  - Safety Triage (Seg 2)
  - Pathway (Seg 3)
  - Care Options (Seg 4)
  - Navigation (Seg 5)
  - Care Plan (Post-Discharge)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.patient.care_options.router import router as co_router
from app.patient.intake.router import router as intake_router
from app.patient.navigation.router import router as nav_router
from app.patient.pathway.router import router as pathway_router
from app.patient.safety.router import router as safety_router
from app.core.security import get_current_patient
from app.db.base import get_db
from app.models.user import User

patient_router = APIRouter()

patient_router.include_router(intake_router)
patient_router.include_router(safety_router)
patient_router.include_router(pathway_router)
patient_router.include_router(co_router)
patient_router.include_router(nav_router)


# Patient Care Plan endpoint (post-discharge status for patients)
@patient_router.get(
    "/care-plan",
    tags=["Patient - Care Plan"],
    summary="Get my post-discharge care plan",
    description="View your post-discharge care plan tasks, follow-up schedule, and appointment status.",
)
async def get_my_care_plan(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    """Patient endpoint to view their own post-discharge care plan."""
    from app.care_manager.post_discharge.service import get_post_discharge_status
    
    return await get_post_discharge_status(current_user.patient_id, db)
