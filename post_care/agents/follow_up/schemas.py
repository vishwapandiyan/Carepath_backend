"""
Follow-up Agent Schemas

Data contracts for the Follow-up Agent.

The Follow-up Agent receives an EXISTING ACTIVE care plan and executes/follows its pending tasks.
It does NOT create the care plan and does NOT perform risk classification.

The Follow-up Agent processes care plan tasks, manages check-ins, and tracks patient engagement.

Input: FollowUpInput (care plan with tasks to follow up on)
Output: FollowUpOutput (check-in results and next actions)
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from datetime import datetime


# ============================================================================
# REUSED SCHEMAS FROM CARE PLAN AGENT
# ============================================================================

class FollowUpTask(BaseModel):
    """
    Task representation for Follow-up Agent.
    
    This is essentially the same as CareTask from the Care Plan Agent,
    but used in the context of the Follow-up Agent.
    
    Represents a specific action or follow-up activity within a care plan
    that the Follow-up Agent will manage or execute.
    
    NEW FIELDS:
    - description: Personalized or generic description of the care task.
    - doctor_instruction: Specific doctor instruction associated with this task, if any.
    """
    task_id: str = Field(
        ...,
        description="Unique identifier for the task"
    )
    task_type: Literal[
        "EARLY_CHECKIN",
        "FREQUENT_CHECKINS",
        "FOLLOW_UP_APPOINTMENT",
        "APPOINTMENT_MONITORING",
        "CONCERN_ESCALATION",
        "CHECKIN",
        "APPOINTMENT_REMINDER",
        "RESPONSE_MONITORING",
        "BASIC_CHECKIN",
        "FOLLOW_UP_REMINDER",
        "PATIENT_SUPPORT"
    ] = Field(
        ...,
        description="Type of task (from Care Plan Agent task types)"
    )
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"] = Field(
        default="PENDING",
        description="Current status of the task"
    )
    description: Optional[str] = Field(
        default=None,
        description="Personalized or generic description of the care task"
    )
    doctor_instruction: Optional[str] = Field(
        default=None,
        description="Specific doctor instruction associated with this task, if any"
    )


# ============================================================================
# PATIENT PREFERENCES SCHEMA
# ============================================================================

class PatientPreferences(BaseModel):
    """
    Optional patient preferences for follow-up communications.
    
    These preferences may be provided to customize the Follow-up Agent's behavior.
    All fields are optional because preference sources will be integrated later.
    """
    language: Optional[str] = Field(
        default=None,
        description="Preferred language for communications (e.g., 'en', 'es', 'fr')"
    )
    preferred_checkin_time: Optional[str] = Field(
        default=None,
        description="Preferred time for check-ins (e.g., '09:00', '14:00')"
    )
    preferred_channel: Optional[str] = Field(
        default=None,
        description="Preferred communication channel (e.g., 'sms', 'email', 'push', 'phone')"
    )

    class Config:
        """Pydantic configuration."""
        extra = "allow"  # Allow additional preference fields for future extensibility


# ============================================================================
# FOLLOW-UP INPUT SCHEMA
# ============================================================================

class FollowUpInput(BaseModel):
    """
    Input schema for the Follow-up Agent.
    
    The Follow-up Agent receives an EXISTING ACTIVE care plan from the orchestrator
    and processes its pending tasks.
    
    This schema represents the care plan data that the Follow-up Agent will work with.
    
    Fields:
    - mrn: Application-level patient identifier
    - care_plan_id: ID of the active care plan to follow up on
    - risk_level: Informational risk level (do NOT recalculate)
    - intensity: Informational intensity level (do NOT recalculate)
    - tasks: List of tasks in the care plan to manage
    - notes: Optional discharge/EHR instructions (may be empty)
    - patient_preferences: Optional patient communication preferences
    """
    mrn: str = Field(
        ...,
        description="Medical Record Number (application-level unique patient identifier)"
    )
    care_plan_id: str = Field(
        ...,
        description="Unique identifier for the existing ACTIVE care plan"
    )
    risk_level: Literal["HIGH", "MODERATE", "LOW"] = Field(
        ...,
        description="Risk level classification (informational only, do NOT recalculate)"
    )
    intensity: Literal["INTENSIVE", "REGULAR", "BASIC"] = Field(
        ...,
        description="Post-care intensity level (informational only, do NOT recalculate)"
    )
    tasks: list[FollowUpTask] = Field(
        ...,
        description="List of tasks in the care plan that need follow-up"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Discharge/EHR notes (may be empty or None)"
    )
    patient_preferences: Optional[PatientPreferences] = Field(
        default=None,
        description="Optional patient preferences for follow-up communications"
    )

    @field_validator("mrn")
    def mrn_not_empty(cls, v):
        """Validate MRN is not empty."""
        if not v or not v.strip():
            raise ValueError("MRN cannot be empty")
        return v

    @field_validator("care_plan_id")
    def care_plan_id_not_empty(cls, v):
        """Validate care_plan_id is not empty."""
        if not v or not v.strip():
            raise ValueError("care_plan_id cannot be empty")
        return v

    @field_validator("risk_level", mode="before")
    def risk_level_valid(cls, v):
        """Validate risk_level is one of allowed values."""
        if v not in ["HIGH", "MODERATE", "LOW"]:
            raise ValueError(f"Invalid risk_level: {v}. Must be HIGH, MODERATE, or LOW")
        return v

    @field_validator("intensity", mode="before")
    def intensity_valid(cls, v):
        """Validate intensity is one of allowed values."""
        if v not in ["INTENSIVE", "REGULAR", "BASIC"]:
            raise ValueError(f"Invalid intensity: {v}. Must be INTENSIVE, REGULAR, or BASIC")
        return v

    @field_validator("tasks")
    def tasks_not_empty(cls, v):
        """Validate that tasks list is not empty."""
        if not v:
            raise ValueError("tasks list cannot be empty")
        return v


# ============================================================================
# CHECK-IN SCHEMA
# ============================================================================

class CheckIn(BaseModel):
    """
    Represents a single check-in event with a patient.
    
    A check-in is a communication with the patient as part of following up on a task.
    It tracks when it was scheduled, what was communicated, and the response status.
    
    NEW FIELDS:
    - response: Patient's response to the check-in, if received.
    - response_received_at: Timestamp when the patient's response was received.
    """
    checkin_id: str = Field(
        ...,
        description="Unique identifier for this check-in"
    )
    task_id: str = Field(
        ...,
        description="ID of the task this check-in relates to"
    )
    checkin_type: str = Field(
        ...,
        description="Type of check-in (e.g., 'appointment_reminder', 'symptom_check', 'medication_adherence')"
    )
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="When the check-in was scheduled (if applicable)"
    )
    channel: Optional[str] = Field(
        default=None,
        description="Communication channel used (e.g., 'sms', 'email', 'push', 'phone')"
    )
    status: Literal["SCHEDULED", "SENT", "RESPONSE_RECEIVED", "COMPLETED", "MISSED", "CANCELLED"] = Field(
        default="SCHEDULED",
        description="Current status of the check-in"
    )
    message: Optional[str] = Field(
        default=None,
        description="Message content or communication details"
    )
    response: Optional[str] = Field(
        default=None,
        description="Patient's response to the check-in, if received"
    )
    response_received_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the patient's response was received"
    )

    @field_validator("status")
    def status_valid(cls, v):
        """Validate check-in status is one of allowed values."""
        allowed = ["SCHEDULED", "SENT", "RESPONSE_RECEIVED", "COMPLETED", "MISSED", "CANCELLED"]
        if v not in allowed:
            raise ValueError(f"Invalid status: {v}. Must be one of {allowed}")
        return v


# ============================================================================
# FOLLOW-UP OUTPUT SCHEMA
# ============================================================================

class FollowUpOutput(BaseModel):
    """
    Output schema for the Follow-up Agent.
    
    Represents the results of follow-up actions on a care plan's tasks.
    
    The Follow-up Agent produces check-in results and determines the next action
    to take in the workflow.
    
    Fields:
    - mrn: Application-level patient identifier (echoed from input)
    - care_plan_id: ID of the care plan being followed up on (echoed from input)
    - follow_up: Results of follow-up activities (check-ins, updates, etc.)
    - next_action: What the orchestrator should do next
    - error: Any error that occurred (if applicable)
    """
    mrn: str = Field(
        ...,
        description="Medical Record Number (echoed from input)"
    )
    care_plan_id: str = Field(
        ...,
        description="Unique identifier for the care plan (echoed from input)"
    )
    follow_up: Optional[dict] = Field(
        default=None,
        description="Follow-up activity results (contains check-ins, task updates, etc.)"
    )
    next_action: Literal[
        "SCHEDULE_CHECKIN",
        "WAIT_FOR_PATIENT_RESPONSE",
        "UPDATE_TASK",
        "NO_PENDING_TASKS"
    ] = Field(
        ...,
        description="Next action for the orchestrator to take"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if something went wrong (None if successful)"
    )

    @field_validator("next_action", mode="before")
    def next_action_valid(cls, v):
        """Validate next_action is one of allowed values."""
        allowed = ["SCHEDULE_CHECKIN", "WAIT_FOR_PATIENT_RESPONSE", "UPDATE_TASK", "NO_PENDING_TASKS"]
        if v not in allowed:
            raise ValueError(f"Invalid next_action: {v}. Must be one of {allowed}")
        return v

    @field_validator("mrn")
    def mrn_not_empty(cls, v):
        """Validate MRN is not empty."""
        if not v or not v.strip():
            raise ValueError("MRN cannot be empty")
        return v

    @field_validator("care_plan_id")
    def care_plan_id_not_empty(cls, v):
        """Validate care_plan_id is not empty."""
        if not v or not v.strip():
            raise ValueError("care_plan_id cannot be empty")
        return v
