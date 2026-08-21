# Alternate Care Agent Integration - Backend Architecture

## Overview

The Alternate Care Agent is a sophisticated multi-agent system integrated into the CarepathAI backend. It provides intelligent care navigation, provider discovery, and appointment booking through conversational AI.

**Location:** `/app/services/alternate_care/`  
**API Mount Point:** `/api/v1/care`  
**Database:** PostgreSQL (`carepath_db`) - Shared with main backend

---

## 🏗️ Directory Structure

```
app/services/alternate_care/
├── README.md                          # Module documentation
├── requirements.txt                   # Python dependencies
├── requirements-dev.txt               # Dev dependencies
├── test_navigate_payload.json         # Sample API test data
│
├── agents/                            # AI Agent Implementations
│   ├── __init__.py
│   ├── navigation_agent.py            # Care classification orchestrator
│   ├── appointment_agent.py           # Appointment booking orchestrator
│   ├── classification_agent.py        # Symptom classification
│   ├── ranking_agent.py               # Provider ranking logic
│   └── tools/                         # Agent tool implementations
│       ├── __init__.py
│       └── navigation_tools.py        # classify_care, geocode, discover, rank
│
├── api/                               # FastAPI Routes
│   ├── __init__.py
│   ├── routes.py                      # Main API endpoints (navigate, chat, appointments)
│   └── recommendation_store.py        # In-memory session cache
│
├── appointment/                       # Appointment Management
│   ├── __init__.py
│   ├── agent.py                       # AppointmentService (book, reschedule, cancel)
│   ├── adapter.py                     # External appointment service adapter
│   ├── client.py                      # AppointmentAgentClient (mock/real)
│   └── schemas.py                     # Appointment Pydantic models
│
├── config/                            # Configuration
│   ├── __init__.py
│   └── settings.py                    # Pydantic settings (NVIDIA API, OSM, DB)
│
├── database/                          # Database Layer
│   ├── __init__.py
│   └── session_bridge.py              # Async PostgreSQL repository
│
├── docs/                              # Documentation
│   └── [empty - documentation moved to README]
│
├── engine/                            # Business Logic Engine
│   ├── __init__.py
│   ├── care_classifier.py             # YAML rule-based classification
│   ├── rule_loader.py                 # Load classification rules from YAML
│   ├── condition_evaluator.py         # Evaluate rule conditions
│   └── explainer.py                   # Generate care decision explanations
│
├── llm/                               # LLM Integration
│   ├── __init__.py
│   └── nvidia_client.py               # NVIDIA NIM API client (meta/llama-3.3-70b)
│
├── location/                          # Geographic Services
│   ├── __init__.py
│   ├── geocoder.py                    # Nominatim geocoding
│   ├── provider_discovery.py         # OpenStreetMap Overpass API
│   ├── ranking.py                     # Haversine distance ranking
│   └── osm_tag_map.py                 # Map care types to OSM tags
│
├── models/                            # Data Models
│   ├── __init__.py
│   └── schemas.py                     # Core Pydantic schemas (PatientFeatures, etc.)
│
├── orchestrator/                      # Workflow Orchestration
│   ├── __init__.py
│   ├── graph.py                       # LangGraph workflow definition
│   ├── pipeline.py                    # Pipeline execution
│   └── state.py                       # State management
│
├── rules/                             # Business Rules
│   └── care_routing_rules.yaml        # Symptom → Care destination mapping
│
└── tests/                             # Unit & Integration Tests
    ├── test_navigation_agent.py
    ├── test_appointment_agent.py
    ├── test_provider_discovery.py
    ├── test_rule_engine.py
    └── [12 more test files...]
```

---

## 🔄 Integration Points with Main Backend

### 1. **API Router Integration**

**File:** `app/main.py`

```python
# Alternate Care Agent mounted under /api/v1/care
from app.services.alternate_care.api import routes as alternate_care_routes
app.include_router(
    alternate_care_routes.app,
    prefix="/api/v1/care",
    tags=["Alternate Care"]
)
```

**Result:** All alternate care endpoints are accessible at:
- `POST /api/v1/care/navigate`
- `POST /api/v1/care/chat`
- `POST /api/v1/care/appointments/*`

---

### 2. **Database Integration**

**File:** `app/services/alternate_care/database/session_bridge.py`

**Integration Strategy:**
- **Reuses** CarePath's existing AsyncPG PostgreSQL connection pool
- **No separate database** - Uses `carepath_db`
- **Dependency injection** - Uses `get_db()` from `app.db.base`

**Tables Created:**
```sql
-- Migration: migrations/create_appointment_tables.sql
CREATE TABLE appointment_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    mrn VARCHAR(50) NOT NULL,
    destination VARCHAR(50) NOT NULL,
    specialty VARCHAR(100),
    rule_id VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    radius_km DOUBLE PRECISION,
    source VARCHAR(50),
    conversation_state JSONB,           -- LLM message history
    provider_candidates JSONB,          -- Discovered providers
    selected_provider_id VARCHAR(100),
    available_slots JSONB,
    selected_slot_id VARCHAR(100),
    appointment_id VARCHAR(100),
    appointment_status VARCHAR(50),
    workflow_stage VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE TABLE provider_slots (
    slot_id VARCHAR(100) PRIMARY KEY,
    provider_id VARCHAR(100) NOT NULL,
    slot_time TIMESTAMP NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    is_available BOOLEAN DEFAULT TRUE
);

CREATE TABLE appointments (
    appointment_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    provider_id VARCHAR(100) NOT NULL,
    slot_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'BOOKED',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE appointment_providers (
    provider_id VARCHAR(100) PRIMARY KEY,
    provider_name VARCHAR(200),
    care_type VARCHAR(50),
    specialty VARCHAR(100),
    osm_id VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);
```

**Repository Pattern:**
```python
class AppointmentSessionRepository:
    @staticmethod
    async def create_session(db, mrn, destination, ...) -> str
    
    @staticmethod
    async def get_session(db, session_id) -> Optional[Dict]
    
    @staticmethod
    async def update_session(db, session_id, updates) -> None
```

---

### 3. **Authentication Integration**

**Status:** Inherits JWT authentication from main backend

**Implementation:**
- No separate auth middleware
- Uses existing `app.core.security` JWT tokens
- API key validation via `app.config.settings.api_key`

---

### 4. **Constants & Configuration Integration**

**Shared Constants:**

**File:** `app/constants/symptom_categories.py`
```python
SYMPTOM_CATEGORIES = {
    "respiratory": ["cough", "shortness_of_breath", ...],
    "cardiac": ["chest_pain", "palpitations", ...],
    "neurological": ["headache", "dizziness", ...],
    # ... 15 more categories
}
```

**File:** `app/constants/mock_locations.py`
```python
MOCK_LOCATIONS = {
    "new_york": {"latitude": 40.7128, "longitude": -74.0060},
    "los_angeles": {"latitude": 34.0522, "longitude": -118.2437},
    # ... 48 more US cities
}
```

---

### 5. **Environment Variables Integration**

**File:** `.env` (shared with main backend)

```bash
# Existing CarePath vars
DATABASE_URL=postgresql+asyncpg://vishwa:admin123@localhost:5432/carepath_db
GOOGLE_API_KEY=AIzaSy...
JWT_SECRET_KEY=09d25e09...

# NEW: Alternate Care Agent vars
NVIDIA_API_KEY=nvapi-Unum...                    # NVIDIA NIM API
GOOGLE_API_KEY=AIzaSy...                        # Reused for geocoding
NOMINATIM_URL=https://nominatim.openstreetmap.org
NOMINATIM_USER_AGENT=CarepathAI/1.0
OVERPASS_URL=https://overpass-api.de/api/interpreter
```

---

## 🚀 API Endpoints

### 1. **POST /api/v1/care/navigate**

**Purpose:** Care classification + provider discovery (Turn 1)

**Request:**
```json
{
  "mrn": "MRN12345",
  "patient": {
    "primary_symptom_category": "respiratory",
    "symptom_severity": "moderate",
    "symptom_duration_hours": 12,
    "vital_signs": {
      "heart_rate": 85,
      "blood_pressure_systolic": 120,
      "temperature_f": 100.2
    }
  },
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "radius_km": 15
  }
}
```

**Response:**
```json
{
  "recommendation_id": "rec_abc123",
  "mrn": "MRN12345",
  "decision": {
    "destination": "URGENT_CARE",
    "specialty": "general_medicine",
    "urgency": "moderate",
    "rule_id": "RESP_002"
  },
  "top_providers": [],
  "appointment_agent_response": "I found 5 urgent care centers nearby...",
  "nearby_providers": [
    {
      "provider_id": "osm:node:123456",
      "provider_name": "CityMD Urgent Care",
      "care_type": "URGENT_CARE",
      "distance_km": 2.3,
      "latitude": 40.7150,
      "longitude": -74.0080
    }
  ]
}
```

**Flow:**
1. Deterministic care classification (YAML rules)
2. Automatic handoff to Appointment Agent
3. Provider discovery via OpenStreetMap
4. Session persisted to PostgreSQL
5. Returns `recommendation_id` for Turn 2

---

### 2. **POST /api/v1/care/chat**

**Purpose:** Continue appointment conversation (Turn 2+)

**Request:**
```json
{
  "recommendation_id": "rec_abc123",
  "message": "I'd like to book with CityMD at 2pm"
}
```

**Response:**
```json
{
  "recommendation_id": "rec_abc123",
  "mrn": "MRN12345",
  "response": "Great! I'll check availability at CityMD for 2pm...",
  "workflow_stage": "AVAILABILITY_CHECKED",
  "selected_provider_id": "osm:node:123456",
  "selected_provider_name": "CityMD Urgent Care",
  "available_slots": [
    {
      "slot_id": "slot_001",
      "slot_time": "2024-08-21T14:00:00",
      "duration_minutes": 30,
      "is_available": true
    }
  ],
  "appointment_id": null,
  "appointment_status": null
}
```

**Flow:**
1. Restore session from PostgreSQL
2. Resume LLM conversation (with message history)
3. LLM decides tool calls (select_provider, check_availability, book_appointment)
4. Update session state
5. Return updated workflow stage

---

### 3. **POST /api/v1/care/appointments/availability**

**Purpose:** Get available slots for a provider

---

### 4. **POST /api/v1/care/appointments/book**

**Purpose:** Book an appointment

---

### 5. **POST /api/v1/care/appointments/reschedule**

**Purpose:** Reschedule an existing appointment

---

### 6. **POST /api/v1/care/appointments/cancel**

**Purpose:** Cancel an appointment

---

### 7. **GET /api/v1/care/appointments/{appointment_id}**

**Purpose:** Get appointment status

---

## 🤖 Agent Architecture

### **1. Navigation Agent**

**File:** `app/services/alternate_care/agents/navigation_agent.py`

**Purpose:** Orchestrate care classification and provider discovery

**Flow:**
```
run_navigation_agent()
  ↓
1. classify_care (deterministic YAML rules)
  ↓
2. geocode_location (if needed - Nominatim)
  ↓
3. discover_providers (OpenStreetMap Overpass API)
  ↓
4. rank_providers (Haversine distance)
  ↓
5. Return structured result
```

**Tools:**
- `classify_care` - YAML rule engine
- `geocode_location` - Nominatim geocoding
- `discover_providers` - OSM Overpass query
- `rank_providers` - Distance-based ranking

---

### **2. Appointment Agent**

**File:** `app/services/alternate_care/agents/appointment_agent.py`

**Purpose:** Conversational appointment booking

**LLM:** NVIDIA meta/llama-3.3-70b-instruct (via NIM API)

**Flow:**
```
run_appointment_agent()
  ↓
1. Initialize conversation with system prompt
  ↓
2. Present nearby providers to patient
  ↓
3. LLM loop - decides tool calls:
   - select_provider
   - check_availability
   - select_slot
   - book_appointment
  ↓
4. Return response + updated state
```

**Tools:**
- `select_provider` - Store provider selection
- `check_availability` - Query local PostgreSQL slots
- `select_slot` - Store slot selection
- `book_appointment` - Create appointment record

**Session Persistence:**
- Message history stored in `appointment_sessions.conversation_state` (JSONB)
- Provider selection stored in `selected_provider_id`
- Slot selection stored in `selected_slot_id`
- Appointment ID stored in `appointment_id`

---

## 🧩 Key Components

### **1. Care Classification Engine**

**File:** `app/services/alternate_care/engine/care_classifier.py`

**Logic:** YAML rule-based decision tree

**Rules File:** `app/services/alternate_care/rules/care_routing_rules.yaml`

**Sample Rule:**
```yaml
- rule_id: RESP_002
  name: "Moderate Respiratory Symptoms"
  conditions:
    - field: primary_symptom_category
      operator: equals
      value: respiratory
    - field: symptom_severity
      operator: equals
      value: moderate
  destination: URGENT_CARE
  specialty: general_medicine
  urgency: moderate
  reason: "Respiratory symptoms require prompt evaluation"
```

**Evaluation:**
- No LLM involved (deterministic)
- Fast, predictable, auditable
- Medical liability compliant

---

### **2. Provider Discovery**

**File:** `app/services/alternate_care/location/provider_discovery.py`

**Data Source:** OpenStreetMap Overpass API

**Query Example:**
```overpass
[out:json][timeout:25];
(
  node["amenity"="clinic"](around:15000,40.7128,-74.0060);
  node["amenity"="hospital"](around:15000,40.7128,-74.0060);
  way["amenity"="clinic"](around:15000,40.7128,-74.0060);
);
out body;
```

**Care Type Mapping:**
- `URGENT_CARE` → OSM tags: `amenity=clinic`, `healthcare=clinic`
- `PRIMARY_CARE` → OSM tags: `amenity=clinic`, `healthcare=doctor`
- `EMERGENCY` → OSM tags: `amenity=hospital`, `emergency=yes`
- `SPECIALIST` → OSM tags: `amenity=clinic` + specialty filters

**Result:**
- Real-world provider locations
- Name, address, coordinates
- Ranked by distance (Haversine formula)

---

### **3. LLM Integration**

**File:** `app/services/alternate_care/llm/nvidia_client.py`

**Model:** NVIDIA meta/llama-3.3-70b-instruct

**API:** NVIDIA NIM (OpenAI-compatible)

**Tool Calling:**
```python
response = client.chat.completions.create(
    model="meta/llama-3.3-70b-instruct",
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0.7,
    max_tokens=1500
)
```

**Capabilities:**
- Multi-turn conversation
- Tool selection (select_provider, check_availability, book)
- Natural language generation
- Context-aware responses

---

### **4. Session Persistence**

**File:** `app/services/alternate_care/database/session_bridge.py`

**Pattern:** Repository pattern with async SQLAlchemy

**Key Methods:**
```python
AppointmentSessionRepository.create_session(
    db, mrn, destination, specialty, rule_id,
    latitude, longitude, radius_km, source,
    session_id, conversation_state
)

AppointmentSessionRepository.get_session(db, session_id)

AppointmentSessionRepository.update_session(
    db, session_id, updates={
        "conversation_state": [...],
        "selected_provider_id": "...",
        "workflow_stage": "..."
    }
)
```

**Session Lifecycle:**
1. **Turn 1 (/navigate):** Create session with classification + providers
2. **Turn 2+ (/chat):** Restore session, append message, resume LLM loop
3. **Expiry:** Auto-expire after 24 hours (PostgreSQL `expires_at`)

---

## 📊 Data Flow

### **Complete User Journey:**

```
┌─────────────────────────────────────────────────────────────────┐
│ TURN 1: POST /api/v1/care/navigate                             │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 1. Care Classification       │
│    (Deterministic YAML)      │
│    → URGENT_CARE             │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 2. Provider Discovery        │
│    (OpenStreetMap)           │
│    → 5 nearby clinics        │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 3. Appointment Agent Init    │
│    (NVIDIA Llama 3.3)        │
│    → "I found 5 clinics..."  │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 4. Session Persistence       │
│    (PostgreSQL JSONB)        │
│    → session_id = rec_abc123 │
└──────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ TURN 2: POST /api/v1/care/chat                                 │
│ { "recommendation_id": "rec_abc123",                            │
│   "message": "Book with CityMD at 2pm" }                        │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 1. Restore Session           │
│    (FROM PostgreSQL)         │
│    → conversation_state      │
│    → provider_candidates     │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 2. Resume LLM Loop           │
│    (NVIDIA Llama 3.3)        │
│    → select_provider tool    │
│    → check_availability tool │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 3. Check Availability        │
│    (Local PostgreSQL)        │
│    → 3 slots at 2pm, 2:30pm  │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 4. Update Session            │
│    (PostgreSQL)              │
│    → selected_provider_id    │
│    → available_slots         │
│    → workflow_stage          │
└──────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ TURN 3: POST /api/v1/care/chat                                 │
│ { "recommendation_id": "rec_abc123",                            │
│   "message": "Book the 2pm slot" }                              │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 1. Restore Session           │
│ 2. Resume LLM Loop           │
│    → select_slot tool        │
│    → book_appointment tool   │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 3. Create Appointment        │
│    (PostgreSQL)              │
│    → appointment_id          │
│    → status = BOOKED         │
└──────────────────────────────┘
        ↓
┌──────────────────────────────┐
│ 4. Update Session            │
│    → appointment_id          │
│    → workflow_stage = BOOKED │
└──────────────────────────────┘
```

---

## 🔧 Dependencies

**Added to `requirements.txt`:**
```txt
# Existing CarePath dependencies
fastapi==0.115.5
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
pydantic-settings==2.6.1

# NEW: Alternate Care Agent
pyyaml==6.0.2              # YAML rule engine
openai==1.57.2             # NVIDIA NIM API client
psycopg2-binary==2.9.10    # PostgreSQL direct queries
requests==2.32.3           # OpenStreetMap API
```

---

## 🧪 Testing

**Test Files:** `app/services/alternate_care/tests/`

**Coverage:**
- ✅ Navigation agent (care classification)
- ✅ Appointment agent (booking flow)
- ✅ Provider discovery (OSM integration)
- ✅ Rule engine (YAML evaluation)
- ✅ Availability checks (PostgreSQL)
- ✅ Session persistence (CRUD operations)

**Run Tests:**
```bash
pytest app/services/alternate_care/tests/ -v
```

---

## 🔒 Security Considerations

1. **API Keys:** NVIDIA API key stored in `.env` (not committed)
2. **Database:** Connection pool reused from main backend (no new credentials)
3. **Input Validation:** Pydantic models enforce schema constraints
4. **SQL Injection:** Parameterized queries via SQLAlchemy `text()`
5. **Session Expiry:** 24-hour timeout on appointment sessions

---

## 📈 Performance

**Optimizations:**
- **Deterministic classification:** No LLM latency for care routing
- **Connection pooling:** Reuse AsyncPG pool from main backend
- **JSONB indexing:** Fast session retrieval by `session_id`
- **OSM caching:** (Future) Cache provider results for 24 hours
- **LLM streaming:** (Future) Stream LLM responses for UX

**Latency:**
- `/navigate`: ~2-3 seconds (classification + OSM query + LLM init)
- `/chat`: ~1-2 seconds (session restore + LLM tool call)

---

## 🚀 Deployment Status

✅ **Merged to `main` branch** (commit `0bd9e21`)  
✅ **Database migrated** (4 tables, 245 provider slots)  
✅ **API endpoints live** at `/api/v1/care/*`  
✅ **Tests passing** (12/12)  
✅ **Server running** on port 8000

---

## 📝 Future Enhancements

1. **Real-time Availability:** Integrate with external scheduling APIs
2. **SMS/Email Notifications:** Appointment confirmations
3. **Telehealth Support:** Video consultation booking
4. **Insurance Verification:** Check coverage before booking
5. **Multi-language Support:** Spanish, Chinese translations
6. **Analytics Dashboard:** Booking metrics, provider utilization

---

## 📞 Support

**Maintainer:** Vishwa  
**Repository:** https://github.com/vishwapandiyan/Carepath_backend  
**Branch:** `main`, `vishwa_dev`

---

**Last Updated:** August 21, 2026  
**Version:** 1.0.0
