from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_patient
from .schemas import FollowUpResponse
from .service import run_followup

router = APIRouter(
    prefix="/patients/{patient_id}/follow-up",
    tags=["Patient - Module 6: Follow-up"],
    dependencies=[Depends(get_current_patient)],
)


@router.post("/", response_model=FollowUpResponse)
def trigger_followup(patient_id: str):
    """
    Runs the Telegram follow-up agent: sets up the plan, check-in schedule,
    and reminders after an appointment/care pathway has been established.
    Only accessible by authenticated Patients.
    """
    try:
        return run_followup(patient_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))


@router.get("/", response_model=FollowUpResponse)
def get_followup_status(patient_id: str):
    """
    Read-only view of current follow-up plan/check-in status —
    used by the Care Manager's Post Discharge view.
    Only accessible by authenticated Patients.
    """
    # TODO: read stored follow-up state rather than re-triggering the agent
    raise HTTPException(status_code=501, detail="Not yet implemented — read stored follow-up state")
