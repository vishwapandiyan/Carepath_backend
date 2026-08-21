"""
Aggregates all patient-pipeline segment routers.
Include this single router in your app's main.py, alongside
intake and safety (already built), and the Care Manager routers.
"""

from fastapi import APIRouter

from .care_options.router import router as care_options_router
from .navigation.router import router as navigation_router
from .pathway.router import router as pathway_router

patient_pipeline_router = APIRouter()

patient_pipeline_router.include_router(pathway_router)
patient_pipeline_router.include_router(care_options_router)
patient_pipeline_router.include_router(navigation_router)
