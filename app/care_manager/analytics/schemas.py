from datetime import datetime
from pydantic import BaseModel, Field


class AggregateAnalyticsOut(BaseModel):
    total_patients: int = Field(description="Total patient count in database")
    active_patients: int = Field(description="Active patient count")
    high_risk_patients: int = Field(description="Patients with high readmission risk (score >= 0.70)")
    medium_risk_patients: int = Field(description="Patients with medium readmission risk (0.40 <= score < 0.70)")
    low_risk_patients: int = Field(description="Patients with low readmission risk (score < 0.40)")
    readmission_rate_pct: float = Field(description="Percentage of patients categorized as high risk")
    total_safety_evaluations: int = Field(description="Total emergency triage safety evaluations")
    emergency_alerts_triggered: int = Field(description="Emergency referrals (YES verdicts)")
    post_discharge_active_monitors: int = Field(description="Active post-discharge agent monitors")
    timestamp: datetime


class PatientAnalyticsOut(BaseModel):
    patient_id: str
    mrn: str
    name: str | None = None
    readmission_risk_score: float | None = None
    readmission_risk_level: str | None = None
    total_triage_sessions: int = 0
    emergency_triage_triggers: int = 0
    post_discharge_status: str | None = None
    last_activity_at: datetime | None = None
