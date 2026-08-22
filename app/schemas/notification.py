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
        # Map 'meta_data' field from database to 'metadata' in response
        populate_by_name = True
    
    @classmethod
    def model_validate(cls, obj):
        """Custom validation to handle meta_data -> metadata conversion"""
        if hasattr(obj, 'meta_data'):
            # Convert database object with meta_data to dict
            data = {
                'id': str(obj.id),  # Convert UUID to string
                'patient_id': obj.patient_id,
                'notification_type': obj.notification_type,
                'title': obj.title,
                'message': obj.message,
                'task_index': obj.task_index,
                'task_text': obj.task_text,
                'metadata': obj.meta_data,  # Map meta_data to metadata
                'priority': obj.priority,
                'scheduled_for': obj.scheduled_for,
                'expires_at': obj.expires_at,
                'status': obj.status,
                'delivered_at': obj.delivered_at,
                'read_at': obj.read_at,
                'acted_at': obj.acted_at,
                'created_at': obj.created_at,
            }
            return super().model_validate(data)
        return super().model_validate(obj)


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
