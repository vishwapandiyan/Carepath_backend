# Test Plan: Care Plan Access Separation

## Quick Test Commands

### 1. Start Backend Server
```bash
cd /Users/vishwa/Desktop/CarepathAI_backend
# Activate your virtual environment if needed
uvicorn app.main:app --reload
```

### 2. Start Frontend Server
```bash
cd /Users/vishwa/Desktop/CarePath_CTS
npm run dev
```

---

## Test Scenarios

### Scenario 1: Patient Login - Follow-Up Tasks Only

**Steps:**
1. Login as patient (e.g., username: `patient`, password: `test123`)
2. Navigate to Care Plans page (clicking "Care Plans" in sidebar)
3. Verify you see "My Follow-Up Tasks" page (NOT "My Care Plans")
4. Verify you see:
   - Pending tasks section (if any exist)
   - Completed tasks section (if any exist)
   - Chat interface at the bottom
5. Try to manually navigate to `/my-care-plan`
   - Should redirect or show error

**Expected Backend API Calls:**
```bash
# This should work (200 OK)
GET http://localhost:8000/api/v1/patients/{patient_id}/follow-up-tasks
Authorization: Bearer {patient_token}

# This should fail (403 Forbidden)
GET http://localhost:8000/api/v1/patient/care-plan
Authorization: Bearer {patient_token}
```

**Expected Results:**
- ✅ Patient sees follow-up tasks page
- ✅ Patient does NOT see risk level, intensity, clinical notes
- ✅ Patient can mark tasks complete
- ✅ Patient can chat with care team
- ❌ Patient CANNOT access care plan endpoints

---

### Scenario 2: Care Manager Login - Full Care Plans

**Steps:**
1. Login as care manager (e.g., username: `caremanager`, password: `test123`)
2. Navigate to Post Discharge page
3. Select a patient
4. Click "Generate Care Plan" (if not already generated)
5. Verify you see:
   - Risk Level (HIGH/MODERATE/LOW)
   - Intensity (INTENSIVE/REGULAR/BASIC)
   - Clinical Notes
   - Doctor Instructions
   - All care plan tasks
   - Patient responses (if any)

**Expected Backend API Calls:**
```bash
# This should work (200 OK)
GET http://localhost:8000/api/v1/patients/{mrn}/care-plan
Authorization: Bearer {care_manager_token}

# Generate care plan
POST http://localhost:8000/api/v1/care-manager/post-discharge/{mrn}/generate-care-plan
Authorization: Bearer {care_manager_token}
```

**Expected Results:**
- ✅ Care manager sees full care plan details
- ✅ Care manager can generate care plans
- ✅ Care manager sees all clinical information
- ✅ Care manager can view patient responses and classifications

---

### Scenario 3: Patient Response Flow

**Steps:**
1. Login as patient
2. Go to Care Plans page (now showing Follow-Up Tasks)
3. Type a message in the chat: "I'm feeling much better today!"
4. Click Send
5. Verify you get a response from the AI
6. Backend should:
   - Call Response Analyzer Agent
   - Classify the response (ROUTINE in this case)
   - Return appropriate message

**Test Different Response Types:**

**Routine Response:**
```
Message: "I took my medication today"
Expected Classification: ROUTINE
Expected AI Response: "Thank you for the update! I've recorded this. Keep up the good work with your recovery tasks."
```

**Concern Response:**
```
Message: "I'm having trouble sleeping"
Expected Classification: CONCERN
Expected AI Response: "Thank you for letting me know. I've updated your care team about your concerns. They will review this and may adjust your follow-up plan."
```

**Urgent Response:**
```
Message: "I'm having chest pain"
Expected Classification: URGENT
Expected AI Response: "I've detected this is urgent. Your care team has been notified and we're arranging support for you. Please wait for further instructions."
```

**Expected Backend API Calls:**
```bash
POST http://localhost:8000/api/v1/patients/{patient_id}/care-plan-response
Authorization: Bearer {patient_token}
Content-Type: application/json

{
  "patient_response": "I'm feeling much better today!"
}
```

**Expected Results:**
- ✅ Patient can submit responses
- ✅ Response is analyzed and classified
- ✅ Care plan is updated (invisible to patient)
- ✅ Patient receives appropriate feedback
- ✅ Care manager can see the response and classification

---

### Scenario 4: Verify Access Restrictions

**Test Patient Access to Care Plan Endpoints:**

```bash
# Should all return 403 Forbidden

# Test 1: My care plan
curl -X GET "http://localhost:8000/api/v1/patient/my-care-plan" \
  -H "Authorization: Bearer {patient_token}"
# Expected: 403 Forbidden - "Patients cannot access care plans directly. Use /patients/{patient_id}/follow-up-tasks instead."

# Test 2: Care plan by MRN
curl -X GET "http://localhost:8000/api/v1/patients/MRN000015/care-plan" \
  -H "Authorization: Bearer {patient_token}"
# Expected: 403 Forbidden - "Patients cannot access care plans. Use /patients/{patient_id}/follow-up-tasks instead."

# Test 3: Care plan by ID
curl -X GET "http://localhost:8000/api/v1/care-plans/PLAN_123456/care-plan" \
  -H "Authorization: Bearer {patient_token}"
# Expected: 403 Forbidden - "Patients cannot access care plans. Use /patients/{patient_id}/follow-up-tasks instead."
```

**Test Care Manager Access:**

```bash
# Should all return 200 OK

# Test 1: Care plan by MRN
curl -X GET "http://localhost:8000/api/v1/patients/MRN000015/care-plan" \
  -H "Authorization: Bearer {care_manager_token}"
# Expected: 200 OK - Returns full care plan with all details

# Test 2: Care plan by ID
curl -X GET "http://localhost:8000/api/v1/care-plans/PLAN_123456/care-plan" \
  -H "Authorization: Bearer {care_manager_token}"
# Expected: 200 OK - Returns full care plan with all details
```

---

## Database Verification

### Check Follow-Up Tasks
```sql
-- Connect to database
/opt/homebrew/opt/postgresql@18/bin/psql -U vishwa -d carepath_db

-- View follow-up tasks for a patient
SELECT 
    fc.id,
    fc.checkin_type,
    fc.checkin_message,
    fc.status,
    fc.patient_response,
    fc.classification,
    fc.scheduled_at,
    cp.mrn
FROM follow_up_checkins fc
JOIN care_plans cp ON fc.care_plan_id = cp.id
WHERE cp.mrn = 'MRN000015'
ORDER BY fc.created_at DESC;
```

### Check Care Plans (Should not be visible to patients)
```sql
-- View care plan with clinical details
SELECT 
    id,
    mrn,
    risk_level,
    intensity,
    status,
    doctor_instructions,
    clinical_notes,
    created_at
FROM care_plans
WHERE mrn = 'MRN000015'
AND status = 'ACTIVE';
```

### Check Patient Responses
```sql
-- View patient responses with classifications
SELECT 
    fc.patient_response,
    fc.classification,
    fc.response_received_at,
    cp.mrn
FROM follow_up_checkins fc
JOIN care_plans cp ON fc.care_plan_id = cp.id
WHERE fc.patient_response IS NOT NULL
ORDER BY fc.response_received_at DESC
LIMIT 10;
```

---

## Troubleshooting

### Issue: Patient sees care plan details
**Check:**
- Verify App.tsx is using FollowUpTasks component for `/care-plans` route
- Check browser cache - clear and reload
- Verify frontend build is up to date: `npm run dev` (restart if needed)

### Issue: 403 errors for patients on follow-up tasks
**Check:**
- Ensure endpoint is `/patients/{patient_id}/follow-up-tasks` (not `/patient/care-plan`)
- Verify patient token is valid: `GET /api/v1/auth/me`
- Check patient_id matches in URL and token

### Issue: Care manager cannot see care plans
**Check:**
- Verify care manager is logged in (not patient)
- Check role in token: Should be "CARE_MANAGER" not "PATIENT"
- Verify MRN is correct
- Check if care plan exists: Query database

### Issue: Patient responses not triggering agents
**Check:**
- Backend logs for agent execution
- Verify post_care orchestrator is running
- Check database for patient_response and classification
- Verify patient_response endpoint is being called: `/patients/{patient_id}/care-plan-response`

---

## Success Criteria

✅ **Patients:**
- Can access `/care-plans` and see "My Follow-Up Tasks"
- Can see follow-up tasks (pending and completed)
- Can chat with care team
- Can mark tasks as complete
- CANNOT access care plan endpoints (403 errors)
- CANNOT see risk level, intensity, clinical notes

✅ **Care Managers:**
- Can access Post Discharge page
- Can generate care plans
- Can see full care plan details
- Can view patient responses and classifications
- Can access all care plan endpoints

✅ **Agent Flow:**
- Patient response → Response Analyzer → Classification
- URGENT/CONCERN → Care Continuity → Care plan update
- New follow-up tasks created
- Patient sees new tasks (not the care plan changes)

---

## Browser Test Checklist

### Patient View
- [ ] Login as patient
- [ ] Navigate to "Care Plans" from sidebar
- [ ] See "My Follow-Up Tasks" heading
- [ ] See pending tasks section
- [ ] See completed tasks section
- [ ] See chat interface at bottom
- [ ] Type and send a message
- [ ] Receive AI response
- [ ] Task appears in pending section (if new task created)
- [ ] Can mark task as complete
- [ ] Task moves to completed section
- [ ] NO risk level visible
- [ ] NO intensity visible
- [ ] NO clinical notes visible
- [ ] NO doctor instructions visible

### Care Manager View
- [ ] Login as care manager
- [ ] Navigate to "Post Discharge" page
- [ ] See list of patients
- [ ] Select a patient
- [ ] See "Generate Care Plan" button (if not generated)
- [ ] Click "Generate Care Plan"
- [ ] Wait for generation (see loading state)
- [ ] See care plan details appear:
  - [ ] Risk Level badge (HIGH/MODERATE/LOW)
  - [ ] Intensity (INTENSIVE/REGULAR/BASIC)
  - [ ] Clinical Notes
  - [ ] Doctor Instructions
  - [ ] Care Plan Tasks list
  - [ ] Follow-up Check-ins section
  - [ ] Patient Responses (if any)

---

**Test Date**: 2026-08-22
**Status**: Ready for testing
**Version**: v1.0 - Care Plan Access Separation
