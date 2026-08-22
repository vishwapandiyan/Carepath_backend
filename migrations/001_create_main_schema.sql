-- Migration 001: Create Main Schema in PostgreSQL
-- Purpose: Migrate all tables from SQLite to PostgreSQL
-- Date: 2026-08-22

-- =============================================================================
-- USERS & AUTHENTICATION
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('PATIENT', 'CARE_MANAGER')),
    patient_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_patient_id ON users(patient_id);

-- =============================================================================
-- PATIENT EHR (Electronic Health Records)
-- =============================================================================

CREATE TABLE IF NOT EXISTS patient_ehr (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) UNIQUE NOT NULL,
    mrn VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    age INTEGER,
    gender VARCHAR(20),
    date_of_birth DATE,
    
    -- Contact Information
    phone VARCHAR(50),
    email VARCHAR(255),
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(20),
    
    -- Clinical Data
    discharge_date DATE,
    discharge_destination VARCHAR(100),
    clinical_notes TEXT,
    
    -- Vital Signs
    systolic_bp INTEGER,
    diastolic_bp INTEGER,
    heart_rate INTEGER,
    respiratory_rate INTEGER,
    temperature NUMERIC(4, 1),
    spo2 INTEGER,
    pain_score_clinical NUMERIC(3, 1),
    
    -- Lab Results
    hba1c NUMERIC(4, 1),
    creatinine NUMERIC(4, 2),
    egfr INTEGER,
    sodium INTEGER,
    potassium NUMERIC(3, 1),
    hemoglobin NUMERIC(4, 1),
    
    -- Condition Flags
    diabetes_flag INTEGER DEFAULT 0,
    hypertension_flag INTEGER DEFAULT 0,
    heart_failure_flag INTEGER DEFAULT 0,
    copd_asthma_flag INTEGER DEFAULT 0,
    ckd_flag INTEGER DEFAULT 0,
    
    -- Hospitalization History
    prior_30_day_readmission_flag INTEGER DEFAULT 0,
    previous_admissions_12m INTEGER DEFAULT 0,
    icu_stay_flag INTEGER DEFAULT 0,
    length_of_stay INTEGER,
    
    -- Medications & Adherence
    active_medication_count INTEGER DEFAULT 0,
    medication_adherence_rate NUMERIC(5, 2),
    
    -- Comorbidity & Risk Scores
    charlson_comorbidity_index INTEGER DEFAULT 0,
    
    -- Follow-up
    follow_up_appointment_date DATE,
    follow_up_within_7_days_flag INTEGER DEFAULT 0,
    
    -- System Fields
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_ehr_patient_id ON patient_ehr(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_ehr_mrn ON patient_ehr(mrn);
CREATE INDEX IF NOT EXISTS idx_patient_ehr_name ON patient_ehr(name);
CREATE INDEX IF NOT EXISTS idx_patient_ehr_is_active ON patient_ehr(is_active);

-- =============================================================================
-- SAFETY ASSESSMENTS (Immutable Audit Log)
-- =============================================================================

CREATE TABLE IF NOT EXISTS safety_assessments (
    id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    result VARCHAR(20) NOT NULL CHECK (result IN ('PENDING', 'YES', 'NO', 'ERROR')),
    next_action VARCHAR(50) NOT NULL,
    triggered_rules JSONB NOT NULL DEFAULT '[]',
    missing_information JSONB NOT NULL DEFAULT '[]',
    red_flags_snapshot JSONB,
    error_detail VARCHAR(1000),
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_safety_assessments_session_id ON safety_assessments(session_id);
CREATE INDEX IF NOT EXISTS idx_safety_assessments_patient_id ON safety_assessments(patient_id);
CREATE INDEX IF NOT EXISTS idx_safety_assessments_result ON safety_assessments(result);
CREATE INDEX IF NOT EXISTS idx_safety_assessments_evaluated_at ON safety_assessments(evaluated_at);

-- =============================================================================
-- READMISSION PREDICTIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS readmission_predictions (
    id VARCHAR(255) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    risk_score NUMERIC(5, 4) NOT NULL,
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    predicted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_readmission_predictions_patient_id ON readmission_predictions(patient_id);
CREATE INDEX IF NOT EXISTS idx_readmission_predictions_risk_level ON readmission_predictions(risk_level);
CREATE INDEX IF NOT EXISTS idx_readmission_predictions_predicted_at ON readmission_predictions(predicted_at);

-- =============================================================================
-- ML PREDICTIONS (General)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ml_predictions (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    mrn VARCHAR(50),
    model_type VARCHAR(100) NOT NULL,
    prediction_result INTEGER NOT NULL,
    confidence_score NUMERIC(5, 4),
    risk_level VARCHAR(20),
    model_version VARCHAR(50),
    features_used JSONB,
    predicted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_patient_id ON ml_predictions(patient_id);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_mrn ON ml_predictions(mrn);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_model_type ON ml_predictions(model_type);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_composite ON ml_predictions(patient_id, model_type, predicted_at);

-- =============================================================================
-- POST DISCHARGE STATUS
-- =============================================================================

CREATE TABLE IF NOT EXISTS post_discharge_statuses (
    id VARCHAR(255) PRIMARY KEY,
    patient_id VARCHAR(50) UNIQUE NOT NULL,
    care_plan JSONB NOT NULL DEFAULT '{}',
    follow_up JSONB NOT NULL DEFAULT '{}',
    response_analyser JSONB NOT NULL DEFAULT '{}',
    appointment JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_post_discharge_statuses_patient_id ON post_discharge_statuses(patient_id);

-- =============================================================================
-- CHAT SESSIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patient_id VARCHAR(50) REFERENCES patient_ehr(patient_id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL DEFAULT 'New Chat',
    is_title_auto_generated BOOLEAN DEFAULT TRUE,
    message_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    is_pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_patient_id ON chat_sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_is_active ON chat_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message_at ON chat_sessions(last_message_at);

-- =============================================================================
-- CHAT MESSAGES
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(50) UNIQUE NOT NULL,
    session_id VARCHAR(50) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    message_data JSONB NOT NULL,
    role VARCHAR(20) NOT NULL,
    content_preview TEXT,
    parent_message_id VARCHAR(50) REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    is_current_version BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_message_id ON chat_messages(message_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages(role);
CREATE INDEX IF NOT EXISTS idx_chat_messages_is_current_version ON chat_messages(is_current_version);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

-- =============================================================================
-- NOTIFICATIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    patient_id VARCHAR(50) NOT NULL,
    notification_type VARCHAR(50) NOT NULL CHECK (notification_type IN ('task_reminder', 'appointment_reminder', 'care_manager_message', 'task_reframed', 'followup_scheduled')),
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status VARCHAR(20) DEFAULT 'unread' CHECK (status IN ('unread', 'read', 'archived', 'dismissed')),
    is_actionable BOOLEAN DEFAULT FALSE,
    action_url VARCHAR(500),
    action_label VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    related_task_index INTEGER,
    scheduled_for TIMESTAMP WITH TIME ZONE,
    read_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notifications_patient_id ON notifications(patient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_notifications_priority ON notifications(priority);
CREATE INDEX IF NOT EXISTS idx_notifications_scheduled_for ON notifications(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

-- =============================================================================
-- AUTO-UPDATE TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_patient_ehr_updated_at BEFORE UPDATE ON patient_ehr
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_post_discharge_statuses_updated_at BEFORE UPDATE ON post_discharge_statuses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chat_sessions_updated_at BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chat_messages_updated_at BEFORE UPDATE ON chat_messages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SUCCESS MESSAGE
-- =============================================================================

DO $$ 
BEGIN 
    RAISE NOTICE '✅ Main schema created successfully in PostgreSQL';
    RAISE NOTICE '   Tables created:';
    RAISE NOTICE '   - users';
    RAISE NOTICE '   - patient_ehr';
    RAISE NOTICE '   - safety_assessments';
    RAISE NOTICE '   - readmission_predictions';
    RAISE NOTICE '   - ml_predictions';
    RAISE NOTICE '   - post_discharge_statuses';
    RAISE NOTICE '   - chat_sessions';
    RAISE NOTICE '   - chat_messages';
    RAISE NOTICE '   - notifications';
    RAISE NOTICE '';
    RAISE NOTICE '✅ All indexes created';
    RAISE NOTICE '✅ Auto-update triggers created';
END $$;
