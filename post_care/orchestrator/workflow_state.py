"""
Workflow State Definition for Post-Care Agentic Orchestrator

This module defines the shared state structure used by the agentic orchestrator.
The PostCareWorkflowState TypedDict is used by all orchestrator components to
maintain workflow state across LangGraph nodes.

Key Components:
- PostCareWorkflowState: TypedDict defining all workflow state fields
- Used by: orchestrator_llm_node, tool_executor_node, guardrails, graph_builder
- Supports: NVIDIA LLM orchestration, tool binding, state updates, routing

Extracted from orchestrator_langgraph.py to separate active state definition
from legacy sequential orchestrator implementation.
"""

import logging
from typing import Optional, TypedDict, Literal, Any, Dict

logger = logging.getLogger(__name__)


# ============================================================================
# LANGGRAPH STATE DEFINITION
# ============================================================================

class PostCareWorkflowState(TypedDict):
    """
    Typed state for the post-care workflow graph.

    This represents the complete workflow state flowing through all nodes.
    All fields are preserved exactly across nodes (no regeneration).
    
    The state flows through:
    1. orchestrator_llm_node - NVIDIA LLM decides next tool
    2. tool_executor_node - Executes selected tool
    3. State update - Merges tool results
    4. Routing - Determines next action (loop or complete)
    """

    # ========================================================================
    # INPUT DATA
    # ========================================================================

    mrn: str
    patient_id: Optional[str]
    prediction: int
    probability: float
    notes: Optional[str]

    # ========================================================================
    # CARE PLAN PHASE OUTPUT
    # ========================================================================

    care_plan: Optional[Dict[str, Any]]  # CarePlanOutput as dict
    care_plan_id: Optional[str]
    risk_level: Optional[str]
    intensity: Optional[str]
    care_plan_status: Optional[str]

    # ========================================================================
    # FOLLOW-UP PHASE OUTPUT
    # ========================================================================

    follow_up_output: Optional[Dict[str, Any]]
    task_id: Optional[str]
    task_type: Optional[str]
    checkin_id: Optional[str]
    checkin_status: Optional[str]

    # ========================================================================
    # PATIENT RESPONSE (TERMINAL INPUT)
    # ========================================================================

    patient_response: Optional[str]

    # ========================================================================
    # RESPONSE ANALYZER OUTPUT
    # ========================================================================

    response_analyzer_output: Optional[Dict[str, Any]]
    classification: Optional[Literal["NORMAL", "CONCERN", "URGENT", "UNCLEAR"]]
    response_confidence: Optional[float]
    symptoms: Optional[list[str]]
    concerns: Optional[list[str]]

    # ========================================================================
    # CARE CONTINUITY OUTPUT
    # ========================================================================

    care_continuity_output: Optional[Dict[str, Any]]
    continuity_action: Optional[Literal[
        "CONTINUE_FOLLOW_UP",
        "CLINICAL_REVIEW",
        "URGENT_REVIEW",
        "CLARIFICATION_REQUIRED"
    ]]
    requires_human_review: Optional[bool]
    requires_appointment: Optional[bool]

    # ========================================================================
    # WORKFLOW STATE
    # ========================================================================

    workflow_status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "WAITING"]
    current_node: Optional[str]
    next_node: Optional[str]
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]
    
    # ========================================================================
    # ORCHESTRATOR STATE (AGENTIC GRAPH)
    # ========================================================================
    
    orchestrator_decision: Optional[Dict[str, Any]]  # {"tool_name": str, "tool_args": Dict, "reasoning": str}
