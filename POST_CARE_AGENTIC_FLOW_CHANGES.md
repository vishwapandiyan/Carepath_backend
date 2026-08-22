# Post-Care Agentic Flow — Changes, Database, and Integration Guide

## 1. What Changed in the Agentic Flow

### Before (Old Flow)
```
Care Plan Agent
    ↓
Follow-Up Agent
    ↓
WAIT FOR PATIENT (blocking — input() / simulated response)
    ↓
Response Analyzer
    ↓
Care Continuity
    ↓
END
```
- The workflow blocked waiting for patient input
- In non-interactive mode, it simulated a fake patient response
- The entire pipeline ran as one monolithic execution
- No appointment integration
- `requires_appointment` was always `False`

### After (New Flow — Split Architecture)

**PHASE 1: Initial Graph (Non-blocking, LLM-orchestrated)**
```
START
    ↓
NVIDIA LLM Orchestrator decides → call_care_plan_agent
    ↓
Tool Executor → Care Plan Agent → PostgreSQL
    ↓
State: care_plan_id = CP-0AEB878E, risk_level = HIGH
    ↓
NVIDIA LLM Orchestrator decides → call_follow_up_agent
    ↓
Tool Executor → Follow-Up Agent → PostgreSQL
    ↓
State: task_id, checkin_id persisted
    ↓
Graph routing: follow_up done + no patient_response → COMPLETE
    ↓
Notification trigger
    ↓
END (workflow does NOT wait)
```

**PHASE 2: Async Patient Response (Independent, hours/days later)**
```
Patient responds to notification
    ↓
POST /patients/{patient_id}/care-plan-response
    ↓
Load context from PostgreSQL (MRN → care_plan → task → check-in)
    ↓
Response Analyzer (Groq LLM)
    ↓
Care Continuity (deterministic routing)
    ↓
├── NORMAL → CONTINUE_FOLLOW_UP (no action needed)
├── CONCERN → CLINICAL_REVIEW → revise care plan → new follow-up task
└── URGENT → URGENT_REVIEW → revise + Appointment Handoff
                                    ↓
                              source = POST_CARE
                              destination = SPECIALIST
                              specialty = CARDIOLOGY
                                    ↓
                        Shared Appointment Agent
                                    ↓
                        Provider Discovery → Availability
                                    ↓
                        STOP (booking requires external service)
```

### Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Graph does NOT wait for patient | Patient may respond hours/days later |
| PostgreSQL is the persistence boundary | Graph state is ephemeral; DB state survives process restarts |
| Patient response is a separate API call | Decouples initial setup from async patient interaction |
| Same care_plan_id preserved always | No duplicate plans; revision adds to existing plan |
| Source-aware Appointment Agent | Same agent handles PATIENT and POST_CARE flows |

---

## 2. Database — What Is Used Now

### Database: `carepath_db`
- **Host:** localhost
- **Port:** 5432
- **User:** subitsha (local dev) / configured via `DB_USER` env var
- **Driver:** psycopg2 (synchronous) for Post-care agents
- **Connection file:** `post_care/database/connection.py`

### Tables Used by Post-Care

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `patient_ehr` | Patient demographics + clinical data | `mrn` (unique), `patient_id`, clinical fields |
| `care_plans` | Agent-generated care plans | `care_plan_id` (varchar PK), `mrn`, `risk_level`, `intensity`, `status`, `doctor_instructions` |
| `care_plan_tasks` | Tasks under each plan | `task_id` (varchar), `care_plan_id` (FK), `task_type`, `status`, `description`, `doctor_instruction` |
| `follow_up_checkins` | Patient check-in records | `checkin_id` (varchar), `task_id` (FK), `status`, `message`, `response`, `response_received_at` |
| `appointment_sessions` | Appointment workflow state | `session_id`, `mrn`, `destination`, `specialty`, `source`, `care_plan_id`, `workflow_stage`, `conversation_state` (JSONB) |
| `appointment_providers` | Provider directory | `provider_id`, `provider_name`, `destination`, `specialty`, `address`, `latitude`, `longitude` |
| `provider_slots` | Available appointment slots | `slot_id`, `provider_id`, `start_time`, `end_time`, `status` |

### Relationship Chain
```
patient_ehr.mrn
    ↓
care_plans.mrn (status='ACTIVE')
    ↓
care_plan_tasks.care_plan_id
    ↓
follow_up_checkins.task_id
    ↓
appointment_sessions.care_plan_id + mrn (source='POST_CARE')
```

---

## 3. Mock/Test Appointment Data (Current)

### Synthetic Test Provider

| Field | Value | Notes |
|-------|-------|-------|
| `provider_id` | `TEST-CARDIO-001` | Clearly marked as test data |
| `provider_name` | `Test Cardiology Center` | Synthetic |
| `destination` | `SPECIALIST` | |
| `specialty` | `CARDIOLOGY` | |
| `address` | `Test Medical Center, 100 Health Ave, Chennai` | Synthetic |
| `latitude` | `13.085` | Near test patient location |
| `longitude` | `80.275` | Near test patient location |
| `active` | `true` | |

### Synthetic Test Slots

| Slot ID | Provider | Time | Purpose |
|---------|----------|------|---------|
| `slot_test_cardio_same_day_001` | TEST-CARDIO-001 | Today +2h | SAME_DAY testing |
| `slot_test_cardio_week_001` | TEST-CARDIO-001 | Tomorrow 9AM | THIS_WEEK testing |
| `slot_test_cardio_week_002` | TEST-CARDIO-001 | Day 3, 10AM | THIS_WEEK testing |
| `slot_test_cardio_week_003` | TEST-CARDIO-001 | Day 4, 2PM | THIS_WEEK testing |
| `slot_test_cardio_routine_001` | TEST-CARDIO-001 | Day 7, 11AM | ROUTINE testing |
| `slot_test_cardio_routine_002` | TEST-CARDIO-001 | Day 10, 3PM | ROUTINE testing |

### Database Schema Changes for Test Data

Added 3 columns to `appointment_providers` (did not exist before):
```sql
ALTER TABLE appointment_providers ADD COLUMN IF NOT EXISTS address VARCHAR(500);
ALTER TABLE appointment_providers ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE appointment_providers ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
```

These columns are required by the Appointment Agent's `search_nearby_providers()` SQL query.

---

## 4. What Should Be Used in Production (Full Backend Integration)

### Remove/Replace Test Data

| Current (Test) | Production (Real) |
|----------------|-------------------|
| `TEST-CARDIO-001` | Real provider IDs from OSM or hospital directory |
| Synthetic lat/lon | Real provider coordinates |
| Synthetic slots | Real availability from scheduling system |
| `carepath_db` (local) | Shared team database (same PostgreSQL, aligned config) |

### Database Configuration for Production

The main backend uses:
```
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/<dbname>
```

Post-care needs to point to the **same database**. Set in `.env`:
```
DB_HOST=<same host>
DB_PORT=5432
DB_NAME=<same database name>
DB_USER=<same user>
DB_PASSWORD=<same password>
```

### Provider Data in Production

The `appointment_providers` table should be populated with:
- Real healthcare providers from hospital partnerships
- Verified coordinates (geocoded from addresses)
- Correct `destination` and `specialty` classifications
- `active` flag managed by admin

The `provider_slots` table should be:
- Populated by the external Appointment Service (your teammate's microservice)
- OR synchronized from a hospital scheduling system
- Slots should have real future dates/times
- Status managed: AVAILABLE → BOOKED when confirmed

### Appointment Booking Service

**Currently:** The booking step calls `http://localhost:8001/appointments/book` — an external microservice that is NOT in this codebase.

**For production:**
1. Your teammate's Shared Appointment Agent microservice must be running
2. Set `APPOINTMENT_AGENT_BASE_URL` in the alternate_care config to point to it
3. The booking service handles:
   - Receiving `{actor, patient_id, request: {intent: "BOOK_APPOINTMENT", provider_id, slot_id, specialty}}`
   - Validating the slot is still available
   - Creating the appointment record
   - Returning `{patient_id, appointment: {appointment_id, provider_id, date, time, status: "BOOKED"}}`

### What the Team Needs to Provide

| Responsibility | Owner | Status |
|----------------|-------|--------|
| Shared Appointment Agent microservice (port 8001) | Teammate | Source not in this workspace |
| Real provider data (with lat/lon) | Team/Admin | Test data exists, real data needed |
| Real slot data | External scheduling system | Test data exists |
| Unified database config | DevOps/Team | Currently separate configs |
| Patient location (lat/lon) | Patient app / EHR | Using default Chennai coords for now |

---

## 5. Appointment Booking Feature — Integration Steps

### Current State (Verified Working)

```
Post-Care Response → URGENT
    ↓
Care Continuity → requires_appointment = true
    ↓
appointment_handoff.py
    ↓
run_appointment_agent(source="POST_CARE", destination="SPECIALIST", specialty="CARDIOLOGY")
    ↓
NVIDIA LLM tool-calling loop
    ↓
search_nearby_providers() → appointment_providers table → providers found
    ↓
check_availability() → provider_slots table → slots returned
    ↓
STOP (booking service not running)
```

### What's Needed to Complete Booking

**Step 1: Start the External Booking Service**
```bash
# On teammate's machine or shared server:
cd <shared-appointment-agent-repo>
uvicorn main:app --port 8001
```

**Step 2: Verify Connectivity**
```python
import requests
resp = requests.get("http://localhost:8001/health")
assert resp.status_code == 200
```

**Step 3: Test Booking End-to-End**
The existing code already does:
```python
# In the Appointment Agent LLM loop:
book_appointment(provider_id="TEST-CARDIO-001", slot_id="slot_test_cardio_same_day_001", patient_id="MRN000015")
    ↓
AppointmentAgentClient.book()
    ↓
POST http://localhost:8001/appointments/book
    ↓
Response: {"patient_id": "MRN000015", "appointment": {"appointment_id": "APT-xxx", "status": "BOOKED"}}
```

**Step 4: Session Update**
After booking, the `/chat` endpoint (or the handoff function) updates:
```sql
UPDATE appointment_sessions 
SET appointment_id = 'APT-xxx', 
    appointment_status = 'BOOKED',
    workflow_stage = 'BOOKED'
WHERE session_id = 'pc_...'
```

### Booking Flow Architecture

```
POST_CARE source:
    Post-care → appointment_handoff.py
        → run_appointment_agent(source="POST_CARE")
        → LLM: search_nearby_providers
        → LLM: select_provider (auto for IMMEDIATE urgency)
        → LLM: check_availability
        → LLM: select_slot (earliest for IMMEDIATE)
        → LLM: book_appointment
        → AppointmentAgentClient.book()
        → POST http://localhost:8001/appointments/book
        → appointment_id returned
        → appointment_sessions updated
        → patient notified

PATIENT source:
    /navigate → /chat (multi-turn)
        → run_appointment_agent(source="PATIENT")
        → LLM: search_nearby_providers → present to patient
        → /chat: patient selects provider
        → LLM: select_provider
        → /chat: patient asks for times
        → LLM: check_availability → present slots
        → /chat: patient picks slot
        → LLM: select_slot
        → /chat: patient confirms
        → LLM: book_appointment
        → same booking path
```

### Source-Aware Behavior Summary

| Aspect | PATIENT | POST_CARE |
|--------|---------|-----------|
| System prompt | Patient-facing, conversational | Care-management, action-oriented |
| Provider selection | Patient chooses interactively | LLM auto-selects nearest (for IMMEDIATE) |
| Slot selection | Patient picks preferred time | LLM selects earliest available |
| Booking confirmation | Requires explicit patient "yes" | Proceeds based on urgency level |
| Multi-turn | Yes (via /chat) | Can complete in 1 turn for IMMEDIATE |
| Session source | `"PATIENT"` | `"POST_CARE"` |
| care_plan_id | Not set | Set from Post-care context |

---

## 6. Files Modified During This Integration

| File | Change Summary |
|------|---------------|
| `post_care/orchestrator/agentic_graph_builder.py` | Route to `complete` after follow-up (non-blocking); updated complete_node |
| `post_care/orchestrator/agentic_guardrails.py` | care_plan_agent only available when no plan exists |
| `post_care/orchestrator/agentic_tools.py` | Probability normalization for LLM arg fix |
| `post_care/database/repositories.py` | Fixed column names (task_description→description, id→task_id/care_plan_id) |
| `post_care/agents/follow_up/tools.py` | Fixed column names in SQL queries |
| `post_care/agents/care_plan/agent.py` | Fixed update_task key names |
| `post_care/agents/care_continuity/schemas.py` | CONCERN: requires_appointment=False; URGENT: requires_appointment=True |
| `post_care/services/care_plan_service_postgresql.py` | Added `revise_care_plan()` — context-aware revision |
| `post_care/services/appointment_handoff.py` | **NEW** — Post-care → Shared Appointment Agent bridge |
| `app/api/v1/endpoints/patient_response.py` | **NEW** — Async patient response endpoint with full pipeline |
| `app/api/v1/api.py` | Registered patient_response router |
| `app/integrations/post_care_adapter.py` | Auto-notification trigger after workflow completion |
| `app/services/alternate_care/agents/appointment_agent.py` | Source-aware system prompts (PATIENT/POST_CARE); updated run_appointment_agent params |
| `app/services/alternate_care/api/routes.py` | Source logging in /chat continuation |

---

## 7. What Is NOT Yet Implemented

| Feature | Status | Blocker |
|---------|--------|---------|
| Actual appointment booking | Architecture ready, external service needed | Teammate's microservice at port 8001 |
| Urgency-based auto-booking (IMMEDIATE) | LLM prompt supports it | External service + slot availability |
| Patient notification delivery | Backend trigger exists | Frontend/Telegram integration |
| Rescheduling from Post-care | API exists, not connected | No current use case triggered |
| Cancellation from Post-care | API exists, not connected | No current use case triggered |
| Real provider data | Schema ready | Hospital directory / admin seeding |
| Patient location from EHR | Default coords used | address → geocoding service |
| Follow-up scheduler (timed) | Tasks + check-ins persist | Cron/background worker needed |
| Orchestrator graph for Phase 2 | Not needed (async pattern works) | Architectural decision: keep separate |

---

## 8. Testing Summary

| Test | Result |
|------|--------|
| Initial graph (non-blocking) | ✅ PASS |
| Care Plan creation/reuse | ✅ PASS |
| Follow-up task + check-in | ✅ PASS |
| NORMAL patient response | ✅ PASS |
| CONCERN → revision | ✅ PASS |
| URGENT → appointment handoff | ✅ PASS |
| Source-aware (PATIENT) | ✅ PASS |
| Source-aware (POST_CARE) | ✅ PASS |
| Provider discovery | ✅ PASS |
| Availability retrieval | ✅ PASS |
| MRN preservation | ✅ PASS |
| care_plan_id preservation | ✅ PASS |
| No duplicate care plans | ✅ PASS |
| No unintended booking | ✅ PASS |
| Agentic orchestration (LLM decides) | ✅ PASS |
| Actual booking via external service | ⏸ Intentionally not tested (service not available) |

---

*Document generated from verified implementation. All results based on actual code execution against `carepath_db` PostgreSQL database.*
