from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NavigationResponse(BaseModel):
    patient_id: str
    appointment_id: str
    category: str            # pcp | specialist | urgent-care | telehealth (from Care Options)
    provider_name: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    is_scheduled: bool
    raw_agent_output: Optional[dict] = None


class UpdateBookingRequest(BaseModel):
    appointment_id: str
    new_scheduled_at: Optional[datetime] = None
    provider_name: Optional[str] = None
    category: Optional[str] = None      # pcp | specialist | urgent-care | telehealth
    notes: Optional[str] = None
