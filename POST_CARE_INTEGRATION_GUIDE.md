# Post-Care Agentic Flow Integration Guide
## Complete Backend Database & Frontend Integration

**Last Updated:** August 22, 2026  
**Status:** Ready for Integration  
**Database:** `carepath_db` (PostgreSQL 5432)

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Database Setup](#database-setup)
3. [Backend Configuration](#backend-configuration)
4. [Frontend Integration](#frontend-integration)
5. [Testing the Integration](#testing-the-integration)
6. [Production Deployment](#production-deployment)

---

## Quick Start

### Prerequisites
- PostgreSQL 5432 running on localhost
- Backend: Python 3.10+, FastAPI
- Frontend: Node.js 18+, React + TypeScript
- Shared database: `carepath_db`

### 5-Minute Integration Test
```bash
# 1. Run all database migrations
cd /Users/vishwa/Desktop/CarepathAI_backend
psql -U vishwa -d carepath_db -f migrations/001_create_main_schema.sql
psql -U vishwa -d carepath_db -f migrations/create_care_plan_tables.sql
psql -U vishwa -d carepath_db -f migrations/create_appointment_tables.sql

# 2. Start backend
uvicorn app.main:app --reload --port 8000

# 3. Start frontend
cd /Users/vishwa/Desktop/CarePath_CTS
npm run dev

# 4. Test the flow
# Visit http://localhost:5173 and follow test instructions below
```

---

## Database Setup

### Current Database Status

| Component | Status | Location |
|-----------|--------|----------|
| Main Schema | ✅ Created | `migrations/001_create_main_schema.sql` |
| Care Plan Tables | ✅ Created | `migrations/create_care_plan_tables.sql` |
| Appointment Tables | ✅ Created | `migrations/create_appointment_tables.sql` |
| Financial Tables | ✅ Created | `migrations/002_create_financial_schema.sql` |

### Tables Used by Post-Care Flow

```
patient_ehr (already exists)
    ├── mrn (UNIQUE) ← Primary identifier
    ├── patient_id
    └── Clinical fields (vitals, labs, conditions)

care_plans (newly created)
    ├── id (VARCHAR PK) = "CP-{UUID}"
    ├── mrn (FK to patient_ehr)
    ├── risk_level (HIGH|MODERATE|LOW)
    ├── intensity (INTENSIVE|REGULAR|BASIC)
    └── status (ACTIVE|COMPLETED|EXPIRED|CANCELLED)

care_plan_tasks (newly created)
    ├── id (VARCHAR PK) = "T-{UUID}"
    ├── care_plan_id (FK)
    ├── task_type (FREQUENT_CHECKINS, MEDICATION_REVIEW, etc.)
    ├── task_description (TEXT)
    └── status (PENDING|IN_PROGRESS|COMPLETED)

follow_up_checkins (newly created)
    ├── id (VARCHAR PK) = "CHK-{UUID}"
    ├── task_id (FK)
    ├── checkin_message (TEXT)
    ├── patient_response (TEXT)
    ├── classification (NORMAL|CONCERN|URGENT)
    └── status (SCHEDULED|SENT|RESPONDED)

appointment_sessions (newly created)
    ├── session_id (VARCHAR PK)
    ├── mrn (FK)
    ├── source (PATIENT|POST_CARE)
    ├── care_plan_id (FK) ← Links post-care to appointments
    ├── destination (PCP|URGENT_CARE|SPECIALIST)
    ├── specialty (CARDIOLOGY, etc.)
    └── workflow_stage (NAVIGATION_COMPLETE→BOOKED)

appointment_providers (test data exists)
    ├── provider_id
    ├── provider_name
    ├── destination
    ├── specialty
    ├── address, latitude, longitude
    └── active

provider_slots (test data exists)
    ├── slot_id
    ├── provider_id (FK)
    ├── start_time, end_time
    └── status (AVAILABLE|BOOKED)

appointments (ready for bookings)
    ├── appointment_id
    ├── mrn
    ├── provider_id
    ├── slot_id
    └── status (BOOKED|CANCELLED|COMPLETED)
```

### Missing Migrations

None! All required tables are created. However, you need to:

1. **Add test data for post-care** (optional but recommended):

```sql
-- Insert test cardiology provider (Chennai area)
INSERT INTO appointment_providers (provider_id, provider_name, destination, specialty, address, latitude, longitude, active)
VALUES 
('TEST-CARDIO-001', 'Test Cardiology Center', 'SPECIALIST', 'CARDIOLOGY', 
 'Test Medical Center, 100 Health Ave, Chennai', 13.085, 80.275, true)
ON CONFLICT (provider_id) DO NOTHING;

-- Insert test slots for next 7 days
INSERT INTO provider_slots (slot_id, provider_id, start_time, end_time, status)
SELECT 
    'slot_test_cardio_' || to_char(slot_time, 'YYYYMMDDHH24'),
    'TEST-CARDIO-001',
    slot_time,
    slot_time + INTERVAL '30 minutes',
    'AVAILABLE'
FROM generate_series(
    NOW() + INTERVAL '1 day',
    NOW() + INTERVAL '7 days',
    INTERVAL '1 hour'
) AS slot_time
WHERE EXTRACT(HOUR FROM slot_time) BETWEEN 9 AND 17
ON CONFLICT (slot_id) DO NOTHING;
```

2. **Verify database connectivity:**

```bash
psql -U vishwa -d carepath_db -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'care_%' OR table_name LIKE 'appointment_%';"
```

Expected output:
```
 table_name
--------------------------
 care_plans
 care_plan_tasks
 follow_up_checkins
 appointment_sessions
 appointment_providers
 provider_slots
 appointments
(7 rows)
```

---

## Backend Configuration

### Environment Variables

Your backend `.env` should have:

```env
# Database (MUST match across all services)
DATABASE_URL=postgresql+asyncpg://vishwa@localhost:5432/carepath_db

# Post-Care sync connection (for post_care module)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=carepath_db
DB_USER=vishwa
DB_PASSWORD=

# LLM Keys (for post-care agents)
NVIDIA_API_KEY=your-nvidia-key
GROQ_API_KEY=your-groq-key
GOOGLE_API_KEY=your-google-key

# Appointment booking service (teammate's microservice)
APPOINTMENT_AGENT_BASE_URL=http://localhost:8001
```

### Backend Architecture

```
app/
├── main.py                              # FastAPI app entry point
├── config.py                            # Settings (DATABASE_URL)
├── api/v1/
│   ├── api.py                           # Router registration
│   └── endpoints/
│       ├── patient_response.py          # NEW: POST /patients/{id}/care-plan-response
│       └── care_plan_generation.py      # Initial post-care trigger
├── integrations/
│   └── post_care_adapter.py             # Bridge to post_care module
├── services/
│   └── alternate_care/
│       └── agents/appointment_agent.py  # Shared appointment booking
└── care_manager/
    └── post_discharge/
        ├── router.py                    # Care manager post-discharge endpoints
        └── service.py                   # Post-discharge business logic

post_care/                               # Agentic orchestrator (separate module)
├── database/
│   ├── connection.py                    # PostgreSQL sync connection
│   └── repositories.py                  # Data access layer
├── orchestrator/
│   ├── agentic_graph_builder.py         # LangGraph workflow (non-blocking)
│   ├── agentic_tools.py                 # LLM tool registry
│   └── agentic_guardrails.py            # Conditional tool availability
├── agents/
│   ├── care_plan/agent.py               # Care Plan Agent
│   ├── follow_up/agent.py               # Follow-Up Agent
│   ├── response_analyzer/agent.py       # Patient Response Analyzer
│   └── care_continuity/agent.py         # Care Continuity Routing
└── services/
    ├── care_plan_service_postgresql.py  # Care plan CRUD + revision
    └── appointment_handoff.py           # Post-care → Appointment integration
```

### Key Backend Files Modified

| File | Change Summary |
|------|---------------|
| `app/api/v1/endpoints/patient_response.py` | **NEW** — Async patient response endpoint |
| `app/integrations/post_care_adapter.py` | Auto-notification trigger after workflow |
| `app/services/alternate_care/agents/appointment_agent.py` | Source-aware (PATIENT vs POST_CARE) |
| `post_care/orchestrator/agentic_graph_builder.py` | Non-blocking, routes to `complete` after follow-up |
| `post_care/services/appointment_handoff.py` | **NEW** — Appointment booking integration |
| `post_care/services/care_plan_service_postgresql.py` | Added `revise_care_plan()` for CONCERN responses |

### API Endpoints for Post-Care

#### 1. Initial Care Plan Generation (Phase 1)
```http
POST /api/v1/patients/{mrn}/post-care/generate
Content-Type: application/json

Response 200:
{
  "status": "success",
  "care_plan_id": "CP-0AEB878E",
  "risk_level": "HIGH",
  "intensity": "INTENSIVE",
  "tasks": [
    {
      "task_id": "T-ABC123",
      "task_type": "FREQUENT_CHECKINS",
      "description": "Call patient within 24 hours",
      "status": "PENDING"
    }
  ],
  "follow_up": {
    "checkin_id": "CHK-XYZ789",
    "message": "How are you feeling today?",
    "status": "SENT"
  }
}
```

#### 2. Patient Response Handling (Phase 2)
```http
POST /api/v1/patients/{patient_id}/care-plan-response
Content-Type: application/json

{
  "response": "I'm feeling chest pain and shortness of breath"
}

Response 200 (URGENT → Appointment Handoff):
{
  "status": "URGENT",
  "care_plan_id": "CP-0AEB878E",
  "revised": true,
  "new_tasks": [
    {
      "task_id": "T-DEF456",
      "task_type": "FOLLOWUP_APPOINTMENT",
      "description": "Cardiology consultation scheduled",
      "status": "IN_PROGRESS"
    }
  ],
  "appointment": {
    "session_id": "pc_appointment_MRN000015_urgent_1234",
    "destination": "SPECIALIST",
    "specialty": "CARDIOLOGY",
    "providers_found": 3,
    "workflow_stage": "AVAILABILITY_CHECKED",
    "message": "We found available appointments. Booking in progress..."
  }
}

Response 200 (CONCERN → Revision):
{
  "status": "CONCERN",
  "care_plan_id": "CP-0AEB878E",
  "revised": true,
  "new_tasks": [...],
  "message": "Your care plan has been updated based on your response."
}

Response 200 (NORMAL):
{
  "status": "NORMAL",
  "message": "Thank you for your update. Continue with your care plan."
}
```

---

## Frontend Integration

### Frontend Service Structure

```
src/services/
├── api.ts                    # Main API aggregator
├── apiClient.ts              # Axios client (BASE_URL)
├── careService.ts            # POST-CARE specific (NEW)
├── careManagerService.ts     # Care manager dashboard
└── predictionService.ts      # ML predictions
```

### Add Post-Care Service

Create `/Users/vishwa/Desktop/CarePath_CTS/src/services/careService.ts`:

```typescript
/**
 * Post-Care Service — Patient Care Plan Management
 * Handles initial care plan generation and async patient responses
 */

import client from './apiClient';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface CareTask {
  task_id: string;
  task_type: string;
  description: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'SKIPPED';
  scheduled_date?: string;
  priority?: 'LOW' | 'MEDIUM' | 'HIGH';
}

export interface FollowUpCheckIn {
  checkin_id: string;
  message: string;
  status: 'SCHEDULED' | 'SENT' | 'RESPONDED' | 'COMPLETED';
  response?: string;
  response_received_at?: string;
  classification?: 'NORMAL' | 'CONCERN' | 'URGENT';
}

export interface CarePlan {
  care_plan_id: string;
  mrn: string;
  risk_level: 'HIGH' | 'MODERATE' | 'LOW';
  intensity: 'INTENSIVE' | 'REGULAR' | 'BASIC';
  status: 'ACTIVE' | 'COMPLETED' | 'EXPIRED';
  doctor_instructions?: string;
  tasks: CareTask[];
  created_at: string;
  updated_at: string;
}

export interface CareGenerationResponse {
  status: 'success' | 'error';
  care_plan_id: string;
  risk_level: string;
  intensity: string;
  tasks: CareTask[];
  follow_up?: FollowUpCheckIn;
  message?: string;
}

export interface AppointmentInfo {
  session_id: string;
  destination: string;
  specialty?: string;
  providers_found?: number;
  workflow_stage: string;
  message: string;
}

export interface PatientResponseResult {
  status: 'NORMAL' | 'CONCERN' | 'URGENT' | 'ERROR';
  care_plan_id: string;
  revised?: boolean;
  new_tasks?: CareTask[];
  appointment?: AppointmentInfo;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Methods
// ─────────────────────────────────────────────────────────────────────────────

export const careService = {
  /**
   * Initial care plan generation (Phase 1)
   * Triggers the non-blocking agentic workflow
   */
  generateCarePlan: (mrn: string) =>
    client
      .post<CareGenerationResponse>(`/patients/${mrn}/post-care/generate`)
      .then((r) => r.data),

  /**
   * Submit patient response to follow-up check-in (Phase 2)
   * May trigger care plan revision or appointment booking
   */
  submitResponse: (patientId: string, response: string) =>
    client
      .post<PatientResponseResult>(`/patients/${patientId}/care-plan-response`, {
        response,
      })
      .then((r) => r.data),

  /**
   * Get current active care plan for a patient
   */
  getCarePlan: (mrn: string) =>
    client.get<CarePlan>(`/patients/${mrn}/care-plan`).then((r) => r.data),

  /**
   * Get care plan by ID
   */
  getCarePlanById: (carePlanId: string) =>
    client.get<CarePlan>(`/care-plans/${carePlanId}`).then((r) => r.data),

  /**
   * Get all check-ins for a care plan
   */
  getCheckIns: (carePlanId: string) =>
    client
      .get<{ checkins: FollowUpCheckIn[] }>(`/care-plans/${carePlanId}/checkins`)
      .then((r) => r.data),

  /**
   * Get tasks for a care plan
   */
  getTasks: (carePlanId: string) =>
    client
      .get<{ tasks: CareTask[] }>(`/care-plans/${carePlanId}/tasks`)
      .then((r) => r.data),
};

export default careService;
```

### Update Main API Export

Edit `/Users/vishwa/Desktop/CarePath_CTS/src/services/api.ts`:

```typescript
// Add to imports section:
export { careService } from './careService';
export type {
  CareTask,
  FollowUpCheckIn,
  CarePlan,
  CareGenerationResponse,
  PatientResponseResult,
  AppointmentInfo,
} from './careService';
```

### Create Patient Care Plan Page

Create `/Users/vishwa/Desktop/CarePath_CTS/src/pages/patient/MyCarePlan.tsx`:

```typescript
import { useState, useEffect } from 'react';
import { careService, type CarePlan, type FollowUpCheckIn } from '../../services/api';
import { toApiError } from '../../services/apiClient';

export default function MyCarePlan() {
  const [carePlan, setCarePlan] = useState<CarePlan | null>(null);
  const [checkins, setCheckins] = useState<FollowUpCheckIn[]>([]);
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitStatus, setSubmitStatus] = useState('');

  // Load care plan on mount
  useEffect(() => {
    loadCarePlan();
  }, []);

  async function loadCarePlan() {
    try {
      setLoading(true);
      // Get patient's MRN from context/auth
      const patientId = localStorage.getItem('patient_id') || 'DEMO001';
      const plan = await careService.getCarePlan(patientId);
      setCarePlan(plan);
      
      if (plan?.care_plan_id) {
        const { checkins: checkinsData } = await careService.getCheckIns(plan.care_plan_id);
        setCheckins(checkinsData);
      }
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitResponse() {
    if (!response.trim()) return;
    
    try {
      setLoading(true);
      setSubmitStatus('');
      const patientId = localStorage.getItem('patient_id') || 'DEMO001';
      const result = await careService.submitResponse(patientId, response);
      
      if (result.status === 'URGENT') {
        setSubmitStatus('⚠️ Urgent response detected. An appointment is being scheduled.');
      } else if (result.status === 'CONCERN') {
        setSubmitStatus('⚠️ Your care plan has been updated based on your response.');
      } else {
        setSubmitStatus('✅ Thank you for your update.');
      }
      
      setResponse('');
      await loadCarePlan(); // Refresh
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }

  if (loading && !carePlan) return <div className="p-4">Loading your care plan...</div>;
  if (error) return <div className="p-4 text-red-600">Error: {error}</div>;
  if (!carePlan) return <div className="p-4">No active care plan found.</div>;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <h1 className="text-3xl font-bold">My Care Plan</h1>
      
      {/* Care Plan Summary */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-xl font-semibold">Plan ID: {carePlan.care_plan_id}</h2>
            <p className="text-gray-600">Risk Level: <span className="font-medium">{carePlan.risk_level}</span></p>
            <p className="text-gray-600">Intensity: <span className="font-medium">{carePlan.intensity}</span></p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm ${
            carePlan.status === 'ACTIVE' ? 'bg-green-100 text-green-800' :
            carePlan.status === 'COMPLETED' ? 'bg-blue-100 text-blue-800' :
            'bg-gray-100 text-gray-800'
          }`}>
            {carePlan.status}
          </span>
        </div>
        
        {carePlan.doctor_instructions && (
          <div className="bg-blue-50 p-4 rounded">
            <p className="font-medium text-blue-900">Doctor's Instructions:</p>
            <p className="text-blue-800">{carePlan.doctor_instructions}</p>
          </div>
        )}
      </div>

      {/* Tasks */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Care Tasks</h3>
        <div className="space-y-3">
          {carePlan.tasks.map((task) => (
            <div key={task.task_id} className="flex items-start border-l-4 pl-4 py-2" style={{
              borderColor: task.status === 'COMPLETED' ? '#10b981' :
                          task.status === 'IN_PROGRESS' ? '#3b82f6' :
                          '#d1d5db'
            }}>
              <div className="flex-1">
                <p className="font-medium">{task.task_type.replace(/_/g, ' ')}</p>
                <p className="text-sm text-gray-600">{task.description}</p>
                {task.scheduled_date && (
                  <p className="text-xs text-gray-500 mt-1">Scheduled: {new Date(task.scheduled_date).toLocaleDateString()}</p>
                )}
              </div>
              <span className="text-sm text-gray-500">{task.status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Follow-Up Check-Ins */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Check-In History</h3>
        <div className="space-y-4">
          {checkins.map((checkin) => (
            <div key={checkin.checkin_id} className="border rounded p-4">
              <p className="font-medium text-gray-800">{checkin.message}</p>
              {checkin.response && (
                <div className="mt-2 bg-gray-50 p-3 rounded">
                  <p className="text-sm text-gray-600">Your Response:</p>
                  <p className="text-gray-800">{checkin.response}</p>
                  {checkin.classification && (
                    <span className={`inline-block mt-2 px-2 py-1 rounded text-xs ${
                      checkin.classification === 'URGENT' ? 'bg-red-100 text-red-800' :
                      checkin.classification === 'CONCERN' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-green-100 text-green-800'
                    }`}>
                      {checkin.classification}
                    </span>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-500 mt-2">Status: {checkin.status}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Submit Response */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Check-In Response</h3>
        <textarea
          className="w-full border rounded p-3 mb-3"
          rows={4}
          placeholder="How are you feeling today? Any concerns?"
          value={response}
          onChange={(e) => setResponse(e.target.value)}
        />
        <button
          onClick={handleSubmitResponse}
          disabled={loading || !response.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300"
        >
          {loading ? 'Submitting...' : 'Submit Response'}
        </button>
        {submitStatus && (
          <p className="mt-3 text-sm font-medium">{submitStatus}</p>
        )}
      </div>
    </div>
  );
}
```

### Add Route

Edit `/Users/vishwa/Desktop/CarePath_CTS/src/App.tsx` (or your router file):

```typescript
import MyCarePlan from './pages/patient/MyCarePlan';

// In your routes:
<Route path="/patient/care-plan" element={<MyCarePlan />} />
```

---

## Testing the Integration

### Step 1: Verify Database Tables

```bash
psql -U vishwa -d carepath_db -c "
SELECT 
  'care_plans' AS table_name, COUNT(*) AS rows FROM care_plans
UNION ALL
SELECT 'care_plan_tasks', COUNT(*) FROM care_plan_tasks
UNION ALL
SELECT 'follow_up_checkins', COUNT(*) FROM follow_up_checkins
UNION ALL
SELECT 'appointment_providers', COUNT(*) FROM appointment_providers
UNION ALL
SELECT 'provider_slots', COUNT(*) FROM provider_slots;
"
```

### Step 2: Test Initial Care Plan Generation

```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/post-care/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Expected response:
```json
{
  "status": "success",
  "care_plan_id": "CP-...",
  "risk_level": "HIGH",
  "intensity": "INTENSIVE",
  "tasks": [...]
}
```

### Step 3: Test NORMAL Patient Response

```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/care-plan-response \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"response": "I am feeling much better today, no issues"}'
```

Expected: `status: "NORMAL"`

### Step 4: Test CONCERN Response (Triggers Revision)

```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/care-plan-response \
  -H "Content-Type: application/json" \
  -d '{"response": "I have some mild chest discomfort after exercise"}'
```

Expected:
```json
{
  "status": "CONCERN",
  "revised": true,
  "new_tasks": [...],
  "message": "Your care plan has been updated..."
}
```

### Step 5: Test URGENT Response (Triggers Appointment)

```bash
curl -X POST http://localhost:8000/api/v1/patients/MRN000015/care-plan-response \
  -H "Content-Type: application/json" \
  -d '{"response": "I am having severe chest pain and shortness of breath"}'
```

Expected:
```json
{
  "status": "URGENT",
  "revised": true,
  "appointment": {
    "session_id": "pc_appointment_...",
    "destination": "SPECIALIST",
    "specialty": "CARDIOLOGY",
    "workflow_stage": "AVAILABILITY_CHECKED",
    "providers_found": 3
  }
}
```

### Step 6: Verify Appointment Session Created

```bash
psql -U vishwa -d carepath_db -c "
SELECT session_id, mrn, source, destination, specialty, workflow_stage 
FROM appointment_sessions 
WHERE mrn = 'MRN000015' 
ORDER BY created_at DESC 
LIMIT 1;
"
```

Expected:
```
session_id                             | mrn       | source    | destination | specialty  | workflow_stage
--------------------------------------|-----------|-----------|-------------|------------|-------------------
pc_appointment_MRN000015_urgent_...   | MRN000015 | POST_CARE | SPECIALIST  | CARDIOLOGY | AVAILABILITY_CHECKED
```

### Step 7: Frontend E2E Test

1. Start frontend: `cd /Users/vishwa/Desktop/CarePath_CTS && npm run dev`
2. Login as patient (MRN000015)
3. Navigate to `/patient/care-plan`
4. Submit response: "I am having severe chest pain"
5. Verify:
   - Status message shows "Urgent response detected"
   - Care plan refreshes with new tasks
   - Notification appears (if implemented)

---

## Production Deployment

### Database Migration Checklist

- [x] Main schema (001_create_main_schema.sql)
- [x] Care plan tables (create_care_plan_tables.sql)
- [x] Appointment tables (create_appointment_tables.sql)
- [ ] Remove test data (TEST-CARDIO-001, slot_test_cardio_*)
- [ ] Add production provider data
- [ ] Configure database backups
- [ ] Set up read replicas (if needed)

### Replace Test Data with Production

```sql
-- Remove test providers
DELETE FROM appointment_providers WHERE provider_id LIKE 'TEST-%';
DELETE FROM provider_slots WHERE provider_id LIKE 'TEST-%';

-- Add real providers (example)
INSERT INTO appointment_providers 
(provider_id, provider_name, destination, specialty, address, latitude, longitude, phone, active)
VALUES
('APOLLO-CARDIO-001', 'Apollo Hospital Cardiology', 'SPECIALIST', 'CARDIOLOGY', 
 'Apollo Hospitals, Greams Road, Chennai 600006', 13.0569, 80.2433, '+91-44-2829-3333', true);

-- Production slots should come from external scheduling API
```

### Environment Variables (Production)

```env
# Backend .env
DATABASE_URL=postgresql+asyncpg://prod_user:secure_password@db.production.com:5432/carepath_db
DB_HOST=db.production.com
DB_PORT=5432
DB_NAME=carepath_db
DB_USER=prod_user
DB_PASSWORD=secure_password

NVIDIA_API_KEY=prod-nvidia-key
GROQ_API_KEY=prod-groq-key

# Appointment booking service (teammate's production endpoint)
APPOINTMENT_AGENT_BASE_URL=https://appointments.carepath.com

# Frontend .env
VITE_API_BASE_URL=https://api.carepath.com/api/v1
```

### External Service Requirements

| Service | Owner | Status | URL |
|---------|-------|--------|-----|
| Shared Appointment Agent | Teammate | Required | Port 8001 / Production domain |
| Provider Directory API | Hospital IT | Optional | OSM fallback available |
| Slot Availability API | External Scheduling | Required for booking | TBD |
| Notification Service | Team | Optional | Backend can log to DB |

### Monitoring & Observability

Add to your monitoring:

1. **Database Metrics:**
   - Care plan creation rate
   - Response classification distribution (NORMAL/CONCERN/URGENT)
   - Appointment handoff success rate

2. **API Metrics:**
   - `/post-care/generate` latency
   - `/care-plan-response` error rate
   - Appointment booking success rate

3. **Agent Metrics:**
   - LLM token usage (NVIDIA, Groq)
   - Graph execution time
   - Tool invocation counts

### Security Considerations

1. **Authentication:**
   - All endpoints require JWT token
   - Patient can only access their own care plan
   - Care managers have broader access

2. **Data Privacy:**
   - PHI in `patient_ehr`, `care_plans`, `follow_up_checkins`
   - Encrypt at rest
   - Audit log all access

3. **Rate Limiting:**
   - Patient response: 10/hour per patient
   - Care plan generation: 5/hour per patient
   - Appointment search: 20/hour per session

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PATIENT FRONTEND (React)                       │
│  /patient/care-plan → POST /care-plan-response → UI updates            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTPS
┌────────────────────────────────┴────────────────────────────────────────┐
│                       FASTAPI BACKEND (Port 8000)                       │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ /api/v1/patients/{id}/care-plan-response                          │ │
│  │   ├─→ Load context from PostgreSQL                                │ │
│  │   ├─→ Call post_care.agents.response_analyzer                     │ │
│  │   ├─→ Call post_care.agents.care_continuity                       │ │
│  │   └─→ If URGENT: appointment_handoff.py                           │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ post_care/orchestrator/agentic_graph_builder.py                   │ │
│  │   ├─→ NVIDIA LLM orchestrator (tool calling)                      │ │
│  │   ├─→ Care Plan Agent → care_plans table                          │ │
│  │   ├─→ Follow-Up Agent → care_plan_tasks + follow_up_checkins     │ │
│  │   └─→ Complete (non-blocking)                                     │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ app/services/alternate_care/agents/appointment_agent.py           │ │
│  │   ├─→ Source-aware (PATIENT vs POST_CARE)                         │ │
│  │   ├─→ Search providers → appointment_providers                    │ │
│  │   ├─→ Check availability → provider_slots                         │ │
│  │   └─→ Book → POST localhost:8001/appointments/book                │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ PostgreSQL
┌────────────────────────────────┴────────────────────────────────────────┐
│                    POSTGRESQL (carepath_db)                             │
│                                                                          │
│  patient_ehr → care_plans → care_plan_tasks → follow_up_checkins       │
│                    ↓                                                     │
│              appointment_sessions → appointments                        │
│                    ↓                                                     │
│         appointment_providers ← provider_slots                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## FAQ

### Q: Do I need to run the post-care module separately?
**A:** No. The `post_care/` module is imported by the main FastAPI backend. It runs as part of `app.main:app`.

### Q: How do I test without real appointment booking?
**A:** The flow already stops at `AVAILABILITY_CHECKED` if the external service at port 8001 is not running. You can verify providers and slots are found.

### Q: Can I use the same appointment agent for patient-initiated bookings?
**A:** Yes! The appointment agent is source-aware. Set `source="PATIENT"` for conversational booking, `source="POST_CARE"` for automated booking.

### Q: How do I prevent duplicate care plans?
**A:** The Care Plan Agent checks for existing ACTIVE plans by MRN. If found, it reuses that plan. Only one ACTIVE plan per patient.

### Q: What if the patient responds multiple times?
**A:** Each response creates a new `follow_up_checkin` record. The care plan can be revised multiple times (additive, not replacement).

### Q: How do I integrate real provider data?
**A:** Populate `appointment_providers` table with real providers (with `latitude`, `longitude`). The appointment agent queries this table.

### Q: How do I integrate real slot availability?
**A:** Option 1: Sync external calendar → `provider_slots` table. Option 2: Modify appointment agent to call external API instead of querying `provider_slots`.

### Q: How do I enable actual appointment booking?
**A:** Start the teammate's Shared Appointment Agent microservice on port 8001. The `book_appointment` tool will succeed.

### Q: What notifications are triggered?
**A:** Currently, the backend creates notification records in `notifications` table. Frontend should poll `/api/v1/notifications/` or implement WebSocket/push notifications.

### Q: How do I handle scheduling follow-ups?
**A:** The `follow_up_checkins` table has `scheduled_at` field. Implement a background worker (Celery, cron) to send notifications at scheduled times.

---

## Next Steps

1. **Run all migrations** (see Quick Start)
2. **Test the flow end-to-end** (see Testing section)
3. **Add production provider data** (replace test data)
4. **Connect teammate's appointment service** (port 8001)
5. **Implement notification delivery** (SMS, email, push)
6. **Add frontend pages** (MyCarePlan component above)
7. **Set up monitoring** (logs, metrics, alerts)
8. **Deploy to staging** (test with real data)
9. **Deploy to production** (with database backups!)

---

**Status:** ✅ All backend infrastructure ready  
**Blockers:** Appointment booking microservice (port 8001)  
**Contact:** Backend team for database access, Frontend team for UI integration

