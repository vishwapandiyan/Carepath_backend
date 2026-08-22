"""
Notifications API Router - Patient notification endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_patient
from app.db.base import get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationOut,
    NotificationListResponse,
    NotificationUpdate,
    TaskCompletionRequest,
)
from app.services import notification_service

router = APIRouter(
    prefix="/notifications",
    tags=["Patient - Notifications"],
)


@router.get(
    "/",
    response_model=NotificationListResponse,
    summary="List my notifications",
    description="Get all notifications for the authenticated patient. Includes task reminders, appointment alerts, and care manager messages.",
)
async def list_notifications(
    status: str | None = Query(None, description="Filter by status: pending, read, dismissed, acted_upon"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """List notifications for authenticated patient."""
    
    return await notification_service.list_notifications(
        db=db,
        patient_id=current_user.patient_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{notification_id}",
    response_model=NotificationOut,
    summary="Update notification status",
    description="Mark notification as read, dismissed, or acted upon.",
)
async def update_notification(
    notification_id: str,
    update: NotificationUpdate,
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> NotificationOut:
    """Update notification status."""
    
    result = await notification_service.update_notification_status(
        db=db,
        notification_id=notification_id,
        patient_id=current_user.patient_id,
        update_data=update,
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )
    
    return result


@router.post(
    "/tasks/respond",
    summary="Respond to task reminder",
    description="Mark task as complete or request reframing if unable to complete.",
)
async def respond_to_task(
    request: TaskCompletionRequest,
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    """
    Patient responds to task reminder.
    - If completed=True: Mark task complete
    - If completed=False: Trigger LLM reframing with optional reason
    """
    
    try:
        result = await notification_service.mark_task_complete(
            db=db,
            patient_id=current_user.patient_id,
            task_index=request.task_index,
            completed=request.completed,
            reason=request.reason,
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/unread-count",
    summary="Get unread notification count",
    description="Quick endpoint to show badge counter in UI",
)
async def get_unread_count(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get count of unread notifications."""
    
    result = await notification_service.list_notifications(
        db=db,
        patient_id=current_user.patient_id,
        status='pending',
        limit=1,
        offset=0,
    )
    
    return {
        'unread_count': result.unread_count,
        'pending_count': result.pending_count,
    }
