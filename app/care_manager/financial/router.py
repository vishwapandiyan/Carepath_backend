"""
CarePath Financial Analytics - API Router

FastAPI endpoints for financial metrics, ROI analysis, and cost tracking.
"""

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.care_manager.financial import schemas
from app.care_manager.financial import service


router = APIRouter(prefix="/financial", tags=["Financial Analytics"])


# ============================================================================
# Financial Metrics Endpoints
# ============================================================================

@router.get(
    "/metrics",
    response_model=schemas.FinancialMetricsOut,
    summary="Get aggregate financial metrics",
    description="""
    Returns aggregate financial KPIs across all patients for a specified time period.
    
    Includes:
    - Total cost savings by category
    - Program costs and ROI
    - Intervention volumes
    - Per-patient averages
    
    Defaults to last 30 days if dates not specified.
    """,
)
async def get_financial_metrics(
    start_date: date | None = Query(None, description="Start date (default: 30 days ago)"),
    end_date: date | None = Query(None, description="End date (default: today)"),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate financial metrics for a time period."""
    try:
        metrics = await service.get_aggregate_metrics(
            db=db,
            start_date=start_date,
            end_date=end_date,
        )
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate financial metrics: {str(e)}",
        )


@router.get(
    "/patients",
    response_model=List[schemas.PatientFinancialOut],
    summary="Get patient-level financial data",
    description="""
    Returns financial metrics for individual patients with pagination and sorting.
    
    Use for:
    - Patient financial table on dashboard
    - Identifying high-value patients
    - Drilling down into individual cases
    """,
)
async def get_patient_financials(
    limit: int = Query(50, ge=1, le=200, description="Records per page"),
    offset: int = Query(0, ge=0, description="Skip N records"),
    sort_by: str = Query("total_savings", description="Sort field: total_savings, total_costs, roi_percentage"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    db: AsyncSession = Depends(get_db),
):
    """Get patient-level financial data with pagination."""
    try:
        patients = await service.get_patient_financials(
            db=db,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return patients
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch patient financial data: {str(e)}",
        )


@router.get(
    "/interventions",
    response_model=List[schemas.InterventionCostOut],
    summary="Get intervention cost breakdown",
    description="""
    Returns cost and performance data for each intervention type.
    
    Shows:
    - Standard costs and estimated savings per intervention
    - Actual intervention counts in period
    - Total costs and savings
    - ROI per intervention type
    
    Defaults to last 30 days for actual performance data.
    """,
)
async def get_intervention_costs(
    start_date: date | None = Query(None, description="Period start (default: 30 days ago)"),
    end_date: date | None = Query(None, description="Period end (default: today)"),
    db: AsyncSession = Depends(get_db),
):
    """Get intervention cost breakdown with actual performance."""
    try:
        interventions = await service.get_intervention_costs(
            db=db,
            period_start=start_date,
            period_end=end_date,
        )
        return interventions
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch intervention costs: {str(e)}",
        )


@router.get(
    "/trend",
    response_model=schemas.SavingsTrendOut,
    summary="Get savings trend over time",
    description="""
    Returns time-series data for savings trend chart.
    
    Returns daily data points showing:
    - Total savings
    - Total costs
    - Net savings
    - Intervention count
    
    Use for line charts showing financial performance over time.
    """,
)
async def get_savings_trend(
    days: int = Query(30, ge=7, le=365, description="Number of days to include"),
    db: AsyncSession = Depends(get_db),
):
    """Get time-series data for savings trend chart."""
    try:
        trend = await service.get_savings_trend(
            db=db,
            days=days,
        )
        return trend
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch savings trend: {str(e)}",
        )


# ============================================================================
# Intervention Logging Endpoints
# ============================================================================

@router.post(
    "/interventions/log",
    response_model=schemas.InterventionLogOut,
    status_code=201,
    summary="Log a new intervention",
    description="""
    Create a log entry for an intervention performed for a patient.
    
    This records the intervention in the audit log and will be used
    for financial calculations in the next metrics update.
    """,
)
async def log_intervention(
    data: schemas.InterventionLogCreate,
    db: AsyncSession = Depends(get_db),
):
    """Log a new intervention performed for a patient."""
    try:
        log_entry = await service.log_intervention(
            db=db,
            patient_id=data.patient_id,
            intervention_type=data.intervention_type,
            performed_by=data.performed_by,
            outcome=data.outcome,
            notes=data.notes,
        )
        return log_entry
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to log intervention: {str(e)}",
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get(
    "/health",
    summary="Health check for financial service",
    description="Verify the financial analytics service is operational.",
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Simple query to verify database connectivity
        from sqlalchemy import text
        result = await db.execute(text("SELECT COUNT(*) FROM intervention_costs"))
        count = result.scalar()
        
        return {
            "status": "healthy",
            "service": "financial-analytics",
            "intervention_types_configured": count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service unhealthy: {str(e)}",
        )


# ============================================================================
# Configuration / Admin Endpoints (optional - for future use)
# ============================================================================

@router.get(
    "/config",
    summary="Get financial configuration",
    description="Returns standard cost values used in calculations.",
)
async def get_financial_config():
    """Get current financial calculation configuration."""
    return {
        "standard_costs": {
            "readmission": str(service.STANDARD_READMISSION_COST),
            "ed_visit": str(service.STANDARD_ED_COST),
            "hospital_day": str(service.COST_PER_DAY_LOS),
            "care_manager_hourly_rate": str(service.CARE_MANAGER_HOURLY_RATE),
        },
        "note": "These values are configured via environment variables",
    }
