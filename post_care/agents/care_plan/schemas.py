from pydantic import BaseModel, Field
from typing import Literal, Optional


class ReadmissionInput(BaseModel):
    """
    Input schema for readmission prediction data with clinical notes.
    
    This represents the initial data received from the readmission prediction model,
    containing the MRN (patient identifier), prediction classification, probability score,
    and optional discharge/post-discharge instructions (notes).
    
    Fields:
    - mrn: Medical Record Number (application-level patient identifier)
    - prediction: Readmission model output (0 or 1)
    - probability: Readmission probability (0.0-1.0)
    - notes: Optional discharge instructions (manually entered for now, from EHR later)
    """
    mrn: str = Field(
        ..., 
        description="Medical Record Number (application-level unique patient identifier)"
    )
    prediction: Literal[0, 1] = Field(
        ...,
        description="Readmission model classification: 0 (no readmission) or 1 (readmission risk)"
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Readmission probability score between 0 and 1"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Discharge/post-discharge instructions from EHR or manual input. None or empty string means no existing instructions were provided to our system."
    )


class CareTask(BaseModel):
    """
    Individual task within a care plan.
    
    Represents a specific action or follow-up activity that needs to be performed
    as part of the patient's post-care plan.
    
    NEW: Can include personalized description and doctor instruction derived from
    EHR clinical_notes extraction, while maintaining generic task_type for consistency.
    """
    task_id: str = Field(
        ...,
        description="Unique identifier for the task"
    )
    task_type: str = Field(
        ...,
        description="Type of task (e.g., 'medication_reminder', 'appointment_follow_up', 'symptom_check')"
    )
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"] = Field(
        default="PENDING",
        description="Current status of the task"
    )
    description: Optional[str] = Field(
        default=None,
        description="Personalized task description derived from doctor instructions. If not personalized, can be None (generic description used). Generated deterministically from extracted instructions, not LLM-generated."
    )
    doctor_instruction: Optional[str] = Field(
        default=None,
        description="Specific doctor instruction from EHR clinical_notes that relates to this task. Only populated if instruction matches task type. Not modified or paraphrased."
    )


class CarePlanOutput(BaseModel):
    """
    Complete care plan output for a patient.
    
    Represents the generated post-care plan with risk assessment, intensity level,
    list of risk-based tasks, and incorporated doctor instructions from EHR clinical_notes.
    
    Includes:
    - MRN: Application-level patient identifier
    - patient_id: ML dataset patient identifier (for internal tracking)
    - risk_level: HIGH, MODERATE, or LOW based on readmission probability
    - intensity: INTENSIVE, REGULAR, or BASIC corresponding to risk level
    - notes: Preserved input notes (from API request, for backward compatibility)
    - doctor_instructions: Doctor discharge/care instructions from EHR clinical_notes (if present)
    - tasks: Agent-generated post-care tasks (risk-based pathway)
    """
    mrn: str = Field(
        ...,
        description="Medical Record Number (application-level unique patient identifier)"
    )
    patient_id: str = Field(
        ...,
        description="Internal patient identifier from readmission dataset (for tracking)"
    )
    care_plan_id: str = Field(
        ...,
        description="Unique identifier for this care plan"
    )
    risk_level: Literal["HIGH", "MODERATE", "LOW"] = Field(
        ...,
        description="Risk level classification based on readmission probability"
    )
    intensity: Literal["INTENSIVE", "REGULAR", "BASIC"] = Field(
        ...,
        description="Post-care intensity: INTENSIVE (prob >= 0.80), REGULAR (prob 0.50-0.80), BASIC (prob < 0.50)"
    )
    status: Literal["ACTIVE", "COMPLETED", "CANCELLED"] = Field(
        default="ACTIVE",
        description="Current status of the care plan"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Preserved input notes (from API request, for backward compatibility)"
    )
    doctor_instructions: Optional[str] = Field(
        default=None,
        description="Doctor discharge/care instructions from EHR clinical_notes. Preserved exactly as stored. None if EHR notes are empty/NULL."
    )
    tasks: list[CareTask] = Field(
        default_factory=list,
        description="List of risk-based post-care tasks included in this care plan"
    )

