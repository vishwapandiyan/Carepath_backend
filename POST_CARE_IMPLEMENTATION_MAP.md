# Post-Care Implementation Map — Carepath_backend

## 1. CURRENT POST-CARE FLOW IN THE BACKEND

```
API Entry: POST /patients/{patient_id}/generate-care-plan-stream
    │  (app/api/v1/endpoints/care_plan_generation.py)
    │
    ▼ Resolves patient_id → PatientEHR → extracts mrn, clinical flags
    │ Calculates prediction + probability from EHR flags (heuristic, no ML model)
    │
    ▼ Calls: stream_real_post_care_workflow()
    │  (app/integrations/post_care_adapter.py)
    │
    ▼ Imports LangGraph from embedded: post_care/orchestrator/
    │ Builds PostCareWorkflowState, runs graph synchronously in async context
    │
    ▼ Graph executes: orchestrator_llm → tool_executor → route (loop)
    │  Agents: care_plan → follow_up → [wait_for_response] → response_analyzer → care_continuity
    │
    ▼ SSE events emitted per agent completion
    │
    ▼ If requires_appointment == True:
    │   → appointment_bridge.trigger_appointment_workflow()
    │   → Returns context for care manager review (does NOT auto-book)
    │
    ▼ Final SSE "complete" event with results
    │
    ▼ WORKFLOW ENDS
```

**CRITICAL ISSUE:** The `wait_for_response` node uses `input()` (terminal stdin). In the current streaming mode, `patient_response` is `None` so the Response Analyzer and Care Continuity never execute through the real flow. The workflow completes after Follow-Up.

---

## 2. EXACT FILES/FUNCTIONS INVOLVED

### A. Care Plan Generation (Entry Point)

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `app/api/v1/endpoints/care_plan_generation.py` | `generate_care_plan_with_stream()` | API endpoint, resolves patient, calculates risk, starts stream |
| `app/integrations/post_care_adapter.py` | `PostCareStreamingAdapter.stream_workflow()` | Creates initial state, runs LangGraph, emits SSE |
| `app/integrations/post_care_adapter.py` | `_stream_graph_states()` | Iterates graph snapshots, detects agent completions |

### B. Care Plan Agent

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/agents/care_plan/agent.py` | `run_care_plan_agent()` | Risk classification, creates/reuses care plan in DB |
| `post_care/agents/care_plan/schemas.py` | `ReadmissionInput`, `CarePlanOutput` | Input/output contracts |
| `post_care/agents/care_plan/tools.py` | `get_patient_context_tool()`, `get_care_pathway()` | Patient lookup, pathway templates |
| `post_care/services/care_plan_service_postgresql.py` | `create_care_plan()`, `get_existing_care_plan()` | PostgreSQL CRUD |
| `post_care/database/repositories.py` | `CarePlanTaskRepository` | Task CRUD |

### C. Follow-Up Agent

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/agents/follow_up/agent.py` | `orchestrate_follow_up()` | Finds pending task, creates/reuses check-in |
| `post_care/agents/follow_up/schemas.py` | `FollowUpInput`, `FollowUpOutput` | Contracts |
| `post_care/agents/follow_up/tools.py` | `get_active_care_plan()`, check-in CRUD | PostgreSQL operations |

### D. Response Analyzer

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/agents/response_analyzer/agent.py` | `orchestrate_response_analysis()` | Calls Groq LLM to classify patient response |
| `post_care/agents/response_analyzer/schemas.py` | `ResponseAnalyzerInput`, `ResponseAnalyzerOutput` | Contracts |
| `post_care/agents/response_analyzer/tools.py` | `analyze_patient_response()` | LLM prompt + parsing |

### E. Care Continuity

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/agents/care_continuity/agent.py` | `process_care_continuity()` | Deterministic routing |
| `post_care/agents/care_continuity/schemas.py` | `get_continuity_action()` | Classification → action mapping |
| `post_care/agents/care_continuity/tools.py` | `evaluate_continuity()` | Builds output from mapping |

**NOTE:** In the backend's embedded copy, `requires_appointment` is already `True` for CONCERN and URGENT.

### F. Appointment Bridge

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `app/integrations/appointment_bridge.py` | `trigger_appointment_workflow()` | Extracts patient context, determines urgency, returns recommendations |
| `app/integrations/appointment_bridge.py` | `book_appointment_from_recommendation()` | Books via alternate_care agent after care manager approval |

### G. Orchestrator

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/orchestrator/agentic_graph_builder.py` | `build_agentic_graph()`, `run_agentic_workflow()` | Builds LangGraph, runs synchronously |
| `post_care/orchestrator/agentic_orchestrator_node.py` | `orchestrator_llm_node()` | NVIDIA LLM decides next tool |
| `post_care/orchestrator/agentic_tool_executor.py` | `tool_executor_node()` | Executes tool, updates state |
| `post_care/orchestrator/agentic_guardrails.py` | `get_available_tools()`, `validate_tool_call()` | Tool availability rules |
| `post_care/orchestrator/agentic_tools.py` | `call_care_plan_agent()`, etc. | @tool wrappers |
| `post_care/orchestrator/workflow_state.py` | `PostCareWorkflowState` | TypedDict state definition |

### H. Database

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `post_care/database/connection.py` | `get_db_connection()` | Sync psycopg2 → `carepath_db` |
| `post_care/database/repositories.py` | `CarePlanTaskRepository` | Task CRUD (sync) |
| `post_care/database/appointment_repository.py` | `AppointmentSessionRepository` | Appointment session CRUD (sync) |
| `app/db/models.py` | `PostDischargeStatus` | ORM model for JSON blob (async) |
| `app/db/base.py` | `engine`, `get_db()` | Async SQLAlchemy → `ehr_db` |

### I. Notification/Patient Interaction

| File | Function/Class | What It Does Now |
|------|---------------|-----------------|
| `app/services/notification_service.py` | `generate_task_reminder()` | Creates reminder notifications for patient |
| `app/services/notification_service.py` | `mark_task_complete()` | Patient marks task done or triggers reframing |
| `app/api/v1/endpoints/care_plan_generation.py` | `send_care_plan_to_patient()` | Creates notifications for all pending tasks |
| `app/patient/router.py` | `get_my_care_plan()` | Patient reads their post-discharge status |

---

## 3. WHERE EACH NEW-FLOW RESPONSIBILITY SHOULD LIVE

### A. Care-Plan Generation
**Current location:** `post_care/agents/care_plan/agent.py` → `run_care_plan_agent()`
**Status:** ✅ Already works. Called via orchestrator.
**Needs modification:** NO (agent logic is fine)
**BUT:** The orchestrator entry point (`post_care_adapter.py`) needs to be modified to support the new flow that does NOT wait for a patient response before completing.

### B. Follow-Up Task/Check-in Generation
**Current location:** `post_care/agents/follow_up/agent.py` → `orchestrate_follow_up()`
**Status:** ✅ Already works. Creates check-in records in PostgreSQL.
**Needs modification:** YES — needs to be callable AGAIN after a care-plan modification (re-entry point).

### C. Task Scheduling/Persistence
**Current location:** `post_care/database/repositories.py` (tasks) + `follow_up_checkins` table
**Status:** ✅ Tasks and check-ins persist in PostgreSQL.
**Needs modification:** NO for storage. YES for scheduling — currently no timed scheduler exists. The `notification_service.py` creates immediate notifications but not time-delayed ones.

### D. Patient Notification Data
**Current location:** `app/services/notification_service.py` → `generate_task_reminder()`
**Status:** ⚠️ Exists but only creates notifications when care manager clicks "Send to Patient" (`send_care_plan_to_patient` endpoint).
**Needs modification:** YES — should be triggered automatically after Follow-Up Agent creates check-ins, not require manual action.

### E. Patient Optional Free-Text Response
**Current location:** DOES NOT EXIST as an API endpoint.
**Currently:** The old orchestrator has `wait_for_response` node using terminal `input()` — unusable.
**Needs to be implemented at:** New API endpoint (e.g., `POST /patients/{patient_id}/care-plan-response`) that:
1. Accepts patient free-text
2. Stores it (in check-in record or new field)
3. Triggers Response Analyzer + Care Continuity as a SEPARATE workflow run (not blocking the initial flow)

### F. Response Analyzer Invocation
**Current location:** `post_care/agents/response_analyzer/agent.py` → `orchestrate_response_analysis()`
**Status:** ✅ Agent logic works (tested with Groq LLM).
**Needs modification:** NO for the agent itself. YES for HOW it's triggered — must be invocable from a new entry point (patient response endpoint) rather than from within the wait_for_response LangGraph node.

### G. Care Continuity Decision
**Current location:** `post_care/agents/care_continuity/agent.py` → `process_care_continuity()`
**Status:** ✅ Already works. In the backend's embedded copy, `requires_appointment` is ALREADY True for CONCERN/URGENT.
**Needs modification:** NO for the agent. YES for what happens AFTER it runs (routing to appointment, care plan modification, etc.)

### H. Existing Care-Plan Modification
**Current location:** DOES NOT EXIST as a distinct operation.
**Currently:** Care Plan Agent either creates a new plan OR reuses an existing one. There is no "modify existing plan" capability.
**Needs to be implemented at:** New function in `post_care/services/care_plan_service_postgresql.py` — e.g., `modify_care_plan(care_plan_id, modifications)` that can:
- Add tasks
- Change intensity
- Update status
- Adjust scheduling

### I. Re-Running Follow-Up After Care-Plan Change
**Current location:** The Follow-Up Agent can already be called with an updated tasks list.
**Status:** ⚠️ The orchestrator currently calls it exactly once. Re-invocation requires either a new workflow run or a direct call outside the LangGraph.
**Needs modification:** YES — need a mechanism to trigger Follow-Up Agent again after care plan modification. Options:
1. Direct function call (bypass orchestrator)
2. New mini-workflow (care_plan_mod → follow_up → notify)

### J. Appointment Handoff to Shared Appointment Agent
**Current location:** `app/integrations/appointment_bridge.py` → `trigger_appointment_workflow()`
**Status:** ⚠️ PARTIALLY implemented. It:
- Extracts patient context ✅
- Determines urgency ✅
- Returns recommendations for care manager ✅
- Does NOT auto-trigger provider search ❌
- Does NOT call `run_appointment_agent()` from `alternate_care` directly ❌
**Needs modification:** YES — should call `run_appointment_agent()` (the real Shared Appointment Agent) instead of just returning context.

### K. Workflow/State Persistence
**Current location:** In-memory `PostCareWorkflowState` TypedDict (ephemeral)
**Status:** ❌ State is lost if process crashes. No resume mechanism.
**Needs to be implemented:** YES — workflow results should be persisted after each phase:
- After Care Plan: save to `post_discharge_statuses.care_plan`
- After Follow-Up: save to `post_discharge_statuses.follow_up`
- After Response Analysis: save to `post_discharge_statuses.response_analyser`
- After Care Continuity: save to `post_discharge_statuses.appointment`

---

## 4. EXISTING DATABASE TABLES/REPOSITORIES

### Backend Primary DB: `ehr_db` (async SQLAlchemy)

| Table | Used By Post-Care? | Purpose |
|-------|-------------------|---------|
| `patient_ehr` | YES | Patient lookup (mrn, clinical flags, notes) |
| `post_discharge_statuses` | YES | JSON blobs storing 4-agent results per patient |
| `users` | Indirectly | Auth + patient_id linkage |
| `readmission_predictions` | Not yet | ML predictions (could replace heuristic) |

### Embedded post_care DB: `carepath_db` (sync psycopg2)

| Table | Used By Post-Care? | Purpose |
|-------|-------------------|---------|
| `patient_ehr` | YES | Patient context for care plan agent |
| `care_plans` | YES | Normalized care plan storage |
| `care_plan_tasks` | YES | Individual tasks |
| `follow_up_checkins` | YES | Check-in records |
| `appointment_sessions` | YES | Appointment workflow state |

### CAN THE BACKEND DB STORE EVERYTHING?

**YES** — `ehr_db` can store everything if we:
1. Create `care_plans`, `care_plan_tasks`, `follow_up_checkins` tables in `ehr_db` (via migration)
2. OR switch the embedded post_care's `connection.py` to use `ehr_db` instead of `carepath_db`

The `post_discharge_statuses` table already stores JSON summaries but lacks the relational detail. For the new flow, we need BOTH:
- Relational tables (`care_plans`, `care_plan_tasks`, `follow_up_checkins`) for the agents to read/write detailed state
- `post_discharge_statuses` for the dashboard summary view

---

## 5. WHAT CAN REMAIN UNCHANGED

| Component | Status | Reason |
|-----------|--------|--------|
| Care Plan Agent logic | ✅ Keep | Risk classification + plan generation works |
| Follow-Up Agent logic | ✅ Keep | Check-in creation works |
| Response Analyzer Agent logic | ✅ Keep | Groq LLM classification works |
| Care Continuity Agent logic | ✅ Keep | Routing decision works (already has requires_appointment=True) |
| `PostCareWorkflowState` TypedDict | ✅ Keep | State schema is correct |
| Agent schemas (all 4) | ✅ Keep | Pydantic models are correct |
| Agent tools (all 4) | ✅ Keep | Tool implementations work |
| LLM clients (multi_model_fallback) | ✅ Keep | Groq/NVIDIA calls work |
| `appointment_bridge.py` urgency logic | ✅ Keep | Urgency determination is correct |
| Patient EHR model | ✅ Keep | Same table used by all |
| Notification service | ✅ Keep | Task reminder generation works |
| `mark_task_complete()` | ✅ Keep | Task completion logic works |

---

## 6. WHAT NEEDS MODIFICATION

| Component | File | Change Required |
|-----------|------|----------------|
| **Workflow entry** | `app/integrations/post_care_adapter.py` | Split into Phase 1 (care_plan + follow_up) and Phase 2 (response_analyzer + care_continuity). Phase 1 completes without waiting. Phase 2 triggered by patient response. |
| **Patient response endpoint** | NEW file needed | `POST /patients/{patient_id}/care-plan-response` — accepts free-text, triggers Phase 2 |
| **Notification trigger** | `app/api/v1/endpoints/care_plan_generation.py` | Auto-send notifications after follow-up (remove manual "Send to Patient" requirement) |
| **Appointment bridge** | `app/integrations/appointment_bridge.py` | Call `run_appointment_agent()` directly instead of just returning context |
| **Care plan modification** | `post_care/services/care_plan_service_postgresql.py` | Add `modify_care_plan()` function |
| **Re-run follow-up** | Orchestrator or direct call | Mechanism to re-trigger Follow-Up Agent after plan modification |
| **DB connection** | `post_care/database/connection.py` | Point to `ehr_db` (same DB as backend) OR create missing tables in `ehr_db` |
| **State persistence** | `app/integrations/post_care_adapter.py` | After each agent completes, update `post_discharge_statuses` |
| **wait_for_response node** | `post_care/orchestrator/agentic_graph_builder.py` | Remove terminal `input()` — workflow should complete after follow-up in Phase 1 |
| **Guardrails** | `post_care/orchestrator/agentic_guardrails.py` | If using separate phases, add appointment_agent tool |

---

## SUMMARY TABLE

| Responsibility | Where It Should Live | Currently Exists? | Needs Change? |
|---|---|---|---|
| A. Care-plan generation | `post_care/agents/care_plan/agent.py` | ✅ Yes | No |
| B. Follow-up generation | `post_care/agents/follow_up/agent.py` | ✅ Yes | No (logic), Yes (re-invocation) |
| C. Task scheduling | `post_care/database/repositories.py` + notification_service | ✅ Partial | Yes (auto-trigger) |
| D. Patient notification | `app/services/notification_service.py` | ✅ Yes | Yes (auto-trigger after follow-up) |
| E. Patient free-text response | **NEW endpoint needed** | ❌ No | Yes (create) |
| F. Response Analyzer | `post_care/agents/response_analyzer/agent.py` | ✅ Yes | No (logic), Yes (trigger mechanism) |
| G. Care Continuity | `post_care/agents/care_continuity/agent.py` | ✅ Yes | No |
| H. Care-plan modification | `post_care/services/care_plan_service_postgresql.py` | ❌ No | Yes (create) |
| I. Re-run follow-up | Direct call or mini-workflow | ❌ No | Yes (create) |
| J. Appointment handoff | `app/integrations/appointment_bridge.py` | ⚠️ Partial | Yes (call real agent) |
| K. State persistence | `app/integrations/post_care_adapter.py` | ❌ No (in-memory only) | Yes (persist per phase) |
