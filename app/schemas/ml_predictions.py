from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class MLPredictionCreate(BaseModel):
    """Schema for creating a new ML prediction"""
    patient_id: str
    mrn: str
    model_type: str = Field(..., description="Model type: readmission, ed_avoidable, etc.")
    model_version: Optional[str] = None
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk probability (0.0 to 1.0)")
    prediction_result: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None


class MLPredictionResponse(BaseModel):
    """Schema for ML prediction response"""
    id: int
    patient_id: str
    mrn: str
    model_type: str
    model_version: Optional[str]
    risk_score: float
    prediction_result: Optional[Dict[str, Any]]
    predicted_at: datetime
    created_by: Optional[str]
    
    class Config:
        from_attributes = True


class ReadmissionPredictionResponse(BaseModel):
    """Schema for readmission prediction response"""
    readmission_risk_score: float = Field(..., description="30-day readmission probability (0.0 to 1.0)")
    predicted_at: datetime
    model_version: str
    prediction_details: Optional[Dict[str, Any]] = None


class EDAvoidablePredictionResponse(BaseModel):
    """Schema for ED avoidable prediction response"""
    ed_avoidable_probability: float = Field(..., description="ED visit avoidable probability (0.0 to 1.0)")
    predicted_at: datetime
    model_version: str
    prediction_details: Optional[Dict[str, Any]] = None
