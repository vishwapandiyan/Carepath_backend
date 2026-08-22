"""
Orchestrator LLM Node for Agentic Workflow Control

This module implements the orchestrator LLM node that:
1. Builds state summary from workflow state
2. Determines available tools based on guard rails
3. Calls OpenRouter LLM with LangChain tool binding (migrated from Groq)
4. Gets LLM decision on next tool to call
5. Returns orchestrated tool call decision

The orchestrator LLM is the brain of the agentic workflow.
It decides what action to take next based on current state and available tools.

MIGRATION NOTE:
- Migrated from Groq (ChatGroq) to OpenRouter (ChatOpenAI)
- Uses same LangChain tool binding mechanism
- native AIMessage.tool_calls still required
- All 4 existing agents remain unchanged

Key Features:
- Uses OpenRouter for deterministic decisions (low temperature)
- Tool binding via LangChain (automatic tool calling)
- Guard rail integration (only available tools offered to LLM)
- Structured state summary for LLM context
- Clear reasoning prompt template
"""

import logging
import json
from typing import Any, Dict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool

from post_care.orchestrator.workflow_state import PostCareWorkflowState
from post_care.orchestrator.agentic_tools import ALL_TOOLS, TOOL_MAPPING
from post_care.orchestrator.agentic_guardrails import (
    get_available_tools,
    build_state_summary,
    get_tools_description_for_llm,
    validate_tool_call,
)

logger = logging.getLogger(__name__)


# ============================================================================
# LLM INITIALIZATION - NVIDIA PRIMARY, OPENROUTER FALLBACK
# ============================================================================

# PRIMARY: NVIDIA API (Nemotron model)
PRIMARY_ORCHESTRATOR_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
PRIMARY_ORCHESTRATOR_PROVIDER = "NVIDIA"
PRIMARY_BASE_URL = "https://integrate.api.nvidia.com/v1"

# FALLBACK MODELS: OpenRouter
FALLBACK_ORCHESTRATOR_MODELS = [
    {
        "model": "openai/gpt-oss-120b",
        "provider": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1"
    },
    {
        "model": "google/gemini-2.5-flash",
        "provider": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1"
    }
]

def initialize_orchestrator_llm(
    model_name: str = PRIMARY_ORCHESTRATOR_MODEL,
    base_url: str = PRIMARY_BASE_URL,
    api_key_env: str = "NVIDIA_API_KEY"
) -> ChatOpenAI:
    """
    Initialize the ChatOpenAI LLM for orchestration.
    
    Configuration:
    - PRIMARY Provider: NVIDIA API
    - PRIMARY Base URL: https://integrate.api.nvidia.com/v1
    - PRIMARY Model: nvidia/nemotron-3.5-lightning-30b-a3b
    - FALLBACK 1: OpenRouter (openai/gpt-oss-120b)
    - FALLBACK 2: OpenRouter (google/gemini-2.5-flash)
    - Temperature: 0.3 (low, deterministic decisions)
    - Max tokens: 2048 (sufficient for tool calling)
    - Timeout: 30 seconds
    
    Args:
        model_name: Model to use (default: nvidia/nemotron-3.5-lightning-30b-a3b)
        base_url: API base URL (default: NVIDIA API)
        api_key_env: Environment variable name for API key (default: NVIDIA_API_KEY)
    
    Returns:
        ChatOpenAI instance ready for tool calling
    
    Note:
    - Uses native AIMessage.tool_calls (no fallback parsing)
    - bind_tools() enables tool calling
    - tool_choice="required" forces the model to return tool_calls
    - No reasoning_content or message.content parsing
    """
    import os
    from dotenv import load_dotenv
    
    # Load .env if not already loaded
    load_dotenv()
    
    try:
        # Get API key from environment
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"{api_key_env} not found in environment")
        
        # Determine provider for logging
        provider = "NVIDIA" if "nvidia" in base_url else "OpenRouter"
        
        logger.info(f"Initializing ChatOpenAI for orchestration")
        logger.info(f"  Model: {model_name}")
        logger.info(f"  Provider: {provider}")
        logger.info(f"  Base URL: {base_url}")
        logger.info(f"  Temperature: 0.3 (deterministic)")
        logger.info(f"  Max tokens: 2048 (tool calling)")
        logger.info(f"  tool_choice: required (forces native tool_calls)")
        
        llm = ChatOpenAI(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,  # Deterministic (not creative)
            max_tokens=2048,  # Sufficient for tool calling
            request_timeout=30,
        )
        
        logger.info(f"✓ Successfully initialized ChatOpenAI with {model_name} via {provider}")
        return llm
        
    except Exception as e:
        error_msg = f"Failed to initialize ChatOpenAI: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def _is_transient_error(error: Exception) -> bool:
    """
    Check if an error is transient (should trigger fallback).
    
    Transient errors:
    - HTTP 429 (Rate Limited)
    - HTTP 5xx (Server errors)
    - Timeout errors
    - Connection errors
    
    Permanent errors (no fallback):
    - Invalid API key
    - Invalid model name
    - Invalid tool schema
    
    Args:
        error: Exception to check
    
    Returns:
        True if transient, False if permanent
    """
    error_str = str(error).lower()
    
    # Check for transient error patterns
    transient_patterns = [
        "429",  # Rate limit
        "500", "501", "502", "503", "504",  # Server errors
        "timeout",  # Timeout
        "connection",  # Connection error
        "temporarily",  # Temporary issue
        "unavailable",  # Service unavailable
    ]
    
    for pattern in transient_patterns:
        if pattern in error_str:
            return True
    
    return False


def call_orchestrator_llm_with_fallback(
    llm_with_tools,
    prompt: str,
    primary_model: str = PRIMARY_ORCHESTRATOR_MODEL,
    primary_provider: str = PRIMARY_ORCHESTRATOR_PROVIDER
) -> Any:
    """
    Call orchestrator LLM with automatic fallback on transient errors.
    
    Implements safe fallback strategy:
    1. Try primary model (NVIDIA Nemotron)
    2. If transient error (429, timeout, 5xx): try OpenRouter fallback models
    3. If permanent error or all fail: return error state
    
    Args:
        llm_with_tools: LLM with bound tools from primary model
        prompt: LLM prompt (state summary + tool descriptions)
        primary_model: Primary model name for logging
        primary_provider: Primary provider name for logging
    
    Returns:
        LLM response (AIMessage with tool_calls) or raises error
    
    Raises:
        RuntimeError: If all models fail with permanent errors
        Exception: If all models fail with transient errors
    """
    logger.info(f"[ORCHESTRATOR MODEL]")
    logger.info(f"  Primary: {primary_model}")
    logger.info(f"  Provider: {primary_provider}")
    
    # Try primary model
    try:
        logger.info(f"  Attempting primary model: {primary_model}")
        response = llm_with_tools.invoke([HumanMessage(content=prompt)])
        logger.info(f"  ✓ Primary model succeeded")
        return response
    
    except Exception as e:
        error_str = str(e)
        logger.warning(f"  Primary model failed: {error_str[:100]}...")
        
        # Check if this is a transient error
        if not _is_transient_error(e):
            # Permanent error - don't try fallback
            logger.error(f"  Permanent error detected. Not attempting fallback.")
            raise
        
        logger.warning(f"  Transient error detected. Attempting fallback models...")
        return _try_fallback_orchestrator_llm(prompt)


def _try_fallback_orchestrator_llm(prompt: str) -> Any:
    """
    Try fallback orchestrator models via OpenRouter.
    
    This is only called if the primary NVIDIA model fails with a transient error.
    
    Fallback order:
    1. OpenRouter (openai/gpt-oss-120b)
    2. OpenRouter (google/gemini-2.5-flash)
    
    Args:
        prompt: LLM prompt
    
    Returns:
        LLM response (AIMessage with tool_calls)
    
    Raises:
        RuntimeError: If all fallback models fail or don't support tool calling
    """
    from langchain_core.tools import tool
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Try OpenRouter fallback models
    for fallback_config in FALLBACK_ORCHESTRATOR_MODELS:
        fallback_model = fallback_config["model"]
        fallback_provider = fallback_config["provider"]
        fallback_base_url = fallback_config["base_url"]
        
        try:
            logger.info(f"  Fallback attempt: {fallback_model} ({fallback_provider})")
            
            # Get OpenRouter API key
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
            if not openrouter_api_key:
                logger.warning(f"  OPENROUTER_API_KEY not set, skipping OpenRouter fallback")
                continue
            
            # Initialize fallback model
            fallback_llm = initialize_orchestrator_llm(
                model_name=fallback_model,
                base_url=fallback_base_url,
                api_key_env="OPENROUTER_API_KEY"
            )
            
            # Bind tools to fallback model
            fallback_llm_with_tools = fallback_llm.bind_tools(ALL_TOOLS, tool_choice="required")
            
            # Try invoking
            response = fallback_llm_with_tools.invoke([HumanMessage(content=prompt)])
            
            # Verify we got native tool_calls (not reasoning_content)
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                logger.warning(f"  Fallback model {fallback_model} did not return native tool_calls")
                continue
            
            logger.info(f"  ✓ Fallback model {fallback_model} succeeded with native tool_calls")
            logger.info(f"  Fallback model: {fallback_model}")
            logger.info(f"  Fallback provider: {fallback_provider}")
            logger.info(f"  Fallback native tool_calls: YES")
            return response
        
        except Exception as fe:
            logger.warning(f"  Fallback model {fallback_model} failed: {str(fe)[:100]}...")
            continue
    
    # All fallback models failed
    error_msg = f"All fallback orchestrator models failed. Primary: {PRIMARY_ORCHESTRATOR_MODEL} ({PRIMARY_ORCHESTRATOR_PROVIDER}). OpenRouter Fallbacks: {[f['model'] for f in FALLBACK_ORCHESTRATOR_MODELS]}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


# ============================================================================
# ORCHESTRATOR LLM NODE
# ============================================================================

def orchestrator_llm_node(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    LangGraph node: Orchestrator LLM decides next tool to call.
    
    This node:
    1. Builds natural language summary of current state
    2. Determines available tools based on guard rails
    3. Calls ChatGroq with available tools bound
    4. Gets LLM decision on next tool to call
    5. Validates tool call against guard rails
    6. Returns decision for tool executor node
    
    Args:
        state: Current workflow state (PostCareWorkflowState)
    
    Returns:
        Updated state with orchestrator_decision field:
        {
            ... (all state fields preserved) ...
            "orchestrator_decision": {
                "tool_name": str (name of tool to call),
                "tool_args": Dict (arguments for tool),
                "reasoning": str (LLM explanation),
            },
            ... (state for routing)
        }
    
    Flow:
        Step 1: Build state summary
        Step 2: Get available tools
        Step 3: Create LLM with tool binding
        Step 4: Call LLM
        Step 5: Parse LLM response
        Step 6: Validate tool call
        Step 7: Return full updated state
    """
    try:
        logger.info("=== ORCHESTRATOR LLM NODE STARTING ===")
        
        # Step 1: Build state summary
        state_summary = build_state_summary(state)
        logger.debug(f"State summary:\n{state_summary}")
        
        # Step 2: Get all approved high-level tools (no pre-filtering)
        # All tools are shown to LLM - LLM decides which is appropriate based on state
        logger.info(f"Approved high-level tools for LLM:")
        for tool in ALL_TOOLS:
            logger.info(f"  • {tool.name}")
        logger.info(f"(LLM will select from all {len(ALL_TOOLS)} approved tools)")
        
        # Step 3: No pre-filtering - pass all tools directly to LLM
        # Tool validation will happen AFTER LLM selection (post-selection validator)
        
        # Step 4: Initialize LLM with ALL approved tools (no filtering)
        llm = initialize_orchestrator_llm()
        
        # Bind tools and set tool_choice="required" to force native tool_calls
        llm_with_tools = llm.bind_tools(ALL_TOOLS, tool_choice="required")
        
        # Step 5: Build prompt
        tools_description = get_tools_description_for_llm([t.name for t in ALL_TOOLS])
        
        prompt = f"""You are the workflow coordinator for a post-care patient monitoring system.

Inspect the complete current workflow state and determine the most appropriate next action toward the patient's care objective.

You have access to all available tools. Do not assume a fixed ordering of tools.

Choose an action based on:
- Current patient state and completed work
- Pending work and available information
- Prerequisites and dependencies
- Patient response availability
- Urgency and risk level
- The current care objective

CRITICAL RULES:
1. Inspect the COMPLETE workflow state before selecting a tool
2. Do NOT repeatedly select a tool whose work has already been completed
3. Use the explicit phase statuses (COMPLETED vs NOT_STARTED) to guide your decision
4. When a phase shows "COMPLETED ✓", do NOT select that tool again
5. Do NOT modify PROTECTED fields (risk_level, intensity, care_plan_id, task assignments)
6. A previously completed action should not be repeated unless the current state provides a valid reason for doing so
7. After each tool execution, the workflow state may change - re-evaluate the updated state before selecting the next action

WORKFLOW STATE ANALYSIS:
{state_summary}

{tools_description}

Based on the workflow state above, determine the most appropriate next action.
The next action must be determined from the current state, not from a predefined sequence."""
        
        logger.info(f"Calling LLM with tool_choice='required' (forces native AIMessage.tool_calls)...")
        
        # Step 6: Call LLM with fallback strategy
        response = None
        try:
            response = llm_with_tools.invoke([HumanMessage(content=prompt)])
            logger.info(f"LLM response type: {type(response).__name__}")
            logger.info(f"LLM finish_reason: {response.response_metadata.get('finish_reason', 'UNKNOWN') if hasattr(response, 'response_metadata') else 'UNKNOWN'}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"LLM call failed: {error_msg[:200]}")
            
            # Check if this is a transient error that warrants fallback
            if _is_transient_error(e):
                logger.info(f"Transient error detected. Attempting fallback orchestrator models...")
                try:
                    response = _try_fallback_orchestrator_llm(prompt)
                    logger.info(f"✓ Fallback model succeeded")
                except Exception as fallback_error:
                    logger.error(f"Fallback orchestrator models also failed: {str(fallback_error)}")
                    state["orchestrator_decision"] = None
                    state["error"] = f"LLM orchestrator failed (primary and fallback): {error_msg}"
                    state["workflow_status"] = "FAILED"
                    return state
            else:
                # Permanent error - don't retry
                logger.error(f"Permanent LLM error. Not attempting fallback.")
                state["orchestrator_decision"] = None
                state["error"] = f"LLM orchestrator failed: {error_msg}"
                state["workflow_status"] = "FAILED"
                return state
        
        # Step 7: Parse response - NATIVE TOOL CALLS ONLY
        # With tool_choice="required", the model MUST return AIMessage.tool_calls
        
        if not hasattr(response, 'tool_calls') or not response.tool_calls:
            # FAIL: No native tool_calls found
            logger.error(f"No native tool_calls in response")
            logger.error(f"  response.tool_calls: {getattr(response, 'tool_calls', 'MISSING')}")
            logger.error(f"  finish_reason: {response.response_metadata.get('finish_reason', 'UNKNOWN') if hasattr(response, 'response_metadata') else 'UNKNOWN'}")
            if hasattr(response, 'additional_kwargs'):
                logger.error(f"  reasoning_content present: {'reasoning_content' in response.additional_kwargs}")
            
            state["orchestrator_decision"] = None
            state["error"] = "LLM did not return native tool_calls. Cannot determine next tool."
            state["workflow_status"] = "FAILED"
            return state
        
        # Extract tool call from native response.tool_calls
        # tool_calls can be either ToolCall objects or dicts
        logger.info("✓ LLM returned native tool_calls")
        logger.info(f"  Finish reason: {response.response_metadata.get('finish_reason', 'UNKNOWN') if hasattr(response, 'response_metadata') else 'UNKNOWN'}")
        
        tool_call = response.tool_calls[0]
        
        # Handle both object and dict formats
        if isinstance(tool_call, dict):
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args', {})
        else:
            tool_name = getattr(tool_call, 'name', None)
            tool_args = getattr(tool_call, 'args', {})
        
        reasoning = f"Native tool call: {tool_name}"
        
        logger.info(f"Tool Call Structure:")
        logger.info(f"  Type: {type(tool_call).__name__}")
        logger.info(f"  Name: {tool_name}")
        logger.info(f"  Args: {tool_args}")
        
        # Step 8: SAFETY VALIDATION - Post-selection check
        # This validator runs AFTER LLM selection, not before
        logger.info(f"\nSAFETY VALIDATION CHECK:")
        logger.info(f"  Tool selected: {tool_name}")
        logger.info(f"  Checking prerequisites...")
        
        # Check for loop first
        from post_care.orchestrator.agentic_guardrails import detect_loop
        is_loop, loop_reason = detect_loop(state, tool_name)
        
        if is_loop:
            logger.error(f"  ✗ LOOP DETECTED: {loop_reason}")
            state["orchestrator_decision"] = None
            state["error"] = f"Orchestration loop detected: {loop_reason}"
            state["workflow_status"] = "FAILED"
            return state
        
        # Then validate tool selection
        is_valid, validation_error = validate_tool_call(tool_name, state)
        
        if not is_valid:
            logger.warning(f"  ✗ VALIDATION REJECTED: {validation_error}")
            logger.warning(f"  LLM must make another selection with updated context")
            state["orchestrator_decision"] = None
            state["error"] = f"Tool selection rejected: {validation_error}"
            state["workflow_status"] = "FAILED"
            return state
        
        logger.info(f"  ✓ VALIDATION PASSED - Tool is safe to execute")
        logger.info(f"Tool arguments: {tool_args}")
        logger.info(f"Reasoning: {reasoning[:100]}...")
        
        # Step 9: Update state with decision
        decision = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "reasoning": reasoning,
        }
        
        state["orchestrator_decision"] = decision
        state["current_node"] = "orchestrator_llm"
        state["workflow_status"] = "RUNNING"
        
        logger.info(f"\n{'='*70}")
        logger.info(f"ORCHESTRATOR DECISION COMPLETE")
        logger.info(f"  Selected Tool: {tool_name}")
        logger.info(f"  Status: WILL EXECUTE")
        logger.info(f"{'='*70}")
        
        return state
        
    except Exception as e:
        logger.error(f"Orchestrator LLM node failed: {str(e)}", exc_info=True)
        state["orchestrator_decision"] = None
        state["error"] = f"Orchestrator error: {str(e)}"
        state["workflow_status"] = "FAILED"
        return state


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_tool_args_for_state(tool_name: str, state: PostCareWorkflowState) -> Dict[str, Any]:
    """
    Build complete tool arguments from state.
    
    This helper fills in tool arguments from state, used if the LLM
    doesn't provide complete arguments.
    
    Args:
        tool_name: Name of the tool
        state: Current workflow state
    
    Returns:
        Dict of tool arguments
    """
    args = {}
    
    if tool_name == "call_care_plan_agent":
        args = {
            "mrn": state.get("mrn"),
            "prediction": state.get("prediction"),
            "probability": state.get("probability"),
            "notes": state.get("notes"),
        }
    
    elif tool_name == "call_follow_up_agent":
        care_plan = state.get("care_plan") or {}
        tasks = care_plan.get("tasks", []) if isinstance(care_plan, dict) else []
        args = {
            "mrn": state.get("mrn"),
            "care_plan_id": state.get("care_plan_id"),
            "risk_level": state.get("risk_level"),
            "intensity": state.get("intensity"),
            "tasks": tasks,
        }
    
    elif tool_name == "call_response_analyzer":
        args = {
            "mrn": state.get("mrn"),
            "care_plan_id": state.get("care_plan_id"),
            "task_id": state.get("task_id"),
            "checkin_id": state.get("checkin_id"),
            "task_type": state.get("task_type"),
            "patient_response": state.get("patient_response"),
            "doctor_instruction": None,  # Optional
            "task_description": None,  # Optional
        }
    
    elif tool_name == "call_care_continuity":
        args = {
            "mrn": state.get("mrn"),
            "care_plan_id": state.get("care_plan_id"),
            "task_id": state.get("task_id"),
            "checkin_id": state.get("checkin_id"),
            "classification": state.get("classification"),
            "summary": state.get("response_analyzer_output", {}).get("summary", ""),
            "symptoms": state.get("symptoms", []),
            "concerns": state.get("concerns", []),
            "confidence": state.get("response_confidence", 0.0),
            "doctor_instruction": None,  # Optional
            "task_description": None,  # Optional
        }
    
    return args
