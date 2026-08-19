"""
Patient Domain Router — registers all patient-facing segment routers.

Contains all working patient segments:
  - Intake (Seg 1)
  - Safety Triage (Seg 2)
  - Pathway (Seg 3)
  - Care Options (Seg 4)
  - Navigation (Seg 5)
  - Follow-up (Seg 6)
"""

from fastapi import APIRouter

from app.patient.care_options.router import router as co_router
from app.patient.followup.router import router as fu_router
from app.patient.intake.router import router as intake_router
from app.patient.navigation.router import router as nav_router
from app.patient.pathway.router import router as pathway_router
from app.patient.safety.router import router as safety_router

patient_router = APIRouter()

patient_router.include_router(intake_router)
patient_router.include_router(safety_router)
patient_router.include_router(pathway_router)
patient_router.include_router(co_router)
patient_router.include_router(nav_router)
patient_router.include_router(fu_router)
