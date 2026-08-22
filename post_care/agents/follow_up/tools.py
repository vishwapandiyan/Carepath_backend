"""
Follow-Up Agent Tools

Database-backed tools for the Follow-Up Agent.

The Follow-Up Agent receives an EXISTING ACTIVE care plan and executes/monitors its tasks.
It does NOT create care plans and does NOT perform risk classification.

Tools in this module:
1. get_active_care_plan() - Retrieve ACTIVE care plan by MRN
2. get_plan_tasks() - Retrieve all tasks for a care plan
3. get_pending_tasks() - Retrieve only PENDING/IN_PROGRESS tasks
4. get_task() - Retrieve single task
5. update_task_status() - Update task status
6. create_checkin() - Create a new check-in record
7. get_checkin() - Retrieve single check-in
8. record_patient_response() - Record patient response to check-in
9. update_checkin_status() - Update check-in status
10. get_task_checkins() - Retrieve all check-ins for a task

All operations use PostgreSQL as source of truth.
No in-memory storage.
"""

import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from post_care.database.connection import get_db_connection, close_db_connection
from post_care.database.repositories import CarePlanRepository, CarePlanTaskRepository

logger = logging.getLogger(__name__)


# ============================================================================
# REPOSITORY: Follow-Up Check-In Operations (PostgreSQL)
# ============================================================================

class FollowUpCheckInRepository:
    """Repository for check-in persistence in PostgreSQL."""
    
    @staticmethod
    def create_checkin(
        task_id: str,
        checkin_type: str,
        scheduled_at: Optional[datetime] = None,
        channel: Optional[str] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new check-in record in PostgreSQL.
        
        Args:
            task_id: Parent task ID
            checkin_type: Type of check-in
            scheduled_at: When check-in is scheduled
            channel: Communication channel (sms, email, push, phone)
            message: Message content
        
        Returns:
            Dictionary with created check-in data
        
        Raises:
            ValueError: If task not found or insertion fails
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Verify task exists and get care_plan_id
            cursor.execute(
                "SELECT id, care_plan_id FROM care_plan_tasks WHERE id = %s",
                (task_id,)
            )
            
            task_result = cursor.fetchone()
            if not task_result:
                raise ValueError(f"Task {task_id} not found")
            
            care_plan_id = task_result[1]
            
            # Generate unique check-in ID
            checkin_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
            
            # Insert check-in
            cursor.execute(
                """
                INSERT INTO follow_up_checkins 
                (id, care_plan_id, task_id, checkin_type, scheduled_at, status, checkin_message, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, task_id, checkin_type, scheduled_at, status, checkin_message, created_at
                """,
                (checkin_id, care_plan_id, task_id, checkin_type, scheduled_at, "SCHEDULED", message)
            )
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "checkin_id": result[0],
                "task_id": result[1],
                "checkin_type": result[2],
                "scheduled_at": result[3].isoformat() if result[3] else None,
                "channel": "notification",  # Default channel
                "status": result[4],
                "message": result[5],
                "response": None,
                "response_received_at": None,
                "created_at": result[6].isoformat() if result[6] else None
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to create check-in: {str(e)}")
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_checkin_by_id(checkin_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a check-in by ID.
        
        Args:
            checkin_id: Check-in identifier
        
        Returns:
            Check-in dictionary if exists, None otherwise
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, task_id, checkin_type, scheduled_at, status, checkin_message, patient_response, response_received_at, created_at, updated_at
                FROM follow_up_checkins
                WHERE id = %s
                """,
                (checkin_id,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            return {
                "checkin_id": result[0],
                "task_id": result[1],
                "checkin_type": result[2],
                "scheduled_at": result[3].isoformat() if result[3] else None,
                "channel": "notification",  # Default channel
                "status": result[4],
                "message": result[5],
                "response": result[6],
                "response_received_at": result[7].isoformat() if result[7] else None,
                "created_at": result[8].isoformat() if result[8] else None,
                "updated_at": result[9].isoformat() if result[9] else None
            }
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_checkins_by_task(task_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all check-ins for a task, ordered chronologically.
        
        Args:
            task_id: Task identifier
        
        Returns:
            List of check-in dictionaries
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, task_id, checkin_type, scheduled_at, status, checkin_message, patient_response, response_received_at, created_at, updated_at
                FROM follow_up_checkins
                WHERE task_id = %s
                ORDER BY created_at ASC
                """,
                (task_id,)
            )
            
            results = cursor.fetchall()
            
            checkins = []
            for result in results:
                checkins.append({
                    "checkin_id": result[0],
                    "task_id": result[1],
                    "checkin_type": result[2],
                    "scheduled_at": result[3].isoformat() if result[3] else None,
                    "channel": "notification",  # Default channel
                    "status": result[4],
                    "message": result[5],
                    "response": result[6],
                    "response_received_at": result[7].isoformat() if result[7] else None,
                    "created_at": result[8].isoformat() if result[8] else None,
                    "updated_at": result[9].isoformat() if result[9] else None
                })
            
            return checkins
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def update_checkin(
        checkin_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update check-in fields.
        
        Args:
            checkin_id: Check-in identifier
            updates: Dictionary of fields to update
        
        Returns:
            Updated check-in dictionary
        
        Raises:
            ValueError: If check-in not found
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Build dynamic UPDATE query
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            
            values = list(updates.values()) + [checkin_id]
            
            cursor.execute(
                f"""
                UPDATE follow_up_checkins
                SET {set_clause}
                WHERE checkin_id = %s
                RETURNING checkin_id, task_id, checkin_type, scheduled_at, channel, status, message, response, response_received_at, created_at, updated_at
                """,
                values
            )
            
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Check-in {checkin_id} not found")
            
            conn.commit()
            
            return {
                "checkin_id": result[0],
                "care_plan_id": result[1],
                "task_id": result[2],
                "checkin_type": result[3],
                "scheduled_at": result[4].isoformat() if result[4] else None,
                "channel": None,  # Not in new schema
                "status": result[5],
                "message": result[6],
                "response": result[7],
                "response_received_at": result[8].isoformat() if result[8] else None,
                "created_at": result[9].isoformat() if result[9] else None,
                "updated_at": result[10].isoformat() if result[10] else None
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to update check-in: {str(e)}")
        
        finally:
            close_db_connection(conn)


# ============================================================================
# TOOL 1: GET ACTIVE CARE PLAN
# ============================================================================

def get_active_care_plan(mrn: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the patient's ACTIVE care plan from PostgreSQL.
    
    Args:
        mrn: Medical Record Number
    
    Returns:
        Care plan with tasks if ACTIVE plan exists, None otherwise
    
    Raises:
        ValueError: If MRN is empty
    """
    if not mrn or not mrn.strip():
        raise ValueError("MRN cannot be empty")
    
    care_plan = CarePlanRepository.get_active_care_plan_by_mrn(mrn)
    
    if not care_plan:
        return None
    
    # Fetch associated tasks
    tasks = CarePlanTaskRepository.get_tasks_by_care_plan(care_plan["care_plan_id"])
    care_plan["tasks"] = tasks
    
    return care_plan


def get_active_care_plan_by_id(care_plan_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an ACTIVE care plan by its ID from PostgreSQL.
    
    Args:
        care_plan_id: Care plan identifier
    
    Returns:
        Care plan with tasks if found and ACTIVE, None otherwise
    
    Raises:
        ValueError: If care_plan_id is empty
    """
    if not care_plan_id or not care_plan_id.strip():
        raise ValueError("care_plan_id cannot be empty")
    
    care_plan = CarePlanRepository.get_care_plan_by_id(care_plan_id)
    
    if not care_plan or care_plan.get("status") != "ACTIVE":
        return None
    
    # Fetch associated tasks
    tasks = CarePlanTaskRepository.get_tasks_by_care_plan(care_plan_id)
    care_plan["tasks"] = tasks
    
    return care_plan


# ============================================================================
# TOOL 2: GET PLAN TASKS
# ============================================================================

def get_plan_tasks(care_plan_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve ALL tasks belonging to the care plan from PostgreSQL.
    
    Args:
        care_plan_id: Care plan identifier
    
    Returns:
        List of task dictionaries with all fields
    
    Raises:
        ValueError: If care plan not found or invalid
    """
    if not care_plan_id or not care_plan_id.strip():
        raise ValueError("care_plan_id cannot be empty")
    
    # Verify care plan exists
    care_plan = CarePlanRepository.get_care_plan_by_id(care_plan_id)
    if not care_plan:
        raise ValueError(f"Care plan {care_plan_id} not found")
    
    tasks = CarePlanTaskRepository.get_tasks_by_care_plan(care_plan_id)
    return tasks


# ============================================================================
# TOOL 3: GET PENDING TASKS
# ============================================================================

def get_pending_tasks(care_plan_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve only tasks with PENDING or IN_PROGRESS status.
    
    Args:
        care_plan_id: Care plan identifier
    
    Returns:
        List of pending task dictionaries
    
    Raises:
        ValueError: If care plan not found
    """
    if not care_plan_id or not care_plan_id.strip():
        raise ValueError("care_plan_id cannot be empty")
    
    # Verify care plan exists
    care_plan = CarePlanRepository.get_care_plan_by_id(care_plan_id)
    if not care_plan:
        raise ValueError(f"Care plan {care_plan_id} not found")
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id, care_plan_id, task_type, status, task_description, doctor_instruction, created_at, updated_at
            FROM care_plan_tasks
            WHERE care_plan_id = %s AND status IN ('PENDING', 'IN_PROGRESS')
            ORDER BY created_at ASC
            """,
            (care_plan_id,)
        )
        
        results = cursor.fetchall()
        
        tasks = []
        for result in results:
            tasks.append({
                "task_id": result[0],
                "care_plan_id": result[1],
                "task_type": result[2],
                "status": result[3],
                "task_description": result[4],  # Use consistent field name
                "doctor_instruction": result[5],
                "created_at": result[6].isoformat() if result[6] else None,
                "updated_at": result[7].isoformat() if result[7] else None
            })
        
        return tasks
    
    finally:
        close_db_connection(conn)


# ============================================================================
# TOOL 4: GET TASK
# ============================================================================

def get_task(task_id: str) -> Dict[str, Any]:
    """
    Retrieve one task from PostgreSQL.
    
    Args:
        task_id: Task identifier
    
    Returns:
        Task dictionary with all fields
    
    Raises:
        ValueError: If task not found
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id cannot be empty")
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id, care_plan_id, task_type, status, task_description, doctor_instruction, created_at, updated_at
            FROM care_plan_tasks
            WHERE id = %s
            """,
            (task_id,)
        )
        
        result = cursor.fetchone()
        
        if not result:
            raise ValueError(f"Task {task_id} not found")
        
        return {
            "task_id": result[0],
            "care_plan_id": result[1],
            "task_type": result[2],
            "status": result[3],
            "task_description": result[4],  # Use consistent field name
            "doctor_instruction": result[5],
            "created_at": result[6].isoformat() if result[6] else None,
            "updated_at": result[7].isoformat() if result[7] else None
        }
    
    finally:
        close_db_connection(conn)


# ============================================================================
# TOOL 5: UPDATE TASK STATUS
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
        ValueError: If task not found or invalid status
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id cannot be empty")
    
    if not status or not status.strip():
        raise ValueError("status cannot be empty")
    
    valid_statuses = ["PENDING", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
    
    return CarePlanTaskRepository.update_task(task_id, {"status": status})


# ============================================================================
# TOOL 6: CREATE CHECK-IN
# ============================================================================

def create_checkin(
    task_id: str,
    checkin_type: str,
    scheduled_at: Optional[datetime] = None,
    channel: Optional[str] = None,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a persistent check-in record in PostgreSQL.
    
    Args:
        task_id: Parent task ID
        checkin_type: Type of check-in (e.g., 'appointment_reminder', 'symptom_check')
        scheduled_at: When check-in is scheduled (optional)
        channel: Communication channel (optional, e.g., 'sms', 'email', 'push', 'phone')
        message: Message content (optional)
    
    Returns:
        Created check-in dictionary
    
    Raises:
        ValueError: If task not found or insertion fails
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id cannot be empty")
    
    if not checkin_type or not checkin_type.strip():
        raise ValueError("checkin_type cannot be empty")
    
    return FollowUpCheckInRepository.create_checkin(
        task_id=task_id,
        checkin_type=checkin_type,
        scheduled_at=scheduled_at,
        channel=channel,
        message=message
    )


# ============================================================================
# TOOL 7: GET CHECK-IN
# ============================================================================

def get_checkin(checkin_id: str) -> Dict[str, Any]:
    """
    Retrieve a check-in from PostgreSQL.
    
    Args:
        checkin_id: Check-in identifier
    
    Returns:
        Check-in dictionary with all fields
    
    Raises:
        ValueError: If check-in not found
    """
    if not checkin_id or not checkin_id.strip():
        raise ValueError("checkin_id cannot be empty")
    
    checkin = FollowUpCheckInRepository.get_checkin_by_id(checkin_id)
    
    if not checkin:
        raise ValueError(f"Check-in {checkin_id} not found")
    
    return checkin


# ============================================================================
# TOOL 8: RECORD PATIENT RESPONSE
# ============================================================================

def record_patient_response(checkin_id: str, response: str) -> Dict[str, Any]:
    """
    Record patient response to a check-in.
    
    Updates:
    - patient_response field with patient's response
    - response_received_at with current timestamp
    - status to RESPONDED
    
    Args:
        checkin_id: Check-in identifier
        response: Patient's response text
    
    Returns:
        Updated check-in dictionary
    
    Raises:
        ValueError: If check-in not found or response empty
    """
    if not checkin_id or not checkin_id.strip():
        raise ValueError("checkin_id cannot be empty")
    
    if not response or not response.strip():
        raise ValueError("response cannot be empty")
    
    return FollowUpCheckInRepository.update_checkin(
        checkin_id,
        {
            "patient_response": response,
            "response_received_at": datetime.now(),
            "status": "RESPONDED"
        }
    )


# ============================================================================
# TOOL 9: UPDATE CHECK-IN STATUS
# ============================================================================

def update_checkin_status(checkin_id: str, status: str) -> Dict[str, Any]:
    """
    Update check-in status in PostgreSQL.
    
    Args:
        checkin_id: Check-in identifier
        status: New status (SCHEDULED, SENT, RESPONDED, COMPLETED, SKIPPED, CANCELLED)
    
    Returns:
        Updated check-in dictionary
    
    Raises:
        ValueError: If check-in not found or invalid status
    """
    if not checkin_id or not checkin_id.strip():
        raise ValueError("checkin_id cannot be empty")
    
    if not status or not status.strip():
        raise ValueError("status cannot be empty")
    
    valid_statuses = ["SCHEDULED", "SENT", "RESPONDED", "COMPLETED", "SKIPPED", "CANCELLED"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
    
    return FollowUpCheckInRepository.update_checkin(checkin_id, {"status": status})


# ============================================================================
# TOOL 10: GET CHECK-INS FOR TASK
# ============================================================================

def get_task_checkins(task_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all check-ins for a task, ordered chronologically.
    
    Args:
        task_id: Task identifier
    
    Returns:
        List of check-in dictionaries with historical/current status
    
    Raises:
        ValueError: If task not found or invalid
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id cannot be empty")
    
    # Verify task exists
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT task_id FROM care_plan_tasks WHERE task_id = %s",
            (task_id,)
        )
        
        if not cursor.fetchone():
            raise ValueError(f"Task {task_id} not found")
    
    finally:
        close_db_connection(conn)
    
    return FollowUpCheckInRepository.get_checkins_by_task(task_id)
