-- CarePath Healthcare Platform Database Schema
-- PostgreSQL Schema for EHR System
-- Auto-generated schema documentation

-- ============================================
-- AUTHENTICATION & USER MANAGEMENT
-- ============================================

-- Users Table: Stores authentication credentials and role information
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('PATIENT', 'CARE_MANAGER')),
    patient_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

-- ============================================
-- PATIENT RECORDS (Legacy/Simple)
-- ============================================

-- Patients Table: Basic patient information for authentication linkage
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    date_of_birth VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patients_mrn ON patients(mrn);

-- ============================================
-- ELECTRONIC HEALTH RECORDS (EHR)
-- ============================================

-- Patient EHR Table: Comprehensive patient medical records
CREATE TABLE IF NOT EXISTS patient_ehr (
    -- Primary Identification
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(255) UNIQUE NOT NULL,
    
    -- Demographics
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    date_of_birth DATE NOT NULL,
    age INTEGER NOT NULL CHECK (age >= 0 AND age <= 120),
    gender VARCHAR(50) NOT NULL CHECK (gender IN ('male', 'female', 'other')),
    bmi DECIMAL(5,2) NOT NULL CHECK (bmi >= 10.0 AND bmi <= 80.0),
    insurance_type VARCHAR(100) NOT NULL CHECK (insurance_type IN ('Medicare', 'Medicaid', 'Private', 'Self-pay', 'Medicare_Advantage', 'Uninsured')),
    race VARCHAR(100),
    
    -- Chronic Conditions (Binary Flags: 0 or 1)
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
    temperature DECIMAL(4,1),
    spo2 INTEGER CHECK (spo2 IS NULL OR (spo2 >= 70 AND spo2 <= 100)),
    pain_score_clinical DECIMAL(3,1) CHECK (pain_score_clinical IS NULL OR (pain_score_clinical >= 0 AND pain_score_clinical <= 10)),
    
    -- Lab Values (13 unique labs)
    hemoglobin DECIMAL(5,2) NOT NULL,
    creatinine DECIMAL(5,2) NOT NULL,
    glucose INTEGER NOT NULL,
    hba1c DECIMAL(4,2),
    wbc_count DECIMAL(6,2) NOT NULL,
    total_bilirubin DECIMAL(5,2),
    platelet_count INTEGER,
    sodium DECIMAL(5,2),
    potassium DECIMAL(4,2),
    troponin DECIMAL(8,4),
    bnp INTEGER,
    lactate DECIMAL(4,2),
    inr DECIMAL(4,2),
    
    -- Medications
    active_medication_count INTEGER DEFAULT 0 CHECK (active_medication_count >= 0),
    medication_count_at_discharge INTEGER,
    polypharmacy_flag INTEGER DEFAULT 0 CHECK (polypharmacy_flag IN (0, 1)),
    high_risk_medication_flag INTEGER DEFAULT 0 CHECK (high_risk_medication_flag IN (0, 1)),
    on_anticoagulants_flag INTEGER DEFAULT 0 CHECK (on_anticoagulants_flag IN (0, 1)),
    on_insulin_flag INTEGER DEFAULT 0 CHECK (on_insulin_flag IN (0, 1)),
    medication_adherence_rate DECIMAL(3,2) CHECK (medication_adherence_rate IS NULL OR (medication_adherence_rate >= 0 AND medication_adherence_rate <= 1)),
    
    -- Utilization History
    previous_admissions_12m INTEGER NOT NULL CHECK (previous_admissions_12m >= 0),
    previous_er_visits_12m INTEGER NOT NULL CHECK (previous_er_visits_12m >= 0),
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
    admission_type VARCHAR(50) CHECK (admission_type IS NULL OR admission_type IN ('elective', 'emergency', 'urgent')),
    length_of_stay_days INTEGER,
    icu_stay_flag INTEGER DEFAULT 0 CHECK (icu_stay_flag IN (0, 1)),
    discharge_destination VARCHAR(50) CHECK (discharge_destination IS NULL OR discharge_destination IN ('home', 'rehab', 'nursing_home', 'other')),
    follow_up_within_7_days_flag INTEGER DEFAULT 0 CHECK (follow_up_within_7_days_flag IN (0, 1)),
    follow_up_appointment_date DATE,
    total_charges_index_stay DECIMAL(12,2),
    
    -- Clinical Notes
    clinical_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_patient_ehr_mrn ON patient_ehr(mrn);
CREATE INDEX idx_patient_ehr_last_name ON patient_ehr(last_name);
CREATE INDEX idx_patient_ehr_dob ON patient_ehr(date_of_birth);
CREATE INDEX idx_patient_ehr_created_at ON patient_ehr(created_at);

-- Foreign Key Constraints
ALTER TABLE users 
    ADD CONSTRAINT fk_users_patient 
    FOREIGN KEY (patient_id) 
    REFERENCES patients(id) 
    ON DELETE SET NULL;

-- ============================================
-- TRIGGER: Auto-update updated_at timestamp
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_patient_ehr_updated_at
    BEFORE UPDATE ON patient_ehr
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- COMMENTS (Documentation)
-- ============================================

COMMENT ON TABLE users IS 'User authentication and authorization table';
COMMENT ON TABLE patients IS 'Basic patient information for authentication linkage';
COMMENT ON TABLE patient_ehr IS 'Comprehensive patient electronic health records';

COMMENT ON COLUMN patient_ehr.mrn IS 'Medical Record Number - auto-generated unique identifier';
COMMENT ON COLUMN patient_ehr.bmi IS 'Body Mass Index - required for ML Model 1 (Readmission)';
COMMENT ON COLUMN patient_ehr.charlson_comorbidity_index IS 'Charlson Comorbidity Index (0-37)';
COMMENT ON COLUMN patient_ehr.clinical_notes IS 'Free-text clinical notes, observations, discharge summaries';
