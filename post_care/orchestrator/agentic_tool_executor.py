"""
Tool Execution Node for Agentic Orchestrator

This module implements the tool executor node that:
1. Receives LLM's tool call decision from orchestrator
2. Validates tool call against guard rails
3. Maps tool name to actual tool function
4. Executes tool with state arguments
5. Updates state with tool result
6. Handles errors gracefully

The tool executor is the execution engine of the agentic workflow.
It takes decisions from the orchestrator LLM and executes them,
then updates the shared state with results.

Key Features:
- Tool call validation (safety)
- Argument mapping and formatting
- Error handling and propagation
- State update with tool results
- Logging of all executions
"""

import logging
from typing import Any, Dict, Optional

from post_care.orchestrator.workflow_state import PostCareWorkflowState
from post_care.orchestrator.agentic_tools import TOOL_MAPPING
from post_care.orchestrator.agentic_guardrails import (
    validate_tool_call,
    increment_iteration_count,
)

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL EXECUTION NODE
# ============================================================================

def tool_executor_node(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    LangGraph node: Execute the tool selected by orchestrator LLM.
    
    This node:
    1. Receives orchestrator decision from previous node
    2. Validates tool call against guard rails
    3. Maps tool name to function
    4. Executes tool with arguments
    5. Updates state with tool result
    6. Handles errors gracefully
    
    Args:
        state: Current workflow state (PostCareWorkflowState)
    
    Returns:
        Updated state with tool execution results
    
    Expected inputs in state:
    - orchestrator_decision: Dict with tool_name, tool_args, reasoning
    
    State updates:
    - Tool execution results merged into state
    - current_node updated
    - metadata updated with execution info
    - workflow_status updated appropriately
    
    Error handling:
    - If tool call invalid: set error, mark workflow FAILED
    - If tool execution fails: set error, mark workflow FAILED
    - If tool returns error: propagate to state error field
    """
    try:
        logger.info("=== TOOL EXECUTOR NODE STARTING ===")
        
        # Get orchestrator decision
        orchestrator_decision = state.get("orchestrator_decision")
        if not orchestrator_decision:
            error_msg = "No orchestrator decision in state"
            logger.error(error_msg)
            state["error"] = error_msg
            state["workflow_status"] = "FAILED"
            return state
        
        tool_name = orchestrator_decision.get("tool_name")
        tool_args = orchestrator_decision.get("tool_args") or {}
        reasoning = orchestrator_decision.get("reasoning")
        
        logger.info(f"Executing tool: {tool_name}")
        logger.info(f"Tool args from LLM: {tool_args}")
        logger.info(f"Reasoning: {reasoning}")
        
        # Fill in missing arguments from state for certain tools
        # The LLM may not have complete arguments, so we augment them from state
        if tool_name == "call_follow_up_agent":
            # Fill in all required follow-up arguments from state
            # These come from trusted state, not from LLM
            
            # Ensure required fields are present from state
            if "mrn" not in tool_args or not tool_args.get("mrn"):
                tool_args["mrn"] = state.get("mrn")
            
            if "care_plan_id" not in tool_args or not tool_args.get("care_plan_id"):
                tool_args["care_plan_id"] = state.get("care_plan_id")
            
            if "risk_level" not in tool_args or not tool_args.get("risk_level"):
                tool_args["risk_level"] = state.get("risk_level")
            
            if "intensity" not in tool_args or not tool_args.get("intensity"):
                tool_args["intensity"] = state.get("intensity")
            
            # ALWAYS use tasks from care_plan state, NEVER from LLM
            # LLM often hallucinates fake tasks - we must use the real ones from database
            logger.info(f"\nFOLLOW-UP TOOL INPUT CHECK:")
            logger.info(f"  LLM provided tasks: {tool_args.get('tasks', [])} (IGNORING - using state instead)")
            
            care_plan = state.get("care_plan") or {}
            tasks_from_state = care_plan.get("tasks", []) if isinstance(care_plan, dict) else []
            logger.info(f"  Tasks from state['care_plan']['tasks']: {len(tasks_from_state)} tasks")
            
            # Always override with state tasks
            tool_args["tasks"] = tasks_from_state
            logger.info(f"  → tool_args['tasks'] now contains {len(tool_args['tasks'])} tasks from state")
        
        logger.info(f"Tool args after state augmentation: {tool_args}")
        
        # Print detailed follow-up input before execution
        if tool_name == "call_follow_up_agent":
            logger.info(f"\n{'='*70}")
            logger.info(f"FOLLOW-UP TOOL EXECUTION - FINAL INPUT")
            logger.info(f"{'='*70}")
            logger.info(f"  mrn: {tool_args.get('mrn')}")
            logger.info(f"  care_plan_id: {tool_args.get('care_plan_id')}")
            logger.info(f"  risk_level: {tool_args.get('risk_level')}")
            logger.info(f"  intensity: {tool_args.get('intensity')}")
            tasks_list = tool_args.get('tasks', [])
            logger.info(f"  tasks: {tasks_list}")
            logger.info(f"  Task count: {len(tasks_list)}")
            for i, task in enumerate(tasks_list, 1):
                logger.info(f"    Task {i}: {task.get('task_id')} - {task.get('task_type')}")
            logger.info(f"{'='*70}\n")
        
        # Validate tool call
        is_valid, validation_error = validate_tool_call(tool_name, state)
        if not is_valid:
            error_msg = f"Invalid tool call {tool_name}: {validation_error}"
            logger.error(error_msg)
            state["error"] = error_msg
            state["workflow_status"] = "FAILED"
            return state
        
        # Get tool function
        tool_func = TOOL_MAPPING.get(tool_name)
        if not tool_func:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(error_msg)
            state["error"] = error_msg
            state["workflow_status"] = "FAILED"
            return state
        
        logger.info(f"Tool function found: {tool_func}")
        
        # Execute tool
        logger.info(f"Calling tool: {tool_name}")
        tool_result = tool_func.invoke(tool_args)
        
        logger.info(f"Tool execution completed")
        logger.info(f"Tool result: {tool_result}")
        
        # Check for tool-level errors
        if tool_result.get("error"):
            error_msg = f"Tool {tool_name} returned error: {tool_result.get('error')}"
            logger.error(error_msg)
            state["error"] = error_msg
            state["workflow_status"] = "FAILED"
            return state
        
        # Update state based on which tool was executed
        state = _update_state_from_tool_result(tool_name, tool_result, state)
        
        # Update execution metadata
        if state.get("metadata") is None:
            state["metadata"] = {}
        
        metadata = state.get("metadata")
        metadata["last_tool_executed"] = tool_name
        metadata["last_tool_result_keys"] = list(tool_result.keys())
        state["metadata"] = metadata
        
        # Increment iteration counter
        state = increment_iteration_count(state)
        
        # Update workflow status
        state["workflow_status"] = "RUNNING"
        state["current_node"] = "tool_executor"
        
        logger.info(f"=== TOOL EXECUTOR NODE COMPLETE - TOOL: {tool_name} ===")
        return state
        
    except Exception as e:
        logger.error(f"Tool executor node failed: {str(e)}", exc_info=True)
        state["error"] = f"Tool executor error: {str(e)}"
        state["workflow_status"] = "FAILED"
        return state


# ============================================================================
# STATE UPDATE FUNCTIONS
# ============================================================================

def _update_state_from_tool_result(
    tool_name: str,
    tool_result: Dict[str, Any],
    state: PostCareWorkflowState
) -> PostCareWorkflowState:
    """
    Update state based on which tool was executed and its result.
    
    Each tool returns different fields, which are mapped to state.
    This function handles the mapping for each tool type.
    
    Args:
        tool_name: Name of executed tool
        tool_result: Result dict from tool
        state: Current state to update
    
    Returns:
        Updated state
    """
    
    if tool_name == "call_care_plan_agent":
        return _update_state_care_plan(tool_result, state)
    
    elif tool_name == "call_follow_up_agent":
        return _update_state_follow_up(tool_result, state)
    
    elif tool_name == "call_response_analyzer":
        return _update_state_response_analyzer(tool_result, state)
    
    elif tool_name == "call_care_continuity":
        return _update_state_care_continuity(tool_result, state)
    
    else:
        logger.warning(f"Unknown tool for state update: {tool_name}")
        return state


def _update_state_care_plan(
    tool_result: Dict[str, Any],
    state: PostCareWorkflowState
) -> PostCareWorkflowState:
    """
    Update state with Care Plan Agent results.
    
    Maps care plan output fields to state.
    """
    logger.info("Updating state from care_plan_agent result")
    logger.info(f"  Tool result keys: {list(tool_result.keys())}")
    logger.info(f"  Tasks in result: {tool_result.get('tasks', [])}")
    
    state["care_plan"] = tool_result
    state["mrn"] = tool_result.get("mrn", state.get("mrn"))
    state["patient_id"] = tool_result.get("patient_id")
    state["care_plan_id"] = tool_result.get("care_plan_id")
    state["risk_level"] = tool_result.get("risk_level")
    state["intensity"] = tool_result.get("intensity")
    state["care_plan_status"] = tool_result.get("status")
    
    logger.info(f"State updated: care_plan_id={state.get('care_plan_id')}, risk={state.get('risk_level')}")
    logger.info(f"State['care_plan']: {state.get('care_plan')}")
    logger.info(f"State['care_plan']['tasks']: {state.get('care_plan', {}).get('tasks', [])}")
    return state


def _update_state_follow_up(
    tool_result: Dict[str, Any],
    state: PostCareWorkflowState
) -> PostCareWorkflowState:
    """
    Update state with Follow-Up Agent results.
    
    Maps follow-up output fields to state.
    """
    logger.info("Updating state from follow_up_agent result")
    
    state["follow_up_output"] = tool_result
    state["mrn"] = tool_result.get("mrn", state.get("mrn"))
    state["care_plan_id"] = tool_result.get("care_plan_id", state.get("care_plan_id"))
    state["task_id"] = tool_result.get("task_id")
    state["checkin_id"] = tool_result.get("checkin_id")
    
    # Extract follow-up details
    follow_up = tool_result.get("follow_up") or {}
    state["task_type"] = follow_up.get("task_type", state.get("task_type"))
    state["checkin_status"] = follow_up.get("status")
    
    logger.info(f"State updated: task_id={state.get('task_id')}, checkin_id={state.get('checkin_id')}")
    return state


def _update_state_response_analyzer(
    tool_result: Dict[str, Any],
    state: PostCareWorkflowState
) -> PostCareWorkflowState:
    """
    Update state with Response Analyzer Agent results.
    
    Maps response analysis output fields to state.
    """
    logger.info("Updating state from response_analyzer result")
    
    state["response_analyzer_output"] = tool_result
    state["mrn"] = tool_result.get("mrn", state.get("mrn"))
    state["care_plan_id"] = tool_result.get("care_plan_id", state.get("care_plan_id"))
    state["task_id"] = tool_result.get("task_id", state.get("task_id"))
    state["checkin_id"] = tool_result.get("checkin_id", state.get("checkin_id"))
    
    # Map analysis results
    state["classification"] = tool_result.get("classification")
    state["response_confidence"] = tool_result.get("confidence")
    state["symptoms"] = tool_result.get("symptoms", [])
    state["concerns"] = tool_result.get("concerns", [])
    
    logger.info(f"State updated: classification={state.get('classification')}, confidence={state.get('response_confidence')}")
    return state


def _update_state_care_continuity(
    tool_result: Dict[str, Any],
    state: PostCareWorkflowState
) -> PostCareWorkflowState:
    """
    Update state with Care Continuity Agent results.
    
    Maps continuity output fields to state (final phase).
    """
    logger.info("Updating state from care_continuity result")
    
    state["care_continuity_output"] = tool_result
    state["mrn"] = tool_result.get("mrn", state.get("mrn"))
    state["care_plan_id"] = tool_result.get("care_plan_id", state.get("care_plan_id"))
    state["task_id"] = tool_result.get("task_id", state.get("task_id"))
    state["checkin_id"] = tool_result.get("checkin_id", state.get("checkin_id"))
    
    # Map continuity decision
    state["continuity_action"] = tool_result.get("continuity_action")
    state["requires_human_review"] = tool_result.get("requires_human_review")
    state["requires_appointment"] = tool_result.get("requires_appointment")
    
    logger.info(f"State updated: continuity_action={state.get('continuity_action')}")
    return state


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_tool_execution_error(state: PostCareWorkflowState) -> bool:
    """
    Check if tool execution resulted in error.
    
    Returns True if state has error field set.
    """
    return state.get("error") is not None


def get_last_tool_executed(state: PostCareWorkflowState) -> Optional[str]:
    """
    Get the name of the last tool executed.
    
    Returns tool name from metadata or None.
    """
    metadata = state.get("metadata") or {}
    return metadata.get("last_tool_executed")


def format_tool_execution_summary(state: PostCareWorkflowState) -> str:
    """
    Format a human-readable summary of tool execution.
    
    Returns formatted string for logging.
    """
    last_tool = get_last_tool_executed(state)
    metadata = state.get("metadata") or {}
    result_keys = metadata.get("last_tool_result_keys", [])
    
    summary = f"Tool Execution: {last_tool}"
    if result_keys:
        summary += f"\n  Result keys: {', '.join(result_keys)}"
    
    return summary
