-- Add appointment_type column to distinguish post-discharge followups
-- Created: January 2027
-- Purpose: Support post-discharge care agent appointment tracking

-- Add appointment_type column
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(50) DEFAULT 'regular';

-- Add index for querying by type
CREATE INDEX IF NOT EXISTS idx_appointments_type ON appointments(appointment_type);

-- Add comment
COMMENT ON COLUMN appointments.appointment_type IS 'Type of appointment: regular, post_discharge_followup';

-- Verification
SELECT 'appointments' AS table_name, COUNT(*) AS row_count FROM appointments;
