"""
Care Plan Agent Tools

Thin wrapper layer for care plan operations.

This module provides tool interfaces for care plan and task management.
All business logic and storage is delegated to the service layer (now PostgreSQL-backed).

Data flow:
agent.py
    ↓
tools.py (this module - thin wrappers)
    ↓
services/care_plan_service_postgresql.py (PostgreSQL service layer)
    ↓
database/repositories.py (PostgreSQL repositories)
    ↓
PostgreSQL
"""

from typing import Dict, Optional, Any, List

# Import patient context retrieval
from post_care.shared_tools.patient.patient_context import get_patient_context


# ============================================================================
# TOOL 1: Get Patient Context
# ============================================================================

def get_patient_context_tool(mrn: str) -> tuple[Dict[str, Any], str]:
    """
    Retrieve patient context from the patient dataset using MRN.
    
    Wrapper around shared patient context service.
    Delegates to: shared_tools.patient.patient_context.get_patient_context()
    
    Uses MRN (Medical Record Number) as the application-level lookup key
    to retrieve patient context from the readmission dataset.
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier, e.g., "MRN001")
    
    Returns:
        Tuple of (patient_context_dict, patient_id):
        - patient_context_dict: Dictionary containing patient demographic and clinical context
        - patient_id: Internal patient identifier from readmission dataset
    
    Raises:
        ValueError: If patient with MRN not found in the dataset
    """
    return get_patient_context(mrn)


# ============================================================================
# TOOL 2: Get Existing Care Plan
# ============================================================================

def get_existing_care_plan(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Check whether the patient already has an active care plan (agent-generated).
    
    Uses PostgreSQL persistence (replaced from in-memory service).
    
    Uses MRN as the lookup key for our post-care system's generated plans
    (separate from EHR discharge instructions).
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier)
    
    Returns:
        Care plan dictionary if ACTIVE plan exists, None otherwise
    """
    # Import here to use PostgreSQL version
    from services.care_plan_service_postgresql import get_existing_care_plan as get_existing_care_plan_pg
    return get_existing_care_plan_pg(mrn)


# ============================================================================
# TOOL 3: Get Care Pathway
# ============================================================================

def get_care_pathway(risk_level: str) -> list[str]:
    """
    Return the predefined post-care pathway based on risk level.
    
    No service delegation needed - pathways are predefined locally.
    
    Args:
        risk_level: One of "HIGH", "MODERATE", "LOW"
    
    Returns:
        List of task types for the pathway
    
    Raises:
        ValueError: If risk_level is invalid
    """
    pathways = {
        "HIGH": [
            "EARLY_CHECKIN",
            "FREQUENT_CHECKINS",
            "FOLLOW_UP_APPOINTMENT",
            "APPOINTMENT_MONITORING",
            "CONCERN_ESCALATION"
        ],
        "MODERATE": [
            "CHECKIN",
            "FOLLOW_UP_APPOINTMENT",
            "APPOINTMENT_REMINDER",
            "RESPONSE_MONITORING"
        ],
        "LOW": [
            "BASIC_CHECKIN",
            "FOLLOW_UP_REMINDER",
            "PATIENT_SUPPORT"
        ]
    }
    
    if risk_level not in pathways:
        raise ValueError(
            f"Invalid risk_level: '{risk_level}'. "
            f"Must be one of: {', '.join(pathways.keys())}"
        )
    
    return pathways[risk_level]


# ============================================================================
# TOOL 4: Create Care Plan
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
    
    Uses PostgreSQL persistence (replaced from in-memory service).
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier)
        patient_id: Patient ID from patient_ehr table
        risk_level: One of "HIGH", "MODERATE", "LOW"
        intensity: One of "INTENSIVE", "REGULAR", "BASIC"
        doctor_instructions: Optional extracted doctor instructions
    
    Returns:
        Created care plan dictionary
    
    Raises:
        ValueError: If patient already has ACTIVE plan or validation fails
    """
    from services.care_plan_service_postgresql import create_care_plan as create_care_plan_pg
    return create_care_plan_pg(mrn, patient_id, risk_level, intensity, doctor_instructions)


# ============================================================================
# TOOL 5: Update Care Plan
# ============================================================================

def update_care_plan(care_plan_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing care plan.
    
    Wrapper around service layer.
    Delegates to: services.care_plan_service.update_care_plan()
    
    Args:
        care_plan_id: Unique care plan identifier
        updates: Dictionary of fields to update
    
    Returns:
        Updated care plan dictionary
    
    Raises:
        ValueError: If care plan does not exist
    """
    return service_update_care_plan(care_plan_id, updates)


# ============================================================================
# TOOL 6: Create Task
# ============================================================================

def create_task(
    care_plan_id: str,
    task_type: str,
    description: Optional[str] = None,
    doctor_instruction: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a task under an existing care plan in PostgreSQL.
    
    Uses PostgreSQL persistence (replaced from in-memory service).
    
    Args:
        care_plan_id: Unique care plan identifier
        task_type: Type of task (e.g., "EARLY_CHECKIN")
        description: Optional personalized description
        doctor_instruction: Optional extracted doctor instruction
    
    Returns:
        Created task dictionary with task_id, status=PENDING, etc.
    
    Raises:
        ValueError: If care plan does not exist
    """
    from services.care_plan_service_postgresql import create_task as create_task_pg
    return create_task_pg(care_plan_id, task_type, description, doctor_instruction)


# ============================================================================
# TOOL 7: Get Next Task
# ============================================================================

def get_next_task(patient_id: str) -> Optional[Dict[str, Any]]:
    """
    Find the next PENDING task for the patient's active care plan.
    
    Wrapper around service layer.
    Delegates to: services.care_plan_service.get_next_task()
    
    Args:
        patient_id: Unique patient identifier
    
    Returns:
        First PENDING task dictionary if found, None otherwise
    """
    return service_get_next_task(patient_id)


# ============================================================================
# TOOL 8: Update Task Status
# ============================================================================

def update_task_status(task_id: str, status: str) -> Dict[str, Any]:
    """
    Update a task's status.
    
    Wrapper around service layer.
    Delegates to: services.care_plan_service.update_task_status()
    
    Args:
        task_id: Unique task identifier
        status: New status (one of: PENDING, IN_PROGRESS, COMPLETED, MISSED, CANCELLED)
    
    Returns:
        Updated task dictionary
    
    Raises:
        ValueError: If task not found or status is invalid
    """
    return service_update_task_status(task_id, status)


# ============================================================================
# TOOL 9: Get Existing Plan Tasks
# ============================================================================

def get_plan_tasks(care_plan_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all tasks for an existing care plan from PostgreSQL.
    
    Uses PostgreSQL persistence (replaced from in-memory service).
    
    Used when reusing an ACTIVE care plan to preserve existing tasks.
    
    Args:
        care_plan_id: Unique care plan identifier
    
    Returns:
        List of task dictionaries with their current statuses
    
    Raises:
        ValueError: If care plan does not exist
    """
    from services.care_plan_service_postgresql import get_plan_tasks as get_plan_tasks_pg
    return get_plan_tasks_pg(care_plan_id)

