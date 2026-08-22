# Post-Care Agent Integration - Deployment Checklist

## Pre-Deployment Checklist

- [ ] **1. API Keys Verified**
  ```bash
  cat /Users/vishwa/Desktop/CarepathAI_backend/post_care/.env | grep -E "(NVIDIA|GROQ|OPENROUTER)_API_KEY"
  ```
  Expected: All 3 keys present and valid

- [ ] **2. Database Accessible**
  ```bash
  psql -U vishwa -d carepath_db -c "SELECT 1;"
  ```
  Expected: Returns 1

- [ ] **3. Backend Dependencies Installed**
  ```bash
  pip list | grep -E "(langgraph|langchain)"
  ```
  Expected: Shows langgraph and langchain packages

---

## Deployment Steps

### Step 1: Install Dependencies ⏳

```bash
cd /Users/vishwa/Desktop/CarepathAI_backend

# Add to requirements.txt
cat >> requirements.txt << 'EOF'

# LangGraph & LangChain for Post-Care Agent
langgraph>=0.0.30
langchain>=0.1.0
langchain-nvidia-ai-endpoints>=0.1.0
langchain-groq>=0.1.0
EOF

# Install
pip install langgraph langchain langchain-nvidia-ai-endpoints langchain-groq
```

**Verification:**
```bash
python -c "import langgraph; print('✓ LangGraph installed')"
python -c "from orchestrator.agentic_graph_builder import build_agentic_graph; print('✓ Post-care orchestrator accessible')" 2>&1 || echo "⚠️ Path issue - check sys.path"
```

- [ ] Dependencies installed successfully
- [ ] No import errors

---

### Step 2: Run Database Migrations ⏳

```bash
cd /Users/vishwa/Desktop/CarepathAI_backend/post_care/database/migrations

# Check current tables
psql -U vishwa -d carepath_db -c "\dt" | grep -E "(care_plans|care_plan_tasks|follow_up_checkins)"

# Run migrations
python run_migrations.py
```

**Expected Output:**
- `care_plans` table created
- `care_plan_tasks` table created  
- `follow_up_checkins` table created

**Verification:**
```bash
psql -U vishwa -d carepath_db -c "\d care_plans"
psql -U vishwa -d carepath_db -c "\d care_plan_tasks"
psql -U vishwa -d carepath_db -c "\d follow_up_checkins"
```

- [ ] All 3 tables exist
- [ ] No migration errors

---

### Step 3: Update Care Plan Endpoint ⏳

**File:** `/Users/vishwa/Desktop/CarepathAI_backend/app/api/v1/endpoints/care_plan_generation.py`

**Change 1 - Update Import (line ~13):**

```python
# OLD:
from app.services.care_plan_streaming_service import stream_care_plan_generation

# NEW:
from app.integrations.post_care_adapter import stream_real_post_care_workflow
```

**Change 2 - Update Function Call (line ~40-70):**

```python
# OLD:
return StreamingResponse(
    stream_care_plan_generation(patient_id, db),
    media_type="text/event-stream",
    ...
)

# NEW:
# Calculate readmission prediction
prediction = 1 if patient_ehr.prior_30_day_readmission_flag else 0

# Calculate probability based on risk factors
risk_score = 0.0
if patient_ehr.diabetes_flag:
    risk_score += 0.15
if patient_ehr.heart_failure_flag:
    risk_score += 0.20
if patient_ehr.hypertension_flag:
    risk_score += 0.10
if patient_ehr.prior_30_day_readmission_flag:
    risk_score += 0.25
if patient_ehr.icu_stay_flag:
    risk_score += 0.15

probability = min(risk_score, 1.0)

# Stream real workflow
return StreamingResponse(
    stream_real_post_care_workflow(
        patient_id=patient_id,
        mrn=patient_ehr.mrn,
        prediction=prediction,
        probability=probability,
        notes=patient_ehr.clinical_notes or "Post-discharge monitoring required"
    ),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
)
```

- [ ] Import updated
- [ ] Function call updated
- [ ] File saved

---

### Step 4: Start Backend Server ⏳

```bash
cd /Users/vishwa/Desktop/CarepathAI_backend

# Start server with verbose logging
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

**Watch for:**
- ✓ "Application startup complete"
- ✓ No import errors
- ✓ No database connection errors

- [ ] Server started successfully
- [ ] No startup errors

---

### Step 5: Test with Frontend ⏳

```bash
# In separate terminal, start frontend
cd /Users/vishwa/Desktop/CarePath_CTS
npm run dev
```

**Test Flow:**
1. Login as care manager (username: `caremanager`)
2. Navigate to Post-Discharge page
3. Click on a patient
4. Click "🤖 Generate Care Plan" button
5. Watch modal for real-time agent progress

**Expected Behavior:**
- Modal opens with animated agents
- Agent 1 (Care Plan) executes → shows risk level
- Agent 2 (Follow-Up) executes → shows check-in scheduled
- Agent 3 (Response Analyser) executes → shows classification
- Agent 4 (Care Continuity) executes → shows continuity action
- Final summary displays

- [ ] Modal opened successfully
- [ ] All 4 agents executed
- [ ] No errors in browser console
- [ ] Final summary displayed

---

### Step 6: Verify Database Persistence ⏳

```bash
# Check if care plan was created
psql -U vishwa -d carepath_db -c "SELECT id, mrn, risk_level, status FROM care_plans ORDER BY created_at DESC LIMIT 5;"

# Check tasks
psql -U vishwa -d carepath_db -c "SELECT id, care_plan_id, task_description, status FROM care_plan_tasks ORDER BY created_at DESC LIMIT 10;"

# Check check-ins
psql -U vishwa -d carepath_db -c "SELECT id, care_plan_id, checkin_message, status FROM follow_up_checkins ORDER BY created_at DESC LIMIT 5;"
```

**Expected:**
- At least 1 new care_plan row
- Multiple care_plan_tasks rows
- At least 1 follow_up_checkins row

- [ ] Care plan persisted
- [ ] Tasks persisted
- [ ] Check-ins persisted

---

### Step 7: Check Backend Logs ⏳

**Look for these log messages:**

```
✓ LangGraph built for patient {patient_id}
🔄 Node executed: orchestrator_llm
🔄 Node executed: tool_executor
✅ Care Plan Agent completed
✅ Follow-up Agent completed
✅ Response Analyser completed
✅ Care Continuity completed
```

- [ ] All log messages present
- [ ] No Python exceptions
- [ ] LLM API calls successful

---

## Post-Deployment Verification

### Functional Tests

- [ ] **Test 1: High-Risk Patient**
  - Patient with diabetes + heart failure + prior readmission
  - Expected: Risk level = HIGH, 5+ tasks created

- [ ] **Test 2: Moderate-Risk Patient**
  - Patient with hypertension only
  - Expected: Risk level = MODERATE, 3-4 tasks created

- [ ] **Test 3: Low-Risk Patient**
  - Patient with no chronic conditions
  - Expected: Risk level = LOW, 2-3 tasks created

- [ ] **Test 4: Multiple Patients**
  - Generate care plans for 3 different patients
  - Expected: All succeed, no conflicts

### Performance Tests

- [ ] **Latency Check**
  - Full workflow completes in < 30 seconds
  - No timeout errors

- [ ] **Concurrent Requests**
  - Generate 2 care plans simultaneously
  - Both complete successfully

### Data Quality Tests

- [ ] **Care Plan Content**
  - Tasks are relevant to patient conditions
  - Doctor instructions extracted correctly
  - Task descriptions are personalized

- [ ] **Database Integrity**
  - Foreign keys correct (care_plan_id links)
  - No duplicate care plans for same patient
  - Timestamps populated correctly

---

## Rollback Plan

If integration fails:

```bash
# 1. Revert endpoint changes
cd /Users/vishwa/Desktop/CarepathAI_backend
git checkout app/api/v1/endpoints/care_plan_generation.py

# 2. Remove integration files
rm -rf app/integrations/

# 3. Restart server
# Server will fall back to mock implementation
```

---

## Success Criteria

✅ **All checks passed:**
- Dependencies installed
- Database migrations complete
- Endpoint updated
- Server starts without errors
- Frontend modal works
- Database persistence verified
- Logs show LLM executions
- All 4 agents execute successfully

✅ **Ready for production use!**

---

## Support

**Issue Tracking:**
- Backend logs: `uvicorn` console output
- Frontend logs: Browser DevTools console
- Database queries: PostgreSQL logs

**Common Issues:**
1. Import errors → Check sys.path in adapter
2. Database errors → Verify migrations ran
3. LLM API errors → Check API keys in .env
4. SSE stream closes → Check for Python exceptions

---

## Timeline

- **Estimated Time:** 1-2 hours
- **Phase 1 (30 min):** Install deps + run migrations
- **Phase 2 (15 min):** Update endpoint
- **Phase 3 (30 min):** Test + verify
- **Phase 4 (15 min):** Performance tests

---

**Ready to deploy? Start with Step 1!** 🚀
