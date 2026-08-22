-- Migration: Fix task_type CHECK constraint to match actual agent task types
-- Date: 2026-08-22
-- Issue: Database had old task types, code uses different ones

-- Drop the old constraint
ALTER TABLE care_plan_tasks 
DROP CONSTRAINT IF EXISTS care_plan_tasks_task_type_check;

-- Add new constraint with correct task types
ALTER TABLE care_plan_tasks
ADD CONSTRAINT care_plan_tasks_task_type_check
CHECK (task_type IN (
    -- LOW risk tasks (3 tasks - BASIC pathway)
    'BASIC_CHECKIN',
    'FOLLOW_UP_REMINDER',
    'PATIENT_SUPPORT',
    
    -- MODERATE risk tasks (4 tasks - REGULAR pathway)
    'CHECKIN',
    'FOLLOW_UP_APPOINTMENT',
    'APPOINTMENT_REMINDER',
    'RESPONSE_MONITORING',
    
    -- HIGH risk tasks (5 tasks - INTENSIVE pathway)
    'EARLY_CHECKIN',
    'FREQUENT_CHECKINS',
    'APPOINTMENT_MONITORING',
    'CONCERN_ESCALATION',
    'MEDICATION_REVIEW',
    
    -- Legacy/additional task types (keep for backwards compatibility)
    'VITALS_MONITORING',
    'LABS_MONITORING',
    'EDUCATION',
    'LIFESTYLE',
    'FOLLOWUP_APPOINTMENT',
    'WOUND_CARE',
    'DIET_COUNSELING',
    'PHYSICAL_THERAPY'
));

-- Success message
DO $$ 
BEGIN 
    RAISE NOTICE '✅ Task type constraint updated successfully';
    RAISE NOTICE '   Now supports all agent task types:';
    RAISE NOTICE '   - LOW: BASIC_CHECKIN, FOLLOW_UP_REMINDER, PATIENT_SUPPORT';
    RAISE NOTICE '   - MODERATE: CHECKIN, FOLLOW_UP_APPOINTMENT, APPOINTMENT_REMINDER, RESPONSE_MONITORING';
    RAISE NOTICE '   - HIGH: EARLY_CHECKIN, FREQUENT_CHECKINS, APPOINTMENT_MONITORING, CONCERN_ESCALATION, MEDICATION_REVIEW';
END $$;
