"""
Agentic Tool Definitions for Post-Care Orchestrator

This module defines LangChain @tool decorated functions that wrap the four existing
post-care agents, enabling LLM tool calling via the agentic orchestrator.

Each tool:
1. Wraps an existing agent (no agent logic changes)
2. Has a @tool decorator for LangChain integration
3. Returns structured Dict (not agent output object)
4. Has docstring explaining when to use and dependencies
5. Handles errors gracefully

Tools are designed for LangChain tool calling mechanism:
- LLM selects tool based on state
- Tool executor calls selected tool
- Tool returns structured result
- State is updated with result

No modifications to agent logic - tools are purely wrapper layer.
"""

import logging
from typing import Any, Dict, Optional, List

from langchain_core.tools import tool

# Import existing agents
from post_care.agents.care_plan.agent import run_care_plan_agent
from post_care.agents.care_plan.schemas import ReadmissionInput
from post_care.agents.follow_up.agent import orchestrate_follow_up
from post_care.agents.follow_up.schemas import FollowUpInput, FollowUpTask
from post_care.agents.response_analyzer.agent import orchestrate_response_analysis
from post_care.agents.response_analyzer.schemas import ResponseAnalyzerInput
from post_care.agents.care_continuity.agent import process_care_continuity
from post_care.agents.care_continuity.schemas import CareContinuityInput

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL 1: Care Plan Agent
# ============================================================================

@tool
def call_care_plan_agent(
    mrn: str,
    prediction: int,
    probability: float,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call the Care Plan Agent to generate or retrieve a care plan.
    
    This tool:
    1. Validates readmission input
    2. Retrieves or creates a care plan from PostgreSQL
    3. Returns plan with tasks and personalization
    
    Args:
        mrn: Patient medical record number
        prediction: Readmission prediction (0 or 1)
        probability: Readmission probability (0.0-1.0)
        notes: Optional discharge instructions
    
    Returns:
        Dict with care plan details:
        {
            "mrn": str,
            "patient_id": str,
            "care_plan_id": str,
            "risk_level": "HIGH" | "MODERATE" | "LOW",
            "intensity": "INTENSIVE" | "REGULAR" | "BASIC",
            "status": "ACTIVE" | "COMPLETED" | "SUSPENDED",
            "doctor_instructions": Optional[str],
            "tasks": [
                {
                    "task_id": str,
                    "task_type": str,
                    "status": str,
                    "description": Optional[str],
                    "doctor_instruction": Optional[str]
                },
                ...
            ]
        }
    
    Use when:
    - Starting workflow for a patient
    - Need to establish baseline care plan
    - Checking for existing ACTIVE plan reuse
    
    Dependencies:
    - MRN required
    - PostgreSQL for plan/task storage
    
    Note: Reuses existing ACTIVE plans if available, preserves task statuses.
    """
    try:
        logger.info(f"Tool: call_care_plan_agent - mrn={mrn}")
        
        # Fix LLM argument misinterpretation: if probability > 1, normalize to 0-1 range
        if probability > 1.0:
            probability = probability / 100.0
        probability = max(0.0, min(1.0, probability))
        
        # Validate input
        input_data = ReadmissionInput(
            mrn=mrn,
            prediction=prediction,
            probability=probability,
            notes=notes
        )
        
        # Call existing agent
        output = run_care_plan_agent(input_data)
        
        # Convert to dict for tool return
        result = {
            "mrn": output.mrn,
            "patient_id": output.patient_id,
            "care_plan_id": output.care_plan_id,
            "risk_level": output.risk_level,
            "intensity": output.intensity,
            "status": output.status,
            "doctor_instructions": output.doctor_instructions,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "status": t.status,
                    "description": t.description,
                    "doctor_instruction": t.doctor_instruction,
                }
                for t in output.tasks
            ],
            "notes": output.notes,
            "error": None
        }
        
        logger.info(f"Tool: call_care_plan_agent - SUCCESS - plan_id={output.care_plan_id}")
        return result
        
    except Exception as e:
        logger.error(f"Tool: call_care_plan_agent - ERROR: {str(e)}")
        return {
            "error": str(e),
            "mrn": mrn,
            "care_plan_id": None
        }


# ============================================================================
# TOOL 2: Follow-Up Agent
# ============================================================================

@tool
def call_follow_up_agent(
    mrn: str,
    care_plan_id: str,
    risk_level: str,
    intensity: str,
    tasks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Call the Follow-Up Agent to schedule patient check-in.
    
    This tool:
    1. Verifies care plan exists and is ACTIVE
    2. Finds next actionable task
    3. Creates or reuses check-in
    4. Returns follow-up details
    
    Args:
        mrn: Patient medical record number
        care_plan_id: Associated care plan ID
        risk_level: Risk level from care plan (HIGH|MODERATE|LOW)
        intensity: Intensity level from care plan (INTENSIVE|REGULAR|BASIC)
        tasks: List of care tasks with structure:
            [
                {
                    "task_id": str,
                    "task_type": str,
                    "status": str,
                    "description": Optional[str],
                    "doctor_instruction": Optional[str]
                },
                ...
            ]
    
    Returns:
        Dict with follow-up details:
        {
            "mrn": str,
            "care_plan_id": str,
            "task_id": Optional[str],
            "checkin_id": Optional[str],
            "follow_up": Optional[dict],
            "next_action": "READY_FOR_RESPONSE" | "NO_PENDING_TASKS",
            "error": Optional[str]
        }
    
    Use when:
    - Care plan is established and ACTIVE
    - Ready to schedule patient follow-up
    - Need to identify next actionable task
    
    Dependencies:
    - Valid care_plan_id required
    - PostgreSQL for task/check-in storage
    - Tasks must be provided from care plan
    
    Note: Reuses existing check-ins if still valid within timing window.
    """
    try:
        logger.info(f"Tool: call_follow_up_agent - mrn={mrn}, plan_id={care_plan_id}")
        
        # Convert task dicts to FollowUpTask objects
        follow_up_tasks = [
            FollowUpTask(
                task_id=t["task_id"],
                task_type=t["task_type"],
                status=t.get("status", "PENDING"),
                description=t.get("description"),
                doctor_instruction=t.get("doctor_instruction")
            )
            for t in tasks
        ]
        
        # Validate input
        input_data = FollowUpInput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            risk_level=risk_level,
            intensity=intensity,
            tasks=follow_up_tasks,
            notes=None,
            patient_preferences=None
        )
        
        # Call existing agent
        output = orchestrate_follow_up(input_data)
        
        # Convert to dict
        result = {
            "mrn": output.mrn,
            "care_plan_id": output.care_plan_id,
            "task_id": output.follow_up.get("task_id") if output.follow_up else None,
            "checkin_id": output.follow_up.get("checkin_id") if output.follow_up else None,
            "follow_up": output.follow_up or {},
            "next_action": output.next_action,
            "error": output.error
        }
        
        logger.info(f"Tool: call_follow_up_agent - SUCCESS - action={output.next_action}")
        return result
        
    except Exception as e:
        logger.error(f"Tool: call_follow_up_agent - ERROR: {str(e)}")
        return {
            "error": str(e),
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "next_action": None
        }


# ============================================================================
# TOOL 3: Response Analyzer Agent
# ============================================================================

@tool
def call_response_analyzer(
    mrn: str,
    care_plan_id: str,
    task_id: str,
    checkin_id: str,
    task_type: str,
    patient_response: str,
    doctor_instruction: Optional[str] = None,
    task_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call the Response Analyzer Agent to analyze patient response.
    
    This tool:
    1. Validates patient response input
    2. Calls Groq LLM to analyze response
    3. Returns classification (NORMAL|CONCERN|URGENT|UNCLEAR)
    
    NOTE: This tool makes ONE Groq LLM call internally to analyze response.
    
    Args:
        mrn: Patient medical record number
        care_plan_id: Associated care plan ID
        task_id: Associated task ID
        checkin_id: Associated check-in ID
        task_type: Type of follow-up task
        patient_response: Patient's natural language response
        doctor_instruction: Optional context from care plan
        task_description: Optional context from care plan
    
    Returns:
        Dict with analysis results:
        {
            "mrn": str,
            "care_plan_id": str,
            "task_id": str,
            "checkin_id": str,
            "classification": "NORMAL" | "CONCERN" | "URGENT" | "UNCLEAR",
            "confidence": float (0.0-1.0),
            "summary": str,
            "symptoms": [str],
            "concerns": [str],
            "patient_sentiment": "POSITIVE" | "NEUTRAL" | "NEGATIVE",
            "error": Optional[str]
        }
    
    Use when:
    - Patient has provided a response to follow-up task
    - Need to interpret patient response with LLM
    - Must determine response classification for routing
    
    Dependencies:
    - Valid task_id and checkin_id required
    - patient_response required (non-empty string)
    - Groq LLM call (external, may fail)
    
    Note: This is the primary LLM call in the workflow.
    Response classification drives continuity routing decisions.
    """
    try:
        logger.info(f"Tool: call_response_analyzer - mrn={mrn}, task_id={task_id}")
        
        # Validate input
        input_data = ResponseAnalyzerInput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=checkin_id,
            task_type=task_type,
            patient_response=patient_response,
            doctor_instruction=doctor_instruction,
            task_description=task_description
        )
        
        # Call existing agent (which calls Groq LLM internally)
        output = orchestrate_response_analysis(input_data)
        
        # Convert to dict
        result = {
            "mrn": output.mrn,
            "care_plan_id": output.care_plan_id,
            "task_id": output.task_id,
            "checkin_id": output.checkin_id,
            "classification": output.classification,
            "confidence": output.confidence,
            "summary": output.summary,
            "symptoms": output.symptoms,
            "concerns": output.concerns,
            "patient_sentiment": output.patient_sentiment,
            "error": output.error
        }
        
        logger.info(f"Tool: call_response_analyzer - SUCCESS - classification={output.classification}")
        return result
        
    except Exception as e:
        logger.error(f"Tool: call_response_analyzer - ERROR: {str(e)}")
        return {
            "error": str(e),
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "task_id": task_id,
            "checkin_id": checkin_id,
            "classification": None
        }


# ============================================================================
# TOOL 4: Care Continuity Agent
# ============================================================================

@tool
def call_care_continuity(
    mrn: str,
    care_plan_id: str,
    task_id: str,
    checkin_id: str,
    classification: str,
    summary: str,
    symptoms: List[str],
    concerns: List[str],
    confidence: float,
    doctor_instruction: Optional[str] = None,
    task_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call the Care Continuity Agent to determine workflow routing.
    
    This tool:
    1. Validates response analysis classification
    2. Routes to appropriate continuity action
    3. Determines if human review or appointment needed
    4. Returns deterministic routing decision
    
    Args:
        mrn: Patient medical record number
        care_plan_id: Associated care plan ID
        task_id: Associated task ID
        checkin_id: Associated check-in ID
        classification: Response classification from analyzer
            One of: NORMAL | CONCERN | URGENT | UNCLEAR
        summary: Summary of patient response
        symptoms: List of symptoms mentioned by patient
        concerns: List of concerns identified in response
        confidence: Confidence score from analyzer (0.0-1.0)
        doctor_instruction: Optional context from care plan
        task_description: Optional context from care plan
    
    Returns:
        Dict with continuity decision:
        {
            "mrn": str,
            "care_plan_id": str,
            "task_id": str,
            "checkin_id": str,
            "classification": str,
            "continuity_action": 
                "CONTINUE_FOLLOW_UP" | 
                "CLINICAL_REVIEW" | 
                "URGENT_REVIEW" | 
                "CLARIFICATION_REQUIRED",
            "reason": str,
            "requires_human_review": bool,
            "requires_appointment": bool,
            "error": Optional[str]
        }
    
    Use when:
    - Response analysis is complete
    - Need to determine next workflow phase
    - Must route to appropriate continuation path
    
    Dependencies:
    - response_analyzer_output required
    - Valid classification required (from analyzer)
    - All IDs required for tracking
    
    Note: This is DETERMINISTIC routing based on classification:
    - NORMAL → CONTINUE_FOLLOW_UP
    - CONCERN → CLINICAL_REVIEW
    - URGENT → URGENT_REVIEW
    - UNCLEAR → CLARIFICATION_REQUIRED
    """
    try:
        logger.info(f"Tool: call_care_continuity - mrn={mrn}, classification={classification}")
        
        # Validate input
        input_data = CareContinuityInput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=checkin_id,
            classification=classification,
            summary=summary,
            symptoms=symptoms,
            concerns=concerns,
            patient_sentiment=None,  # Not available at this point
            confidence=confidence,
            doctor_instruction=doctor_instruction,
            task_description=task_description
        )
        
        # Call existing agent
        output = process_care_continuity(input_data)
        
        # Convert to dict
        result = {
            "mrn": output.mrn,
            "care_plan_id": output.care_plan_id,
            "task_id": output.task_id,
            "checkin_id": output.checkin_id,
            "classification": output.classification,
            "continuity_action": output.continuity_action,
            "reason": output.reason,
            "requires_human_review": output.requires_human_review,
            "requires_appointment": output.requires_appointment,
            "error": output.error
        }
        
        logger.info(f"Tool: call_care_continuity - SUCCESS - action={output.continuity_action}")
        return result
        
    except Exception as e:
        logger.error(f"Tool: call_care_continuity - ERROR: {str(e)}")
        return {
            "error": str(e),
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "task_id": task_id,
            "checkin_id": checkin_id,
            "continuity_action": None
        }


# ============================================================================
# TOOL 5: Wait for Patient Response (Optional)
# ============================================================================

@tool
def wait_for_patient_response(
    mrn: str,
    care_plan_id: str,
    task_id: str,
    checkin_id: str,
) -> Dict[str, Any]:
    """
    Explicit wait state for patient response.
    
    This tool signals that the workflow is waiting for external patient input.
    Useful for workflows where timing or external system coordination is needed.
    
    Args:
        mrn: Patient medical record number
        care_plan_id: Associated care plan ID
        task_id: Associated task ID
        checkin_id: Associated check-in ID
    
    Returns:
        Dict indicating wait status:
        {
            "status": "WAITING_FOR_PATIENT_RESPONSE",
            "mrn": str,
            "care_plan_id": str,
            "task_id": str,
            "checkin_id": str,
            "message": str,
            "error": Optional[str]
        }
    
    Use when:
    - Follow-up is scheduled and ready
    - Waiting for patient to provide response
    - Need to signal external system to wait
    
    Note: This is an optional tool. LLM can select it or other tools.
    """
    try:
        logger.info(f"Tool: wait_for_patient_response - mrn={mrn}")
        
        return {
            "status": "WAITING_FOR_PATIENT_RESPONSE",
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "task_id": task_id,
            "checkin_id": checkin_id,
            "message": "Workflow paused - waiting for patient response...",
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Tool: wait_for_patient_response - ERROR: {str(e)}")
        return {
            "error": str(e),
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "status": "FAILED"
        }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

ALL_TOOLS = [
    call_care_plan_agent,
    call_follow_up_agent,
    call_response_analyzer,
    call_care_continuity,
    wait_for_patient_response,  # NEW: Optional tool for explicit wait state
]

TOOL_NAMES = {
    "care_plan": "call_care_plan_agent",
    "follow_up": "call_follow_up_agent",
    "response_analyzer": "call_response_analyzer",
    "care_continuity": "call_care_continuity",
    "wait_for_response": "wait_for_patient_response",  # NEW
}

# Mapping of tool names to tool functions for execution
TOOL_MAPPING = {
    "call_care_plan_agent": call_care_plan_agent,
    "call_follow_up_agent": call_follow_up_agent,
    "call_response_analyzer": call_response_analyzer,
    "call_care_continuity": call_care_continuity,
    "wait_for_patient_response": wait_for_patient_response,  # NEW
}
