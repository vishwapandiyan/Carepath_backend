# Care Plan Access Separation - Implementation Complete

## Overview
Successfully separated access to care plans (care managers only) from follow-up tasks (patients only). This ensures patients never see clinical care plan details and only interact with their follow-up tasks.

---

## Architecture

### Care Managers
- **Access**: Full care plans with all clinical details
- **View**: Risk level, intensity, clinical notes, doctor instructions, all tasks
- **Endpoints**: `/patients/{mrn}/care-plan`, `/care-plans/{care_plan_id}`, etc.
- **Actions**: Can generate care plans, view all details, monitor patient responses

### Patients
- **Access**: Follow-up tasks/check-ins ONLY
- **View**: Task messages, schedules, completion status
- **Endpoint**: `/patients/{patient_id}/follow-up-tasks`
- **Actions**: Mark tasks complete, chat with care team, submit responses

---

## Patient Interaction Flow

1. **Care Manager generates care plan** (invisible to patient)
   - Risk assessment
   - Clinical notes
   - Doctor instructions
   - Care plan tasks created

2. **Follow-up Agent creates check-ins** (visible to patient)
   - Task-specific messages
   - Scheduled check-ins
   - Reminders

3. **Patient receives follow-up tasks**
   - Sees simple task messages
   - Can mark as complete
   - Can chat about concerns

4. **Patient submits response**
   - Goes to Response Analyzer Agent
   - Classified (URGENT, CONCERN, or ROUTINE)
   - Triggers Care Continuity Agent if needed

5. **Care plan revised** (invisible to patient)
   - Care Continuity Agent updates care plan
   - New follow-up tasks generated
   - Patient only sees new tasks, not the plan changes

---

## Changes Made

### Frontend Changes

#### `/Users/vishwa/Desktop/CarePath_CTS/src/App.tsx`
- **CHANGED**: Patient route `/care-plans` now uses `FollowUpTasks` component instead of `CarePlans`
- **REMOVED**: `/my-care-plan` route (was showing full care plan to patients)
- **ADDED**: Import for `FollowUpTasks` component

**Before:**
```tsx
import CarePlans from './pages/CarePlans';
import MyCarePlan from './pages/patient/MyCarePlan';
// ...
<Route path="/care-plans" element={<CarePlans />} />
<Route path="/my-care-plan" element={<MyCarePlan />} />
```

**After:**
```tsx
import FollowUpTasks from './pages/patient/FollowUpTasks';
// ...
<Route path="/care-plans" element={<FollowUpTasks />} />
```

#### `/Users/vishwa/Desktop/CarePath_CTS/src/pages/patient/FollowUpTasks.tsx`
- **ALREADY CREATED**: Complete follow-up tasks interface for patients
- **Features**:
  - Displays pending and completed tasks
  - Embedded chat interface for patient responses
  - Calls `/patients/{patient_id}/follow-up-tasks` endpoint
  - Submits responses to `/patients/{patient_id}/care-plan-response`
  - Shows appropriate messages based on response classification

### Backend Changes

#### `/Users/vishwa/Desktop/CarepathAI_backend/app/api/v1/endpoints/care_plan.py`

**All care plan endpoints now restricted to care managers only:**

1. **`GET /my-care-plan`**
   - Added role check: Blocks patients with 403 error
   - Message: "Patients cannot access care plans directly. Use /patients/{patient_id}/follow-up-tasks instead."

2. **`GET /patients/{mrn}/care-plan`**
   - Added role check: Blocks patients with 403 error
   - Only care managers can access
   - Removed patient authorization logic

3. **`GET /care-plans/{care_plan_id}`**
   - Added role check: Blocks patients with 403 error
   - Only care managers can access
   - Removed patient authorization logic

4. **`GET /care-plans/{care_plan_id}/checkins`**
   - Added role check: Blocks patients with 403 error
   - Only care managers can view check-ins via this endpoint

5. **`GET /care-plans/{care_plan_id}/tasks`**
   - Added role check: Blocks patients with 403 error
   - Only care managers can view tasks via this endpoint

**Patient endpoint remains unchanged:**

6. **`GET /patients/{patient_id}/follow-up-tasks`**
   - ✅ Patients can access their own follow-up tasks
   - Returns only check-ins from `follow_up_checkins` table
   - No care plan details exposed

---

## Data Separation

### Care Plan Tables (Care Managers Only)
- `care_plans` - Full clinical care plan
  - risk_level, intensity, status
  - doctor_instructions, clinical_notes
  
- `care_plan_tasks` - Internal care plan tasks
  - task_type, task_description, status
  - priority, scheduled_date

### Follow-Up Tables (Patients See)
- `follow_up_checkins` - Patient-facing tasks
  - checkin_message (simple, friendly)
  - checkin_type (REMINDER, CHECK_IN, etc.)
  - status, scheduled_at
  - patient_response, classification

---

## Security Features

### Role-Based Access Control
```python
# All care plan endpoints now have this check:
if current_user.role == "PATIENT":
    raise HTTPException(
        status_code=403,
        detail="Patients cannot access care plans. Use /patients/{patient_id}/follow-up-tasks instead."
    )
```

### Patient Data Protection
- Patients can only access their own `patient_id` tasks
- Verification: `if current_user.patient_id != patient_id: raise 403`
- No cross-patient data leakage

### Informative Error Messages
- When patients try to access care plans, they get clear direction to use follow-up tasks endpoint
- Care managers get appropriate errors if they try to access non-existent resources

---

## Testing Checklist

### Patient Login
- [ ] Navigate to `/care-plans` - Should see FollowUpTasks page
- [ ] Should see pending follow-up tasks (if any exist)
- [ ] Should be able to mark tasks complete
- [ ] Should be able to chat with care team
- [ ] Chat responses should trigger Response Analyzer
- [ ] Should NOT be able to access `/my-care-plan`
- [ ] Should NOT see risk level, intensity, clinical notes
- [ ] API calls to care plan endpoints should return 403

### Care Manager Login
- [ ] Navigate to Post Discharge page
- [ ] Should see full care plan details
- [ ] Should see risk level, intensity, clinical notes
- [ ] Should be able to generate care plans
- [ ] Should see patient responses and classifications
- [ ] API calls to care plan endpoints should work

### Care Plan Generation Flow
- [ ] Care manager generates plan for patient
- [ ] Plan stored in `care_plans` and `care_plan_tasks`
- [ ] Follow-up Agent creates check-ins in `follow_up_checkins`
- [ ] Patient sees only follow-up tasks, not care plan
- [ ] Patient response triggers Response Analyzer → Care Continuity
- [ ] Care plan updated (invisible to patient)
- [ ] New follow-up tasks appear for patient

---

## Database Schema Reference

### Care Plans (Care Manager View)
```sql
CREATE TABLE care_plans (
    id TEXT PRIMARY KEY,
    mrn TEXT NOT NULL,
    patient_id TEXT,
    risk_level TEXT NOT NULL,     -- HIGH, MODERATE, LOW
    intensity TEXT NOT NULL,       -- INTENSIVE, REGULAR, BASIC
    status TEXT NOT NULL,          -- ACTIVE, COMPLETED, SUSPENDED
    doctor_instructions TEXT,      -- Clinical instructions
    clinical_notes TEXT,           -- Care manager notes
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE care_plan_tasks (
    id TEXT PRIMARY KEY,
    care_plan_id TEXT REFERENCES care_plans(id),
    task_type TEXT NOT NULL,
    task_description TEXT,        -- Internal task details
    status TEXT,
    priority TEXT,
    scheduled_date TIMESTAMP,
    completed_date TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Follow-Up Tasks (Patient View)
```sql
CREATE TABLE follow_up_checkins (
    id TEXT PRIMARY KEY,
    care_plan_id TEXT REFERENCES care_plans(id),
    task_id TEXT REFERENCES care_plan_tasks(id),
    checkin_type TEXT,             -- REMINDER, CHECK_IN, etc.
    checkin_message TEXT,          -- Patient-friendly message
    patient_response TEXT,         -- Patient's chat response
    response_received_at TIMESTAMP,
    classification TEXT,           -- URGENT, CONCERN, ROUTINE
    status TEXT NOT NULL,          -- SCHEDULED, SENT, RESPONDED, COMPLETED
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    created_at TIMESTAMP
);
```

---

## Files Modified

### Frontend
1. `/Users/vishwa/Desktop/CarePath_CTS/src/App.tsx` - Route changes
2. `/Users/vishwa/Desktop/CarePath_CTS/src/pages/patient/FollowUpTasks.tsx` - Already created

### Backend
1. `/Users/vishwa/Desktop/CarepathAI_backend/app/api/v1/endpoints/care_plan.py` - Access restrictions

---

## Next Steps (Optional Enhancements)

1. **Remove old patient care plan pages** (if they exist and are unused)
   - `/Users/vishwa/Desktop/CarePath_CTS/src/pages/patient/CarePlans.tsx`
   - `/Users/vishwa/Desktop/CarePath_CTS/src/pages/patient/MyCarePlan.tsx`

2. **Add notification system**
   - Push notifications when new follow-up tasks arrive
   - Alert care managers when patient responses are URGENT

3. **Task scheduling**
   - Automatic task delivery based on `scheduled_at`
   - Reminder notifications before due date

4. **Analytics dashboard**
   - Track patient compliance with tasks
   - Response time metrics
   - Classification distribution (URGENT vs CONCERN vs ROUTINE)

---

## Summary

✅ **COMPLETE**: Patients can no longer access care plans
✅ **COMPLETE**: Patients only see follow-up tasks
✅ **COMPLETE**: Care managers have full access to care plans
✅ **COMPLETE**: Patient responses flow through Response Analyzer → Care Continuity → Care plan updates
✅ **COMPLETE**: Frontend routes updated
✅ **COMPLETE**: Backend access controls implemented

**Status**: Ready for testing
**Date**: 2026-08-22
