# Alternate Care Navigation Agent — Project Documentation

## 1. Purpose and scope

The Alternate Care Navigation Agent routes non-emergency patients to the most appropriate care destination and finds nearby providers. It operates on patients that an upstream ED-avoidance model has already classified as `avoidable_ed == 1` and that carry no active red-flag symptom. Red-flag detection and ED triage are explicitly **out of scope** — see `scope_note` in `rules/care_destination_rules.yaml`.

The agent answers two questions in sequence:

- **WHAT** care does this patient need? → deterministic rule engine
- **WHERE** is suitable care available nearby? → OpenStreetMap provider discovery

It then adds a plain-language explanation via Gemini (the only LLM call), and stores the result so the downstream appointment workflow can proceed safely.

---

## 2. End-to-end flow

```
1. Caller POSTs /navigate
   { "patient": { ... }, "location": { ... } }
           │
           ▼
2. validate_input_node
   Checks that primary_symptom_category is present.
           │
           ▼
3. classify_node  ← Agent 1: AlternateCareAgent
   CareClassifier evaluates the priority-sorted rule list.
   First matching rule wins.
   Produces CareDecision { rule_id, destination, specialty, status, explanation }
           │
           ├── destination == TELEHEALTH → skip rank_node
           │
           ▼ (all other destinations)
4. rank_node  ← Agent 2: RankingAgent
   a. resolve_location() — geocodes address to lat/lon if needed (Nominatim)
   b. find_nearby_providers() — Overpass API query filtered by destination/specialty
   c. rank_providers() — Haversine distance + optional PCP continuity bonus
   Produces List[ProviderCandidate], resolved PatientLocation
           │
           ▼
5. explain_node  ← Gemini via LangChain
   explain_decision(CareDecision) → patient-facing sentence
   LLM failure is caught; the graph still returns a valid result.
           │
           ▼
6. Route checks state["errors"] for geocoding failures → HTTP 422
7. RecommendationStore.create() stores (Recommendation, PatientLocation)
8. /navigate returns Recommendation { recommendation_id, decision, top_providers }
           │
           (patient views providers, picks one)
           │
           ▼
9. Caller POSTs /appointments/availability
   Validated against stored recommendation.
   care_type and specialty derived from stored CareDecision (not from caller).
           │
           ▼
10. Caller POSTs /appointments/book
    Provider validated as belonging to the stored recommendation.
    Handed off to the external Shared Appointment Agent.
```

---

## 3. LangGraph architecture

The pipeline is implemented as a LangGraph `StateGraph` in `orchestrator/graph.py`. All nodes read from and write to a shared `NavigationState` TypedDict.

### State schema (`orchestrator/state.py`)

| Key | Type | Written by |
|---|---|---|
| `patient` | `PatientFeatures` | Caller (input) |
| `location` | `PatientLocation` | Caller (input); updated by `rank_node` after geocoding |
| `decision` | `CareDecision` | `classify_node` |
| `ranked_providers` | `List[ProviderCandidate]` | `rank_node` |
| `patient_facing_explanation` | `Optional[str]` | `explain_node` |
| `errors` | `List[str]` | Any node (append-only error channel) |

### Nodes

| Node | Function | What it does |
|---|---|---|
| `validate_input_node` | `orchestrator/graph.py` | Checks `primary_symptom_category` is non-empty. Appends to `errors` if not. |
| `classify_node` | Wraps `AlternateCareAgent.decide()` | Runs the deterministic rule engine. Produces `CareDecision`. |
| `rank_node` | Wraps `RankingAgent.rank()` | Geocodes if needed, queries Overpass, scores by distance. Catches all exceptions into `errors`. |
| `explain_node` | Calls `explain_decision()` (Gemini) | Produces a patient-facing string. LLM failures caught; returns `None` on failure. |

### Edges

```
validate_input → classify
classify → rank         (PCP, URGENT_CARE, SPECIALIST, DENTISTRY)
classify → explain      (TELEHEALTH only — no physical search)
rank → explain
explain → END
```

The conditional edge after `classify` is the only branch. TELEHEALTH bypasses `rank_node` entirely, so no Overpass query or geocoding is attempted for virtual-care decisions.

---

## 4. Rule engine

### Loading (`engine/rule_loader.py`)

`load_rules()` reads `rules/care_destination_rules.yaml`, validates every rule has required keys and a known destination, then returns the rules sorted by `priority` descending. Ties preserve YAML file order (stable sort). The `FALLBACK-999` rule (priority 0, `conditions: all: []`) always matches and is the final safety net.

### Condition evaluation (`engine/condition_evaluator.py`)

`evaluate_conditions(conditions, patient_dict)` handles two shapes:

- `all: [...]` — all conditions must be true
- `any: [...]` — at least one condition must be true

Each condition is `{ feature, operator, value }`. Supported operators: `equals`, `in`, `gte`, `lte`. Unknown operators raise `UnknownOperatorError`. `TypeError` (e.g. `None >= int`) returns `False` gracefully.

### Classification (`engine/care_classifier.py`)

`CareClassifier.classify(patient)` iterates the pre-sorted rules and returns a `CareDecision` for the first matching rule. Raises `RuntimeError` if even `FALLBACK-999` fails to match (unreachable in practice).

**Design note:** Classification and specialty routing are fused into one pass because the rule file already sets both `destination` and `specialty` together in each rule. Splitting into two passes would re-implement the same first-match-wins list twice and risk the two passes disagreeing.

---

## 5. Destination and specialty taxonomy

### Destinations (`models/schemas.py`)

```
Destination = Literal["PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH", "DENTISTRY"]
```

| Destination | Meaning | Provider search |
|---|---|---|
| `PCP` | Primary Care Physician | Overpass: `amenity=doctors`, `healthcare=doctor` |
| `URGENT_CARE` | Same-day urgent care clinic | Overpass: `healthcare=urgent_care`, `amenity=clinic` |
| `SPECIALIST` | Specialist referral | Overpass: specialty-specific tag + `amenity=doctors` fallback |
| `TELEHEALTH` | Virtual visit | No provider search — skip `rank_node` |
| `DENTISTRY` | Dental care | Overpass: `amenity=dentist` |

### SPECIALIST vs DENTISTRY

`DENTISTRY` is a **first-class destination**, not a sub-specialty under `SPECIALIST`. It maps directly to `["amenity"="dentist"]` in `location/osm_tag_map.py` with no specialty field required.

`SPECIALIST` requires a `specialty` value (e.g. `PULMONOLOGY`, `ORTHOPEDICS`) which is set by the matching rule. The OSM query for a specialist first attempts a specialty-specific tag (`healthcare:speciality=pulmonology`) and falls back to the generic `amenity=doctors` to cover areas where OSM tagging is sparse.

### Active specialties

`PULMONOLOGY`, `ORTHOPEDICS`, `DERMATOLOGY`, `UROLOGY`, `GYNECOLOGY`, `GASTROENTEROLOGY`, `CHRONIC_DISEASE_MANAGEMENT_REVIEW`, `CARDIOLOGY`, `NEPHROLOGY`, `ENDOCRINOLOGY`, `INFECTIOUS_DISEASE`, `ONCOLOGY`.

To add a new specialty: add the OSM tag mapping to `location/osm_tag_map.py` and add a routing rule to `rules/care_destination_rules.yaml`.

---

## 6. Location handling

### `PatientLocation` (`models/schemas.py`)

Accepts three forms:

| Form | Example |
|---|---|
| Coordinates | `{"latitude": 37.7749, "longitude": -122.4194}` |
| Address string | `{"address": "123 Main St, Springfield, IL 62701"}` |
| ZIP code | `{"address": "94102"}` |
| City/state | `{"address": "Boston, MA"}` |

At least one of `(latitude + longitude)` or `address` must be supplied (enforced by `model_validator`). When both are supplied, coordinates take precedence and no geocoding is performed.

### Geocoding (`location/geocoder.py`)

`resolve_location(location)` is the single geocoding call-site. It is a no-op when coordinates are already present. For address-only input it calls `geocode(address)` which queries Nominatim (OpenStreetMap geocoding service, free, no API key).

The query is restricted to `countrycodes=us`. A `User-Agent` header is sent as required by Nominatim's fair-use policy.

**Exception hierarchy:**

```
GeocodingError (RuntimeError)
├── InvalidLocationError      — address not found (zero results)
└── GeocodingNetworkError     — network or HTTP error
    └── GeocodingRateLimitError  — HTTP 429
```

### API error boundary

When geocoding fails, `rank_node` catches the exception and appends `"rank_node failed: <ExceptionType>: <message>"` to `state["errors"]`. The route handler checks `state["errors"]` after the graph completes and raises `HTTP 422` with a structured `detail` message before storing any recommendation. This ensures the caller receives a clear error rather than a silent HTTP 200 with no providers.

---

## 7. Provider discovery (`location/provider_discovery.py`)

`find_nearby_providers(location, destination, specialty)`:

1. Returns `[]` immediately for `TELEHEALTH` (no network call).
2. Raises `ValueError` if `location.latitude` or `location.longitude` is `None` (geocoding must happen first).
3. Calls `tags_for(destination, specialty)` in `location/osm_tag_map.py` to get Overpass tag filters.
4. Builds an Overpass QL query covering both `node` and `way` elements within `radius_m` of the patient.
5. POSTs to the Overpass API endpoint (configurable via `OVERPASS_URL`).
6. Parses elements, filters out unnamed nodes, and deduplicates node/way pairs representing the same physical facility using `(name, round(lat,3), round(lon,3))` as the dedup key.
7. Returns `List[ProviderCandidate]`.

**Deduplication detail:** OSM frequently returns both a `node` (entrance point) and a `way` (building polygon centroid) for the same clinic with slightly different coordinates. Rounding to 3 decimal places (~111m precision) collapses these into one result.

**Error hierarchy:**

```
ProviderDiscoveryError (RuntimeError)
└── ProviderDiscoveryNetworkError
    └── ProviderDiscoveryRateLimitError  — HTTP 429
```

Non-exception case: zero results returns an empty list, not an error. The caller (ranking) receives `[]` and the recommendation is created with `top_providers: []`.

---

## 8. Distance calculation and ranking (`location/ranking.py`)

`rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag, top_n=5)`:

- Computes `distance_km` for each candidate using the Haversine formula (great-circle distance on a sphere of radius 6371 km).
- Scores each candidate: `score = max(0, 1 − distance_km/25)` — score is 1.0 at 0 km and 0.0 at 25 km or beyond.
- Adds a `0.05` continuity bonus when `destination_type == "PCP"` and `has_pcp_flag == 1` (patient already has a PCP relationship).
- Returns the top `top_n` candidates sorted by score descending.

Gemini is not involved in distance calculation or provider selection.

---

## 9. Gemini's exact role (`engine/explainer.py`)

`explain_decision(decision: CareDecision) → str` is the **only** LLM call in the system.

- Model: `gemini-1.5-flash` via `langchain_google_genai.ChatGoogleGenerativeAI`
- Temperature: 0.3
- Max tokens: 200
- The chain is lazily initialised — importing the module never triggers authentication or a network call.
- Input to the LLM: `destination`, `specialty`, `status`, and the rule's `explanation` text from the YAML.
- The LLM produces a 2–3 sentence patient-facing summary. It does **not** determine the destination, select providers, or calculate distances.
- If the LLM call fails for any reason, `explain_node` catches the exception, appends to `state["errors"]`, and sets `patient_facing_explanation = None`. The graph still returns a complete, usable `Recommendation`.

---

## 10. Recommendation storage (`api/recommendation_store.py`)

`RecommendationStore` is an in-memory, thread-safe store with a 30-minute TTL.

- `create(recommendation, patient_location)` — generates a `rec_<token>` ID, stamps it on the `Recommendation`, stores both alongside a TTL timestamp.
- `require(recommendation_id)` — returns the recommendation or raises `KeyError` (used before appointment operations to verify the recommendation exists and hasn't expired).
- `require_provider(recommendation_id, provider_id)` — validates that the provider belongs to the given recommendation. Prevents callers from booking arbitrary providers.
- `get_patient_location(recommendation_id)` — returns the stored `PatientLocation` (with resolved coordinates) for forwarding to the external Appointment Agent.

Entries are cleaned up lazily on every read/write operation. No background thread is needed.

---

## 11. Appointment workflow

The appointment workflow is handled by two layers:

**`appointment/client.py` (`AppointmentAgentClient`)** — thin HTTP client. Makes the actual HTTP calls to the external Shared Appointment Agent. Uses `appointment/adapter.py` to serialise/deserialise.

**`appointment/agent.py` (`AppointmentService`)** — service layer between `api/routes.py` and the client. Derives `care_type` and `specialty` from the stored `CareDecision`; never trusts these values from the caller.

**`appointment/adapter.py` (`SharedAppointmentAdapter`)** — stateless translation layer. Converts internal models to/from the external HTTP contract. `recommendation_id` is **never** forwarded to the external service.

### External request envelope

```json
{
  "actor": "PATIENT",
  "patient_id": "...",
  "request": {
    "intent": "CHECK_AVAILABILITY | BOOK_APPOINTMENT | RESCHEDULE_APPOINTMENT | CANCEL_APPOINTMENT",
    "specialty": "...",
    "preferred_date": "...",
    "preferred_time": "...",
    "date_range": "..."
  },
  "patient_context": {
    "location": { "latitude": ..., "longitude": ... },
    "preference": { "language": "..." }
  }
}
```

### Contract gaps (documented in source)

- `provider_id` placement in external requests is unconfirmed — omitted from outbound payload.
- `slot_id` is not in the external booking request spec — omitted.
- Status lookup endpoint (`GET /appointments/{id}`) contract is unconfirmed — assumes `?patient_id=` query param.

---

## 12. API request/response flow

### POST /navigate

```
Request:  { patient: PatientFeatures, location: PatientLocation }
Response: Recommendation { recommendation_id, decision: CareDecision, top_providers: List[ProviderCandidate] }
Errors:   400 — missing primary_symptom_category
          422 — location cannot be geocoded
```

### POST /appointments/availability

```
Request:  { recommendation_id, provider_id, date_range?, patient_id? }
Response: { available_slots: [], provider_id, care_type, specialty }
Errors:   404 — unknown/expired recommendation_id or provider not in recommendation
```

`care_type` and `specialty` are derived from the stored `CareDecision`. The caller cannot supply or override them.

### POST /appointments/book

```
Request:  { patient_id, recommendation_id, provider_id, slot_id }
Response: AppointmentConfirmation { appointment_id, patient_id, status, provider_id, ... }
Errors:   404 — unknown/expired recommendation_id or provider not in recommendation
```

### POST /appointments/reschedule

```
Request (Workflow A): { patient_id, appointment_id, new_slot_id }
Request (Workflow B): { patient_id, appointment_id, preferred_date?, preferred_time? }
Response: AppointmentConfirmation
Errors:   502 — external Appointment Agent error
```

`recommendation_id` is not required — the recommendation may have expired by the time a patient reschedules.

### POST /appointments/cancel

```
Request:  { patient_id, appointment_id }
Response: AppointmentStatusResponse { appointment_id, patient_id, status, ... }
Errors:   502 — external Appointment Agent error
```

### GET /appointments/{appointment_id}

```
Query params: patient_id (optional)
Response: AppointmentStatusResponse
Errors:   502 — external Appointment Agent error
```

---

## 13. Data models

All core models are in `models/schemas.py`. Appointment-specific models are in `appointment/schemas.py`.

### Core models

**`PatientFeatures`** — clinical and demographic features used by the rule engine. `extra="allow"` so callers can pass additional fields without errors.

**`PatientLocation`** — patient location. Accepts lat/lon, address, or both. `model_validator` enforces that at least one is present.

**`CareDecision`** — the output of the rule engine: `rule_id`, `priority`, `destination`, `specialty` (None for non-specialist), `status`, `explanation`.

**`ProviderCandidate`** — a single discovered provider: `provider_id` (format `osm:node:ID` or `osm:way:ID`), `name`, `destination_type`, `specialty`, `latitude`, `longitude`, `address` (may be null), `distance_km`, `score`, `source` (`"osm"`).

**`Recommendation`** — the complete navigation result: `recommendation_id`, `decision`, `top_providers`.

**`AppointmentSlot`** — `slot_id`, `provider_id`, `start_time`, `end_time` (all plain strings).

---

## 14. External services

| Service | Module | Used for | API key | Rate limit |
|---|---|---|---|---|
| Google Gemini (`gemini-1.5-flash`) | `engine/explainer.py` | Plain-language explanation only | `GOOGLE_API_KEY` | Free tier |
| Overpass API (OSM) | `location/provider_discovery.py` | Healthcare facility search | None | Fair-use (~1 complex query/s) |
| Nominatim (OSM) | `location/geocoder.py` | Address/ZIP → lat/lon geocoding | None | 1 req/s |
| Shared Appointment Agent | `appointment/client.py` | Availability, booking, reschedule, cancel | URL only | Depends on teammate |

---

## 15. Configuration (`config/settings.py`)

All settings are read from environment variables with safe defaults. The module is imported by `location/geocoder.py`, `location/provider_discovery.py`, and `appointment/client.py`.

| Variable | Default |
|---|---|
| `GOOGLE_API_KEY` | (none — required at runtime) |
| `APPOINTMENT_AGENT_BASE_URL` | `http://localhost:8001` |
| `OVERPASS_URL` | `https://overpass-api.de/api/interpreter` |
| `DEFAULT_SEARCH_RADIUS_KM` | `15.0` |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` |
| `NOMINATIM_USER_AGENT` | `AlternateCareNavigationAgent/1.0 (development; ...)` |

---

## 16. Test structure

All tests live in `tests/`. No real network calls are made — all external boundaries are mocked.

| File | What it tests |
|---|---|
| `test_rule_engine.py` | `CareClassifier.classify()` against 10 patient cases from `sample_patients.json`. Verifies rule_id for every case. No mocking needed — purely deterministic. |
| `test_provider_discovery.py` | `find_nearby_providers()`: OSM node/way deduplication, DENTISTRY destination, PULMONOLOGY/CARDIOLOGY specialty mappings. Mocks `requests.post`. |
| `test_location_maps.py` | `PatientLocation` schema (address forms, validator), `geocode()` / `resolve_location()` (all error paths), `find_nearby_providers()` error handling, `RankingAgent` geocoding wiring, config settings, and the `/navigate` → HTTP 422 boundary. All mocked. |
| `test_appointment_flow.py` | Full pipeline via `TestClient`: `/navigate` → store → `/appointments/availability` → `/appointments/book`. Exercises all 6 destinations. Mocks Overpass and Gemini; uses the real `RecommendationStore` and `CareClassifier`. |
| `test_appointment_agent.py` | `AppointmentService` unit tests and all route handlers with mocked client methods. All 4 care types × all 4 appointment intents. |
| `test_appointment_schemas.py` | Pydantic schema validation for all appointment models. |
| `test_shared_appointment_contract.py` | `SharedAppointmentAdapter` wire payload shape — verifies `recommendation_id` is never forwarded externally. |

**Running the suite:**

```bash
python -m pytest tests/ -q          # 325 tests, ~3 seconds
python -m pytest tests/ -v          # verbose, one line per test
```
