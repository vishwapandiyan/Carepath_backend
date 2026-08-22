"""
Care Plan Service

Abstracts care plan and task management business logic.

This service layer handles:
- Care plan creation and retrieval
- Task management within care plans
- Task status lifecycle

Uses MRN (Medical Record Number) as the application-level patient identifier.

Currently uses a simple in-memory store for development.

Later phases:
- Replace in-memory store with PostgreSQL via a repository layer
- Add caching if needed
- Add audit logging

Architecture:
services/care_plan_service.py
    ↓
_care_plans_store (in-memory)
_tasks_store (in-memory)
_patient_care_plans (in-memory index, keyed by MRN)

Later:
services/care_plan_service.py
    ↓
database/repositories.py
    ↓
PostgreSQL
"""

import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime


# ============================================================================
# TEMPORARY IN-MEMORY STORES
# ============================================================================

# Store for care plans: {care_plan_id: care_plan_dict}
_care_plans_store: Dict[str, Dict[str, Any]] = {}

# Store for tasks: {task_id: task_dict}
_tasks_store: Dict[str, Dict[str, Any]] = {}

# Index for patient (MRN) -> care_plan_id (for quick lookup of patient's active plan)
# Keyed by MRN (application-level identifier)
_patient_care_plans: Dict[str, str] = {}


# ============================================================================
# FUNCTION 1: Create Care Plan
# ============================================================================

def create_care_plan(
    mrn: str,
    risk_level: str,
    intensity: str
) -> Dict[str, Any]:
    """
    Create a new active care plan.
    
    Generates a unique care_plan_id and stores the plan in the service.
    Uses MRN as the application-level patient identifier.
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier, e.g., "MRN001")
        risk_level: One of "HIGH", "MODERATE", "LOW"
        intensity: One of "INTENSIVE", "REGULAR", "BASIC"
    
    Returns:
        Created care plan dictionary with:
        - care_plan_id: Generated UUID
        - mrn: The Medical Record Number
        - risk_level: Risk classification
        - intensity: Post-care intensity
        - status: "ACTIVE"
        - created_at: ISO timestamp
        - tasks: Empty list (tasks added separately)
    
    Raises:
        ValueError: If risk_level or intensity are invalid
    """
    # Validate inputs
    valid_risk_levels = {"HIGH", "MODERATE", "LOW"}
    valid_intensities = {"INTENSIVE", "REGULAR", "BASIC"}
    
    if risk_level not in valid_risk_levels:
        raise ValueError(
            f"Invalid risk_level: '{risk_level}'. "
            f"Must be one of: {', '.join(valid_risk_levels)}"
        )
    
    if intensity not in valid_intensities:
        raise ValueError(
            f"Invalid intensity: '{intensity}'. "
            f"Must be one of: {', '.join(valid_intensities)}"
        )
    
    # Generate unique care plan ID
    care_plan_id = f"CP-{uuid.uuid4().hex[:8].upper()}"
    
    # Create care plan
    care_plan = {
        "care_plan_id": care_plan_id,
        "mrn": mrn,
        "risk_level": risk_level,
        "intensity": intensity,
        "status": "ACTIVE",
        "created_at": datetime.utcnow().isoformat(),
        "tasks": []
    }
    
    # Store in memory
    _care_plans_store[care_plan_id] = care_plan
    _patient_care_plans[mrn] = care_plan_id
    
    return care_plan


# ============================================================================
# FUNCTION 2: Get Existing Care Plan
# ============================================================================

def get_existing_care_plan(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Find the patient's active care plan.
    
    Searches for an ACTIVE care plan associated with the MRN.
    Uses MRN as the application-level patient identifier.
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier)
    
    Returns:
        Care plan dictionary if ACTIVE plan exists for patient, None otherwise
    """
    if mrn not in _patient_care_plans:
        return None
    
    care_plan_id = _patient_care_plans[mrn]
    care_plan = _care_plans_store.get(care_plan_id)
    
    if not care_plan:
        return None
    
    # Only return if status is ACTIVE
    if care_plan.get("status") == "ACTIVE":
        return care_plan
    
    return None


# ============================================================================
# FUNCTION 3: Update Care Plan
# ============================================================================

def update_care_plan(care_plan_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing care plan.
    
    Applies updates to a care plan identified by care_plan_id.
    
    Args:
        care_plan_id: Unique care plan identifier
        updates: Dictionary of fields to update
                 (e.g., {"status": "COMPLETED", "intensity": "REGULAR"})
    
    Returns:
        Updated care plan dictionary
    
    Raises:
        ValueError: If care plan does not exist
    """
    if care_plan_id not in _care_plans_store:
        raise ValueError(
            f"Care plan '{care_plan_id}' not found."
        )
    
    care_plan = _care_plans_store[care_plan_id]
    
    # Apply updates
    care_plan.update(updates)
    
    # Record update timestamp if not already in updates
    if "updated_at" not in updates:
        care_plan["updated_at"] = datetime.utcnow().isoformat()
    
    return care_plan


# ============================================================================
# FUNCTION 4: Create Task
# ============================================================================

def create_task(care_plan_id: str, task_type: str) -> Dict[str, Any]:
    """
    Create a task under an existing care plan.
    
    Generates a unique task_id and associates it with the care plan.
    
    Args:
        care_plan_id: Unique care plan identifier
        task_type: Type of task (e.g., "EARLY_CHECKIN", "FOLLOW_UP_APPOINTMENT")
    
    Returns:
        Created task dictionary with:
        - task_id: Generated UUID
        - care_plan_id: Reference to parent care plan
        - task_type: Type of task
        - status: "PENDING"
        - created_at: ISO timestamp
    
    Raises:
        ValueError: If care plan does not exist
    """
    if care_plan_id not in _care_plans_store:
        raise ValueError(
            f"Care plan '{care_plan_id}' not found. Cannot create task."
        )
    
    # Generate unique task ID
    task_id = f"T-{uuid.uuid4().hex[:8].upper()}"
    
    # Create task
    task = {
        "task_id": task_id,
        "care_plan_id": care_plan_id,
        "task_type": task_type,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Store task in memory
    _tasks_store[task_id] = task
    
    # Add task ID to care plan's task list
    care_plan = _care_plans_store[care_plan_id]
    care_plan["tasks"].append(task_id)
    
    return task


# ============================================================================
# FUNCTION 5: Get Next Task
# ============================================================================

def get_next_task(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Find the first PENDING task in the patient's active care plan.
    
    Searches for the patient's ACTIVE care plan using MRN, then returns the first
    PENDING task in that plan's task list.
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier)
    
    Returns:
        First PENDING task dictionary if found, None otherwise
    """
    # Get patient's active care plan
    if mrn not in _patient_care_plans:
        return None
    
    care_plan_id = _patient_care_plans[mrn]
    care_plan = _care_plans_store.get(care_plan_id)
    
    # Verify care plan exists and is ACTIVE
    if not care_plan or care_plan.get("status") != "ACTIVE":
        return None
    
    # Find first PENDING task in the care plan's task list
    for task_id in care_plan.get("tasks", []):
        task = _tasks_store.get(task_id)
        if task and task.get("status") == "PENDING":
            return task
    
    return None


# ============================================================================
# FUNCTION 6: Update Task Status
# ============================================================================

def update_task_status(task_id: str, status: str) -> Dict[str, Any]:
    """
    Update a task's status.
    
    Applies a new status to a task. Only valid statuses are accepted.
    
    Args:
        task_id: Unique task identifier
        status: New status (one of: PENDING, IN_PROGRESS, COMPLETED, MISSED, CANCELLED)
    
    Returns:
        Updated task dictionary
    
    Raises:
        ValueError: If task not found or status is invalid
    """
    valid_statuses = {"PENDING", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"}
    
    # Validate status
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Find task
    if task_id not in _tasks_store:
        raise ValueError(
            f"Task '{task_id}' not found."
        )
    
    # Update task
    task = _tasks_store[task_id]
    task["status"] = status
    task["updated_at"] = datetime.utcnow().isoformat()
    
    return task


# ============================================================================
# UTILITY: Clear stores (for testing only)
# ============================================================================

def _clear_stores() -> None:
    """
    Clear all in-memory stores.
    
    Used for testing and resetting state between test runs.
    Do NOT call in production.
    """
    global _care_plans_store, _tasks_store, _patient_care_plans
    _care_plans_store.clear()
    _tasks_store.clear()
    _patient_care_plans.clear()


# ============================================================================
# UTILITY: Get store statistics (for debugging/testing)
# ============================================================================

def _get_store_stats() -> Dict[str, int]:
    """
    Get current in-memory store statistics.
    
    Returns:
        Dictionary with counts of stored items
    """
    return {
        "care_plans": len(_care_plans_store),
        "tasks": len(_tasks_store),
        "patient_plans": len(_patient_care_plans)
    }
