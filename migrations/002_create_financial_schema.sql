-- ============================================================================
-- CarePath Financial Metrics Schema
-- Migration: 002_create_financial_schema.sql
-- Description: Creates tables for tracking financial metrics, intervention costs,
--              and patient intervention logs for ROI analysis
-- Created: 2026-08-22
-- ============================================================================

-- ============================================================================
-- Table: intervention_costs
-- Purpose: Master table of intervention types with associated costs and savings
-- ============================================================================
CREATE TABLE IF NOT EXISTS intervention_costs (
    id SERIAL PRIMARY KEY,
    intervention_type VARCHAR(100) NOT NULL UNIQUE,
    cost_per_unit DECIMAL(10, 2) NOT NULL CHECK (cost_per_unit >= 0),
    estimated_savings_per_unit DECIMAL(10, 2) NOT NULL CHECK (estimated_savings_per_unit >= 0),
    description TEXT,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for active intervention lookups
CREATE INDEX idx_intervention_costs_active ON intervention_costs(active) WHERE active = true;

-- ============================================================================
-- Table: patient_intervention_log
-- Purpose: Tracks all interventions performed for patients
-- ============================================================================
CREATE TABLE IF NOT EXISTS patient_intervention_log (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    intervention_type VARCHAR(100) NOT NULL,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    performed_by VARCHAR(100),
    outcome VARCHAR(50) DEFAULT 'in_progress',
    notes TEXT,
    
    -- Foreign key constraints
    CONSTRAINT fk_intervention_patient 
        FOREIGN KEY (patient_id) 
        REFERENCES patient_ehr(patient_id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_intervention_type 
        FOREIGN KEY (intervention_type) 
        REFERENCES intervention_costs(intervention_type) 
        ON UPDATE CASCADE,
    
    -- Check constraint for valid outcomes
    CONSTRAINT chk_intervention_outcome 
        CHECK (outcome IN ('success', 'in_progress', 'failed', 'pending'))
);

-- Performance indexes
CREATE INDEX idx_intervention_log_patient ON patient_intervention_log(patient_id);
CREATE INDEX idx_intervention_log_type ON patient_intervention_log(intervention_type);
CREATE INDEX idx_intervention_log_date ON patient_intervention_log(performed_at DESC);
CREATE INDEX idx_intervention_log_outcome ON patient_intervention_log(outcome);

-- Composite index for common queries (patient + date range)
CREATE INDEX idx_intervention_log_patient_date ON patient_intervention_log(patient_id, performed_at DESC);

-- ============================================================================
-- Table: financial_metrics
-- Purpose: Stores calculated financial metrics per patient per time period
-- ============================================================================
CREATE TABLE IF NOT EXISTS financial_metrics (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    
    -- Savings breakdown by category
    readmission_savings DECIMAL(10, 2) DEFAULT 0 CHECK (readmission_savings >= 0),
    ed_visit_savings DECIMAL(10, 2) DEFAULT 0 CHECK (ed_visit_savings >= 0),
    los_reduction_savings DECIMAL(10, 2) DEFAULT 0 CHECK (los_reduction_savings >= 0),
    medication_adherence_savings DECIMAL(10, 2) DEFAULT 0 CHECK (medication_adherence_savings >= 0),
    other_savings DECIMAL(10, 2) DEFAULT 0 CHECK (other_savings >= 0),
    total_savings DECIMAL(10, 2) GENERATED ALWAYS AS (
        readmission_savings + 
        ed_visit_savings + 
        los_reduction_savings + 
        medication_adherence_savings + 
        other_savings
    ) STORED,
    
    -- Cost tracking
    intervention_costs DECIMAL(10, 2) DEFAULT 0 CHECK (intervention_costs >= 0),
    program_costs DECIMAL(10, 2) DEFAULT 0 CHECK (program_costs >= 0),
    total_costs DECIMAL(10, 2) GENERATED ALWAYS AS (
        intervention_costs + program_costs
    ) STORED,
    
    -- Net savings (can be negative if costs exceed savings)
    net_savings DECIMAL(10, 2) GENERATED ALWAYS AS (
        (readmission_savings + 
         ed_visit_savings + 
         los_reduction_savings + 
         medication_adherence_savings + 
         other_savings) - 
        (intervention_costs + program_costs)
    ) STORED,
    
    -- ROI percentage
    roi_percentage DECIMAL(10, 2) GENERATED ALWAYS AS (
        CASE 
            WHEN (intervention_costs + program_costs) > 0 THEN
                (((readmission_savings + 
                   ed_visit_savings + 
                   los_reduction_savings + 
                   medication_adherence_savings + 
                   other_savings) - 
                  (intervention_costs + program_costs)) / 
                 (intervention_costs + program_costs)) * 100
            ELSE 0
        END
    ) STORED,
    
    -- Intervention counts
    intervention_count INTEGER DEFAULT 0 CHECK (intervention_count >= 0),
    readmissions_prevented INTEGER DEFAULT 0 CHECK (readmissions_prevented >= 0),
    ed_visits_prevented INTEGER DEFAULT 0 CHECK (ed_visits_prevented >= 0),
    
    -- Metadata
    calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    
    -- Foreign key
    CONSTRAINT fk_financial_patient 
        FOREIGN KEY (patient_id) 
        REFERENCES patient_ehr(patient_id) 
        ON DELETE CASCADE,
    
    -- Ensure period_start is before period_end
    CONSTRAINT chk_period_order 
        CHECK (period_start <= period_end),
    
    -- Unique constraint: one record per patient per period
    CONSTRAINT uq_financial_patient_period 
        UNIQUE (patient_id, period_start, period_end)
);

-- Performance indexes
CREATE INDEX idx_financial_patient ON financial_metrics(patient_id);
CREATE INDEX idx_financial_period_start ON financial_metrics(period_start DESC);
CREATE INDEX idx_financial_period_end ON financial_metrics(period_end DESC);
CREATE INDEX idx_financial_calculation_date ON financial_metrics(calculation_date DESC);

-- Composite index for date range queries
CREATE INDEX idx_financial_period_range ON financial_metrics(period_start, period_end);

-- Index for finding high-value patients
CREATE INDEX idx_financial_total_savings ON financial_metrics(total_savings DESC);
CREATE INDEX idx_financial_roi ON financial_metrics(roi_percentage DESC);

-- ============================================================================
-- Seed Data: Standard Intervention Costs
-- ============================================================================
INSERT INTO intervention_costs (
    intervention_type, 
    cost_per_unit, 
    estimated_savings_per_unit, 
    description
) VALUES
    (
        'readmission_prevention',
        500.00,
        15000.00,
        'Comprehensive care coordination to prevent 30-day readmission including risk assessment, care planning, and follow-up'
    ),
    (
        'ed_visit_avoidance',
        200.00,
        1500.00,
        'Early intervention and triage support to avoid unnecessary emergency department visits'
    ),
    (
        'medication_adherence',
        50.00,
        800.00,
        'Medication compliance monitoring, education, and adherence support to prevent complications'
    ),
    (
        'follow_up_call',
        25.00,
        300.00,
        'Post-discharge follow-up phone call to assess patient status and provide support'
    ),
    (
        'care_plan_review',
        100.00,
        500.00,
        'Comprehensive care plan review session with patient and family to optimize care strategy'
    ),
    (
        'home_visit',
        150.00,
        1200.00,
        'In-home assessment and care coordination visit to address barriers to recovery'
    ),
    (
        'specialist_coordination',
        75.00,
        600.00,
        'Coordination with specialist providers to ensure continuity of care and prevent complications'
    )
ON CONFLICT (intervention_type) DO NOTHING;

-- ============================================================================
-- Trigger: Update intervention_costs.updated_at on modification
-- ============================================================================
CREATE OR REPLACE FUNCTION update_intervention_costs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_intervention_costs_timestamp
    BEFORE UPDATE ON intervention_costs
    FOR EACH ROW
    EXECUTE FUNCTION update_intervention_costs_timestamp();

-- ============================================================================
-- View: patient_financial_summary
-- Purpose: Convenient view for querying current financial status per patient
-- ============================================================================
CREATE OR REPLACE VIEW patient_financial_summary AS
SELECT 
    fm.patient_id,
    p.name as patient_name,
    p.mrn,
    fm.total_savings,
    fm.total_costs,
    fm.net_savings,
    fm.roi_percentage,
    fm.intervention_count,
    fm.readmissions_prevented,
    fm.ed_visits_prevented,
    fm.period_start,
    fm.period_end,
    fm.calculation_date,
    -- Calculate cost trend (compare to previous period)
    LAG(fm.total_costs) OVER (
        PARTITION BY fm.patient_id 
        ORDER BY fm.period_start
    ) as previous_period_costs,
    CASE 
        WHEN LAG(fm.total_costs) OVER (
            PARTITION BY fm.patient_id 
            ORDER BY fm.period_start
        ) IS NULL THEN 'new'
        WHEN fm.total_costs < LAG(fm.total_costs) OVER (
            PARTITION BY fm.patient_id 
            ORDER BY fm.period_start
        ) THEN 'decreasing'
        WHEN fm.total_costs > LAG(fm.total_costs) OVER (
            PARTITION BY fm.patient_id 
            ORDER BY fm.period_start
        ) THEN 'increasing'
        ELSE 'stable'
    END as cost_trend
FROM 
    financial_metrics fm
    INNER JOIN patient_ehr p ON fm.patient_id = p.patient_id;

-- ============================================================================
-- View: aggregate_financial_metrics
-- Purpose: System-wide financial performance summary
-- ============================================================================
CREATE OR REPLACE VIEW aggregate_financial_metrics AS
SELECT 
    COUNT(DISTINCT patient_id) as total_patients_tracked,
    SUM(total_savings) as total_savings,
    SUM(total_costs) as total_program_costs,
    SUM(net_savings) as net_savings,
    AVG(roi_percentage) as avg_roi_percentage,
    SUM(intervention_count) as total_interventions,
    SUM(readmissions_prevented) as total_readmissions_prevented,
    SUM(ed_visits_prevented) as total_ed_visits_prevented,
    AVG(total_savings) as avg_savings_per_patient,
    AVG(total_costs) as avg_cost_per_patient,
    MAX(calculation_date) as last_calculation_date
FROM 
    financial_metrics
WHERE 
    -- Only include recent data (last 90 days)
    period_end >= CURRENT_DATE - INTERVAL '90 days';

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE intervention_costs IS 'Master list of intervention types with standard costs and estimated savings';
COMMENT ON TABLE patient_intervention_log IS 'Audit log of all interventions performed for patients';
COMMENT ON TABLE financial_metrics IS 'Calculated financial metrics per patient per time period with automatic ROI computation';
COMMENT ON VIEW patient_financial_summary IS 'Convenient view joining patient info with latest financial metrics';
COMMENT ON VIEW aggregate_financial_metrics IS 'System-wide financial performance KPIs';

-- ============================================================================
-- Grant permissions (adjust based on your security model)
-- ============================================================================
-- GRANT SELECT ON intervention_costs TO care_manager_role;
-- GRANT SELECT, INSERT ON patient_intervention_log TO care_manager_role;
-- GRANT SELECT ON financial_metrics TO care_manager_role;
-- GRANT SELECT ON patient_financial_summary TO care_manager_role;
-- GRANT SELECT ON aggregate_financial_metrics TO care_manager_role;

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- Verify tables created:
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' AND table_name LIKE '%intervention%' OR table_name LIKE '%financial%';

-- Verify seed data:
-- SELECT intervention_type, cost_per_unit, estimated_savings_per_unit FROM intervention_costs;
