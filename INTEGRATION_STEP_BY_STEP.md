# Post-Care Integration: Step-by-Step Execution

## Status Check

✅ **API Keys:** All configured (NVIDIA, Groq, OpenRouter)
✅ **Database:** carepath_db exists with user `vishwa`
✅ **Post-Care Agent:** Complete implementation exists
✅ **Migrations:** SQL scripts available

---

## STEP 1: Update Requirements

```bash
cd /Users/vishwa/Desktop/CarepathAI_backend

# Add LangGraph dependencies to main requirements.txt
cat >> requirements.txt << 'EOF'

# LangGraph & LangChain for Post-Care Agent
langgraph>=0.0.30
langchain>=0.1.0
langchain-nvidia-ai-endpoints>=0.1.0
langchain-groq>=0.1.0
EOF

# Install new dependencies
pip install langgraph langchain langchain-nvidia-ai-endpoints langchain-groq
```

---

## STEP 2: Database Migrations

Check what tables already exist, then run migrations:

```bash
# Check existing tables
psql -U vishwa -d carepath_db -c "\dt"

# Run post_care migrations if needed
cd /Users/vishwa/Desktop/CarepathAI_backend/post_care/database/migrations
python run_migrations.py
```

---

## STEP 3: Create Integration Layer

### 3.1 New File: `app/integrations/__init__.py`

```python
"""
Integration layer for external modules
"""
```

### 3.2 New File: `app/integrations/post_care_adapter.py`

```python
"""
Adapter for integrating post_care LangGraph orchestrator into main FastAPI app
"""

import sys
from pathlib import Path
import logging
from typing import AsyncGenerator, Dict, Any
import json
import asyncio

# Add post_care to Python path
POST_CARE_PATH = Path(__file__).parent.parent.parent / "post_care"
if str(POST_CARE_PATH) not in sys.path:
    sys.path.insert(0, str(POST_CARE_PATH))

# Now import post_care modules
from orchestrator.agentic_graph_builder import build_agentic_graph
from orchestrator.workflow_state import PostCareWorkflowState

logger = logging.getLogger(__name__)


class PostCareStreamingAdapter:
    """
    Adapts LangGraph state machine to SSE streaming for frontend
    """
    
    def __init__(self, patient_id: str):
        self.patient_id = patient_id
        self.graph = None
        self.agent_map = {
            "care_plan": "care_plan",
            "follow_up": "followup",
            "response_analyzer": "response_analyser",
            "care_continuity": "care_continuity"
        }
    
    async def stream_workflow(
        self,
        mrn: str,
        prediction: int,
        probability: float,
        notes: str
    ) -> AsyncGenerator[str, None]:
        """
        Execute LangGraph workflow and stream progress as SSE events
        """
        try:
            # Emit initialization
            yield self._event("init", {
                "message": "Initializing LangGraph orchestrator...",
                "patient_id": self.patient_id
            })
            await asyncio.sleep(0.3)
            
            # Build graph
            self.graph = build_agentic_graph()
            logger.info(f"LangGraph built for patient {self.patient_id}")
            
            yield self._event("loading", {
                "message": "Starting agentic workflow..."
            })
            await asyncio.sleep(0.3)
            
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
            async for event in self._stream_graph_states(initial_state):
                yield event
            
        except Exception as e:
            logger.error(f"Workflow streaming failed: {e}", exc_info=True)
            yield self._event("error", {
                "message": f"Workflow execution failed: {str(e)}",
                "retry_available": True
            })
    
    async def _stream_graph_states(
        self,
        initial_state: PostCareWorkflowState
    ) -> AsyncGenerator[str, None]:
        """
        Execute graph and emit SSE events for each state change
        """
        
        previous_care_plan = None
        previous_follow_up = None
        previous_response = None
        previous_continuity = None
        
        # Execute graph (synchronous but we'll wrap it)
        for state_snapshot in self.graph.stream(initial_state):
            
            # state_snapshot is Dict[node_name, state]
            for node_name, current_state in state_snapshot.items():
                
                logger.info(f"Node executed: {node_name}")
                
                # Detect Care Plan Agent execution
                if current_state.get("care_plan") and current_state.get("care_plan") != previous_care_plan:
                    previous_care_plan = current_state.get("care_plan")
                    
                    yield self._event("agent_start", {
                        "agent": "care_plan",
                        "title": "🤖 Care Plan Agent",
                        "message": "Analyzing patient conditions and creating care plan..."
                    })
                    await asyncio.sleep(0.5)
                    
                    yield self._event("tool_call", {
                        "agent": "care_plan",
                        "tool": "risk_classification",
                        "message": f"Risk level: {current_state.get('risk_level')}"
                    })
                    await asyncio.sleep(0.3)
                    
                    tasks = current_state.get("care_plan", {}).get("tasks", [])
                    yield self._event("llm_chunk", {
                        "agent": "care_plan",
                        "text": f"→ Created {len(tasks)} care tasks"
                    })
                    await asyncio.sleep(0.3)
                    
                    yield self._event("agent_complete", {
                        "agent": "care_plan",
                        "message": f"✅ Care Plan Agent completed: {len(tasks)} tasks created",
                        "output": {
                            "care_plan_id": current_state.get("care_plan_id"),
                            "risk_level": current_state.get("risk_level")
                        }
                    })
                    await asyncio.sleep(0.5)
                
                # Detect Follow-Up Agent execution
                if current_state.get("follow_up_output") and current_state.get("follow_up_output") != previous_follow_up:
                    previous_follow_up = current_state.get("follow_up_output")
                    
                    yield self._event("agent_start", {
                        "agent": "followup",
                        "title": "🤖 Follow-up Agent",
                        "message": "Scheduling patient check-ins..."
                    })
                    await asyncio.sleep(0.5)
                    
                    yield self._event("tool_call", {
                        "agent": "followup",
                        "tool": "schedule_checkin",
                        "message": "Creating check-in record..."
                    })
                    await asyncio.sleep(0.3)
                    
                    yield self._event("agent_complete", {
                        "agent": "followup",
                        "message": "✅ Follow-up Agent completed: Check-in scheduled",
                        "output": current_state.get("follow_up_output")
                    })
                    await asyncio.sleep(0.5)
                
                # Detect Response Analyzer execution
                if current_state.get("response_analyzer_output") and current_state.get("response_analyzer_output") != previous_response:
                    previous_response = current_state.get("response_analyzer_output")
                    
                    yield self._event("agent_start", {
                        "agent": "response_analyser",
                        "title": "🤖 Response Analyser Agent",
                        "message": "Analyzing patient response with LLM..."
                    })
                    await asyncio.sleep(0.5)
                    
                    yield self._event("tool_call", {
                        "agent": "response_analyser",
                        "tool": "groq_llm_analysis",
                        "message": "Classifying response severity..."
                    })
                    await asyncio.sleep(0.8)
                    
                    classification = current_state.get("classification")
                    yield self._event("llm_chunk", {
                        "agent": "response_analyser",
                        "text": f"→ Classification: {classification}"
                    })
                    await asyncio.sleep(0.3)
                    
                    yield self._event("agent_complete", {
                        "agent": "response_analyser",
                        "message": f"✅ Response Analyser completed: {classification}",
                        "output": current_state.get("response_analyzer_output")
                    })
                    await asyncio.sleep(0.5)
                
                # Detect Care Continuity execution
                if current_state.get("care_continuity_output") and current_state.get("care_continuity_output") != previous_continuity:
                    previous_continuity = current_state.get("care_continuity_output")
                    
                    yield self._event("agent_start", {
                        "agent": "appointment",
                        "title": "🤖 Care Continuity Agent",
                        "message": "Determining next action..."
                    })
                    await asyncio.sleep(0.5)
                    
                    continuity_action = current_state.get("continuity_action")
                    yield self._event("agent_complete", {
                        "agent": "appointment",
                        "message": f"✅ Care Continuity completed: {continuity_action}",
                        "output": current_state.get("care_continuity_output")
                    })
                    await asyncio.sleep(0.5)
                
                # Check if workflow complete
                if current_state.get("workflow_status") == "COMPLETED":
                    yield self._event("saving", {
                        "message": "Workflow completed, finalizing..."
                    })
                    await asyncio.sleep(0.5)
                    
                    # Prepare summary
                    care_plan = current_state.get("care_plan", {})
                    summary = {
                        "total_tasks": len(care_plan.get("tasks", [])),
                        "status": current_state.get("risk_level", "on_track").lower(),
                        "next_checkin": current_state.get("follow_up_output", {}).get("next_checkin"),
                        "appointment_scheduled": current_state.get("requires_appointment", False)
                    }
                    
                    yield self._event("complete", {
                        "message": "Care plan generated successfully!",
                        "care_plan": care_plan,
                        "follow_up": current_state.get("follow_up_output"),
                        "response_analyser": current_state.get("response_analyzer_output"),
                        "appointment": {
                            "status": "scheduled" if current_state.get("requires_appointment") else "not_required"
                        },
                        "summary": summary
                    })
                    return
            
            await asyncio.sleep(0.1)  # Throttle
    
    def _event(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format SSE event"""
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"


# Entry point function
async def stream_real_post_care_workflow(
    patient_id: str,
    mrn: str,
    prediction: int,
    probability: float,
    notes: str
) -> AsyncGenerator[str, None]:
    """
    Main entry point for streaming real post-care workflow
    
    Args:
        patient_id: Patient ID in system
        mrn: Medical Record Number
        prediction: 0 (no risk) or 1 (readmission risk)
        probability: 0.0-1.0 readmission probability
        notes: Clinical notes / discharge instructions
    
    Yields:
        SSE formatted events
    """
    adapter = PostCareStreamingAdapter(patient_id)
    async for event in adapter.stream_workflow(mrn, prediction, probability, notes):
        yield event
```

---

## STEP 4: Update Care Plan Generation Endpoint

Replace the mock with real orchestrator:

### File: `app/api/v1/endpoints/care_plan_generation.py`

```python
"""
Care Plan Generation API - Real LangGraph Integration
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_care_manager
from app.db.base import get_db
from app.models.user import User

# Import REAL post-care adapter
from app.integrations.post_care_adapter import stream_real_post_care_workflow

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/patients/{patient_id}/generate-care-plan-stream")
async def generate_care_plan_with_stream(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate care plan using REAL LangGraph post-care orchestrator.
    
    **NEW:** This now calls the actual 4-agent system with LLM orchestration.
    
    **Agents:**
    1. Care Plan Agent - Risk classification + task generation
    2. Follow-Up Agent - Check-in scheduling
    3. Response Analyzer - LLM-powered patient response analysis
    4. Care Continuity - Routing logic
    
    **Returns:** Server-Sent Events stream (text/event-stream)
    """
    
    logger.info(f"Real care plan generation requested by {current_user.username} for patient {patient_id}")
    
    try:
        # Get patient EHR data
        from app.models.ehr import PatientEHR
        from sqlalchemy import select
        
        stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
        result = await db.execute(stmt)
        patient_ehr = result.scalar_one_or_none()
        
        if not patient_ehr:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found in EHR"
            )
        
        # Calculate readmission prediction
        # TODO: Replace with actual ML model
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start real care plan generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate care plan: {str(e)}"
        )


@router.post("/patients/{patient_id}/send-care-plan")
async def send_care_plan_to_patient(
    patient_id: str,
    current_user: User = Depends(get_current_care_manager),
    db: AsyncSession = Depends(get_db)
):
    """
    Send generated care plan to patient and create task reminders.
    
    **NOTE:** This now queries the real post_care tables (care_plans, care_plan_tasks)
    """
    
    logger.info(f"Sending care plan to patient {patient_id} by {current_user.username}")
    
    try:
        # Import post_care database connection
        import sys
        from pathlib import Path
        POST_CARE_PATH = Path(__file__).parent.parent.parent.parent.parent / "post_care"
        sys.path.insert(0, str(POST_CARE_PATH))
        
        from database.connection import get_db_connection
        
        # Get care plan from post_care tables
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get patient MRN
        from app.models.ehr import PatientEHR
        from sqlalchemy import select
        
        stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
        result = await db.execute(stmt)
        patient_ehr = result.scalar_one_or_none()
        
        if not patient_ehr:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # Query care_plans table
        cursor.execute("""
            SELECT id, risk_level, status
            FROM care_plans
            WHERE mrn = %s AND status = 'ACTIVE'
            ORDER BY created_at DESC
            LIMIT 1
        """, (patient_ehr.mrn,))
        
        care_plan = cursor.fetchone()
        
        if not care_plan:
            raise HTTPException(
                status_code=404,
                detail=f"No active care plan found for patient {patient_id}"
            )
        
        care_plan_id = care_plan[0]
        
        # Query care_plan_tasks
        cursor.execute("""
            SELECT id, task_description, status
            FROM care_plan_tasks
            WHERE care_plan_id = %s AND status = 'PENDING'
        """, (care_plan_id,))
        
        tasks = cursor.fetchall()
        
        conn.close()
        
        # Create notifications for each task
        from app.services.notification_service import generate_task_reminder
        
        notification_count = 0
        for idx, task in enumerate(tasks):
            task_id_db, task_desc, task_status = task
            await generate_task_reminder(
                db=db,
                patient_id=patient_id,
                task_index=idx,
                task_text=task_desc,
                scheduled_for=None
            )
            notification_count += 1
        
        logger.info(f"✓ Sent care plan {care_plan_id} to patient {patient_id}: {notification_count} notifications created")
        
        return {
            "success": True,
            "message": "Care plan sent to patient successfully",
            "care_plan_id": care_plan_id,
            "notifications_created": notification_count,
            "tasks_count": len(tasks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send care plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send care plan: {str(e)}"
        )
```

---

## STEP 5: Test the Integration

```bash
# Start backend
cd /Users/vishwa/Desktop/CarepathAI_backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, test the endpoint
curl -X POST "http://localhost:8000/api/v1/care-manager/patients/PAT_2BDF2BEF/generate-care-plan-stream" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## STEP 6: Frontend (No Changes Needed!)

The frontend modal (`CareplanGenerationModal.tsx`) already handles the SSE events correctly. The real orchestrator emits the same event types, so it will work automatically!

---

## Execution Order

1. ✅ Check API keys in `/Users/vishwa/Desktop/CarepathAI_backend/post_care/.env`
2. ⏳ Install LangGraph dependencies
3. ⏳ Run database migrations
4. ⏳ Create integration adapter
5. ⏳ Update API endpoint
6. ⏳ Test with real patient
7. ⏳ Verify database persistence

Ready to execute?
