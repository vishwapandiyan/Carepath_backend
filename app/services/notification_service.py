"""
Notification Service - Business logic for patient notifications and task reminders
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.schemas.notification import (
    NotificationCreate,
    NotificationUpdate,
    NotificationOut,
    NotificationListResponse,
    TaskReframingResponse,
)

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    notification: NotificationCreate,
) -> NotificationOut:
    """Create a new notification."""
    
    # Set delivered_at if not scheduled for future
    delivered_at = None
    if not notification.scheduled_for or notification.scheduled_for <= datetime.now(timezone.utc):
        delivered_at = datetime.now(timezone.utc)
    
    db_notification = Notification(
        patient_id=notification.patient_id,
        notification_type=notification.notification_type,
        title=notification.title,
        message=notification.message,
        task_index=notification.task_index,
        task_text=notification.task_text,
        meta_data=notification.metadata,
        priority=notification.priority,
        scheduled_for=notification.scheduled_for,
        expires_at=notification.expires_at,
        delivered_at=delivered_at,
        status='pending',
    )
    
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    
    logger.info(
        "Created notification: type=%s patient=%s task_index=%s",
        notification.notification_type,
        notification.patient_id,
        notification.task_index,
    )
    
    return NotificationOut.model_validate(db_notification)


async def list_notifications(
    db: AsyncSession,
    patient_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> NotificationListResponse:
    """List notifications for a patient."""
    
    # Build query
    conditions = [Notification.patient_id == patient_id]
    
    if status:
        conditions.append(Notification.status == status)
    
    # Only show delivered or scheduled-for-past notifications
    conditions.append(
        (Notification.delivered_at.isnot(None)) | 
        (Notification.scheduled_for <= datetime.now(timezone.utc))
    )
    
    # Don't show expired
    conditions.append(
        (Notification.expires_at.is_(None)) |
        (Notification.expires_at > datetime.now(timezone.utc))
    )
    
    # Get notifications
    stmt = (
        select(Notification)
        .where(and_(*conditions))
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    
    # Get counts
    total_stmt = select(func.count(Notification.id)).where(and_(*conditions))
    total = (await db.execute(total_stmt)).scalar() or 0
    
    unread_stmt = select(func.count(Notification.id)).where(
        and_(
            Notification.patient_id == patient_id,
            Notification.status == 'pending',
            (Notification.delivered_at.isnot(None)) | 
            (Notification.scheduled_for <= datetime.now(timezone.utc))
        )
    )
    unread_count = (await db.execute(unread_stmt)).scalar() or 0
    
    pending_count = unread_count  # Same for now
    
    return NotificationListResponse(
        notifications=[NotificationOut.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        pending_count=pending_count,
    )


async def update_notification_status(
    db: AsyncSession,
    notification_id: str,
    patient_id: str,
    update_data: NotificationUpdate,
) -> Optional[NotificationOut]:
    """Update notification status (mark as read, dismissed, acted upon)."""
    
    stmt = (
        update(Notification)
        .where(
            and_(
                Notification.id == notification_id,
                Notification.patient_id == patient_id,
            )
        )
        .values(
            status=update_data.status,
            read_at=update_data.read_at or datetime.now(timezone.utc) if update_data.status == 'read' else None,
            acted_at=update_data.acted_at or datetime.now(timezone.utc) if update_data.status == 'acted_upon' else None,
        )
        .returning(Notification)
    )
    
    result = await db.execute(stmt)
    await db.commit()
    
    notification = result.scalar_one_or_none()
    if not notification:
        return None
    
    return NotificationOut.model_validate(notification)


async def generate_task_reminder(
    db: AsyncSession,
    patient_id: str,
    task_index: int,
    task_text: str,
    scheduled_for: Optional[datetime] = None,
) -> NotificationOut:
    """Generate a task reminder notification."""
    
    notification = NotificationCreate(
        patient_id=patient_id,
        notification_type='task_reminder',
        title='Care Plan Task Reminder',
        message=f'Time to complete: {task_text}',
        task_index=task_index,
        task_text=task_text,
        priority='normal',
        scheduled_for=scheduled_for,
        expires_at=(scheduled_for or datetime.now(timezone.utc)) + timedelta(hours=4) if scheduled_for else None,
        metadata={
            'action': 'complete_task',
            'action_url': f'/care-plans?task={task_index}',
        },
    )
    
    return await create_notification(db, notification)


async def reframe_task_with_llm(
    original_task: str,
    reason: Optional[str] = None,
) -> TaskReframingResponse:
    """Use LLM to reframe a task that patient couldn't complete."""
    
    try:
        import google.generativeai as genai
        from app.config import settings
        
        genai.configure(api_key=settings.google_api_key)
        model = genai.GenerativeModel(settings.llm_model)
        
        prompt = f"""You are a compassionate healthcare assistant helping patients with post-discharge care tasks.

A patient was unable to complete this task:
"{original_task}"

{f"Reason: {reason}" if reason else "No reason provided."}

Your job: Reframe this task to be more achievable while maintaining clinical benefit.

Options:
1. Make it EASIER (smaller steps, less frequency)
2. Provide ALTERNATIVE approach (different method, same goal)
3. EXTEND deadline (give more time)

Respond in JSON format:
{{
  "reframed_task": "The new, easier task description",
  "reasoning": "Brief explanation of why this is better",
  "difficulty_level": "easier" or "alternative" or "extended_deadline"
}}

Keep the reframed task under 100 characters. Be specific and actionable.
"""
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Parse JSON
        import json
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        
        return TaskReframingResponse(
            original_task=original_task,
            reframed_task=result['reframed_task'],
            reasoning=result['reasoning'],
            difficulty_level=result['difficulty_level'],
        )
        
    except Exception as e:
        logger.error("LLM task reframing failed: %s", e, exc_info=True)
        
        # Fallback: generic easier version
        return TaskReframingResponse(
            original_task=original_task,
            reframed_task=f"Try: {original_task.lower()[:80]}... (take your time)",
            reasoning="Simplified version with extended timeline",
            difficulty_level='easier',
        )


async def mark_task_complete(
    db: AsyncSession,
    patient_id: str,
    task_index: int,
    completed: bool,
    reason: Optional[str] = None,
) -> dict:
    """
    Mark a task as complete or trigger reframing if not completed.
    Returns updated task status and any reframing notification.
    """
    
    from app.db.models import PostDischargeStatus
    
    # Get post-discharge status
    stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient_id)
    result = await db.execute(stmt)
    status_row = result.scalar_one_or_none()
    
    if not status_row:
        raise ValueError(f"No post-discharge status found for patient {patient_id}")
    
    care_plan = status_row.care_plan
    tasks = care_plan.get('tasks', [])
    
    if task_index < 0 or task_index >= len(tasks):
        raise ValueError(f"Invalid task_index {task_index}")
    
    task = tasks[task_index]
    
    if completed:
        # Mark task as completed
        task['status'] = 'completed'
        care_plan['tasks'] = tasks
        status_row.care_plan = care_plan
        
        await db.commit()
        
        logger.info("Task %d marked complete for patient %s", task_index, patient_id)
        
        return {
            'status': 'completed',
            'task': task,
            'message': 'Great job! Task marked as complete.',
        }
    
    else:
        # Task not completed - reframe it
        original_task = task['task']
        
        # Generate reframed task
        reframed = await reframe_task_with_llm(original_task, reason)
        
        # Update task with reframed version
        task['task'] = reframed.reframed_task
        task['status'] = 'pending'
        task['reframed'] = True
        task['original_task'] = original_task
        care_plan['tasks'] = tasks
        status_row.care_plan = care_plan
        
        await db.commit()
        
        # Create notification about reframing
        notification = await create_notification(
            db,
            NotificationCreate(
                patient_id=patient_id,
                notification_type='task_reframed',
                title='Task Adjusted For You',
                message=f'We made this easier: {reframed.reframed_task}',
                task_index=task_index,
                task_text=reframed.reframed_task,
                priority='normal',
                metadata={
                    'original_task': original_task,
                    'reasoning': reframed.reasoning,
                    'difficulty_level': reframed.difficulty_level,
                },
            ),
        )
        
        # Notify care manager
        logger.info(
            "Task %d reframed for patient %s: %s -> %s",
            task_index,
            patient_id,
            original_task,
            reframed.reframed_task,
        )
        
        return {
            'status': 'reframed',
            'task': task,
            'reframing': reframed,
            'notification': notification,
            'message': 'We adjusted the task to make it easier.',
        }


async def schedule_task_reminders(
    db: AsyncSession,
    patient_id: str,
    care_plan: dict,
) -> List[NotificationOut]:
    """
    Schedule task-specific reminders based on task type.
    - Medications: 3x/day (8 AM, 2 PM, 8 PM)
    - BP monitoring: 2x/day (9 AM, 9 PM)
    - Glucose: 3x/day (before meals: 7 AM, 12 PM, 6 PM)
    - Other: 1x/day (9 AM)
    """
    
    notifications = []
    tasks = care_plan.get('tasks', [])
    now = datetime.now(timezone.utc)
    
    for idx, task in enumerate(tasks):
        if task.get('status') == 'completed':
            continue
        
        task_text = task['task'].lower()
        schedule_times = []
        
        # Determine schedule based on task type
        if 'medication' in task_text or 'medicine' in task_text:
            # 3x per day
            schedule_times = [
                now.replace(hour=8, minute=0, second=0, microsecond=0),
                now.replace(hour=14, minute=0, second=0, microsecond=0),
                now.replace(hour=20, minute=0, second=0, microsecond=0),
            ]
        elif 'blood pressure' in task_text or 'bp' in task_text:
            # 2x per day
            schedule_times = [
                now.replace(hour=9, minute=0, second=0, microsecond=0),
                now.replace(hour=21, minute=0, second=0, microsecond=0),
            ]
        elif 'glucose' in task_text or 'blood sugar' in task_text:
            # 3x per day (before meals)
            schedule_times = [
                now.replace(hour=7, minute=0, second=0, microsecond=0),
                now.replace(hour=12, minute=0, second=0, microsecond=0),
                now.replace(hour=18, minute=0, second=0, microsecond=0),
            ]
        else:
            # Default: 1x per day
            schedule_times = [now.replace(hour=9, minute=0, second=0, microsecond=0)]
        
        # Create reminders for each scheduled time
        for scheduled_time in schedule_times:
            # If time has passed today, schedule for tomorrow
            if scheduled_time <= now:
                scheduled_time += timedelta(days=1)
            
            notification = await generate_task_reminder(
                db,
                patient_id,
                idx,
                task['task'],
                scheduled_time,
            )
            notifications.append(notification)
    
    logger.info(
        "Scheduled %d task reminders for patient %s",
        len(notifications),
        patient_id,
    )
    
    return notifications
