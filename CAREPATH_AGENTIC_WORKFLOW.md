# CarePath Post-Care Agentic Workflow

## Overview

CarePath is an agentic post-discharge care management system that monitors patients after hospital discharge, classifies readmission risk, generates personalized care plans, schedules follow-ups, analyzes patient responses via LLM, and routes to appropriate continuity-of-care actions.

The system uses a **LangGraph state machine** with an **NVIDIA LLM orchestrator** that autonomously decides which tool (agent) to call next based on the current workflow state.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAREPATH AGENTIC SYSTEM                       │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │           LANGGRAPH STATE MACHINE                         │  │
│  │                                                           │  │
│  │   START → [Orchestrator LLM] → [Tool Executor] → ROUTE   │  │
│  │              ↑                         │                  │  │
│  │              └─────── LOOP ────────────┘                  │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │         SPECIALIZED AGENTS (Tools)                        │  │
│  │                                                           │  │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │  │
│  │   │Care Plan │  │Follow-Up │  │Response  │  │Care    │  │  │
│  │   │Agent     │  │Agent     │  │Analyzer  │  │Contin. │  │  │
│  │   └──────────┘  └──────────┘  └──────────┘  └────────┘  │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │              POSTGRESQL (carepath_db)                      │  │
│  │                                                           │  │
│  │   patient_ehr │ care_plans │ care_plan_tasks │ checkins   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## System Components

### 1. Orchestrator LLM (Brain)

| Property | Value |
|----------|-------|
| Framework | LangGraph (StateGraph) |
| Primary LLM | NVIDIA Nemotron (`nvidia/nemotron-3.5-lightning-30b-a3b`) |
| Provider | NVIDIA API (`https://integrate.api.nvidia.com/v1`) |
| Temperature | 0.3 (deterministic decisions) |
| Tool Calling | Native `AIMessage.tool_calls` via LangChain `bind_tools()` |
| Fallback 1 | OpenRouter `openai/gpt-oss-120b` |
| Fallback 2 | OpenRouter `google/gemini-2.5-flash` |

The orchestrator LLM does NOT perform medical analysis — it only decides which agent to invoke next.

### 2. Specialized Agents (4 Active)

| Agent | Type | LLM Used | Purpose |
|-------|------|----------|---------|
| Care Plan Agent | Hybrid (deterministic + LLM extraction) | Groq `openai/gpt-oss-120b` | Risk classification, care plan generation |
| Follow-Up Agent | Deterministic | None | Check-in scheduling, task management |
| Response Analyzer | LLM-based | Groq `openai/gpt-oss-120b` | NLP analysis of patient responses |
| Care Continuity | Deterministic | None | Workflow routing based on classification |

### 3. Database

| Table | Purpose |
|-------|---------|
| `patient_ehr` | Patient demographics, vitals, labs, medications, history |
| `care_plans` | Agent-generated care plans (risk level, intensity, status) |
| `care_plan_tasks` | Individual tasks within each plan |
| `follow_up_checkins` | Check-in records and patient responses |
| `appointment_sessions` | Appointment workflow state (ready for integration) |

---

## Workflow Input

```python
run_agentic_workflow(
    mrn="MRN000015",         # Patient medical record number
    prediction=1,            # ML model output: 0=no risk, 1=readmission risk
    probability=0.85,        # Readmission probability (0.0-1.0)
    notes="Follow up with cardiology in 7 days.",  # Discharge instructions
    initial_response=None    # Optional pre-loaded patient response (testing)
)
```

---

## Agentic Flow (Step by Step)

```
INPUT: MRN + Prediction + Probability + Notes
                    │
                    ▼
┌──────────────────────────────────────────┐
│          ORCHESTRATOR LLM NODE           │
│                                          │
│  1. Build state summary                  │
│  2. Get available tools (guardrails)     │
│  3. Call NVIDIA LLM with tool binding    │
│  4. LLM selects: call_care_plan_agent    │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│           TOOL EXECUTOR NODE             │
│                                          │
│  Execute: call_care_plan_agent()         │
│  Update state with results               │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│       ROUTE: route_after_tool_execution  │
│                                          │
│  Stopping condition? NO                  │
│  Patient response needed? NO             │
│  → Loop back to ORCHESTRATOR LLM        │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│          ORCHESTRATOR LLM NODE           │
│                                          │
│  State now has: care_plan_id, risk_level │
│  LLM selects: call_follow_up_agent      │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│           TOOL EXECUTOR NODE             │
│                                          │
│  Execute: call_follow_up_agent()         │
│  Update state: task_id, checkin_id       │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│       ROUTE: route_after_tool_execution  │
│                                          │
│  Stopping condition? NO                  │
│  Patient response needed? YES            │
│  → Route to WAIT_FOR_RESPONSE           │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│        WAIT FOR RESPONSE NODE            │
│                                          │
│  Collect patient response                │
│  (terminal input / pre-loaded)           │
│  Store in state["patient_response"]      │
│  → Route back to ORCHESTRATOR LLM       │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│          ORCHESTRATOR LLM NODE           │
│                                          │
│  State now has: patient_response         │
│  LLM selects: call_response_analyzer    │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│           TOOL EXECUTOR NODE             │
│                                          │
│  Execute: call_response_analyzer()       │
│  Groq LLM analyzes patient text          │
│  Update state: classification,           │
│  symptoms, concerns, confidence          │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│       ROUTE: route_after_tool_execution  │
│                                          │
│  Stopping condition? NO                  │
│  → Loop back to ORCHESTRATOR LLM        │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│          ORCHESTRATOR LLM NODE           │
│                                          │
│  State has: classification="URGENT"      │
│  LLM selects: call_care_continuity      │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│           TOOL EXECUTOR NODE             │
│                                          │
│  Execute: call_care_continuity()         │
│  Deterministic mapping:                  │
│    URGENT → URGENT_REVIEW               │
│  Update state: continuity_action         │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│       ROUTE: route_after_tool_execution  │
│                                          │
│  Stopping condition? YES                 │
│  (continuity_action is set)              │
│  → Route to COMPLETE                    │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│            COMPLETE NODE                 │
│                                          │
│  Mark workflow_status = "COMPLETED"      │
│  Return final state                      │
└──────────────────────────────────────────┘
```

---

## Guardrail Rules (Tool Availability)

The orchestrator uses **post-selection validation** — the LLM sees all tools, selects one, and guardrails validate the selection before execution.

| Tool | Availability Rule | Prevents |
|------|-------------------|----------|
| `call_care_plan_agent` | Always available (entry point) | — |
| `call_follow_up_agent` | Only if `care_plan_id` exists | Calling follow-up without a plan |
| `call_response_analyzer` | Only if care_plan + follow_up + patient_response exist, AND not already analyzed | Analyzing without context, or re-analyzing |
| `call_care_continuity` | Only if `response_analyzer_output` exists, AND `continuity_action` not yet determined | Routing without analysis, or re-routing |

**Progress Protection:** If a tool's phase is already completed, the validator rejects repeated calls and instructs the LLM to move forward.

---

## Stopping Conditions

The workflow stops when any of these conditions are met:

| Condition | Result |
|-----------|--------|
| `continuity_action` is set | Workflow complete (success) |
| `error` field is set | Workflow failed |
| `orchestrator_iterations >= 10` | Safety limit reached |

---

## Agent Details

### Agent 1: Care Plan Agent

**Purpose:** Generate or retrieve a personalized post-discharge care plan.

**Input:**
```python
ReadmissionInput(
    mrn="MRN000015",
    prediction=1,
    probability=0.85,
    notes="Follow up with cardiology in 7 days."
)
```

**Process:**
1. Validate input
2. Look up patient in PostgreSQL (`patient_ehr` table by MRN)
3. Classify risk: probability ≥ 0.80 → HIGH/INTENSIVE, ≥ 0.50 → MODERATE/REGULAR, < 0.50 → LOW/BASIC
4. Check for existing ACTIVE care plan (reuse if found)
5. If new: create care plan + generate risk-based tasks from predefined pathways
6. Extract doctor instructions from notes via Groq LLM
7. Personalize task descriptions based on extracted instructions

**Output:**
```python
CarePlanOutput(
    mrn="MRN000015",
    patient_id="11",
    care_plan_id="CP-0AEB878E",
    risk_level="HIGH",
    intensity="INTENSIVE",
    status="ACTIVE",
    doctor_instructions="Follow-up: Wound-care review within 5 days...",
    tasks=[CareTask(...), ...]
)
```

**Stored in:** `care_plans` + `care_plan_tasks` tables

---

### Agent 2: Follow-Up Agent

**Purpose:** Schedule patient check-ins based on care plan tasks.

**Input:**
```python
FollowUpInput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    risk_level="HIGH",
    intensity="INTENSIVE",
    tasks=[...]
)
```

**Process:**
1. Verify ACTIVE care plan exists in PostgreSQL
2. Retrieve current task statuses
3. Find next actionable task (status=PENDING or IN_PROGRESS)
4. Create or reuse a check-in record
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
        "checkin_id": "CHK-998DC412",
        "checkin_status": "SCHEDULED",
        "message": "Follow-up: Frequent patient check-ins."
    }
)
```

**Stored in:** `follow_up_checkins` table

---

### Agent 3: Response Analyzer

**Purpose:** Analyze patient's natural-language response using LLM.

**Input:**
```python
ResponseAnalyzerInput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    task_id="T-9640CAAC",
    checkin_id="CHK-998DC412",
    task_type="FREQUENT_CHECKINS",
    patient_response="I have been feeling chest tightness..."
)
```

**Process:**
1. Call Groq LLM (`openai/gpt-oss-120b`) with structured prompt
2. LLM classifies response: NORMAL / CONCERN / URGENT / UNCLEAR
3. Extract symptoms, concerns, sentiment
4. Return confidence score

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

**Purpose:** Deterministic routing based on response classification.

**Input:**
```python
CareContinuityInput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    task_id="T-9640CAAC",
    checkin_id="CHK-998DC412",
    classification="URGENT",
    summary="...",
    symptoms=[...],
    concerns=[...],
    confidence=0.9
)
```

**Process (deterministic, no LLM):**

| Classification | Action | Human Review | Appointment |
|---|---|---|---|
| NORMAL | CONTINUE_FOLLOW_UP | No | No |
| CONCERN | CLINICAL_REVIEW | Yes | No* |
| URGENT | URGENT_REVIEW | Yes | No* |
| UNCLEAR | CLARIFICATION_REQUIRED | No | No |

*`requires_appointment` is currently hardcoded to `False` — designed as a future integration point for the Shared Appointment Agent.

**Output:**
```python
CareContinuityOutput(
    mrn="MRN000015",
    care_plan_id="CP-0AEB878E",
    classification="URGENT",
    continuity_action="URGENT_REVIEW",
    reason="Patient response contains potentially urgent symptoms...",
    requires_human_review=True,
    requires_appointment=False
)
```

---

## Workflow State (TypedDict)

The entire workflow shares a single typed state object that flows through all nodes:

```python
PostCareWorkflowState = {
    # Input
    mrn: str,
    patient_id: Optional[str],
    prediction: int,          # 0 or 1
    probability: float,       # 0.0-1.0
    notes: Optional[str],

    # Care Plan Phase
    care_plan: Optional[Dict],
    care_plan_id: Optional[str],
    risk_level: Optional[str],      # HIGH | MODERATE | LOW
    intensity: Optional[str],       # INTENSIVE | REGULAR | BASIC

    # Follow-Up Phase
    follow_up_output: Optional[Dict],
    task_id: Optional[str],
    task_type: Optional[str],
    checkin_id: Optional[str],

    # Patient Response
    patient_response: Optional[str],

    # Response Analysis Phase
    response_analyzer_output: Optional[Dict],
    classification: Optional[str],  # NORMAL | CONCERN | URGENT | UNCLEAR
    response_confidence: Optional[float],
    symptoms: Optional[List[str]],
    concerns: Optional[List[str]],

    # Care Continuity Phase
    care_continuity_output: Optional[Dict],
    continuity_action: Optional[str],
    requires_human_review: Optional[bool],
    requires_appointment: Optional[bool],

    # Workflow Meta
    workflow_status: str,            # PENDING | RUNNING | COMPLETED | FAILED | WAITING
    current_node: Optional[str],
    error: Optional[str],
    orchestrator_decision: Optional[Dict],
}
```

---

## LLM Usage Summary

| Component | LLM | Provider | Purpose | Temperature |
|-----------|-----|----------|---------|-------------|
| Orchestrator | nvidia/nemotron-3.5-lightning-30b-a3b | NVIDIA API | Tool selection (which agent next?) | 0.3 |
| Doctor Instructions | openai/gpt-oss-120b | Groq | Extract structured instructions from notes | 0.7 |
| Response Analyzer | openai/gpt-oss-120b | Groq | Classify patient responses (NLP) | 0.7 |
| Task Personalization | openai/gpt-oss-120b | Groq | Map instructions to task descriptions | 0.7 |

---

## File Structure

```
post_care/
├── main.py                          # FastAPI EHR API (patient CRUD)
├── .env                             # API keys (NVIDIA, Groq, OpenRouter)
├── requirements.txt
│
├── orchestrator/                    # LangGraph agentic loop
│   ├── workflow_state.py            # State definition (TypedDict)
│   ├── agentic_graph_builder.py     # Graph topology + nodes + routing
│   ├── agentic_orchestrator_node.py # NVIDIA LLM decision node
│   ├── agentic_tool_executor.py     # Execute tool + update state
│   ├── agentic_guardrails.py        # Tool availability + validation
│   └── agentic_tools.py             # @tool wrappers for 4 agents
│
├── agents/
│   ├── care_plan/                   # Risk classification + plan creation
│   │   ├── agent.py, schemas.py, tools.py
│   ├── follow_up/                   # Check-in scheduling
│   │   ├── agent.py, schemas.py, tools.py
│   ├── response_analyzer/           # Groq LLM NLP analysis
│   │   ├── agent.py, schemas.py, tools.py
│   ├── care_continuity/             # Deterministic routing
│   │   ├── agent.py, schemas.py, tools.py
│   └── appointment/                 # Placeholder (future integration)
│
├── database/
│   ├── connection.py                # PostgreSQL connection pool
│   ├── repositories.py              # CarePlanTaskRepository
│   ├── appointment_repository.py    # AppointmentSessionRepository
│   └── migrations/                  # Schema definitions (001-005)
│
├── services/
│   ├── care_plan_service.py         # Plan persistence logic
│   └── care_plan_service_postgresql.py
│
├── llm/
│   ├── multi_model_fallback.py      # Groq model fallback chain
│   ├── doctor_instructions.py       # LLM extraction of instructions
│   └── task_personalization.py      # Instruction → task mapping
│
├── shared_tools/
│   └── patient/patient_context.py   # Patient context from PostgreSQL
│
└── tests/                           # Integration tests (7 files)
```

---

## Sample Execution Output

**Input:**
```json
{
  "mrn": "MRN000015",
  "prediction": 1,
  "probability": 0.85,
  "notes": "Follow up with cardiology in 7 days. Monitor blood pressure daily."
}
```

**Patient response (simulated):**
> "I have been feeling chest tightness and shortness of breath since yesterday. My blood pressure was 160/95 this morning."

**Final Output:**
```json
{
  "step_1_care_plan": {
    "mrn": "MRN000015",
    "care_plan_id": "CP-0AEB878E",
    "risk_level": "HIGH",
    "intensity": "INTENSIVE",
    "status": "ACTIVE",
    "tasks": 5
  },
  "step_2_follow_up": {
    "task_id": "T-9640CAAC",
    "checkin_id": "CHK-998DC412",
    "next_action": "SCHEDULE_CHECKIN"
  },
  "step_3_patient_response": "I have been feeling chest tightness...",
  "step_4_response_analyzer": {
    "classification": "URGENT",
    "confidence": 0.9,
    "symptoms": ["chest tightness", "shortness of breath", "elevated blood pressure"]
  },
  "step_5_care_continuity": {
    "continuity_action": "URGENT_REVIEW",
    "requires_human_review": true,
    "requires_appointment": false
  }
}
```

---

## Key Design Decisions

1. **LLM as orchestrator, not executor.** The NVIDIA LLM decides WHICH tool to call — it never performs medical analysis directly. That separation ensures clinical logic stays in deterministic code or specialized Groq models.

2. **Deterministic agents where possible.** Only the Response Analyzer requires an LLM for NLP classification. Care Plan risk thresholds, Follow-Up task scheduling, and Care Continuity routing are all deterministic.

3. **Guard rails enforce sequencing.** The LLM cannot skip steps or call agents out of order — guardrails validate dependencies before execution.

4. **PostgreSQL as source of truth.** Care plans, tasks, and check-ins are persisted. The in-memory state (TypedDict) is ephemeral during execution only.

5. **Existing plan reuse.** If a patient already has an ACTIVE care plan, the system reuses it (preserving task statuses) rather than creating duplicates.

6. **Agentic loop with safety limits.** Max 10 iterations prevents infinite loops. Errors immediately terminate the workflow.

---

## Future Integration Point

The `requires_appointment` flag in Care Continuity output is the designated handoff point for connecting to the Shared Appointment Agent. When enabled:

```
Care Continuity (URGENT/CONCERN)
        │
        │ requires_appointment = True
        ▼
[Appointment Agent Node]  ← NEW
        │
        │ Provider search + booking
        ▼
    COMPLETE
```

No architectural changes needed — just enable the flag and add a new tool + graph node.
