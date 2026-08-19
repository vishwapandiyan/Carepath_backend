from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema"""
    username: str


class UserResponse(BaseModel):
    """User response schema"""
    id: int
    username: str
    role: UserRole
    patient_id: Optional[str | int] = None
    created_at: Optional[datetime] = None

    
    class Config:
        from_attributes = True
