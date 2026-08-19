"""
Care Manager Master Domain Router — registers all 4 PRD modules:
  - Module 1: Patient (CRUD with MRN auto-generation like MRN000001, MRN040001)
  - Module 2: Readmission Prediction (/patients/{id}/readmission)
  - Module 3: Post Discharge 4-Agent Status (/patients/{id}/post-discharge)
  - Module 4: Platform & Patient Analytics (/analytics)
"""

from fastapi import APIRouter

from app.care_manager.analytics.router import router as analytics_router
from app.care_manager.patient.router import router as patient_crud_router
from app.care_manager.post_discharge.router import router as post_discharge_router
from app.care_manager.readmission.router import router as readmission_router

care_manager_router = APIRouter()

# Mount all 4 modules
care_manager_router.include_router(patient_crud_router)
care_manager_router.include_router(readmission_router)
care_manager_router.include_router(post_discharge_router)
care_manager_router.include_router(analytics_router)


@care_manager_router.get("/health", tags=["Care Manager"], summary="Care Manager Domain Health Check")
async def care_manager_health():
    return {
        "status": "ok",
        "domain": "care_manager",
        "modules": ["Patient CRUD", "Readmission Prediction", "Post Discharge", "Analytics"],
    }
