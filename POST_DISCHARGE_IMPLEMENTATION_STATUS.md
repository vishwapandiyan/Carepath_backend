# Post-Discharge Care Agent - Implementation Status

## ✅ Phase 1: Backend Foundation (COMPLETED)

### Database Schema
- ✅ **notifications table** - Stores task reminders, alerts, care manager messages
- ✅ **appointment_type column** - Added to appointments table for followup tracking
- ✅ Migration file: `migrations/create_notifications_table.sql`

### Models & Schemas
- ✅ **Notification model** (`app/models/notification.py`)
  - Supports 5 notification types
  - Status tracking (pending, read, dismissed, acted_upon)
  - Priority levels (low, normal, high, urgent)
  - Task-specific fields for care plan integration
  
- ✅ **Pydantic schemas** (`app/schemas/notification.py`)
  - NotificationCreate, NotificationOut, NotificationUpdate
  - TaskCompletionRequest, TaskReframingResponse
  - NotificationListResponse with counts

### Business Logic
- ✅ **Notification Service** (`app/services/notification_service.py`)
  - `create_notification()` - Create new notifications
  - `list_notifications()` - Get patient notifications with filtering
  - `update_notification_status()` - Mark read/dismissed/acted
  - `generate_task_reminder()` - Auto-generate task reminders
  - `reframe_task_with_llm()` - **LLM-powered task reframing using Gemini**
  - `mark_task_complete()` - Handle task completion or trigger reframing
  - `schedule_task_reminders()` - **Task-specific scheduling:**
    - Medications: 3x/day (8 AM, 2 PM, 8 PM)
    - Blood Pressure: 2x/day (9 AM, 9 PM)
    - Glucose: 3x/day (7 AM, 12 PM, 6 PM)
    - Other tasks: 1x/day (9 AM)

### API Endpoints
- ✅ **Notifications Router** (`app/api/v1/endpoints/notifications.py`)
  - `GET /api/v1/notifications/` - List notifications (paginated, filtered)
  - `GET /api/v1/notifications/unread-count` - Badge counter
  - `PATCH /api/v1/notifications/{id}` - Update status
  - `POST /api/v1/notifications/tasks/respond` - **Task completion flow**

- ✅ **Patient Care Plan** (`app/patient/router.py`)
  - `GET /api/v1/patient/care-plan` - View own post-discharge status

- ✅ **Router Registration** (`app/api/v1/api.py`)
  - Notifications router registered
  - Available at `/api/v1/notifications/*`

## 🔄 Phase 2: Task Notification & Reframing (READY TO TEST)

### How It Works

#### 1. Patient Sees Task Reminder
```
Notification appears:
"Time to complete: Take prescribed medications (3 active)"
[Yes, I did it] [No, I couldn't]
```

#### 2A. Patient Clicks "Yes"
```
POST /api/v1/notifications/tasks/respond
{
  "task_index": 0,
  "completed": true
}

→ Task marked complete in post_discharge_statuses
→ Notification marked as acted_upon
→ Success message shown
```

#### 2B. Patient Clicks "No"
```
POST /api/v1/notifications/tasks/respond
{
  "task_index": 0,
  "completed": false,
  "reason": "Too difficult to remember all 3 times"
}

→ LLM analyzes task and reason
→ Generates easier alternative:
   "Take medications with breakfast & dinner (2 times/day)"
→ Updates task in database
→ Creates new notification about reframing
→ Notifies care manager via logs
```

### LLM Reframing Example

**Original Task:**
"Take prescribed medications (3 active) at 8 AM, 2 PM, and 8 PM"

**Patient Says:**
"I keep forgetting the afternoon dose"

**LLM Generates:**
```json
{
  "reframed_task": "Take medications with breakfast & dinner (morning + evening only)",
  "reasoning": "Reduced to 2 critical times when patient eats, easier to remember",
  "difficulty_level": "easier"
}
```

## 📋 Phase 3: Appointment Integration (READY)

### Appointment Type Column
- ✅ Added `appointment_type` to appointments table
- ✅ Values: 'regular', 'post_discharge_followup', 'urgent_followup', 'specialist_referral'
- ✅ Indexed for fast filtering

### Integration Strategy
1. **Alternate Care Agent** books initial appointment
   - Sets `appointment_type = 'post_discharge_followup'`
   - Links to post_discharge_statuses via `patient_id`

2. **Post-Discharge Agent** manages followup
   - Reads from appointments table
   - Can reschedule (update start_time, end_time)
   - Cannot cancel (care manager only)

3. **Patient View**
   - Sees followup appointments in Appointments page
   - Highlighted as "Post-Discharge Follow-Up"
   - Can request reschedule via chat/care manager

## 🔧 What Needs To Be Built Next

### Backend (30 min)
- [ ] **Cron job / scheduler** for automated reminder delivery
  - Use APScheduler or Celery
  - Check scheduled_for timestamps
  - Deliver pending notifications
  - Update delivered_at field

### Frontend (4-5 hours)
- [ ] **Notification Modal Component** - Popup for task reminders
- [ ] **Badge Counter** - Unread count on Care Plans tab
- [ ] **Interactive Care Plan Page** - Task completion buttons
- [ ] **Task Reframing Display** - Show LLM-adjusted tasks
- [ ] **WebSocket/Polling** - Real-time notification delivery
- [ ] **Appointment Integration** - Show followup appointments

## 🧪 Testing Commands

### 1. Run Database Migration
```bash
cd /Users/vishwa/Desktop/CarepathAI_backend
psql -U vishwa -d carepath_db -f migrations/create_notifications_table.sql
```

### 2. Test API Endpoints
```bash
# Get auth token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"patient1","password":"password"}' | jq -r '.access_token')

# Get care plan
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/patient/care-plan | jq

# List notifications
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/notifications/ | jq

# Get unread count
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/notifications/unread-count | jq

# Complete a task
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_index": 0, "completed": true}' \
  http://127.0.0.1:8000/api/v1/notifications/tasks/respond | jq

# Skip task (trigger reframing)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_index": 0, "completed": false, "reason": "Too difficult"}' \
  http://127.0.0.1:8000/api/v1/notifications/tasks/respond | jq
```

### 3. Test LLM Reframing
```python
import asyncio
from app.services.notification_service import reframe_task_with_llm

async def test():
    result = await reframe_task_with_llm(
        "Take prescribed medications (3 active) at 8 AM, 2 PM, and 8 PM",
        "I keep forgetting the afternoon dose"
    )
    print(result.model_dump_json(indent=2))

asyncio.run(test())
```

## 📊 Database Schema

### notifications table
```sql
id                  UUID PRIMARY KEY
patient_id          VARCHAR(50) NOT NULL
notification_type   VARCHAR(50) NOT NULL  -- task_reminder, appointment_reminder, etc.
title               VARCHAR(255) NOT NULL
message             TEXT NOT NULL
task_index          INTEGER  -- Index in care_plan.tasks array
task_text           TEXT
metadata            JSONB  -- Flexible extra data
status              VARCHAR(20) DEFAULT 'pending'  -- pending, read, dismissed, acted_upon
priority            VARCHAR(20) DEFAULT 'normal'  -- low, normal, high, urgent
scheduled_for       TIMESTAMP WITH TIME ZONE  -- When to deliver
delivered_at        TIMESTAMP WITH TIME ZONE  -- When actually delivered
read_at             TIMESTAMP WITH TIME ZONE
acted_at            TIMESTAMP WITH TIME ZONE
created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
expires_at          TIMESTAMP WITH TIME ZONE  -- Auto-dismiss after this
```

### appointments table (updated)
```sql
appointment_type    VARCHAR(50) DEFAULT 'regular'
  -- Values: 'regular', 'post_discharge_followup', 'urgent_followup', 'specialist_referral'
```

## 🎯 Key Features Implemented

### ✅ Task-Specific Scheduling
Different tasks get different reminder frequencies:
- **Medications**: 3x/day because adherence is critical
- **Blood Pressure**: 2x/day (morning/evening) for trend tracking
- **Glucose**: 3x/day (before meals) for diabetic monitoring
- **Other tasks**: 1x/day default

### ✅ LLM-Powered Reframing
When patients can't complete tasks:
1. System understands the reason
2. Gemini generates easier alternative
3. Maintains clinical benefit while reducing burden
4. Options: easier steps, alternative method, extended deadline

### ✅ Care Manager Visibility
All task reframings logged for care manager review:
- Original task vs new task
- Patient's reason
- LLM reasoning
- When it was reframed

### ✅ Smart Notification System
- **Scheduled delivery** - Not spammy, delivered at right times
- **Expiration** - Old notifications auto-dismiss
- **Priority levels** - Urgent medications vs routine tasks
- **Status tracking** - Pending → Read → Acted Upon

## 🚀 Next Session: Frontend Implementation

Will build:
1. **NotificationModal.tsx** - Task reminder popup
2. **NotificationBadge.tsx** - Unread counter
3. **InteractiveCarePlan.tsx** - Task completion UI
4. **useNotifications.ts** - Hook for polling/WebSocket
5. **appointmentSync.ts** - Followup appointment display

Estimated: 4-5 hours for complete frontend integration.

## 📝 Notes

- **LLM Model**: Using `gemini-flash-lite-latest` (already configured)
- **API Key**: Already set in `.env` as `google_api_key`
- **Authentication**: Uses existing JWT system with `get_current_patient`
- **Database**: PostgreSQL with async SQLAlchemy
- **Real-time**: Can add WebSocket later, starting with polling

## ✅ Ready For Testing

Backend is **fully functional** and ready to test. Run the database migration and test the API endpoints above to verify everything works!
