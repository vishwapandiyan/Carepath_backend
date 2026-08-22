"""
Response Analyzer Schemas

Data contracts for the Response Analyzer.

The Response Analyzer receives a patient's natural-language response
from a Follow-Up check-in and converts it into structured information.

Purpose:
    Input: Patient's natural language response from check-in
        ↓
    Response Analyzer (extracts meaning, classifies)
        ↓
    Output: Structured interpretation with classification
        ↓
    Safety Controller (makes final action decision)

The Response Analyzer answers: "What did the patient communicate?"
The Safety Controller answers: "What action should be taken?"

Key Principle:
    The Response Analyzer performs LANGUAGE UNDERSTANDING only.
    It extracts what the patient said, identifies symptoms and concerns,
    and provides a structured classification.
    
    It does NOT make medical decisions or escalation actions.
    Those belong to the Safety Controller.

Input: ResponseAnalyzerInput (patient response + context)
Output: ResponseAnalyzerOutput (structured interpretation)
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


# ============================================================================
# RESPONSE ANALYZER INPUT
# ============================================================================

class ResponseAnalyzerInput(BaseModel):
    """
    Input schema for the Response Analyzer.
    
    The Response Analyzer receives a patient's natural-language response
    from a Follow-Up check-in along with contextual information about
    the task and care plan.
    
    Required Fields:
    - mrn: Medical Record Number (patient identifier)
    - care_plan_id: Associated care plan ID
    - task_id: Associated task ID
    - checkin_id: Associated check-in ID
    - task_type: Type of follow-up task (context)
    - patient_response: Patient's natural language response
    
    Optional Context:
    - doctor_instruction: Original doctor instruction (context)
    - task_description: Task description (context)
    
    Does NOT include:
    - Risk classification fields (not the analyzer's responsibility)
    - Prediction probability (not the analyzer's responsibility)
    - Action decision fields (Safety Controller responsibility)
    """
    
    mrn: str = Field(
        ...,
        description="Medical Record Number (application-level patient identifier)"
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
        description="Associated check-in ID (where response was recorded)"
    )
    
    task_type: str = Field(
        ...,
        description="Type of follow-up task (e.g., 'FREQUENT_CHECKINS', 'FOLLOW_UP_APPOINTMENT')"
    )
    
    patient_response: str = Field(
        ...,
        description="Patient's natural language response to the check-in"
    )
    
    doctor_instruction: Optional[str] = Field(
        default=None,
        description="Original doctor instruction from care plan (contextual)"
    )
    
    task_description: Optional[str] = Field(
        default=None,
        description="Task description from care plan (contextual)"
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
    
    @field_validator("task_type")
    def task_type_not_empty(cls, v):
        """Validate task_type is not empty."""
        if not v or not v.strip():
            raise ValueError("task_type cannot be empty")
        return v
    
    @field_validator("patient_response")
    def patient_response_not_empty(cls, v):
        """Validate patient_response is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("patient_response cannot be empty or whitespace")
        return v


# ============================================================================
# RESPONSE CLASSIFICATION
# ============================================================================

# Classification levels for patient responses
ResponseClassification = Literal["NORMAL", "CONCERN", "URGENT", "UNCLEAR"]

# Classification Definitions:
# NORMAL: Patient reports expected/improving status and no concerning information
# CONCERN: Patient reports a potentially concerning symptom or worsening condition
# URGENT: Patient response contains potentially severe or immediately concerning information
# UNCLEAR: Response is ambiguous, insufficient, contradictory, or cannot be reliably interpreted


# ============================================================================
# RESPONSE ANALYZER OUTPUT
# ============================================================================

class ResponseAnalyzerOutput(BaseModel):
    """
    Output schema for the Response Analyzer.
    
    Structured interpretation of the patient's natural language response.
    
    Fields:
    - mrn: Medical Record Number (echoed from input)
    - care_plan_id: Associated care plan ID (echoed from input)
    - task_id: Associated task ID (echoed from input)
    - checkin_id: Associated check-in ID (echoed from input)
    - classification: One of NORMAL, CONCERN, URGENT, UNCLEAR
    - summary: Human-readable summary of what the patient communicated
    - symptoms: List of symptoms mentioned by patient
    - concerns: List of concerns identified from response
    - patient_sentiment: Optional sentiment (positive, neutral, negative, etc.)
    - confidence: Confidence score (0.0 to 1.0) of the analysis
    - error: Error message if analysis failed (None if successful)
    
    Does NOT include:
    - final_action (Safety Controller decides)
    - escalation_action (Safety Controller decides)
    - medical diagnosis (not the analyzer's role)
    - treatment recommendations (not the analyzer's role)
    - hospital recommendations (not the analyzer's role)
    
    Key Principle:
    The analyzer extracts WHAT the patient said.
    The Safety Controller decides WHAT TO DO about it.
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
    
    classification: ResponseClassification = Field(
        ...,
        description="Response classification: NORMAL, CONCERN, URGENT, or UNCLEAR"
    )
    
    summary: str = Field(
        ...,
        description="Human-readable summary of what patient communicated"
    )
    
    symptoms: list[str] = Field(
        default_factory=list,
        description="List of symptoms mentioned by patient (may be empty)"
    )
    
    concerns: list[str] = Field(
        default_factory=list,
        description="List of concerns identified from response (may be empty)"
    )
    
    patient_sentiment: Optional[str] = Field(
        default=None,
        description="Patient's sentiment (e.g., positive, neutral, negative). Optional."
    )
    
    confidence: float = Field(
        ...,
        description="Confidence score of analysis (0.0 to 1.0)"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if analysis failed (None if successful)"
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
# CLASSIFICATION EXAMPLES (for reference)
# ============================================================================

# NORMAL Example:
# Input: {"patient_response": "I am feeling much better today."}
# Output: {
#     "classification": "NORMAL",
#     "summary": "Patient reports feeling better.",
#     "symptoms": [],
#     "concerns": [],
#     "patient_sentiment": "positive",
#     "confidence": 0.95
# }

# CONCERN Example:
# Input: {"patient_response": "My wound is more swollen and painful today."}
# Output: {
#     "classification": "CONCERN",
#     "summary": "Patient reports increased wound swelling and pain.",
#     "symptoms": ["wound swelling", "pain"],
#     "concerns": ["worsening wound symptoms"],
#     "patient_sentiment": "negative",
#     "confidence": 0.91
# }

# URGENT Example:
# Input: {"patient_response": "I am having severe difficulty breathing and I cannot catch my breath."}
# Output: {
#     "classification": "URGENT",
#     "summary": "Patient reports severe dyspnea requiring immediate evaluation.",
#     "symptoms": ["severe difficulty breathing", "dyspnea"],
#     "concerns": ["respiratory distress", "potential acute respiratory condition"],
#     "patient_sentiment": "negative",
#     "confidence": 0.97
# }

# UNCLEAR Example:
# Input: {"patient_response": "Okay."}
# Output: {
#     "classification": "UNCLEAR",
#     "summary": "Patient response does not provide sufficient information to determine current condition.",
#     "symptoms": [],
#     "concerns": [],
#     "patient_sentiment": None,
#     "confidence": 0.45
# }
