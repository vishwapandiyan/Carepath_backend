"""
Response Analyzer Tools

LLM-powered tools for analyzing patient responses and converting them
into structured information.

Primary Tool:
- analyze_patient_response(): Uses Groq LLM to analyze patient response

Flow:
    ResponseAnalyzerInput
        ↓
    Groq LLM (structured JSON output)
        ↓
    Validation
        ↓
    ResponseAnalyzerOutput

Responsibility:
    - LLM interaction with structured prompts
    - JSON parsing and validation
    - Response classification and extraction
    - Confidence scoring
    
NOT Responsible:
    - Final action decisions (Safety Controller)
    - Medical diagnosis (analyzer only classifies, doesn't diagnose)
    - Escalation logic (Safety Controller)
    - Treatment recommendations (Safety Controller)
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv

from post_care.agents.response_analyzer.schemas import (
    ResponseAnalyzerInput,
    ResponseAnalyzerOutput,
)
from post_care.llm.multi_model_fallback import call_llm_with_fallback

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

RESPONSE_ANALYZER_SYSTEM_PROMPT = """You are a healthcare patient-response language analyzer.

Your job is to analyze the patient's message and convert it into structured information.

CRITICAL SCOPE LIMITATIONS:
- You are NOT a doctor and must NOT provide medical advice.
- You must NOT diagnose the patient.
- You must NOT recommend treatment.
- You must NOT decide whether emergency care should be initiated.
- You must NOT decide the final escalation action.

Your task is ONLY to identify what the patient communicated.

CLASSIFICATION RULES:
Classify the response as exactly one of: NORMAL, CONCERN, URGENT, UNCLEAR

NORMAL:
- The patient reports improvement, stability, expected status, or no current concern.
- Patient is doing well, recovering as expected, or reporting normal symptoms.
- No signs of deterioration or worrying developments.

CONCERN:
- The patient reports a potentially concerning symptom, worsening condition, difficulty, or issue requiring further review.
- Something has changed for the worse or there are new symptoms that warrant attention.
- Patient is not in immediate danger but needs follow-up evaluation.

URGENT:
- The patient describes potentially severe or immediately concerning symptoms or circumstances.
- Requires immediate clinical attention but classification is NOT a medical decision.
- Examples: severe dyspnea, chest pain, altered mental status, severe bleeding.
- You classify as URGENT based on what the patient said, not on medical judgment.

UNCLEAR:
- The response is ambiguous, contradictory, too short, or does not provide enough information for reliable interpretation.
- Cannot reliably determine patient's actual condition from what was said.
- Examples: "Okay.", "Fine.", "I don't know", contradictory statements.

EXTRACTION RULES:
- Extract symptoms explicitly mentioned or clearly communicated by the patient.
- Extract concerns explicitly communicated or reasonably supported by the patient's response.
- Do NOT invent symptoms.
- Do NOT infer a diagnosis.
- Do NOT invent information that is not present in the response.

SENTIMENT RULES:
- Identify patient sentiment as: positive, neutral, negative, or mixed.
- Base sentiment on tone and word choice, not medical condition.
- A patient describing severe symptoms might have negative sentiment.

CONFIDENCE SCORING:
- Provide confidence as a decimal 0.0 to 1.0 representing how confident you are in your classification.
- High confidence (0.8+): Clear, unambiguous response with obvious classification.
- Medium confidence (0.5-0.8): Some ambiguity but reasonable classification.
- Low confidence (<0.5): Significant ambiguity or unclear information.

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown, no code blocks) with exactly this structure:
{
    "classification": "NORMAL|CONCERN|URGENT|UNCLEAR",
    "summary": "Human-readable summary of what patient communicated",
    "symptoms": ["symptom1", "symptom2"],
    "concerns": ["concern1", "concern2"],
    "patient_sentiment": "positive|neutral|negative|mixed",
    "confidence": 0.85
}

All fields are required. symptoms and concerns may be empty arrays if none are present."""


# ============================================================================
# TOOL 1: ANALYZE PATIENT RESPONSE
# ============================================================================

def analyze_patient_response(
    input_data: ResponseAnalyzerInput,
) -> ResponseAnalyzerOutput:
    """
    Analyze a patient's natural-language response using Groq LLM.
    
    Converts unstructured patient response into structured, validated
    ResponseAnalyzerOutput with classification, symptoms, and concerns.
    
    Args:
        input_data: ResponseAnalyzerInput with patient response and context
        
    Returns:
        ResponseAnalyzerOutput with structured interpretation
        
    Process:
        1. Validate input_data (ResponseAnalyzerInput validation)
        2. Build user prompt from patient response and context
        3. Call Groq LLM with model="openai/gpt-oss-120b"
        4. Parse returned JSON
        5. Validate result against ResponseAnalyzerOutput schema
        6. Return validated ResponseAnalyzerOutput
        
    Raises:
        ValueError: If input validation fails
        json.JSONDecodeError: If LLM returns invalid JSON
        ValidationError: If output fails ResponseAnalyzerOutput validation
    """
    
    # Step 1: Validate input (Pydantic will raise if invalid)
    logger.info(
        f"Analyzing patient response for MRN {input_data.mrn}, "
        f"check-in {input_data.checkin_id}"
    )
    
    # Step 2: Build user prompt from patient response and context
    user_prompt = _build_user_prompt(input_data)
    
    # Step 3: Call Groq LLM
    logger.debug("Calling Groq LLM for response analysis")
    response_text = _call_groq_llm(user_prompt)
    
    # Step 4: Parse returned JSON
    logger.debug("Parsing LLM response JSON")
    parsed_output = _parse_llm_json(response_text)
    
    # Step 5: Build ResponseAnalyzerOutput with echoed fields
    output_dict = _build_output_dict(input_data, parsed_output)
    
    # Step 6: Validate and return
    logger.debug("Validating ResponseAnalyzerOutput schema")
    validated_output = ResponseAnalyzerOutput(**output_dict)
    
    logger.info(
        f"Analysis complete for MRN {input_data.mrn}: "
        f"classification={validated_output.classification}, "
        f"confidence={validated_output.confidence}"
    )
    
    return validated_output


# ============================================================================
# HELPER: BUILD USER PROMPT
# ============================================================================

def _build_user_prompt(input_data: ResponseAnalyzerInput) -> str:
    """
    Build the user prompt for the LLM from patient response and context.
    
    Includes only the information needed for the LLM to understand the
    patient's response. Excludes unnecessary database information.
    
    Args:
        input_data: ResponseAnalyzerInput with patient response and context
        
    Returns:
        Formatted prompt string for the LLM
    """
    
    lines = [
        "Analyze the following patient response:",
        "",
        f"MRN: {input_data.mrn}",
        f"Task type: {input_data.task_type}",
    ]
    
    # Add optional context fields if present
    if input_data.task_description:
        lines.append(f"Task description: {input_data.task_description}")
    
    if input_data.doctor_instruction:
        lines.append(f"Doctor instruction: {input_data.doctor_instruction}")
    
    lines.extend([
        "",
        "Patient response:",
        f'"{input_data.patient_response}"',
        "",
        "Analyze this response and return JSON with classification, summary, "
        "symptoms, concerns, sentiment, and confidence score.",
    ])
    
    return "\n".join(lines)


# ============================================================================
# HELPER: CALL GROQ LLM
# ============================================================================

def _call_groq_llm(user_prompt: str) -> str:
    """
    Call LLM with automatic fallback to next provider on failure.
    
    Uses multi-model fallback system:
    1. Groq (primary - fast, open source)
    2. OpenAI (fallback 1 - reliable)
    3. Anthropic (fallback 2 - good reasoning)
    4. Ollama (fallback 3 - local, always available)
    
    Args:
        user_prompt: User message with patient response context
        
    Returns:
        Response text from the first successful LLM provider
        
    Raises:
        RuntimeError: If all LLM providers fail
    """
    
    logger.info("Calling LLM with multi-model fallback")
    
    response = call_llm_with_fallback(
        prompt=user_prompt,
        system=RESPONSE_ANALYZER_SYSTEM_PROMPT
    )
    
    logger.info("✅ LLM call succeeded")
    return response


# ============================================================================
# HELPER: PARSE LLM JSON
# ============================================================================

def _parse_llm_json(response_text: str) -> dict:
    """
    Parse JSON from LLM response.
    
    Handles cases where the LLM returns the JSON wrapped in markdown code blocks.
    Extracts the actual JSON and parses it.
    
    Attempts to fix common LLM JSON issues:
    - Markdown code block wrapping (```json ... ```)
    - Number written as words (e.g., "0. nine" -> "0.9")
    - Missing quotes around field values
    
    Args:
        response_text: Response text from the LLM
        
    Returns:
        Parsed JSON dictionary with keys:
        - classification
        - summary
        - symptoms
        - concerns
        - patient_sentiment
        - confidence
        
    Raises:
        json.JSONDecodeError: If response doesn't contain valid JSON
        ValueError: If required fields are missing from parsed JSON
    """
    
    # Remove markdown code blocks if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]  # Remove ```json
    if text.startswith("```"):
        text = text[3:]  # Remove ```
    if text.endswith("```"):
        text = text[:-3]  # Remove trailing ```
    
    text = text.strip()
    
    # Attempt to fix common LLM JSON issues
    text = _fix_llm_json_issues(text)
    
    # Parse JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {response_text}")
        raise
    
    # Validate required fields are present
    required_fields = {
        "classification",
        "summary",
        "symptoms",
        "concerns",
        "patient_sentiment",
        "confidence",
    }
    
    missing_fields = required_fields - set(parsed.keys())
    if missing_fields:
        raise ValueError(
            f"LLM response missing required fields: {missing_fields}. "
            f"Response: {parsed}"
        )
    
    return parsed


def _fix_llm_json_issues(text: str) -> str:
    """
    Fix common LLM JSON formatting issues.
    
    Known issues:
    - LLM sometimes writes numbers as words (e.g., "0. nine" instead of "0.9")
    - These appear as confidence values
    
    Args:
        text: Potentially malformed JSON text
        
    Returns:
        Fixed JSON text
    """
    
    # Fix "0. nine" -> "0.9", "0. eight" -> "0.8", etc.
    number_words = {
        "zero": "0",
        "one": "1", 
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    
    # Match patterns like "0. eight" and convert to "0.8"
    for word, digit in number_words.items():
        # Pattern: decimal point followed by space and word
        pattern = rf'0\.\s+{word}(?=[,\n}}])'
        replacement = f'0.{digit}'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text


# ============================================================================
# HELPER: BUILD OUTPUT DICT
# ============================================================================

def _build_output_dict(
    input_data: ResponseAnalyzerInput,
    parsed_output: dict,
) -> dict:
    """
    Build the ResponseAnalyzerOutput dictionary with echoed fields from input.
    
    Args:
        input_data: Original input with MRN, care_plan_id, task_id, checkin_id
        parsed_output: Parsed JSON from LLM with analysis results
        
    Returns:
        Dictionary ready to construct ResponseAnalyzerOutput
    """
    
    return {
        # Echo fields from input
        "mrn": input_data.mrn,
        "care_plan_id": input_data.care_plan_id,
        "task_id": input_data.task_id,
        "checkin_id": input_data.checkin_id,
        # Analysis results from LLM
        "classification": parsed_output["classification"],
        "summary": parsed_output["summary"],
        "symptoms": parsed_output.get("symptoms", []),
        "concerns": parsed_output.get("concerns", []),
        "patient_sentiment": parsed_output.get("patient_sentiment"),
        "confidence": parsed_output["confidence"],
        "error": None,
    }
