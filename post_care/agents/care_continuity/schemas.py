"""
Care Continuity Schemas

Data contracts for the Care Continuity Agent.

The Care Continuity Agent receives the structured output of the Response Analyzer
and determines the continuity-of-care workflow that should happen next.

Input: ResponseAnalyzerOutput
Output: CareContinuityOutput

Purpose:
    Response Analyzer answers: "What did the patient communicate?"
    Care Continuity answers: "What continuity workflow should happen?"

Key Principle:
    The Care Continuity Agent is deterministic.
    It makes workflow routing decisions based on classification.
    It does NOT perform medical analysis or diagnosis.
    It does NOT prescribe treatment or medication.
    It does NOT directly contact patients or book appointments.

Architecture:
    Patient Response
        ↓
    Response Analyzer
        ├─ classification (NORMAL|CONCERN|URGENT|UNCLEAR)
        ├─ summary
        ├─ symptoms
        ├─ concerns
        └─ confidence
        ↓
    Care Continuity Agent
        ├─ classification (echo)
        ├─ continuity_action
        ├─ requires_human_review
        ├─ requires_appointment
        └─ reason
        ↓
    Later: Appointment Agent / Communication / Orchestrator

Workflow Classification (NOT medical diagnosis):
    NORMAL → CONTINUE_FOLLOW_UP
    CONCERN → CLINICAL_REVIEW
    URGENT → URGENT_REVIEW
    UNCLEAR → CLARIFICATION_REQUIRED

Safety Boundary:
    Care Continuity does NOT:
    - Diagnose
    - Prescribe
    - Change medication
    - Provide treatment
    - Contact emergency services
    - Send messages
    - Book appointments
    - Modify database
    - Modify care plans
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


# ============================================================================
# CARE CONTINUITY ACTION
# ============================================================================

ContinuityAction = Literal[
    "CONTINUE_FOLLOW_UP",
    "CLINICAL_REVIEW",
    "URGENT_REVIEW",
    "CLARIFICATION_REQUIRED",
]

# Action Definitions:
# CONTINUE_FOLLOW_UP: Patient is stable/improving. Continue routine follow-up.
# CLINICAL_REVIEW: Concerning symptoms. Requires clinical review.
# URGENT_REVIEW: Urgent symptoms. Requires immediate clinical review.
# CLARIFICATION_REQUIRED: Response unclear. Requires clarification from patient.


# ============================================================================
# CARE CONTINUITY INPUT
# ============================================================================

class CareContinuityInput(BaseModel):
    """
    Input schema for the Care Continuity Agent.
    
    The Care Continuity Agent receives the structured output from the
    Response Analyzer and determines what continuity-of-care workflow
    should happen next.
    
    This schema mirrors ResponseAnalyzerOutput to ensure compatibility
    with the Response Analyzer pipeline.
    
    Required Fields:
    - mrn: Medical Record Number
    - care_plan_id: Associated care plan
    - task_id: Associated task
    - checkin_id: Associated check-in
    - classification: Response classification (NORMAL|CONCERN|URGENT|UNCLEAR)
    - summary: Summary of patient response
    - confidence: Confidence in classification (0.0-1.0)
    
    Optional Fields:
    - symptoms: Symptoms identified by Response Analyzer
    - concerns: Concerns identified by Response Analyzer
    - patient_sentiment: Patient sentiment (positive|negative|neutral|mixed)
    - doctor_instruction: Original doctor instruction (for context)
    - task_description: Task description (for context)
    
    Does NOT include:
    - Medical diagnosis
    - Treatment decisions
    - Appointment scheduling details
    - Final action decisions (Care Continuity only routes workflows)
    """
    
    mrn: str = Field(
        ...,
        description="Medical Record Number (patient identifier)"
    )
    
    care_plan_id: str = Field(
        ...,
        description="Associated care plan ID"
    )
    
    task_id: str = Field(
        ...,
        description="Associated task ID"
    )
    
    checkin_id: str = Field(
        ...,
        description="Associated check-in ID"
    )
    
    classification: Literal["NORMAL", "CONCERN", "URGENT", "UNCLEAR"] = Field(
        ...,
        description="Response classification from Response Analyzer"
    )
    
    summary: str = Field(
        ...,
        description="Summary of what patient communicated"
    )
    
    symptoms: list[str] = Field(
        default_factory=list,
        description="Symptoms identified by Response Analyzer"
    )
    
    concerns: list[str] = Field(
        default_factory=list,
        description="Concerns identified by Response Analyzer"
    )
    
    patient_sentiment: Optional[str] = Field(
        default=None,
        description="Patient sentiment (positive|negative|neutral|mixed)"
    )
    
    confidence: float = Field(
        ...,
        description="Confidence in Response Analyzer classification (0.0-1.0)"
    )
    
    doctor_instruction: Optional[str] = Field(
        default=None,
        description="Original doctor instruction (contextual)"
    )
    
    task_description: Optional[str] = Field(
        default=None,
        description="Task description (contextual)"
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
    
    @field_validator("task_id")
    def task_id_not_empty(cls, v):
        """Validate task_id is not empty."""
        if not v or not v.strip():
            raise ValueError("task_id cannot be empty")
        return v
    
    @field_validator("checkin_id")
    def checkin_id_not_empty(cls, v):
        """Validate checkin_id is not empty."""
        if not v or not v.strip():
            raise ValueError("checkin_id cannot be empty")
        return v
    
    @field_validator("summary")
    def summary_not_empty(cls, v):
        """Validate summary is not empty."""
        if not v or not v.strip():
            raise ValueError("summary cannot be empty")
        return v
    
    @field_validator("confidence")
    def confidence_in_range(cls, v):
        """Validate confidence is between 0.0 and 1.0."""
        if not isinstance(v, (int, float)):
            raise ValueError("confidence must be a number")
        if v < 0.0 or v > 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return float(v)
    
    @field_validator("symptoms")
    def symptoms_is_list(cls, v):
        """Validate symptoms is a list."""
        if not isinstance(v, list):
            raise ValueError("symptoms must be a list")
        return v
    
    @field_validator("concerns")
    def concerns_is_list(cls, v):
        """Validate concerns is a list."""
        if not isinstance(v, list):
            raise ValueError("concerns must be a list")
        return v


# ============================================================================
# CARE CONTINUITY OUTPUT
# ============================================================================

class CareContinuityOutput(BaseModel):
    """
    Output schema for the Care Continuity Agent.
    
    Workflow routing decision based on Response Analyzer classification.
    
    This schema determines what continuity-of-care workflow should happen next,
    but does NOT make medical decisions or take actions.
    
    Fields:
    - mrn: Medical Record Number (echoed from input)
    - care_plan_id: Associated care plan ID (echoed from input)
    - task_id: Associated task ID (echoed from input)
    - checkin_id: Associated check-in ID (echoed from input)
    - classification: Response classification (echoed from input)
    - continuity_action: Workflow action (CONTINUE_FOLLOW_UP|CLINICAL_REVIEW|URGENT_REVIEW|CLARIFICATION_REQUIRED)
    - reason: Human-readable reason for the action
    - requires_human_review: Whether human clinician should review
    - requires_appointment: Whether appointment workflow may be needed
    - error: Error message if determination failed (None if successful)
    
    Does NOT include:
    - Medical diagnosis
    - Treatment recommendations
    - Medication changes
    - Final action decision
    - Appointment booking
    
    Key Principle:
    Care Continuity routes workflow based on classification.
    Other components (Appointment Agent, Communication) handle downstream actions.
    
    Deterministic Mapping:
    NORMAL    → CONTINUE_FOLLOW_UP (no human review, no appointment)
    CONCERN   → CLINICAL_REVIEW (human review, may need appointment)
    URGENT    → URGENT_REVIEW (human review, may need appointment)
    UNCLEAR   → CLARIFICATION_REQUIRED (no immediate human review, needs clarification)
    """
    
    mrn: str = Field(
        ...,
        description="Medical Record Number (echoed from input)"
    )
    
    care_plan_id: str = Field(
        ...,
        description="Associated care plan ID (echoed from input)"
    )
    
    task_id: str = Field(
        ...,
        description="Associated task ID (echoed from input)"
    )
    
    checkin_id: str = Field(
        ...,
        description="Associated check-in ID (echoed from input)"
    )
    
    classification: Literal["NORMAL", "CONCERN", "URGENT", "UNCLEAR"] = Field(
        ...,
        description="Response classification (echoed from Response Analyzer)"
    )
    
    continuity_action: ContinuityAction = Field(
        ...,
        description="Continuity workflow action"
    )
    
    reason: str = Field(
        ...,
        description="Human-readable reason for the continuity action"
    )
    
    requires_human_review: bool = Field(
        ...,
        description="Whether human clinician should review this case"
    )
    
    requires_appointment: bool = Field(
        ...,
        description="Whether appointment workflow may be required"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if determination failed (None if successful)"
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
    
    @field_validator("task_id")
    def task_id_not_empty(cls, v):
        """Validate task_id is not empty."""
        if not v or not v.strip():
            raise ValueError("task_id cannot be empty")
        return v
    
    @field_validator("checkin_id")
    def checkin_id_not_empty(cls, v):
        """Validate checkin_id is not empty."""
        if not v or not v.strip():
            raise ValueError("checkin_id cannot be empty")
        return v
    
    @field_validator("reason")
    def reason_not_empty(cls, v):
        """Validate reason is not empty."""
        if not v or not v.strip():
            raise ValueError("reason cannot be empty")
        return v


# ============================================================================
# DETERMINISTIC MAPPING REFERENCE
# ============================================================================

"""
Classification → Continuity Action Mapping:

NORMAL Classification:
    classification: "NORMAL"
    continuity_action: "CONTINUE_FOLLOW_UP"
    requires_human_review: False
    requires_appointment: False
    reason: "Patient reports stable or improving condition. Continue routine follow-up."

CONCERN Classification:
    classification: "CONCERN"
    continuity_action: "CLINICAL_REVIEW"
    requires_human_review: True
    requires_appointment: False
    reason: "Patient response contains potentially concerning symptoms. Requires clinical review."

URGENT Classification:
    classification: "URGENT"
    continuity_action: "URGENT_REVIEW"
    requires_human_review: True
    requires_appointment: False
    reason: "Patient response contains potentially urgent symptoms. Requires immediate clinical review."

UNCLEAR Classification:
    classification: "UNCLEAR"
    continuity_action: "CLARIFICATION_REQUIRED"
    requires_human_review: False
    requires_appointment: False
    reason: "Patient response does not provide sufficient information. Requires clarification from patient."

This mapping is deterministic and does not require LLM processing.
"""


# ============================================================================
# MAPPING FUNCTION (for reference in agent implementation)
# ============================================================================

def get_continuity_action(classification: str) -> dict:
    """
    Get the deterministic continuity action for a classification.
    
    This function encapsulates the classification → action mapping.
    
    Args:
        classification: One of NORMAL, CONCERN, URGENT, UNCLEAR
    
    Returns:
        Dictionary with:
        - continuity_action: Workflow action
        - requires_human_review: Boolean
        - requires_appointment: Boolean
        - reason: Explanation
    
    Raises:
        ValueError: If classification is invalid
    """
    
    mapping = {
        "NORMAL": {
            "continuity_action": "CONTINUE_FOLLOW_UP",
            "requires_human_review": False,
            "requires_appointment": False,
            "reason": "Patient reports stable or improving condition. Continue routine follow-up.",
        },
        "CONCERN": {
            "continuity_action": "CLINICAL_REVIEW",
            "requires_human_review": True,
            "requires_appointment": False,
            "reason": "Patient response contains potentially concerning symptoms. Flagged for clinical review. Continue monitoring.",
        },
        "URGENT": {
            "continuity_action": "URGENT_REVIEW",
            "requires_human_review": True,
            "requires_appointment": True,
            "reason": "Patient response contains potentially urgent symptoms. Requires immediate clinical review and urgent appointment.",
        },
        "UNCLEAR": {
            "continuity_action": "CLARIFICATION_REQUIRED",
            "requires_human_review": False,
            "requires_appointment": False,
            "reason": "Patient response does not provide sufficient information. Requires clarification from patient.",
        },
    }
    
    if classification not in mapping:
        raise ValueError(f"Invalid classification: {classification}. Must be one of: NORMAL, CONCERN, URGENT, UNCLEAR")
    
    return mapping[classification]
