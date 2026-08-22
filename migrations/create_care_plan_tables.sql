-- Migration: Create Care Plan Tables for Post-Care Agent
-- Purpose: Real LangGraph orchestrator persistence layer
-- Date: 2026-08-22

-- 1. Create care_plans table
CREATE TABLE IF NOT EXISTS care_plans (
    id VARCHAR(255) PRIMARY KEY,                -- CP-{UUID}
    mrn VARCHAR(50) NOT NULL,
    patient_id BIGINT,
    risk_level VARCHAR(50) NOT NULL
        CHECK (risk_level IN ('HIGH', 'MODERATE', 'LOW')),
    intensity VARCHAR(50) NOT NULL
        CHECK (intensity IN ('INTENSIVE', 'REGULAR', 'BASIC')),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'CANCELLED')),
    doctor_instructions TEXT,
    clinical_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Create indexes for care_plans
CREATE INDEX IF NOT EXISTS idx_care_plans_mrn ON care_plans(mrn);
CREATE INDEX IF NOT EXISTS idx_care_plans_patient_id ON care_plans(patient_id);
CREATE INDEX IF NOT EXISTS idx_care_plans_status ON care_plans(status);
CREATE INDEX IF NOT EXISTS idx_care_plans_created_at ON care_plans(created_at);

-- 2. Create care_plan_tasks table
CREATE TABLE IF NOT EXISTS care_plan_tasks (
    id VARCHAR(255) PRIMARY KEY,                -- T-{UUID}
    care_plan_id VARCHAR(255) NOT NULL,
    task_type VARCHAR(100) NOT NULL
        CHECK (task_type IN (
            'FREQUENT_CHECKINS',
            'MEDICATION_REVIEW',
            'VITALS_MONITORING',
            'LABS_MONITORING',
            'EDUCATION',
            'LIFESTYLE',
            'FOLLOWUP_APPOINTMENT',
            'WOUND_CARE',
            'DIET_COUNSELING',
            'PHYSICAL_THERAPY'
        )),
    task_description TEXT NOT NULL,
    task_details JSONB,
    priority VARCHAR(20) DEFAULT 'MEDIUM'
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')),
    status VARCHAR(50) DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'CANCELLED')),
    scheduled_date DATE,
    completed_date DATE,
    assigned_to VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (care_plan_id) REFERENCES care_plans(id) ON DELETE CASCADE
);

-- Create indexes for care_plan_tasks
CREATE INDEX IF NOT EXISTS idx_care_plan_tasks_care_plan_id ON care_plan_tasks(care_plan_id);
CREATE INDEX IF NOT EXISTS idx_care_plan_tasks_status ON care_plan_tasks(status);
CREATE INDEX IF NOT EXISTS idx_care_plan_tasks_scheduled_date ON care_plan_tasks(scheduled_date);

-- 3. Create follow_up_checkins table
CREATE TABLE IF NOT EXISTS follow_up_checkins (
    id VARCHAR(255) PRIMARY KEY,                -- CHK-{UUID}
    care_plan_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    checkin_type VARCHAR(100),
    checkin_message TEXT,
    patient_response TEXT,
    response_received_at TIMESTAMP,
    classification VARCHAR(50)
        CHECK (classification IS NULL OR classification IN (
            'NORMAL', 'CONCERN', 'URGENT', 'UNCLEAR'
        )),
    status VARCHAR(50) DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'SENT', 'RESPONDED', 'COMPLETED', 'SKIPPED', 'CANCELLED')),
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (care_plan_id) REFERENCES care_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES care_plan_tasks(id) ON DELETE CASCADE
);

-- Create indexes for follow_up_checkins
CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_care_plan_id ON follow_up_checkins(care_plan_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_task_id ON follow_up_checkins(task_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_status ON follow_up_checkins(status);
CREATE INDEX IF NOT EXISTS idx_follow_up_checkins_classification ON follow_up_checkins(classification);

-- Success message
DO $$ 
BEGIN 
    RAISE NOTICE '✅ Care plan tables created successfully';
    RAISE NOTICE '   - care_plans';
    RAISE NOTICE '   - care_plan_tasks';
    RAISE NOTICE '   - follow_up_checkins';
END $$;
