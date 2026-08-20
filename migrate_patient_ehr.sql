-- Migration Script: Merge patients table into patient_ehr
-- This adds patient_id, full_name, contact_number, email, address, insurance_id, is_active, and deleted_at fields to patient_ehr table

BEGIN;

-- Step 1: Add new columns to patient_ehr if they don't exist
ALTER TABLE patient_ehr 
ADD COLUMN IF NOT EXISTS patient_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS full_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS address VARCHAR(500),
ADD COLUMN IF NOT EXISTS insurance_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Step 2: Update existing patient_ehr records to generate patient_id if NULL
UPDATE patient_ehr 
SET patient_id = 'PAT_' || upper(substr(md5(random()::text || id::text), 1, 8))
WHERE patient_id IS NULL;

-- Step 3: Update full_name for existing records
UPDATE patient_ehr 
SET full_name = first_name || ' ' || last_name
WHERE full_name IS NULL;

-- Step 4: Set is_active to 1 for all existing records
UPDATE patient_ehr 
SET is_active = 1
WHERE is_active IS NULL;

-- Step 5: Make patient_id NOT NULL and UNIQUE after populating
ALTER TABLE patient_ehr 
ALTER COLUMN patient_id SET NOT NULL;

-- Add unique constraint if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'patient_ehr_patient_id_key'
    ) THEN
        ALTER TABLE patient_ehr ADD CONSTRAINT patient_ehr_patient_id_key UNIQUE (patient_id);
    END IF;
END $$;

-- Step 6: Create indexes for new fields
CREATE INDEX IF NOT EXISTS idx_patient_ehr_patient_id ON patient_ehr(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_ehr_email ON patient_ehr(email);
CREATE INDEX IF NOT EXISTS idx_patient_ehr_is_active ON patient_ehr(is_active);

-- Step 7: Add check constraint for is_active
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'patient_ehr_is_active_check'
    ) THEN
        ALTER TABLE patient_ehr ADD CONSTRAINT patient_ehr_is_active_check CHECK (is_active IN (0, 1));
    END IF;
END $$;

COMMIT;

-- Verification queries
SELECT 'Total patient_ehr records' as description, COUNT(*) as count FROM patient_ehr;
SELECT 'Records with patient_id' as description, COUNT(*) as count FROM patient_ehr WHERE patient_id IS NOT NULL;
SELECT 'Records with full_name' as description, COUNT(*) as count FROM patient_ehr WHERE full_name IS NOT NULL;
SELECT 'Active records' as description, COUNT(*) as count FROM patient_ehr WHERE is_active = 1;
