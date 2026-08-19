-- CarePath Healthcare Platform Database Schema
-- PostgreSQL Schema for EHR, Authentication, and Patient Management
-- Generated: 2026-08-19

-- ============================================
-- Database: carepath_db
-- ============================================

-- Create Database (run this separately as postgres superuser)
-- CREATE DATABASE carepath_db;
-- \c carepath_db;

-- ============================================
-- TABLE: users
-- Purpose: User authentication and role management
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('PATIENT', 'CARE_MANAGER')),
    patient_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_patient FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

-- ============================================
-- TABLE: patients
-- Purpose: Basic patient records (legacy, minimal data)
-- ============================================
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(50) UNIQUE NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    date_of_birth VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patients_mrn ON patients(mrn);

-- ============================================
-- TABLE: patient_ehr
-- Purpose: Complete EHR records following CAREPATH schema
-- ============================================
CREATE TABLE IF NOT EXISTS patient_ehr (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(50) UNIQUE NOT NULL,
    
    -- Demographics
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    date_of_birth DATE NOT NULL,
    age INTEGER NOT NULL CHECK (age >= 0 AND age <= 120),
    gender VARCHAR(20) NOT NULL CHECK (gender IN ('male', 'female', 'other')),
    bmi NUMERIC(5,2) NOT NULL CHECK (bmi >= 10.0 AND bmi <= 80.0),
    insurance_type VARCHAR(50) NOT NULL CHECK (insurance_type IN ('Medicare', 'Medicaid', 'Private', 'Self-pay', 'Medicare_Advantage', 'Uninsured')),
    race VARCHAR(100),
    
    -- Chronic Conditions (binary flags)
    diabetes_flag INTEGER DEFAULT 0 CHECK (diabetes_flag IN (0, 1)),
    heart_failure_flag INTEGER DEFAULT 0 CHECK (heart_failure_flag IN (0, 1)),
    cardiac_history_flag INTEGER DEFAULT 0 CHECK (cardiac_history_flag IN (0, 1)),
    copd_asthma_flag INTEGER DEFAULT 0 CHECK (copd_asthma_flag IN (0, 1)),
    ckd_flag INTEGER DEFAULT 0 CHECK (ckd_flag IN (0, 1)),
    cancer_flag INTEGER DEFAULT 0 CHECK (cancer_flag IN (0, 1)),
    dementia_flag INTEGER DEFAULT 0 CHECK (dementia_flag IN (0, 1)),
    hypertension_flag INTEGER DEFAULT 0 CHECK (hypertension_flag IN (0, 1)),
    immunocompromised_flag INTEGER DEFAULT 0 CHECK (immunocompromised_flag IN (0, 1)),
    charlson_comorbidity_index INTEGER DEFAULT 0 CHECK (charlson_comorbidity_index >= 0 AND charlson_comorbidity_index <= 37),
    
    -- Vital Signs (Current)
    systolic_bp INTEGER,
    diastolic_bp INTEGER,
    heart_rate INTEGER,
    respiratory_rate INTEGER,
    temperature NUMERIC(4,1),
    spo2 INTEGER CHECK (spo2 IS NULL OR (spo2 >= 70 AND spo2 <= 100)),
    pain_score_clinical NUMERIC(3,1) CHECK (pain_score_clinical IS NULL OR (pain_score_clinical >= 0 AND pain_score_clinical <= 10)),
    
    -- Lab Values (13 unique labs)
    hemoglobin NUMERIC(5,2) NOT NULL,
    creatinine NUMERIC(5,2) NOT NULL,
    glucose INTEGER NOT NULL,
    hba1c NUMERIC(4,2),
    wbc_count NUMERIC(6,2) NOT NULL,
    total_bilirubin NUMERIC(5,2),
    platelet_count INTEGER,
    sodium NUMERIC(5,2),
    potassium NUMERIC(4,2),
    troponin NUMERIC(8,4),
    bnp INTEGER,
    lactate NUMERIC(5,2),
    inr NUMERIC(4,2),
    
    -- Medications
    active_medication_count INTEGER DEFAULT 0 CHECK (active_medication_count >= 0),
    medication_count_at_discharge INTEGER,
    polypharmacy_flag INTEGER DEFAULT 0 CHECK (polypharmacy_flag IN (0, 1)),
    high_risk_medication_flag INTEGER DEFAULT 0 CHECK (high_risk_medication_flag IN (0, 1)),
    on_anticoagulants_flag INTEGER DEFAULT 0 CHECK (on_anticoagulants_flag IN (0, 1)),
    on_insulin_flag INTEGER DEFAULT 0 CHECK (on_insulin_flag IN (0, 1)),
    medication_adherence_rate NUMERIC(3,2) CHECK (medication_adherence_rate IS NULL OR (medication_adherence_rate >= 0 AND medication_adherence_rate <= 1)),
    
    -- Utilization History
    previous_admissions_12m INTEGER NOT NULL DEFAULT 0 CHECK (previous_admissions_12m >= 0),
    previous_er_visits_12m INTEGER NOT NULL DEFAULT 0 CHECK (previous_er_visits_12m >= 0),
    prior_30_day_readmission_flag INTEGER DEFAULT 0 CHECK (prior_30_day_readmission_flag IN (0, 1)),
    days_since_last_ed_visit INTEGER,
    ed_visits_90d INTEGER,
    ed_visits_30d INTEGER,
    outpatient_visits_365d INTEGER,
    days_since_last_pcp_visit INTEGER,
    missed_appointments_6m INTEGER,
    
    -- Admission Data
    admission_date DATE,
    discharge_date DATE,
    admission_type VARCHAR(20) CHECK (admission_type IS NULL OR admission_type IN ('elective', 'emergency', 'urgent')),
    length_of_stay_days INTEGER,
    icu_stay_flag INTEGER DEFAULT 0 CHECK (icu_stay_flag IN (0, 1)),
    discharge_destination VARCHAR(50) CHECK (discharge_destination IS NULL OR discharge_destination IN ('home', 'rehab', 'nursing_home', 'other')),
    follow_up_within_7_days_flag INTEGER DEFAULT 0 CHECK (follow_up_within_7_days_flag IN (0, 1)),
    follow_up_appointment_date DATE,
    total_charges_index_stay NUMERIC(12,2),
    
    -- Clinical Notes
    clinical_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patient_ehr_mrn ON patient_ehr(mrn);
CREATE INDEX idx_patient_ehr_name ON patient_ehr(last_name, first_name);
CREATE INDEX idx_patient_ehr_dob ON patient_ehr(date_of_birth);
CREATE INDEX idx_patient_ehr_created ON patient_ehr(created_at);

-- ============================================
-- TRIGGERS
-- ============================================

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to users table
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to patients table
CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to patient_ehr table
CREATE TRIGGER update_patient_ehr_updated_at BEFORE UPDATE ON patient_ehr
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE users IS 'User authentication and role-based access control';
COMMENT ON TABLE patients IS 'Basic patient records (legacy table for authentication)';
COMMENT ON TABLE patient_ehr IS 'Complete EHR records following CAREPATH JSON schema';

COMMENT ON COLUMN patient_ehr.mrn IS 'Auto-generated Medical Record Number (format: MRN######)';
COMMENT ON COLUMN patient_ehr.bmi IS 'Body Mass Index - required for ML Model 1';
COMMENT ON COLUMN patient_ehr.charlson_comorbidity_index IS 'Charlson Comorbidity Index (0-37)';
COMMENT ON COLUMN patient_ehr.clinical_notes IS 'All care manager notes, observations, discharge summary';

-- ============================================
-- SAMPLE DATA (Optional - for testing)
-- ============================================

-- Sample Care Manager
INSERT INTO users (username, password_hash, role, patient_id) VALUES 
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYmRXPq7sCS', 'CARE_MANAGER', NULL)
ON CONFLICT (username) DO NOTHING;
-- Password: admin123

-- ============================================
-- GRANTS (Optional - adjust as needed)
-- ============================================

-- Grant privileges to application user
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO carepath_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO carepath_app_user;
