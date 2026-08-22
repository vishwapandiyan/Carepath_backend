"""
Follow-Up Agent Orchestration

Main agent logic for managing patient follow-up within existing care plans.

Architecture:
    Receives: FollowUpInput (existing ACTIVE care plan)
        ↓
    Orchestration Layer (this module)
        ├─ Verify active care plan
        ├─ Get current tasks from PostgreSQL
        ├─ Find actionable/pending task
        ├─ Determine next follow-up action
        ├─ Create/retrieve check-in when appropriate
        ├─ Record responses without interpretation
        └─ Return FollowUpOutput with next_action
        ↓
    Tools Layer (post_care/agents/follow_up/tools.py)
        ↓
    PostgreSQL (source of truth)

Responsibilities:
    ✅ Orchestrate existing care plan follow-up
    ✅ Manage task state retrieval and updates
    ✅ Coordinate check-in creation and tracking
    ✅ Handle patient responses (pass-through, no interpretation)
    ✅ Determine next orchestration step

Does NOT:
    ❌ Create care plans (Care Plan Agent)
    ❌ Classify risk (Care Plan Agent)
    ❌ Generate new tasks (Care Plan Agent)
    ❌ Call Groq (Care Plan Agent)
    ❌ Interpret symptoms (Response Analyzer)
    ❌ Make escalation decisions (Safety Controller)
    ❌ Send Telegram messages (Telegram service)
    ❌ Perform medical diagnosis (doctors)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from post_care.agents.follow_up.schemas import FollowUpInput, FollowUpOutput
from post_care.agents.follow_up import tools

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN ORCHESTRATION FUNCTION
# ============================================================================

def orchestrate_follow_up(follow_up_input: FollowUpInput) -> FollowUpOutput:
    """
    Main orchestration function for the Follow-Up Agent.
    
    Flow:
        1. Verify ACTIVE care plan exists
        2. Retrieve current tasks from PostgreSQL
        3. Find next actionable task
        4. Manage check-ins
        5. Determine next action
        6. Return result
    
    Args:
        follow_up_input: FollowUpInput containing MRN, care_plan_id, tasks, etc.
    
    Returns:
        FollowUpOutput with next_action and follow-up details
    
    Does NOT:
        - Create new care plans
        - Classify risk
        - Generate new tasks
        - Call Groq
        - Perform medical interpretation
        - Make escalation decisions
    """
    mrn = follow_up_input.mrn
    care_plan_id = follow_up_input.care_plan_id
    risk_level = follow_up_input.risk_level
    intensity = follow_up_input.intensity
    
    try:
        # ====================================================================
        # STEP 1: VERIFY ACTIVE CARE PLAN
        # ====================================================================
        
        care_plan = tools.get_active_care_plan(mrn)
        
        if care_plan is None:
            logger.warning(
                f"No ACTIVE care plan found for MRN: {mrn}. "
                f"Expected care_plan_id: {care_plan_id}"
            )
            return FollowUpOutput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                follow_up=None,
                next_action="NO_PENDING_TASKS",
                error=f"No ACTIVE care plan found for patient {mrn}"
            )
        
        # Verify the returned care plan matches the supplied care_plan_id
        if care_plan['care_plan_id'] != care_plan_id:
            logger.error(
                f"Care plan ID mismatch for MRN {mrn}: "
                f"input={care_plan_id}, found={care_plan['care_plan_id']}"
            )
            return FollowUpOutput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                follow_up=None,
                next_action="NO_PENDING_TASKS",
                error=f"Care plan ID mismatch: input {care_plan_id} != found {care_plan['care_plan_id']}"
            )
        
        logger.info(
            f"ACTIVE care plan verified for {mrn}: {care_plan_id} "
            f"({risk_level}/{intensity})"
        )
        
        # ====================================================================
        # STEP 2: GET CURRENT TASKS
        # ====================================================================
        
        # Retrieve current tasks from PostgreSQL (authoritative)
        all_tasks = tools.get_plan_tasks(care_plan_id)
        
        if not all_tasks:
            logger.warning(
                f"No tasks found for care plan {care_plan_id}. "
                "This should not happen for an active plan."
            )
            return FollowUpOutput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                follow_up=None,
                next_action="NO_PENDING_TASKS",
                error=f"No tasks found for care plan {care_plan_id}"
            )
        
        logger.debug(f"Retrieved {len(all_tasks)} tasks from PostgreSQL")
        
        # ====================================================================
        # STEP 3: DETERMINE NEXT ACTIONABLE TASK
        # ====================================================================
        
        actionable_task = _find_actionable_task(all_tasks)
        
        if actionable_task is None:
            logger.info(f"No actionable tasks for care plan {care_plan_id}")
            return FollowUpOutput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                follow_up={"completed_tasks": len([t for t in all_tasks if t['status'] == 'COMPLETED'])},
                next_action="NO_PENDING_TASKS",
                error=None
            )
        
        logger.info(f"Found actionable task: {actionable_task['task_id']} ({actionable_task['task_type']})")
        
        # ====================================================================
        # STEP 4: DETERMINE FOLLOW-UP ACTION & MANAGE CHECK-INS
        # ====================================================================
        
        follow_up_action_result = _determine_follow_up_action(
            task=actionable_task,
            care_plan_id=care_plan_id,
            risk_level=risk_level,
            intensity=intensity
        )
        
        logger.debug(f"Follow-up action: {follow_up_action_result['next_action']}")
        
        # ====================================================================
        # STEP 5: RETURN ORCHESTRATION RESULT
        # ====================================================================
        
        return FollowUpOutput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            follow_up=follow_up_action_result.get('follow_up_data'),
            next_action=follow_up_action_result['next_action'],
            error=None
        )
    
    except Exception as e:
        logger.error(f"Follow-Up Agent orchestration error: {str(e)}", exc_info=True)
        return FollowUpOutput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            follow_up=None,
            next_action="NO_PENDING_TASKS",
            error=f"Follow-Up Agent error: {str(e)}"
        )


# ============================================================================
# HELPER: FIND ACTIONABLE TASK
# ============================================================================

def _find_actionable_task(tasks: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select the next actionable task according to priority:
        1. IN_PROGRESS (highest priority)
        2. PENDING
    
    Skip:
        - COMPLETED
        - CANCELLED
        - MISSED (do NOT auto-regenerate)
    
    Args:
        tasks: List of task dictionaries from PostgreSQL
    
    Returns:
        Next actionable task or None if no actionable tasks
    """
    # Priority 1: IN_PROGRESS tasks
    for task in tasks:
        if task['status'] == 'IN_PROGRESS':
            return task
    
    # Priority 2: PENDING tasks
    for task in tasks:
        if task['status'] == 'PENDING':
            return task
    
    # No actionable tasks
    return None


# ============================================================================
# HELPER: DETERMINE FOLLOW-UP ACTION
# ============================================================================

def _determine_follow_up_action(
    task: Dict[str, Any],
    care_plan_id: str,
    risk_level: str,
    intensity: str
) -> Dict[str, Any]:
    """
    Determine the next follow-up action based on task type and current state.
    
    Maps task types to follow-up actions deterministically (no LLM).
    
    HIGH risk tasks:
        - EARLY_CHECKIN → Check/create early check-in
        - FREQUENT_CHECKINS → Check/create frequent check-in
        - FOLLOW_UP_APPOINTMENT → Check/create appointment follow-up
        - APPOINTMENT_MONITORING → Monitor appointment status
        - CONCERN_ESCALATION → Pass to Safety Controller (later)
    
    MODERATE risk tasks:
        - CHECKIN → Check/create patient check-in
        - FOLLOW_UP_APPOINTMENT → Check/create appointment follow-up
        - APPOINTMENT_REMINDER → Check/create appointment reminder
        - RESPONSE_MONITORING → Monitor response status
    
    LOW risk tasks:
        - BASIC_CHECKIN → Check/create basic check-in
        - FOLLOW_UP_REMINDER → Check/create follow-up reminder
        - PATIENT_SUPPORT → Check/create patient support interaction
    
    Args:
        task: Task dictionary with task_id, task_type, status, etc.
        care_plan_id: Associated care plan ID
        risk_level: HIGH, MODERATE, or LOW
        intensity: INTENSIVE, REGULAR, or BASIC
    
    Returns:
        Dict with:
            - next_action: SCHEDULE_CHECKIN, WAIT_FOR_PATIENT_RESPONSE, UPDATE_TASK, or NO_PENDING_TASKS
            - follow_up_data: Details of follow-up action (if applicable)
    """
    task_id = task['task_id']
    task_type = task['task_type']
    status = task['status']
    description = task.get('description')
    doctor_instruction = task.get('doctor_instruction')
    
    # Tasks that require check-in creation/management
    checkin_required_types = {
        "EARLY_CHECKIN",
        "FREQUENT_CHECKINS",
        "FOLLOW_UP_APPOINTMENT",
        "APPOINTMENT_MONITORING",
        "CHECKIN",
        "APPOINTMENT_REMINDER",
        "RESPONSE_MONITORING",
        "BASIC_CHECKIN",
        "FOLLOW_UP_REMINDER",
        "PATIENT_SUPPORT"
    }
    
    # Tasks that should be escalated (not handled here)
    escalation_types = {
        "CONCERN_ESCALATION"
    }
    
    # ====================================================================
    # Handle escalation tasks (CONCERN_ESCALATION)
    # ====================================================================
    
    if task_type in escalation_types:
        logger.info(f"Task {task_id} requires escalation handling (not yet implemented)")
        return {
            "next_action": "UPDATE_TASK",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "status": status,
                "description": description,
                "note": "Requires escalation decision from Safety Controller"
            }
        }
    
    # ====================================================================
    # Handle check-in-based tasks
    # ====================================================================
    
    if task_type in checkin_required_types:
        return _handle_checkin_task(
            task_id=task_id,
            task_type=task_type,
            status=status,
            description=description,
            doctor_instruction=doctor_instruction,
            care_plan_id=care_plan_id,
            risk_level=risk_level
        )
    
    # Unknown task type - log and return UPDATE_TASK
    logger.warning(f"Unknown task type: {task_type}")
    return {
        "next_action": "UPDATE_TASK",
        "follow_up_data": {
            "task_id": task_id,
            "task_type": task_type,
            "status": status,
            "note": f"Unknown task type: {task_type}"
        }
    }


# ============================================================================
# HELPER: HANDLE CHECK-IN TASK
# ============================================================================

def _handle_checkin_task(
    task_id: str,
    task_type: str,
    status: str,
    description: Optional[str],
    doctor_instruction: Optional[str],
    care_plan_id: str,
    risk_level: str
) -> Dict[str, Any]:
    """
    Handle tasks that require check-in creation/management.
    
    Flow:
        1. Check if check-in already exists for this task
        2. If exists: determine action based on check-in status
        3. If not exists: create new check-in
        4. Return appropriate next_action
    
    Args:
        task_id: Task identifier
        task_type: Type of task
        status: Current task status
        description: Task description (for check-in message)
        doctor_instruction: Doctor instruction (for check-in context)
        care_plan_id: Associated care plan
        risk_level: Patient risk level (HIGH/MODERATE/LOW)
    
    Returns:
        Dict with next_action and follow_up_data
    """
    
    # ====================================================================
    # STEP 1: CHECK FOR EXISTING CHECK-INS
    # ====================================================================
    
    try:
        existing_checkins = tools.get_task_checkins(task_id)
    except Exception as e:
        logger.warning(f"Error retrieving check-ins for task {task_id}: {str(e)}")
        existing_checkins = []
    
    # Find active (non-completed, non-cancelled) check-in
    active_checkin = None
    for checkin in existing_checkins:
        if checkin['status'] not in ['COMPLETED', 'CANCELLED', 'MISSED']:
            active_checkin = checkin
            break
    
    # ====================================================================
    # STEP 2: DETERMINE ACTION BASED ON EXISTING CHECK-IN
    # ====================================================================
    
    if active_checkin is not None:
        return _handle_existing_checkin(
            task_id=task_id,
            task_type=task_type,
            checkin=active_checkin,
            description=description,
            doctor_instruction=doctor_instruction
        )
    
    # ====================================================================
    # STEP 3: CREATE NEW CHECK-IN
    # ====================================================================
    
    return _create_new_checkin(
        task_id=task_id,
        task_type=task_type,
        status=status,
        description=description,
        doctor_instruction=doctor_instruction,
        risk_level=risk_level
    )


# ============================================================================
# HELPER: HANDLE EXISTING CHECK-IN
# ============================================================================

def _handle_existing_checkin(
    task_id: str,
    task_type: str,
    checkin: Dict[str, Any],
    description: Optional[str],
    doctor_instruction: Optional[str]
) -> Dict[str, Any]:
    """
    Handle case where an active check-in already exists for a task.
    
    Logic:
        - SCHEDULED → Reuse, wait for send or scheduling
        - SENT → Wait for patient response
        - RESPONSE_RECEIVED → Pass response forward (no interpretation)
    
    Args:
        task_id: Task identifier
        task_type: Type of task
        checkin: Existing check-in dictionary
        description: Task description (context)
        doctor_instruction: Doctor instruction (context)
    
    Returns:
        Dict with next_action and follow_up_data
    """
    checkin_id = checkin['checkin_id']
    checkin_status = checkin['status']
    
    logger.info(
        f"Reusing existing check-in {checkin_id} for task {task_id} "
        f"(status: {checkin_status})"
    )
    
    # If response has been received, pass it forward
    if checkin_status == 'RESPONSE_RECEIVED' and checkin.get('response'):
        logger.info(f"Patient response received for check-in {checkin_id}")
        return {
            "next_action": "UPDATE_TASK",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "checkin_id": checkin_id,
                "response": checkin['response'],
                "response_received_at": checkin['response_received_at'],
                "response_status": "RESPONSE_RECEIVED",
                "note": "Patient response ready for Response Analyzer"
            }
        }
    
    # If sent, wait for response
    if checkin_status == 'SENT':
        return {
            "next_action": "WAIT_FOR_PATIENT_RESPONSE",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "checkin_id": checkin_id,
                "checkin_status": checkin_status,
                "message": checkin.get('message'),
                "channel": checkin.get('channel'),
                "note": "Check-in sent, waiting for patient response"
            }
        }
    
    # If scheduled, can proceed to send
    if checkin_status == 'SCHEDULED':
        return {
            "next_action": "SCHEDULE_CHECKIN",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "checkin_id": checkin_id,
                "checkin_status": checkin_status,
                "description": description,
                "doctor_instruction": doctor_instruction,
                "message": checkin.get('message'),
                "channel": checkin.get('channel'),
                "note": "Check-in scheduled and ready to send"
            }
        }
    
    # Default: pass check-in info
    return {
        "next_action": "WAIT_FOR_PATIENT_RESPONSE",
        "follow_up_data": {
            "task_id": task_id,
            "task_type": task_type,
            "checkin_id": checkin_id,
            "checkin_status": checkin_status,
            "note": f"Check-in in status: {checkin_status}"
        }
    }


# ============================================================================
# HELPER: CREATE NEW CHECK-IN
# ============================================================================

def _create_new_checkin(
    task_id: str,
    task_type: str,
    status: str,
    description: Optional[str],
    doctor_instruction: Optional[str],
    risk_level: str
) -> Dict[str, Any]:
    """
    Create a new check-in record for a task.
    
    Uses task description and doctor instruction to contextualize the check-in.
    Does NOT create a new task.
    
    Args:
        task_id: Task identifier
        task_type: Type of task
        status: Current task status
        description: Task description (for check-in message)
        doctor_instruction: Doctor instruction (for check-in context)
        risk_level: Patient risk level (HIGH/MODERATE/LOW)
    
    Returns:
        Dict with next_action and follow_up_data
    """
    
    try:
        # Create check-in with task information
        checkin_type = _task_type_to_checkin_type(task_type)
        
        checkin = tools.create_checkin(
            task_id=task_id,
            checkin_type=checkin_type,
            scheduled_at=datetime.now(),
            channel="placeholder",  # Telegram integration happens later
            message=_build_checkin_message(
                task_type=task_type,
                description=description,
                doctor_instruction=doctor_instruction
            )
        )
        
        logger.info(
            f"Created new check-in {checkin['checkin_id']} for task {task_id}"
        )
        
        # Update task to IN_PROGRESS if it's PENDING
        if status == 'PENDING':
            try:
                tools.update_task_status(task_id, 'IN_PROGRESS')
                logger.info(f"Updated task {task_id} to IN_PROGRESS")
                new_status = 'IN_PROGRESS'
            except Exception as e:
                logger.warning(f"Could not update task status: {str(e)}")
                new_status = status
        else:
            new_status = status
        
        return {
            "next_action": "SCHEDULE_CHECKIN",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "checkin_id": checkin['checkin_id'],
                "checkin_status": checkin['status'],
                "description": description,
                "doctor_instruction": doctor_instruction,
                "message": checkin['message'],
                "channel": checkin['channel'],
                "task_status": new_status,
                "note": "New check-in created, ready for scheduling"
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to create check-in for task {task_id}: {str(e)}")
        return {
            "next_action": "UPDATE_TASK",
            "follow_up_data": {
                "task_id": task_id,
                "task_type": task_type,
                "status": status,
                "error": f"Failed to create check-in: {str(e)}"
            }
        }


# ============================================================================
# HELPER: TASK TYPE TO CHECK-IN TYPE
# ============================================================================

def _task_type_to_checkin_type(task_type: str) -> str:
    """
    Map task type to check-in type.
    
    Args:
        task_type: Care plan task type
    
    Returns:
        Check-in type string
    """
    mapping = {
        "EARLY_CHECKIN": "early_patient_check",
        "FREQUENT_CHECKINS": "frequent_check",
        "FOLLOW_UP_APPOINTMENT": "appointment_follow_up",
        "APPOINTMENT_MONITORING": "appointment_monitoring",
        "CONCERN_ESCALATION": "escalation",
        "CHECKIN": "patient_check",
        "APPOINTMENT_REMINDER": "appointment_reminder",
        "RESPONSE_MONITORING": "response_monitoring",
        "BASIC_CHECKIN": "basic_check",
        "FOLLOW_UP_REMINDER": "follow_up_reminder",
        "PATIENT_SUPPORT": "patient_support"
    }
    return mapping.get(task_type, "general_check")


# ============================================================================
# HELPER: BUILD CHECK-IN MESSAGE
# ============================================================================

def _build_checkin_message(
    task_type: str,
    description: Optional[str],
    doctor_instruction: Optional[str]
) -> str:
    """
    Build a check-in message from task description and doctor instruction.
    
    Uses personalized task information from Care Plan Agent.
    Does NOT rewrite medical instructions.
    
    Args:
        task_type: Type of task
        description: Task description
        doctor_instruction: Doctor instruction
    
    Returns:
        Check-in message string
    """
    
    # Use doctor instruction if available (most specific)
    if doctor_instruction:
        return f"Follow-up: {doctor_instruction}"
    
    # Fall back to description
    if description:
        return f"Follow-up: {description}"
    
    # Generic message based on task type
    generic_messages = {
        "EARLY_CHECKIN": "Early patient check-in",
        "FREQUENT_CHECKINS": "Frequent check-in",
        "FOLLOW_UP_APPOINTMENT": "Follow-up appointment",
        "APPOINTMENT_MONITORING": "Appointment monitoring",
        "CONCERN_ESCALATION": "Concern escalation",
        "CHECKIN": "Patient check-in",
        "APPOINTMENT_REMINDER": "Appointment reminder",
        "RESPONSE_MONITORING": "Response monitoring",
        "BASIC_CHECKIN": "Basic check-in",
        "FOLLOW_UP_REMINDER": "Follow-up reminder",
        "PATIENT_SUPPORT": "Patient support"
    }
    
    return generic_messages.get(task_type, "Patient follow-up check-in")
