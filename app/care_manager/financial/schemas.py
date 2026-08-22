"""
CarePath Financial Analytics - Pydantic Schemas

Request and response models for financial endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Response Models
# ============================================================================

class FinancialMetricsOut(BaseModel):
    """Aggregate financial metrics for the platform or specific time period."""
    
    model_config = ConfigDict(from_attributes=True)
    
    # Aggregate savings
    total_savings: Decimal = Field(..., description="Total cost savings across all categories")
    readmission_savings: Decimal = Field(..., description="Savings from prevented readmissions")
    ed_visit_savings: Decimal = Field(..., description="Savings from avoided ED visits")
    los_reduction_savings: Decimal = Field(..., description="Savings from reduced length of stay")
    medication_adherence_savings: Decimal = Field(..., description="Savings from medication compliance")
    other_savings: Decimal = Field(..., description="Savings from other interventions")
    
    # Aggregate costs
    total_program_costs: Decimal = Field(..., description="Total program operational costs")
    total_intervention_costs: Decimal = Field(..., description="Total cost of all interventions")
    
    # Derived metrics
    net_savings: Decimal = Field(..., description="Total savings minus total costs")
    roi_percentage: Decimal = Field(..., description="Return on investment as a percentage")
    cost_per_patient: Decimal = Field(..., description="Average cost per patient served")
    savings_per_patient: Decimal = Field(..., description="Average savings per patient")
    
    # Volume metrics
    total_patients_tracked: int = Field(..., description="Number of patients with financial data")
    total_interventions: int = Field(..., description="Total number of interventions performed")
    readmissions_prevented: int = Field(..., description="Total readmissions prevented")
    ed_visits_prevented: int = Field(..., description="Total ED visits prevented")
    
    # Metadata
    period_start: date = Field(..., description="Start date of analysis period")
    period_end: date = Field(..., description="End date of analysis period")
    timestamp: datetime = Field(..., description="When these metrics were calculated")


class PatientFinancialOut(BaseModel):
    """Financial data for a specific patient."""
    
    model_config = ConfigDict(from_attributes=True)
    
    patient_id: str
    patient_name: str
    mrn: str
    
    # Savings and costs
    total_savings: Decimal
    total_costs: Decimal
    net_savings: Decimal
    roi_percentage: Decimal
    
    # Breakdown
    readmission_savings: Decimal
    ed_visit_savings: Decimal
    los_reduction_savings: Decimal
    
    # Interventions
    intervention_count: int
    readmissions_prevented: int
    ed_visits_prevented: int
    
    # Trend
    cost_trend: str = Field(..., description="Cost trend: 'increasing', 'decreasing', 'stable', 'new'")
    
    # Period
    period_start: date
    period_end: date
    last_updated: datetime


class InterventionCostOut(BaseModel):
    """Cost and savings data for a specific intervention type."""
    
    model_config = ConfigDict(from_attributes=True)
    
    intervention_type: str
    description: Optional[str] = None
    
    # Standard costs
    cost_per_unit: Decimal
    estimated_savings_per_unit: Decimal
    
    # Actual performance
    count: int = Field(..., description="Number of times this intervention was performed")
    total_cost: Decimal = Field(..., description="Total cost of all occurrences")
    total_savings: Decimal = Field(..., description="Total estimated savings from all occurrences")
    roi_percentage: Decimal = Field(..., description="ROI for this intervention type")
    
    # Status
    active: bool


class SavingsTrendPoint(BaseModel):
    """A single data point in the savings trend."""
    
    date: date
    savings: Decimal
    costs: Decimal
    net_savings: Decimal
    intervention_count: int


class SavingsTrendOut(BaseModel):
    """Time-series data for savings trend chart."""
    
    trend: List[SavingsTrendPoint]
    period_days: int


class InterventionLogOut(BaseModel):
    """Record of a single intervention performed."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    patient_id: str
    patient_name: Optional[str] = None
    intervention_type: str
    performed_at: datetime
    performed_by: Optional[str] = None
    outcome: str
    notes: Optional[str] = None


# ============================================================================
# Request Models
# ============================================================================

class FinancialMetricsQuery(BaseModel):
    """Query parameters for financial metrics endpoint."""
    
    start_date: Optional[date] = Field(None, description="Start date for analysis (defaults to 30 days ago)")
    end_date: Optional[date] = Field(None, description="End date for analysis (defaults to today)")


class PatientFinancialQuery(BaseModel):
    """Query parameters for patient financial data."""
    
    limit: int = Field(50, ge=1, le=200, description="Maximum number of records to return")
    offset: int = Field(0, ge=0, description="Number of records to skip")
    sort_by: str = Field("total_savings", description="Field to sort by")
    sort_order: str = Field("desc", description="Sort order: 'asc' or 'desc'")


class SavingsTrendQuery(BaseModel):
    """Query parameters for savings trend data."""
    
    days: int = Field(30, ge=7, le=365, description="Number of days to include in trend")


class InterventionLogQuery(BaseModel):
    """Query parameters for intervention log."""
    
    patient_id: Optional[str] = None
    intervention_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    outcome: Optional[str] = None
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class InterventionLogCreate(BaseModel):
    """Create a new intervention log entry."""
    
    patient_id: str
    intervention_type: str
    performed_by: Optional[str] = None
    outcome: str = Field("in_progress", description="Outcome: 'success', 'in_progress', 'failed', 'pending'")
    notes: Optional[str] = None


class InterventionCostUpdate(BaseModel):
    """Update intervention cost values."""
    
    cost_per_unit: Optional[Decimal] = Field(None, ge=0)
    estimated_savings_per_unit: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    active: Optional[bool] = None


# ============================================================================
# Internal Models (used by service layer)
# ============================================================================

class FinancialCalculationInput(BaseModel):
    """Input data for calculating financial metrics."""
    
    patient_id: str
    period_start: date
    period_end: date
    
    # Savings components
    readmission_savings: Decimal = Decimal("0.00")
    ed_visit_savings: Decimal = Decimal("0.00")
    los_reduction_savings: Decimal = Decimal("0.00")
    medication_adherence_savings: Decimal = Decimal("0.00")
    other_savings: Decimal = Decimal("0.00")
    
    # Cost components
    intervention_costs: Decimal = Decimal("0.00")
    program_costs: Decimal = Decimal("0.00")
    
    # Counts
    intervention_count: int = 0
    readmissions_prevented: int = 0
    ed_visits_prevented: int = 0
