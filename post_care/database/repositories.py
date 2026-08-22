"""
Care Plan Repository Layer

Provides PostgreSQL persistence for care plans and tasks.

This layer:
- Replaces the in-memory _care_plans_store and _tasks_store
- Implements ACID transactions for atomicity
- Ensures one ACTIVE plan per patient via database constraints
- Provides methods for creating, retrieving, and updating care plans/tasks

Architecture:
    Care Plan Service
        ↓
    Repository Layer (this module)
        ↓
    PostgreSQL
"""

import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from post_care.database.connection import get_db_connection, close_db_connection
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# REPOSITORY: Care Plan Operations
# ============================================================================

class CarePlanRepository:
    """Repository for care plan persistence in PostgreSQL."""
    
    @staticmethod
    def create_care_plan(
        mrn: str,
        patient_id: int,
        risk_level: str,
        intensity: str,
        doctor_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new active care plan in PostgreSQL.
        
        Args:
            mrn: Medical Record Number
            patient_id: Patient ID from patient_ehr
            risk_level: "LOW", "MODERATE", or "HIGH"
            intensity: "BASIC", "REGULAR", or "INTENSIVE"
            doctor_instructions: Optional extracted doctor instructions
        
        Returns:
            Dictionary with created care plan data
        
        Raises:
            ValueError: If patient already has ACTIVE plan or validation fails
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if patient already has an ACTIVE plan
            cursor.execute(
                """
                SELECT id FROM care_plans 
                WHERE patient_id = %s AND status = 'ACTIVE'
                """,
                (patient_id,)
            )
            
            existing = cursor.fetchone()
            if existing:
                raise ValueError(
                    f"Patient {patient_id} already has an ACTIVE care plan: {existing[0]}"
                )
            
            # Generate unique care_plan_id
            care_plan_id = f"CP-{uuid.uuid4().hex[:8].upper()}"
            
            # Insert care plan
            cursor.execute(
                """
                INSERT INTO care_plans 
                (id, patient_id, mrn, risk_level, intensity, status, doctor_instructions, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, patient_id, mrn, risk_level, intensity, status, doctor_instructions, created_at
                """,
                (care_plan_id, patient_id, mrn, risk_level, intensity, "ACTIVE", doctor_instructions)
            )
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "care_plan_id": result[0],
                "patient_id": result[1],
                "mrn": result[2],
                "risk_level": result[3],
                "intensity": result[4],
                "status": result[5],
                "doctor_instructions": result[6],
                "created_at": result[7].isoformat() if result[7] else None,
                "tasks": []
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to create care plan: {str(e)}")
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_active_care_plan_by_mrn(mrn: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve ACTIVE care plan for a patient by MRN.
        
        Args:
            mrn: Medical Record Number
        
        Returns:
            Care plan dictionary if exists, None otherwise
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT care_plan_id, patient_id, mrn, risk_level, intensity, status, doctor_instructions, created_at
                FROM care_plans
                WHERE mrn = %s AND status = 'ACTIVE'
                """,
                (mrn,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            return {
                "care_plan_id": result[0],
                "patient_id": result[1],
                "mrn": result[2],
                "risk_level": result[3],
                "intensity": result[4],
                "status": result[5],
                "doctor_instructions": result[6],
                "created_at": result[7].isoformat() if result[7] else None,
                "tasks": []  # Tasks fetched separately
            }
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_care_plan_by_id(care_plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve care plan by ID.
        
        Args:
            care_plan_id: Care plan identifier
        
        Returns:
            Care plan dictionary if exists, None otherwise
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT care_plan_id, patient_id, mrn, risk_level, intensity, status, doctor_instructions, created_at
                FROM care_plans
                WHERE care_plan_id = %s
                """,
                (care_plan_id,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            return {
                "care_plan_id": result[0],
                "patient_id": result[1],
                "mrn": result[2],
                "risk_level": result[3],
                "intensity": result[4],
                "status": result[5],
                "doctor_instructions": result[6],
                "created_at": result[7].isoformat() if result[7] else None,
                "tasks": []
            }
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def update_care_plan(care_plan_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update care plan fields.
        
        Args:
            care_plan_id: Care plan identifier
            updates: Dictionary of fields to update
        
        Returns:
            Updated care plan dictionary
        
        Raises:
            ValueError: If care plan not found
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Build dynamic UPDATE query
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            
            values = list(updates.values()) + [care_plan_id]
            
            cursor.execute(
                f"""
                UPDATE care_plans
                SET {set_clause}
                WHERE care_plan_id = %s
                RETURNING care_plan_id, patient_id, mrn, risk_level, intensity, status, doctor_instructions, created_at, updated_at
                """,
                values
            )
            
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Care plan {care_plan_id} not found")
            
            conn.commit()
            
            return {
                "care_plan_id": result[0],
                "patient_id": result[1],
                "mrn": result[2],
                "risk_level": result[3],
                "intensity": result[4],
                "status": result[5],
                "doctor_instructions": result[6],
                "created_at": result[7].isoformat() if result[7] else None,
                "updated_at": result[8].isoformat() if result[8] else None,
                "tasks": []
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to update care plan: {str(e)}")
        
        finally:
            close_db_connection(conn)


# ============================================================================
# REPOSITORY: Care Plan Task Operations
# ============================================================================

class CarePlanTaskRepository:
    """Repository for care plan task persistence in PostgreSQL."""
    
    @staticmethod
    def create_task(
        care_plan_id: str,
        task_type: str,
        status: str = "PENDING",
        description: Optional[str] = None,
        doctor_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a task under a care plan.
        
        Args:
            care_plan_id: Parent care plan ID
            task_type: Type of task
            status: Task status (default "PENDING")
            description: Optional task description
            doctor_instruction: Optional extracted doctor instruction for this task
        
        Returns:
            Dictionary with created task data
        
        Raises:
            ValueError: If care plan not found or insertion fails
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Verify care plan exists
            cursor.execute(
                "SELECT care_plan_id FROM care_plans WHERE care_plan_id = %s",
                (care_plan_id,)
            )
            
            if not cursor.fetchone():
                raise ValueError(f"Care plan {care_plan_id} not found")
            
            # Generate unique task ID
            task_id = f"T-{uuid.uuid4().hex[:8].upper()}"
            
            # Insert task
            cursor.execute(
                """
                INSERT INTO care_plan_tasks 
                (task_id, care_plan_id, task_type, status, description, doctor_instruction, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING task_id, care_plan_id, task_type, status, description, doctor_instruction, created_at
                """,
                (task_id, care_plan_id, task_type, status, description, doctor_instruction)
            )
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "task_id": result[0],
                "care_plan_id": result[1],
                "task_type": result[2],
                "status": result[3],
                "description": result[4],
                "doctor_instruction": result[5],
                "created_at": result[6].isoformat() if result[6] else None
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to create task: {str(e)}")
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_tasks_by_care_plan(care_plan_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all tasks for a care plan.
        
        Args:
            care_plan_id: Care plan identifier
        
        Returns:
            List of task dictionaries
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT task_id, care_plan_id, task_type, status, description, doctor_instruction, created_at, updated_at
                FROM care_plan_tasks
                WHERE care_plan_id = %s
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
                    "description": result[4],
                    "doctor_instruction": result[5],
                    "created_at": result[6].isoformat() if result[6] else None,
                    "updated_at": result[7].isoformat() if result[7] else None
                })
            
            return tasks
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def update_task(
        task_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update task fields.
        
        Args:
            task_id: Task identifier
            updates: Dictionary of fields to update
        
        Returns:
            Updated task dictionary
        
        Raises:
            ValueError: If task not found
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Build dynamic UPDATE query
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            
            values = list(updates.values()) + [task_id]
            
            cursor.execute(
                f"""
                UPDATE care_plan_tasks
                SET {set_clause}
                WHERE task_id = %s
                RETURNING task_id, care_plan_id, task_type, status, description, doctor_instruction, created_at, updated_at
                """,
                values
            )
            
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Task {task_id} not found")
            
            conn.commit()
            
            return {
                "task_id": result[0],
                "care_plan_id": result[1],
                "task_type": result[2],
                "status": result[3],
                "description": result[4],
                "doctor_instruction": result[5],
                "created_at": result[6].isoformat() if result[6] else None,
                "updated_at": result[7].isoformat() if result[7] else None
            }
        
        except Exception as e:
            conn.rollback()
            raise ValueError(f"Failed to update task: {str(e)}")
        
        finally:
            close_db_connection(conn)
    
    @staticmethod
    def get_first_pending_task(care_plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Get first PENDING task in care plan.
        
        Args:
            care_plan_id: Care plan identifier
        
        Returns:
            First PENDING task or None
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT task_id, care_plan_id, task_type, status, description, doctor_instruction, created_at, updated_at
                FROM care_plan_tasks
                WHERE care_plan_id = %s AND status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (care_plan_id,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            return {
                "task_id": result[0],
                "care_plan_id": result[1],
                "task_type": result[2],
                "status": result[3],
                "description": result[4],
                "doctor_instruction": result[5],
                "created_at": result[6].isoformat() if result[6] else None,
                "updated_at": result[7].isoformat() if result[7] else None
            }
        
        finally:
            close_db_connection(conn)
