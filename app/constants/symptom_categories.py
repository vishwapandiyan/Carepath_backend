"""
Symptom categories from alternate care agent YAML rules
These MUST match rules/care_destination_rules.yaml exactly

Source: alternate_care_agent 2/rules/care_destination_rules.yaml
Extracted from all rule conditions with primary_symptom_category
"""

# Extracted from care_destination_rules.yaml - ALL categories used in rules
ALLOWED_SYMPTOM_CATEGORIES = [
    # High severity (SAFETY-000 rule)
    "chest_pain",
    "severe_breathing_difficulty",
    "severe_abdominal_pain_or_trauma",
    "neuro_deficit",
    
    # Common categories
    "minor_infection",              # Sore throat, UTI, minor infections
    "mild_breathing_difficulty",    # Mild respiratory issues (not severe)
    "back_pain",                    # Back/spine pain
    "chronic_disease_flareup",      # Diabetes, CHF, CKD flareups
    "mild_general_symptom",         # Headache, fatigue, dizziness
    "dental_pain",                  # Toothache, dental issues
]

# Keyword mapping for fallback classification
CATEGORY_KEYWORDS = {
    "chest_pain": [
        "chest pain", "chest pressure", "chest tightness", "heart pain"
    ],
    "severe_breathing_difficulty": [
        "can't breathe", "cannot breathe", "severe breathing", "gasping"
    ],
    "severe_abdominal_pain_or_trauma": [
        "severe abdominal", "severe stomach", "abdominal trauma", "stabbing pain abdomen"
    ],
    "neuro_deficit": [
        "numbness", "tingling", "weakness in limb", "facial droop", "slurred speech"
    ],
    "minor_infection": [
        "infection", "sore throat", "uti", "urinary", "fever", "flu", "cold",
        "throat infection", "minor infection"
    ],
    "mild_breathing_difficulty": [
        "breathing", "shortness of breath", "wheezing", "respiratory", "cough",
        "mild breathing", "breathing problem"
    ],
    "back_pain": [
        "back pain", "spine", "lower back", "lumbar", "upper back", "back ache"
    ],
    "chronic_disease_flareup": [
        "diabetes", "heart failure", "kidney disease", "chronic condition",
        "flare up", "flareup", "condition worsening"
    ],
    "mild_general_symptom": [
        "headache", "dizziness", "fatigue", "tired", "weak", "nausea",
        "general symptom", "not feeling well", "malaise"
    ],
    "dental_pain": [
        "tooth", "dental", "toothache", "gum", "jaw", "teeth", "tooth pain"
    ],
}

# Human-readable descriptions for UI/prompts
CATEGORY_DESCRIPTIONS = {
    "chest_pain": "Chest pain or pressure (potential cardiac issue)",
    "severe_breathing_difficulty": "Severe difficulty breathing or gasping",
    "severe_abdominal_pain_or_trauma": "Severe abdominal pain or trauma",
    "neuro_deficit": "Neurological symptoms (numbness, weakness, speech problems)",
    "minor_infection": "Minor infections like sore throat, UTI, or mild fever",
    "mild_breathing_difficulty": "Mild breathing problems or respiratory symptoms",
    "back_pain": "Back or spine pain",
    "chronic_disease_flareup": "Worsening of existing chronic condition",
    "mild_general_symptom": "General symptoms like headache, dizziness, or fatigue",
    "dental_pain": "Dental or tooth-related pain",
}

# Safety categories that should trigger immediate review
SAFETY_CATEGORIES = [
    "chest_pain",
    "severe_breathing_difficulty",
    "severe_abdominal_pain_or_trauma",
    "neuro_deficit",
]
