-- Migration: Create ml_predictions table
-- Purpose: Store predictions from all ML models (readmission, ed_avoidable, etc.)
-- Date: 2026-08-20

-- Create ml_predictions table
CREATE TABLE IF NOT EXISTS ml_predictions (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    mrn VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    model_version VARCHAR(20),
    risk_score FLOAT NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    prediction_result JSONB,
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50),
    
    -- Indexes for efficient queries
    CONSTRAINT ml_predictions_patient_id_idx 
        FOREIGN KEY (patient_id) 
        REFERENCES patient_ehr(patient_id) 
        ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX idx_ml_predictions_patient_id ON ml_predictions(patient_id);
CREATE INDEX idx_ml_predictions_mrn ON ml_predictions(mrn);
CREATE INDEX idx_ml_predictions_model_type ON ml_predictions(model_type);
CREATE INDEX idx_ml_predictions_patient_model_time ON ml_predictions(patient_id, model_type, predicted_at DESC);
CREATE INDEX idx_ml_predictions_mrn_model_time ON ml_predictions(mrn, model_type, predicted_at DESC);

-- Add comments
COMMENT ON TABLE ml_predictions IS 'Stores ML model predictions for all patients';
COMMENT ON COLUMN ml_predictions.patient_id IS 'Patient ID (PAT_XXXXXXXX format)';
COMMENT ON COLUMN ml_predictions.mrn IS 'Medical Record Number (MRNXXXXXXXX format)';
COMMENT ON COLUMN ml_predictions.model_type IS 'Model type: readmission, ed_avoidable, etc.';
COMMENT ON COLUMN ml_predictions.model_version IS 'Version of the ML model used';
COMMENT ON COLUMN ml_predictions.risk_score IS 'Risk probability (0.0 to 1.0)';
COMMENT ON COLUMN ml_predictions.prediction_result IS 'Additional prediction details in JSON format';
COMMENT ON COLUMN ml_predictions.predicted_at IS 'Timestamp when prediction was made';
COMMENT ON COLUMN ml_predictions.created_by IS 'User who triggered prediction (system_auto or manual_trigger)';

-- Grant permissions
GRANT SELECT, INSERT ON ml_predictions TO vishwa;
GRANT USAGE, SELECT ON SEQUENCE ml_predictions_id_seq TO vishwa;
