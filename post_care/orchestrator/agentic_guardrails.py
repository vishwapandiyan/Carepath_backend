"""
Safety Validator for Agentic Orchestrator

This module implements post-selection safety validation.

When the LLM selects a tool, this validator checks if the tool can safely
execute with the current state. It does NOT pre-filter which tools the LLM
can see.

IMPORTANT: This is POST-SELECTION validation, not pre-filtering.
- LLM sees ALL approved tools
- LLM selects a tool based on state
- Validator checks if selection is safe
- If invalid, tool is rejected and not executed

The distinction:
- PRE-FILTER: "What tools can LLM choose from?" (deterministic workflow)
- POST-SELECT: "Is this LLM choice safe?" (LLM-driven workflow)

This module implements POST-SELECT validation.

Validation ensures:
1. Required fields exist for the tool
2. State is consistent for execution
3. No duplicate analysis or routing
4. Sequencing constraints met (if any)
5. Safety constraints enforced
"""

import logging
from typing import Dict, List, Any, Optional
from post_care.orchestrator.workflow_state import PostCareWorkflowState

logger = logging.getLogger(__name__)


# ============================================================================
# GUARD RAIL FUNCTIONS
# ============================================================================

def get_available_tools(state: PostCareWorkflowState) -> List[str]:
    """
    Determine which tools are available based on current state.
    
    This implements guard rails to prevent calling tools without their
    required dependencies. Returns only tool names that can safely be called.
    
    Guard Rail Rules:
    ─────────────────
    
    1. care_plan_agent: Always available (entry point, no dependencies)
    
    2. follow_up_agent: Only if care_plan exists
       - Requires: care_plan_id in state
       - Prevents: calling follow-up without care plan
    
    3. response_analyzer: Only if care_plan + follow_up + patient_response
       - Requires: patient_response, care_plan, follow_up_output
       - Prevents: analyzing without follow-up context
       - Prevents: calling again if already analyzed
    
    4. care_continuity: Only if response_analyzer completed
       - Requires: response_analyzer_output with classification
       - Prevents: routing without analysis
       - Prevents: calling again if already determined
    
    Args:
        state: Current workflow state (PostCareWorkflowState)
    
    Returns:
        List of available tool names that can be safely called
    
    Example:
        available = get_available_tools(state)
        # Returns: ["call_care_plan_agent", "call_follow_up_agent"]
        # If no follow_up yet, response_analyzer and care_continuity excluded
    """
    available_tools = []
    
    # Rule 1: care_plan_agent always available (entry point)
    available_tools.append("call_care_plan_agent")
    logger.debug("Guard rail: care_plan_agent AVAILABLE (always)")
    
    # Rule 2: follow_up_agent only if care_plan exists
    if state.get("care_plan_id") is not None:
        available_tools.append("call_follow_up_agent")
        logger.debug("Guard rail: follow_up_agent AVAILABLE (care_plan exists)")
    else:
        logger.debug("Guard rail: follow_up_agent NOT available (missing care_plan)")
    
    # Rule 3: response_analyzer only if care_plan + follow_up + patient_response
    # AND not already analyzed
    if (state.get("care_plan_id") is not None and
        state.get("follow_up_output") is not None and
        state.get("patient_response") is not None and
        state.get("response_analyzer_output") is None):
        available_tools.append("call_response_analyzer")
        logger.debug("Guard rail: response_analyzer AVAILABLE (all deps met, not analyzed yet)")
    else:
        reasons = []
        if state.get("care_plan_id") is None:
            reasons.append("missing care_plan")
        if state.get("follow_up_output") is None:
            reasons.append("missing follow_up_output")
        if state.get("patient_response") is None:
            reasons.append("missing patient_response")
        if state.get("response_analyzer_output") is not None:
            reasons.append("already analyzed")
        logger.debug(f"Guard rail: response_analyzer NOT available ({', '.join(reasons)})")
    
    # Rule 4: care_continuity only if response_analyzer completed
    # AND not already determined
    if (state.get("response_analyzer_output") is not None and
        state.get("continuity_action") is None):
        available_tools.append("call_care_continuity")
        logger.debug("Guard rail: care_continuity AVAILABLE (analysis complete, action not determined)")
    else:
        reasons = []
        if state.get("response_analyzer_output") is None:
            reasons.append("missing response_analyzer_output")
        if state.get("continuity_action") is not None:
            reasons.append("action already determined")
        logger.debug(f"Guard rail: care_continuity NOT available ({', '.join(reasons)})")
    
    logger.info(f"Guard rails: Available tools = {available_tools}")
    return available_tools


def validate_tool_call(tool_name: str, state: PostCareWorkflowState) -> tuple[bool, Optional[str]]:
    """
    POST-SELECTION SAFETY VALIDATOR with PROGRESS PROTECTION.
    
    Validates if a specific tool can be safely called with current state.
    
    This is NOT a pre-filter. It runs AFTER the LLM selects a tool.
    It validates if the selection is safe given current state.
    
    NEW: Progress Protection - Prevents LLM from repeatedly calling completed phases.
    If a phase is already completed and its work is done, validator rejects the call
    and returns clear guidance to LLM about what should be called next.
    
    If validation fails:
    - Tool is NOT executed
    - Error is returned to orchestrator
    - LLM must make another selection based on updated context
    
    Args:
        tool_name: Name of tool that LLM selected
        state: Current workflow state
    
    Returns:
        Tuple of (is_valid: bool, reason: Optional[str])
        If invalid, reason explains why tool cannot execute
    """
    
    # No pre-filtering check - we accept any approved tool name
    # We validate if it can safely execute with current state
    
    if tool_name == "call_care_plan_agent":
        # Required fields check
        if state.get("mrn") is None:
            return False, "care_plan_agent requires: mrn"
        if state.get("prediction") is None:
            return False, "care_plan_agent requires: prediction"
        if state.get("probability") is None:
            return False, "care_plan_agent requires: probability"
        
        # PROGRESS PROTECTION: Check if care plan already completed
        if state.get("care_plan_id") and state.get("care_plan"):
            # Care plan exists and is active - should not be called again
            return False, "Invalid action. The care plan already exists and does not require regeneration in the current workflow state. Re-evaluate the current state and available tools before selecting another action."
        
        return True, None
    
    elif tool_name == "call_follow_up_agent":
        if state.get("care_plan_id") is None:
            return False, "follow_up_agent requires: care_plan_id"
        if state.get("risk_level") is None:
            return False, "follow_up_agent requires: risk_level"
        if state.get("intensity") is None:
            return False, "follow_up_agent requires: intensity"
        if "care_plan" not in state or state.get("care_plan") is None:
            return False, "follow_up_agent requires: care_plan with tasks"
        
        # PROGRESS PROTECTION: Check if follow-up already completed
        if state.get("follow_up_output"):
            return False, "Invalid action. Follow-up has already been scheduled and completed in the current workflow state. Re-evaluate the current state and available tools before selecting another action."
        
        return True, None
    
    elif tool_name == "call_response_analyzer":
        # LLM-DRIVEN: Allow if response exists (not just after follow_up_output set)
        # This enables response analysis earlier if response is ready
        if state.get("patient_response") is None:
            return False, "response_analyzer requires patient_response (not None)"
        if state.get("patient_response") == "":
            return False, "response_analyzer requires patient_response (not empty string)"
        if state.get("task_id") is None:
            return False, "response_analyzer requires: task_id"
        if state.get("checkin_id") is None:
            return False, "response_analyzer requires: checkin_id"
        
        # PROGRESS PROTECTION: Check if response already analyzed
        if state.get("response_analyzer_output") is not None:
            return False, "Invalid action. Patient response has already been analyzed in the current workflow state. Re-evaluate the current state and available tools before selecting another action."
        
        return True, None
    
    elif tool_name == "call_care_continuity":
        if state.get("care_plan_id") is None:
            return False, "care_continuity requires: care_plan_id"
        if state.get("response_analyzer_output") is None:
            return False, "care_continuity requires: response_analyzer_output"
        if state.get("classification") is None:
            return False, "care_continuity requires: classification"
        
        # PROGRESS PROTECTION: Check if continuity already determined
        if state.get("continuity_action") is not None:
            return False, "Invalid action. Care continuity decision has already been determined in the current workflow state. Workflow is complete."
        
        return True, None
    
    elif tool_name == "wait_for_patient_response":
        if state.get("mrn") is None:
            return False, "wait_for_patient_response requires: mrn"
        if state.get("care_plan_id") is None:
            return False, "wait_for_patient_response requires: care_plan_id"
        if state.get("follow_up_output") is None:
            return False, "wait_for_patient_response requires: follow_up scheduled"
        if state.get("patient_response") is not None:
            return False, "patient has already responded"
        return True, None
    
    # Unknown tool
    return False, f"Unknown tool: {tool_name}"


def detect_loop(state: PostCareWorkflowState, tool_name: str) -> tuple[bool, Optional[str]]:
    """
    Detect if the LLM is stuck in a loop selecting the same tool repeatedly.
    
    This prevents infinite loops where the LLM keeps calling the same tool
    without making progress in the workflow.
    
    Args:
        state: Current workflow state
        tool_name: Tool that LLM just selected
    
    Returns:
        Tuple of (is_loop: bool, reason: Optional[str])
        If loop detected, reason explains the loop pattern
    """
    metadata = state.get("metadata") or {}
    
    # Track recent tool selections
    recent_tools = metadata.get("recent_tool_selections", [])
    
    # Add current selection
    recent_tools.append(tool_name)
    
    # Keep only last 5 selections
    if len(recent_tools) > 5:
        recent_tools = recent_tools[-5:]
    
    # Update metadata
    metadata["recent_tool_selections"] = recent_tools
    state["metadata"] = metadata
    
    # Check for loop: same tool called 3+ times in last 5 selections
    if len(recent_tools) >= 3:
        # Count occurrences of current tool in recent selections
        count = sum(1 for t in recent_tools[-3:] if t == tool_name)
        
        if count >= 3:
            return True, f"Loop detected: {tool_name} called {count} times consecutively without progress"
    
    return False, None


def build_state_summary(state: PostCareWorkflowState) -> str:
    """
    Convert workflow state to extremely explicit structured summary for LLM.
    
    This summary makes the workflow state crystal clear to the LLM orchestrator:
    - Each phase has explicit STATUS (COMPLETED | NOT_STARTED | IN_PROGRESS)
    - Shows exactly what data exists and what is missing
    - Identifies the current workflow stage explicitly
    - Prevents LLM from repeatedly calling completed phases
    
    Args:
        state: Current workflow state
    
    Returns:
        Structured state summary optimized for LLM decision-making
    """
    summary_parts = []
    
    # Header
    mrn = state.get("mrn", "UNKNOWN")
    summary_parts.append(f"=== WORKFLOW STATE FOR PATIENT {mrn} ===\n")
    
    # Input data
    summary_parts.append("PATIENT INPUT:")
    summary_parts.append(f"  MRN: {mrn}")
    summary_parts.append(f"  Readmission Prediction: {state.get('prediction')}")
    summary_parts.append(f"  Readmission Probability: {state.get('probability'):.2%}")
    
    # PHASE 1: Care Plan
    summary_parts.append("\n--- PHASE 1: CARE PLAN ---")
    if state.get("care_plan_id"):
        care_plan = state.get("care_plan") or {}
        num_tasks = len(care_plan.get("tasks", [])) if isinstance(care_plan, dict) else 0
        summary_parts.append(f"  Status: COMPLETED ✓")
        summary_parts.append(f"  Care Plan ID: {state.get('care_plan_id')}")
        summary_parts.append(f"  Risk Level: {state.get('risk_level')} (PROTECTED - do not modify)")
        summary_parts.append(f"  Intensity: {state.get('intensity')} (PROTECTED - do not modify)")
        summary_parts.append(f"  Tasks Available: {num_tasks} tasks")
        summary_parts.append(f"  → Care plan exists and is active. Do not call call_care_plan_agent again.")
    else:
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Care Plan ID: None")
        summary_parts.append(f"  → Care plan must be created first using call_care_plan_agent")
    
    # PHASE 2: Follow-Up
    summary_parts.append("\n--- PHASE 2: FOLLOW-UP SCHEDULING ---")
    if state.get("follow_up_output"):
        summary_parts.append(f"  Status: COMPLETED ✓")
        summary_parts.append(f"  Task ID: {state.get('task_id')}")
        summary_parts.append(f"  Check-in ID: {state.get('checkin_id')}")
        summary_parts.append(f"  → Follow-up scheduled. Do not call call_follow_up_agent again.")
    elif state.get("care_plan_id"):
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Dependencies Met: Yes (care plan exists)")
    else:
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Dependencies Met: No (requires care plan first)")
    
    # PHASE 3: Patient Response
    summary_parts.append("\n--- PHASE 3: PATIENT RESPONSE ---")
    if state.get("patient_response"):
        response_preview = state.get("patient_response", "")[:80]
        summary_parts.append(f"  Status: AVAILABLE ✓")
        summary_parts.append(f"  Response: \"{response_preview}...\"")
        summary_parts.append(f"  → Patient has responded. Ready for analysis once follow-up scheduled.")
    else:
        summary_parts.append(f"  Status: NOT_RECEIVED")
        summary_parts.append(f"  → Waiting for patient to respond to follow-up")
    
    # PHASE 4: Response Analysis
    summary_parts.append("\n--- PHASE 4: RESPONSE ANALYSIS ---")
    if state.get("response_analyzer_output"):
        summary_parts.append(f"  Status: COMPLETED ✓")
        summary_parts.append(f"  Classification: {state.get('classification')}")
        summary_parts.append(f"  Confidence: {state.get('response_confidence', 0.0):.2%}")
        summary_parts.append(f"  → Response analyzed. Do not call call_response_analyzer again.")
    elif state.get("follow_up_output") and state.get("patient_response"):
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Dependencies Met: Yes (follow-up scheduled + patient responded)")
    else:
        summary_parts.append(f"  Status: NOT_STARTED")
        missing = []
        if not state.get("follow_up_output"):
            missing.append("follow-up not scheduled")
        if not state.get("patient_response"):
            missing.append("patient has not responded")
        summary_parts.append(f"  Dependencies Met: No ({', '.join(missing)})")
    
    # PHASE 5: Care Continuity
    summary_parts.append("\n--- PHASE 5: CARE CONTINUITY DECISION ---")
    if state.get("continuity_action"):
        summary_parts.append(f"  Status: COMPLETED ✓")
        summary_parts.append(f"  Continuity Action: {state.get('continuity_action')}")
        summary_parts.append(f"  Requires Review: {state.get('requires_human_review', False)}")
        summary_parts.append(f"  → Continuity determined. Workflow complete.")
    elif state.get("response_analyzer_output"):
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Dependencies Met: Yes (response analyzed)")
    else:
        summary_parts.append(f"  Status: NOT_STARTED")
        summary_parts.append(f"  Dependencies Met: No (response not analyzed)")
    
    # Current workflow stage
    summary_parts.append("\n=== CURRENT WORKFLOW STAGE ===")
    if state.get("continuity_action"):
        summary_parts.append("  WORKFLOW COMPLETE")
    elif state.get("response_analyzer_output"):
        summary_parts.append("  STAGE: Care Continuity Decision Pending")
    elif state.get("follow_up_output") and state.get("patient_response"):
        summary_parts.append("  STAGE: Response Analysis Pending")
    elif state.get("care_plan_id") and not state.get("follow_up_output"):
        summary_parts.append("  STAGE: Follow-Up Scheduling Pending")
    elif not state.get("care_plan_id"):
        summary_parts.append("  STAGE: Care Plan Creation Pending")
    else:
        summary_parts.append("  STAGE: Waiting for patient response")
    
    return "\n".join(summary_parts)


def get_tool_description(tool_name: str) -> str:
    """
    Get human-readable description of a tool.
    
    Used to help the LLM understand what each tool does and when to use it.
    
    Args:
        tool_name: Name of the tool
    
    Returns:
        Description of the tool
    
    Example:
        desc = get_tool_description("call_care_plan_agent")
        # Returns: "Care Plan Agent: Creates or retrieves a care plan..."
    """
    descriptions = {
        "call_care_plan_agent": (
            "Care Plan Agent: Creates or retrieves an ACTIVE care plan for the patient. "
            "Determines risk level (HIGH/MODERATE/LOW), intensity (INTENSIVE/REGULAR/BASIC), "
            "and generates personalized care tasks. If an ACTIVE plan already exists for this "
            "patient, it reuses that plan. "
            "USE WHEN: No care plan exists yet (care_plan_id is None). "
            "DO NOT USE: If care plan already exists and is COMPLETED - select the next phase instead."
        ),
        "call_follow_up_agent": (
            "Follow-Up Agent: Schedules a patient check-in by selecting the next actionable task "
            "from the existing care plan and creating/reusing check-in records. Requires an existing "
            "ACTIVE care plan with tasks. "
            "USE WHEN: Care plan exists (COMPLETED) but follow-up has NOT been scheduled yet. "
            "DO NOT USE: If follow-up already COMPLETED - select response analysis instead."
        ),
        "call_response_analyzer": (
            "Response Analyzer Agent: Analyzes patient's natural language response using Groq LLM. "
            "Classifies response as NORMAL|CONCERN|URGENT|UNCLEAR. This tool makes ONE external LLM call. "
            "USE WHEN: Follow-up is scheduled (COMPLETED) AND patient response is available AND "
            "response has NOT been analyzed yet. "
            "DO NOT USE: If response already analyzed (COMPLETED) - select care continuity instead."
        ),
        "call_care_continuity": (
            "Care Continuity Agent: Determines the next workflow phase based on the response classification. "
            "Routes to: CONTINUE_FOLLOW_UP | CLINICAL_REVIEW | URGENT_REVIEW | CLARIFICATION_REQUIRED. "
            "This is deterministic routing based on classification from response analyzer. "
            "USE WHEN: Response has been analyzed (COMPLETED) AND continuity action has NOT been determined yet. "
            "DO NOT USE: If continuity action already determined (COMPLETED) - workflow is complete."
        ),
    }
    return descriptions.get(tool_name, f"Unknown tool: {tool_name}")


def get_tools_description_for_llm(available_tools: List[str]) -> str:
    """
    Get formatted descriptions of available tools for LLM prompt.
    
    Args:
        available_tools: List of available tool names
    
    Returns:
        Formatted string describing available tools
    """
    parts = ["AVAILABLE TOOLS:\n"]
    for tool in available_tools:
        desc = get_tool_description(tool)
        parts.append(f"• {tool}:")
        parts.append(f"  {desc}\n")
    return "\n".join(parts)


# ============================================================================
# STOPPING CONDITION CHECKS
# ============================================================================

def check_stopping_condition(state: PostCareWorkflowState) -> tuple[bool, Optional[str]]:
    """
    Check if workflow should stop.
    
    Returns (should_stop: bool, reason: Optional[str])
    
    Stopping conditions:
    1. continuity_action determined (workflow complete)
    2. error encountered (workflow failed)
    3. max_iterations exceeded (safety limit)
    """
    # Condition 1: continuity_action determined (success)
    if state.get("continuity_action") is not None:
        return True, f"Workflow complete - continuity action determined: {state.get('continuity_action')}"
    
    # Condition 2: error encountered (failure)
    if state.get("error") is not None:
        return True, f"Workflow failed - error: {state.get('error')}"
    
    # Condition 3: max iterations (safety)
    metadata = state.get("metadata") or {}
    iterations = metadata.get("orchestrator_iterations", 0)
    max_iterations = 10  # Safety limit
    if iterations >= max_iterations:
        return True, f"Max iterations reached ({max_iterations})"
    
    return False, None


def increment_iteration_count(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    Increment the orchestrator iteration counter in metadata.
    
    Used for safety limit detection.
    """
    if state.get("metadata") is None:
        state["metadata"] = {}
    
    metadata = state.get("metadata") or {}
    metadata["orchestrator_iterations"] = metadata.get("orchestrator_iterations", 0) + 1
    state["metadata"] = metadata
    
    return state
