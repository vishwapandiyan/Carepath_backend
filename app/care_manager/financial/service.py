"""
CarePath Financial Analytics - Service Layer

Business logic for financial calculations, metrics aggregation, and ROI analysis.
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import select, func, and_, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.care_manager.financial.schemas import (
    FinancialMetricsOut,
    PatientFinancialOut,
    InterventionCostOut,
    SavingsTrendOut,
    SavingsTrendPoint,
    InterventionLogOut,
    FinancialCalculationInput,
)


# ============================================================================
# Configuration - Standard Costs (from environment or defaults)
# ============================================================================

STANDARD_READMISSION_COST = Decimal(os.getenv("STANDARD_READMISSION_COST", "15000.00"))
STANDARD_ED_COST = Decimal(os.getenv("STANDARD_ED_COST", "1500.00"))
COST_PER_DAY_LOS = Decimal(os.getenv("COST_PER_DAY_LOS", "2000.00"))
CARE_MANAGER_HOURLY_RATE = Decimal(os.getenv("CARE_MANAGER_HOURLY_RATE", "75.00"))


# ============================================================================
# Core Service Functions
# ============================================================================

async def get_aggregate_metrics(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> FinancialMetricsOut:
    """
    Calculate aggregate financial metrics across all patients.
    
    Args:
        db: Database session
        start_date: Start of analysis period (defaults to 30 days ago)
        end_date: End of analysis period (defaults to today)
    
    Returns:
        FinancialMetricsOut with aggregated metrics
    """
    # Default date range: last 30 days
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)
    
    # Query aggregate metrics from financial_metrics table
    query = text("""
        SELECT 
            COALESCE(COUNT(DISTINCT patient_id), 0) as total_patients_tracked,
            COALESCE(SUM(total_savings), 0) as total_savings,
            COALESCE(SUM(readmission_savings), 0) as readmission_savings,
            COALESCE(SUM(ed_visit_savings), 0) as ed_visit_savings,
            COALESCE(SUM(los_reduction_savings), 0) as los_reduction_savings,
            COALESCE(SUM(medication_adherence_savings), 0) as medication_adherence_savings,
            COALESCE(SUM(other_savings), 0) as other_savings,
            COALESCE(SUM(intervention_costs), 0) as total_intervention_costs,
            COALESCE(SUM(program_costs), 0) as total_program_costs,
            COALESCE(SUM(intervention_count), 0) as total_interventions,
            COALESCE(SUM(readmissions_prevented), 0) as readmissions_prevented,
            COALESCE(SUM(ed_visits_prevented), 0) as ed_visits_prevented
        FROM financial_metrics
        WHERE period_start >= :start_date 
          AND period_end <= :end_date
    """)
    
    result = await db.execute(query, {"start_date": start_date, "end_date": end_date})
    row = result.fetchone()
    
    if not row:
        # No data - return zeros
        return _create_empty_metrics(start_date, end_date)
    
    # Extract values
    total_patients = int(row[0])
    total_savings = Decimal(str(row[1]))
    readmission_savings = Decimal(str(row[2]))
    ed_visit_savings = Decimal(str(row[3]))
    los_reduction_savings = Decimal(str(row[4]))
    medication_adherence_savings = Decimal(str(row[5]))
    other_savings = Decimal(str(row[6]))
    total_intervention_costs = Decimal(str(row[7]))
    total_program_costs = Decimal(str(row[8]))
    total_interventions = int(row[9])
    readmissions_prevented = int(row[10])
    ed_visits_prevented = int(row[11])
    
    # Calculate derived metrics
    total_costs = total_intervention_costs + total_program_costs
    net_savings = total_savings - total_costs
    
    # ROI calculation
    if total_costs > 0:
        roi_percentage = ((total_savings - total_costs) / total_costs) * 100
    else:
        roi_percentage = Decimal("0.00")
    
    # Per-patient averages
    cost_per_patient = total_costs / total_patients if total_patients > 0 else Decimal("0.00")
    savings_per_patient = total_savings / total_patients if total_patients > 0 else Decimal("0.00")
    
    return FinancialMetricsOut(
        total_savings=total_savings,
        readmission_savings=readmission_savings,
        ed_visit_savings=ed_visit_savings,
        los_reduction_savings=los_reduction_savings,
        medication_adherence_savings=medication_adherence_savings,
        other_savings=other_savings,
        total_program_costs=total_program_costs,
        total_intervention_costs=total_intervention_costs,
        net_savings=net_savings,
        roi_percentage=roi_percentage,
        cost_per_patient=cost_per_patient,
        savings_per_patient=savings_per_patient,
        total_patients_tracked=total_patients,
        total_interventions=total_interventions,
        readmissions_prevented=readmissions_prevented,
        ed_visits_prevented=ed_visits_prevented,
        period_start=start_date,
        period_end=end_date,
        timestamp=datetime.utcnow(),
    )


async def get_patient_financials(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "total_savings",
    sort_order: str = "desc",
) -> List[PatientFinancialOut]:
    """
    Get patient-level financial data with pagination and sorting.
    
    Args:
        db: Database session
        limit: Maximum records to return
        offset: Number of records to skip
        sort_by: Field to sort by
        sort_order: 'asc' or 'desc'
    
    Returns:
        List of PatientFinancialOut
    """
    # Build query using the patient_financial_summary view
    sort_col = sort_by if sort_by in ["total_savings", "total_costs", "roi_percentage"] else "total_savings"
    order = desc if sort_order.lower() == "desc" else asc
    
    query = text(f"""
        SELECT 
            pfs.patient_id,
            pfs.patient_name,
            pfs.mrn,
            pfs.total_savings,
            pfs.total_costs,
            pfs.net_savings,
            pfs.roi_percentage,
            COALESCE(fm.readmission_savings, 0) as readmission_savings,
            COALESCE(fm.ed_visit_savings, 0) as ed_visit_savings,
            COALESCE(fm.los_reduction_savings, 0) as los_reduction_savings,
            pfs.intervention_count,
            pfs.readmissions_prevented,
            pfs.ed_visits_prevented,
            pfs.cost_trend,
            pfs.period_start,
            pfs.period_end,
            pfs.calculation_date
        FROM patient_financial_summary pfs
        LEFT JOIN financial_metrics fm ON pfs.patient_id = fm.patient_id 
            AND pfs.period_start = fm.period_start 
            AND pfs.period_end = fm.period_end
        ORDER BY pfs.{sort_col} {sort_order.upper()}
        LIMIT :limit OFFSET :offset
    """)
    
    result = await db.execute(query, {"limit": limit, "offset": offset})
    rows = result.fetchall()
    
    return [
        PatientFinancialOut(
            patient_id=row[0],
            patient_name=row[1] or "Unknown",
            mrn=row[2],
            total_savings=Decimal(str(row[3])),
            total_costs=Decimal(str(row[4])),
            net_savings=Decimal(str(row[5])),
            roi_percentage=Decimal(str(row[6])),
            readmission_savings=Decimal(str(row[7])),
            ed_visit_savings=Decimal(str(row[8])),
            los_reduction_savings=Decimal(str(row[9])),
            intervention_count=int(row[10]),
            readmissions_prevented=int(row[11]),
            ed_visits_prevented=int(row[12]),
            cost_trend=row[13] or "new",
            period_start=row[14],
            period_end=row[15],
            last_updated=row[16],
        )
        for row in rows
    ]


async def get_intervention_costs(
    db: AsyncSession,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> List[InterventionCostOut]:
    """
    Get intervention type breakdown with actual performance data.
    
    Args:
        db: Database session
        period_start: Start date for actual performance (optional)
        period_end: End date for actual performance (optional)
    
    Returns:
        List of InterventionCostOut with actual counts and totals
    """
    # Default to last 30 days if not specified
    if period_end is None:
        period_end = date.today()
    if period_start is None:
        period_start = period_end - timedelta(days=30)
    
    query = text("""
        SELECT 
            ic.intervention_type,
            ic.description,
            ic.cost_per_unit,
            ic.estimated_savings_per_unit,
            ic.active,
            COALESCE(COUNT(pil.id), 0) as count,
            COALESCE(COUNT(pil.id) * ic.cost_per_unit, 0) as total_cost,
            COALESCE(COUNT(pil.id) * ic.estimated_savings_per_unit, 0) as total_savings
        FROM intervention_costs ic
        LEFT JOIN patient_intervention_log pil 
            ON ic.intervention_type = pil.intervention_type
            AND pil.performed_at::date >= :start_date
            AND pil.performed_at::date <= :end_date
        GROUP BY ic.intervention_type, ic.description, ic.cost_per_unit, 
                 ic.estimated_savings_per_unit, ic.active
        ORDER BY total_savings DESC
    """)
    
    result = await db.execute(
        query, 
        {"start_date": period_start, "end_date": period_end}
    )
    rows = result.fetchall()
    
    return [
        InterventionCostOut(
            intervention_type=row[0],
            description=row[1],
            cost_per_unit=Decimal(str(row[2])),
            estimated_savings_per_unit=Decimal(str(row[3])),
            active=row[4],
            count=int(row[5]),
            total_cost=Decimal(str(row[6])),
            total_savings=Decimal(str(row[7])),
            roi_percentage=(
                ((Decimal(str(row[7])) - Decimal(str(row[6]))) / Decimal(str(row[6]))) * 100
                if Decimal(str(row[6])) > 0 else Decimal("0.00")
            ),
        )
        for row in rows
    ]


async def get_savings_trend(
    db: AsyncSession,
    days: int = 30,
) -> SavingsTrendOut:
    """
    Get time-series data for savings trend chart.
    
    Args:
        db: Database session
        days: Number of days to include (default 30)
    
    Returns:
        SavingsTrendOut with daily data points
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    query = text("""
        SELECT 
            fm.calculation_date::date as trend_date,
            COALESCE(SUM(fm.total_savings), 0) as savings,
            COALESCE(SUM(fm.total_costs), 0) as costs,
            COALESCE(SUM(fm.net_savings), 0) as net_savings,
            COALESCE(SUM(fm.intervention_count), 0) as intervention_count
        FROM financial_metrics fm
        WHERE fm.calculation_date >= :start_date
          AND fm.calculation_date <= :end_date
        GROUP BY fm.calculation_date::date
        ORDER BY trend_date ASC
    """)
    
    result = await db.execute(
        query,
        {"start_date": start_date, "end_date": end_date}
    )
    rows = result.fetchall()
    
    # If no data, return empty trend with dates filled in
    if not rows:
        trend_points = []
        current = start_date
        while current <= end_date:
            trend_points.append(
                SavingsTrendPoint(
                    date=current,
                    savings=Decimal("0.00"),
                    costs=Decimal("0.00"),
                    net_savings=Decimal("0.00"),
                    intervention_count=0,
                )
            )
            current += timedelta(days=1)
        
        return SavingsTrendOut(trend=trend_points, period_days=days)
    
    # Build trend points from query results
    trend_points = [
        SavingsTrendPoint(
            date=row[0],
            savings=Decimal(str(row[1])),
            costs=Decimal(str(row[2])),
            net_savings=Decimal(str(row[3])),
            intervention_count=int(row[4]),
        )
        for row in rows
    ]
    
    return SavingsTrendOut(trend=trend_points, period_days=days)


# ============================================================================
# Helper Functions
# ============================================================================

def _create_empty_metrics(start_date: date, end_date: date) -> FinancialMetricsOut:
    """Create a FinancialMetricsOut with all zeros (no data case)."""
    return FinancialMetricsOut(
        total_savings=Decimal("0.00"),
        readmission_savings=Decimal("0.00"),
        ed_visit_savings=Decimal("0.00"),
        los_reduction_savings=Decimal("0.00"),
        medication_adherence_savings=Decimal("0.00"),
        other_savings=Decimal("0.00"),
        total_program_costs=Decimal("0.00"),
        total_intervention_costs=Decimal("0.00"),
        net_savings=Decimal("0.00"),
        roi_percentage=Decimal("0.00"),
        cost_per_patient=Decimal("0.00"),
        savings_per_patient=Decimal("0.00"),
        total_patients_tracked=0,
        total_interventions=0,
        readmissions_prevented=0,
        ed_visits_prevented=0,
        period_start=start_date,
        period_end=end_date,
        timestamp=datetime.utcnow(),
    )


async def log_intervention(
    db: AsyncSession,
    patient_id: str,
    intervention_type: str,
    performed_by: Optional[str] = None,
    outcome: str = "in_progress",
    notes: Optional[str] = None,
) -> InterventionLogOut:
    """
    Log a new intervention performed for a patient.
    
    Args:
        db: Database session
        patient_id: Patient identifier
        intervention_type: Type of intervention
        performed_by: Who performed it
        outcome: Outcome status
        notes: Additional notes
    
    Returns:
        InterventionLogOut with created record
    """
    query = text("""
        INSERT INTO patient_intervention_log 
            (patient_id, intervention_type, performed_by, outcome, notes, performed_at)
        VALUES 
            (:patient_id, :intervention_type, :performed_by, :outcome, :notes, :performed_at)
        RETURNING id, patient_id, intervention_type, performed_at, performed_by, outcome, notes
    """)
    
    result = await db.execute(
        query,
        {
            "patient_id": patient_id,
            "intervention_type": intervention_type,
            "performed_by": performed_by,
            "outcome": outcome,
            "notes": notes,
            "performed_at": datetime.utcnow(),
        },
    )
    await db.commit()
    
    row = result.fetchone()
    
    return InterventionLogOut(
        id=row[0],
        patient_id=row[1],
        intervention_type=row[2],
        performed_at=row[3],
        performed_by=row[4],
        outcome=row[5],
        notes=row[6],
    )
