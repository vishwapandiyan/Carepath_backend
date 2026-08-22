# Complete Agent Flow & Run Guide

> **Source authority:** Every statement in this document is derived from the actual source
> code. Examples marked **ACTUAL TESTED OUTPUT** were produced by executing the code.
> If something cannot be confirmed, it is marked **NOT CONFIRMED**, **NOT IMPLEMENTED**,
> or **IMPLEMENTED BUT NOT CURRENTLY INTEGRATED**.

---

## If You Know Nothing About This Agent

```
WHAT ENTERS?
  A patient's clinical information (symptoms, pain level, medical history)
  + their location (GPS coordinates or US address/ZIP)
  ↓

WHO RECEIVES IT?
  A FastAPI server running at localhost:8000
  The main entry point is POST /navigate
  ↓

WHAT DOES THE AGENT DECIDE?
  Which type of healthcare the patient needs:
  → PCP (primary care physician)
  → URGENT_CARE (same-day clinic)
  → SPECIALIST (with a specific specialty, e.g. ORTHOPEDICS)
  → TELEHEALTH (virtual visit)
  → DENTISTRY (dentist)
  ↓

WHAT INFORMATION DOES IT NEED?
  A YAML rule file (rules/care_destination_rules.yaml) is the brain.
  No AI/LLM is involved in the routing decision.
  It's pure if/then logic evaluated in priority order.
  ↓

WHAT TOOLS DOES IT CALL?
  If the destination is physical (not TELEHEALTH):
    → Nominatim (free OpenStreetMap geocoding) to convert address to GPS
    → Overpass API (free OpenStreetMap) to find nearby clinics/doctors
    → Haversine formula (math) to calculate distance
  ↓

WHAT EXTERNAL APIs DOES IT CALL?
  1. Nominatim (free, no key): converts address → coordinates
  2. Overpass API (free, no key): finds healthcare facilities near coordinates
  3. Google Gemini (requires GOOGLE_API_KEY): explains the decision in plain English
  4. External Appointment Agent (teammate's service): handles booking
  ↓

WHAT DOES GEMINI DO?
  ONLY generates a plain-language sentence explaining the routing decision.
  Example: "Based on your worsening symptoms, a same-day urgent care visit is appropriate."
  Gemini does NOT choose the destination. Gemini does NOT find providers. Gemini does NOT
  calculate distances. These are all done deterministically by code before Gemini is called.
  ↓

WHAT COMES BACK?
  A JSON response with:
  - A recommendation_id (use this for booking)
  - The routing decision (destination + specialty + rule that matched)
  - Up to 5 nearby providers ranked by distance
```

---

## Table of Contents

1. [What the Agent Is](#1-what-the-agent-is)
2. [Project Architecture](#2-project-architecture)
3. [Agent Hierarchy](#3-agent-hierarchy)
4. [Entry Points](#4-entry-points)
5. [Environment Setup — How to Run](#5-environment-setup)
6. [Environment Variables](#6-environment-variables)
7. [LangGraph — State, Nodes, Edges](#7-langgraph)
8. [Rule Engine](#8-rule-engine)
9. [Care Decision and Routing Rules](#9-routing-rules)
10. [Location Processing](#10-location-processing)
11. [Geocoding (Nominatim)](#11-geocoding)
12. [Provider Discovery (Overpass/OSM)](#12-provider-discovery)
13. [Filtering and Deduplication](#13-filtering-and-deduplication)
14. [Distance Calculation](#14-distance-calculation)
15. [Provider Ranking](#15-provider-ranking)
16. [Gemini Explanation](#16-gemini-explanation)
17. [Recommendation Storage](#17-recommendation-storage)
18. [Appointment Availability](#18-appointment-availability)
19. [Booking](#19-booking)
20. [Reschedule and Cancel](#20-reschedule-and-cancel)
21. [Error Handling](#21-error-handling)
22. [Complete Runtime Flow — Step by Step](#22-complete-runtime-flow)
23. [One Full Request Walkthrough](#23-one-full-request-walkthrough)
24. [Running Without a UI](#24-running-without-a-ui)
25. [How to Test](#25-how-to-test)
26. [How Another Agent Consumes This](#26-teammate-integration)
27. [Current Integration Status](#27-integration-status)
28. [Known Limitations](#28-known-limitations)
29. [Troubleshooting](#29-troubleshooting)

---

## 1. What the Agent Is

The **Alternate Care Navigation Agent** is a FastAPI-backed LangGraph pipeline that routes non-emergency patients to the correct care destination and finds nearby providers.

**Scope:** Patients that an upstream ED-avoidance model has already classified as non-emergency. This agent does NOT perform red-flag/ED triage.

**It is not a single "agent" in the traditional LLM sense.** It is:
- A deterministic rule engine (no LLM) for routing decisions
- A deterministic OSM-based location search for finding providers
- A deterministic Haversine calculation for distance
- A single Gemini LLM call for generating a patient-facing explanation

---

## 2. Project Architecture

```
alternate_care_agent/
│
├── main.py                      ← uvicorn entry point (imports app from api/routes.py)
│
├── api/
│   ├── routes.py                ← FastAPI app, all HTTP endpoints
│   └── recommendation_store.py  ← In-memory TTL store (recommendation_id binding)
│
├── orchestrator/
│   ├── graph.py                 ← LangGraph StateGraph wiring
│   └── state.py                 ← NavigationState TypedDict
│
├── agents/
│   ├── classification_agent.py  ← AlternateCareAgent (wraps CareClassifier)
│   ├── ranking_agent.py         ← RankingAgent (wraps geocoder + discovery + ranking)
│   └── appointment_agent.py     ← Re-export of AppointmentAgentClient (no logic)
│
├── engine/
│   ├── rule_loader.py           ← Loads + sorts care_destination_rules.yaml
│   ├── condition_evaluator.py   ← Evaluates rule conditions against patient data
│   ├── care_classifier.py       ← First-match-wins rule evaluation
│   └── explainer.py             ← ONLY LLM call — Gemini explanation
│
├── location/
│   ├── geocoder.py              ← Nominatim geocoding (address → lat/lon)
│   ├── provider_discovery.py    ← Overpass API (finds healthcare facilities)
│   ├── ranking.py               ← Haversine distance + scoring
│   └── osm_tag_map.py           ← Maps destination/specialty to OSM tags
│
├── models/
│   └── schemas.py               ← All shared Pydantic models
│
├── appointment/
│   ├── schemas.py               ← Appointment workflow Pydantic models
│   ├── adapter.py               ← Translation: internal ↔ external JSON
│   ├── client.py                ← HTTP client for external Appointment Agent
│   └── agent.py                 ← AppointmentService (service layer)
│
├── rules/
│   └── care_destination_rules.yaml  ← THE routing rule file
│
└── config/
    └── settings.py              ← All env-var configuration
```

---

## 3. Agent Hierarchy

```
Alternate Care Navigation Agent
│
├── LangGraph Pipeline  (orchestrator/graph.py)
│   │
│   ├── validate_input_node
│   │   └── Checks: primary_symptom_category present
│   │
│   ├── classify_node  [Agent 1: AlternateCareAgent]
│   │   └── engine/care_classifier.py
│   │       └── engine/rule_loader.py  ← reads care_destination_rules.yaml
│   │       └── engine/condition_evaluator.py  ← evaluates conditions
│   │
│   ├── rank_node  [Agent 2: RankingAgent]  ← SKIPPED for TELEHEALTH
│   │   └── location/geocoder.py  ← Nominatim (if address-only)
│   │       └── External: Nominatim API (nominatim.openstreetmap.org)
│   │   └── location/provider_discovery.py  ← Overpass
│   │       └── External: Overpass API (overpass-api.de)
│   │   └── location/ranking.py  ← Haversine math (no external API)
│   │
│   └── explain_node  [Gemini LLM]
│       └── engine/explainer.py
│           └── External: Google Gemini (gemini-1.5-flash)
│
├── RecommendationStore  (api/recommendation_store.py)
│   └── In-memory, TTL=30min, thread-safe
│
└── Appointment Layer  (appointment/)
    ├── AppointmentService  (appointment/agent.py)
    ├── AppointmentAgentClient  (appointment/client.py)
    ├── SharedAppointmentAdapter  (appointment/adapter.py)
    └── External: Shared Appointment Agent (teammate's service)
```

---

## 4. Entry Points

### Primary entry point — HTTP API

```
File:     api/routes.py
Function: navigate(patient: PatientFeatures, location: PatientLocation)
Endpoint: POST /navigate
How:      uvicorn main:app --reload
Invokes:  navigation_graph.invoke({"patient": patient, "location": location, "errors": []})
```

### LangGraph invocation (inside the route)

```python
# orchestrator/graph.py — module-level compilation
navigation_graph = build_graph()

# Called from api/routes.py
result = navigation_graph.invoke(
    {"patient": patient, "location": location, "errors": []}
)
```

### Test entry point

```
python -m pytest tests/ -v
```

Tests use `fastapi.testclient.TestClient` to call the real routes with mocked external services.

### Direct function invocation (no HTTP, for debugging)

```python
# Works without starting the server
from orchestrator.graph import navigation_graph
from models.schemas import PatientFeatures, PatientLocation
from unittest.mock import patch

with patch('location.provider_discovery.find_nearby_providers', return_value=[]):
    result = navigation_graph.invoke({
        "patient": PatientFeatures(primary_symptom_category="minor_infection"),
        "location": PatientLocation(latitude=30.2672, longitude=-97.7431),
        "errors": []
    })
```

**NO STANDALONE CLI ENTRY POINT EXISTS.** The agent is invoked via HTTP or direct Python.

---

## 5. Environment Setup

### Prerequisites

- Python 3.11+ (project runs on 3.14.2 as confirmed by test output)
- `pip`

### Step 1 — Navigate to the project directory

```
cd c:\Users\Hp\Downloads\alternate_care_agent\alternate_care_agent
```

### Step 2 — Create a virtual environment

```bash
# Windows
python -m venv .venv

# macOS/Linux
python3 -m venv .venv
```

### Step 3 — Activate the environment

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat

# macOS/Linux
source .venv/bin/activate
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt      # production
pip install -r requirements-dev.txt  # adds pytest
```

**Exact versions (from `requirements.txt`):**
```
fastapi==0.135.1
uvicorn[standard]==0.40.0
pydantic==2.12.5
PyYAML==6.0.3
requests==2.32.5
langchain==1.3.15
langchain-core==1.6.0
langchain-google-genai==4.3.4
langgraph==1.2.11
```

### Step 5 — Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in GOOGLE_API_KEY
```

### Step 6 — Start the API server

```bash
uvicorn main:app --reload
```

Server starts at: `http://localhost:8000`
Interactive API docs: `http://localhost:8000/docs`

---

## 6. Environment Variables

All defined in `config/settings.py`, read from `os.environ` at import time.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | **Yes (for Gemini)** | none | Google AI Studio key. Pipeline still works without it — explanation will be null. |
| `APPOINTMENT_AGENT_BASE_URL` | Yes (for booking) | `http://localhost:8001` | URL of external Appointment Agent service |
| `OVERPASS_URL` | No | `https://overpass-api.de/api/interpreter` | Overpass endpoint |
| `DEFAULT_SEARCH_RADIUS_KM` | No | `15.0` | Provider search radius fallback |
| `NOMINATIM_URL` | No | `https://nominatim.openstreetmap.org/search` | Nominatim endpoint |
| `NOMINATIM_USER_AGENT` | No | `AlternateCareNavigationAgent/1.0 (...)` | Required by Nominatim policy |

**What happens without each:**

| Missing | Effect |
|---|---|
| `GOOGLE_API_KEY` | First call to Gemini raises auth error; caught by `explain_node`; `patient_facing_explanation=None`; routing + providers still work |
| `APPOINTMENT_AGENT_BASE_URL` | Falls back to `http://localhost:8001`; booking fails with connection error if no service running |
| `OVERPASS_URL` | Uses public Overpass; may hit rate limits under load |
| `NOMINATIM_URL` | Uses public Nominatim; 1 req/s rate limit |

---

## 7. LangGraph

**File:** `orchestrator/graph.py`

### State — NavigationState (orchestrator/state.py)

```python
class NavigationState(TypedDict, total=False):
    patient: PatientFeatures          # input
    location: PatientLocation         # input + updated by rank_node
    decision: CareDecision            # written by classify_node
    ranked_providers: List[ProviderCandidate]  # written by rank_node
    patient_facing_explanation: Optional[str]  # written by explain_node
    errors: List[str]                 # append-only error channel
```

### Graph structure

```
API
 |
 v
[validate_input_node]
 |  checks: primary_symptom_category present
 |
 v
[classify_node]  ← AlternateCareAgent.decide()
 |  writes: decision
 |
 +---(destination == "TELEHEALTH")---> [explain_node]
 |                                           |
 v                                           |
[rank_node]  ← RankingAgent.rank()           |
 |  writes: ranked_providers, location       |
 |  catches ALL exceptions → errors list     |
 |                                           |
 v                                           |
[explain_node]  ← explain_decision() <------+
 |  writes: patient_facing_explanation
 |  catches ALL exceptions → errors list
 |
 v
END
```

### Graph compilation

```python
navigation_graph = build_graph()  # compiled at module import time
```

### Invocation

```python
result = navigation_graph.invoke(
    {"patient": patient, "location": location, "errors": []}
)
# result is a dict with all NavigationState keys populated
```

### Node details

| Node | File | Key behavior |
|---|---|---|
| `validate_input_node` | `graph.py` | Checks `primary_symptom_category` truthy; appends to errors if not |
| `classify_node` | `graph.py` → `agents/classification_agent.py` | Calls `CareClassifier.classify()`; writes `decision` |
| `rank_node` | `graph.py` → `agents/ranking_agent.py` | Geocodes if needed; queries Overpass; scores; writes `ranked_providers` + updated `location`; catches ALL exceptions |
| `explain_node` | `graph.py` → `engine/explainer.py` | Calls Gemini; writes `patient_facing_explanation`; catches ALL exceptions |

---

## 8. Rule Engine

**Files:** `engine/care_classifier.py`, `engine/rule_loader.py`, `engine/condition_evaluator.py`

### Loading

`CareClassifier.__init__()` calls `load_rules()` which:
1. Opens `rules/care_destination_rules.yaml`
2. Validates required keys and destination values
3. Sorts by `priority` descending (stable sort)
4. Returns sorted list

### Evaluation

`CareClassifier.classify(patient)`:
1. Converts `PatientFeatures` to dict via `model_dump()`
2. Iterates rules (highest priority first)
3. For each rule, calls `evaluate_conditions(rule["conditions"], patient_dict)`
4. Returns `CareDecision` for the FIRST matching rule
5. `FALLBACK-999` (priority 0, empty `all: []` conditions) always matches last

### Condition evaluation

Supported operators (from `engine/condition_evaluator.py`):
- `equals` — exact match
- `in` — value in list
- `gte` — greater than or equal
- `lte` — less than or equal

```python
conditions:
  all:    # all conditions must be true
  any:    # at least one condition must be true
```

---

## 9. Routing Rules

All 18 rules from `rules/care_destination_rules.yaml`, sorted by priority:

| rule_id | priority | destination | specialty | Primary trigger |
|---|---|---|---|---|
| SAFETY-000 | 100 | URGENT_CARE | null | Severe symptoms (defensive fallback) |
| SPEC-002-PULM | 50 | SPECIALIST | PULMONOLOGY | mild_breathing_difficulty + COPD + chronic≥2 |
| SPEC-003-ORTHO | 45 | SPECIALIST | ORTHOPEDICS | back_pain + gradual + worsening + ED≥3/yr |
| SPEC-001-FLAREUP | 45 | SPECIALIST | CHRONIC_DISEASE_MANAGEMENT_REVIEW | chronic_disease_flareup + worsening + CCI≥7 |
| TELE-001-FLAREUP | 40 | TELEHEALTH | null | chronic_disease_flareup + stable + pain≤3 |
| TELE-002-INFECTION | 40 | TELEHEALTH | null | minor_infection + improving + pain≤3 |
| UC-001-INFECTION | 30 | URGENT_CARE | null | minor_infection (default) |
| UC-002-BREATHING | 30 | URGENT_CARE | null | mild_breathing_difficulty + hours |
| UC-003-BACKPAIN | 30 | URGENT_CARE | null | back_pain + sudden onset |
| TELE-003-GENERAL | 30 | TELEHEALTH | null | mild_general_symptom + improving + pain≤3 |
| PCP-001-FLAREUP | 30 | PCP | null | chronic_disease_flareup (default) |
| TELE-004-BACKPAIN | 30 | TELEHEALTH | null | back_pain + gradual + stable + pain≤3 |
| TELE-005-BREATHING | 25 | TELEHEALTH | null | mild_breathing_difficulty + days + stable + pain≤3 |
| PCP-002-BREATHING | 20 | PCP | null | mild_breathing_difficulty (default) |
| PCP-003-BACKPAIN | 20 | PCP | null | back_pain (default) |
| TELE-003-GENERAL | 30 | TELEHEALTH | null | mild_general_symptom + improving + pain≤3 |
| PCP-004-GENERAL | 20 | PCP | null | mild_general_symptom (default) |
| SPEC-004-DENTAL | 20 | DENTISTRY | null | dental_pain |
| FALLBACK-999 | 0 | PCP | null | Anything (empty conditions — always matches) |

**Status values present in rules:**
- `DOCUMENT_SUPPORTED` — clinically validated pattern
- `RECOMMENDED_REQUIRES_VALIDATION` — requires clinical sign-off before production activation
- `SAFETY_FALLBACK` — last resort only

---

## 10. Location Processing

**File:** `agents/ranking_agent.py` → `location/geocoder.py`
**Function:** `RankingAgent.rank(location, decision, has_pcp_flag)`

```
PatientLocation received by rank_node
        │
        ├── coords present (latitude + longitude both non-null)?
        │   YES → use directly, no geocoding
        │   NO  → call geocoder.resolve_location()
        │               │
        │               v
        │           Nominatim API call
        │               │
        │               v
        │           resolved PatientLocation (with coords)
        │
        v
    find_nearby_providers(resolved_location, destination, specialty)
        │
        v
    rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag)
```

The resolved `PatientLocation` (always with coordinates) is written back to `state["location"]` so the recommendation store persists the resolved coordinates.

---

## 11. Geocoding

**File:** `location/geocoder.py`
**Function:** `geocode(address: str) -> (float, float)`
**Service:** Nominatim (OpenStreetMap) — **free, no API key**

### Request

```
GET https://nominatim.openstreetmap.org/search
?q=<address>
&format=json
&limit=1
&countrycodes=us
&addressdetails=0
Headers: User-Agent: AlternateCareNavigationAgent/1.0 (...)
Timeout: 10 seconds
```

### Response extraction

```python
results[0]["lat"]  # string → float
results[0]["lon"]  # string → float
```

### Error handling

| Situation | Exception raised | HTTP effect |
|---|---|---|
| Empty address | `InvalidLocationError` | 422 (no network call) |
| Zero results | `InvalidLocationError` | 422 |
| HTTP 429 | `GeocodingRateLimitError` | 422 |
| Network timeout | `GeocodingNetworkError` | 422 |
| Connection error | `GeocodingNetworkError` | 422 |
| HTTP 5xx | `GeocodingNetworkError` | 422 |

All geocoding exceptions are caught by `rank_node`, recorded in `state["errors"]`, and surfaced as HTTP 422 by the route handler via `_find_location_error()`.

---

## 12. Provider Discovery

**File:** `location/provider_discovery.py`
**Function:** `find_nearby_providers(location, destination, specialty) -> List[ProviderCandidate]`
**Service:** Overpass API — **free, no API key**

### Trigger

Called by `RankingAgent.rank()` for all destinations EXCEPT `TELEHEALTH`.
For `TELEHEALTH`: returns `[]` immediately, no HTTP call.

### Request

```
POST https://overpass-api.de/api/interpreter
Body: data=<Overpass QL query>
Timeout: 15 seconds
```

### Query structure

```
[out:json][timeout:25];(
  node[<tag_filter1>](around:<radius_m>,<lat>,<lon>);
  way[<tag_filter1>](around:<radius_m>,<lat>,<lon>);
  node[<tag_filter2>](around:<radius_m>,<lat>,<lon>);
  way[<tag_filter2>](around:<radius_m>,<lat>,<lon>);
);out center tags;
```

`radius_m = int(location.radius_km * 1000)` — default 15000 metres.

---

## 13. Filtering and Deduplication

**Implemented in:** `location/provider_discovery.py` → `_parse_elements()`

**Filter 1 — Unnamed elements:** Any OSM element without a `name` tag is discarded.

**Filter 2 — No coordinates:** Nodes must have `lat/lon`; ways must have `center.lat/center.lon`. Elements missing coordinates are discarded.

**Deduplication:** Key is `(name, round(lat, 3), round(lon, 3))`. Rounding to 3 decimal places = ~111m tolerance. OSM often returns both a `node` (entrance) and a `way` (building polygon) for the same clinic — this collapses them into one. First occurrence is kept.

---

## 14. Distance Calculation

**File:** `location/ranking.py`
**Formula:** Haversine

```python
EARTH_RADIUS_KM = 6371.0

def haversine_km(lat1, lon1, lat2, lon2):
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1-a))
```

Result stored in `candidate.distance_km` rounded to 2 decimal places.

**ACTUAL TESTED OUTPUT (Script 1):**
Patient `(30.2672, -97.7431)` → Provider `(30.2701, -97.7448)` = **0.36 km**

---

## 15. Provider Ranking

**File:** `location/ranking.py`
**Function:** `rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag, top_n=5)`

### Score formula

```python
distance_score = max(0.0, 1 - (distance_km / 25))   # 0.0 at 25+ km
continuity_bonus = 0.05 if (destination_type == "PCP" and has_pcp_flag) else 0.0
score = round(distance_score + continuity_bonus, 3)
```

- Score 1.0 = same location as patient
- Score 0.0 = 25 km or further away
- PCP + `has_pcp_flag=1` adds 0.05 bonus (continuity of care)

Sorted descending by score. Returns top `top_n` (default 5).

---

## 16. Gemini Explanation

**File:** `engine/explainer.py`
**Model:** `gemini-1.5-flash`
**LangChain:** `ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3, max_tokens=200)`

### When called

`explain_node` in the graph, AFTER routing and provider discovery are complete.

### Input (from CareDecision)

```python
{
  "destination": "URGENT_CARE",
  "specialty": "n/a",
  "status": "DOCUMENT_SUPPORTED",
  "explanation": "DOCUMENT-SUPPORTED. Default for minor_infection..."
}
```

### What Gemini is told (system prompt)

> "You are explaining a non-emergency care routing decision to a patient in plain, reassuring language. Do not add clinical advice beyond what's given. Do not mention rule IDs, priority numbers, or internal system details. 2-3 sentences max..."

### Output

A 2–3 sentence plain-English string stored in `state["patient_facing_explanation"]`.

**IMPORTANT:** This field is NOT returned in the `/navigate` response. The `Recommendation` model does not include it. It is computed but currently silently discarded at the API boundary.

**IMPLEMENTED BUT NOT CURRENTLY INTEGRATED INTO THE RESPONSE MODEL.**

### What Gemini does NOT do

Confirmed from code: Gemini receives only the already-determined `CareDecision`. It has no access to patient features, no access to provider lists, no ability to change the routing decision, and no access to distance or location data.

---

## 17. Recommendation Storage

**File:** `api/recommendation_store.py`
**Singleton:** `recommendation_store = RecommendationStore(ttl_minutes=30)`

### What is stored

Per `recommendation_id`:
- The full `Recommendation` (decision + ranked providers)
- The resolved `PatientLocation` (with coordinates)
- TTL: 30 minutes from creation

### Why it exists

Prevents callers from supplying arbitrary `care_type`, `specialty`, or `provider_id` values in appointment calls. The stored `CareDecision` is the **authoritative source** for all downstream appointment operations.

---

## 18. Appointment Availability

**Entry point:** `POST /appointments/availability`
**Requires:** Valid `recommendation_id` (not expired, ≤30 min old)

The route:
1. Validates `provider_id` belongs to the recommendation
2. Derives `care_type` and `specialty` from stored `CareDecision`
3. Reconstructs `AppointmentPatientContext` from stored `PatientLocation`
4. Calls the external Appointment Agent

External payload never contains `recommendation_id`, `care_type`, or `destination` — these are internal.

---

## 19. Booking

**Entry point:** `POST /appointments/book`

The route:
1. Validates `provider_id` belongs to recommendation
2. Derives `care_type`, `specialty`, and `provider_name` from stored data
3. Passes to `AppointmentService.book_appointment()`

**CONTRACT GAP (confirmed in `appointment/adapter.py`):** `provider_id` and `slot_id` are NOT forwarded to the external Appointment Agent because their placement in the external contract is unconfirmed.

---

## 20. Reschedule and Cancel

**Reschedule:** `POST /appointments/reschedule` — `recommendation_id` optional (may have expired)
**Cancel:** `POST /appointments/cancel` — `patient_id` + `appointment_id` only
**Status:** `GET /appointments/{appointment_id}?patient_id=...`

These three routes do not require a live recommendation. They delegate directly to `AppointmentService` → `AppointmentAgentClient` → external service.

---

## 21. Error Handling

```
validate_input_node
  → Missing primary_symptom_category: appended to errors
  → Pipeline continues; caller gets HTTP 400 if caught

rank_node
  → Any exception (geocoding, network, etc.): caught, appended to errors as
    "rank_node failed: <ExceptionType>: <message>"
  → Pipeline continues to explain_node with empty ranked_providers
  → Route inspects errors for geocoding types → raises HTTP 422

explain_node
  → Any LLM exception: caught, appended to errors
  → patient_facing_explanation = None
  → Pipeline completes normally; HTTP 200 returned

Route (/navigate)
  → After graph completes, checks errors for geocoding failure → HTTP 422
  → ValueError from graph.invoke() → HTTP 400

Appointment routes
  → KeyError from recommendation store → HTTP 404
  → Any exception from AppointmentService → HTTP 502
```

---

## 22. Complete Runtime Flow

Step-by-step from actual source code:

```
Step 1:  HTTP POST /navigate arrives at routes.py:navigate()
         File: api/routes.py

Step 2:  Pydantic validates PatientFeatures + PatientLocation
         PatientLocation model_validator checks: coords or address present
         File: models/schemas.py

Step 3:  navigation_graph.invoke({"patient": patient, "location": location, "errors": []})
         File: api/routes.py → orchestrator/graph.py

Step 4:  validate_input_node(state)
         Checks: primary_symptom_category is truthy
         Output: {errors: [...]}
         File: orchestrator/graph.py

Step 5:  classify_node(state)
         Calls: AlternateCareAgent.decide(patient)
         Calls: CareClassifier.classify(patient)
         Converts patient to dict, evaluates rules in priority order
         Returns first matching CareDecision
         Output: {decision: CareDecision}
         File: orchestrator/graph.py → agents/classification_agent.py
               → engine/care_classifier.py

Step 6:  route_after_classify(state)
         If destination == "TELEHEALTH" → go to Step 10 (skip Steps 7-9)
         Otherwise → go to Step 7
         File: orchestrator/graph.py

Step 7:  rank_node(state)  [non-TELEHEALTH only]
         Calls: RankingAgent.rank(location, decision, has_pcp_flag)
         File: orchestrator/graph.py → agents/ranking_agent.py

Step 7a: geocoder.resolve_location(location)
         If coords present: returns same object (no network call)
         If address-only:
           - calls geocode(address)
           - GET Nominatim API
           - returns resolved PatientLocation with lat/lon
         File: location/geocoder.py

Step 7b: find_nearby_providers(resolved_location, destination, specialty)
         - Gets OSM tag filters from tags_for(destination, specialty)
         - Builds Overpass QL query
         - POST Overpass API
         - Parses elements: filter unnamed, extract coords
         - Deduplicates by (name, round(lat,3), round(lon,3))
         - Returns List[ProviderCandidate]
         File: location/provider_discovery.py → location/osm_tag_map.py

Step 7c: rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag)
         For each candidate:
           - distance_km = haversine(patient, provider) rounded to 2dp
           - score = max(0, 1 - distance_km/25) + continuity_bonus
         Sort descending by score
         Return top 5
         File: location/ranking.py

         Output: {ranked_providers: [...], location: resolved_location, errors: [...]}
         On exception: {ranked_providers: [], errors: ["rank_node failed: <type>: <msg>"]}

Step 8:  explain_node(state)
         Calls: explain_decision(decision)
         Lazily builds LangChain chain: ChatPromptTemplate | ChatGoogleGenerativeAI
         Invokes with destination/specialty/status/explanation
         Returns content string
         Output: {patient_facing_explanation: str | None, errors: [...]}
         File: orchestrator/graph.py → engine/explainer.py

Step 9:  navigation_graph.invoke() returns result dict
         File: api/routes.py

Step 10: Check result["errors"] for geocoding failures
         _find_location_error(errors) looks for "rank_node failed: InvalidLocationError..." etc.
         If found: raise HTTPException(422, detail=...)
         File: api/routes.py

Step 11: Build Recommendation(recommendation_id="", decision=..., top_providers=...)
         File: api/routes.py

Step 12: recommendation_store.create(rec, patient_location=stored_location)
         Generates rec_<token_urlsafe(12)>
         Stamps recommendation_id on Recommendation
         Stores with 30-min TTL
         Returns recommendation_id string
         File: api/recommendation_store.py

Step 13: Return recommendation_store.require(recommendation_id)
         → HTTP 200 with Recommendation JSON
         File: api/routes.py
```

---

## 23. One Full Request Walkthrough

**Input:** Urgent care routing for Austin, TX using GPS coordinates.

### Input

```http
POST http://localhost:8000/navigate
Content-Type: application/json

{
  "patient": {
    "primary_symptom_category": "minor_infection",
    "symptom_trend": "worsening",
    "pain_level_self_reported": 6
  },
  "location": {
    "latitude": 30.2672,
    "longitude": -97.7431,
    "radius_km": 15.0
  }
}
```

### Step-by-step data transformation

```
INPUT JSON
patient.primary_symptom_category = "minor_infection"
patient.symptom_trend = "worsening"
patient.pain_level_self_reported = 6
location.latitude = 30.2672
location.longitude = -97.7431
location.radius_km = 15.0
  ↓
PYDANTIC VALIDATION (models/schemas.py)
PatientFeatures created ✓
PatientLocation created ✓ (has coords, no geocoding needed)
  ↓
GRAPH INVOKED (orchestrator/graph.py)
state = {"patient": PatientFeatures(...), "location": PatientLocation(30.2672, -97.7431), "errors": []}
  ↓
validate_input_node
  checks: "minor_infection" is truthy ✓
  state["errors"] = []
  ↓
classify_node → CareClassifier.classify()
  patient_dict = {"primary_symptom_category": "minor_infection", "symptom_trend": "worsening", "pain_level_self_reported": 6, ...}
  rules evaluated in order (priority desc):
    SAFETY-000 (100): conditions.any: primary_symptom_category in [chest_pain,...] → NO
    SPEC-002-PULM (50): primary_symptom_category == "mild_breathing_difficulty" → NO
    SPEC-003-ORTHO (45): primary_symptom_category == "back_pain" → NO
    SPEC-001-FLAREUP (45): primary_symptom_category == "chronic_disease_flareup" → NO
    TELE-001-FLAREUP (40): primary_symptom_category == "chronic_disease_flareup" → NO
    TELE-002-INFECTION (40): symptom_trend == "improving" → NO (it's "worsening")
    UC-001-INFECTION (30): primary_symptom_category == "minor_infection" → YES ✓ MATCH
  Returns CareDecision(rule_id="UC-001-INFECTION", destination="URGENT_CARE", specialty=None, priority=30)
  ↓
route_after_classify: destination != "TELEHEALTH" → go to rank_node
  ↓
rank_node → RankingAgent.rank()
  resolve_location: lat=30.2672 and lon=-97.7431 already set → no geocoding call
  tags_for("URGENT_CARE", None) → ['["healthcare"="urgent_care"]', '["amenity"="clinic"]']
  radius_m = int(15.0 * 1000) = 15000
  query = "[out:json][timeout:25];(node["healthcare"="urgent_care"](around:15000,30.2672,-97.7431);..."
  POST https://overpass-api.de/api/interpreter
  [In real execution: returns OSM elements near Austin, TX]
  [In tests: returns mocked list]
  _parse_elements: filter unnamed, extract coords, deduplicate
  candidates = [
    ProviderCandidate(provider_id="osm:node:111", name="Austin Urgent Care Center",
                      latitude=30.2701, longitude=-97.7448),
    ProviderCandidate(provider_id="osm:node:222", name="St. David's Medical Center",
                      latitude=30.2610, longitude=-97.7500),
  ]
  rank_providers(30.2672, -97.7431, candidates):
    candidate 1: distance = haversine(30.2672,-97.7431, 30.2701,-97.7448) = 0.36 km
                 score = max(0, 1 - 0.36/25) = 0.9856 → 0.986
    candidate 2: distance = haversine(30.2672,-97.7431, 30.2610,-97.7500) = 0.96 km
                 score = max(0, 1 - 0.96/25) = 0.9616 → 0.962
    sorted: [candidate1 (0.986), candidate2 (0.962)]
  state updates: ranked_providers=[...], location=PatientLocation(30.2672,-97.7431)
  ↓
explain_node → explain_decision(CareDecision)
  Input to Gemini: destination="URGENT_CARE", specialty="n/a", status="DOCUMENT_SUPPORTED", explanation="..."
  Output: "Based on your worsening infection symptoms, same-day evaluation at an urgent care clinic is appropriate."
  state["patient_facing_explanation"] = "Based on..."
  ↓
GRAPH RETURNS result dict
  ↓
Route checks errors: [] → no geocoding failure
  ↓
Recommendation created and stored:
  recommendation_store.create(Recommendation(...), patient_location=PatientLocation(30.2672,-97.7431))
  recommendation_id = "rec_psjWK4IQ1kMVxNRR"
  ↓
RESPONSE RETURNED
```

### ACTUAL TESTED OUTPUT (Script 2)

```json
HTTP 200
{
  "recommendation_id": "rec_psjWK4IQ1kMVxNRR",
  "decision": {
    "rule_id": "UC-001-INFECTION",
    "priority": 30,
    "destination": "URGENT_CARE",
    "specialty": null,
    "status": "DOCUMENT_SUPPORTED",
    "explanation": "DOCUMENT-SUPPORTED. Default for minor_infection (PQE03_AcuteACSC): acute onset, moderate pain (mean 4.5/10), same-day evaluation appropriate — matches doc 1 sec. 7 \"acute, non-emergency, needs physical examination\" -> URGENT_CARE definition."
  },
  "top_providers": [
    {
      "provider_id": "osm:node:111",
      "name": "Austin Urgent Care Center",
      "destination_type": "URGENT_CARE",
      "specialty": null,
      "latitude": 30.2701,
      "longitude": -97.7448,
      "address": null,
      "distance_km": 0.36,
      "score": 0.986,
      "source": "osm"
    },
    {
      "provider_id": "osm:node:222",
      "name": "St. David's Medical Center",
      "destination_type": "URGENT_CARE",
      "specialty": null,
      "latitude": 30.261,
      "longitude": -97.75,
      "address": null,
      "distance_km": 0.96,
      "score": 0.962,
      "source": "osm"
    }
  ]
}
```

---

## 24. Running Without a UI

### The agent does not need a UI to run

The UI (if one existed) would only be a visual wrapper around HTTP calls to the backend. Without a UI, you can make the same HTTP calls directly using any of these methods.

### Method 1 — Run the test suite (safest, no credentials needed)

```bash
# In the project directory:
python -m pytest tests/ -v
```

This runs 325 tests covering every path. All external APIs are mocked. No credentials required.

### Method 2 — Start the server and call with curl

**Start the server:**
```bash
uvicorn main:app --reload
```

**Call the API (minimal input, GPS coordinates):**
```bash
curl -X POST http://localhost:8000/navigate \
  -H "Content-Type: application/json" \
  -d '{
    "patient": {
      "primary_symptom_category": "minor_infection",
      "symptom_trend": "worsening",
      "pain_level_self_reported": 6
    },
    "location": {
      "latitude": 30.2672,
      "longitude": -97.7431,
      "radius_km": 15.0
    }
  }'
```

**Call with address input:**
```bash
curl -X POST http://localhost:8000/navigate \
  -H "Content-Type: application/json" \
  -d '{
    "patient": {
      "primary_symptom_category": "minor_infection",
      "symptom_trend": "worsening",
      "pain_level_self_reported": 6
    },
    "location": {
      "address": "Austin, TX 78701"
    }
  }'
```

**Notes on live execution:**
- Overpass and Nominatim calls are real — real facilities near Austin will be returned
- Gemini call requires `GOOGLE_API_KEY` in environment; if missing, providers are still returned but `patient_facing_explanation` in state will be null (not in response anyway)
- The `explanation` field in the response comes from the YAML rule file, NOT from Gemini

### Method 3 — Interactive API docs

With the server running: open `http://localhost:8000/docs`

### Method 4 — Direct Python (no server needed)

```python
import sys
sys.path.insert(0, '.')

from orchestrator.graph import navigation_graph
from models.schemas import PatientFeatures, PatientLocation
from unittest.mock import patch

# Mock Overpass (optional — remove mock for real provider search)
with patch('location.provider_discovery.find_nearby_providers', return_value=[]):
    result = navigation_graph.invoke({
        "patient": PatientFeatures(
            primary_symptom_category="minor_infection",
            symptom_trend="worsening",
            pain_level_self_reported=6
        ),
        "location": PatientLocation(latitude=30.2672, longitude=-97.7431),
        "errors": []
    })

print("Destination:", result["decision"].destination)
print("Rule:", result["decision"].rule_id)
print("Providers:", len(result.get("ranked_providers", [])))
```

### What output means

| Field | Meaning |
|---|---|
| `recommendation_id` | Save this. Use it for `/appointments/availability` and `/appointments/book` |
| `decision.destination` | Where the patient should go (PCP / URGENT_CARE / SPECIALIST / TELEHEALTH / DENTISTRY) |
| `decision.specialty` | Which specialist (only when destination is SPECIALIST) |
| `decision.rule_id` | Which rule matched (for debugging/audit) |
| `decision.status` | `DOCUMENT_SUPPORTED` = clinically validated; `RECOMMENDED_REQUIRES_VALIDATION` = needs clinical sign-off |
| `top_providers` | Ranked list of nearby facilities. Each has coordinates, distance, and score |
| `top_providers[0]` | The closest/highest-scored provider |

### How to know execution succeeded

- HTTP status `200` for `/navigate`
- Response contains `recommendation_id` starting with `rec_`
- `decision.destination` is one of: `PCP`, `URGENT_CARE`, `SPECIALIST`, `TELEHEALTH`, `DENTISTRY`
- For physical destinations: `top_providers` contains at least one entry (if OSM has data)
- For TELEHEALTH: `top_providers` is always `[]` — this is correct behavior

---

## 25. How to Test

### Run all 325 tests

```bash
python -m pytest tests/ -v
```

### Run specific test files

```bash
# Rule engine only (no mocking needed)
python -m pytest tests/test_rule_engine.py -v

# Location/maps layer
python -m pytest tests/test_location_maps.py -v

# Provider discovery
python -m pytest tests/test_provider_discovery.py -v

# Full pipeline flows
python -m pytest tests/test_appointment_flow.py -v

# Appointment schemas
python -m pytest tests/test_appointment_schemas.py -v

# External contract
python -m pytest tests/test_shared_appointment_contract.py -v
```

### No credentials needed for any test

All tests mock external APIs. `GOOGLE_API_KEY` is not required.

**ACTUAL TESTED result:** `325 passed, 0 failed, 1 warning` in 10.16s.

---

## 26. Teammate Integration

### How Another Agent Should Call This Agent

**The teammate does NOT need to:**
- Know about OSM, Nominatim, or Overpass
- Know about the rule engine or YAML files
- Implement any routing logic
- Calculate distances
- Call Gemini
- Talk to the recommendation store directly

**The teammate ONLY needs to:**

1. Call `POST /navigate` with patient features + location
2. Receive a `recommendation_id` and a list of providers
3. Optionally call `POST /appointments/availability` and `POST /appointments/book`

### Minimum integration contract

```
Other Agent
  │
  │ POST /navigate {patient, location}
  ↓
This Agent
  │
  │ Returns: Recommendation {recommendation_id, decision, top_providers}
  ↓
Other Agent
  │
  │ POST /appointments/availability {recommendation_id, provider_id, ...}
  ↓
This Agent → External Appointment Agent
  │
  │ Returns: AvailabilityWorkflowResponse {available_slots, care_type, ...}
  ↓
Other Agent
  │
  │ POST /appointments/book {patient_id, recommendation_id, provider_id, slot_id}
  ↓
This Agent → External Appointment Agent
  │
  │ Returns: AppointmentConfirmation
  ↓
Other Agent
```

### What the caller must provide

```json
{
  "patient": {
    "primary_symptom_category": "...",  // REQUIRED
    // optional clinical flags as needed
  },
  "location": {
    "latitude": ..., "longitude": ...   // OR "address": "..."
  }
}
```

### What the caller receives

```json
{
  "recommendation_id": "rec_...",       // use for all appointment calls
  "decision": {
    "destination": "URGENT_CARE",       // WHAT care is needed
    "specialty": null,                   // WHICH specialist (if applicable)
    "rule_id": "UC-001-INFECTION",      // for audit/debugging
    "status": "DOCUMENT_SUPPORTED"
  },
  "top_providers": [                    // WHERE care is available
    {
      "provider_id": "osm:node:...",
      "name": "...",
      "distance_km": 0.36,
      "score": 0.986,
      ...
    }
  ]
}
```

### Errors the caller must handle

| HTTP | Meaning | When |
|---|---|---|
| 400 | Invalid input | Missing `primary_symptom_category` |
| 422 | Unprocessable location | Address cannot be geocoded; or missing both coords and address |
| 404 | Recommendation not found | `recommendation_id` expired (>30 min) or wrong provider |
| 502 | External service error | External Appointment Agent unavailable |

### Environment variables the caller needs to know about

Only `APPOINTMENT_AGENT_BASE_URL` affects the shared contract (it points to the teammate's service). All other variables (`GOOGLE_API_KEY`, `OVERPASS_URL`, `NOMINATIM_URL`) are internal to this agent.

---

## 27. Integration Status

### IMPLEMENTED AND EXECUTABLE

| Component | Status |
|---|---|
| `POST /navigate` — routing + provider discovery | **IMPLEMENTED, EXECUTABLE, TESTED** |
| Rule engine (18 rules) | **IMPLEMENTED, EXECUTABLE, TESTED** |
| Nominatim geocoding (address → coords) | **IMPLEMENTED, EXECUTABLE, TESTED** |
| Overpass provider discovery | **IMPLEMENTED, EXECUTABLE, TESTED** |
| Haversine distance + ranking | **IMPLEMENTED, EXECUTABLE, TESTED** |
| RecommendationStore (30-min TTL) | **IMPLEMENTED, EXECUTABLE, TESTED** |
| `POST /appointments/availability` | **IMPLEMENTED, EXECUTABLE, TESTED** |
| `POST /appointments/book` | **IMPLEMENTED, EXECUTABLE, TESTED** |
| `POST /appointments/reschedule` | **IMPLEMENTED, EXECUTABLE, TESTED** |
| `POST /appointments/cancel` | **IMPLEMENTED, EXECUTABLE, TESTED** |
| `GET /appointments/{id}` | **IMPLEMENTED, EXECUTABLE, TESTED** |

### IMPLEMENTED BUT NOT INTEGRATED INTO RESPONSE

| Component | Status | Notes |
|---|---|---|
| `patient_facing_explanation` (Gemini output) | **IMPLEMENTED BUT NOT IN RESPONSE MODEL** | Computed by `explain_node`, stored in `NavigationState`, but NOT returned in `Recommendation` response |

### NOT IMPLEMENTED

| Component | Status |
|---|---|
| Cardiology routing rule | **NOT IMPLEMENTED** (OSM tags + schemas exist; no YAML rule) |
| SAFETY-000 activation | **REQUIRES_VALIDATION** (rule exists but flagged for clinical sign-off) |
| Multi-process recommendation store | **NOT IMPLEMENTED** (in-memory only) |
| Provider address enrichment | **NOT IMPLEMENTED** (OSM `addr:street` is often null) |

---

## 28. Known Limitations

1. **`patient_facing_explanation` not returned.** Gemini generates an explanation but the `Recommendation` response model does not expose it. The field exists in `NavigationState` but is not in `models/schemas.Recommendation`.

2. **In-memory recommendation store.** Restarts lose all active recommendations. Not suitable for multi-process/multi-server deployment.

3. **30-minute TTL.** Patients who take >30 minutes between `/navigate` and `/appointments/availability` receive HTTP 404.

4. **OSM address data sparseness.** `ProviderCandidate.address` is `null` for most providers because OSM's `addr:street` tag is rarely populated.

5. **No retry logic.** One network failure on Overpass or Appointment Agent = immediate error.

6. **Appointment Agent CONTRACT GAPS.** `provider_id` and `slot_id` are not forwarded in the booking request because their placement in the external contract is unconfirmed.

7. **Nominatim rate limit.** Public instance allows ~1 req/s. Concurrent load will fail.

8. **Cardiology routing.** Full OSM + appointment support exists, but there is no routing rule to activate it without clinical sign-off.

---

## 29. Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| HTTP 422: "Location could not be resolved" | Address not found by Nominatim | Use GPS coordinates; check address format; or use `"City, ST"` format |
| HTTP 422: rate limit | Nominatim 1 req/s limit | Set `NOMINATIM_URL` to self-hosted instance |
| HTTP 404: "Unknown or expired recommendation_id" | Recommendation expired (>30 min) | Call `/navigate` again |
| HTTP 404: "Provider ... is not part of recommendation" | Wrong `provider_id` in request | Use a `provider_id` from the `/navigate` response |
| HTTP 502 on appointment routes | External Appointment Agent not running | Start the service at `APPOINTMENT_AGENT_BASE_URL` |
| `top_providers: []` for physical destination | No named OSM facilities within radius | Increase `radius_km`; OSM data may be sparse for that area |
| Routing goes to PCP unexpectedly | FALLBACK-999 matched | Check `primary_symptom_category` value; must match a known symptom category |
| Tests fail with import errors | Dependencies not installed | `pip install -r requirements-dev.txt` |
| Server won't start | Wrong Python version or missing deps | Check Python 3.11+; run `pip install -r requirements.txt` |
