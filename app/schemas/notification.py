"""
Notification Schemas - Pydantic models for API requests/responses
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# Enums
NotificationType = Literal[
    'task_reminder',
    'appointment_reminder', 
    'care_manager_message',
    'task_reframed',
    'followup_scheduled'
]

NotificationStatus = Literal['pending', 'read', 'dismissed', 'acted_upon']
NotificationPriority = Literal['low', 'normal', 'high', 'urgent']


class NotificationBase(BaseModel):
    """Base notification fields"""
    notification_type: NotificationType
    title: str = Field(..., max_length=255)
    message: str
    task_index: Optional[int] = None
    task_text: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    priority: NotificationPriority = 'normal'
    scheduled_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class NotificationCreate(NotificationBase):
    """Create new notification"""
    patient_id: str = Field(..., max_length=50)


class NotificationUpdate(BaseModel):
    """Update notification status"""
    status: NotificationStatus
    read_at: Optional[datetime] = None
    acted_at: Optional[datetime] = None


class NotificationOut(NotificationBase):
    """Notification response"""
    id: str
    patient_id: str
    status: NotificationStatus
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    acted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
        # Map 'metadata' field to 'meta_data' column in database
        populate_by_name = True


class NotificationListResponse(BaseModel):
    """Paginated list of notifications"""
    notifications: list[NotificationOut]
    total: int
    unread_count: int
    pending_count: int


class TaskCompletionRequest(BaseModel):
    """Patient response to task reminder"""
    task_index: int
    completed: bool = Field(..., description="True if task done, False if not done")
    reason: Optional[str] = Field(None, description="Why task wasn't completed (if completed=False)")


class TaskReframingResponse(BaseModel):
    """LLM-generated reframed task"""
    original_task: str
    reframed_task: str
    reasoning: str
    difficulty_level: Literal['easier', 'alternative', 'extended_deadline']
