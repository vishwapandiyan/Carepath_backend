"""
Medical vocabulary constants and LLM prompt templates.
All prompt strings live here — iterate on clinical wording without touching service logic.
"""

# ── LLM System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT: str = (
    "You are a specialized clinical intake and healthcare assistant for an emergency triage system.\n\n"
    "STRICT DOMAIN SCOPING RULE:\n"
    "- You MUST ONLY answer questions directly related to medical/health concerns, symptoms, clinical definitions, "
    "appointment scheduling, care management plans, and post-discharge follow-up.\n"
    "- IF THE PATIENT ASKS ANYTHING OUTSIDE THIS MEDICAL/HEALTHCARE SCOPE (for example: sports, cricket, MS Dhoni, "
    "entertainment, coding, history, politics, general trivia, pop culture, etc.):\n"
    "  You MUST REJECT the non-medical question and set 'user_query_answer' strictly to:\n"
    "  \"I am a specialized Clinical & Healthcare Assistant. I can only assist with medical questions, health concerns, appointment scheduling, and care management plans. How can I help you with your health or care plan today?\"\n\n"
    "Your tasks:\n"
    "1. Extract structured medical information from the patient's message.\n"
    "2. If the patient asked a valid medical, healthcare, appointment, or care plan question, provide a helpful, clear, and concise 2-3 sentence answer in the 'user_query_answer' field.\n"
    "   If the patient asked an off-topic non-medical question, provide the strict rejection response above.\n"
    "   If the patient did NOT ask any question or query, set 'user_query_answer' to null.\n\n"
    "Rules for clinical field extraction:\n"
    "- Extract ONLY what the patient explicitly stated.\n"
    "- Do NOT infer, assume, or fill in missing clinical fields.\n"
    "- Use null for any field the patient did not mention.\n\n"
    "Return a single JSON object with EXACTLY these keys:\n"
    "{\n"
    '  "chief_complaint": "string or null  (main symptom or reason for visit)",\n'
    '  "symptom_onset":   "string or null  (when it started, e.g. \'2 hours ago\', \'this morning\')",\n'
    '  "pain_scale":       integer 0-10 or null  (patient\'s self-reported severity),\n'
    '  "location":        "string or null  (body region, e.g. \'left chest\', \'lungs\')",\n'
    '  "pain_duration":   "string or null  (how long symptoms have lasted, e.g. \'2 hours\', \'3 days\')",\n'
    '  "pain_character":  "string or null  (quality: sharp, dull, throbbing, burning, cramping, pressure)",\n'
    '  "pain_radiating":  "string or null  (does pain spread: yes/no and where)",\n'
    '  "symptom_trend":   "string or null  (better, worse, or stable)",\n'
    '  "user_query_answer": "string or null  (answer if query is healthcare related, decline message if off-topic, or null if no question)"\n'
    "}\n\n"
    "Return ONLY the JSON object. No markdown, no explanation, no extra keys."
)


# ── Question Templates (keyed by field name) ──────────────────────────────────

QUESTION_TEMPLATES: dict[str, str] = {
    "chief_complaint": (
        "What is your main concern or symptom today? "
        "Please describe what you are experiencing."
    ),
    "symptom_onset": (
        "When did these symptoms start? Was the onset sudden or did it develop gradually?"
    ),
    "pain_scale": (
        "On a scale of 0 to 10 — 0 being no discomfort and 10 being the worst pain "
        "imaginable — how would you rate what you're feeling right now?"
    ),
    "location": (
        "Where exactly in your body are you experiencing this? "
        "Can you describe or point to the specific area?"
    ),
    "pain_duration": (
        "How long have you been experiencing this symptom? "
        "Please tell me in hours, days, or weeks."
    ),
    "pain_character": (
        "How would you describe the quality of the pain or discomfort? "
        "For example: sharp, dull, throbbing, burning, cramping, pressure, stabbing, or aching."
    ),
    "pain_radiating": (
        "Does the pain spread or radiate to other parts of your body? "
        "Please answer yes or no, and if yes, tell me where it spreads to."
    ),
    "symptom_trend": (
        "Are your symptoms getting better, getting worse, or staying about the same since they started?"
    ),
}

# Ordered list — intake is COMPLETE only when all these fields are non-None
REQUIRED_FIELD_ORDER: list[str] = [
    "chief_complaint",
    "symptom_onset",
    "pain_scale",
    "location",
    "pain_duration",
    "pain_character",
    "pain_radiating",
    "symptom_trend",
]


# ── Symptom Classification Integration ───────────────────────────────────────

def enhance_intake_with_classification(intake_data: dict) -> dict:
    """
    Enhance intake data with symptom category classification
    
    Args:
        intake_data: Dict with 'chief_complaint' and other intake fields
    
    Returns:
        Enhanced intake_data with added fields:
        - primary_symptom_category
        - symptom_category_confidence
        - symptom_category_method
        - is_safety_category
    """
    from app.services.symptom_classifier import symptom_classifier
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Only classify if chief_complaint exists
    if intake_data.get("chief_complaint"):
        classification_result = symptom_classifier.classify_complaint(
            chief_complaint=intake_data["chief_complaint"],
            additional_context=None  # Could add patient history if available
        )
        
        # Add classification fields
        intake_data["primary_symptom_category"] = classification_result["category"]
        intake_data["symptom_category_confidence"] = classification_result["confidence"]
        intake_data["symptom_category_method"] = classification_result["method"]
        intake_data["is_safety_category"] = classification_result["is_safety_category"]
        
        logger.info(
            f"Classified complaint '{intake_data['chief_complaint'][:50]}...' "
            f"→ category '{classification_result['category']}' "
            f"(confidence: {classification_result['confidence']}, "
            f"method: {classification_result['method']})"
        )
    else:
        # No chief complaint - use default
        intake_data["primary_symptom_category"] = "mild_general_symptom"
        intake_data["symptom_category_confidence"] = "low"
        intake_data["symptom_category_method"] = "default"
        intake_data["is_safety_category"] = False
    
    return intake_data
