# Post-Care Agent Integration Analysis

## Executive Summary

**STATUS: NOT INTEGRATED ❌**

The actual `post_care` agent system is a **standalone LangGraph-based agentic orchestrator** that is **completely separate** from the current CarePath backend integration. What we've implemented so far is a **simplified mock** that mimics the post-care agents' output structure but lacks the actual LLM-orchestrated workflow.

---

## Current State Comparison

### What We Built (Simplified Mock)

| Component | Location | Type | Status |
|-----------|----------|------|--------|
| **Service Layer** | `app/care_manager/post_discharge/service.py` | Deterministic Python functions | ✅ Working |
| **Streaming Service** | `app/services/care_plan_streaming_service.py` | Simulated agent streaming | ✅ Complete |
| **API Endpoints** | `app/api/v1/endpoints/care_plan_generation.py` | SSE streaming | ✅ Complete |
| **Frontend** | `src/components/CareplanGenerationModal.tsx` | React modal with SSE | ✅ Complete |
| **Database** | PostgreSQL `carepath_db` | Basic tables | ✅ Working |

**What it does:**
- Returns fake agent-like responses from deterministic functions
- Shows animated agent progress in the UI
- Stores basic care plan data
- **Does NOT use LLM orchestration**
- **Does NOT use LangGraph state machine**
- **Does NOT call the real 4-agent system**

---

### What Actually Exists (Real Post-Care Agent)

| Component | Location | Type | Status |
|-----------|----------|------|--------|
| **LangGraph Orchestrator** | `post_care/orchestrator/agentic_graph_builder.py` | LangGraph StateGraph | ✅ Implemented |
| **4 Specialized Agents** | `post_care/agents/` | LLM + deterministic hybrids | ✅ Implemented |
| **NVIDIA Orchestrator LLM** | `post_care/orchestrator/agentic_orchestrator_node.py` | Nemotron 30B | ✅ Configured |
| **Groq Agent LLMs** | `post_care/llm/` | GPT-OSS 120B fallback chain | ✅ Configured |
| **Database Layer** | `post_care/database/` | PostgreSQL with repositories | ✅ Implemented |
| **Appointment Integration** | `post_care/agents/appointment/` | Placeholder (empty) | ❌ NOT IMPLEMENTED |

**What it does:**
- **LLM-orchestrated workflow** using NVIDIA Nemotron as the "brain" that decides which agent to call next
- **4 real agents** with actual LLM reasoning (Care Plan, Follow-Up, Response Analyzer, Care Continuity)
- **LangGraph state machine** with guardrails, routing, and stopping conditions
- **PostgreSQL persistence** with proper schema (care_plans, care_plan_tasks, follow_up_checkins)
- **Doctor instruction extraction** using Groq LLM from discharge notes
- **Patient response NLP analysis** using Groq LLM for classification (NORMAL/CONCERN/URGENT)
- **Real medical logic** with risk stratification based on vitals, labs, comorbidities

**What it does NOT do:**
- No integration with main CarePath backend
- No REST API endpoints exposed
- No connection to the care manager frontend
- No appointment agent integration (placeholder exists)

---

## Architecture Mismatch

### Current "Mock" Architecture

```
Frontend (React)
    │
    │ POST /care-manager/patients/{id}/generate-care-plan-stream
    │
    ▼
Backend FastAPI (app/)
    │
    ├─ care_plan_streaming_service.py (FAKE STREAMING)
    │      │
    │      ├─ Simulates agent 1: Care Plan ← NOT REAL
    │      ├─ Simulates agent 2: Follow-Up ← NOT REAL
    │      ├─ Simulates agent 3: Response Analyzer ← NOT REAL
    │      └─ Simulates agent 4: Appointment ← NOT REAL
    │
    └─ app/care_manager/post_discharge/service.py (DETERMINISTIC)
           │
           └─ Simple Python functions returning hardcoded data
```

### Real Post-Care Architecture

```
Entry Point: run_agentic_workflow(mrn, prediction, probability, notes)
    │
    ▼
LangGraph StateGraph (orchestrator/)
    │
    ├─ START → orchestrator_llm_node (NVIDIA Nemotron LLM)
    │      │
    │      ├─ LLM decides: "Call care_plan_agent"
    │      │
    │      ▼
    ├─ tool_executor_node
    │      │
    │      ├─ Executes: agents/care_plan/agent.py
    │      │      │
    │      │      ├─ PostgreSQL: SELECT * FROM patient_ehr WHERE mrn = ?
    │      │      ├─ Risk classification (deterministic thresholds)
    │      │      ├─ Groq LLM: Extract doctor instructions from notes
    │      │      ├─ Groq LLM: Personalize task descriptions
    │      │      ├─ PostgreSQL: INSERT INTO care_plans + care_plan_tasks
    │      │      └─ Returns: CarePlanOutput(care_plan_id, risk_level, tasks[])
    │      │
    │      └─ Update state["care_plan"] = output
    │
    ├─ route_after_tool_execution (ROUTING LOGIC)
    │      │
    │      ├─ Check stopping condition
    │      ├─ Apply guardrails (which tools available next?)
    │      └─ Decide: orchestrator_llm (loop) OR wait_for_response OR complete
    │
    ├─ orchestrator_llm_node (LOOP BACK)
    │      │
    │      ├─ LLM sees: state["care_plan"] exists
    │      ├─ Available tools: call_follow_up_agent, call_response_analyzer...
    │      ├─ LLM decides: "Call follow_up_agent"
    │      │
    │      ▼
    ├─ tool_executor_node
    │      │
    │      ├─ Executes: agents/follow_up/agent.py
    │      │      │
    │      │      ├─ PostgreSQL: SELECT tasks FROM care_plan_tasks WHERE care_plan_id = ?
    │      │      ├─ Find next PENDING task
    │      │      ├─ PostgreSQL: INSERT INTO follow_up_checkins (task_id, status='SCHEDULED')
    │      │      └─ Returns: FollowUpOutput(task_id, checkin_id, next_action)
    │      │
    │      └─ Update state["follow_up_output"] = output
    │
    ├─ route_after_tool_execution
    │      │
    │      ├─ Patient response needed? YES
    │      └─ Route to: wait_for_response
    │
    ├─ wait_for_response_node (TERMINAL INPUT OR TELEGRAM)
    │      │
    │      ├─ Terminal: input("Patient response: ")
    │      ├─ Or: Wait for Telegram webhook
    │      └─ Update state["patient_response"] = "I have chest pain..."
    │
    ├─ orchestrator_llm_node (LOOP BACK AFTER RESPONSE)
    │      │
    │      ├─ LLM sees: patient_response exists
    │      ├─ LLM decides: "Call response_analyzer"
    │      │
    │      ▼
    ├─ tool_executor_node
    │      │
    │      ├─ Executes: agents/response_analyzer/agent.py
    │      │      │
    │      │      ├─ Groq LLM: Classify response (NORMAL/CONCERN/URGENT/UNCLEAR)
    │      │      ├─ Extract symptoms, concerns, confidence
    │      │      └─ Returns: ResponseAnalyzerOutput(classification, symptoms[], concerns[])
    │      │
    │      └─ Update state["response_analyzer_output"] = output
    │
    ├─ orchestrator_llm_node (FINAL LOOP)
    │      │
    │      ├─ LLM sees: response classification exists
    │      ├─ LLM decides: "Call care_continuity"
    │      │
    │      ▼
    ├─ tool_executor_node
    │      │
    │      ├─ Executes: agents/care_continuity/agent.py
    │      │      │
    │      │      ├─ Deterministic mapping:
    │      │      │   NORMAL → CONTINUE_FOLLOW_UP
    │      │      │   CONCERN → CLINICAL_REVIEW
    │      │      │   URGENT → URGENT_REVIEW
    │      │      │   UNCLEAR → CLARIFICATION_REQUIRED
    │      │      │
    │      │      └─ Returns: CareContinuityOutput(continuity_action, requires_appointment=False)
    │      │
    │      └─ Update state["continuity_action"] = output
    │
    └─ route_after_tool_execution
           │
           ├─ Stopping condition met (continuity_action set)
           └─ Route to: complete_node → END
```

---

## The 4 Agents (Real Implementation)

### Agent 1: Care Plan Agent

**File:** `post_care/agents/care_plan/agent.py`

**LLM Usage:**
- **Groq `openai/gpt-oss-120b`** for extracting doctor instructions from discharge notes
- **Groq `openai/gpt-oss-120b`** for personalizing task descriptions

**Process:**
1. Look up patient in `patient_ehr` table by MRN
2. Classify risk based on `probability`:
   - ≥ 0.80 → HIGH/INTENSIVE
   - ≥ 0.50 → MODERATE/REGULAR
   - < 0.50 → LOW/BASIC
3. Check for existing ACTIVE care plan (reuse if found)
4. Generate tasks based on risk level and chronic conditions (deterministic pathways)
5. Extract doctor instructions from notes using Groq LLM
6. Personalize task descriptions using Groq LLM
7. Store in `care_plans` + `care_plan_tasks` tables

**Output:**
```python
CarePlanOutput(
    mrn="MRN000015",
    patient_id="11",
    care_plan_id="CP-0AEB878E",  # Generated UUID
    risk_level="HIGH",           # Based on probability
    intensity="INTENSIVE",
    status="ACTIVE",
    doctor_instructions="Follow-up: Wound-care...",  # LLM extracted
    tasks=[
        CareTask(task_id="T-...", task_type="FREQUENT_CHECKINS", ...),
        CareTask(task_id="T-...", task_type="MEDICATION_REVIEW", ...),
        ...
    ]
)
```

---

### Agent 2: Follow-Up Agent

**File:** `post_care/agents/follow_up/agent.py`

**LLM Usage:** None (100% deterministic)

**Process:**
1. Verify ACTIVE care plan exists
2. Query `care_plan_tasks` for task statuses
3. Find next actionable task (PENDING or IN_PROGRESS)
4. Create or reuse check-in record in `follow_up_checkins` table
5. Generate check-in message

**Output:**
```python
FollowUpOutput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    next_action="SCHEDULE_CHECKIN",
    follow_up={
        "task_id": "T-9640CAAC",
        "task_type": "FREQUENT_CHECKINS",
        "checkin_id": "CHK-998DC412",  # Generated UUID
        "checkin_status": "SCHEDULED",
        "message": "Follow-up: Frequent patient check-ins."
    }
)
```

---

### Agent 3: Response Analyzer

**File:** `post_care/agents/response_analyzer/agent.py`

**LLM Usage:**
- **Groq `openai/gpt-oss-120b`** for NLP classification of patient responses

**Process:**
1. Call Groq LLM with structured prompt containing patient response
2. LLM classifies: NORMAL | CONCERN | URGENT | UNCLEAR
3. Extract symptoms, concerns, sentiment
4. Return confidence score

**Prompt Example:**
```
You are a medical response classifier...

Patient response: "I have been feeling chest tightness..."

Classify as: NORMAL, CONCERN, URGENT, or UNCLEAR
Extract: symptoms, concerns, sentiment
Provide: confidence score (0.0-1.0)
```

**Output:**
```python
ResponseAnalyzerOutput(
    classification="URGENT",
    confidence=0.9,
    summary="Patient reports chest tightness and shortness of breath...",
    symptoms=["chest tightness", "shortness of breath", "elevated blood pressure"],
    concerns=["chest tightness", "shortness of breath", "elevated blood pressure"],
    patient_sentiment="negative"
)
```

---

### Agent 4: Care Continuity Agent

**File:** `post_care/agents/care_continuity/agent.py`

**LLM Usage:** None (100% deterministic mapping)

**Process:**
1. Receive classification from Response Analyzer
2. Map to continuity action (hardcoded rules):
   - NORMAL → CONTINUE_FOLLOW_UP
   - CONCERN → CLINICAL_REVIEW (requires_human_review=True)
   - URGENT → URGENT_REVIEW (requires_human_review=True)
   - UNCLEAR → CLARIFICATION_REQUIRED
3. Set `requires_appointment=False` (hardcoded, designed as integration point)

**Output:**
```python
CareContinuityOutput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    classification="URGENT",
    continuity_action="URGENT_REVIEW",
    reason="Patient response contains potentially urgent symptoms...",
    requires_human_review=True,
    requires_appointment=False  # ← INTEGRATION POINT (currently disabled)
)
```

---

## Database Schema Differences

### Current Tables (Mock System)

```sql
-- App's simple post_discharge_status table
CREATE TABLE post_discharge_status (
    id VARCHAR PRIMARY KEY,
    patient_id VARCHAR NOT NULL,
    care_plan JSONB,      -- Flat JSON storage
    follow_up JSONB,      -- Flat JSON storage
    response_analyser JSONB,
    appointment JSONB,
    updated_at TIMESTAMP
);
```

### Real Post-Care Tables

```sql
-- Properly normalized schema

-- 1. Care Plans
CREATE TABLE care_plans (
    id VARCHAR(255) PRIMARY KEY,        -- CP-{UUID}
    mrn VARCHAR(50) NOT NULL,
    patient_id BIGINT NOT NULL,
    risk_level VARCHAR(50) NOT NULL     -- HIGH | MODERATE | LOW
        CHECK (risk_level IN ('HIGH', 'MODERATE', 'LOW')),
    intensity VARCHAR(50) NOT NULL      -- INTENSIVE | REGULAR | BASIC
        CHECK (intensity IN ('INTENSIVE', 'REGULAR', 'BASIC')),
    status VARCHAR(50) NOT NULL         -- ACTIVE | COMPLETED | EXPIRED
        CHECK (status IN ('ACTIVE', 'COMPLETED', 'EXPIRED')),
    doctor_instructions TEXT,           -- LLM-extracted instructions
    clinical_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patient_ehr(id)
);

-- 2. Care Plan Tasks (normalized, not JSONB)
CREATE TABLE care_plan_tasks (
    id VARCHAR(255) PRIMARY KEY,        -- T-{UUID}
    care_plan_id VARCHAR(255) NOT NULL,
    task_type VARCHAR(100) NOT NULL     -- FREQUENT_CHECKINS | MEDICATION_REVIEW | ...
        CHECK (task_type IN (
            'FREQUENT_CHECKINS', 'MEDICATION_REVIEW', 'VITALS_MONITORING',
            'LABS_MONITORING', 'EDUCATION', 'LIFESTYLE', 'FOLLOWUP_APPOINTMENT'
        )),
    task_description TEXT NOT NULL,
    task_details JSONB,
    priority VARCHAR(20) DEFAULT 'MEDIUM'
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')),
    status VARCHAR(50) DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED')),
    scheduled_date DATE,
    completed_date DATE,
    assigned_to VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (care_plan_id) REFERENCES care_plans(id)
);

-- 3. Follow-Up Check-ins
CREATE TABLE follow_up_checkins (
    id VARCHAR(255) PRIMARY KEY,        -- CHK-{UUID}
    care_plan_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    checkin_type VARCHAR(100),
    checkin_message TEXT,
    patient_response TEXT,              -- Actual patient text (for NLP)
    response_received_at TIMESTAMP,
    classification VARCHAR(50)          -- NORMAL | CONCERN | URGENT | UNCLEAR
        CHECK (classification IS NULL OR classification IN (
            'NORMAL', 'CONCERN', 'URGENT', 'UNCLEAR'
        )),
    status VARCHAR(50) DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'SENT', 'RESPONDED', 'COMPLETED', 'SKIPPED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (care_plan_id) REFERENCES care_plans(id),
    FOREIGN KEY (task_id) REFERENCES care_plan_tasks(id)
);

-- 4. Patient EHR (already exists, 60+ columns)
-- Used by Care Plan Agent for risk classification
```

---

## Integration Gap Analysis

### What Needs to Happen

| # | Task | Current | Target | Complexity |
|---|------|---------|--------|------------|
| 1 | **Replace mock with real orchestrator** | Fake streaming service | Call `run_agentic_workflow()` | 🔴 HIGH |
| 2 | **Expose POST-care as API** | Standalone Python module | FastAPI endpoints | 🟡 MEDIUM |
| 3 | **Real-time streaming adapter** | SSE simulation | Capture LangGraph intermediate states | 🔴 HIGH |
| 4 | **Database migration** | Flat JSONB `post_discharge_status` | Normalized `care_plans` + `care_plan_tasks` + `follow_up_checkins` | 🟡 MEDIUM |
| 5 | **LLM configuration** | None | NVIDIA API key + Groq API key | 🟢 LOW |
| 6 | **Appointment agent integration** | Placeholder | Connect to shared appointment agent | 🔴 HIGH |
| 7 | **Notification system integration** | Mock notifications | Connect to real notification service | 🟡 MEDIUM |
| 8 | **Frontend state management** | Simple phases | Handle async resumption (patient response wait) | 🟡 MEDIUM |

---

## Integration Options

### Option 1: Full Integration (Recommended but Complex)

**Approach:** Expose the real `post_care` orchestrator as a FastAPI service and replace the mock.

**Steps:**
1. Create new FastAPI router: `/api/v1/post-care/workflow`
2. Add endpoint: `POST /workflow/start` → calls `run_agentic_workflow()`
3. Add endpoint: `POST /workflow/{workflow_id}/continue` → resumes with patient response
4. Implement SSE adapter that captures LangGraph state changes in real-time
5. Migrate database schema (add `care_plans`, `care_plan_tasks`, `follow_up_checkins`)
6. Update frontend to handle async resumption (patient response wait state)
7. Configure NVIDIA + Groq API keys

**Pros:**
- Get the actual agentic system with LLM orchestration
- Real medical logic with risk stratification
- Real NLP analysis of patient responses
- Proper doctor instruction extraction
- Extensible for appointment agent integration

**Cons:**
- High complexity (LangGraph → SSE streaming is non-trivial)
- Requires LLM API keys and costs
- Database migration needed
- Frontend needs to handle async resumption

**Estimated Effort:** 2-3 weeks

---

### Option 2: Simplified Integration (Pragmatic)

**Approach:** Keep the current mock structure but add **selective real agent calls** where it matters most.

**Steps:**
1. Keep streaming service mock
2. Replace **Response Analyzer** step with real Groq LLM call
3. Replace **Care Plan Agent** with real risk classification logic
4. Keep Follow-Up and Care Continuity as deterministic
5. Add minimal database fields for risk_level and classification

**Pros:**
- Get real LLM-powered response analysis (the most valuable part)
- Get real risk stratification
- Lower complexity
- No LangGraph learning curve
- Frontend stays the same

**Cons:**
- Not the true agentic orchestrator
- No LLM-based tool selection
- Missing some advanced features (doctor instruction extraction, task personalization)

**Estimated Effort:** 3-5 days

---

### Option 3: Parallel System (Hybrid)

**Approach:** Keep the current mock for UI demo, run the **real orchestrator in parallel** for backend processing.

**Steps:**
1. Keep current `/generate-care-plan-stream` as-is (for UI demo)
2. Add background job that calls real `run_agentic_workflow()` asynchronously
3. Store real orchestrator results in separate tables
4. Add comparison endpoint for testing accuracy

**Pros:**
- No disruption to current frontend
- Can A/B test mock vs real
- Real orchestrator runs in production (for data collection)
- Low risk

**Cons:**
- Duplicate systems
- Confusing architecture
- Requires eventual migration

**Estimated Effort:** 1 week

---

## Recommendation

**Go with Option 2 (Simplified Integration)** for the following reasons:

1. **User value:** Real response analysis (URGENT/CONCERN/NORMAL) is the most impactful feature
2. **Time constraint:** Full LangGraph integration is a multi-week project
3. **Risk mitigation:** Lower complexity means fewer bugs
4. **Iterative approach:** Can upgrade to Option 1 later if needed

### Implementation Plan for Option 2

**Phase 1: Response Analyzer Integration (Day 1-2)**
- Import Groq client from `post_care/llm/`
- Replace mock response analysis with real LLM call
- Test with real patient responses

**Phase 2: Risk Classification Integration (Day 2-3)**
- Import risk classification logic from `post_care/agents/care_plan/agent.py`
- Replace mock risk levels with real threshold-based logic
- Add `patient_ehr` table lookup

**Phase 3: Database Schema Enhancement (Day 3-4)**
- Add `risk_score`, `risk_level`, `classification`, `confidence` columns to existing tables
- Migrate existing data

**Phase 4: Testing & Refinement (Day 4-5)**
- Test with real discharge scenarios
- Tune LLM prompts
- Add error handling

---

## Next Steps

1. **Decision:** Which integration option?
2. **API Keys:** Obtain NVIDIA and Groq API keys if going with LLM integration
3. **Database:** Decide on schema migration approach (full vs minimal)
4. **Timeline:** Set realistic expectations with stakeholders
5. **Testing:** Identify test patients for pilot

---

## Questions for Discussion

1. Do we need the full LangGraph orchestrator, or is the simplified version sufficient?
2. What's the budget for LLM API calls? (Groq is cheaper than NVIDIA)
3. How important is the "doctor instruction extraction" feature?
4. Should the appointment agent integration happen now or later?
5. What's the priority: feature completeness vs time to production?

---

**Document Version:** 1.0  
**Date:** 2026-08-22  
**Author:** System Analysis
