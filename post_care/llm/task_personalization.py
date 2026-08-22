"""
Task Personalization using extracted doctor instructions.

This module maps extracted doctor instructions to existing task types
and personalizes task descriptions deterministically.

IMPORTANT CONSTRAINTS:
- Uses ONLY extracted doctor instructions (from Groq)
- Does NOT use LLM to decide task mapping
- Does NOT invent medical information
- Does NOT change task types or counts
- Does NOT modify risk-based pathways
- Deterministic mapping only
"""

from typing import Dict, List, Optional, Tuple
from post_care.llm.doctor_instructions import DoctorInstructions


# ============================================================================
# DETERMINISTIC TASK MAPPING
# ============================================================================

def map_instructions_to_tasks(
    risk_level: str,
    doctor_instructions: Optional[DoctorInstructions]
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Map extracted doctor instructions to task types for personalization.
    
    Creates a mapping from task_type to personalization data (description, doctor_instruction).
    
    Args:
        risk_level: "LOW", "MODERATE", or "HIGH"
        doctor_instructions: Extracted DoctorInstructions object (may be empty)
    
    Returns:
        Dict mapping task_type → {"description": str, "doctor_instruction": str}
        Both values can be None if no matching instruction found.
    
    Example:
        {
            "FOLLOW_UP_APPOINTMENT": {
                "description": "Follow up with endocrinology in 10 days.",
                "doctor_instruction": "Follow up with endocrinology in 10 days"
            },
            "RESPONSE_MONITORING": {
                "description": "Check blood glucose every morning.",
                "doctor_instruction": "Check blood glucose every morning"
            }
        }
    """
    
    # Initialize empty mapping for all possible task types
    mapping: Dict[str, Dict[str, Optional[str]]] = {}
    
    if not doctor_instructions:
        # No instructions to map
        return mapping
    
    # ========================================================================
    # MAP follow_up → FOLLOW_UP_APPOINTMENT
    # ========================================================================
    if doctor_instructions.follow_up:
        mapping["FOLLOW_UP_APPOINTMENT"] = {
            "description": doctor_instructions.follow_up,
            "doctor_instruction": doctor_instructions.follow_up
        }
    
    # ========================================================================
    # MAP monitoring → RESPONSE_MONITORING or APPOINTMENT_MONITORING
    # ========================================================================
    if doctor_instructions.monitoring:
        monitoring_str = "\n".join(doctor_instructions.monitoring)
        
        # Choose task type based on risk level
        # HIGH risk pathways use APPOINTMENT_MONITORING
        # MODERATE/LOW use RESPONSE_MONITORING
        task_type = "APPOINTMENT_MONITORING" if risk_level == "HIGH" else "RESPONSE_MONITORING"
        
        mapping[task_type] = {
            "description": monitoring_str,
            "doctor_instruction": monitoring_str
        }
    
    # ========================================================================
    # MAP medication → generic description (no specific task type)
    # ========================================================================
    # Medication instructions are preserved in doctor_instructions field only
    # They are NOT forced into task personalization because tasks are not
    # specifically medication-reminder tasks in the current pathways
    
    # ========================================================================
    # MAP escalation → CONCERN_ESCALATION (if in pathway)
    # ========================================================================
    if doctor_instructions.escalation:
        escalation_str = "\n".join(doctor_instructions.escalation)
        
        # CONCERN_ESCALATION only exists in HIGH risk pathway (5 tasks)
        if risk_level == "HIGH":
            mapping["CONCERN_ESCALATION"] = {
                "description": escalation_str,
                "doctor_instruction": escalation_str
            }
    
    # ========================================================================
    # MAP other_instructions → generic description (no specific task type)
    # ========================================================================
    # Other instructions are preserved in doctor_instructions field only
    
    return mapping


# ============================================================================
# TASK PERSONALIZATION
# ============================================================================

def personalize_task(
    task_type: str,
    mapping: Dict[str, Dict[str, Optional[str]]]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Get personalization data for a specific task.
    
    Args:
        task_type: Type of task (e.g., "FOLLOW_UP_APPOINTMENT")
        mapping: Mapping from map_instructions_to_tasks()
    
    Returns:
        Tuple of (description, doctor_instruction) or (None, None) if no mapping
    
    Example:
        description, doctor_instruction = personalize_task(
            "FOLLOW_UP_APPOINTMENT",
            mapping
        )
        # Returns:
        # ("Follow up with endocrinology in 10 days.", "Follow up with endocrinology in 10 days")
    """
    
    if task_type not in mapping:
        return None, None
    
    task_data = mapping[task_type]
    return task_data.get("description"), task_data.get("doctor_instruction")


# ============================================================================
# GENERIC DESCRIPTIONS (fallback if not personalized)
# ============================================================================

GENERIC_DESCRIPTIONS = {
    # LOW risk (3 tasks)
    "BASIC_CHECKIN": "Basic patient check-in.",
    "FOLLOW_UP_REMINDER": "Follow-up reminder.",
    "PATIENT_SUPPORT": "Patient support and guidance.",
    
    # MODERATE risk (4 tasks)
    "CHECKIN": "Patient check-in.",
    "FOLLOW_UP_APPOINTMENT": "Follow-up appointment.",
    "APPOINTMENT_REMINDER": "Appointment reminder.",
    "RESPONSE_MONITORING": "Monitor patient response.",
    
    # HIGH risk (5 tasks)
    "EARLY_CHECKIN": "Early patient check-in.",
    "FREQUENT_CHECKINS": "Frequent patient check-ins.",
    "APPOINTMENT_MONITORING": "Monitor appointment attendance.",
    "CONCERN_ESCALATION": "Escalate concerns as needed.",
}


def get_task_description(
    task_type: str,
    personalized_description: Optional[str] = None
) -> str:
    """
    Get description for a task, preferring personalized over generic.
    
    Args:
        task_type: Type of task
        personalized_description: Personalized description (if available)
    
    Returns:
        Personalized description if available, otherwise generic description
    
    Example:
        # With personalization:
        desc = get_task_description(
            "FOLLOW_UP_APPOINTMENT",
            "Follow up with endocrinology in 10 days."
        )
        # Returns: "Follow up with endocrinology in 10 days."
        
        # Without personalization:
        desc = get_task_description("CHECKIN", None)
        # Returns: "Patient check-in."
    """
    
    if personalized_description:
        return personalized_description
    
    return GENERIC_DESCRIPTIONS.get(task_type, f"{task_type} task.")
