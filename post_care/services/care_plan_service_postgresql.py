"""
Care Plan Service - PostgreSQL Production Version

This is the production version of the Care Plan Service that uses PostgreSQL persistence
instead of in-memory storage.

Architecture:
    Agent
        ↓
    Service (this module)
        ↓
    Repository Layer (database/repositories.py)
        ↓
    PostgreSQL

Key Changes:
- All functions now use PostgreSQL repositories
- No in-memory stores (except for temporary test data)
- Atomic transactions ensure consistency
- One ACTIVE plan per patient enforced via database constraint
- Duplicate tasks prevented by foreign key cascade
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import repository layer
from post_care.database.repositories import CarePlanRepository, CarePlanTaskRepository

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCTION 1: Create Care Plan (PostgreSQL version)
# ============================================================================

def create_care_plan(
    mrn: str,
    patient_id: int,
    risk_level: str,
    intensity: str,
    doctor_instructions: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new active care plan in PostgreSQL.
    
    Generates unique care_plan_id and stores in PostgreSQL.
    
    Args:
        mrn: Medical Record Number
        patient_id: Patient ID from patient_ehr table
        risk_level: One of "HIGH", "MODERATE", "LOW"
        intensity: One of "INTENSIVE", "REGULAR", "BASIC"
        doctor_instructions: Optional extracted doctor instructions
    
    Returns:
        Created care plan dictionary
    
    Raises:
        ValueError: If patient already has ACTIVE plan or validation fails
    """
    return CarePlanRepository.create_care_plan(
        mrn=mrn,
        patient_id=patient_id,
        risk_level=risk_level,
        intensity=intensity,
        doctor_instructions=doctor_instructions
    )


# ============================================================================
# FUNCTION 2: Get Existing Care Plan (PostgreSQL version)
# ============================================================================

def get_existing_care_plan(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Find the patient's active care plan from PostgreSQL.
    
    Uses MRN as lookup key, searches for ACTIVE status.
    
    Args:
        mrn: Medical Record Number
    
    Returns:
        Care plan dictionary if ACTIVE plan exists, None otherwise
    """
    care_plan = CarePlanRepository.get_active_care_plan_by_mrn(mrn)
    
    if not care_plan:
        return None
    
    # Fetch associated tasks
    tasks = CarePlanTaskRepository.get_tasks_by_care_plan(care_plan["care_plan_id"])
    care_plan["tasks"] = [t["task_id"] for t in tasks]  # Store task IDs for compatibility
    
    return care_plan


# ============================================================================
# FUNCTION 3: Update Care Plan (PostgreSQL version)
# ============================================================================

def update_care_plan(care_plan_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update care plan in PostgreSQL.
    
    Args:
        care_plan_id: Care plan identifier
        updates: Dictionary of fields to update
    
    Returns:
        Updated care plan dictionary
    
    Raises:
        ValueError: If care plan not found
    """
    return CarePlanRepository.update_care_plan(care_plan_id, updates)


# ============================================================================
# FUNCTION 4: Create Task (PostgreSQL version)
# ============================================================================

def create_task(
    care_plan_id: str,
    task_type: str,
    description: Optional[str] = None,
    doctor_instruction: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a task under an existing care plan in PostgreSQL.
    
    Generates unique task_id and associates with care plan.
    
    Args:
        care_plan_id: Parent care plan identifier
        task_type: Type of task (e.g., "EARLY_CHECKIN")
        description: Optional task description
        doctor_instruction: Optional extracted doctor instruction
    
    Returns:
        Created task dictionary
    
    Raises:
        ValueError: If care plan not found
    """
    # Provide default description if none given (task_description is NOT NULL in DB)
    if description is None:
        # Use predefined generic descriptions from task_personalization
        from post_care.llm.task_personalization import get_task_description
        description = get_task_description(task_type, None)
    
    return CarePlanTaskRepository.create_task(
        care_plan_id=care_plan_id,
        task_type=task_type,
        status="PENDING",
        description=description,
        doctor_instruction=doctor_instruction
    )


# ============================================================================
# FUNCTION 5: Get Next Task (PostgreSQL version)
# ============================================================================

def get_next_task(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Find the first PENDING task in patient's active care plan from PostgreSQL.
    
    Args:
        mrn: Medical Record Number
    
    Returns:
        First PENDING task if found, None otherwise
    """
    # Get patient's active care plan
    care_plan = CarePlanRepository.get_active_care_plan_by_mrn(mrn)
    
    if not care_plan:
        return None
    
    # Get first PENDING task
    return CarePlanTaskRepository.get_first_pending_task(care_plan["care_plan_id"])


# ============================================================================
# FUNCTION 6: Update Task Status (PostgreSQL version)
# ============================================================================

def update_task_status(task_id: str, status: str) -> Dict[str, Any]:
    """
    Update task status in PostgreSQL.
    
    Args:
        task_id: Task identifier
        status: New status (PENDING, IN_PROGRESS, COMPLETED, MISSED, CANCELLED)
    
    Returns:
        Updated task dictionary
    
    Raises:
        ValueError: If task not found or status invalid
    """
    valid_statuses = {"PENDING", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"}
    
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
    
    return CarePlanTaskRepository.update_task(task_id, {"status": status})


# ============================================================================
# HELPER: Get Plan Tasks (for reuse operations)
# ============================================================================

def get_plan_tasks(care_plan_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all tasks for a care plan from PostgreSQL.
    
    Used when reusing ACTIVE care plan to preserve existing tasks.
    
    Args:
        care_plan_id: Care plan identifier
    
    Returns:
        List of task dictionaries with their current statuses
    
    Raises:
        ValueError: If care plan doesn't exist
    """
    return CarePlanTaskRepository.get_tasks_by_care_plan(care_plan_id)


# ============================================================================
# UTILITY: Database Health Check
# ============================================================================

def check_database_health() -> Dict[str, Any]:
    """
    Check if PostgreSQL connection and tables are working.
    
    Returns:
        Dictionary with health status
    """
    from database.connection import get_db_connection, close_db_connection
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check care_plans table
        cursor.execute("SELECT COUNT(*) FROM care_plans")
        care_plans_count = cursor.fetchone()[0]
        
        # Check care_plan_tasks table
        cursor.execute("SELECT COUNT(*) FROM care_plan_tasks")
        tasks_count = cursor.fetchone()[0]
        
        cursor.close()
        close_db_connection(conn)
        
        return {
            "status": "healthy",
            "database": "PostgreSQL",
            "care_plans_count": care_plans_count,
            "tasks_count": tasks_count
        }
    
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "PostgreSQL",
            "error": str(e)
        }
