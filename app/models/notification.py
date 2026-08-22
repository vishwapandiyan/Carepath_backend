"""
Notification Model - Patient notification system for care reminders
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, DateTime, JSON, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Notification(Base):
    """
    Patient notifications for post-discharge care reminders and alerts.
    Supports task reminders, appointment alerts, and care manager messages.
    """
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    patient_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    notification_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        index=True
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Task-specific fields (nullable)
    task_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    task_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata JSONB - using 'meta_data' to avoid SQLAlchemy reserved 'metadata'
    meta_data: Mapped[dict] = mapped_column('metadata', JSON, nullable=False, default=dict)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default='normal')
    
    # Scheduling timestamps
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('task_reminder', 'appointment_reminder', 'care_manager_message', 'task_reframed', 'followup_scheduled')",
            name='check_notification_type'
        ),
        CheckConstraint(
            "status IN ('pending', 'read', 'dismissed', 'acted_upon')",
            name='check_notification_status'
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name='check_notification_priority'
        ),
    )
