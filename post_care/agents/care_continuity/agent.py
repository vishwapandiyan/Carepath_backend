"""
Care Continuity Agent

Orchestration layer for care continuity workflow routing.

The Care Continuity Agent receives structured output from the Response Analyzer
and orchestrates its conversion into a validated care continuity decision.

Primary Responsibility:
    Receive CareContinuityInput → Delegate to tools → Return CareContinuityOutput

What the agent DOES:
    - Accept CareContinuityInput
    - Validate input using Pydantic schema
    - Delegate to evaluate_continuity() tool
    - Return the CareContinuityOutput
    - Handle exceptions safely

What the agent DOES NOT do:
    - Call any LLM (Groq, etc.)
    - Make natural language analysis (Response Analyzer responsibility)
    - Make medical decisions (downstream components responsibility)
    - Send messages (Communication layer responsibility)
    - Book appointments (Appointment Agent responsibility)
    - Modify database (orchestrator responsibility)
    - Call other agents
    - Access external systems

Architecture:
    ResponseAnalyzerOutput
        ↓
    Care Continuity Agent (this file)
        ↓
    evaluate_continuity() [tools.py]
        ↓
    Deterministic routing
        ↓
    CareContinuityOutput
        ↓
    Later: Appointment Agent / Communication / Orchestrator

Philosophy:
    The agent answers: "What continuity workflow should happen?"
    The downstream components answer: "How should we implement it?"
"""

import logging

from post_care.agents.care_continuity.schemas import (
    CareContinuityInput,
    CareContinuityOutput,
)
from post_care.agents.care_continuity.tools import evaluate_continuity

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# MAIN AGENT FUNCTION
# ============================================================================

def process_care_continuity(
    input_data: CareContinuityInput,
) -> CareContinuityOutput:
    """
    Process care continuity workflow routing.
    
    This is the main entry point for the Care Continuity Agent.
    
    Responsibility:
        1. Accept CareContinuityInput
        2. Validate input (Pydantic validation)
        3. Delegate to evaluate_continuity() tool
        4. Return CareContinuityOutput
        5. Handle exceptions safely
    
    NOT Responsibility:
        - Calling LLM
        - Natural language analysis
        - Making medical decisions
        - Sending messages
        - Booking appointments
        - Modifying database
        - Calling other agents
    
    Args:
        input_data: CareContinuityInput with Response Analyzer classification
                   - mrn: Medical Record Number
                   - care_plan_id: Associated care plan
                   - task_id: Associated task
                   - checkin_id: Associated check-in
                   - classification: NORMAL|CONCERN|URGENT|UNCLEAR
                   - summary: Summary of patient response
                   - symptoms: Identified symptoms (may be empty)
                   - concerns: Identified concerns (may be empty)
                   - confidence: Confidence score 0.0-1.0
                   - doctor_instruction: Optional context
                   - task_description: Optional context
    
    Returns:
        CareContinuityOutput with continuity routing decision:
        - classification: Echoed from input
        - continuity_action: Workflow action
        - reason: Human-readable explanation
        - requires_human_review: Boolean
        - requires_appointment: Boolean
        - All input IDs preserved exactly
    
    Process Flow:
        input_data
            ↓
        Validate (Pydantic)
            ↓
        evaluate_continuity() [tools.py]
            ↓
        Deterministic mapping (classification → action)
            ↓
        CareContinuityOutput
            ↓
        return
    
    Raises:
        ValueError: If input validation fails
        Exception: If tool call fails
    
    Example:
        >>> from post_care.agents.care_continuity.schemas import CareContinuityInput
        >>> from post_care.agents.care_continuity.agent import process_care_continuity
        >>> 
        >>> input_data = CareContinuityInput(
        ...     mrn="MRN000015",
        ...     care_plan_id="CP-0AEB878E",
        ...     task_id="T-5284815F",
        ...     checkin_id="CHK-998DC412",
        ...     classification="CONCERN",
        ...     summary="Patient reports worsening wound symptoms.",
        ...     symptoms=["swelling", "pain", "redness"],
        ...     concerns=["worsening wound"],
        ...     confidence=0.95
        ... )
        >>> 
        >>> output = process_care_continuity(input_data)
        >>> print(output.continuity_action)  # CLINICAL_REVIEW
    """
    
    # Step 1: Log the request
    logger.info(
        f"Care Continuity Agent: Processing continuity for MRN {input_data.mrn}, "
        f"classification {input_data.classification}"
    )
    
    # Step 2: Input validation
    # Pydantic schema validation happens automatically in __init__
    logger.debug(
        f"Input validated: mrn={input_data.mrn}, "
        f"classification={input_data.classification}, "
        f"confidence={input_data.confidence}"
    )
    
    # Step 3: Delegate to evaluate_continuity tool
    logger.debug("Delegating to evaluate_continuity tool")
    try:
        output = evaluate_continuity(input_data)
        
        logger.info(
            f"Care Continuity Agent: Processing complete for MRN {input_data.mrn}, "
            f"continuity_action={output.continuity_action}, "
            f"requires_human_review={output.requires_human_review}"
        )
        
        return output
        
    except ValueError as e:
        logger.error(f"Input validation error: {str(e)}")
        raise
    
    except Exception as e:
        logger.error(f"Continuity processing failed: {str(e)}", exc_info=True)
        raise


# ============================================================================
# ALTERNATIVE NAMING (for consistency with other agents)
# ============================================================================

def evaluate_care_continuity(
    input_data: CareContinuityInput,
) -> CareContinuityOutput:
    """
    Evaluate care continuity (alternative naming for consistency).
    
    This is a wrapper around process_care_continuity() for consistency
    with the project's naming conventions.
    
    Same behavior as process_care_continuity().
    
    Args:
        input_data: CareContinuityInput with Response Analyzer classification
    
    Returns:
        CareContinuityOutput with continuity routing decision
    
    See process_care_continuity() for full documentation.
    """
    return process_care_continuity(input_data)


# ============================================================================
# AGENT RESPONSIBILITY BOUNDARIES
# ============================================================================

"""
AGENT DOES:
✅ Receive CareContinuityInput
✅ Validate input (Pydantic)
✅ Delegate to evaluate_continuity() tool
✅ Return CareContinuityOutput
✅ Handle exceptions safely
✅ Log activities

AGENT DOES NOT:
❌ Call any LLM
❌ Perform natural language analysis
❌ Make medical decisions
❌ Send Telegram messages
❌ Book or cancel appointments
❌ Modify PostgreSQL
❌ Modify care plans or tasks
❌ Call other agents
❌ Access external systems

Those responsibilities belong to:
- Tools layer (deterministic routing)
- Downstream components (Appointment Agent, Communication, Orchestrator)
- Other specialized components
"""


# ============================================================================
# REFERENCE: CONTINUITY ACTIONS
# ============================================================================

"""
Valid Continuity Actions:
- CONTINUE_FOLLOW_UP: Patient stable/improving. Continue routine follow-up.
- CLINICAL_REVIEW: Concerning symptoms. Requires clinical review.
- URGENT_REVIEW: Urgent symptoms. Requires immediate clinical review.
- CLARIFICATION_REQUIRED: Response unclear. Requires patient clarification.

These are workflow classifications, NOT medical decisions.
"""
