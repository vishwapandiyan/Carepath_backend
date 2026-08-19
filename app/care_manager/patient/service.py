"""
Patient Service — full CRUD and MRN auto-generation for Care Manager.
Supports 40,000+ existing database rows (where primary key is patient_id like PAT_000001).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.patient.schemas import PatientCreate, PatientListOut, PatientOut, PatientUpdate
from app.db.models import Patient

logger = logging.getLogger(__name__)


def to_patient_out(patient: Patient) -> PatientOut:
    """Helper to convert Patient ORM model to PatientOut schema safely."""
    pid = patient.patient_id or patient.id or ""
    return PatientOut(
        id=pid,
        mrn=patient.mrn or pid,
        name=patient.name or patient.full_name or "N/A",
        dob=patient.dob,
        gender=patient.gender,
        contact_number=patient.contact_number,
        email=patient.email,
        address=patient.address,
        insurance_id=patient.insurance_id,
        admission_date=patient.admission_date,
        discharge_date=patient.discharge_date,
        is_active=patient.is_active if patient.is_active is not None else True,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


async def generate_next_mrn(db: AsyncSession) -> str:
    """
    Auto-generates a unique Medical Record Number (MRN).
    Supports large databases (40,000+ rows).
    Formats like MRN000001, MRN040001, etc.
    """
    count_stmt = select(func.count(Patient.patient_id))
    result = await db.execute(count_stmt)
    total_count = result.scalar() or 0

    candidate_seq = total_count + 1
    while True:
        candidate_mrn = f"MRN{candidate_seq:05d}"
        # Check uniqueness across mrn, patient_id, and id
        check_stmt = select(Patient.patient_id).where(
            (Patient.mrn == candidate_mrn)
            | (Patient.patient_id == candidate_mrn)
            | (Patient.id == candidate_mrn)
        )
        existing = (await db.execute(check_stmt)).scalar_one_or_none()
        if existing is None:
            return candidate_mrn
        candidate_seq += 1


async def create_patient(payload: PatientCreate, db: AsyncSession) -> PatientOut:
    """
    Create a new patient profile.
    If MRN is not provided, auto-generate sequential MRN (e.g. MRN040001).
    """
    mrn_to_use = payload.mrn.strip() if payload.mrn else await generate_next_mrn(db)

    # Check if provided MRN is already taken
    if payload.mrn:
        check_stmt = select(Patient.patient_id).where(
            (Patient.mrn == mrn_to_use)
            | (Patient.patient_id == mrn_to_use)
            | (Patient.id == mrn_to_use)
        )
        existing = (await db.execute(check_stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patient with MRN/ID '{mrn_to_use}' already exists.",
            )

    now = datetime.now(timezone.utc)
    pid = f"PAT_{uuid.uuid4().hex[:8].upper()}"

    patient = Patient(
        patient_id=pid,
        id=pid,
        mrn=mrn_to_use,
        name=payload.name,
        full_name=payload.name,
        dob=payload.dob,
        gender=payload.gender,
        contact_number=payload.contact_number,
        email=payload.email,
        address=payload.address,
        insurance_id=payload.insurance_id,
        admission_date=payload.admission_date,
        discharge_date=payload.discharge_date,
        is_active=True,
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
    """
    List patient profiles with pagination and search filter.
    """
    query = select(Patient)
    count_query = select(func.count(Patient.patient_id))

    if not include_inactive:
        query = query.where((Patient.is_active.is_(True)) | (Patient.is_active.is_(None)))
        count_query = count_query.where((Patient.is_active.is_(True)) | (Patient.is_active.is_(None)))

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        filter_cond = (
            Patient.name.ilike(search_term)
            | Patient.full_name.ilike(search_term)
            | Patient.mrn.ilike(search_term)
            | Patient.patient_id.ilike(search_term)
            | Patient.insurance_id.ilike(search_term)
        )
        query = query.where(filter_cond)
        count_query = count_query.where(filter_cond)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Patient.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    patient_outs = [to_patient_out(p) for p in rows]
    return PatientListOut(
        total=total,
        skip=skip,
        limit=limit,
        patients=patient_outs,
    )


async def get_patient_by_id(patient_id: str, db: AsyncSession) -> PatientOut:
    """Get single patient profile by patient_id, MRN, or id."""
    query = select(Patient).where(
        (Patient.patient_id == patient_id)
        | (Patient.mrn == patient_id)
        | (Patient.id == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )
    return to_patient_out(patient)


async def update_patient(
    patient_id: str, payload: PatientUpdate, db: AsyncSession
) -> PatientOut:
    """Full update patient profile."""
    query = select(Patient).where(
        (Patient.patient_id == patient_id)
        | (Patient.mrn == patient_id)
        | (Patient.id == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, val)

    patient.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(patient)
    logger.info("Updated patient | patient_id=%s | MRN=%s", patient.patient_id, patient.mrn)
    return to_patient_out(patient)


async def delete_patient(patient_id: str, db: AsyncSession) -> dict:
    """Soft delete patient profile record (is_active=False)."""
    query = select(Patient).where(
        (Patient.patient_id == patient_id)
        | (Patient.mrn == patient_id)
        | (Patient.id == patient_id)
    )
    patient = (await db.execute(query)).scalars().first()

    if patient is None or patient.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID/MRN '{patient_id}' not found.",
        )

    patient.is_active = False
    patient.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("Soft-deleted patient | patient_id=%s | MRN=%s", patient.patient_id, patient.mrn)
    return {
        "message": f"Patient '{patient_id}' deactivated successfully.",
        "patient_id": patient.patient_id,
        "mrn": patient.mrn or patient.patient_id,
        "is_active": False,
    }
