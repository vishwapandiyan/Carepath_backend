from datetime import datetime
from pydantic import BaseModel, Field


class AggregateAnalyticsOut(BaseModel):
    total_patients: int = Field(description="Total patient count in database")
    active_patients: int = Field(description="Active patient count")
    
    # Readmission Risk Analytics
    high_risk_patients: int = Field(description="Patients with high readmission risk (score >= 0.70)")
    medium_risk_patients: int = Field(description="Patients with medium readmission risk (0.40 <= score < 0.70)")
    low_risk_patients: int = Field(description="Patients with low readmission risk (score < 0.40)")
    readmission_rate_pct: float = Field(description="Percentage of patients categorized as high risk")
    
    # ED (Emergency Department) Analytics
    high_ed_risk_patients: int = Field(description="Patients with high ED avoidability risk (score >= 0.70)", default=0)
    medium_ed_risk_patients: int = Field(description="Patients with medium ED avoidability risk (0.40 <= score < 0.70)", default=0)
    low_ed_risk_patients: int = Field(description="Patients with low ED avoidability risk (score < 0.40)", default=0)
    ed_high_risk_rate_pct: float = Field(description="Percentage of patients with high ED risk", default=0.0)
    total_ed_visits_30d: int = Field(description="Total ED visits in last 30 days across all patients", default=0)
    total_ed_visits_90d: int = Field(description="Total ED visits in last 90 days across all patients", default=0)
    avg_ed_visits_per_patient: float = Field(description="Average ED visits per patient (12 months)", default=0.0)
    
    # Safety & Triage Analytics
    total_safety_evaluations: int = Field(description="Total emergency triage safety evaluations")
    emergency_alerts_triggered: int = Field(description="Emergency referrals (YES verdicts)")
    
    # Post-Discharge Analytics
    post_discharge_active_monitors: int = Field(description="Active post-discharge agent monitors")
    
    timestamp: datetime


class PatientAnalyticsOut(BaseModel):
    patient_id: str
    mrn: str
    name: str | None = None
    
    # Readmission Risk
    readmission_risk_score: float | None = None
    readmission_risk_level: str | None = None
    
    # ED Avoidability Risk
    ed_risk_score: float | None = None
    ed_risk_level: str | None = None
    ed_visits_30d: int = 0
    ed_visits_90d: int = 0
    
    # Safety & Triage
    total_triage_sessions: int = 0
    emergency_triage_triggers: int = 0
    
    # Post-Discharge
    post_discharge_status: str | None = None
    last_activity_at: datetime | None = None
