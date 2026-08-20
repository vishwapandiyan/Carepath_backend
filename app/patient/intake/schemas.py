from datetime import datetime
from pydantic import BaseModel, Field


class LLMExtraction(BaseModel):
    """
    Structured output produced by the LLM from a patient's free-text message.
    Captures the 4 fields needed for emergency triage routing, plus an optional answer to patient queries.

    All fields are nullable — the LLM must NOT guess or infer missing information.
    """
    chief_complaint: str | None = None
    symptom_onset: str | None = None          # replaces duration — onset is clinically more relevant
    pain_scale: int | None = Field(None, ge=0, le=10)
    location: str | None = None
    pain_duration: str | None = None
    pain_character: str | None = None
    pain_radiating: str | None = None
    symptom_trend: str | None = None
    user_query_answer: str | None = None


# ── Request schemas ───────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    patient_id: str = Field(..., description="Unique patient identifier")


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, description="Patient's free-text message")


# ── Response schemas ──────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    session_id: str
    patient_id: str
    status: str                              # IN_PROGRESS | COMPLETE | ERROR
    features: LLMExtraction | None = None
    messages: list[dict] = Field(default_factory=list)
    next_question: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    session_id: str
    extracted: LLMExtraction | None = None
    next_question: str | None = None
    status: str                              # IN_PROGRESS | COMPLETE | ERROR
    error_detail: str | None = None
