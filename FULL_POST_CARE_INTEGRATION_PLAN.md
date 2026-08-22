# Full Post-Care Agent Integration Plan

## Mission: Complete Integration of Real LangGraph Post-Care Orchestrator

**Goal:** Replace the mock streaming service with the actual LangGraph-based agentic orchestrator and integrate the shared appointment agent.

**Timeline:** 2-3 weeks (systematic approach)

---

## Phase 1: Environment & Dependencies Setup (Day 1)

### 1.1 Install LangGraph Dependencies

**Action:** Add post_care dependencies to main backend

```bash
# In /Users/vishwa/Desktop/CarepathAI_backend/
pip install langgraph langchain langchain-nvidia-ai-endpoints langchain-groq
```

**Files to check:**
- `post_care/requirements.txt` - review all dependencies
- Add to main `requirements.txt`

### 1.2 API Keys Configuration

**Action:** Add NVIDIA and Groq API keys to main `.env`

```bash
# In /Users/vishwa/Desktop/CarepathAI_backend/.env

# NVIDIA API (for orchestrator LLM)
NVIDIA_API_KEY=your_nvidia_api_key_here

# Groq API (for specialized agents)
GROQ_API_KEY=your_groq_api_key_here

# OpenRouter API (fallback)
OPENROUTER_API_KEY=your_openrouter_key_here
```

### 1.3 Database Schema Migration

**Action:** Run post_care database migrations

**Files to execute:**
```
post_care/database/migrations/
  001_create_care_plans.sql
  002_create_care_plan_tasks.sql
  003_create_follow_up_checkins.sql
  004_add_indexes.sql
  005_add_constraints.sql
```

**Migration script:**
```bash
psql -U vishwa -d carepath_db -f post_care/database/migrations/001_create_care_plans.sql
psql -U vishwa -d carepath_db -f post_care/database/migrations/002_create_care_plan_tasks.sql
psql -U vishwa -d carepath_db -f post_care/database/migrations/003_create_follow_up_checkins.sql
psql -U vishwa -d carepath_db -f post_care/database/migrations/004_add_indexes.sql
psql -U vishwa -d carepath_db -f post_care/database/migrations/005_add_constraints.sql
```

---

## Phase 2: Backend Integration (Days 2-7)

### 2.1 Import Post-Care Module into Main App

**Action:** Make post_care accessible from main FastAPI app

**File:** `/Users/vishwa/Desktop/CarepathAI_backend/app/__init__.py`

```python
# Add to Python path
import sys
from pathlib import Path

# Add post_care to path
POST_CARE_PATH = Path(__file__).parent.parent / "post_care"
sys.path.insert(0, str(POST_CARE_PATH))
```

### 2.2 Create Post-Care FastAPI Router

**New File:** `app/api/v1/endpoints/post_care_orchestrator.py`

```python
"""
Post-Care Orchestrator API
Exposes the LangGraph agentic workflow as REST endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

# Import the real orchestrator
from post_care.orchestrator.agentic_graph_builder import run_agentic_workflow

router = APIRouter()


class WorkflowStartRequest(BaseModel):
    mrn: str
    prediction: int  # 0 or 1
    probability: float  # 0.0-1.0
    notes: Optional[str] = None
    initial_response: Optional[str] = None


class WorkflowContinueRequest(BaseModel):
    workflow_id: str
    patient_response: str


@router.post("/workflow/start")
async def start_workflow(
    request: WorkflowStartRequest,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a new post-care workflow for a patient.
    
    This calls the real LangGraph orchestrator with 4 specialized agents.
    
    Returns:
        Workflow state after initial execution
    """
    try:
        # Call the real orchestrator
        final_state = run_agentic_workflow(
            mrn=request.mrn,
            prediction=request.prediction,
            probability=request.probability,
            notes=request.notes,
            initial_response=request.initial_response
        )
        
        return {
            "success": True,
            "workflow_status": final_state.get("workflow_status"),
            "care_plan_id": final_state.get("care_plan_id"),
            "risk_level": final_state.get("risk_level"),
            "intensity": final_state.get("intensity"),
            "classification": final_state.get("classification"),
            "continuity_action": final_state.get("continuity_action"),
            "requires_human_review": final_state.get("requires_human_review"),
            "requires_appointment": final_state.get("requires_appointment"),
            "state": final_state
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Workflow execution failed: {str(e)}"
        )


@router.post("/workflow/{workflow_id}/continue")
async def continue_workflow(
    workflow_id: str,
    request: WorkflowContinueRequest,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Continue an existing workflow with patient response.
    
    Used when workflow is in WAITING state for patient input.
    """
    # TODO: Implement workflow resumption with LangGraph checkpoints
    raise HTTPException(status_code=501, detail="Not implemented yet")
```

### 2.3 Replace Mock Streaming Service

**File:** `app/services/care_plan_streaming_service.py` (REWRITE)

```python
"""
Real Post-Care Streaming Service
Adapts LangGraph orchestrator to SSE streaming
"""

import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

# Import real orchestrator
from post_care.orchestrator.agentic_graph_builder import build_agentic_graph
from post_care.orchestrator.workflow_state import PostCareWorkflowState

logger = logging.getLogger(__name__)


class PostCareStreamingAdapter:
    """
    Adapts LangGraph intermediate states to SSE events for frontend
    """
    
    def __init__(self, patient_id: str, db: AsyncSession):
        self.patient_id = patient_id
        self.db = db
        self.graph = None
    
    async def stream_workflow(
        self,
        mrn: str,
        prediction: int,
        probability: float,
        notes: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream workflow execution as SSE events
        """
        try:
            # Initialize
            yield self._event("init", {
                "message": "Starting real agentic workflow...",
                "patient_id": self.patient_id
            })
            
            # Build LangGraph
            self.graph = build_agentic_graph()
            
            # Initial state
            initial_state: PostCareWorkflowState = {
                "mrn": mrn,
                "prediction": prediction,
                "probability": probability,
                "notes": notes,
                "workflow_status": "PENDING",
                "patient_id": None,
                "care_plan": None,
                "care_plan_id": None,
                "risk_level": None,
                "intensity": None,
                "follow_up_output": None,
                "task_id": None,
                "task_type": None,
                "checkin_id": None,
                "patient_response": None,
                "response_analyzer_output": None,
                "classification": None,
                "response_confidence": None,
                "symptoms": None,
                "concerns": None,
                "care_continuity_output": None,
                "continuity_action": None,
                "requires_human_review": None,
                "requires_appointment": None,
                "current_node": None,
                "error": None,
                "orchestrator_decision": None,
            }
            
            # Stream graph execution
            async for state in self._stream_graph_execution(initial_state):
                yield state
            
        except Exception as e:
            logger.error(f"Workflow streaming failed: {e}", exc_info=True)
            yield self._event("error", {
                "message": f"Workflow failed: {str(e)}",
                "retry_available": True
            })
    
    async def _stream_graph_execution(
        self,
        initial_state: PostCareWorkflowState
    ) -> AsyncGenerator[str, None]:
        """
        Execute LangGraph and emit events at each state change
        """
        
        # Execute graph with streaming
        for state_update in self.graph.stream(initial_state):
            # Extract current node and state
            for node_name, node_state in state_update.items():
                
                # Map node transitions to SSE events
                if node_name == "orchestrator_llm":
                    yield self._handle_orchestrator_event(node_state)
                
                elif node_name == "tool_executor":
                    yield self._handle_tool_event(node_state)
                
                elif node_name == "wait_for_response":
                    yield self._handle_wait_event(node_state)
                
                elif node_name == "complete":
                    yield self._handle_complete_event(node_state)
                
                # Yield state update
                await asyncio.sleep(0.1)  # Throttle events
        
        # Final completion
        yield self._event("complete", {
            "message": "Workflow completed successfully"
        })
    
    def _handle_orchestrator_event(self, state: Dict) -> str:
        """Convert orchestrator LLM decision to SSE event"""
        decision = state.get("orchestrator_decision", {})
        tool_name = decision.get("tool_name", "unknown")
        
        return self._event("orchestrator_decision", {
            "message": f"Orchestrator decided: {tool_name}",
            "tool_name": tool_name,
            "reasoning": decision.get("reasoning", "")
        })
    
    def _handle_tool_event(self, state: Dict) -> str:
        """Convert tool execution to SSE event"""
        # Map to agent events based on tool executed
        if state.get("care_plan"):
            return self._event("agent_complete", {
                "agent": "care_plan",
                "message": "✅ Care Plan Agent completed",
                "output": {
                    "care_plan_id": state.get("care_plan_id"),
                    "risk_level": state.get("risk_level"),
                    "tasks": len(state.get("care_plan", {}).get("tasks", []))
                }
            })
        
        elif state.get("follow_up_output"):
            return self._event("agent_complete", {
                "agent": "followup",
                "message": "✅ Follow-up Agent completed",
                "output": state.get("follow_up_output")
            })
        
        elif state.get("response_analyzer_output"):
            return self._event("agent_complete", {
                "agent": "response_analyser",
                "message": "✅ Response Analyzer completed",
                "output": state.get("response_analyzer_output")
            })
        
        elif state.get("care_continuity_output"):
            return self._event("agent_complete", {
                "agent": "care_continuity",
                "message": "✅ Care Continuity completed",
                "output": state.get("care_continuity_output")
            })
        
        return self._event("tool_call", {"message": "Tool executing..."})
    
    def _handle_wait_event(self, state: Dict) -> str:
        """Patient response needed"""
        return self._event("waiting_for_response", {
            "message": "Waiting for patient response...",
            "checkin_id": state.get("checkin_id")
        })
    
    def _handle_complete_event(self, state: Dict) -> str:
        """Workflow complete"""
        return self._event("complete", {
            "message": "Workflow completed",
            "care_plan_id": state.get("care_plan_id"),
            "risk_level": state.get("risk_level"),
            "classification": state.get("classification"),
            "continuity_action": state.get("continuity_action"),
            "requires_appointment": state.get("requires_appointment")
        })
    
    def _event(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format SSE event"""
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"


async def stream_real_care_plan_generation(
    patient_id: str,
    mrn: str,
    prediction: int,
    probability: float,
    notes: str,
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """
    Entry point for streaming real post-care workflow
    """
    adapter = PostCareStreamingAdapter(patient_id, db)
    async for event in adapter.stream_workflow(mrn, prediction, probability, notes):
        yield event
```

### 2.4 Update Care Plan Generation Endpoint

**File:** `app/api/v1/endpoints/care_plan_generation.py` (UPDATE)

```python
# Replace the import
from app.services.care_plan_streaming_service import stream_real_care_plan_generation

@router.post("/patients/{patient_id}/generate-care-plan-stream")
async def generate_care_plan_with_stream(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate care plan using REAL LangGraph orchestrator with streaming
    """
    
    # Get patient MRN
    from app.models.ehr import PatientEHR
    from sqlalchemy import select
    
    stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
    result = await db.execute(stmt)
    patient_ehr = result.scalar_one_or_none()
    
    if not patient_ehr:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Calculate readmission prediction (mock for now - replace with ML model)
    prediction = 1 if patient_ehr.prior_30_day_readmission_flag else 0
    probability = 0.75 if prediction == 1 else 0.25
    
    return StreamingResponse(
        stream_real_care_plan_generation(
            patient_id=patient_id,
            mrn=patient_ehr.mrn,
            prediction=prediction,
            probability=probability,
            notes=patient_ehr.clinical_notes or "Post-discharge monitoring",
            db=db
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

---

## Phase 3: Appointment Agent Integration (Days 8-12)

### 3.1 Create Appointment Agent Tool for Post-Care

**New File:** `post_care/agents/appointment/agent.py`

```python
"""
Appointment Agent for Post-Care
Integrates with shared appointment agent from alternate_care
"""

import sys
from pathlib import Path

# Add alternate_care to path
ALTERNATE_CARE_PATH = Path(__file__).parent.parent.parent.parent / "alternate_care_agent 2"
sys.path.insert(0, str(ALTERNATE_CARE_PATH))

from agents.appointment_agent import run_appointment_agent
from database.repositories.appointment_repository import AppointmentSessionRepository


def call_appointment_agent(
    mrn: str,
    care_plan_id: str,
    destination: str,
    specialty: str,
    latitude: float,
    longitude: float,
    radius_km: float = 15.0
) -> dict:
    """
    Call shared appointment agent from post-care context
    
    Args:
        mrn: Patient MRN
        care_plan_id: Care plan ID (for traceability)
        destination: PCP | URGENT_CARE | SPECIALIST | TELEHEALTH
        specialty: Specialty type (e.g., CARDIOLOGY)
        latitude: Patient latitude
        longitude: Patient longitude
        radius_km: Search radius
    
    Returns:
        Appointment agent result with session_id, providers, response
    """
    
    # Generate session ID for post-care
    import secrets
    session_id = f"pc_{care_plan_id}_{secrets.token_urlsafe(8)}"
    
    # Call shared appointment agent
    result = run_appointment_agent(
        recommendation_id=session_id,
        destination=destination,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        specialty=specialty,
        max_iterations=5
    )
    
    # Create session with POST_CARE source
    AppointmentSessionRepository.create_session(
        mrn=mrn,
        destination=destination,
        specialty=specialty,
        source="POST_CARE",              # ← Key differentiation
        care_plan_id=care_plan_id,       # ← Link back to care plan
        session_id=session_id,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        provider_candidates=result.get("providers"),
        conversation_state=result.get("messages"),
        workflow_stage="PROVIDERS_SEARCHED"
    )
    
    return {
        "session_id": session_id,
        "appointment_result": result,
        "source": "POST_CARE"
    }
```

### 3.2 Add Appointment Tool to LangGraph

**File:** `post_care/orchestrator/agentic_tools.py` (ADD)

```python
from langchain.tools import tool
from post_care.agents.appointment.agent import call_appointment_agent

@tool
def call_appointment_agent_tool(
    mrn: str,
    care_plan_id: str,
    destination: str,
    specialty: str,
    latitude: float,
    longitude: float
) -> dict:
    """
    Book follow-up appointment using shared appointment agent.
    
    Use this when:
    - Patient classification is CONCERN or URGENT
    - requires_appointment flag is True
    - Patient needs specialist follow-up
    
    Args:
        mrn: Patient MRN
        care_plan_id: Care plan ID
        destination: Care destination (PCP, SPECIALIST, URGENT_CARE)
        specialty: Medical specialty if SPECIALIST
        latitude: Patient location latitude
        longitude: Patient location longitude
    
    Returns:
        Appointment booking result with session_id and providers
    """
    return call_appointment_agent(
        mrn=mrn,
        care_plan_id=care_plan_id,
        destination=destination,
        specialty=specialty,
        latitude=latitude,
        longitude=longitude
    )
```

### 3.3 Enable requires_appointment Flag

**File:** `post_care/agents/care_continuity/schemas.py` (MODIFY)

```python
# CHANGE FROM:
"CONCERN": {
    "continuity_action": "CLINICAL_REVIEW",
    "requires_human_review": True,
    "requires_appointment": False,  # ← CHANGE THIS
    ...
},
"URGENT": {
    "continuity_action": "URGENT_REVIEW",
    "requires_human_review": True,
    "requires_appointment": False,  # ← CHANGE THIS
    ...
},

# CHANGE TO:
"CONCERN": {
    "continuity_action": "CLINICAL_REVIEW",
    "requires_human_review": True,
    "requires_appointment": True,  # ← NOW ENABLED
    ...
},
"URGENT": {
    "continuity_action": "URGENT_REVIEW",
    "requires_human_review": True,
    "requires_appointment": True,  # ← NOW ENABLED
    ...
},
```

### 3.4 Update Graph Routing

**File:** `post_care/orchestrator/agentic_graph_builder.py` (MODIFY)

```python
def route_after_tool_execution(
    state: PostCareWorkflowState
) -> Literal["orchestrator_llm", "wait_for_response", "appointment_agent", "complete"]:
    """
    Route to next node based on workflow state
    """
    
    # Check stopping conditions first
    if check_stopping_condition(state):
        # Check if appointment needed BEFORE completing
        if state.get("requires_appointment") and not state.get("appointment_session_id"):
            return "appointment_agent"
        return "complete"
    
    # Check if patient response is needed
    if state.get("follow_up_output") and not state.get("patient_response"):
        return "wait_for_response"
    
    # Continue orchestrator loop
    return "orchestrator_llm"


# ADD NEW NODE
def appointment_agent_node(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    Call shared appointment agent to book follow-up appointment
    """
    from post_care.agents.appointment.agent import call_appointment_agent
    
    # Derive destination and specialty from clinical context
    destination = derive_destination(state)
    specialty = derive_specialty(state)
    
    # Get patient location (from EHR or default)
    latitude, longitude = get_patient_location(state["mrn"])
    
    # Call appointment agent
    result = call_appointment_agent(
        mrn=state["mrn"],
        care_plan_id=state["care_plan_id"],
        destination=destination,
        specialty=specialty,
        latitude=latitude,
        longitude=longitude
    )
    
    state["appointment_session_id"] = result["session_id"]
    state["appointment_result"] = result["appointment_result"]
    
    return state


# UPDATE GRAPH BUILDER
def build_agentic_graph() -> CompiledStateGraph:
    graph = StateGraph(PostCareWorkflowState)
    
    # Add nodes
    graph.add_node("orchestrator_llm", orchestrator_llm_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("wait_for_response", wait_for_response_node)
    graph.add_node("appointment_agent", appointment_agent_node)  # ← NEW
    graph.add_node("complete", complete_node)
    
    # Add edges
    graph.set_entry_point("orchestrator_llm")
    graph.add_edge("orchestrator_llm", "tool_executor")
    graph.add_conditional_edges(
        "tool_executor",
        route_after_tool_execution,
        {
            "orchestrator_llm": "orchestrator_llm",
            "wait_for_response": "wait_for_response",
            "appointment_agent": "appointment_agent",  # ← NEW
            "complete": "complete"
        }
    )
    graph.add_edge("wait_for_response", "orchestrator_llm")
    graph.add_edge("appointment_agent", "complete")  # ← NEW
    graph.add_edge("complete", END)
    
    return graph.compile()
```

---

## Phase 4: Frontend Updates (Days 13-15)

### 4.1 Handle New SSE Event Types

**File:** `src/components/CareplanGenerationModal.tsx` (ADD)

```typescript
// Add new event handlers
case 'orchestrator_decision':
  setAgents((prev) =>
    prev.map((agent) => ({
      ...agent,
      logs: agent.status === 'active' 
        ? [...agent.logs, `🧠 Orchestrator: ${data.message}`]
        : agent.logs
    }))
  );
  break;

case 'waiting_for_response':
  setPhase('waiting');
  setCurrentMessage(data.message);
  break;

case 'appointment_booking':
  setCurrentMessage('📅 Booking follow-up appointment...');
  break;
```

### 4.2 Add Patient Response Input

**File:** `src/components/CareplanGenerationModal.tsx` (ADD)

```typescript
// Add waiting phase for patient response
{phase === 'waiting' && (
  <div className="careplan-modal__body">
    <div className="careplan-modal__waiting">
      <h3>⏳ Waiting for Patient Response</h3>
      <p>The patient needs to respond to the check-in before continuing.</p>
      
      <textarea
        placeholder="Enter patient response..."
        value={patientResponse}
        onChange={(e) => setPatientResponse(e.target.value)}
      />
      
      <button onClick={handleSubmitResponse}>
        Submit Response
      </button>
    </div>
  </div>
)}
```

---

## Phase 5: Testing & Validation (Days 16-20)

### 5.1 Unit Tests

- Test each agent individually
- Test LangGraph routing logic
- Test appointment agent integration
- Test SSE streaming adapter

### 5.2 Integration Tests

- End-to-end workflow test
- Appointment booking flow test
- Database persistence test
- Error handling test

### 5.3 Performance Tests

- LLM latency measurement
- Concurrent workflow execution
- Database connection pooling

---

## Phase 6: Deployment & Monitoring (Days 21+)

### 6.1 Environment Variables

Ensure all API keys are configured:
- NVIDIA_API_KEY
- GROQ_API_KEY
- OPENROUTER_API_KEY

### 6.2 Monitoring

- Log all LLM calls with tokens used
- Track workflow success/failure rates
- Monitor appointment booking conversion
- Alert on errors

### 6.3 Documentation

- Update API documentation
- Create runbook for operations
- Document error codes and resolution

---

## Success Criteria

✅ **Backend:**
- Real LangGraph orchestrator integrated
- All 4 agents working (Care Plan, Follow-Up, Response Analyzer, Care Continuity)
- Appointment agent integrated and callable
- SSE streaming adapter working
- Database migrations complete

✅ **Frontend:**
- Modal shows real agent progress
- Patient response input working
- Appointment booking visible
- Error handling graceful

✅ **Integration:**
- Shared appointment agent accessible from both patient and post-care flows
- `appointment_sessions` table has `source='POST_CARE'` records
- `care_plan_id` correctly links appointments to care plans

✅ **Testing:**
- Unit tests passing
- Integration tests passing
- Manual end-to-end test successful

---

## Risk Mitigation

**Risk 1:** LangGraph streaming to SSE is complex
- **Mitigation:** Build adapter layer incrementally, test with simple workflows first

**Risk 2:** LLM API costs
- **Mitigation:** Set rate limits, use cheaper Groq models where possible, cache results

**Risk 3:** Appointment agent path resolution
- **Mitigation:** Use absolute imports, add both systems to Python path

**Risk 4:** Database connection conflicts
- **Mitigation:** Use connection pooling, test concurrent access

---

## Next Immediate Actions

1. **Verify API Keys:** Do you have NVIDIA and Groq API keys?
2. **Backup Database:** Before running migrations
3. **Create Feature Branch:** `git checkout -b feature/full-post-care-integration`
4. **Start Phase 1:** Install dependencies and run migrations

Ready to proceed?
