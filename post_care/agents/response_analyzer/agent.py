"""
Response Analyzer Agent

Orchestration layer for patient response analysis.

The Response Analyzer Agent receives a patient's natural-language response
and orchestrates its analysis through the Response Analyzer tools.

Primary Responsibility:
    Receive ResponseAnalyzerInput → Delegate to tools → Return ResponseAnalyzerOutput

What the agent DOES:
    - Accept ResponseAnalyzerInput
    - Validate input using Pydantic schema
    - Delegate to analyze_patient_response() tool
    - Return the ResponseAnalyzerOutput
    - Handle exceptions safely

What the agent DOES NOT do:
    - Call Groq LLM directly (that's in tools.py)
    - Make safety decisions (Safety Controller responsibility)
    - Send messages (Telegram, etc.)
    - Modify care plans or tasks
    - Call other agents
    - Store results in memory/database

Architecture:
    ResponseAnalyzerInput
        ↓
    Response Analyzer Agent (this file)
        ↓
    analyze_patient_response() [tools.py]
        ↓
    Groq LLM (openai/gpt-oss-120b)
        ↓
    ResponseAnalyzerOutput
        ↓
    Safety Controller (future)

Philosophy:
    The agent answers: "What did the patient communicate?"
    The Safety Controller answers: "What should we do about it?"
"""

import logging
from typing import Optional

from post_care.agents.response_analyzer.schemas import (
    ResponseAnalyzerInput,
    ResponseAnalyzerOutput,
)
from post_care.agents.response_analyzer.tools import analyze_patient_response

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# MAIN AGENT FUNCTION
# ============================================================================

def orchestrate_response_analysis(
    input_data: ResponseAnalyzerInput,
) -> ResponseAnalyzerOutput:
    """
    Orchestrate the analysis of a patient's response.
    
    This is the main entry point for the Response Analyzer Agent.
    
    Responsibility:
        1. Accept ResponseAnalyzerInput
        2. Validate input (Pydantic validation)
        3. Delegate to analyze_patient_response() tool
        4. Return ResponseAnalyzerOutput
        5. Handle exceptions safely
    
    NOT Responsibility:
        - Calling Groq LLM directly
        - Making safety/escalation decisions
        - Sending messages or notifications
        - Modifying database
        - Storing results in memory
    
    Args:
        input_data: ResponseAnalyzerInput with patient response and context
                   - mrn: Medical Record Number
                   - care_plan_id: Associated care plan
                   - task_id: Associated task
                   - checkin_id: Associated check-in
                   - task_type: Type of follow-up task
                   - patient_response: Patient's natural language response
                   - doctor_instruction: Optional context
                   - task_description: Optional context
    
    Returns:
        ResponseAnalyzerOutput with structured interpretation:
        - classification: NORMAL, CONCERN, URGENT, or UNCLEAR
        - summary: Human-readable summary
        - symptoms: List of symptoms mentioned
        - concerns: List of concerns identified
        - patient_sentiment: Detected sentiment
        - confidence: Confidence score (0.0-1.0)
        - error: Error message if analysis failed
    
    Process Flow:
        input_data
            ↓
        Validate (Pydantic)
            ↓
        analyze_patient_response() [tools.py]
            ↓
        Groq LLM analysis
            ↓
        ResponseAnalyzerOutput
            ↓
        return
    
    Raises:
        ValueError: If input validation fails
        json.JSONDecodeError: If tool receives invalid JSON
        Exception: If Groq API call fails
    
    Example:
        >>> from post_care.agents.response_analyzer.schemas import ResponseAnalyzerInput
        >>> from post_care.agents.response_analyzer.agent import orchestrate_response_analysis
        >>> 
        >>> input_data = ResponseAnalyzerInput(
        ...     mrn="MRN000015",
        ...     care_plan_id="CP-0AEB878E",
        ...     task_id="T-9640CAAC",
        ...     checkin_id="CHK-001",
        ...     task_type="FREQUENT_CHECKINS",
        ...     patient_response="I am feeling much better today."
        ... )
        >>> 
        >>> output = orchestrate_response_analysis(input_data)
        >>> print(output.classification)  # "NORMAL", "CONCERN", "URGENT", or "UNCLEAR"
        >>> print(output.confidence)       # 0.95
    """
    
    # Step 1: Log the request
    logger.info(
        f"Response Analyzer Agent: Starting analysis for MRN {input_data.mrn}, "
        f"check-in {input_data.checkin_id}"
    )
    
    # Step 2: Input validation
    # Pydantic schema validation happens automatically in __init__
    logger.debug(
        f"Input validated: mrn={input_data.mrn}, "
        f"task_type={input_data.task_type}, "
        f"response_length={len(input_data.patient_response)}"
    )
    
    # Step 3: Delegate to analyze_patient_response tool
    logger.debug("Delegating to analyze_patient_response tool")
    try:
        output = analyze_patient_response(input_data)
        
        logger.info(
            f"Response Analyzer Agent: Analysis complete for MRN {input_data.mrn}, "
            f"classification={output.classification}, "
            f"confidence={output.confidence}"
        )
        
        return output
        
    except ValueError as e:
        logger.error(f"Input validation error: {str(e)}")
        raise
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error from tool: {str(e)}")
        raise
    
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        raise


# ============================================================================
# ALTERNATIVE NAMING (for compatibility with Follow-Up Agent pattern)
# ============================================================================

def analyze_patient_response_orchestrated(
    input_data: ResponseAnalyzerInput,
) -> ResponseAnalyzerOutput:
    """
    Analyze patient response (alternative naming for consistency).
    
    This is a wrapper around orchestrate_response_analysis() for
    consistency with the project's naming convention if preferred.
    
    Same behavior as orchestrate_response_analysis().
    
    Args:
        input_data: ResponseAnalyzerInput with patient response
    
    Returns:
        ResponseAnalyzerOutput with structured interpretation
    
    See orchestrate_response_analysis() for full documentation.
    """
    return orchestrate_response_analysis(input_data)


# ============================================================================
# INTERNAL HELPER: FIELD PRESERVATION VALIDATION
# ============================================================================

def _validate_field_preservation(
    input_data: ResponseAnalyzerInput,
    output: ResponseAnalyzerOutput,
) -> None:
    """
    Validate that echoed fields are preserved correctly.
    
    Used internally to ensure agent doesn't corrupt input fields.
    
    Args:
        input_data: Original input
        output: Returned output
    
    Raises:
        AssertionError: If any echoed field doesn't match
    """
    assert output.mrn == input_data.mrn, f"MRN mismatch: {output.mrn} != {input_data.mrn}"
    assert output.care_plan_id == input_data.care_plan_id, f"care_plan_id mismatch"
    assert output.task_id == input_data.task_id, f"task_id mismatch"
    assert output.checkin_id == input_data.checkin_id, f"checkin_id mismatch"


# ============================================================================
# REFERENCE: CLASSIFICATION VALUES
# ============================================================================

# Valid classification values (from ResponseAnalyzerOutput schema)
VALID_CLASSIFICATIONS = ["NORMAL", "CONCERN", "URGENT", "UNCLEAR"]

# Classification Definitions:
# NORMAL:  Patient reports improvement, stability, expected status, no concern
# CONCERN: Patient reports concerning symptom, worsening condition
# URGENT:  Patient describes severe or immediately concerning symptoms
# UNCLEAR: Response is ambiguous, insufficient, or unreliable


# ============================================================================
# AGENT RESPONSIBILITY BOUNDARIES
# ============================================================================

"""
AGENT DOES:
✅ Receive ResponseAnalyzerInput
✅ Validate input (Pydantic)
✅ Delegate to analyze_patient_response() tool
✅ Return ResponseAnalyzerOutput
✅ Handle exceptions safely
✅ Log activities

AGENT DOES NOT:
❌ Call Groq LLM directly
❌ Make safety decisions
❌ Send messages (Telegram, email, etc.)
❌ Create, modify, or escalate tasks
❌ Modify care plans
❌ Update check-in status
❌ Call other agents
❌ Store results in memory
❌ Access database directly

Those responsibilities belong to:
- Tools layer (LLM integration)
- Safety Controller (action decisions)
- Follow-Up Agent (task orchestration)
- Other specialized components
"""


# ============================================================================
# IMPORTS NEEDED FOR TYPE HINTS AND LOGGING
# ============================================================================

import json  # For JSONDecodeError handling
