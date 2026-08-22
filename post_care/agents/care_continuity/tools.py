"""
Care Continuity Tools

Deterministic routing tools for care continuity workflow.

The Care Continuity tools receive structured ResponseAnalyzerOutput
and convert it into validated CareContinuityOutput using deterministic
routing rules.

Primary Tool:
- evaluate_continuity(): Routes patient response to appropriate continuity workflow

Flow:
    ResponseAnalyzerOutput
        ↓
    evaluate_continuity()
    ├─ Validate input (Pydantic)
    ├─ Get continuity action (deterministic mapping)
    ├─ Build output
    └─ Return CareContinuityOutput
        ↓
    CareContinuityOutput
        ↓
    Care Continuity Agent / Later Components

Key Principles:
    - Deterministic (no randomness, no LLM)
    - Field preservation (no ID generation or modification)
    - No external actions (no Telegram, no database, no appointments)
    - Pure routing logic
"""

import logging

from post_care.agents.care_continuity.schemas import (
    CareContinuityInput,
    CareContinuityOutput,
    get_continuity_action,
)

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# PRIMARY TOOL: EVALUATE CONTINUITY
# ============================================================================

def evaluate_continuity(input_data: CareContinuityInput) -> CareContinuityOutput:
    """
    Evaluate continuity-of-care workflow based on Response Analyzer classification.
    
    This is the primary tool for care continuity routing. It receives structured
    analysis from the Response Analyzer and routes it to the appropriate
    continuity workflow using deterministic rules.
    
    Responsibility:
        1. Accept CareContinuityInput (validated ResponseAnalyzerOutput)
        2. Apply deterministic mapping (classification → action)
        3. Build CareContinuityOutput with routing decision
        4. Preserve all input fields exactly
        5. Return structured continuity decision
    
    NOT Responsibility:
        - Natural language analysis (Response Analyzer responsibility)
        - Medical decisions (downstream components responsibility)
        - Appointment scheduling (Appointment Agent responsibility)
        - Sending messages (Communication layer responsibility)
        - Database modifications (orchestrator responsibility)
    
    Args:
        input_data: CareContinuityInput with classification and confidence
                   - mrn: Medical Record Number
                   - care_plan_id: Associated care plan
                   - task_id: Associated task
                   - checkin_id: Associated check-in
                   - classification: NORMAL|CONCERN|URGENT|UNCLEAR
                   - summary: Summary of patient response
                   - symptoms: Identified symptoms (may be empty)
                   - concerns: Identified concerns (may be empty)
                   - confidence: Confidence score 0.0-1.0
    
    Returns:
        CareContinuityOutput with continuity routing decision:
        - classification: Echoed from input
        - continuity_action: CONTINUE_FOLLOW_UP|CLINICAL_REVIEW|URGENT_REVIEW|CLARIFICATION_REQUIRED
        - reason: Human-readable explanation
        - requires_human_review: Boolean (based on classification)
        - requires_appointment: Boolean (always False for routing, Appointment Agent decides)
        - All input IDs preserved exactly
    
    Routing Rules (Deterministic):
        NORMAL    → CONTINUE_FOLLOW_UP (no review, no appointment)
        CONCERN   → CLINICAL_REVIEW (review, no appointment)
        URGENT    → URGENT_REVIEW (review, no appointment)
        UNCLEAR   → CLARIFICATION_REQUIRED (no review, no appointment)
    
    Raises:
        ValueError: If input validation fails (Pydantic)
        Exception: If continuity action lookup fails
    
    Example:
        >>> from post_care.agents.care_continuity.schemas import CareContinuityInput
        >>> from post_care.agents.care_continuity.tools import evaluate_continuity
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
        >>> output = evaluate_continuity(input_data)
        >>> print(output.continuity_action)  # CLINICAL_REVIEW
        >>> print(output.requires_human_review)  # True
        >>> print(output.requires_appointment)  # False
    """
    
    # Step 1: Log the request
    logger.info(
        f"Care Continuity: Evaluating continuity for MRN {input_data.mrn}, "
        f"classification {input_data.classification}"
    )
    
    # Step 2: Input validation (Pydantic validation happens automatically)
    logger.debug(
        f"Input validated: mrn={input_data.mrn}, "
        f"classification={input_data.classification}, "
        f"confidence={input_data.confidence}"
    )
    
    # Step 3: Get deterministic continuity action
    logger.debug(f"Looking up continuity action for classification: {input_data.classification}")
    try:
        action_data = get_continuity_action(input_data.classification)
    except ValueError as e:
        logger.error(f"Invalid classification in input: {str(e)}")
        raise
    
    logger.debug(
        f"Continuity action: {action_data['continuity_action']}, "
        f"requires_human_review: {action_data['requires_human_review']}"
    )
    
    # Step 4: Build CareContinuityOutput
    output = CareContinuityOutput(
        # Echo input fields exactly (preserve IDs)
        mrn=input_data.mrn,
        care_plan_id=input_data.care_plan_id,
        task_id=input_data.task_id,
        checkin_id=input_data.checkin_id,
        
        # Echo classification
        classification=input_data.classification,
        
        # Add continuity routing decision
        continuity_action=action_data["continuity_action"],
        reason=action_data["reason"],
        requires_human_review=action_data["requires_human_review"],
        requires_appointment=action_data["requires_appointment"],
        
        # No error (success case)
        error=None,
    )
    
    # Step 5: Log completion and return
    logger.info(
        f"Care Continuity: Evaluation complete for MRN {input_data.mrn}, "
        f"continuity_action={output.continuity_action}, "
        f"requires_human_review={output.requires_human_review}"
    )
    
    return output


# ============================================================================
# RESPONSIBILITY BOUNDARIES
# ============================================================================

"""
TOOLS.PY DOES:
✅ Receive CareContinuityInput
✅ Apply deterministic mapping
✅ Build CareContinuityOutput
✅ Preserve fields exactly
✅ Return structured decision
✅ Validate using Pydantic
✅ Log activities

TOOLS.PY DOES NOT:
❌ Perform natural language analysis (Response Analyzer responsibility)
❌ Call any LLM or Groq
❌ Make medical decisions
❌ Send Telegram messages
❌ Book or cancel appointments
❌ Modify PostgreSQL
❌ Modify care plans or tasks
❌ Call other agents
❌ Contact doctors or emergency services
❌ Access external systems

These responsibilities belong to downstream components.
"""


# ============================================================================
# CLASSIFICATION → ACTION MAPPING (Reference)
# ============================================================================

"""
Deterministic Routing Rules:

NORMAL Classification:
    continuity_action: CONTINUE_FOLLOW_UP
    requires_human_review: False
    requires_appointment: False
    reason: "Patient reports stable or improving condition. Continue routine follow-up."
    → Patient is doing well, continue with scheduled follow-up.

CONCERN Classification:
    continuity_action: CLINICAL_REVIEW
    requires_human_review: True
    requires_appointment: False
    reason: "Patient response contains potentially concerning symptoms. Requires clinical review."
    → Concerning symptoms detected, needs clinical review.

URGENT Classification:
    continuity_action: URGENT_REVIEW
    requires_human_review: True
    requires_appointment: False
    reason: "Patient response contains potentially urgent symptoms. Requires immediate clinical review."
    → Urgent symptoms detected, needs immediate clinical review.

UNCLEAR Classification:
    continuity_action: CLARIFICATION_REQUIRED
    requires_human_review: False
    requires_appointment: False
    reason: "Patient response does not provide sufficient information. Requires clarification from patient."
    → Response unclear, needs clarification from patient.

All mappings are deterministic and do not require LLM processing.
"""
