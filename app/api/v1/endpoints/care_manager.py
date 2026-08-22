from fastapi import APIRouter, Depends
from app.core.security import get_current_care_manager
from app.models import User
from app.api.v1.endpoints import care_plan_generation

router = APIRouter()

# Include care plan generation sub-router
router.include_router(care_plan_generation.router, tags=["Care Plan Generation"])


@router.get("/dashboard")
async def get_care_manager_dashboard(
    current_user: User = Depends(get_current_care_manager)
):
    """
    Care Manager dashboard endpoint.
    Only accessible by users with CARE_MANAGER role.
    """
    return {
        "message": "Welcome to Care Manager Dashboard",
        "user": {
            "username": current_user.username,
            "role": current_user.role.value
        },
    }


@router.get("/profile")
async def get_care_manager_profile(
    current_user: User = Depends(get_current_care_manager)
):
    """
    Get Care Manager profile.
    Only accessible by Care Managers.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }
