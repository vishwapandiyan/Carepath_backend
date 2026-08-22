from fastapi import APIRouter
from app.api.v1.endpoints import auth, patient, care_manager, ehr, chat, notifications, patient_response, care_plan

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(patient.router, prefix="/patient", tags=["Patient"])
api_router.include_router(care_manager.router, prefix="/care-manager", tags=["Care Manager"])
api_router.include_router(ehr.router, prefix="/ehr", tags=["EHR Management"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat History"])
api_router.include_router(notifications.router, tags=["Patient Notifications"])
api_router.include_router(patient_response.router, tags=["Patient - Care Plan Response"])
api_router.include_router(care_plan.router, tags=["Care Plans"])
