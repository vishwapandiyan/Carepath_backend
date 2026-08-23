"""
Care Plan API - Query endpoints for the new agentic care plan system
Reads from: care_plans, care_plan_tasks, follow_up_checkins tables
"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text
from pydantic import BaseModel, Field

from app.core.security import get_current_patient, get_current_user
from app.db.base import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────────────────────

class CareTask(BaseModel):
    """Individual care plan task"""
    task_id: str
    task_type: str
    description: str
    status: str
    priority: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed_date: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class FollowUpCheckIn(BaseModel):
    """Follow-up check-in record"""
    checkin_id: str
    task_id: str
    checkin_type: Optional[str] = None
    message: str
    response: Optional[str] = None
    response_received_at: Optional[str] = None
    classification: Optional[str] = None
    status: str
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class CarePlan(BaseModel):
    """Complete care plan with tasks"""
    care_plan_id: str
    mrn: str
    patient_id: Optional[int] = None
    risk_level: str
    intensity: str
    status: str
    doctor_instructions: Optional[str] = None
    clinical_notes: Optional[str] = None
    tasks: List[CareTask] = []
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None

    class Config:
        from_attributes = True


class CheckInsResponse(BaseModel):
    """Response for check-ins list"""
    checkins: List[FollowUpCheckIn]
    total: int


class TasksResponse(BaseModel):
    """Response for tasks list"""
    tasks: List[CareTask]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

async def get_care_plan_with_tasks(care_plan_id: str, db: AsyncSession) -> Optional[CarePlan]:
    """Get care plan by ID with all tasks loaded"""
    
    # Query using raw SQL since we're dealing with existing tables
    query = """
    SELECT 
        cp.id as care_plan_id,
        cp.mrn,
        cp.patient_id,
        cp.risk_level,
        cp.intensity,
        cp.status,
        cp.doctor_instructions,
        cp.clinical_notes,
        cp.created_at,
        cp.updated_at,
        cp.expires_at
    FROM care_plans cp
    WHERE cp.id = :care_plan_id
    """
    
    result = await db.execute(
        select([care_plan_id]).from_statement(query),
        {"care_plan_id": care_plan_id}
    )
    plan_row = result.first()
    
    if not plan_row:
        return None
    
    # Get tasks
    tasks_query = """
    SELECT 
        id as task_id,
        task_type,
        task_description as description,
        status,
        priority,
        scheduled_date,
        completed_date,
        created_at,
        updated_at
    FROM care_plan_tasks
    WHERE care_plan_id = :care_plan_id
    ORDER BY created_at ASC
    """
    
    tasks_result = await db.execute(
        select([care_plan_id]).from_statement(tasks_query),
        {"care_plan_id": care_plan_id}
    )
    tasks = tasks_result.all()
    
    # Build response
    return CarePlan(
        care_plan_id=plan_row[0],
        mrn=plan_row[1],
        patient_id=plan_row[2],
        risk_level=plan_row[3],
        intensity=plan_row[4],
        status=plan_row[5],
        doctor_instructions=plan_row[6],
        clinical_notes=plan_row[7],
        created_at=str(plan_row[8]),
        updated_at=str(plan_row[9]),
        expires_at=str(plan_row[10]) if plan_row[10] else None,
        tasks=[
            CareTask(
                task_id=t[0],
                task_type=t[1],
                description=t[2],
                status=t[3],
                priority=t[4],
                scheduled_date=str(t[5]) if t[5] else None,
                completed_date=str(t[6]) if t[6] else None,
                created_at=str(t[7]),
                updated_at=str(t[8])
            )
            for t in tasks
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/my-care-plan",
    response_model=CarePlan,
    tags=["Care Plans"],
    summary="Get my active care plan - PATIENTS ONLY"
)
async def get_my_care_plan(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db)
) -> CarePlan:
    """
    Get the active care plan for the current patient from post_discharge_statuses.
    
    **Access:** Patients only
    
    **Returns:** Complete care plan with all tasks (transformed from post_discharge_statuses)
    
    **NOTE:** This reads from the care manager's post_discharge_statuses table which is 
    updated by the care plan revision agent when patients submit concerns.
    """
    
    patient_id = current_user.patient_id
    if not patient_id:
        raise HTTPException(status_code=400, detail="Patient ID not found in user record")
    
    logger.info(f"My care plan request for patient: {patient_id}")
    
    # Get patient's MRN
    from app.models.ehr import PatientEHR
    from app.db.models import PostDischargeStatus
    from sqlalchemy import text
    
    stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
    result = await db.execute(stmt)
    patient_ehr = result.scalar_one_or_none()
    
    if not patient_ehr:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    mrn = patient_ehr.mrn
    
    # Get post_discharge_status which contains the care plan data
    stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient_id)
    result = await db.execute(stmt)
    status_row = result.scalar_one_or_none()
    
    if not status_row or not status_row.care_plan:
        # Try to get from PostgreSQL care_plans table as fallback
        query = text("""
            SELECT 
                cp.id,
                cp.mrn,
                cp.risk_level,
                cp.intensity,
                cp.status,
                cp.doctor_instructions,
                cp.created_at,
                cp.updated_at
            FROM care_plans cp
            WHERE cp.mrn = :mrn AND cp.status = 'ACTIVE'
            ORDER BY cp.created_at DESC
            LIMIT 1
        """)
        
        pg_result = await db.execute(query, {"mrn": mrn})
        plan_row = pg_result.first()
        
        if not plan_row:
            raise HTTPException(
                status_code=404,
                detail="No active care plan found. Please contact your care manager."
            )
        
        care_plan_id = plan_row[0]
        
        # Get tasks from PostgreSQL
        tasks_query = text("""
            SELECT 
                id,
                task_type,
                task_description,
                status,
                priority,
                scheduled_date,
                created_at,
                updated_at
            FROM care_plan_tasks
            WHERE care_plan_id = :care_plan_id
            ORDER BY created_at ASC
        """)
        
        tasks_result = await db.execute(tasks_query, {"care_plan_id": care_plan_id})
        tasks = tasks_result.all()
        
        return CarePlan(
            care_plan_id=plan_row[0],
            mrn=plan_row[1],
            risk_level=plan_row[2],
            intensity=plan_row[3],
            status=plan_row[4],
            doctor_instructions=plan_row[5],
            created_at=str(plan_row[6]),
            updated_at=str(plan_row[7]),
            tasks=[
                CareTask(
                    task_id=t[0],
                    task_type=t[1],
                    description=t[2],
                    status=t[3],
                    priority=t[4],
                    scheduled_date=str(t[5]) if t[5] else None,
                    completed_date=None,
                    created_at=str(t[6]),
                    updated_at=str(t[7])
                )
                for t in tasks
            ]
        )
    
    # Transform post_discharge_status to CarePlan format
    care_plan_data = status_row.care_plan
    
    # Get care plan ID from PostgreSQL using MRN
    query = text("SELECT id, doctor_instructions, risk_level, intensity, status, created_at, updated_at FROM care_plans WHERE mrn = :mrn AND status = 'ACTIVE' LIMIT 1")
    pg_result = await db.execute(query, {"mrn": mrn})
    pg_row = pg_result.first()
    
    if not pg_row:
        raise HTTPException(
            status_code=404,
            detail="Care plan not found in database. Please contact your care manager."
        )
    
    care_plan_id = pg_row[0]
    doctor_instructions = pg_row[1]
    risk_level = pg_row[2]
    intensity = pg_row[3]
    status = pg_row[4]
    created_at = pg_row[5]
    updated_at = pg_row[6]
    
    # Transform tasks from post_discharge_statuses format to CarePlan format
    tasks = care_plan_data.get("tasks", [])
    
    # If post_discharge_statuses has no tasks, get from PostgreSQL
    if not tasks:
        tasks_query = text("""
            SELECT 
                id,
                task_type,
                task_description,
                status,
                priority,
                scheduled_date,
                created_at,
                updated_at
            FROM care_plan_tasks
            WHERE care_plan_id = :care_plan_id
            ORDER BY created_at ASC
        """)
        
        tasks_result = await db.execute(tasks_query, {"care_plan_id": care_plan_id})
        pg_tasks = tasks_result.all()
        
        tasks = [
            CareTask(
                task_id=str(t[0]),
                task_type=t[1],
                description=t[2],
                status=t[3],
                priority=t[4],
                scheduled_date=str(t[5]) if t[5] else None,
                completed_date=None,
                created_at=str(t[6]),
                updated_at=str(t[7])
            )
            for t in pg_tasks
        ]
    else:
        # Transform from post_discharge_statuses format
        tasks = [
            CareTask(
                task_id=f"task_{idx}",
                task_type="MONITORING",
                description=t.get("task", ""),
                status=t.get("status", "pending").upper(),
                priority=None,
                scheduled_date=None,
                completed_date=None,
                created_at=str(created_at),
                updated_at=str(updated_at)
            )
            for idx, t in enumerate(tasks)
        ]
    
    return CarePlan(
        care_plan_id=care_plan_id,
        mrn=mrn,
        risk_level=risk_level,
        intensity=intensity,
        status=status,
        doctor_instructions=doctor_instructions,
        created_at=str(created_at),
        updated_at=str(updated_at),
        tasks=tasks
    )


@router.get(
    "/patients/{patient_id}/follow-up-tasks",
    response_model=CheckInsResponse,
    tags=["Care Plans"],
    summary="Get follow-up tasks for a patient"
)
async def get_patient_follow_up_tasks(
    patient_id: str,
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db)
) -> CheckInsResponse:
    """
    Get all follow-up check-in tasks for the current patient.
    
    **Access:** Patient only
    
    **Returns:** List of follow-up tasks/check-ins
    """
    
    # Verify patient can only access their own tasks
    if current_user.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Cannot access another patient's tasks")
    
    logger.info(f"Follow-up tasks request for patient: {patient_id}")
    
    # Get patient's MRN
    from app.models.ehr import PatientEHR
    from sqlalchemy import text
    
    stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
    result = await db.execute(stmt)
    patient_ehr = result.scalar_one_or_none()
    
    if not patient_ehr:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Get all follow-up check-ins for this patient's active care plans
    query = text("""
        SELECT 
            fc.id,
            fc.task_id,
            fc.checkin_type,
            fc.checkin_message,
            fc.patient_response,
            fc.response_received_at,
            fc.classification,
            fc.status,
            fc.scheduled_at,
            fc.sent_at,
            fc.created_at
        FROM follow_up_checkins fc
        JOIN care_plans cp ON fc.care_plan_id = cp.id
        WHERE cp.mrn = :mrn AND cp.status = 'ACTIVE'
        ORDER BY fc.created_at DESC
    """)
    
    result = await db.execute(query, {"mrn": patient_ehr.mrn})
    checkins = result.all()
    
    return CheckInsResponse(
        checkins=[
            FollowUpCheckIn(
                checkin_id=c[0],
                task_id=c[1],
                checkin_type=c[2],
                message=c[3] or "",
                response=c[4],
                response_received_at=str(c[5]) if c[5] else None,
                classification=c[6],
                status=c[7],
                scheduled_at=str(c[8]) if c[8] else None,
                sent_at=str(c[9]) if c[9] else None,
                created_at=str(c[10])
            )
            for c in checkins
        ],
        total=len(checkins)
    )


@router.get(
    "/patients/{mrn}/care-plan",
    response_model=CarePlan,
    tags=["Care Plans"],
    summary="Get active care plan by patient MRN - CARE MANAGERS ONLY"
)
async def get_care_plan_by_mrn(
    mrn: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CarePlan:
    """
    Get the active care plan for a patient by their MRN - CARE MANAGERS ONLY.
    
    **Access:** Care managers only
    
    **Returns:** Complete care plan with all tasks
    
    **NOTE:** Patients should NOT use this endpoint. They should use /patients/{patient_id}/follow-up-tasks
    """
    
    # CRITICAL: Block patient access
    if current_user.role == "PATIENT":
        raise HTTPException(
            status_code=403,
            detail="Patients cannot access care plans. Use /patients/{patient_id}/follow-up-tasks instead."
        )
    
    logger.info(f"Care plan request for MRN: {mrn} by care manager: {current_user.username}")
    
    # Query for active care plan using text SQL
    from sqlalchemy import text
    
    query = text("""
        SELECT 
            cp.id,
            cp.mrn,
            cp.patient_id,
            cp.risk_level,
            cp.intensity,
            cp.status,
            cp.doctor_instructions,
            cp.clinical_notes,
            cp.created_at,
            cp.updated_at,
            cp.expires_at
        FROM care_plans cp
        WHERE cp.mrn = :mrn AND cp.status = 'ACTIVE'
        ORDER BY cp.created_at DESC
        LIMIT 1
    """)
    
    result = await db.execute(query, {"mrn": mrn})
    plan_row = result.first()
    
    if not plan_row:
        raise HTTPException(
            status_code=404,
            detail=f"No active care plan found for patient {mrn}"
        )
    
    care_plan_id = plan_row[0]
    
    # Get tasks for this care plan
    tasks_query = text("""
        SELECT 
            id,
            task_type,
            task_description,
            status,
            priority,
            scheduled_date,
            completed_date,
            created_at,
            updated_at
        FROM care_plan_tasks
        WHERE care_plan_id = :care_plan_id
        ORDER BY created_at ASC
    """)
    
    tasks_result = await db.execute(tasks_query, {"care_plan_id": care_plan_id})
    tasks = tasks_result.all()
    
    # Build response
    return CarePlan(
        care_plan_id=plan_row[0],
        mrn=plan_row[1],
        patient_id=plan_row[2],
        risk_level=plan_row[3],
        intensity=plan_row[4],
        status=plan_row[5],
        doctor_instructions=plan_row[6],
        clinical_notes=plan_row[7],
        created_at=str(plan_row[8]),
        updated_at=str(plan_row[9]),
        expires_at=str(plan_row[10]) if plan_row[10] else None,
        tasks=[
            CareTask(
                task_id=t[0],
                task_type=t[1],
                description=t[2],
                status=t[3],
                priority=t[4],
                scheduled_date=str(t[5]) if t[5] else None,
                completed_date=str(t[6]) if t[6] else None,
                created_at=str(t[7]),
                updated_at=str(t[8])
            )
            for t in tasks
        ]
    )


@router.get(
    "/care-plans/{care_plan_id}",
    response_model=CarePlan,
    tags=["Care Plans"],
    summary="Get care plan by ID - CARE MANAGERS ONLY"
)
async def get_care_plan_by_id(
    care_plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CarePlan:
    """
    Get a specific care plan by its ID - CARE MANAGERS ONLY.
    
    **Access:** Care managers only
    
    **Returns:** Complete care plan with all tasks
    
    **NOTE:** Patients should NOT use this endpoint. They should use /patients/{patient_id}/follow-up-tasks
    """
    
    # CRITICAL: Block patient access
    if current_user.role == "PATIENT":
        raise HTTPException(
            status_code=403,
            detail="Patients cannot access care plans. Use /patients/{patient_id}/follow-up-tasks instead."
        )
    
    logger.info(f"Care plan request for ID: {care_plan_id} by care manager: {current_user.username}")
    
    # Get care plan
    query = text("""
        SELECT 
            cp.id,
            cp.mrn,
            cp.patient_id,
            cp.risk_level,
            cp.intensity,
            cp.status,
            cp.doctor_instructions,
            cp.clinical_notes,
            cp.created_at,
            cp.updated_at,
            cp.expires_at
        FROM care_plans cp
        WHERE cp.id = :care_plan_id
    """)
    
    result = await db.execute(query, {"care_plan_id": care_plan_id})
    plan_row = result.first()
    
    if not plan_row:
        raise HTTPException(
            status_code=404,
            detail=f"Care plan {care_plan_id} not found"
        )
    
    # Get tasks
    tasks_query = text("""
        SELECT 
            id,
            task_type,
            task_description,
            status,
            priority,
            scheduled_date,
            completed_date,
            created_at,
            updated_at
        FROM care_plan_tasks
        WHERE care_plan_id = :care_plan_id
        ORDER BY created_at ASC
    """)
    
    tasks_result = await db.execute(tasks_query, {"care_plan_id": care_plan_id})
    tasks = tasks_result.all()
    
    return CarePlan(
        care_plan_id=plan_row[0],
        mrn=plan_row[1],
        patient_id=plan_row[2],
        risk_level=plan_row[3],
        intensity=plan_row[4],
        status=plan_row[5],
        doctor_instructions=plan_row[6],
        clinical_notes=plan_row[7],
        created_at=str(plan_row[8]),
        updated_at=str(plan_row[9]),
        expires_at=str(plan_row[10]) if plan_row[10] else None,
        tasks=[
            CareTask(
                task_id=t[0],
                task_type=t[1],
                description=t[2],
                status=t[3],
                priority=t[4],
                scheduled_date=str(t[5]) if t[5] else None,
                completed_date=str(t[6]) if t[6] else None,
                created_at=str(t[7]),
                updated_at=str(t[8])
            )
            for t in tasks
        ]
    )


@router.get(
    "/care-plans/{care_plan_id}/checkins",
    response_model=CheckInsResponse,
    tags=["Care Plans"],
    summary="Get all check-ins for a care plan - CARE MANAGERS ONLY"
)
async def get_care_plan_checkins(
    care_plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CheckInsResponse:
    """
    Get all follow-up check-ins for a care plan - CARE MANAGERS ONLY.
    
    **Access:** Care managers only
    
    **Returns:** List of check-ins with patient responses and classifications
    
    **NOTE:** Patients should use /patients/{patient_id}/follow-up-tasks instead
    """
    
    # CRITICAL: Block patient access
    if current_user.role == "PATIENT":
        raise HTTPException(
            status_code=403,
            detail="Patients cannot access care plan check-ins. Use /patients/{patient_id}/follow-up-tasks instead."
        )
    
    logger.info(f"Check-ins request for care plan: {care_plan_id} by care manager: {current_user.username}")
    
    # Verify care plan exists
    from sqlalchemy import text
    
    plan_query = text("SELECT mrn FROM care_plans WHERE id = :care_plan_id")
    plan_result = await db.execute(plan_query, {"care_plan_id": care_plan_id})
    plan_row = plan_result.first()
    
    if not plan_row:
        raise HTTPException(
            status_code=404,
            detail=f"Care plan {care_plan_id} not found"
        )
    
    # Get check-ins
    checkins_query = text("""
        SELECT 
            fc.id,
            fc.task_id,
            fc.checkin_type,
            fc.checkin_message,
            fc.patient_response,
            fc.response_received_at,
            fc.classification,
            fc.status,
            fc.scheduled_at,
            fc.sent_at,
            fc.created_at
        FROM follow_up_checkins fc
        WHERE fc.care_plan_id = :care_plan_id
        ORDER BY fc.created_at DESC
    """)
    
    result = await db.execute(checkins_query, {"care_plan_id": care_plan_id})
    checkins = result.all()
    
    return CheckInsResponse(
        checkins=[
            FollowUpCheckIn(
                checkin_id=c[0],
                task_id=c[1],
                checkin_type=c[2],
                message=c[3] or "",
                response=c[4],
                response_received_at=str(c[5]) if c[5] else None,
                classification=c[6],
                status=c[7],
                scheduled_at=str(c[8]) if c[8] else None,
                sent_at=str(c[9]) if c[9] else None,
                created_at=str(c[10])
            )
            for c in checkins
        ],
        total=len(checkins)
    )


@router.get(
    "/care-plans/{care_plan_id}/tasks",
    response_model=TasksResponse,
    tags=["Care Plans"],
    summary="Get all tasks for a care plan - CARE MANAGERS ONLY"
)
async def get_care_plan_tasks(
    care_plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> TasksResponse:
    """
    Get all tasks for a care plan - CARE MANAGERS ONLY.
    
    **Access:** Care managers only
    
    **Returns:** List of care plan tasks with their status
    
    **NOTE:** Patients should use /patients/{patient_id}/follow-up-tasks instead
    """
    
    # CRITICAL: Block patient access
    if current_user.role == "PATIENT":
        raise HTTPException(
            status_code=403,
            detail="Patients cannot access care plan tasks. Use /patients/{patient_id}/follow-up-tasks instead."
        )
    
    logger.info(f"Tasks request for care plan: {care_plan_id} by care manager: {current_user.username}")
    
    # Verify care plan exists
    from sqlalchemy import text
    
    plan_query = text("SELECT mrn FROM care_plans WHERE id = :care_plan_id")
    plan_result = await db.execute(plan_query, {"care_plan_id": care_plan_id})
    plan_row = plan_result.first()
    
    if not plan_row:
        raise HTTPException(
            status_code=404,
            detail=f"Care plan {care_plan_id} not found"
        )
    
    # Get tasks
    tasks_query = text("""
        SELECT 
            id,
            task_type,
            task_description,
            status,
            priority,
            scheduled_date,
            completed_date,
            created_at,
            updated_at
        FROM care_plan_tasks
        WHERE care_plan_id = :care_plan_id
        ORDER BY created_at ASC
    """)
    
    result = await db.execute(tasks_query, {"care_plan_id": care_plan_id})
    tasks = result.all()
    
    return TasksResponse(
        tasks=[
            CareTask(
                task_id=t[0],
                task_type=t[1],
                description=t[2],
                status=t[3],
                priority=t[4],
                scheduled_date=str(t[5]) if t[5] else None,
                completed_date=str(t[6]) if t[6] else None,
                created_at=str(t[7]),
                updated_at=str(t[8])
            )
            for t in tasks
        ],
        total=len(tasks)
    )
