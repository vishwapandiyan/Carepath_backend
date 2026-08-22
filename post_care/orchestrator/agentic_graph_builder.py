"""
Agentic Graph Builder for Post-Care Orchestrator

This module implements the LangGraph StateGraph that orchestrates the
post-care workflow using LLM-based tool calling.

Graph Structure:
────────────────

START
  ↓
[orchestrator_llm]  ← LLM decides next tool
  ↓
[tool_executor]     ← Execute selected tool + update state
  ↓
┌─────────────────────────────────────────┐
│ route_after_tool_execution()            │
│ - Check stopping condition              │
│ - Decide next node                      │
└─────────────────────────────────────────┘
  ↓
┌─ Continue loop to orchestrator_llm (more work)
├─ Go to specific node (wait_for_response if needed)
└─ Go to complete node (workflow finished)

Key Features:
- Agentic loop with LLM-based routing
- Tool availability guard rails
- Stopping condition checks
- Error handling at each step
- Metadata tracking for monitoring

Nodes:
1. orchestrator_llm: LLM decides tool to call
2. tool_executor: Execute tool + update state
3. wait_for_response: Wait for patient input
4. complete: Finalize workflow

Edges:
- START → orchestrator_llm
- orchestrator_llm → tool_executor
- tool_executor → route_after_tool_execution()
  - More work → orchestrator_llm (loop)
  - Need patient input → wait_for_response
  - Workflow complete → complete
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from post_care.orchestrator.workflow_state import PostCareWorkflowState
from post_care.orchestrator.agentic_orchestrator_node import orchestrator_llm_node
from post_care.orchestrator.agentic_tool_executor import tool_executor_node
from post_care.orchestrator.agentic_guardrails import check_stopping_condition

logger = logging.getLogger(__name__)


# ============================================================================
# COMPLETION NODE
# ============================================================================

def complete_node(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    Complete the workflow and finalize results.
    
    This node:
    1. Marks workflow as COMPLETED or FAILED
    2. Logs final state
    3. Prepares results for return
    
    Args:
        state: Current workflow state
    
    Returns:
        Finalized state
    """
    if state.get("error"):
        state["workflow_status"] = "FAILED"
        logger.error(f"Workflow completed with error: {state.get('error')}")
    elif state.get("continuity_action"):
        state["workflow_status"] = "COMPLETED"
        logger.info(f"Workflow completed successfully. Action: {state.get('continuity_action')}")
    elif state.get("follow_up_output"):
        # Step 1 non-blocking: workflow completed after follow-up (no patient response yet)
        state["workflow_status"] = "COMPLETED"
        logger.info("Workflow completed after follow-up (non-blocking). Awaiting patient response asynchronously.")
    else:
        state["workflow_status"] = "COMPLETED"
        logger.info("Workflow completed")
    
    state["current_node"] = "complete"
    return state


def wait_for_response_node(state: PostCareWorkflowState) -> PostCareWorkflowState:
    """
    LangGraph node: Wait for patient response.

    In production mode (non-interactive environments), auto-generates simulated responses based on risk level.
    In terminal/debug mode, prompts for manual input.

    This node:
        1. Displays workflow information
        2. Collects or simulates patient response
        3. Stores response in state
        4. Returns to graph for next phase

    Args:
        state: Current workflow state

    Returns:
        Updated state with patient_response populated
    """
    logger.info("="*80)
    logger.info("LANGGRAPH NODE: WAIT_FOR_RESPONSE")
    logger.info("="*80)

    state["workflow_status"] = "WAITING"
    state["current_node"] = "wait_for_response"
    state["next_node"] = "response_analyzer"

    try:
        # Check if patient response already provided in state
        if state.get("patient_response") and state.get("patient_response").strip():
            logger.info(f"Patient response already in state: {state.get('patient_response')[:100]}...")
            state["workflow_status"] = "RUNNING"
            state["current_node"] = "wait_for_response"
            state["next_node"] = "response_analyzer"
            return state
        
        # Check if running in non-interactive mode (production API)
        # If stdin is not a terminal, use simulated response
        import sys
        is_terminal = sys.stdin.isatty()
        
        risk_level = state.get("risk_level", "LOW")
        
        # Auto-simulate responses in production mode
        if not is_terminal:
            logger.info("🤖 Non-interactive mode detected - simulating patient response")
            
            # Generate appropriate simulated response based on risk level
            simulated_responses = {
                "HIGH": "I'm feeling okay but a bit worried. Had some chest discomfort earlier but it's better now.",
                "MODERATE": "I'm doing alright. Taking my medications as prescribed. Minor discomfort but manageable.",
                "LOW": "I'm feeling good. No issues to report. Following all instructions."
            }
            
            patient_response = simulated_responses.get(risk_level, simulated_responses["LOW"])
            logger.info(f"✓ Simulated {risk_level} risk response: {patient_response}")
            
            state["patient_response"] = patient_response
            state["workflow_status"] = "RUNNING"
            return state
        
        # Terminal mode - show interactive prompt
        logger.info("⌨️  Interactive terminal mode - waiting for manual input")
        
        # Display workflow information
        print("\n" + "="*80)
        print("CAREPATH POST-CARE WORKFLOW")
        print("="*80)
        print(f"Patient MRN       : {state['mrn']}")
        print(f"Care Plan ID      : {state['care_plan_id']}")
        print(f"Risk Level        : {state['risk_level']}")
        print(f"Intensity         : {state['intensity']}")
        print("-"*80)
        print("FOLLOW-UP")
        print("-"*80)

        if state["follow_up_output"] and state["follow_up_output"].get("follow_up"):
            follow_up_data = state["follow_up_output"]["follow_up"]
            for key, value in follow_up_data.items():
                if key != "channel":  # Skip internal fields
                    print(f"{key:<20}: {value}")

        # Display task info
        if state["task_id"]:
            print(f"Task Type         : {state['task_type']}")
            print(f"Task ID           : {state['task_id']}")

        print("-"*80)
        print("PATIENT RESPONSE")
        print("-"*80)

        # Get patient response from terminal
        patient_response = input("Enter patient response: ").strip()

        if not patient_response:
            raise ValueError("Patient response cannot be empty")

        state["patient_response"] = patient_response
        state["workflow_status"] = "RUNNING"

        logger.info(f"Patient response received: {patient_response[:100]}...")

        return state

    except KeyboardInterrupt:
        logger.info("Workflow cancelled by user")
        state["workflow_status"] = "FAILED"
        state["error"] = "Workflow cancelled by user"
        return state
    except Exception as e:
        logger.error(f"Wait for Response Node failed: {str(e)}", exc_info=True)
        state["workflow_status"] = "FAILED"
        state["error"] = f"Patient response error: {str(e)}"
        return state


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================

def route_after_tool_execution(state: PostCareWorkflowState) -> Literal[
    "orchestrator_llm",
    "wait_for_response",
    "complete",
]:
    """
    Route after tool execution based on state.
    
    Decision logic:
    1. Check if workflow should stop
       - If yes: go to complete
    2. Check if we're waiting for patient response
       - If yes: go to wait_for_response
    3. Otherwise: loop back to orchestrator to decide next tool
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name: "orchestrator_llm", "wait_for_response", or "complete"
    """
    
    # Check stopping condition
    should_stop, stop_reason = check_stopping_condition(state)
    if should_stop:
        logger.info(f"Stopping condition met: {stop_reason}")
        return "complete"
    
    # STEP 1: Non-blocking flow — complete after follow-up
    # The workflow does NOT wait for patient response inline.
    # Patient responses are handled asynchronously in a separate step.
    if (state.get("follow_up_output") is not None and
        state.get("patient_response") is None):
        logger.info("Follow-up complete. Workflow ending (non-blocking). Patient response handled asynchronously.")
        return "complete"
    
    # Otherwise continue looping - orchestrator will decide next tool
    logger.info("More work to do - routing back to orchestrator_llm")
    return "orchestrator_llm"


def route_after_orchestrator_decision(state: PostCareWorkflowState) -> Literal[
    "tool_executor",
    "complete",
]:
    """
    Route after orchestrator LLM makes decision.
    
    Decision logic:
    1. Check if orchestrator made a valid decision
       - If error: go to complete (workflow failed)
       - If no decision: go to complete (no tools available)
    2. Otherwise: execute the tool
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node: "tool_executor" or "complete"
    """
    
    logger.info(f"[ROUTING] route_after_orchestrator_decision called")
    logger.info(f"  state.error: {state.get('error')}")
    logger.info(f"  orchestrator_decision: {state.get('orchestrator_decision')}")
    
    if state.get("error") is not None:
        logger.warning(f"Error in state: {state.get('error')}")
        return "complete"
    
    orchestrator_decision = state.get("orchestrator_decision")
    if not orchestrator_decision:
        logger.warning("Orchestrator made no valid decision (None)")
        return "complete"
    
    # Valid decision - check it has required fields
    if not orchestrator_decision.get("tool_name"):
        logger.warning("Orchestrator decision missing tool_name")
        return "complete"
    
    logger.info(f"Orchestrator decided: {orchestrator_decision.get('tool_name')}")
    return "tool_executor"


# ============================================================================
# GRAPH BUILDER
# ============================================================================

def build_agentic_graph() -> CompiledStateGraph:
    """
    Build the agentic workflow graph.
    
    Creates a LangGraph StateGraph with:
    - Nodes for orchestrator, tool execution, patient wait, completion
    - Edges with routing logic
    - Compiled state management
    - Error handling
    
    Returns:
        CompiledStateGraph ready for execution
    
    Graph Structure:
    ────────────────
    START
      ↓
    [orchestrator_llm]
      ↓
    ┌─ route_after_orchestrator_decision()
    │  ├─ valid decision → [tool_executor]
    │  └─ error → [complete]
    ↓
    [tool_executor]
      ↓
    ┌─ route_after_tool_execution()
    │  ├─ stop condition → [complete]
    │  ├─ need patient response → [wait_for_response]
    │  └─ more work → [orchestrator_llm]
    ↓
    [wait_for_response]  ← External system sets patient_response
      ↓
    [orchestrator_llm]  ← Loop back
    
    [complete]
      ↓
    END
    """
    
    # Create graph
    graph = StateGraph(PostCareWorkflowState)
    
    # Add nodes
    logger.info("Adding nodes to graph...")
    graph.add_node("orchestrator_llm", orchestrator_llm_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("wait_for_response", wait_for_response_node)
    graph.add_node("complete", complete_node)
    
    # Set entry point
    graph.set_entry_point("orchestrator_llm")
    
    # Add edges
    logger.info("Adding edges to graph...")
    
    # orchestrator_llm → route_after_orchestrator_decision
    graph.add_conditional_edges(
        "orchestrator_llm",
        route_after_orchestrator_decision,
        {
            "tool_executor": "tool_executor",
            "complete": "complete",
        }
    )
    
    # tool_executor → route_after_tool_execution
    graph.add_conditional_edges(
        "tool_executor",
        route_after_tool_execution,
        {
            "orchestrator_llm": "orchestrator_llm",
            "wait_for_response": "wait_for_response",
            "complete": "complete",
        }
    )
    
    # wait_for_response → orchestrator_llm (loop back with patient_response set)
    graph.add_edge("wait_for_response", "orchestrator_llm")
    
    # complete → END
    graph.add_edge("complete", END)
    
    # Compile graph
    logger.info("Compiling graph...")
    compiled_graph = graph.compile()
    
    logger.info("Agentic graph built successfully")
    return compiled_graph


# ============================================================================
# GRAPH CACHING (optional optimization)
# ============================================================================

_cached_graph: CompiledStateGraph = None


def get_agentic_graph(use_cache: bool = True) -> CompiledStateGraph:
    """
    Get the agentic workflow graph (with caching option).
    
    The graph is compiled once and cached for reuse, improving performance.
    
    Args:
        use_cache: If True, return cached graph if available
    
    Returns:
        CompiledStateGraph ready for invocation
    """
    global _cached_graph
    
    if use_cache and _cached_graph is not None:
        logger.info("Returning cached agentic graph")
        return _cached_graph
    
    logger.info("Building agentic graph (not cached)")
    _cached_graph = build_agentic_graph()
    return _cached_graph


# ============================================================================
# GRAPH EXECUTION HELPERS
# ============================================================================

def create_initial_state(
    mrn: str,
    prediction: int,
    probability: float,
    notes: str = None,
) -> PostCareWorkflowState:
    """
    Create initial workflow state for graph execution.
    
    Args:
        mrn: Medical Record Number
        prediction: Readmission prediction (0 or 1)
        probability: Readmission probability (0.0-1.0)
        notes: Optional discharge instructions
    
    Returns:
        PostCareWorkflowState ready for graph execution
    """
    return PostCareWorkflowState(
        # Input data
        mrn=mrn,
        patient_id=None,
        prediction=prediction,
        probability=probability,
        notes=notes,
        
        # Care plan phase
        care_plan=None,
        care_plan_id=None,
        risk_level=None,
        intensity=None,
        care_plan_status=None,
        
        # Follow-up phase
        follow_up_output=None,
        task_id=None,
        task_type=None,
        checkin_id=None,
        checkin_status=None,
        
        # Patient response
        patient_response=None,
        
        # Response analyzer phase
        response_analyzer_output=None,
        classification=None,
        response_confidence=None,
        symptoms=None,
        concerns=None,
        
        # Care continuity phase
        care_continuity_output=None,
        continuity_action=None,
        requires_human_review=None,
        requires_appointment=None,
        
        # Workflow state
        workflow_status="PENDING",
        current_node=None,
        next_node=None,
        error=None,
        metadata=None,
        
        # Orchestrator state (agentic graph)
        orchestrator_decision=None,
    )


def run_agentic_workflow(
    mrn: str,
    prediction: int,
    probability: float,
    notes: str = None,
    initial_response: str = None,
) -> PostCareWorkflowState:
    """
    Run the agentic workflow to completion.
    
    This is the main entry point for executing the workflow.
    
    Args:
        mrn: Medical Record Number
        prediction: Readmission prediction (0 or 1)
        probability: Readmission probability (0.0-1.0)
        notes: Optional discharge instructions
        initial_response: Optional initial patient response (for testing)
    
    Returns:
        Final workflow state after execution
    
    Flow:
    1. Create initial state
    2. Get compiled graph
    3. Execute graph until END
    4. Return final state
    """
    logger.info(f"Starting agentic workflow for MRN: {mrn}")
    
    # Create initial state
    state = create_initial_state(mrn, prediction, probability, notes)
    
    # Set initial response if provided (for testing)
    if initial_response:
        state["patient_response"] = initial_response
        logger.info(f"Initial patient response set: {initial_response}")
    
    # Get graph
    graph = get_agentic_graph()
    
    # Execute graph
    logger.info("Executing agentic graph...")
    final_state = graph.invoke(state)
    
    logger.info(f"Workflow complete. Status: {final_state.get('workflow_status')}")
    logger.info(f"Continuity action: {final_state.get('continuity_action')}")
    
    return final_state


# ============================================================================
# GRAPH INTROSPECTION (debugging helpers)
# ============================================================================

def get_graph_structure() -> dict:
    """
    Get information about the graph structure for debugging.
    
    Returns dict with nodes, edges, and routing information.
    """
    graph = get_agentic_graph()
    
    # CompiledStateGraph doesn't expose nodes/edges directly
    # Return static structure based on our implementation
    return {
        "nodes": ["orchestrator_llm", "tool_executor", "wait_for_response", "complete"],
        "edges": [
            ("orchestrator_llm", "tool_executor"),
            ("orchestrator_llm", "complete"),
            ("tool_executor", "orchestrator_llm"),
            ("tool_executor", "wait_for_response"),
            ("tool_executor", "complete"),
            ("wait_for_response", "orchestrator_llm"),
            ("complete", "END"),
        ],
        "entry_point": "orchestrator_llm",
        "exit_point": "END",
    }


def visualize_graph():
    """
    Print a text visualization of the graph structure.
    
    Useful for debugging and documentation.
    """
    logger.info("=== AGENTIC WORKFLOW GRAPH ===\n")
    logger.info("""
    START
      ↓
    [orchestrator_llm] ← LLM decides next tool
      ↓
    ┌─ route_after_orchestrator_decision()
    │  ├─ Valid decision → [tool_executor]
    │  └─ Error → [complete]
    ↓
    [tool_executor] ← Execute selected tool
      ↓
    ┌─ route_after_tool_execution()
    │  ├─ Stop condition met → [complete]
    │  ├─ Need patient response → [wait_for_response]
    │  └─ More work to do → [orchestrator_llm] (LOOP)
    ↓
    [wait_for_response] ← External system provides response
      ↓
    [orchestrator_llm] ← Resume after response
    
    [complete] ← Finalize workflow
      ↓
    END
    """)
