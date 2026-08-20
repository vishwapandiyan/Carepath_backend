"""
Care Manager — Module 1: Patient CRUD Router (/patients)
"""

from fastapi import APIRouter, Depends, Query, status

from app.care_manager.patient import schemas, service
from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

router = APIRouter(
    prefix="/patients",
    tags=["Care Manager - Module 1: Patient"],
)


@router.post(
    "/",
    response_model=schemas.PatientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new patient profile",
    description="Create a patient record. If MRN is not provided, auto-generates sequential MRN like MRN000001 or MRN040001.",
)
async def create_patient(
    payload: schemas.PatientCreate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PatientOut:
    return await service.create_patient(payload, db)


@router.get(
    "/",
    response_model=schemas.PatientListOut,
    summary="List all patients (paginated)",
    description="List active patient records with pagination and optional search filter (matches name, MRN, insurance ID).",
)
async def list_patients(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max number of records to return"),
    search: str | None = Query(None, description="Optional search term (name, MRN, or insurance ID)"),
    include_inactive: bool = Query(False, description="Whether to include soft-deleted patients"),
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PatientListOut:
    return await service.list_patients(skip, limit, search, include_inactive, db)


@router.get(
    "/{patient_id}",
    response_model=schemas.PatientOut,
    summary="Get a single patient profile",
    description="Fetch patient profile by internal ID or MRN.",
)
async def get_patient(
    patient_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PatientOut:
    return await service.get_patient_by_id(patient_id, db)


@router.put(
    "/{patient_id}",
    response_model=schemas.PatientOut,
    summary="Update a patient profile",
    description="Update a patient's profile details.",
)
async def update_patient(
    patient_id: str,
    payload: schemas.PatientUpdate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
) -> schemas.PatientOut:
    return await service.update_patient(patient_id, payload, db)


@router.delete(
    "/{patient_id}",
    summary="Deactivate / soft-delete a patient record",
    description="Deactivates a patient profile record (soft delete setting is_active=False).",
)
async def delete_patient(
    patient_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_care_manager),
):
    return await service.delete_patient(patient_id, db)
