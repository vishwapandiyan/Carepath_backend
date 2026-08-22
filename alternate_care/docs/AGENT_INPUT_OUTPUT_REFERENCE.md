# Agent Input & Output Reference

> **Source authority:** Every field, example, and schema in this document is derived
> directly from the source code in this repository. All examples marked
> **ACTUAL TESTED OUTPUT** were produced by executing the implementation.
> Examples marked **CODE-DERIVED EXAMPLE** were constructed from schema definitions
> but not directly executed.

---

## Table of Contents

1. [Main Agent Input — POST /navigate](#1-main-agent-input)
2. [Main Agent Output — Recommendation](#2-main-agent-output)
3. [Node-by-Node Input/Output](#3-node-by-node-inputoutput)
4. [Rule Engine Input/Output](#4-rule-engine)
5. [CareDecision](#5-caredecision)
6. [Location Input/Output](#6-location)
7. [Geocoding Input/Output](#7-geocoding)
8. [Overpass/OSM Input/Output](#8-overpassosm)
9. [ProviderCandidate](#9-providercandidate)
10. [Distance Calculation](#10-distance-calculation)
11. [Ranking Input/Output](#11-ranking)
12. [Gemini Input/Output](#12-gemini)
13. [Recommendation Storage](#13-recommendation-storage)
14. [Appointment Availability Input/Output](#14-appointment-availability)
15. [Booking Input/Output](#15-booking)
16. [Reschedule/Cancel Input/Output](#16-reschedulecancellation)
17. [Error Outputs](#17-error-outputs)
18. [Complete Test Matrix](#18-test-matrix)

---

## 1. Main Agent Input

**Entry point:** `POST /navigate`
**File:** `api/routes.py`
**Function:** `navigate(patient: PatientFeatures, location: PatientLocation)`

The endpoint accepts a JSON body with two top-level objects: `patient` and `location`.

### patient — PatientFeatures

Defined in `models/schemas.py`. `extra="allow"` so additional fields are silently accepted.

| Field | Type | Required | Example | Purpose |
|---|---|---|---|---|
| `primary_symptom_category` | `str` | **YES** | `"minor_infection"` | Primary routing key — matched against all rules |
| `pain_level_self_reported` | `int \| null` | No | `6` | Used by telehealth/specialist routing thresholds |
| `pain_onset` | `str \| null` | No | `"gradual"` or `"sudden"` | Distinguishes UC vs specialist for back_pain |
| `pain_duration` | `str \| null` | No | `"hours"` or `"days"` | Used by SPEC-002-PULM and UC-002-BREATHING |
| `pain_location` | `str \| null` | No | — | Not used by any current rule |
| `symptom_trend` | `str \| null` | No | `"worsening"`, `"same"`, `"improving"` | Used by multiple routing rules |
| `copd_asthma_flag` | `int` | No (default `0`) | `1` | Triggers SPEC-002-PULM when combined with others |
| `cardiac_history_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `diabetes_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `ckd_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `cancer_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `immunocompromised_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `hypertension_flag` | `int` | No (default `0`) | `1` | Not used by any active rule |
| `chronic_condition_count` | `int` | No (default `0`) | `3` | Used by SPEC-002-PULM (gte 2) |
| `charlson_comorbidity_index` | `int` | No (default `0`) | `8` | Used by SPEC-001-FLAREUP (gte 7) |
| `ed_visits_past_year` | `int` | No (default `0`) | `4` | Used by SPEC-003-ORTHO (gte 3) |
| `admissions_past_year` | `int` | No (default `0`) | — | Not used by any active rule |
| `has_pcp_flag` | `int \| null` | No | `1` | Used in provider ranking (PCP continuity bonus) |
| `age` | `int \| null` | No | `45` | Not used by any active rule |
| `gender` | `str \| null` | No | — | Not used by any active rule |

### location — PatientLocation

Defined in `models/schemas.py`. At least one of `(latitude + longitude)` or `address` is required (validated by `model_validator`).

| Field | Type | Required | Example | Purpose |
|---|---|---|---|---|
| `latitude` | `float \| null` | Conditional | `30.2672` | Patient GPS latitude; skips geocoding if both provided |
| `longitude` | `float \| null` | Conditional | `-97.7431` | Patient GPS longitude |
| `radius_km` | `float` | No (default `15.0`) | `15.0` | Provider search radius in kilometres |
| `address` | `str \| null` | Conditional | `"Austin, TX 78701"` | Free-text US location; triggers Nominatim geocoding |

**Accepted address forms (confirmed from `location/geocoder.py`):**
- Street address: `"123 Main St, Springfield, IL 62701"`
- City/state: `"Boston, MA"`
- ZIP code: `"10001"`
- Combined: `"Austin, TX 78701, USA"`

**Resolution rule (from `models/schemas.py` `model_validator`):**
- Both coords + address supplied → coords used, address stored for display only
- Coords only → used directly, no geocoding
- Address only → geocoded via Nominatim before Overpass search

### Complete minimal HTTP request example

**ACTUAL TESTED OUTPUT** (Script 2):

```http
POST /navigate
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

**Address-only input example — ACTUAL TESTED OUTPUT** (Script 4):

```http
POST /navigate
Content-Type: application/json

{
  "patient": {
    "primary_symptom_category": "back_pain",
    "pain_onset": "gradual",
    "symptom_trend": "worsening",
    "ed_visits_past_year": 4
  },
  "location": {
    "address": "Austin, TX 78701"
  }
}
```

---

## 2. Main Agent Output

**Response model:** `Recommendation` (defined in `models/schemas.py`)
**HTTP status on success:** `200 OK`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `recommendation_id` | `str` | Yes | Server-generated ID (`rec_<token>`) — use this for all appointment calls |
| `decision` | `CareDecision` | Yes | The routing decision (see §5) |
| `top_providers` | `List[ProviderCandidate]` | Yes | Ranked list of nearby providers (empty for TELEHEALTH) |

### ACTUAL TESTED OUTPUT — URGENT_CARE (Script 2)

```json
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

### ACTUAL TESTED OUTPUT — TELEHEALTH (Script 3)

```json
{
  "recommendation_id": "rec_cyaRpQJkPlTx5MPV",
  "decision": {
    "rule_id": "TELE-003-GENERAL",
    "priority": 30,
    "destination": "TELEHEALTH",
    "specialty": null,
    "status": "DOCUMENT_SUPPORTED",
    "explanation": "DOCUMENT-SUPPORTED. Matches NonPQE_FollowUp majority pattern (60% improving trend, mean pain 2.43, high prior utilization suggesting an existing care relationship) — a virtual follow-up fits doc 1 sec. 16."
  },
  "top_providers": []
}
```

### ACTUAL TESTED OUTPUT — SPECIALIST/ORTHOPEDICS with address input (Script 4)

```json
{
  "recommendation_id": "rec_m8RIFoa7KEt7TVQS",
  "decision": {
    "rule_id": "SPEC-003-ORTHO",
    "priority": 45,
    "destination": "SPECIALIST",
    "specialty": "ORTHOPEDICS",
    "status": "RECOMMENDED_REQUIRES_VALIDATION",
    "explanation": "DOCUMENT-SUPPORTED PATTERN. PQE05_BackPain rows average 3.52 ED visits/year (recurrent utilizers) with 69% gradual onset. Persistent, non-improving, recurrent back pain is escalated to an orthopedics candidate rather than PCP, per doc 1's \"persistence/recurrent pattern\" criterion for specialist routing."
  },
  "top_providers": [
    {
      "provider_id": "osm:node:555",
      "name": "Austin Orthopedic Clinic",
      "destination_type": "SPECIALIST",
      "specialty": "ORTHOPEDICS",
      "latitude": 30.275,
      "longitude": -97.74,
      "address": null,
      "distance_km": 0.92,
      "score": 0.963,
      "source": "osm"
    }
  ]
}
```

---

## 3. Node-by-Node Input/Output

### LangGraph State — NavigationState

Defined in `orchestrator/state.py`. TypedDict with `total=False` (all fields optional at declaration, populated progressively).

| Key | Type | Written by | Read by |
|---|---|---|---|
| `patient` | `PatientFeatures` | API route (input) | `validate_input_node`, `classify_node`, `rank_node` |
| `location` | `PatientLocation` | API route (input); **updated** by `rank_node` after geocoding | `rank_node`, API route |
| `decision` | `CareDecision` | `classify_node` | `route_after_classify`, `rank_node`, `explain_node`, API route |
| `ranked_providers` | `List[ProviderCandidate]` | `rank_node` | API route |
| `patient_facing_explanation` | `Optional[str]` | `explain_node` | API route (not currently in Recommendation response model) |
| `errors` | `List[str]` | Any node (append-only) | API route (inspects for geocoding failures → HTTP 422) |

---

### Node: validate_input_node

**File:** `orchestrator/graph.py`
**Function:** `validate_input_node(state)`

| | Detail |
|---|---|
| **Reads from state** | `state["patient"].primary_symptom_category`, `state["errors"]` |
| **Writes to state** | `{"errors": errors}` |
| **Logic** | Checks `primary_symptom_category` is truthy; appends error message if not |
| **Output on missing field** | Appends `"Missing primary_symptom_category"` to errors |

---

### Node: classify_node (Agent 1 — AlternateCareAgent)

**File:** `orchestrator/graph.py` → `agents/classification_agent.py` → `engine/care_classifier.py`

| | Detail |
|---|---|
| **Reads from state** | `state["patient"]` |
| **Writes to state** | `{"decision": CareDecision}` |
| **Input type** | `PatientFeatures` |
| **Output type** | `CareDecision` |

---

### Conditional edge: route_after_classify

| Decision | Condition | Next node |
|---|---|---|
| `"explain"` | `state["decision"].destination == "TELEHEALTH"` | `explain_node` (skips rank) |
| `"rank"` | All other destinations | `rank_node` |

---

### Node: rank_node (Agent 2 — RankingAgent)

**File:** `orchestrator/graph.py` → `agents/ranking_agent.py`

| | Detail |
|---|---|
| **Reads from state** | `state["location"]`, `state["decision"]`, `state["patient"].has_pcp_flag` |
| **Writes to state** | `{"ranked_providers": [...], "location": resolved_location, "errors": errors}` |
| **Input** | `PatientLocation`, `CareDecision`, optional `has_pcp_flag` |
| **Output** | `(List[ProviderCandidate], PatientLocation)` tuple from `RankingAgent.rank()` |
| **On exception** | Catches ALL exceptions; appends `"rank_node failed: <ExceptionType>: <message>"` to errors; returns `ranked_providers=[]` |

---

### Node: explain_node (Gemini)

**File:** `orchestrator/graph.py` → `engine/explainer.py`

| | Detail |
|---|---|
| **Reads from state** | `state["decision"]` |
| **Writes to state** | `{"patient_facing_explanation": str \| None, "errors": errors}` |
| **Input** | `CareDecision` fields: `destination`, `specialty`, `status`, `explanation` |
| **Output** | Plain-language sentence from Gemini |
| **On LLM failure** | Appends `"explain_node failed: <error>"` to errors; sets `patient_facing_explanation = None`; does NOT crash the pipeline |

**Note:** `patient_facing_explanation` is stored in `NavigationState` but is **not included** in the `Recommendation` response model returned to the caller. It is computed and then discarded at the API boundary.

---

## 4. Rule Engine

**File:** `engine/care_classifier.py` → `engine/rule_loader.py` → `engine/condition_evaluator.py`

### Input

```python
PatientFeatures.model_dump()  # dict of all patient fields
```

### Processing

Rules loaded from `rules/care_destination_rules.yaml`, sorted by `priority` descending. First matching rule wins. `FALLBACK-999` (priority 0, `conditions: all: []`) always matches.

### Output

`CareDecision` — see §5.

### ACTUAL TESTED OUTPUTS (from direct execution)

| Input | rule_id | destination | specialty | priority |
|---|---|---|---|---|
| `minor_infection`, worsening, pain=6 | `UC-001-INFECTION` | `URGENT_CARE` | `null` | 30 |
| `back_pain`, gradual, worsening, ED≥4 | `SPEC-003-ORTHO` | `SPECIALIST` | `ORTHOPEDICS` | 45 |
| `mild_breathing_difficulty`, COPD, chronic≥3 | `SPEC-002-PULM` | `SPECIALIST` | `PULMONOLOGY` | 50 |
| `dental_pain` | `SPEC-004-DENTAL` | `DENTISTRY` | `null` | 20 |
| `mild_general_symptom`, improving, pain=2 | `TELE-003-GENERAL` | `TELEHEALTH` | `null` | 30 |
| `chronic_disease_flareup`, stable, CCI=2 | `PCP-001-FLAREUP` | `PCP` | `null` | 30 |
| `chronic_disease_flareup`, worsening, CCI=8 | `SPEC-001-FLAREUP` | `SPECIALIST` | `CHRONIC_DISEASE_MANAGEMENT_REVIEW` | 45 |
| `unknown_xyz` | `FALLBACK-999` | `PCP` | `null` | 0 |

### Specialist invariant (confirmed from code)

`AvailabilityWorkflowRequest` model validator in `appointment/schemas.py`:
```python
if self.care_type == "SPECIALIST" and not self.specialty:
    raise ValueError("care_type SPECIALIST requires specialty to be specified.")
```

`DENTISTRY` → `specialty=None` confirmed: rule `SPEC-004-DENTAL` has `specialty: null`, OSM tag map has `DENTISTRY` in `DESTINATION_TAGS` (not `SPECIALTY_TAGS`).

---

## 5. CareDecision

**File:** `models/schemas.py`

| Field | Type | Required | Meaning | Example |
|---|---|---|---|---|
| `rule_id` | `str` | Yes | Which rule matched | `"UC-001-INFECTION"` |
| `priority` | `int` | Yes | Rule priority (higher = evaluated first) | `30` |
| `destination` | `Destination` | Yes | Care destination literal | `"URGENT_CARE"` |
| `specialty` | `str \| null` | No | Sub-specialty (only for `SPECIALIST`) | `"ORTHOPEDICS"` or `null` |
| `status` | `str` | Yes | Rule validation status | `"DOCUMENT_SUPPORTED"` |
| `explanation` | `str` | Yes | Clinical reasoning text from rule YAML | `"DOCUMENT-SUPPORTED. Default for..."` |

**Valid `destination` values:** `"PCP"`, `"URGENT_CARE"`, `"SPECIALIST"`, `"TELEHEALTH"`, `"DENTISTRY"`

---

## 6. Location

### Input to location layer

`PatientLocation` arrives at `RankingAgent.rank()` from `state["location"]`.

Two forms:

**Form A — Coordinates:**
```json
{"latitude": 30.2672, "longitude": -97.7431, "radius_km": 15.0}
```

**Form B — Address:**
```json
{"address": "Austin, TX 78701"}
```

### Output from location layer

After `geocoder.resolve_location()`:
```json
{"latitude": 30.2672, "longitude": -97.7431, "radius_km": 15.0, "address": "Austin, TX 78701"}
```

Always has both `latitude` and `longitude` set before Overpass is called.

---

## 7. Geocoding

**File:** `location/geocoder.py`
**Function:** `geocode(address: str) -> (float, float)`

### Input

```python
address = "Austin, TX 78701"
```

### Nominatim HTTP request (confirmed from code)

```
GET https://nominatim.openstreetmap.org/search
    ?q=Austin%2C+TX+78701
    &format=json
    &limit=1
    &countrycodes=us
    &addressdetails=0
Headers:
    User-Agent: AlternateCareNavigationAgent/1.0 (development; contact: dev@example.com)
```

### Nominatim response (example — CODE-DERIVED, actual response varies by address)

```json
[
  {
    "lat": "30.2672",
    "lon": "-97.7431",
    ...
  }
]
```

### Output

```python
(30.2672, -97.7431)  # (latitude, longitude) as floats
```

### ACTUAL TESTED OUTPUT — geocoded address input (Script 4)

Nominatim was mocked to return `[{"lat": "30.2672", "lon": "-97.7431"}]`.
Geocoder extracted: `latitude=30.2672, longitude=-97.7431`.

### Error types raised

| Condition | Exception |
|---|---|
| Empty/whitespace address | `InvalidLocationError` (no network call) |
| HTTP 200, zero results | `InvalidLocationError` |
| HTTP 429 | `GeocodingRateLimitError` (subclass of `GeocodingNetworkError`) |
| Network timeout | `GeocodingNetworkError` |
| Connection error | `GeocodingNetworkError` |
| HTTP 5xx | `GeocodingNetworkError` |

---

## 8. Overpass/OSM

**File:** `location/provider_discovery.py`
**Function:** `find_nearby_providers(location, destination, specialty) -> List[ProviderCandidate]`

### When called

Only for non-TELEHEALTH destinations. TELEHEALTH returns `[]` immediately with no HTTP call.

### Input

| Parameter | Type | Example |
|---|---|---|
| `location` | `PatientLocation` (must have coords) | `PatientLocation(latitude=30.2672, longitude=-97.7431, radius_km=15.0)` |
| `destination` | `Destination` | `"URGENT_CARE"` |
| `specialty` | `str \| null` | `"ORTHOPEDICS"` or `None` |

### OSM tag mapping (complete, from `location/osm_tag_map.py`)

| destination | specialty | Overpass tags used |
|---|---|---|
| `PCP` | — | `["amenity"="doctors"]`, `["healthcare"="doctor"]` |
| `URGENT_CARE` | — | `["healthcare"="urgent_care"]`, `["amenity"="clinic"]` |
| `DENTISTRY` | — | `["amenity"="dentist"]` |
| `SPECIALIST` | `PULMONOLOGY` | `["healthcare:speciality"="pulmonology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `ORTHOPEDICS` | `["healthcare:speciality"="orthopaedics"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `DERMATOLOGY` | `["healthcare:speciality"="dermatology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `UROLOGY` | `["healthcare:speciality"="urology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `GYNECOLOGY` | `["healthcare:speciality"="gynaecology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `GASTROENTEROLOGY` | `["healthcare:speciality"="gastroenterology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `CHRONIC_DISEASE_MANAGEMENT_REVIEW` | `["amenity"="doctors"]` |
| `SPECIALIST` | `CARDIOLOGY` | `["healthcare:speciality"="cardiology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `NEPHROLOGY` | `["healthcare:speciality"="nephrology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `ENDOCRINOLOGY` | `["healthcare:speciality"="endocrinology"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `INFECTIOUS_DISEASE` | `["healthcare:speciality"="infectious_disease"]`, `["amenity"="doctors"]` |
| `SPECIALIST` | `ONCOLOGY` | `["healthcare:speciality"="oncology"]`, `["amenity"="doctors"]` |

### Overpass query structure (from `_build_query()`)

For `destination=URGENT_CARE`, `radius_km=15.0`, patient at `(30.2672, -97.7431)`:

```
[out:json][timeout:25];(
  node["healthcare"="urgent_care"](around:15000,30.2672,-97.7431);
  way["healthcare"="urgent_care"](around:15000,30.2672,-97.7431);
  node["amenity"="clinic"](around:15000,30.2672,-97.7431);
  way["amenity"="clinic"](around:15000,30.2672,-97.7431);
);out center tags;
```

Radius is `int(radius_km * 1000)` metres. Both `node` and `way` elements are queried per tag filter.

### HTTP call (confirmed from code)

```
POST https://overpass-api.de/api/interpreter
Content-Type: application/x-www-form-urlencoded
Body: data=<Overpass QL query>
Timeout: 15 seconds
```

### Raw response structure (from `_parse_elements()`)

```json
{
  "elements": [
    {
      "type": "node",
      "id": 123456,
      "lat": 30.2701,
      "lon": -97.7448,
      "tags": {
        "name": "Austin Urgent Care Center",
        "amenity": "clinic",
        "addr:street": "Main St"
      }
    },
    {
      "type": "way",
      "id": 789012,
      "center": {"lat": 30.2702, "lon": -97.7449},
      "tags": {
        "name": "Austin Urgent Care Center"
      }
    }
  ]
}
```

### Filtering rules (from `_parse_elements()`)

1. Elements with no `tags.name` → **discarded**
2. Elements with no coordinates (no `lat/lon` for nodes, no `center.lat/lon` for ways) → **discarded**
3. Duplicate detection key: `(name, round(lat, 3), round(lon, 3))` → **first occurrence kept**, subsequent discarded

### Provider ID generation

```python
f"osm:{el['type']}:{el['id']}"
# Example: "osm:node:123456" or "osm:way:789012"
```

### Address extraction

```python
tags.get("addr:full") or tags.get("addr:street")
# Returns None when neither tag is present (common in OSM data)
```

---

## 9. ProviderCandidate

**File:** `models/schemas.py`

| Field | Type | Required | Example | Set by |
|---|---|---|---|---|
| `provider_id` | `str` | Yes | `"osm:node:12345"` | `find_nearby_providers()` |
| `name` | `str` | Yes | `"Austin Urgent Care Center"` | `find_nearby_providers()` |
| `destination_type` | `Destination` | Yes | `"URGENT_CARE"` | `find_nearby_providers()` |
| `specialty` | `str \| null` | No | `"ORTHOPEDICS"` or `null` | `find_nearby_providers()` |
| `latitude` | `float` | Yes | `30.2701` | `find_nearby_providers()` |
| `longitude` | `float` | Yes | `-97.7448` | `find_nearby_providers()` |
| `address` | `str \| null` | No | `"Main St"` or `null` | `find_nearby_providers()` (often `null`) |
| `distance_km` | `float \| null` | No | `0.36` | `rank_providers()` |
| `score` | `float \| null` | No | `0.986` | `rank_providers()` |
| `source` | `str` | Yes (default `"osm"`) | `"osm"` | `find_nearby_providers()` |

### ACTUAL TESTED OUTPUT — from Script 1 (LangGraph pipeline)

```json
{
  "provider_id": "osm:node:12345",
  "name": "City Urgent Care",
  "destination_type": "URGENT_CARE",
  "specialty": null,
  "latitude": 30.2701,
  "longitude": -97.7448,
  "address": null,
  "distance_km": 0.36,
  "score": 0.986,
  "source": "osm"
}
```

---

## 10. Distance Calculation

**File:** `location/ranking.py`
**Function:** `haversine_km(lat1, lon1, lat2, lon2) -> float`

### Algorithm (confirmed from source)

```python
EARTH_RADIUS_KM = 6371.0

def haversine_km(lat1, lon1, lat2, lon2):
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1-a))
```

### ACTUAL TESTED EXAMPLE

Patient at `(30.2672, -97.7431)`, provider at `(30.2701, -97.7448)`:
**Result: `0.36 km`** (from Script 1 and Script 2 outputs)

Patient at same location, provider at `(30.2610, -97.7500)`:
**Result: `0.96 km`** (from Script 2 output)

Distance is rounded to 2 decimal places:
```python
c.distance_km = round(haversine_km(patient_lat, patient_lon, c.latitude, c.longitude), 2)
```

---

## 11. Ranking

**File:** `location/ranking.py`
**Function:** `rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag, top_n=5)`

### Scoring formula (confirmed from source)

```python
distance_score = max(0.0, 1 - (distance_km / 25))  # 0.0 at 25km+
continuity_bonus = 0.05 if (destination_type == "PCP" and has_pcp_flag) else 0.0
score = round(distance_score + continuity_bonus, 3)
```

### ACTUAL TESTED OUTPUT

| provider | distance_km | score | Formula |
|---|---|---|---|
| Austin Urgent Care Center | 0.36 | 0.986 | `max(0, 1 - 0.36/25) = 0.9856 → 0.986` |
| St. David's Medical Center | 0.96 | 0.962 | `max(0, 1 - 0.96/25) = 0.9616 → 0.962` |

Sorted descending by score. Returns top 5 (configurable via `top_n`).

---

## 12. Gemini

**File:** `engine/explainer.py`
**Function:** `explain_decision(decision: CareDecision) -> str`

### Model

`gemini-1.5-flash` via `langchain_google_genai.ChatGoogleGenerativeAI`

Configuration:
- `temperature=0.3`
- `max_tokens=200`
- Lazy initialization — chain not built until first call

### Input to Gemini (confirmed from prompt template)

```python
{
  "destination": decision.destination,      # e.g. "URGENT_CARE"
  "specialty": decision.specialty or "n/a", # e.g. "n/a"
  "status": decision.status,                # e.g. "DOCUMENT_SUPPORTED"
  "explanation": decision.explanation       # rule YAML explanation text
}
```

### System prompt (confirmed from source)

> "You are explaining a non-emergency care routing decision to a patient in plain, reassuring language. Do not add clinical advice beyond what's given. Do not mention rule IDs, priority numbers, or internal system details. 2-3 sentences max. If status is not DOCUMENT_SUPPORTED, don't state the recommendation with false certainty — use softer language like 'likely' or 'a reasonable next step'."

### Output

A 2–3 sentence plain-language string.

**Example (mocked in all tests, this is the mock value):**
`"Based on your worsening infection symptoms, same-day evaluation at an urgent care clinic is the most appropriate next step."`

**IMPORTANT:** The `patient_facing_explanation` returned by Gemini is stored in `NavigationState` but is **NOT included in the `Recommendation` response model** returned from `/navigate`. It is currently computed and then not surfaced to the API caller.

### What Gemini does NOT do (confirmed from code)

- ❌ Does not classify the patient
- ❌ Does not determine the destination
- ❌ Does not determine the specialty
- ❌ Does not find providers
- ❌ Does not calculate distances
- ❌ Does not rank providers
- ❌ Does not select providers
- ✅ Only generates a plain-language explanation of an already-determined `CareDecision`

---

## 13. Recommendation Storage

**File:** `api/recommendation_store.py`
**Class:** `RecommendationStore`

### Input to `create()`

```python
recommendation_store.create(
    recommendation=Recommendation(recommendation_id="", decision=..., top_providers=[...]),
    patient_location=PatientLocation(latitude=30.2672, longitude=-97.7431, ...)
)
```

### Output

```python
"rec_psjWK4IQ1kMVxNRR"  # rec_ + token_urlsafe(12)
```

### TTL: 30 minutes. In-memory, thread-safe, process-local.

### What is stored

`_StoredRecommendation`:
- `recommendation`: the full `Recommendation` with stamped `recommendation_id`
- `expires_at`: `now + 30 minutes`
- `patient_location`: the resolved `PatientLocation` (with coordinates)

### Key methods

| Method | Returns | Raises |
|---|---|---|
| `create(rec, location)` | `str` recommendation_id | — |
| `get(id)` | `Recommendation \| None` | — |
| `require(id)` | `Recommendation` | `KeyError` if missing/expired |
| `require_provider(id, provider_id)` | `ProviderCandidate` | `KeyError` if missing |
| `get_patient_location(id)` | `PatientLocation \| None` | — |

---

## 14. Appointment Availability

**Entry point:** `POST /appointments/availability`
**File:** `api/routes.py`

### Input

```json
{
  "recommendation_id": "rec_psjWK4IQ1kMVxNRR",
  "provider_id": "osm:node:111",
  "date_range": "next_7_days",
  "patient_id": "patient_001"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `recommendation_id` | `str` | Yes | Must exist and not be expired |
| `provider_id` | `str` | Yes | Must belong to the recommendation |
| `date_range` | `str` | No (default `"next_7_days"`) | Forwarded to external service |
| `patient_id` | `str \| null` | No | Forwarded to external service |

`care_type` and `specialty` are **NOT accepted from the caller** — derived from stored `CareDecision`.

### Output

```json
{
  "available_slots": [
    {
      "slot_id": "slot_001",
      "provider_id": "osm:node:111",
      "start_time": "2026-08-25T09:00:00",
      "end_time": "2026-08-25T09:30:00"
    }
  ],
  "provider_id": "osm:node:111",
  "care_type": "URGENT_CARE",
  "specialty": null
}
```

### Error responses

| Condition | HTTP status |
|---|---|
| Unknown/expired `recommendation_id` | 404 |
| `provider_id` not in recommendation | 404 |

---

## 15. Booking

**Entry point:** `POST /appointments/book`

### Input

```json
{
  "patient_id": "patient_001",
  "recommendation_id": "rec_psjWK4IQ1kMVxNRR",
  "provider_id": "osm:node:111",
  "slot_id": "slot_001"
}
```

All four fields required.

### Output — AppointmentConfirmation

```json
{
  "appointment_id": "APT-001",
  "patient_id": "patient_001",
  "status": "BOOKED",
  "provider_id": "DOC-123",
  "provider_name": "Dr. Smith",
  "care_type": "URGENT_CARE",
  "specialty": null,
  "hospital_id": null,
  "hospital_name": null,
  "slot": {
    "slot_id": "EXTERNAL_SLOT",
    "provider_id": "DOC-123",
    "start_time": "2026-08-25T09:00:00",
    "end_time": "2026-08-25T09:30:00"
  },
  "date": "2026-08-25",
  "time": "09:00"
}
```

**Note:** `slot_id` in the slot object is `"EXTERNAL_SLOT"` as a placeholder because the external Appointment Agent response does not return a `slot_id`. This is a confirmed CONTRACT GAP documented in `appointment/adapter.py`.

### External payload sent (recommendation_id NEVER forwarded)

```json
{
  "actor": "PATIENT",
  "patient_id": "patient_001",
  "request": {
    "intent": "BOOK_APPOINTMENT",
    "specialty": null
  },
  "patient_context": {
    "location": {"latitude": 30.2672, "longitude": -97.7431}
  }
}
```

---

## 16. Reschedule/Cancellation

### Reschedule Input

**Workflow A** (specific slot):
```json
{
  "patient_id": "patient_001",
  "appointment_id": "APT-001",
  "new_slot_id": "slot_002"
}
```

**Workflow B** (preference-based):
```json
{
  "patient_id": "patient_001",
  "appointment_id": "APT-001",
  "preferred_date": "2026-08-30",
  "preferred_time": "morning"
}
```

`recommendation_id` is optional (30-min TTL may have expired by reschedule time).

### Cancel Input

```json
{
  "patient_id": "patient_001",
  "appointment_id": "APT-001"
}
```

### Status lookup

```
GET /appointments/{appointment_id}?patient_id=patient_001
```

---

## 17. Error Outputs

### HTTP 400 — Missing primary_symptom_category

Raised by `routes.py` catching `ValueError` from `navigation_graph.invoke()`.
```json
{"detail": "Missing primary_symptom_category"}
```

### HTTP 422 — Geocoding failure

```json
{"detail": "Location could not be resolved: InvalidLocationError: No geocoding results found for address: 'ZZZZ INVALID'..."}
```

### HTTP 404 — Unknown recommendation

```json
{"detail": "Unknown or expired recommendation_id: rec_doesnotexist000000"}
```

### HTTP 404 — Provider not in recommendation

```json
{"detail": "Provider 'provider:not:found' is not part of recommendation 'rec_...'"}
```

### HTTP 502 — External Appointment Agent error

```json
{"detail": "Appointment Agent error: <exception message>"}
```

### Pydantic validation error (HTTP 422)

If `PatientLocation` has no coords and no address:
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": [],
      "msg": "Value error, PatientLocation requires either (latitude + longitude) or a non-empty address string.",
      "input": {...}
    }
  ]
}
```

---

## 18. Test Matrix

All tests use mocked external calls. **ACTUAL TESTED** results from running `pytest tests/ -v`.

| Test path | Input summary | Expected destination | Rule ID | Result |
|---|---|---|---|---|
| A — Default/Fallback | `unknown_xyz` symptom | PCP | FALLBACK-999 | **PASS** (ACTUAL TESTED) |
| B — PCP | `chronic_disease_flareup`, stable, CCI=2 | PCP | PCP-001-FLAREUP | **PASS** (ACTUAL TESTED) |
| C — Urgent Care | `minor_infection`, worsening, pain=6 | URGENT_CARE | UC-001-INFECTION | **PASS** (ACTUAL TESTED) |
| D — Specialist/Ortho | `back_pain`, gradual, worsening, ED≥4 | SPECIALIST/ORTHOPEDICS | SPEC-003-ORTHO | **PASS** (ACTUAL TESTED) |
| E — Pulmonology | `mild_breathing_difficulty`, COPD, chronic≥3 | SPECIALIST/PULMONOLOGY | SPEC-002-PULM | **PASS** (ACTUAL TESTED) |
| F — Cardiology | No routing rule exists | NOT IMPLEMENTED (OSM tags exist, no rule) | — | NOT IMPLEMENTED |
| G — Dentistry | `dental_pain` | DENTISTRY | SPEC-004-DENTAL | **PASS** (ACTUAL TESTED) |
| H — Telehealth | `mild_general_symptom`, improving, pain=2 | TELEHEALTH | TELE-003-GENERAL | **PASS** (ACTUAL TESTED) |
| I — Invalid location | Address not in Nominatim | HTTP 422 | — | **PASS** (ACTUAL TESTED) |
| J — Missing required input | No `primary_symptom_category` | HTTP 400/422 | — | **PASS** (ACTUAL TESTED) |
| K — Invalid address | `"ZZZZ INVALID"` address | HTTP 422 geocoding error | — | **PASS** (ACTUAL TESTED) |
| L — Address input | `"Austin, TX 78701"` | Depends on patient | Works (ACTUAL TESTED — Script 4) | **PASS** |
| M — Provider not in recommendation | Wrong provider_id for availability | HTTP 404 | — | **PASS** (ACTUAL TESTED) |
| N — Expired/unknown recommendation | Wrong recommendation_id | HTTP 404 | — | **PASS** (ACTUAL TESTED) |

**Full suite result (ACTUAL TESTED):** `325 passed, 0 failed, 1 warning` in 10.16s.
