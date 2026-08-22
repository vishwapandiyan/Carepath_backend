"""
Doctor Instruction Extraction using Groq LLM.

This module uses Groq (openai/gpt-oss-120b) to extract structured doctor instructions
from EHR clinical_notes. The extracted instructions are used to personalize care-plan tasks
WITHOUT modifying the risk-based pathway logic.

IMPORTANT CONSTRAINTS:
- LLM ONLY extracts and structures instructions from clinical notes
- LLM MUST NOT determine risk level, care intensity, or task selection
- LLM MUST NOT invent medical information
- LLM MUST NOT override deterministic safety rules
- If LLM fails or notes are empty, fall back to default behavior

Data flow:
PostgreSQL clinical_notes → Groq extraction → DoctorInstructions → Care plan personalization
"""

import json
import logging
import os
from typing import Optional
from pydantic import BaseModel, Field

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)

# Load environment from .env file if not already loaded
from dotenv import load_dotenv
load_dotenv()


# ============================================================================
# STRUCTURED EXTRACTION SCHEMA
# ============================================================================

class DoctorInstructions(BaseModel):
    """
    Structured extraction of doctor instructions from clinical notes.
    
    All fields are optional. If a category is not present in the notes,
    the field will be None or an empty list.
    
    NO hallucinated information. NO invented dates, medications, or specialties.
    """
    follow_up: Optional[str] = Field(
        default=None,
        description="Follow-up appointment or specialist recommendation (preserved exactly from notes)"
    )
    monitoring: list[str] = Field(
        default_factory=list,
        description="Specific monitoring instructions (no invented symptoms)"
    )
    medication: list[str] = Field(
        default_factory=list,
        description="Medication-related instructions (no invented medication names)"
    )
    escalation: list[str] = Field(
        default_factory=list,
        description="Symptoms or conditions requiring escalation/urgent care"
    )
    other_instructions: list[str] = Field(
        default_factory=list,
        description="Other important instructions"
    )


# ============================================================================
# EXTRACTION FUNCTION
# ============================================================================

def extract_doctor_instructions(clinical_notes: Optional[str]) -> DoctorInstructions:
    """
    Extract structured doctor instructions from clinical notes using Groq LLM.
    
    SAFE FALLBACK: If notes are empty, Groq unavailable, or LLM fails,
    returns default empty DoctorInstructions (no crash, no fabrication).
    
    Args:
        clinical_notes: Raw clinical notes from EHR (may be None or empty)
    
    Returns:
        DoctorInstructions: Structured extraction (empty if no instructions or error)
    
    Raises:
        None - all errors are caught and logged, returns default on failure
    """
    
    # STEP 1: Validate input
    if not clinical_notes or not clinical_notes.strip():
        # Empty or NULL notes - skip LLM
        logger.debug("Clinical notes empty/NULL - skipping LLM extraction")
        return DoctorInstructions()
    
    # STEP 2: Check if Groq is available
    if not GROQ_AVAILABLE:
        logger.warning("Groq not installed - skipping doctor instruction extraction")
        return DoctorInstructions()
    
    try:
        # STEP 3: Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not found in environment - skipping doctor instruction extraction")
            return DoctorInstructions()
        
        client = Groq(api_key=api_key)
        
        # STEP 4: Build extraction prompt
        extraction_prompt = f"""Extract doctor instructions from the following clinical notes into structured JSON.

Clinical Notes:
{clinical_notes}

Return ONLY valid JSON (no markdown, no extra text) with this exact structure:
{{
  "follow_up": "Follow-up appointment or specialist recommendation (or null if not present)",
  "monitoring": ["List of specific monitoring instructions"],
  "medication": ["List of medication-related instructions"],
  "escalation": ["Symptoms or conditions requiring escalation/urgent care"],
  "other_instructions": ["Other important instructions"]
}}

CRITICAL RULES:
- If a category is not mentioned, use an empty list [] or null.
- DO NOT invent information.
- DO NOT hallucinate appointment dates or medication names.
- Preserve exact dates and names from the notes.
- If no instructions are present, return all empty/null values.
- Only extract what is explicitly stated in the notes."""
        
        # STEP 5: Call Groq LLM
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=1,
            max_completion_tokens=2048,
            top_p=1,
            reasoning_effort="medium",
            stream=False
        )
        
        # STEP 6: Extract response
        llm_response = completion.choices[0].message.content.strip()
        
        # STEP 7: Parse JSON
        try:
            parsed_json = json.loads(llm_response)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}")
            logger.error(f"Response was: {llm_response}")
            return DoctorInstructions()
        
        # STEP 8: Validate with Pydantic
        try:
            validated = DoctorInstructions(**parsed_json)
            logger.info(f"Doctor instructions extracted successfully")
            return validated
        except Exception as e:
            logger.error(f"LLM JSON validation failed: {e}")
            logger.error(f"Parsed JSON: {parsed_json}")
            return DoctorInstructions()
    
    except Exception as e:
        # Catch-all: any error returns default (no crash)
        logger.error(f"Doctor instruction extraction failed: {type(e).__name__}: {str(e)}")
        return DoctorInstructions()


# ============================================================================
# TASK PERSONALIZATION (NOT IMPLEMENTED YET)
# ============================================================================

def personalize_task_descriptions(
    task_type: str,
    doctor_instructions: DoctorInstructions
) -> Optional[str]:
    """
    Generate personalized task description based on doctor instructions.
    
    This is a placeholder for future enhancement. Currently returns None
    (tasks use generic descriptions).
    
    Args:
        task_type: Type of task (e.g., "FOLLOW_UP_APPOINTMENT")
        doctor_instructions: Extracted doctor instructions
    
    Returns:
        Personalized description (or None if no personalization applicable)
    
    NOTE: This function is NOT called by the agent yet.
    Task personalization will be implemented in a future phase.
    """
    # Placeholder for future implementation
    return None
