from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_patient
from .schemas import PathwayResponse
from .service import run_pathway

router = APIRouter(
    prefix="/patients/{patient_id}/pathway",
    tags=["Patient - Module 3: Pathway"],
    dependencies=[Depends(get_current_patient)],
)


@router.post("/", response_model=PathwayResponse)
def trigger_pathway(patient_id: str):
    """
    Runs the pathway agent (CMS claims -> feature engineering -> ML risk score)
    and returns whether the patient is NOT_AVOIDABLE (-> ER) or
    POTENTIALLY_AVOIDABLE (-> continues to Care Options).
    Only accessible by authenticated Patients.
    """
    try:
        return run_pathway(patient_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
