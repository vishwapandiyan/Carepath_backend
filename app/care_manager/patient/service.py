"""
Patient Service — full CRUD and MRN auto-generation for Care Manager.
Uses unified PatientEHR model (app.models.ehr).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.patient.schemas import PatientCreate, PatientListOut, PatientOut, PatientUpdate
from app.models.ehr import PatientEHR

logger = logging.getLogger(__name__)


def to_patient_out(patient: PatientEHR) -> PatientOut:
    """Helper to convert PatientEHR ORM model to PatientOut schema safely."""
    pid = patient.patient_id or str(patient.id)
    return PatientOut(
        id=pid,
        mrn=patient.mrn or pid,
        name=patient.name or "N/A",
        dob=patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        gender=patient.gender,
        contact_number=patient.contact_number,
        email=patient.email,
        address=patient.address,
        insurance_id=patient.insurance_id or patient.insurance_type,
        admission_date=patient.admission_date.isoformat() if patient.admission_date else None,
        discharge_date=patient.discharge_date.isoformat() if patient.discharge_date else None,
        is_active=bool(patient.is_active != 0),
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


async def generate_next_mrn(db: AsyncSession) -> str:
    """Auto-generates a unique Medical Record Number (MRN)."""
    count_stmt = select(func.count(PatientEHR.id))
    result = await db.execute(count_stmt)
    total_count = result.scalar() or 0

    candidate_seq = total_count + 1
    while True:
        candidate_mrn = f"MRN{candidate_seq:08d}"
        check_stmt = select(PatientEHR.patient_id).where(PatientEHR.mrn == candidate_mrn)
        existing = (await db.execute(check_stmt)).scalar_one_or_none()
        if existing is None:
            return candidate_mrn
        candidate_seq += 1


async def create_patient(payload: PatientCreate, db: AsyncSession) -> PatientOut:
    """Create a new patient profile using PatientEHR."""
    mrn_to_use = payload.mrn.strip() if payload.mrn else await generate_next_mrn(db)

    if payload.mrn:
        check_stmt = select(PatientEHR.id).where(
            (PatientEHR.mrn == mrn_to_use) | (PatientEHR.patient_id == mrn_to_use)
        )
        existing = (await db.execute(check_stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patient with MRN/ID '{mrn_to_use}' already exists.",
            )

    now = datetime.now(timezone.utc)
    pid = f"PAT_{uuid.uuid4().hex[:8].upper()}"

    dob_date = None
    if payload.dob:
        try:
            dob_date = datetime.strptime(payload.dob, "%Y-%m-%d").date()
        except ValueError:
            pass

    patient = PatientEHR(
        patient_id=pid,
        mrn=mrn_to_use,
        name=payload.name,
        date_of_birth=dob_date,
        age=30,  # default
        gender=payload.gender or "other",
        bmi=25.0,
        insurance_type=payload.insurance_id or "Private",
        hemoglobin=12.0,
        creatinine=1.0,
        glucose=100,
        wbc_count=7.0,
        previous_admissions_12m=0,
        previous_er_visits_12m=0,
        contact_number=payload.contact_number,
        email=payload.email,
        address=payload.address,
        insurance_id=payload.insurance_id,
        is_active=1,
        created_at=now,
        updated_at=now,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info("Created patient | patient_id=%s | MRN=%s | name=%s", patient.patient_id, patient.mrn, patient.name)
    return to_patient_out(patient)


async def list_patients(
    skip: int, limit: int, search: str | None, include_inactive: bool, db: AsyncSession
) -> PatientListOut:
    """List all patient records from patient_ehr with pagination and optional search filter."""
    query = select(PatientEHR)
    count_query = select(func.count(PatientEHR.id))

    if not include_inactive:
        query = query.where(PatientEHR.is_active != 0)
        count_query = count_query.where(PatientEHR.is_active != 0)

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        filter_cond = or_(
            PatientEHR.name.ilike(search_term),
            PatientEHR.mrn.ilike(search_term),
            PatientEHR.patient_id.ilike(search_term),
            PatientEHR.insurance_id.ilike(search_term),
        )
        query = query.where(filter_cond)
        count_query = count_query.where(filter_cond)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(PatientEHR.id.asc()).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    patient_outs = [to_patient_out(p) for p in rows]
    return PatientListOut(
        total=total,
        skip=skip,
        limit=limit,
        patients=patient_outs,
    )


async def get_patient_by_id(patient_id: str, db: AsyncSession) -> PatientOut:
    """Get single patient profile by patient_id (PAT_XXXXXXXX), MRN, or integer ID."""
    conds = [
        PatientEHR.patient_id == patient_id,
        PatientEHR.mrn == patient_id,
    ]
    if patient_id.isdigit():
        conds.append(PatientEHR.id == int(patient_id))

    query = select(PatientEHR).where(or_(*conds))
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )
    return to_patient_out(patient)


async def update_patient(
    patient_id: str, payload: PatientUpdate, db: AsyncSession
) -> PatientOut:
    """Update patient profile."""
    conds = [
        PatientEHR.patient_id == patient_id,
        PatientEHR.mrn == patient_id,
    ]
    if patient_id.isdigit():
        conds.append(PatientEHR.id == int(patient_id))

    query = select(PatientEHR).where(or_(*conds))
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )

    for field, val in payload.model_dump(exclude_unset=True).items():
        if field == "dob" and val:
            try:
                patient.date_of_birth = datetime.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                pass
        elif hasattr(patient, field):
            setattr(patient, field, val)

    patient.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(patient)
    logger.info("Updated patient | patient_id=%s | MRN=%s", patient.patient_id, patient.mrn)
    return to_patient_out(patient)


async def delete_patient(patient_id: str, db: AsyncSession) -> dict:
    """Soft delete patient profile record (is_active=0)."""
    conds = [
        PatientEHR.patient_id == patient_id,
        PatientEHR.mrn == patient_id,
    ]
    if patient_id.isdigit():
        conds.append(PatientEHR.id == int(patient_id))

    query = select(PatientEHR).where(or_(*conds))
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )

    patient.is_active = 0
    patient.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("Soft-deleted patient | patient_id=%s | MRN=%s", patient.patient_id, patient.mrn)
    return {
        "message": f"Patient '{patient_id}' deactivated successfully.",
        "patient_id": patient.patient_id,
        "mrn": patient.mrn or patient.patient_id,
        "is_active": False,
    }
