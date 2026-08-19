from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class PatientBase(BaseModel):
    """Base patient schema"""
    mrn: str
    first_name: str
    last_name: str


class PatientResponse(BaseModel):
    """Patient response schema"""
    id: int
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class PatientDetail(PatientResponse):
    """Detailed patient schema - for future EHR data"""
    pass
