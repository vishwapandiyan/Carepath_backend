from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_patient
from .schemas import CareOptionsResponse
from .service import get_care_options

router = APIRouter(
    prefix="/patients/{patient_id}/care-options",
    tags=["Patient - Module 4: Care Options"],
    dependencies=[Depends(get_current_patient)],
)


@router.post("/", response_model=CareOptionsResponse)
def trigger_care_options(patient_id: str):
    """
    Runs the care-options agent to bucket the patient into one of:
    pcp | specialist | urgent-care | telehealth.
    Called after Pathway returns POTENTIALLY_AVOIDABLE.
    Only accessible by authenticated Patients.
    """
    try:
        return get_care_options(patient_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
