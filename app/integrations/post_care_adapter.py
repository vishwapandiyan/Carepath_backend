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

# Import appointment bridge
from app.integrations.appointment_bridge import appointment_bridge

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
            "care_continuity": "appointment"  # Frontend expects "appointment" for agent 4
        }
    
    async def stream_workflow(
        self,
        mrn: str,
        prediction: int,
        probability: float,
        notes: str,
        db = None
    ) -> AsyncGenerator[str, None]:
        """
        Execute LangGraph workflow and stream progress as SSE events
        """
        try:
            # Emit initialization
            yield self._event("init", {
                "message": "Initializing real LangGraph orchestrator...",
                "patient_id": self.patient_id
            })
            await asyncio.sleep(0.3)
            
            # Build graph
            self.graph = build_agentic_graph()
            logger.info(f"✓ LangGraph built for patient {self.patient_id}")
            
            yield self._event("loading", {
                "message": "Starting 4-agent workflow with LLM orchestration..."
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
            async for event in self._stream_graph_states(initial_state, db):
                yield event
            
        except Exception as e:
            logger.error(f"Workflow streaming failed: {e}", exc_info=True)
            yield self._event("error", {
                "message": f"Workflow execution failed: {str(e)}",
                "retry_available": True
            })
    
    async def _stream_graph_states(
        self,
        initial_state: PostCareWorkflowState,
        db = None
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
                
                logger.info(f"🔄 Node executed: {node_name}")
                
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
                    
                    # Check if appointment is required
                    if current_state.get("requires_appointment") and db:
                        yield self._event("agent_start", {
                            "agent": "appointment",
                            "title": "🏥 Appointment Bridge",
                            "message": "Checking appointment requirements..."
                        })
                        await asyncio.sleep(0.5)
                        
                        # Trigger appointment bridge
                        try:
                            appointment_result = await appointment_bridge.trigger_appointment_workflow(
                                patient_id=self.patient_id,
                                care_continuity_output=current_state.get("care_continuity_output", {}),
                                db=db
                            )
                            
                            if appointment_result and appointment_result.get("success"):
                                yield self._event("tool_call", {
                                    "agent": "appointment",
                                    "tool": "appointment_bridge",
                                    "message": f"Appointment required: {appointment_result.get('appointment_context', {}).get('urgency', 'routine')}"
                                })
                                await asyncio.sleep(0.3)
                                
                                yield self._event("agent_complete", {
                                    "agent": "appointment",
                                    "message": "✅ Appointment workflow prepared",
                                    "output": appointment_result
                                })
                            else:
                                yield self._event("llm_chunk", {
                                    "agent": "appointment",
                                    "text": "→ No appointment needed or manual booking required"
                                })
                        except Exception as e:
                            logger.error(f"Appointment bridge failed: {e}", exc_info=True)
                            yield self._event("llm_chunk", {
                                "agent": "appointment",
                                "text": f"→ Appointment coordination pending manual review"
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
                    
                    # Check for appointment context from bridge
                    appointment_data = None
                    if current_state.get("requires_appointment"):
                        # Try to get appointment context if bridge was called
                        appointment_data = {
                            "appointment_required": True,
                            "status": "requires_review"
                        }
                    else:
                        appointment_data = {
                            "status": "not_required"
                        }
                    
                    # STEP 1: Auto-trigger patient notifications after follow-up
                    if current_state.get("follow_up_output") and db:
                        try:
                            from app.services.notification_service import generate_task_reminder
                            tasks = care_plan.get("tasks", [])
                            notification_count = 0
                            for idx, task in enumerate(tasks):
                                task_status = task.get("status", "PENDING")
                                if task_status in ("PENDING", "pending"):
                                    task_text = task.get("description") or task.get("task_type") or task.get("task", f"Task {idx+1}")
                                    await generate_task_reminder(
                                        db=db,
                                        patient_id=self.patient_id,
                                        task_index=idx,
                                        task_text=task_text,
                                        scheduled_for=None
                                    )
                                    notification_count += 1
                            
                            if notification_count > 0:
                                logger.info(f"✓ Auto-sent {notification_count} task notifications to patient {self.patient_id}")
                                yield self._event("notification", {
                                    "message": f"Sent {notification_count} task notifications to patient",
                                    "count": notification_count
                                })
                                await asyncio.sleep(0.3)
                        except Exception as notif_err:
                            logger.warning(f"Failed to auto-send notifications: {notif_err}")
                    
                    yield self._event("complete", {
                        "message": "Care plan generated successfully!",
                        "care_plan": care_plan,
                        "follow_up": current_state.get("follow_up_output"),
                        "response_analyser": current_state.get("response_analyzer_output"),
                        "appointment": appointment_data,
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
    notes: str,
    db = None
) -> AsyncGenerator[str, None]:
    """
    Main entry point for streaming real post-care workflow
    
    Args:
        patient_id: Patient ID in system
        mrn: Medical Record Number
        prediction: 0 (no risk) or 1 (readmission risk)
        probability: 0.0-1.0 readmission probability
        notes: Clinical notes / discharge instructions
        db: Optional database session for appointment integration
    
    Yields:
        SSE formatted events
    """
    adapter = PostCareStreamingAdapter(patient_id)
    async for event in adapter.stream_workflow(mrn, prediction, probability, notes, db):
        yield event
