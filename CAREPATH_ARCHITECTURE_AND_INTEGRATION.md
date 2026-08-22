# CarePath Architecture & Integration Document

## 1. Document Goal

This document is the **architecture reference for connecting the Post-care Orchestrator to the Shared Appointment Agent**. It captures the current state of both systems — the CarePath Backend (patient-facing appointment flow) and the Post-care Orchestrator (clinical follow-up flow) — and defines the precise integration contract that allows Post-care to reuse the same Appointment Agent that already serves patients.

**Audience:** Engineers implementing the Post-care → Appointment Agent handoff.

**Scope:** Code-level architecture, data contracts, integration points, and implementation readiness — all derived from the actual codebase.

---

## 2. System Components

The CarePath platform consists of four distinct components that share a single PostgreSQL database:

### 2.1 CarePath Backend (`alternate_care_agent 2`)

| Property | Value |
|----------|-------|
| Type | FastAPI web service |
| Entry Point | `main.py` → `uvicorn main:app` |
| API Routes | `api/routes.py` |
| Endpoints | `POST /navigate`, `POST /chat`, `POST /appointments/availability`, `POST /appointments/book`, `POST /appointments/reschedule`, `POST /appointments/cancel`, `GET /appointments/{id}` |
| Purpose | Patient-facing care navigation and appointment scheduling |

This service handles the patient-initiated flow: a patient describes symptoms → the system classifies care destination → finds nearby providers → the patient selects a provider and books an appointment through a conversational LLM interface.

### 2.2 Post-care Orchestrator (`post_care`)

| Property | Value |
|----------|-------|
| Type | LangGraph state machine with NVIDIA LLM orchestrator |
| Framework | LangGraph `StateGraph` |
| Primary LLM | NVIDIA Nemotron (`nvidia/nemotron-3.5-lightning-30b-a3b`) |
| Entry Point | `orchestrator/agentic_graph_builder.py` → `run_agentic_workflow()` |
| Agents | Care Plan, Follow-Up, Response Analyzer, Care Continuity |
| Purpose | Post-discharge monitoring, risk classification, response analysis, and care routing |

The orchestrator monitors discharged patients: generates care plans → schedules follow-ups → analyzes patient responses via LLM → routes to appropriate continuity action. The workflow terminates at Care Continuity with a `requires_appointment` flag (currently always `False`).

### 2.3 Shared Appointment Agent (`agents/appointment_agent.py`)

| Property | Value |
|----------|-------|
| Type | LLM tool-calling loop (conversational) |
| LLM | NVIDIA meta/llama (via `NvidiaClient`) |
| Tools | `search_nearby_providers`, `select_provider`, `check_availability`, `select_slot`, `book_appointment` |
| Location | `alternate_care_agent 2/agents/appointment_agent.py` |
| Purpose | Autonomous provider discovery, slot surfacing, and appointment booking |

This is the single appointment scheduling engine. It operates as a bounded LLM tool-calling loop (max 5 iterations) that reasons over patient context and autonomously decides which scheduling tools to invoke.

### 2.4 PostgreSQL Database (`carepath_db`)

| Property | Value |
|----------|-------|
| Name | `carepath_db` |
| Host | `localhost:5432` |
| Connection | `post_care/database/connection.py` → `get_db_connection()` |
| Shared By | Both `post_care` and `alternate_care_agent 2` (via `session_bridge.py`) |

**Key Tables:**

| Table | Owner System | Purpose |
|-------|-------------|---------|
| `patient_ehr` | Post-care | Patient demographics, vitals, labs, history |
| `care_plans` | Post-care | Agent-generated care plans with risk/intensity |
| `care_plan_tasks` | Post-care | Individual tasks within each plan |
| `follow_up_checkins` | Post-care | Check-in records and patient responses |
| `appointment_sessions` | Shared | Appointment workflow state (both flows) |

---

## 3. Existing Appointment Agent

### 3.1 `run_appointment_agent()` — Turn 1 (Fresh Start)

```python
def run_appointment_agent(
    recommendation_id: str,       # Session identifier
    destination: str,             # Care destination (PCP, URGENT_CARE, SPECIALIST, etc.)
    latitude: float,              # Patient latitude
    longitude: float,             # Patient longitude
    radius_km: float = 15.0,     # Search radius
    specialty: Optional[str] = None,  # Specialist sub-type
    *,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = 5,
) -> Dict[str, Any]
```

**Returns:**
```python
{
    "ok": bool,
    "response": str,                   # Conversational text for patient
    "tool_calls_made": int,
    "iterations": int,
    "providers": List[Dict] | None,    # Raw provider list from OSM search
    "available_slots": List[Dict] | None,
    "selected_provider_id": str | None,
    "selected_provider_name": str | None,
    "selected_slot_id": str | None,
    "appointment_id": str | None,
    "appointment_status": str | None,
    "messages": List[Dict],            # Full LLM conversation history — PERSIST THIS
}
```

### 3.2 `continue_appointment_agent()` — Turn 2+ (Resume)

```python
def continue_appointment_agent(
    conversation_state: List[Dict[str, Any]],  # Restored message history
    patient_message: str,                       # New patient text
    *,
    known_providers: Optional[List[Dict]] = None,  # Prior provider list
    known_slots: Optional[List[Dict]] = None,      # Prior slot list
    session_selected_provider_id: Optional[str] = None,
    session_selected_slot_id: Optional[str] = None,
    session_mrn: Optional[str] = None,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = 5,
) -> Dict[str, Any]
```

Same return structure as `run_appointment_agent()`.

### 3.3 Available Tools (5 Total)

| # | Tool | Purpose | Triggers |
|---|------|---------|----------|
| 1 | `search_nearby_providers` | Find real facilities from OpenStreetMap | First turn (no provider list yet) |
| 2 | `select_provider` | Record patient's provider choice | Patient names a provider |
| 3 | `check_availability` | Fetch available slots from Appointment Service | Patient asks for times |
| 4 | `select_slot` | Record patient's slot choice | Patient picks a time |
| 5 | `book_appointment` | Execute real booking via Appointment Service | Patient confirms |

### 3.4 Conversation State Persistence

The Appointment Agent persists its **entire LLM message history** (system prompt + all assistant/user/tool messages) as a JSONB column (`conversation_state`) in the `appointment_sessions` table. This allows multi-turn conversations across HTTP requests — `/navigate` creates the session, `/chat` resumes it.

### 3.5 Session Model (`appointment_sessions` table)

```sql
CREATE TABLE appointment_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    mrn VARCHAR(50) NOT NULL,
    destination VARCHAR(50) NOT NULL
        CHECK (destination IN ('PCP', 'URGENT_CARE', 'SPECIALIST', 'TELEHEALTH', 'DENTISTRY')),
    specialty VARCHAR(100),
    rule_id VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    radius_km DOUBLE PRECISION DEFAULT 15.0,
    provider_candidates JSONB,
    ranked_providers JSONB,
    selected_provider_id VARCHAR(255),
    available_slots JSONB,
    selected_slot_id VARCHAR(255),
    appointment_id VARCHAR(255),
    appointment_status VARCHAR(50)
        CHECK (appointment_status IS NULL OR appointment_status IN (
            'BOOKED', 'RESCHEDULED', 'CANCELLED', 'COMPLETED'
        )),
    workflow_stage VARCHAR(50) NOT NULL DEFAULT 'NAVIGATION_COMPLETE'
        CHECK (workflow_stage IN (
            'NAVIGATION_COMPLETE', 'PROVIDERS_SEARCHED', 'PROVIDER_SELECTED',
            'AVAILABILITY_CHECKED', 'SLOT_SELECTED', 'BOOKED', 'RESCHEDULED', 'CANCELLED'
        )),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    source VARCHAR(50) NOT NULL DEFAULT 'PATIENT'
        CHECK (source IN ('PATIENT', 'POST_CARE')),
    care_plan_id VARCHAR(255),
    conversation_state JSONB
);
```

---

## 4. Patient-Side Flow (Current, Working)

### 4.1 Sequence

```
Patient → POST /navigate (NavigateRequest: mrn, patient features, location)
                │
                ▼
         Care Classification (deterministic YAML rule engine)
                │
                ▼
         run_appointment_agent(recommendation_id, destination, lat, lon, specialty)
                │
                ▼
         LLM calls search_nearby_providers → presents provider list
                │
                ▼
         AppointmentSessionRepository.create_session(
             mrn=mrn,
             destination=decision.destination,
             specialty=decision.specialty,
             source="PATIENT",                 ← SOURCE FIELD
             session_id=recommendation_id,
             conversation_state=messages
         )
                │
                ▼
         Response: Recommendation + provider list + appointment_agent_response
```

### 4.2 Continuation (Turn 2+)

```
Patient → POST /chat (recommendation_id, message)
                │
                ▼
         AppointmentSessionRepository.get_session(recommendation_id)
                │
                ▼
         continue_appointment_agent(
             conversation_state=session["conversation_state"],
             patient_message=request.message,
             known_providers=session["provider_candidates"],
             known_slots=session["available_slots"],
             session_selected_provider_id=session["selected_provider_id"],
             session_selected_slot_id=session["selected_slot_id"],
             session_mrn=session["mrn"]
         )
                │
                ▼
         AppointmentSessionRepository.update_session(recommendation_id, updates)
                │
                ▼
         Response: ChatResponse (response, workflow_stage, selections)
```

### 4.3 Source Field Usage

In the patient flow, `create_session` is called with `source="PATIENT"`. This is hardcoded in `api/routes.py` line within the `/navigate` endpoint:

```python
AppointmentSessionRepository.create_session(
    mrn=mrn,
    destination=decision.destination,
    specialty=decision.specialty,
    ...
    source="PATIENT",       # ← Already parameterized
    session_id=recommendation_id,
    conversation_state=appt_result.get("messages"),
)
```

---

## 5. Post-Care Flow (Current)

### 5.1 The 4-Agent Pipeline

```
INPUT: MRN + Prediction + Probability + Notes
        │
        ▼
┌─────────────────────────────────────┐
│ Agent 1: Care Plan Agent            │
│                                     │
│ Output:                             │
│   • care_plan_id (e.g. CP-0AEB878E) │
│   • risk_level (HIGH/MODERATE/LOW)  │
│   • intensity (INTENSIVE/REGULAR/   │
│     BASIC)                          │
│   • tasks[] with task_type, status  │
│   • doctor_instructions             │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│ Agent 2: Follow-Up Agent            │
│                                     │
│ Output:                             │
│   • task_id (e.g. T-9640CAAC)      │
│   • checkin_id (e.g. CHK-998DC412) │
│   • next_action (SCHEDULE_CHECKIN)  │
│   • checkin message                 │
└─────────────────┬───────────────────┘
                  ▼
         [Wait for Patient Response]
                  ▼
┌─────────────────────────────────────┐
│ Agent 3: Response Analyzer          │
│                                     │
│ Output:                             │
│   • classification (NORMAL/CONCERN/ │
│     URGENT/UNCLEAR)                 │
│   • confidence (0.0-1.0)           │
│   • symptoms[] (extracted)          │
│   • concerns[] (extracted)          │
│   • summary (text)                  │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│ Agent 4: Care Continuity            │
│                                     │
│ Output:                             │
│   • continuity_action               │
│   • requires_human_review           │
│   • requires_appointment = False ← │
│   • reason (text)                   │
└─────────────────────────────────────┘
```

### 5.2 Information Available at Care Continuity Output

When Care Continuity completes, the workflow state contains:

| Field | Source | Example |
|-------|--------|---------|
| `mrn` | Input | `"MRN000015"` |
| `care_plan_id` | Care Plan Agent | `"CP-0AEB878E"` |
| `risk_level` | Care Plan Agent | `"HIGH"` |
| `intensity` | Care Plan Agent | `"INTENSIVE"` |
| `task_id` | Follow-Up Agent | `"T-9640CAAC"` |
| `checkin_id` | Follow-Up Agent | `"CHK-998DC412"` |
| `classification` | Response Analyzer | `"URGENT"` |
| `confidence` | Response Analyzer | `0.9` |
| `symptoms` | Response Analyzer | `["chest tightness", "shortness of breath"]` |
| `concerns` | Response Analyzer | `["elevated blood pressure"]` |
| `continuity_action` | Care Continuity | `"URGENT_REVIEW"` |
| `requires_human_review` | Care Continuity | `True` |
| `requires_appointment` | Care Continuity | `False` (hardcoded) |
| `notes` | Input | `"Follow up with cardiology in 7 days."` |
| `doctor_instructions` | Care Plan Agent | Extracted from notes |

### 5.3 The `requires_appointment` Flag

Located in `post_care/agents/care_continuity/schemas.py` → `get_continuity_action()`:

```python
mapping = {
    "NORMAL": {
        "continuity_action": "CONTINUE_FOLLOW_UP",
        "requires_human_review": False,
        "requires_appointment": False,    # ← All False currently
        ...
    },
    "CONCERN": {
        "continuity_action": "CLINICAL_REVIEW",
        "requires_human_review": True,
        "requires_appointment": False,    # ← Integration point
        ...
    },
    "URGENT": {
        "continuity_action": "URGENT_REVIEW",
        "requires_human_review": True,
        "requires_appointment": False,    # ← Integration point
        ...
    },
    "UNCLEAR": {
        "continuity_action": "CLARIFICATION_REQUIRED",
        "requires_human_review": False,
        "requires_appointment": False,
        ...
    },
}
```

**Design Intent:** When `requires_appointment` is set to `True` for CONCERN/URGENT, the workflow should hand off to the Appointment Agent instead of terminating.

---

## 6. Shared Appointment Agent Architecture

### ONE Agent, TWO Callers

```
┌─────────────────────────────┐     ┌─────────────────────────────────┐
│     PATIENT-SIDE FLOW       │     │       POST-CARE FLOW            │
│                             │     │                                 │
│  POST /navigate             │     │  run_agentic_workflow()         │
│    ↓                        │     │    ↓                            │
│  Care Classification        │     │  Care Plan → Follow-Up →       │
│    ↓                        │     │  Response Analyzer →            │
│  run_appointment_agent()  ──┼──┐  │  Care Continuity               │
│    ↓                        │  │  │    ↓                            │
│  POST /chat                 │  │  │  requires_appointment = True    │
│    ↓                        │  │  │    ↓                            │
│  continue_appointment_    ──┼──┤  │  run_appointment_agent()  ──────┼──┐
│    agent()                  │  │  │    ↓                            │  │
│                             │  │  │  continue_appointment_        ──┼──┤
│                             │  │  │    agent()                      │  │
└─────────────────────────────┘  │  └─────────────────────────────────┘  │
                                 │                                        │
                                 ▼                                        ▼
                    ┌────────────────────────────────────────────────────────┐
                    │          SHARED APPOINTMENT AGENT                      │
                    │                                                        │
                    │  _run_appointment_agent_loop()                         │
                    │    ↓                                                   │
                    │  NVIDIA LLM tool-calling loop (max 5 iterations)       │
                    │    ↓                                                   │
                    │  Tools:                                                │
                    │    • search_nearby_providers (OpenStreetMap/Overpass)   │
                    │    • select_provider                                   │
                    │    • check_availability (External Appointment Service) │
                    │    • select_slot                                       │
                    │    • book_appointment (External Appointment Service)   │
                    └───────────────────────┬────────────────────────────────┘
                                            │
                                            ▼
                    ┌────────────────────────────────────────────────────────┐
                    │           PostgreSQL (carepath_db)                     │
                    │                                                        │
                    │   appointment_sessions                                 │
                    │     • source = 'PATIENT' | 'POST_CARE'               │
                    │     • care_plan_id (FK when source = POST_CARE)       │
                    │     • conversation_state (JSONB - full LLM history)   │
                    └────────────────────────────────────────────────────────┘
```

### Key Architectural Principle

The Appointment Agent (`_run_appointment_agent_loop`) is **caller-agnostic**. It receives:
- A list of messages (conversation history)
- Known provider/slot state for grounding

It does NOT know or care whether the caller is the patient-facing API or the Post-care orchestrator. The `source` column in `appointment_sessions` tracks provenance for analytics and audit — it does not change the agent's behavior.

---

## 7. Source/Origin Design

### 7.1 Database Schema (Already Exists)

The `appointment_sessions` table has a `source` column with a CHECK constraint:

```sql
source VARCHAR(50) NOT NULL DEFAULT 'PATIENT'
    CHECK (source IN ('PATIENT', 'POST_CARE'))
```

**Index exists:** `idx_appointment_sessions_source`

### 7.2 Repository API (Already Accepts `source` Parameter)

`AppointmentSessionRepository.create_session()` already accepts `source` as a parameter:

```python
@staticmethod
def create_session(
    mrn: str,
    destination: str,
    specialty: Optional[str] = None,
    ...
    source: str = "PATIENT",         # ← Already parameterized
    care_plan_id: Optional[str] = None,  # ← Already parameterized
    ...
) -> Dict[str, Any]:
```

### 7.3 `care_plan_id` Column (Already Exists)

The `care_plan_id` column exists in `appointment_sessions` specifically for the POST_CARE use case — it links the appointment session back to the care plan that triggered it.

### 7.4 What This Means for Integration

**No schema migration needed.** The database is already designed for dual-source appointment sessions. The Post-care integration only needs to:
1. Call `create_session(source="POST_CARE", care_plan_id=state["care_plan_id"], ...)`
2. Everything else (session retrieval, updates, expiration) works identically.

---

## 8. Post-Care → Appointment Handoff Contract

### 8.1 Fields Required by `run_appointment_agent()`

| Parameter | Status | Source in Post-Care State | Notes |
|-----------|--------|--------------------------|-------|
| `recommendation_id` | **NEEDS TO BE ADDED** | N/A — generate new session_id | Post-care doesn't have a recommendation_id; generate one (e.g. `f"pc_{token_urlsafe(12)}"`) |
| `destination` | **NEEDS EXTERNAL INPUT** | Not in current state | Must be derived from `classification` + `symptoms` + `notes` (e.g. URGENT + cardiology symptoms → SPECIALIST/CARDIOLOGY). Requires a mapping function or LLM decision. |
| `latitude` | **NEEDS EXTERNAL INPUT** | Not in current state | Patient's location is not collected during the Post-care flow. Must be sourced from `patient_ehr` table or provided by the patient at handoff time. |
| `longitude` | **NEEDS EXTERNAL INPUT** | Not in current state | Same as latitude. |
| `radius_km` | **CAN BE DERIVED** | Default 15.0 | Use default or derive from urgency (URGENT → smaller radius for faster access). |
| `specialty` | **CAN BE DERIVED** | `notes` + `symptoms` + `classification` | Extractable from doctor_instructions (e.g. "Follow up with cardiology" → `"CARDIOLOGY"`). Already partially parsed by the Care Plan Agent's LLM instruction extraction. |

### 8.2 Fields Required by `create_session()` for POST_CARE Source

| Parameter | Status | Source | Notes |
|-----------|--------|--------|-------|
| `mrn` | **EXISTS NOW** | `state["mrn"]` | Available from workflow start |
| `destination` | **NEEDS EXTERNAL INPUT** | See above | Mapping from clinical context |
| `specialty` | **CAN BE DERIVED** | `state["notes"]` / doctor_instructions | LLM extraction or pattern matching |
| `source` | **EXISTS NOW** | Hardcode `"POST_CARE"` | Just pass the string |
| `care_plan_id` | **EXISTS NOW** | `state["care_plan_id"]` | Available after Care Plan Agent |
| `latitude` | **NEEDS EXTERNAL INPUT** | `patient_ehr` table or patient input | Not in workflow state |
| `longitude` | **NEEDS EXTERNAL INPUT** | Same | Not in workflow state |
| `session_id` | **CAN BE DERIVED** | Generate new ID | `f"pc_{token_urlsafe(12)}"` |
| `conversation_state` | **EXISTS NOW** | From `run_appointment_agent()` return | Automatically populated |

### 8.3 Summary

| Category | Count | Fields |
|----------|-------|--------|
| EXISTS NOW | 4 | mrn, source, care_plan_id, conversation_state |
| CAN BE DERIVED | 3 | session_id, radius_km, specialty |
| NEEDS EXTERNAL INPUT | 3 | destination, latitude, longitude |
| NEEDS TO BE ADDED | 0 | (recommendation_id is just session_id) |

---

## 9. Appointment Agent Response Contract

### 9.1 What `run_appointment_agent()` Returns Now

```python
{
    "ok": True,                              # Success flag
    "response": "I found 3 nearby...",       # LLM conversational text
    "tool_calls_made": 1,                    # Tool calls in this turn
    "iterations": 2,                         # LLM iterations
    "providers": [                           # Provider list from OSM
        {
            "provider_id": "osm:node:123",
            "provider_name": "City Cardiology",
            "facility_name": "City Cardiology",
            "type": "specialist_clinic",
            "address": "123 Main St",
            "latitude": 12.9,
            "longitude": 80.1,
            "distance_km": 2.5
        }
    ],
    "available_slots": None,                 # Only set after check_availability
    "selected_provider_id": None,            # Only set after select_provider
    "selected_provider_name": None,
    "selected_slot_id": None,                # Only set after select_slot
    "appointment_id": None,                  # Only set after book_appointment
    "appointment_status": None,
    "messages": [...]                        # Full conversation — PERSIST
}
```

### 9.2 What Post-Care Needs

For the Post-care integration, the response from `run_appointment_agent()` provides:

| Field | Post-Care Usage |
|-------|----------------|
| `ok` | Determine if handoff succeeded |
| `response` | Forward to patient (Telegram/SMS) as appointment guidance |
| `providers` | Store in session for future conversation turns |
| `messages` | Persist as `conversation_state` for multi-turn flow |
| `appointment_id` | Final booking confirmation (after full flow completes) |
| `appointment_status` | Track lifecycle (BOOKED, etc.) |

### 9.3 Differences from Patient Flow

| Aspect | Patient Flow | Post-Care Flow |
|--------|-------------|----------------|
| First message content | Navigation recommendation context | Clinical context (symptoms, urgency, care plan) |
| Provider interaction | Patient selects via /chat | Patient selects via Telegram/async channel |
| Session creation | In /navigate route | In orchestrator appointment_agent node |
| Continuation | POST /chat endpoint | Either /chat endpoint OR async resumption |
| Source field | `"PATIENT"` | `"POST_CARE"` |
| care_plan_id | `None` | Set from state |

---

## 10. Session and MRN Continuity

### 10.1 MRN Flow Through Post-Care

```
run_agentic_workflow(mrn="MRN000015", ...)
    │
    ▼ state["mrn"] = "MRN000015"
    │
    ├─ Care Plan Agent → output.mrn = "MRN000015"
    │     state["mrn"] preserved
    │
    ├─ Follow-Up Agent → output.mrn = "MRN000015"
    │     state["mrn"] preserved
    │
    ├─ Response Analyzer → output.mrn = "MRN000015"
    │     state["mrn"] preserved
    │
    ├─ Care Continuity → output.mrn = "MRN000015"
    │     state["mrn"] preserved
    │
    └─ [NEW] Appointment Agent →
          create_session(mrn="MRN000015", ...)
          run_appointment_agent(...) 
          session_mrn = "MRN000015"  ← For book_appointment grounding
```

**MRN is available at every step.** No additional lookup needed.

### 10.2 `care_plan_id` Flow

```
Care Plan Agent creates CP-0AEB878E
    │
    ▼ state["care_plan_id"] = "CP-0AEB878E"
    │
    ├─ Follow-Up Agent uses it
    ├─ Response Analyzer uses it
    ├─ Care Continuity uses it
    │
    └─ [NEW] Appointment Agent →
          create_session(care_plan_id="CP-0AEB878E", ...)
```

**`care_plan_id` links the appointment session back to the triggering care plan** — this is the traceability mechanism.

### 10.3 Session ID for Post-Care

Unlike the patient flow (which uses `recommendation_id` as session_id), the Post-care flow needs its own session_id. Options:

- **Option A (Recommended):** Generate `f"pc_{care_plan_id}_{token_urlsafe(8)}"` — ties session to care plan, unique per appointment attempt.
- **Option B:** Generate `f"pc_{token_urlsafe(12)}"` — simpler but less traceable.

Store this session_id in the workflow state for continuation.

---

## 11. Conversation Continuation

### 11.1 Initial Handoff (Turn 1)

When Post-care triggers the Appointment Agent:

```python
# In the new appointment_agent tool within Post-care orchestrator:
result = run_appointment_agent(
    recommendation_id=session_id,     # Generated session_id
    destination=derived_destination,   # From clinical context
    latitude=patient_lat,             # From patient_ehr or input
    longitude=patient_lon,            # From patient_ehr or input
    radius_km=15.0,
    specialty=derived_specialty,      # From doctor_instructions
)

# Persist session
AppointmentSessionRepository.create_session(
    mrn=state["mrn"],
    destination=derived_destination,
    specialty=derived_specialty,
    source="POST_CARE",
    care_plan_id=state["care_plan_id"],
    session_id=session_id,
    conversation_state=result["messages"],
)
```

### 11.2 Subsequent Turns (Turn 2+)

After the initial handoff, the patient responds (via Telegram, SMS, or any async channel). The continuation works identically to the patient flow:

```python
# Resume conversation
session = AppointmentSessionRepository.get_session(session_id)

result = continue_appointment_agent(
    conversation_state=session["conversation_state"],
    patient_message=patient_reply,
    known_providers=session["provider_candidates"],
    known_slots=session["available_slots"],
    session_selected_provider_id=session["selected_provider_id"],
    session_selected_slot_id=session["selected_slot_id"],
    session_mrn=session["mrn"],
)

# Persist updated state
AppointmentSessionRepository.update_session(session_id, {
    "conversation_state": result["messages"],
    "workflow_stage": new_stage,
    ...
})
```

### 11.3 Continuation Channel

The patient-side uses `POST /chat`. For Post-care, options include:
- **Reuse `/chat` endpoint** — Patient replies route through the same endpoint (it only needs `recommendation_id` + `message`)
- **Telegram webhook** — Patient replies via Telegram, which calls `continue_appointment_agent` directly
- **Async orchestrator resume** — LangGraph checkpoint resumes when patient responds

The Appointment Agent itself is channel-agnostic — it only sees messages and returns responses.

---

## 12. Orchestrator Integration

### 12.1 Insertion Point

The appointment agent node should be inserted **after Care Continuity, before Complete**, triggered by `requires_appointment == True`.

**Current graph:**
```
START → orchestrator_llm → tool_executor → route_after_tool_execution
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                            orchestrator_llm  wait_for_response  complete
                            (loop back)                              │
                                                                     ▼
                                                                    END
```

**Proposed graph:**
```
START → orchestrator_llm → tool_executor → route_after_tool_execution
                                                    │
                                    ┌───────────────┼───────────────┬──────────────┐
                                    ▼               ▼               ▼              ▼
                            orchestrator_llm  wait_for_response  appointment_  complete
                            (loop back)                          agent_node       │
                                                                     │           ▼
                                                                     ▼          END
                                                                  complete
```

### 12.2 Routing Logic Change

In `route_after_tool_execution()` (file: `agentic_graph_builder.py`):

```python
# CURRENT stopping condition:
if state.get("continuity_action") is not None:
    return "complete"

# PROPOSED stopping condition:
if state.get("continuity_action") is not None:
    if state.get("requires_appointment") == True:
        return "appointment_agent"  # NEW route
    return "complete"
```

### 12.3 New Tool to Add

Add to `agentic_tools.py`:

```python
@tool
def call_appointment_agent(
    mrn: str,
    care_plan_id: str,
    destination: str,
    specialty: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Call the Shared Appointment Agent to find providers and initiate booking.
    
    Use when: requires_appointment is True after Care Continuity.
    Dependencies: care_continuity_output must exist with requires_appointment=True.
    """
    ...
```

### 12.4 New State Fields Needed

Add to `PostCareWorkflowState` in `workflow_state.py`:

```python
# APPOINTMENT AGENT PHASE OUTPUT (new)
appointment_session_id: Optional[str]
appointment_destination: Optional[str]       # Derived care destination
appointment_specialty: Optional[str]         # Derived specialty
appointment_agent_response: Optional[str]    # LLM response text
appointment_providers: Optional[List[Dict]]  # Provider search results
appointment_agent_output: Optional[Dict[str, Any]]  # Full agent result
```

### 12.5 Guardrails to Add

Add to `agentic_guardrails.py`:

```python
# Rule 5: appointment_agent only if requires_appointment == True
elif tool_name == "call_appointment_agent":
    if state.get("requires_appointment") != True:
        return False, "appointment_agent requires: requires_appointment == True"
    if state.get("care_plan_id") is None:
        return False, "appointment_agent requires: care_plan_id"
    if state.get("continuity_action") is None:
        return False, "appointment_agent requires: continuity_action set"
    return True, None
```

---

## 13. Clinical Responsibility Boundary

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   POST-CARE DECIDES **WHY**              APPOINTMENT AGENT DECIDES   │
│                                          **HOW**                     │
│                                                                      │
│   • Risk classification (HIGH/MOD/LOW)   • Which providers are       │
│   • Symptom extraction                     nearby (OSM search)       │
│   • Concern identification               • Which slots are           │
│   • Response analysis (URGENT/CONCERN)     available (ext. service)  │
│   • Continuity routing decision          • Booking execution         │
│   • "Patient needs cardiology follow-up" • "Dr. X at City Hospital   │
│   • Urgency determination                   has 9:00 AM tomorrow"    │
│                                                                      │
│   ──────────── BOUNDARY ────────────                                 │
│                                                                      │
│   Post-care NEVER:                       Appointment Agent NEVER:    │
│   • Searches for providers               • Classifies patient risk   │
│   • Checks appointment slots             • Analyzes symptoms         │
│   • Books appointments                   • Makes clinical decisions  │
│   • Knows about OSM/Overpass             • Accesses care plans       │
│   • Contacts external scheduling API     • Reads patient_ehr         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Handoff Data (Clinical Context → Scheduling Context)

The boundary is crossed by translating clinical output into scheduling input:

| Clinical (Post-care) | → | Scheduling (Appointment Agent) |
|---------------------|---|-------------------------------|
| `classification: "URGENT"` + `symptoms: ["chest tightness"]` | → | `destination: "SPECIALIST"` |
| `notes: "Follow up with cardiology"` | → | `specialty: "CARDIOLOGY"` |
| `risk_level: "HIGH"` | → | `radius_km: 10.0` (tighter search) |
| `mrn: "MRN000015"` | → | `mrn: "MRN000015"` (pass-through) |
| `care_plan_id: "CP-0AEB878E"` | → | `care_plan_id: "CP-0AEB878E"` (traceability) |

---

## 14. Final Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                        CAREPATH COMPLETE SYSTEM                                 │
│                                                                                │
│  ┌─────────────────────────────────┐   ┌────────────────────────────────────┐ │
│  │   PATIENT-SIDE (CarePath FE)    │   │   POST-CARE (Orchestrator)         │ │
│  │                                 │   │                                    │ │
│  │   Patient describes symptoms    │   │   Patient discharged from hospital │ │
│  │           │                     │   │           │                        │ │
│  │           ▼                     │   │           ▼                        │ │
│  │   POST /navigate                │   │   run_agentic_workflow()           │ │
│  │   (rule-based classification)   │   │   (LangGraph state machine)       │ │
│  │           │                     │   │           │                        │ │
│  │           ▼                     │   │           ▼                        │ │
│  │   CareDecision                  │   │   Care Plan Agent                 │ │
│  │   (destination + specialty)     │   │   (risk + plan + tasks)           │ │
│  │           │                     │   │           │                        │ │
│  │           │                     │   │           ▼                        │ │
│  │           │                     │   │   Follow-Up Agent                 │ │
│  │           │                     │   │   (schedule check-in)             │ │
│  │           │                     │   │           │                        │ │
│  │           │                     │   │           ▼                        │ │
│  │           │                     │   │   [Wait for Patient Response]     │ │
│  │           │                     │   │           │                        │ │
│  │           │                     │   │           ▼                        │ │
│  │           │                     │   │   Response Analyzer               │ │
│  │           │                     │   │   (Groq LLM → classify)           │ │
│  │           │                     │   │           │                        │ │
│  │           │                     │   │           ▼                        │ │
│  │           │                     │   │   Care Continuity                 │ │
│  │           │                     │   │   (URGENT → requires_appointment) │ │
│  │           │                     │   │           │                        │ │
│  │           ▼                     │   │           ▼                        │ │
│  │   ┌─────────────┐              │   │   ┌─────────────┐                 │ │
│  │   │ source =    │              │   │   │ source =    │                 │ │
│  │   │ "PATIENT"   │              │   │   │ "POST_CARE" │                 │ │
│  │   └──────┬──────┘              │   │   └──────┬──────┘                 │ │
│  └──────────┼──────────────────────┘   └──────────┼─────────────────────────┘ │
│             │                                      │                           │
│             ▼                                      ▼                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │              SHARED APPOINTMENT AGENT                                     │ │
│  │                                                                           │ │
│  │  run_appointment_agent() / continue_appointment_agent()                   │ │
│  │                                                                           │ │
│  │  ┌────────────────────────────────────────────────────────────────┐      │ │
│  │  │            NVIDIA LLM Tool-Calling Loop                        │      │ │
│  │  │                                                                │      │ │
│  │  │  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────┐ │      │ │
│  │  │  │search_nearby_    │  │check_            │  │book_         │ │      │ │
│  │  │  │providers (OSM)   │  │availability      │  │appointment   │ │      │ │
│  │  │  └──────────────────┘  └─────────────────┘  └──────────────┘ │      │ │
│  │  │  ┌──────────────────┐  ┌─────────────────┐                    │      │ │
│  │  │  │select_provider   │  │select_slot      │                    │      │ │
│  │  │  └──────────────────┘  └─────────────────┘                    │      │ │
│  │  └────────────────────────────────────────────────────────────────┘      │ │
│  └──────────────────────────────────────┬───────────────────────────────────┘ │
│                                          │                                     │
│                                          ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                    PostgreSQL (carepath_db)                                │ │
│  │                                                                           │ │
│  │  ┌────────────┐ ┌──────────┐ ┌───────────────┐ ┌──────────────────────┐ │ │
│  │  │patient_ehr │ │care_plans│ │care_plan_tasks│ │appointment_sessions  │ │ │
│  │  │            │ │          │ │               │ │  • session_id        │ │ │
│  │  │ mrn        │ │ plan_id  │ │ task_id       │ │  • mrn              │ │ │
│  │  │ vitals     │ │ risk     │ │ task_type     │ │  • source (PAT/PC)  │ │ │
│  │  │ labs       │ │ intensity│ │ status        │ │  • care_plan_id     │ │ │
│  │  │ history    │ │ status   │ │               │ │  • conversation_    │ │ │
│  │  │            │ │          │ │               │ │    state (JSONB)    │ │ │
│  │  └────────────┘ └──────────┘ └───────────────┘ │  • workflow_stage   │ │ │
│  │                                                  │  • appointment_id   │ │ │
│  │  ┌──────────────────┐                           └──────────────────────┘ │ │
│  │  │follow_up_checkins│                                                     │ │
│  │  │  • checkin_id    │                                                     │ │
│  │  │  • task_id       │                                                     │ │
│  │  │  • response      │                                                     │ │
│  │  └──────────────────┘                                                     │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Implementation Readiness Table

| Component | Current Status | What Needs to Change |
|-----------|---------------|---------------------|
| **`appointment_sessions` table** | ✅ Ready | No changes. `source` CHECK constraint already includes `'POST_CARE'`. `care_plan_id` column exists. |
| **`AppointmentSessionRepository.create_session()`** | ✅ Ready | No changes. Already accepts `source` and `care_plan_id` parameters. |
| **`AppointmentSessionRepository.get_session()`** | ✅ Ready | No changes. Works regardless of source. |
| **`AppointmentSessionRepository.update_session()`** | ✅ Ready | No changes. Works regardless of source. |
| **`session_bridge.py`** | ✅ Ready | No changes. Already imports from post_care and adds workspace root to sys.path. |
| **`run_appointment_agent()`** | ✅ Ready | No changes. Caller-agnostic — only needs destination, coordinates, specialty. |
| **`continue_appointment_agent()`** | ✅ Ready | No changes. Caller-agnostic — only needs conversation_state + message. |
| **`get_continuity_action()` mapping** | ⚠️ Needs Change | Set `requires_appointment: True` for CONCERN and URGENT classifications. |
| **`PostCareWorkflowState`** | ⚠️ Needs Change | Add appointment-phase state fields (session_id, destination, providers, etc.). |
| **`agentic_tools.py`** | ⚠️ Needs Change | Add `call_appointment_agent` tool wrapper. Add to `ALL_TOOLS`, `TOOL_NAMES`, `TOOL_MAPPING`. |
| **`agentic_guardrails.py`** | ⚠️ Needs Change | Add validation rule for `call_appointment_agent`. Update `get_available_tools()` and `validate_tool_call()`. |
| **`agentic_graph_builder.py`** | ⚠️ Needs Change | Add `appointment_agent_node`. Update `route_after_tool_execution()` to route to appointment node when `requires_appointment == True`. |
| **`agentic_tool_executor.py`** | ⚠️ Needs Change | Add `_update_state_appointment_agent()` for state mapping. |
| **Destination Derivation Logic** | 🔴 Needs Creation | New function to map `classification` + `symptoms` + `doctor_instructions` → `destination` + `specialty`. |
| **Patient Location Lookup** | 🔴 Needs Creation | Function to retrieve patient coordinates from `patient_ehr` or collect at runtime. |
| **Async Continuation Channel** | 🔴 Needs Creation | Mechanism for patient to respond to appointment agent messages (Telegram webhook → `continue_appointment_agent`). |
| **System Prompt Customization** | ⚠️ Optional | Custom `_APPOINTMENT_SYSTEM_PROMPT` variant for Post-care context (include urgency level, symptoms in initial message). |

### Implementation Priority Order

1. **Enable the flag** — Change `requires_appointment` to `True` for CONCERN/URGENT in `get_continuity_action()`
2. **Add state fields** — Extend `PostCareWorkflowState` with appointment phase fields
3. **Create destination derivation** — Build mapping from clinical output → scheduling input
4. **Add tool wrapper** — Create `call_appointment_agent` in `agentic_tools.py`
5. **Add guardrails** — Extend validation for the new tool
6. **Add graph node** — Insert appointment_agent_node + routing logic
7. **Add state updater** — `_update_state_appointment_agent()` in tool executor
8. **Patient location** — Implement coordinate lookup from `patient_ehr` or async collection
9. **Continuation channel** — Connect Telegram/async to `continue_appointment_agent()`
10. **End-to-end test** — Full workflow from URGENT response → booked appointment

---

*Document generated from source code inspection. All references point to actual implementations in the `post_care/` and `alternate_care_agent 2/` codebases.*
