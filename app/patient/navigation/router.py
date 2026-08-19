from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_patient
from .schemas import NavigationResponse, UpdateBookingRequest
from .service import run_navigation, update_booking

router = APIRouter(
    prefix="/patients/{patient_id}/navigation",
    tags=["Patient - Module 5: Navigation/Booking"],
    dependencies=[Depends(get_current_patient)],
)


class NavigationRequest(BaseModel):
    category: str  # pcp | specialist | urgent-care | telehealth, from Care Options step


@router.post("/", response_model=NavigationResponse)
def trigger_navigation(patient_id: str, payload: NavigationRequest):
    """
    Runs the navigation agent: ranks providers/slots for the given category
    and books the appointment (agent writes via POST /appointments internally).
    The resulting appointment_id/scheduled_at also surfaces in the patient's
    Appointment sidebar and the Care Manager's Post Discharge view, since
    both read from the same appointments resource.
    Only accessible by authenticated Patients.
    """
    try:
        return run_navigation(patient_id, payload.category)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))


@router.put("/booking", response_model=NavigationResponse)
def adjust_booking(patient_id: str, payload: UpdateBookingRequest):
    """
    Adjusts or reschedules an existing appointment for the patient.
    Allows changing appointment slot/time, provider, care category, or notes.
    Reflects automatically in the patient sidebar and Care Manager post-discharge view.
    Only accessible by authenticated Patients.
    """
    try:
        return update_booking(patient_id, payload)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
