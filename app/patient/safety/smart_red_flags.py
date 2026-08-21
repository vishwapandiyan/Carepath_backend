"""
Smart Red Flag Filtering using LLM with Constraint-Based Prompting

Uses Gemini to analyze patient symptoms and intelligently determine which
red flag questions are most relevant, avoiding showing all 10 scary questions.
"""

import logging
from typing import Dict, List, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RelevantRedFlag(BaseModel):
    """A red flag question that should be asked based on symptoms."""
    field: str
    question: str
    relevance_reason: str
    priority: str  # "critical", "high", "medium"


class RedFlagFilterResult(BaseModel):
    """Result of filtering red flags based on symptoms."""
    relevant_flags: List[RelevantRedFlag]
    total_relevant: int
    skipped_count: int
    reasoning: str


# All possible red flag questions
ALL_RED_FLAGS = [
    {
        "field": "chest_pain",
        "question": "Are you having chest pain or pressure — squeezing, tightness, or pressure in the chest?",
        "keywords": ["chest", "heart", "cardiac", "pressure", "squeezing"],
        "categories": ["cardiac", "respiratory"]
    },
    {
        "field": "difficulty_breathing",
        "question": "Are you having SEVERE difficulty breathing — unable to speak in full sentences, or gasping for air?",
        "keywords": ["breath", "breathing", "respiratory", "air", "oxygen", "gasping"],
        "categories": ["respiratory", "cardiac"]
    },
    {
        "field": "altered_consciousness",
        "question": "Have you lost consciousness, fainted, or are you acutely confused / unresponsive?",
        "keywords": ["consciousness", "faint", "confused", "dizzy", "head", "mental"],
        "categories": ["neurological", "cardiac"]
    },
    {
        "field": "severe_bleeding",
        "question": "Are you bleeding severely and unable to stop it despite direct pressure?",
        "keywords": ["bleeding", "blood", "hemorrhage", "cut", "wound", "injury"],
        "categories": ["trauma", "injury"]
    },
    {
        "field": "stroke_symptoms",
        "question": "Do you have facial drooping, sudden arm/leg weakness, or inability to speak — happening RIGHT NOW?",
        "keywords": ["stroke", "facial", "drooping", "weakness", "arm", "leg", "speech", "slurred"],
        "categories": ["neurological"]
    },
    {
        "field": "suicidal_ideation",
        "question": "Are you having thoughts of hurting yourself or ending your life?",
        "keywords": ["suicide", "self-harm", "hurt myself", "end my life", "depressed", "hopeless"],
        "categories": ["mental_health"]
    },
    {
        "field": "anaphylaxis",
        "question": "Are you having a severe allergic reaction — throat swelling, widespread hives, or feeling faint?",
        "keywords": ["allergic", "allergy", "hives", "swelling", "throat", "anaphylaxis"],
        "categories": ["allergic", "respiratory"]
    },
    {
        "field": "high_fever",
        "question": "Do you have a dangerously high fever — 103°F (39.4°C) or higher?",
        "keywords": ["fever", "temperature", "hot", "burning"],
        "categories": ["infectious", "inflammatory"]
    },
    {
        "field": "unable_to_walk",
        "question": "Are you completely unable to walk, stand, or bear any weight?",
        "keywords": ["walk", "stand", "leg", "foot", "ankle", "knee", "mobility"],
        "categories": ["musculoskeletal", "neurological"]
    },
    {
        "field": "severe_abdominal_pain",
        "question": "Are you having severe, sharp, or crushing abdominal (belly) pain?",
        "keywords": ["abdomen", "belly", "stomach", "gut", "abdominal"],
        "categories": ["gastrointestinal", "abdominal"]
    },
]


def filter_red_flags_with_llm(
    chief_complaint: str,
    extracted_features: Dict[str, Any],
) -> RedFlagFilterResult:
    """
    Use LLM with constraint-based prompting to determine relevant red flags.
    
    Args:
        chief_complaint: Main symptom described by patient
        extracted_features: All extracted features from conversation
        
    Returns:
        RedFlagFilterResult with 2-5 most relevant questions
    """
    try:
        import google.generativeai as genai
        from app.config import settings
        
        # Configure Gemini
        genai.configure(api_key=settings.google_api_key)
        model = genai.GenerativeModel(settings.llm_model)
        
        # Build context from extracted features
        context_parts = [f"Chief Complaint: {chief_complaint}"]
        
        if extracted_features:
            if extracted_features.get("pain_location"):
                context_parts.append(f"Pain Location: {extracted_features['pain_location']}")
            if extracted_features.get("pain_scale"):
                context_parts.append(f"Pain Level: {extracted_features['pain_scale']}/10")
            if extracted_features.get("symptom_onset"):
                context_parts.append(f"Onset: {extracted_features['symptom_onset']}")
            if extracted_features.get("duration"):
                context_parts.append(f"Duration: {extracted_features['duration']}")
        
        context = "\n".join(context_parts)
        
        # Create constraint-based prompt
        prompt = f"""You are a medical triage AI. Based on the patient's symptoms, determine which emergency red flag questions are MOST RELEVANT to ask.

PATIENT SYMPTOMS:
{context}

AVAILABLE RED FLAG QUESTIONS (you must choose 2-5 of these):
{_format_flags_for_prompt()}

CONSTRAINTS:
1. Select MINIMUM 2 and MAXIMUM 5 questions
2. Prioritize questions directly related to the symptom area
3. Always include life-threatening possibilities for that body system
4. Skip obviously irrelevant questions (e.g., don't ask about chest pain for ankle injury)
5. Include mental health screening ONLY if mental health keywords detected

RESPONSE FORMAT (JSON only, no explanation):
{{
  "relevant_flags": [
    {{
      "field": "field_name",
      "priority": "critical|high|medium",
      "relevance_reason": "one sentence why this is relevant"
    }}
  ],
  "reasoning": "brief overall reasoning for selections"
}}

Respond with JSON only:"""
        
        # Call LLM
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Parse JSON response
        import json
        # Extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        
        # Build relevant flags with full questions
        relevant_flags = []
        flag_fields = {flag["field"] for flag in result.get("relevant_flags", [])}
        
        for flag_data in result.get("relevant_flags", []):
            field = flag_data["field"]
            # Find the full question
            full_flag = next((f for f in ALL_RED_FLAGS if f["field"] == field), None)
            if full_flag:
                relevant_flags.append(RelevantRedFlag(
                    field=field,
                    question=full_flag["question"],
                    relevance_reason=flag_data.get("relevance_reason", "Relevant to symptoms"),
                    priority=flag_data.get("priority", "medium")
                ))
        
        # Safety check: ensure we have at least 2 questions
        if len(relevant_flags) < 2:
            logger.warning("LLM returned fewer than 2 flags, adding safety defaults")
            relevant_flags = _add_safety_defaults(relevant_flags, chief_complaint)
        
        # Ensure we don't exceed 5 questions
        relevant_flags = relevant_flags[:5]
        
        skipped = len(ALL_RED_FLAGS) - len(relevant_flags)
        
        logger.info(
            "Smart red flag filtering: selected %d/%d questions for '%s'",
            len(relevant_flags), len(ALL_RED_FLAGS), chief_complaint
        )
        
        return RedFlagFilterResult(
            relevant_flags=relevant_flags,
            total_relevant=len(relevant_flags),
            skipped_count=skipped,
            reasoning=result.get("reasoning", "Selected based on symptom relevance")
        )
        
    except Exception as e:
        logger.error("LLM red flag filtering failed: %s", e, exc_info=True)
        # Fallback: return all flags for safety
        return _get_all_flags_fallback()


def _format_flags_for_prompt() -> str:
    """Format all red flags for the LLM prompt."""
    lines = []
    for i, flag in enumerate(ALL_RED_FLAGS, 1):
        lines.append(f"{i}. field='{flag['field']}' - {flag['question']}")
    return "\n".join(lines)


def _add_safety_defaults(
    current_flags: List[RelevantRedFlag],
    chief_complaint: str
) -> List[RelevantRedFlag]:
    """Add default safety questions if too few were selected."""
    current_fields = {flag.field for flag in current_flags}
    
    # Always useful defaults
    defaults = ["altered_consciousness", "difficulty_breathing"]
    
    for field in defaults:
        if field not in current_fields:
            full_flag = next((f for f in ALL_RED_FLAGS if f["field"] == field), None)
            if full_flag:
                current_flags.append(RelevantRedFlag(
                    field=field,
                    question=full_flag["question"],
                    relevance_reason="Safety screening default",
                    priority="high"
                ))
        if len(current_flags) >= 2:
            break
    
    return current_flags


def _get_all_flags_fallback() -> RedFlagFilterResult:
    """Fallback: return all red flags if LLM filtering fails."""
    logger.warning("Using fallback: returning all 10 red flags")
    
    all_flags = [
        RelevantRedFlag(
            field=flag["field"],
            question=flag["question"],
            relevance_reason="Complete safety screening (LLM unavailable)",
            priority="medium"
        )
        for flag in ALL_RED_FLAGS
    ]
    
    return RedFlagFilterResult(
        relevant_flags=all_flags,
        total_relevant=len(all_flags),
        skipped_count=0,
        reasoning="LLM filtering unavailable - showing all questions for safety"
    )
