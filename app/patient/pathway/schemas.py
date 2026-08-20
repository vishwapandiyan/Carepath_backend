from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class PathwayDecision(str, Enum):
    NOT_AVOIDABLE = "NOT_AVOIDABLE"                  # -> Emergency Room / Immediate Intervention
    POTENTIALLY_AVOIDABLE = "POTENTIALLY_AVOIDABLE"  # -> Telehealth / Urgent Care / Outpatient


class CarePlanOption(BaseModel):
    title: str
    urgency: str
    description: str
    recommended_action: str


class PathwayRequest(BaseModel):
    patient_id: str
    chief_complaint: Optional[str] = None
    symptom_onset: Optional[str] = None
    pain_scale: Optional[int] = Field(None, ge=0, le=10)
    location: Optional[str] = None
    red_flag_answers: Optional[Dict[str, bool]] = None


class PathwayResponse(BaseModel):
    patient_id: str
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Emergency / Readmission Risk Score percentage")
    risk_level: str = Field(..., description="LOW, MODERATE, HIGH, or CRITICAL")
    decision: PathwayDecision
    explanation: str
    care_plan: List[CarePlanOption] = []
    predicted_at: datetime
    raw_agent_output: Optional[Dict[str, Any]] = None
