"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class RiskTier(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


class Priority(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    URGENT = "URGENT"


# ============================================================================
# Patient Features (Input)
# ============================================================================

class PatientFeatures(BaseModel):
    """29 required features for prediction"""
    
    # Demographics
    age: int = Field(..., ge=0, le=120, description="Patient age in years")
    sex: int = Field(..., ge=0, le=1, description="Sex (0=Female, 1=Male)")
    bmi: float = Field(..., ge=10, le=100, description="Body Mass Index")
    insurance_type: str = Field(..., description="Insurance type")
    
    # Clinical conditions
    comorbidity_index: int = Field(..., ge=0, le=37, description="Charlson Comorbidity Index")
    diabetes_flag: int = Field(..., ge=0, le=1)
    heart_failure_flag: int = Field(..., ge=0, le=1)
    copd_flag: int = Field(..., ge=0, le=1)
    ckd_flag: int = Field(..., ge=0, le=1)
    cancer_flag: int = Field(..., ge=0, le=1)
    dementia_flag: int = Field(..., ge=0, le=1)
    
    # Utilization history
    previous_admissions_12m: int = Field(..., ge=0, le=100)
    previous_er_visits_12m: int = Field(..., ge=0, le=200)
    prior_30_day_readmission_flag: int = Field(..., ge=0, le=1)
    
    # Hospitalization
    admission_type: str = Field(..., description="elective, emergency, or urgent")
    length_of_stay_days: int = Field(..., ge=0, le=365)
    icu_stay_flag: int = Field(..., ge=0, le=1)
    discharge_destination: str = Field(..., description="home, nursing_home, rehab, or other")
    
    # Medications
    medication_count_at_discharge: int = Field(..., ge=0, le=50)
    polypharmacy_flag: int = Field(..., ge=0, le=1)
    high_risk_medication_flag: int = Field(..., ge=0, le=1)
    
    # Lab values
    hemoglobin: float = Field(..., ge=3, le=25, description="g/dL")
    creatinine: float = Field(..., ge=0.1, le=30, description="mg/dL")
    glucose: float = Field(..., ge=20, le=1000, description="mg/dL")
    hba1c: float = Field(..., ge=3, le=18, description="%", alias="hbA1c")  # Accept both names
    wbc_count: float = Field(..., ge=0.5, le=100, description="K/uL")
    total_bilirubin: float = Field(..., ge=0.1, le=50, description="mg/dL")
    
    # Other
    follow_up_within_7_days_flag: int = Field(..., ge=0, le=1)
    total_charges_index_stay: float = Field(..., ge=0, le=1000000)
    drg_code: Optional[str] = Field(None, description="DRG code")
    
    class Config:
        populate_by_name = True  # Allow field to be set by alias or name
        json_schema_extra = {
            "example": {
                "age": 65,
                "sex": 1,
                "bmi": 28.5,
                "insurance_type": "Medicare",
                "comorbidity_index": 3,
                "diabetes_flag": 1,
                "heart_failure_flag": 0,
                "copd_flag": 0,
                "ckd_flag": 0,
                "cancer_flag": 0,
                "dementia_flag": 0,
                "previous_admissions_12m": 2,
                "previous_er_visits_12m": 1,
                "prior_30_day_readmission_flag": 0,
                "admission_type": "emergency",
                "length_of_stay_days": 5,
                "icu_stay_flag": 1,
                "discharge_destination": "home",
                "medication_count_at_discharge": 8,
                "polypharmacy_flag": 1,
                "high_risk_medication_flag": 1,
                "hemoglobin": 12.5,
                "creatinine": 1.2,
                "glucose": 145,
                "hbA1c": 7.2,
                "wbc_count": 8.5,
                "total_bilirubin": 0.8,
                "follow_up_within_7_days_flag": 1,
                "total_charges_index_stay": 25000
            }
        }


# ============================================================================
# Prediction Output (5-Layer System)
# ============================================================================

class Layer1Prediction(BaseModel):
    will_readmit: str
    probability: float
    confidence: str


class Layer2RiskLevel(BaseModel):
    risk_tier: RiskTier
    urgency: str
    probability_range: str


class RiskFactor(BaseModel):
    feature: str
    contribution: float
    impact: str


class Layer3Explanation(BaseModel):
    risk_factors: List[RiskFactor]
    protective_factors: List[RiskFactor]
    risk_profile: Dict[str, str]


class Layer4TimeEstimate(BaseModel):
    day7_risk: float
    day30_risk: float
    day90_risk: float
    most_likely_window: str
    note: str


class Recommendation(BaseModel):
    priority: Priority
    intervention: str
    rationale: str


class Layer5Interventions(BaseModel):
    recommendations: List[Recommendation]


class ComprehensivePrediction(BaseModel):
    prediction_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    layer1_prediction: Layer1Prediction
    layer2_risk_level: Layer2RiskLevel
    layer3_why: Layer3Explanation
    layer4_when: Layer4TimeEstimate
    layer5_intervention: Layer5Interventions
    
    model_version: str = "1.0"


# ============================================================================
# API Response Models
# ============================================================================

class PredictionResponse(BaseModel):
    success: bool
    prediction: ComprehensivePrediction
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    timestamp: datetime
