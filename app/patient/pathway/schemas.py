from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class PathwayDecision(str, Enum):
    NOT_AVOIDABLE = "NOT_AVOIDABLE"                  # -> Emergency Room
    POTENTIALLY_AVOIDABLE = "POTENTIALLY_AVOIDABLE"  # -> continues to Care Options


class PathwayResponse(BaseModel):
    patient_id: str
    risk_score: float
    decision: PathwayDecision
    predicted_at: datetime
    raw_agent_output: Optional[dict] = None  # pass-through from teammate's agent output
