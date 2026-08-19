from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class CareCategory(str, Enum):
    PCP = "pcp"
    SPECIALIST = "specialist"
    URGENT_CARE = "urgent-care"
    TELEHEALTH = "telehealth"


class CareOptionsResponse(BaseModel):
    patient_id: str
    category: CareCategory
    determined_at: datetime
    raw_agent_output: Optional[dict] = None
