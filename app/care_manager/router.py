"""
Care Manager Master Domain Router — registers all 3 PRD modules:
  - Module 1: Readmission Prediction (/patients/{id}/readmission)
  - Module 2: Post Discharge 4-Agent Status (/patients/{id}/post-discharge)
  - Module 3: Platform & Patient Analytics (/analytics)

Note: Patient CRUD has been moved to EHR module (/api/v1/ehr/patients) with all fields integrated.
"""

from fastapi import APIRouter

from app.care_manager.analytics.router import router as analytics_router
from app.care_manager.post_discharge.router import router as post_discharge_router
from app.care_manager.readmission.router import router as readmission_router

care_manager_router = APIRouter()

# Mount all 3 modules (Patient CRUD removed - now part of EHR module)
care_manager_router.include_router(readmission_router)
care_manager_router.include_router(post_discharge_router)
care_manager_router.include_router(analytics_router)


@care_manager_router.get("/health", tags=["Care Manager"], summary="Care Manager Domain Health Check")
async def care_manager_health():
    return {
        "status": "ok",
        "domain": "care_manager",
        "modules": ["Readmission Prediction", "Post Discharge", "Analytics"],
        "note": "Patient CRUD moved to /api/v1/ehr/patients with integrated fields"
    }
