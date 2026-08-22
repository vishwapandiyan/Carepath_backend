-- Cleanup script for orphaned care plans (plans without tasks from failed runs)
-- Run this if care plan generation fails with "tasks cannot be empty"

-- Show orphaned plans (plans with 0 tasks)
SELECT 
    cp.id as care_plan_id,
    cp.mrn,
    cp.risk_level,
    cp.created_at,
    COUNT(t.id) as task_count
FROM care_plans cp
LEFT JOIN care_plan_tasks t ON t.care_plan_id = cp.id
WHERE cp.status = 'ACTIVE'
GROUP BY cp.id, cp.mrn, cp.risk_level, cp.created_at
HAVING COUNT(t.id) = 0;

-- Delete orphaned care plans (CAREFUL: This will allow them to be recreated)
-- Uncomment the lines below to actually delete:

-- DELETE FROM care_plans 
-- WHERE id IN (
--     SELECT cp.id
--     FROM care_plans cp
--     LEFT JOIN care_plan_tasks t ON t.care_plan_id = cp.id
--     WHERE cp.status = 'ACTIVE'
--     GROUP BY cp.id
--     HAVING COUNT(t.id) = 0
-- );

-- Or delete a specific care plan:
-- DELETE FROM care_plans WHERE id = 'CP-001222B8';

-- Verify deletion:
-- SELECT * FROM care_plans WHERE mrn = 'TEST_DEMO_001';
