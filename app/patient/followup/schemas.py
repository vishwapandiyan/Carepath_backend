from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class FollowUpTask(BaseModel):
    task: str
    status: str  # pending | completed


class FollowUpResponse(BaseModel):
    patient_id: str
    plan: List[FollowUpTask]
    next_checkin: Optional[datetime] = None
    is_scheduled: bool
    raw_agent_output: Optional[dict] = None
