"""
Care Plan Streaming Service - Real-time agent progress with SSE
Orchestrates 4 agents and streams their progress to the frontend
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.ehr import PatientEHR
from app.db.models import PostDischargeStatus

logger = logging.getLogger(__name__)


class CareplanStreamingService:
    """
    Streams care plan generation progress with 4 agents:
    1. Care Plan Agent - Creates tasks based on conditions
    2. Follow-up Agent - Schedules check-ins
    3. Response Analyser Agent - Reviews discharge notes
    4. Appointment Agent - Checks appointment status
    """
    
    def __init__(self, patient_id: str, db: AsyncSession):
        self.patient_id = patient_id
        self.db = db
        self.patient_ehr = None
        self.care_plan = {}
        self.follow_up = {}
        self.response_analyser = {}
        self.appointment = {}
    
    async def stream_generation(self) -> AsyncGenerator[str, None]:
        """
        Main streaming generator that yields SSE events.
        Yields Server-Sent Events in format: data: {json}\n\n
        """
        try:
            # Initialize
            yield self._event("init", {"message": "Starting care plan generation...", "patient_id": self.patient_id})
            await asyncio.sleep(0.5)
            
            # Load patient data
            yield self._event("loading", {"message": "Loading patient EHR data..."})
            self.patient_ehr = await self._load_patient_ehr()
            
            if not self.patient_ehr:
                yield self._event("error", {
                    "message": f"Patient {self.patient_id} not found",
                    "retry_available": True
                })
                return
            
            yield self._event("patient_loaded", {
                "name": self.patient_ehr.name,
                "mrn": self.patient_ehr.mrn,
                "age": self.patient_ehr.age
            })
            await asyncio.sleep(0.3)
            
            # Agent 1: Care Plan Agent
            async for event in self._run_care_plan_agent():
                yield event
            
            # Agent 2: Follow-up Agent
            async for event in self._run_followup_agent():
                yield event
            
            # Agent 3: Response Analyser Agent
            async for event in self._run_response_analyser_agent():
                yield event
            
            # Agent 4: Appointment Agent
            async for event in self._run_appointment_agent():
                yield event
            
            # Save to database
            yield self._event("saving", {"message": "Saving care plan to database..."})
            await self._save_to_database()
            await asyncio.sleep(0.5)
            
            # Final result
            yield self._event("complete", {
                "message": "Care plan generated successfully!",
                "care_plan": self.care_plan,
                "follow_up": self.follow_up,
                "response_analyser": self.response_analyser,
                "appointment": self.appointment,
                "summary": {
                    "total_tasks": len(self.care_plan.get("tasks", [])),
                    "next_checkin": self.follow_up.get("next_checkin"),
                    "status": self.care_plan.get("status"),
                    "appointment_scheduled": self.appointment.get("status") == "scheduled"
                }
            })
            
        except Exception as e:
            logger.error(f"Care plan generation failed: {e}", exc_info=True)
            yield self._event("error", {
                "message": f"Generation failed: {str(e)}",
                "retry_available": True
            })
    
    async def _run_care_plan_agent(self) -> AsyncGenerator[str, None]:
        """Agent 1: Analyzes patient and creates care tasks"""
        yield self._event("agent_start", {
            "agent": "care_plan",
            "title": "🤖 Care Plan Agent",
            "message": "Analyzing patient conditions..."
        })
        await asyncio.sleep(0.5)
        
        # Tool 1: Get patient conditions
        yield self._event("tool_call", {
            "agent": "care_plan",
            "tool": "analyze_conditions",
            "message": "Checking chronic conditions..."
        })
        await asyncio.sleep(0.8)
        
        conditions = []
        if self.patient_ehr.hypertension_flag:
            conditions.append("Hypertension")
        if self.patient_ehr.diabetes_flag:
            conditions.append("Diabetes")
        if self.patient_ehr.heart_failure_flag:
            conditions.append("Heart Failure")
        if self.patient_ehr.copd_asthma_flag:
            conditions.append("COPD/Asthma")
        
        yield self._event("tool_result", {
            "agent": "care_plan",
            "tool": "analyze_conditions",
            "result": f"Found {len(conditions)} chronic conditions: {', '.join(conditions) if conditions else 'None'}"
        })
        await asyncio.sleep(0.5)
        
        # Tool 2: Generate tasks
        yield self._event("tool_call", {
            "agent": "care_plan",
            "tool": "generate_tasks",
            "message": "Creating care tasks based on conditions..."
        })
        await asyncio.sleep(1.0)
        
        tasks = []
        if self.patient_ehr.active_medication_count and self.patient_ehr.active_medication_count > 0:
            tasks.append({"task": f"Take prescribed medications ({self.patient_ehr.active_medication_count} active)", "status": "pending"})
            yield self._event("llm_chunk", {
                "agent": "care_plan",
                "text": f"→ Added medication adherence task ({self.patient_ehr.active_medication_count} medications)"
            })
            await asyncio.sleep(0.3)
        
        if self.patient_ehr.hypertension_flag or (self.patient_ehr.systolic_bp and self.patient_ehr.systolic_bp > 140):
            tasks.append({"task": "Monitor blood pressure morning & evening", "status": "pending"})
            yield self._event("llm_chunk", {
                "agent": "care_plan",
                "text": "→ Added BP monitoring task (hypertension detected)"
            })
            await asyncio.sleep(0.3)
        
        if self.patient_ehr.diabetes_flag or (self.patient_ehr.hba1c and self.patient_ehr.hba1c > 7.0):
            tasks.append({"task": "Check blood glucose levels daily", "status": "pending"})
            yield self._event("llm_chunk", {
                "agent": "care_plan",
                "text": "→ Added glucose monitoring task (diabetes detected)"
            })
            await asyncio.sleep(0.3)
        
        if self.patient_ehr.heart_failure_flag:
            tasks.append({"task": "Record daily weight & check for ankle swelling", "status": "pending"})
            yield self._event("llm_chunk", {
                "agent": "care_plan",
                "text": "→ Added heart failure monitoring task"
            })
            await asyncio.sleep(0.3)
        
        if self.patient_ehr.copd_asthma_flag:
            tasks.append({"task": "Use maintenance inhaler as prescribed", "status": "pending"})
            yield self._event("llm_chunk", {
                "agent": "care_plan",
                "text": "→ Added respiratory medication task"
            })
            await asyncio.sleep(0.3)
        
        # Add follow-up task
        tasks.append({"task": f"Attend post-discharge follow-up appointment ({self.patient_ehr.discharge_destination or 'home'})", "status": "pending"})
        yield self._event("llm_chunk", {
            "agent": "care_plan",
            "text": "→ Added follow-up appointment task"
        })
        await asyncio.sleep(0.3)
        
        # Determine status
        risk_score = 0.0
        if len(conditions) >= 3:
            risk_score = 0.75
            status = "at_risk"
        elif len(conditions) >= 1:
            risk_score = 0.45
            status = "on_track"
        else:
            risk_score = 0.25
            status = "on_track"
        
        self.care_plan = {
            "status": status,
            "tasks": tasks,
            "risk_score": risk_score
        }
        
        yield self._event("tool_result", {
            "agent": "care_plan",
            "tool": "generate_tasks",
            "result": f"Created {len(tasks)} care tasks"
        })
        await asyncio.sleep(0.5)
        
        yield self._event("agent_complete", {
            "agent": "care_plan",
            "message": f"✅ Care Plan Agent completed: {len(tasks)} tasks created",
            "output": {"task_count": len(tasks), "status": status}
        })
        await asyncio.sleep(0.5)
    
    async def _run_followup_agent(self) -> AsyncGenerator[str, None]:
        """Agent 2: Schedules follow-up check-ins"""
        yield self._event("agent_start", {
            "agent": "followup",
            "title": "🤖 Follow-up Agent",
            "message": "Scheduling follow-up check-ins..."
        })
        await asyncio.sleep(0.5)
        
        # Tool: Calculate next check-in
        yield self._event("tool_call", {
            "agent": "followup",
            "tool": "calculate_checkin",
            "message": "Analyzing discharge date and risk level..."
        })
        await asyncio.sleep(0.8)
        
        now = datetime.now(timezone.utc)
        discharge_date = self.patient_ehr.discharge_date or now.date()
        
        # High risk = 2 days, medium = 3 days, low = 7 days
        risk_status = self.care_plan.get("status", "on_track")
        if risk_status == "at_risk":
            days_until_checkin = 2
        else:
            days_until_checkin = 3
        
        next_checkin = now + timedelta(days=days_until_checkin)
        
        yield self._event("llm_chunk", {
            "agent": "followup",
            "text": f"→ Discharge date: {discharge_date}"
        })
        await asyncio.sleep(0.3)
        
        yield self._event("llm_chunk", {
            "agent": "followup",
            "text": f"→ Risk level: {risk_status}"
        })
        await asyncio.sleep(0.3)
        
        yield self._event("llm_chunk", {
            "agent": "followup",
            "text": f"→ Scheduling check-in in {days_until_checkin} days"
        })
        await asyncio.sleep(0.5)
        
        self.follow_up = {
            "last_checkin": discharge_date.isoformat() if hasattr(discharge_date, 'isoformat') else str(discharge_date),
            "next_checkin": next_checkin.isoformat(),
            "is_scheduled": True
        }
        
        yield self._event("tool_result", {
            "agent": "followup",
            "tool": "calculate_checkin",
            "result": f"Next check-in: {next_checkin.strftime('%B %d, %Y at %I:%M %p')}"
        })
        await asyncio.sleep(0.5)
        
        yield self._event("agent_complete", {
            "agent": "followup",
            "message": "✅ Follow-up Agent completed: Check-in scheduled",
            "output": {"next_checkin": next_checkin.isoformat()}
        })
        await asyncio.sleep(0.5)
    
    async def _run_response_analyser_agent(self) -> AsyncGenerator[str, None]:
        """Agent 3: Reviews discharge notes and key info"""
        yield self._event("agent_start", {
            "agent": "response_analyser",
            "title": "🤖 Response Analyser Agent",
            "message": "Reviewing discharge documentation..."
        })
        await asyncio.sleep(0.5)
        
        # Tool: Extract key info
        yield self._event("tool_call", {
            "agent": "response_analyser",
            "tool": "extract_key_info",
            "message": "Extracting key discharge information..."
        })
        await asyncio.sleep(0.8)
        
        yield self._event("llm_chunk", {
            "agent": "response_analyser",
            "text": f"→ Primary diagnosis: {self.patient_ehr.primary_diagnosis_category or 'Not specified'}"
        })
        await asyncio.sleep(0.3)
        
        yield self._event("llm_chunk", {
            "agent": "response_analyser",
            "text": f"→ Discharge destination: {self.patient_ehr.discharge_destination or 'Home'}"
        })
        await asyncio.sleep(0.3)
        
        yield self._event("llm_chunk", {
            "agent": "response_analyser",
            "text": f"→ Length of stay: {self.patient_ehr.length_of_stay or 0} days"
        })
        await asyncio.sleep(0.3)
        
        self.response_analyser = {
            "key_info": {
                "discharge_date": str(self.patient_ehr.discharge_date or datetime.now().date()),
                "primary_diagnosis": self.patient_ehr.primary_diagnosis_category or "Not specified",
                "discharge_destination": self.patient_ehr.discharge_destination or "Home",
                "length_of_stay": self.patient_ehr.length_of_stay or 0
            }
        }
        
        yield self._event("tool_result", {
            "agent": "response_analyser",
            "tool": "extract_key_info",
            "result": "Key discharge information extracted"
        })
        await asyncio.sleep(0.5)
        
        yield self._event("agent_complete", {
            "agent": "response_analyser",
            "message": "✅ Response Analyser completed: Discharge info reviewed",
            "output": self.response_analyser
        })
        await asyncio.sleep(0.5)
    
    async def _run_appointment_agent(self) -> AsyncGenerator[str, None]:
        """Agent 4: Checks and schedules appointments"""
        yield self._event("agent_start", {
            "agent": "appointment",
            "title": "🤖 Appointment Agent",
            "message": "Checking appointment requirements..."
        })
        await asyncio.sleep(0.5)
        
        # Tool: Check if followup needed
        yield self._event("tool_call", {
            "agent": "appointment",
            "tool": "check_followup_needed",
            "message": "Evaluating follow-up appointment requirements..."
        })
        await asyncio.sleep(0.8)
        
        needs_followup = self.care_plan.get("status") == "at_risk" or self.patient_ehr.follow_up_within_7_days_flag
        
        yield self._event("llm_chunk", {
            "agent": "appointment",
            "text": f"→ Follow-up required: {'Yes' if needs_followup else 'No'}"
        })
        await asyncio.sleep(0.3)
        
        if needs_followup:
            yield self._event("llm_chunk", {
                "agent": "appointment",
                "text": "→ Scheduling post-discharge follow-up appointment..."
            })
            await asyncio.sleep(0.5)
            
            self.appointment = {
                "status": "scheduled",
                "appointment_id": f"APT_{self.patient_id}_FOLLOWUP",
                "scheduled_for": self.follow_up.get("next_checkin"),
                "type": "post_discharge_followup"
            }
            
            yield self._event("tool_result", {
                "agent": "appointment",
                "tool": "schedule_appointment",
                "result": "Follow-up appointment scheduled"
            })
        else:
            yield self._event("llm_chunk", {
                "agent": "appointment",
                "text": "→ No immediate follow-up appointment required"
            })
            await asyncio.sleep(0.3)
            
            self.appointment = {
                "status": "not_required",
                "reason": "Patient is on track with stable condition"
            }
            
            yield self._event("tool_result", {
                "agent": "appointment",
                "tool": "check_followup_needed",
                "result": "No appointment needed at this time"
            })
        
        await asyncio.sleep(0.5)
        
        yield self._event("agent_complete", {
            "agent": "appointment",
            "message": f"✅ Appointment Agent completed: {self.appointment.get('status')}",
            "output": self.appointment
        })
        await asyncio.sleep(0.5)
    
    async def _load_patient_ehr(self) -> Optional[PatientEHR]:
        """Load patient EHR data"""
        from app.patient.safety.service import _get_ehr_for_patient
        return await _get_ehr_for_patient(self.patient_id, self.db)
    
    async def _save_to_database(self):
        """Save generated care plan to database"""
        # Check if post-discharge status already exists
        stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == self.patient_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing
            existing.care_plan = self.care_plan
            existing.follow_up = self.follow_up
            existing.response_analyser = self.response_analyser
            existing.appointment = self.appointment
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new
            new_status = PostDischargeStatus(
                id=f"PDS_{self.patient_id}",
                patient_id=self.patient_id,
                care_plan=self.care_plan,
                follow_up=self.follow_up,
                response_analyser=self.response_analyser,
                appointment=self.appointment,
                updated_at=datetime.now(timezone.utc)
            )
            self.db.add(new_status)
        
        await self.db.commit()
    
    def _event(self, event_type: str, data: Dict[str, Any]) -> str:
        """Format SSE event"""
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"


# Service instance
async def stream_care_plan_generation(patient_id: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    """Main entry point for streaming care plan generation"""
    service = CareplanStreamingService(patient_id, db)
    async for event in service.stream_generation():
        yield event
