-- Migration: Consolidate first_name, last_name, full_name into single 'name' field

BEGIN;

-- Step 1: Add new 'name' column
ALTER TABLE patient_ehr 
ADD COLUMN IF NOT EXISTS name VARCHAR(255);

-- Step 2: Migrate data from first_name and last_name to name
-- If full_name exists, use it; otherwise combine first_name and last_name
UPDATE patient_ehr 
SET name = COALESCE(full_name, first_name || ' ' || last_name)
WHERE name IS NULL;

-- Step 3: Make name NOT NULL after populating
ALTER TABLE patient_ehr 
ALTER COLUMN name SET NOT NULL;

-- Step 4: Drop old columns
ALTER TABLE patient_ehr 
DROP COLUMN IF EXISTS first_name,
DROP COLUMN IF EXISTS last_name,
DROP COLUMN IF EXISTS full_name;

-- Step 5: Drop old index and create new one
DROP INDEX IF EXISTS idx_patient_ehr_last_name;
CREATE INDEX IF NOT EXISTS idx_patient_ehr_name ON patient_ehr(name);

COMMIT;

-- Verification
SELECT 'Records with name' as description, COUNT(*) as count FROM patient_ehr WHERE name IS NOT NULL;
SELECT patient_id, mrn, name, date_of_birth FROM patient_ehr LIMIT 5;
