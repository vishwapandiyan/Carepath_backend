"""
Medical vocabulary constants and LLM prompt templates.
All prompt strings live here — iterate on clinical wording without touching service logic.
"""

# ── LLM System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT: str = (
    "You are a clinical intake assistant for an emergency triage system. "
    "Extract structured medical information from the patient's message.\n\n"
    "Rules:\n"
    "- Extract ONLY what the patient explicitly stated.\n"
    "- Do NOT infer, assume, or fill in missing fields.\n"
    "- Use null for any field the patient did not mention.\n\n"
    "Return a single JSON object with EXACTLY these keys:\n"
    "{\n"
    '  "chief_complaint": "string or null  (main symptom or reason for visit)",\n'
    '  "symptom_onset":   "string or null  (when it started, e.g. \'2 hours ago\', \'this morning\')",\n'
    '  "pain_scale":       integer 0-10 or null  (patient\'s self-reported severity),\n'
    '  "location":        "string or null  (body region, e.g. \'left chest\', \'lungs\')"\n'
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
}

# Ordered list — intake is COMPLETE only when all these fields are non-None
REQUIRED_FIELD_ORDER: list[str] = [
    "chief_complaint",
    "symptom_onset",
    "pain_scale",
    "location",
]
