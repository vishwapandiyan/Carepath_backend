from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from app.patient.pathway.schemas import PathwayResponse


# ── Request schemas ───────────────────────────────────────────────────────────

class RedFlagsIn(BaseModel):
    """
    10-field emergency red-flag checklist.

    Each question already describes a SEVERE, emergency-level presentation.
    A patient who answers True to any field is self-declaring an emergency.

    Value semantics:
        True  → severe symptom IS present → triggers YES (Emergency Room)
        False → symptom is NOT present
        None  → not answered; treated as False by the engine (no trigger)
    """
    chest_pain: bool | None = Field(
        None,
        description=(
            "Chest pain or pressure — squeezing, tightness, or pressure in the chest; "
            "not mild soreness."
        ),
    )
    difficulty_breathing: bool | None = Field(
        None,
        description=(
            "Severe difficulty breathing — cannot speak in full sentences, "
            "gasping, or using accessory muscles to breathe."
        ),
    )
    altered_consciousness: bool | None = Field(
        None,
        description=(
            "Loss of consciousness, fainting, or acute confusion/unresponsiveness."
        ),
    )
    severe_bleeding: bool | None = Field(
        None,
        description=(
            "Severe uncontrolled bleeding that won't stop despite direct pressure."
        ),
    )
    stroke_symptoms: bool | None = Field(
        None,
        description=(
            "Active stroke symptoms (FAST): facial drooping, sudden arm/leg weakness, "
            "or inability to speak — happening RIGHT NOW."
        ),
    )
    suicidal_ideation: bool | None = Field(
        None,
        description="Expressed intent or ideation to self-harm or end life.",
    )
    anaphylaxis: bool | None = Field(
        None,
        description=(
            "Severe systemic allergic reaction: throat swelling, widespread hives, "
            "difficulty swallowing, or feeling faint after allergen exposure."
        ),
    )
    high_fever: bool | None = Field(
        None,
        description="Dangerously high fever — 103°F (39.4°C) or higher.",
    )
    unable_to_walk: bool | None = Field(
        None,
        description=(
            "Completely unable to walk, stand, or bear any weight — not just limping."
        ),
    )
    severe_abdominal_pain: bool | None = Field(
        None,
        description=(
            "Severe acute abdominal pain — sharp, stabbing, or crushing belly pain."
        ),
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class RedFlagsOut(BaseModel):
    session_id: str
    saved_at: datetime


class SafetyResult(BaseModel):
    session_id: str
    result: Literal["YES", "NO", "ERROR"]
    next_action: Literal[
        "EMERGENCY_PATHWAY",   # YES   — route to Emergency Room immediately
        "CMS_ML",              # NO    — hand off to downstream ML pathway
        "ERROR",               # ERROR — engine failure; audit row written, HTTP 500 raised
    ]
    triggered_rules: list[str] = Field(
        default_factory=list,
        description="Rule IDs that fired (non-empty only when result=YES).",
    )
    error_detail: str | None = None
    evaluated_at: datetime
    pathway: Optional[PathwayResponse] = Field(
        None,
        description="ML Avoidable ED prediction result (attached when result=NO / CMS_ML).",
    )
