from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_care_manager
from app.db.session import get_db
from app.models import User
from app.schemas.ehr import (
    PatientEHRCreate,
    PatientEHRListResponse,
    PatientEHRResponse,
    PatientEHRUpdate,
)
from app.services.ehr_crud_service import ehr_crud_service

router = APIRouter()


@router.post("/patients", response_model=PatientEHRResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    ehr_data: PatientEHRCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Create a new patient EHR record.
    MRN is auto-generated.
    Only accessible by Care Managers.
    """
    patient = await ehr_crud_service.create_patient_ehr(db, ehr_data)
    return patient


@router.get("/patients", response_model=List[PatientEHRListResponse])
async def list_patients(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Get list of all patients (simplified view).
    Only accessible by Care Managers.
    Supports pagination.
    """
    patients = await ehr_crud_service.get_all_patients(db, skip=skip, limit=limit)
    return patients


@router.get("/patients/{patient_id}", response_model=PatientEHRResponse)
async def get_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Get patient EHR record by ID.
    Only accessible by Care Managers.
    """
    patient = await ehr_crud_service.get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    return patient


@router.get("/patients/mrn/{mrn}", response_model=PatientEHRResponse)
async def get_patient_by_mrn(
    mrn: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Get patient EHR record by MRN.
    Only accessible by Care Managers.
    """
    patient = await ehr_crud_service.get_patient_by_mrn(db, mrn)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with MRN {mrn} not found"
        )
    return patient


@router.put("/patients/{patient_id}", response_model=PatientEHRResponse)
async def update_patient(
    patient_id: int,
    ehr_update: PatientEHRUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Update patient EHR record.
    Only accessible by Care Managers.
    All fields are optional - only provided fields will be updated.
    """
    patient = await ehr_crud_service.update_patient_ehr(db, patient_id, ehr_update)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    return patient


@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_care_manager)
):
    """
    Delete patient EHR record.
    Only accessible by Care Managers.
    """
    success = await ehr_crud_service.delete_patient_ehr(db, patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    return None
