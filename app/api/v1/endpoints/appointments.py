"""
Appointments API

Fetch booked appointments for patients from the database.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.security import get_current_patient
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


class AppointmentResponse(BaseModel):
    """Appointment response model."""
    appointment_id: str
    mrn: str
    provider_id: str
    provider_name: Optional[str] = None
    slot_id: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: str
    specialty: Optional[str] = None
    destination: Optional[str] = None
    created_at: Optional[datetime] = None


@router.get(
    "/patients/{patient_id}/appointments",
    response_model=List[AppointmentResponse],
    tags=["Patient - Appointments"],
    summary="Get patient appointments",
    description="Fetch all appointments for a patient from the database"
)
async def get_patient_appointments(
    patient_id: str,
    current_user: User = Depends(get_current_patient),
) -> List[AppointmentResponse]:
    """
    Get all appointments for a patient.
    
    Returns appointments ordered by start_time descending (newest first).
    """
    
    # Verify patient identity
    if current_user.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Cannot access another patient's appointments")
    
    # Get patient MRN
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select as sql_select
    from app.db.base import get_db
    from app.models.ehr import PatientEHR
    
    async for db in get_db():
        try:
            stmt = sql_select(PatientEHR).where(PatientEHR.patient_id == patient_id)
            result = await db.execute(stmt)
            patient_ehr = result.scalar_one_or_none()
            
            if not patient_ehr:
                raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
            
            mrn = patient_ehr.mrn
            if not mrn:
                raise HTTPException(status_code=422, detail="Patient has no MRN assigned")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load patient EHR: {e}")
            raise HTTPException(status_code=500, detail="Failed to load patient data")
    
    # Query appointments from database
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.config import settings
        
        # Get database URL and convert from async to sync format
        db_url = settings.DATABASE_URL
        if 'postgresql+asyncpg://' in db_url:
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        # Connect using psycopg2
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Query appointments
            cursor.execute("""
                SELECT 
                    a.appointment_id,
                    a.mrn,
                    a.provider_id,
                    p.provider_name,
                    a.slot_id,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.specialty,
                    a.destination,
                    a.created_at
                FROM appointments a
                LEFT JOIN appointment_providers p ON a.provider_id = p.provider_id
                WHERE a.mrn = %s
                ORDER BY a.start_time DESC
                LIMIT 50
            """, (mrn,))
            
            rows = cursor.fetchall()
            
            appointments = []
            for row in rows:
                appointments.append(AppointmentResponse(
                    appointment_id=row['appointment_id'],
                    mrn=row['mrn'],
                    provider_id=row['provider_id'],
                    provider_name=row['provider_name'],
                    slot_id=row['slot_id'],
                    start_time=row['start_time'],
                    end_time=row['end_time'],
                    status=row['status'],
                    specialty=row['specialty'],
                    destination=row['destination'],
                    created_at=row['created_at']
                ))
            
            logger.info(f"Fetched {len(appointments)} appointments for patient {patient_id}")
            return appointments
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"Failed to fetch appointments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch appointments: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Cancel Appointment
# ─────────────────────────────────────────────────────────────────────────────

class CancelAppointmentRequest(BaseModel):
    """Request to cancel an appointment."""
    appointment_id: str = Field(..., description="ID of the appointment to cancel")
    reason: Optional[str] = Field(None, description="Optional reason for cancellation")


class CancelAppointmentResponse(BaseModel):
    """Response after cancelling an appointment."""
    success: bool
    message: str
    appointment_id: str
    status: str


@router.post(
    "/patients/{patient_id}/appointments/{appointment_id}/cancel",
    response_model=CancelAppointmentResponse,
    tags=["Patient - Appointments"],
    summary="Cancel an appointment",
    description="Cancel a booked appointment and free the slot"
)
async def cancel_patient_appointment(
    patient_id: str,
    appointment_id: str,
    request: CancelAppointmentRequest,
    current_user: User = Depends(get_current_patient),
) -> CancelAppointmentResponse:
    """
    Cancel a patient appointment.
    
    - Marks appointment as CANCELLED in database
    - Frees the provider slot
    - Does NOT delete the appointment record (for history)
    """
    
    # Verify patient identity
    if current_user.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Cannot cancel another patient's appointment")
    
    # Verify appointment belongs to patient
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select as sql_select, update
    from app.db.base import get_db
    from app.models.ehr import PatientEHR
    
    async for db in get_db():
        try:
            # Get patient MRN
            stmt = sql_select(PatientEHR).where(PatientEHR.patient_id == patient_id)
            result = await db.execute(stmt)
            patient_ehr = result.scalar_one_or_none()
            
            if not patient_ehr:
                raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
            
            mrn = patient_ehr.mrn
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load patient data: {e}")
            raise HTTPException(status_code=500, detail="Failed to load patient data")
    
    try:
        import psycopg2
        from app.config import settings
        
        # Get database URL
        db_url = settings.DATABASE_URL
        if 'postgresql+asyncpg://' in db_url:
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        try:
            # Verify appointment belongs to patient
            cursor.execute(
                "SELECT mrn, slot_id, status FROM appointments WHERE appointment_id = %s",
                (appointment_id,)
            )
            appt_row = cursor.fetchone()
            
            if not appt_row:
                raise HTTPException(status_code=404, detail="Appointment not found")
            
            if appt_row[0] != mrn:
                raise HTTPException(status_code=403, detail="Appointment does not belong to this patient")
            
            if appt_row[2] in ('CANCELLED', 'COMPLETED'):
                raise HTTPException(status_code=400, detail=f"Cannot cancel appointment with status: {appt_row[2]}")
            
            slot_id = appt_row[1]
            
            # Update appointment status to CANCELLED
            cursor.execute(
                "UPDATE appointments SET status = 'CANCELLED', updated_at = NOW() WHERE appointment_id = %s",
                (appointment_id,)
            )
            
            # Free the slot (mark as available)
            if slot_id:
                cursor.execute(
                    "UPDATE provider_slots SET status = 'AVAILABLE' WHERE slot_id = %s",
                    (slot_id,)
                )
                logger.info(f"Freed slot {slot_id} after cancelling appointment {appointment_id}")
            
            conn.commit()
            
            logger.info(f"✓ Cancelled appointment {appointment_id} for patient {patient_id}")
            
            return CancelAppointmentResponse(
                success=True,
                message="Appointment cancelled successfully",
                appointment_id=appointment_id,
                status="CANCELLED"
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel appointment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel appointment: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Reschedule Appointment
# ─────────────────────────────────────────────────────────────────────────────

class RescheduleAppointmentRequest(BaseModel):
    """Request to reschedule an appointment."""
    new_slot_id: str = Field(..., description="ID of the new time slot")
    reason: Optional[str] = Field(None, description="Optional reason for rescheduling")


class RescheduleAppointmentResponse(BaseModel):
    """Response after rescheduling an appointment."""
    success: bool
    message: str
    appointment_id: str
    old_slot_id: Optional[str]
    new_slot_id: str
    new_start_time: datetime
    new_end_time: datetime
    status: str


@router.post(
    "/patients/{patient_id}/appointments/{appointment_id}/reschedule",
    response_model=RescheduleAppointmentResponse,
    tags=["Patient - Appointments"],
    summary="Reschedule an appointment",
    description="Change appointment to a new time slot (frees old slot)"
)
async def reschedule_patient_appointment(
    patient_id: str,
    appointment_id: str,
    request: RescheduleAppointmentRequest,
    current_user: User = Depends(get_current_patient),
) -> RescheduleAppointmentResponse:
    """
    Reschedule a patient appointment to a new time slot.
    
    - Updates appointment with new slot
    - Frees the old slot
    - Books the new slot
    - Maintains appointment history
    """
    
    # Verify patient identity
    if current_user.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Cannot reschedule another patient's appointment")
    
    # Get patient MRN
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select as sql_select
    from app.db.base import get_db
    from app.models.ehr import PatientEHR
    
    async for db in get_db():
        try:
            stmt = sql_select(PatientEHR).where(PatientEHR.patient_id == patient_id)
            result = await db.execute(stmt)
            patient_ehr = result.scalar_one_or_none()
            
            if not patient_ehr:
                raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
            
            mrn = patient_ehr.mrn
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load patient data: {e}")
            raise HTTPException(status_code=500, detail="Failed to load patient data")
    
    try:
        import psycopg2
        from app.config import settings
        
        db_url = settings.DATABASE_URL
        if 'postgresql+asyncpg://' in db_url:
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        try:
            # Verify appointment belongs to patient
            cursor.execute(
                "SELECT mrn, slot_id, provider_id, status FROM appointments WHERE appointment_id = %s",
                (appointment_id,)
            )
            appt_row = cursor.fetchone()
            
            if not appt_row:
                raise HTTPException(status_code=404, detail="Appointment not found")
            
            if appt_row[0] != mrn:
                raise HTTPException(status_code=403, detail="Appointment does not belong to this patient")
            
            if appt_row[3] in ('CANCELLED', 'COMPLETED'):
                raise HTTPException(status_code=400, detail=f"Cannot reschedule appointment with status: {appt_row[3]}")
            
            old_slot_id = appt_row[1]
            provider_id = appt_row[2]
            
            # Verify new slot is available and belongs to same provider
            cursor.execute(
                "SELECT provider_id, start_time, end_time, status FROM provider_slots WHERE slot_id = %s",
                (request.new_slot_id,)
            )
            slot_row = cursor.fetchone()
            
            if not slot_row:
                raise HTTPException(status_code=404, detail="New slot not found")
            
            if slot_row[0] != provider_id:
                raise HTTPException(status_code=400, detail="New slot must be with the same provider")
            
            if slot_row[3] != 'AVAILABLE':
                raise HTTPException(status_code=400, detail="New slot is not available")
            
            new_start_time = slot_row[1]
            new_end_time = slot_row[2]
            
            # Free old slot
            if old_slot_id:
                cursor.execute(
                    "UPDATE provider_slots SET status = 'AVAILABLE' WHERE slot_id = %s",
                    (old_slot_id,)
                )
                logger.info(f"Freed old slot {old_slot_id}")
            
            # Book new slot
            cursor.execute(
                "UPDATE provider_slots SET status = 'BOOKED' WHERE slot_id = %s",
                (request.new_slot_id,)
            )
            
            # Update appointment
            cursor.execute(
                """
                UPDATE appointments 
                SET slot_id = %s, 
                    start_time = %s, 
                    end_time = %s,
                    status = 'BOOKED',
                    updated_at = NOW()
                WHERE appointment_id = %s
                """,
                (request.new_slot_id, new_start_time, new_end_time, appointment_id)
            )
            
            conn.commit()
            
            logger.info(f"✓ Rescheduled appointment {appointment_id} from slot {old_slot_id} to {request.new_slot_id}")
            
            return RescheduleAppointmentResponse(
                success=True,
                message="Appointment rescheduled successfully",
                appointment_id=appointment_id,
                old_slot_id=old_slot_id,
                new_slot_id=request.new_slot_id,
                new_start_time=new_start_time,
                new_end_time=new_end_time,
                status="BOOKED"
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reschedule appointment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reschedule appointment: {str(e)}")



# ─────────────────────────────────────────────────────────────────────────────
# Get Available Slots for Provider
# ─────────────────────────────────────────────────────────────────────────────

class AvailableSlot(BaseModel):
    """Available time slot for booking."""
    slot_id: str
    provider_id: str
    start_time: datetime
    end_time: datetime
    status: str


@router.get(
    "/providers/{provider_id}/available-slots",
    response_model=List[AvailableSlot],
    tags=["Patient - Appointments"],
    summary="Get available slots for a provider",
    description="Fetch available time slots for rescheduling"
)
async def get_available_slots(
    provider_id: str,
    days_ahead: int = 7,
    current_user: User = Depends(get_current_patient),
) -> List[AvailableSlot]:
    """
    Get available time slots for a provider.
    
    - Only returns slots with status 'AVAILABLE'
    - Filters to next N days (default 7)
    - Sorted by start_time
    """
    
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.config import settings
        from datetime import datetime, timedelta
        
        db_url = settings.DATABASE_URL
        if 'postgresql+asyncpg://' in db_url:
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get available slots for the next N days
            end_date = datetime.now() + timedelta(days=days_ahead)
            
            cursor.execute("""
                SELECT 
                    slot_id,
                    provider_id,
                    start_time,
                    end_time,
                    status
                FROM provider_slots
                WHERE provider_id = %s
                  AND status = 'AVAILABLE'
                  AND start_time >= NOW()
                  AND start_time <= %s
                ORDER BY start_time ASC
                LIMIT 50
            """, (provider_id, end_date))
            
            rows = cursor.fetchall()
            
            slots = []
            for row in rows:
                slots.append(AvailableSlot(
                    slot_id=row['slot_id'],
                    provider_id=row['provider_id'],
                    start_time=row['start_time'],
                    end_time=row['end_time'],
                    status=row['status']
                ))
            
            logger.info(f"Found {len(slots)} available slots for provider {provider_id}")
            return slots
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"Failed to fetch available slots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch available slots: {str(e)}")
