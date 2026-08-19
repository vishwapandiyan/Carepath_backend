from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_patient
from app.db.session import get_db
from app.models import User

router = APIRouter()


@router.get("/dashboard")
async def get_patient_dashboard(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db)
):
    """
    Patient dashboard endpoint.
    Only accessible by users with PATIENT role.
    """
    return {
        "message": "Welcome to Patient Dashboard",
        "user": {
            "username": current_user.username,
            "role": current_user.role.value
        },
        "patient": {
            "mrn": getattr(current_user, "patient", None).mrn if getattr(current_user, "patient", None) else None,
        },
    }
