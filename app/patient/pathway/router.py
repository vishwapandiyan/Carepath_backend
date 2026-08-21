from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_patient
from app.db.session import get_db
from app.patient.safety.service import _get_ehr_for_patient
from .schemas import PathwayRequest, PathwayResponse
from .service import run_pathway

router = APIRouter(
    prefix="/patients/{patient_id}/pathway",
    tags=["Patient - Module 3: Pathway"],
    dependencies=[Depends(get_current_patient)],
)


@router.post("/", response_model=PathwayResponse)
async def trigger_pathway(
    patient_id: str,
    payload: Optional[PathwayRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Runs the Clinical Emergency Risk Model & CarePlan Agent.
    Evaluates Extracted Intake Data + Red Flag Screening + Patient EHR record.
    Returns calculated Emergency Risk Score, Decision, and CarePlan Options.
    """
    try:
        req = payload or PathwayRequest(patient_id=patient_id)
        if not req.patient_id:
            req.patient_id = patient_id
        
        ehr_data = await _get_ehr_for_patient(patient_id, db)
        return run_pathway(patient_id, request=req, ehr_data=ehr_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
