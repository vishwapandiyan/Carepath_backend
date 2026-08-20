# File and Folder Guide

Every relevant source, test, and configuration file in the repository. Entries are grouped by folder. File purposes are derived from the actual source, not inferred.

---

## Root

### `main.py`
- **Purpose:** uvicorn entry point.
- **Contains:** `from api.routes import app` — a single re-export.
- **How it participates:** `uvicorn main:app --reload` resolves `app` through this file.
- **Interacts with:** `api/routes.py`

### `requirements.txt`
- **Purpose:** Production Python dependencies with pinned versions.
- **Contains:** `fastapi`, `uvicorn[standard]`, `pydantic`, `PyYAML`, `requests`, `langchain`, `langchain-core`, `langchain-google-genai`, `langgraph`.
- **How it participates:** Installed before running the server.
- **Interacts with:** All source modules.

### `requirements-dev.txt`
- **Purpose:** Development and test dependencies.
- **Contains:** `-r requirements.txt` plus `pytest`.
- **How it participates:** Installed in development environments for testing.
- **Interacts with:** `tests/`

### `README.md`
- **Purpose:** Project overview for first-time readers.
- **Contains:** Purpose, agent inventory, architecture diagram, installation, environment variables, API endpoints, example request/response, running tests, known issues.

### `.env.example`
- **Purpose:** Template for creating a local `.env` file.
- **Contains:** All required/optional environment variable names with placeholder values and comments. No real secrets.

### `.gitignore`
- **Purpose:** Prevents secrets, compiled files, and IDE artifacts from being committed.
- **Contains:** `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, and other standard Python/IDE ignores.

---

## `config/`

### `config/settings.py`
- **Purpose:** Centralised configuration from environment variables.
- **Contains:** Six settings: `APPOINTMENT_AGENT_BASE_URL`, `OVERPASS_URL`, `DEFAULT_SEARCH_RADIUS_KM`, `NOMINATIM_URL`, `NOMINATIM_USER_AGENT`. Each reads from `os.environ` with a safe default.
- **How it participates:** Imported by `location/geocoder.py`, `location/provider_discovery.py`, and `appointment/client.py`. Changing an env var and restarting the process changes the endpoint used by those modules.
- **Interacts with:** `location/geocoder.py`, `location/provider_discovery.py`, `appointment/client.py`

### `config/__init__.py`
- **Purpose:** Makes `config/` a Python package.
- **Contains:** Empty.

---

## `models/`

### `models/schemas.py`
- **Purpose:** Shared Pydantic models used across the entire system.
- **Contains:**
  - `Destination` — `Literal` type for the five valid care destinations.
  - `PatientFeatures` — clinical and demographic fields consumed by the rule engine. `extra="allow"` for forward compatibility.
  - `PatientLocation` — patient location (lat/lon or address or both). `model_validator` enforces at least one is present.
  - `CareDecision` — output of the rule engine.
  - `ProviderCandidate` — a single discovered/ranked provider.
  - `Recommendation` — the complete navigation result stored in `RecommendationStore`.
  - `AppointmentSlot`, `AppointmentAvailabilityRequest`, `BookingRequest`, `BookingConfirmation` — appointment workflow types used by routes and the client.
- **How it participates:** Imported by nearly every module. This is the type contract for the whole pipeline.
- **Interacts with:** `engine/`, `location/`, `agents/`, `orchestrator/`, `api/`, `appointment/`

---

## `rules/`

### `rules/care_destination_rules.yaml`
- **Purpose:** The executable routing rule set. This is the single source of truth for which patient features map to which care destination.
- **Contains:** 18 rules, each with `rule_id`, `priority`, `destination`, `specialty` (null for non-specialist), `conditions` (all/any blocks), `explanation`, `status`. Rules are evaluated highest-priority-first; first match wins.
- **How it participates:** Loaded by `engine/rule_loader.py` at classifier construction time.
- **Interacts with:** `engine/rule_loader.py`, `engine/care_classifier.py`

### `rules/routing_rule_matrix.md`, `rules/RULE_MATRIX_AND_VALIDATION.md`
- **Purpose:** Human-readable documentation of the rule matrix, clinical validation notes, and known gaps.
- **Contains:** Decision matrix, known inconsistencies (e.g. SAFETY-000 destination discrepancy), feature gaps, validation status per rule.
- **How it participates:** Reference only — not loaded at runtime.

---

## `engine/`

### `engine/rule_loader.py`
- **Purpose:** Reads, validates, and sorts the routing rules.
- **Contains:** `load_rules(path)` — opens the YAML, validates required keys and destinations, sorts by priority descending. Raises `RuleFileError` on malformed input.
- **How it participates:** Called once by `CareClassifier.__init__()`. The sorted list is held in memory for the lifetime of the process.
- **Interacts with:** `rules/care_destination_rules.yaml`, `engine/care_classifier.py`

### `engine/condition_evaluator.py`
- **Purpose:** Evaluates a single rule's `conditions` block against a patient feature dict.
- **Contains:** `evaluate_conditions(conditions, patient_dict)` — dispatches on `all`/`any`; evaluates each `{feature, operator, value}` condition using `equals`, `in`, `gte`, or `lte`. Raises `UnknownOperatorError` on unknown operators; returns `False` on `TypeError` (e.g. `None >= int`).
- **How it participates:** Called by `CareClassifier.classify()` for every rule until a match is found.
- **Interacts with:** `engine/care_classifier.py`

### `engine/care_classifier.py`
- **Purpose:** Fused care classification and specialty routing in one pass.
- **Contains:** `CareClassifier` class with `classify(patient)` method. Iterates pre-sorted rules, calls `evaluate_conditions()`, returns the first matching `CareDecision`.
- **How it participates:** Wrapped by `AlternateCareAgent.decide()`. Called from `classify_node` in the graph.
- **Interacts with:** `engine/rule_loader.py`, `engine/condition_evaluator.py`, `models/schemas.py`

### `engine/explainer.py`
- **Purpose:** The only LLM-backed step. Converts a `CareDecision` into a patient-facing sentence.
- **Contains:** A `ChatPromptTemplate`, a lazy-initialised `ChatGoogleGenerativeAI` chain (model `gemini-1.5-flash`, temperature 0.3, max 200 tokens), and `explain_decision(decision) → str`. Requires `GOOGLE_API_KEY` at runtime.
- **How it participates:** Called by `explain_node` in the graph. Failures are caught by the graph; the rest of the result is returned without explanation.
- **Interacts with:** `models/schemas.py`, `orchestrator/graph.py`

### `engine/__init__.py`
- Empty.

---

## `location/`

### `location/osm_tag_map.py`
- **Purpose:** The only place that maps care destinations and specialties to OpenStreetMap Overpass tag filters.
- **Contains:** `DESTINATION_TAGS` (PCP, URGENT_CARE, DENTISTRY), `SPECIALTY_TAGS` (12 specialties), and `tags_for(destination, specialty)`. To add a new destination or specialty: edit only this file.
- **How it participates:** Called by `find_nearby_providers()` to build the Overpass query.
- **Interacts with:** `location/provider_discovery.py`

### `location/geocoder.py`
- **Purpose:** The only place that talks to a geocoding service.
- **Contains:** `geocode(address) → (lat, lon)` — queries Nominatim; `resolve_location(location) → PatientLocation` — no-op if coordinates present, otherwise geocodes. Public exception hierarchy: `GeocodingError`, `InvalidLocationError`, `GeocodingNetworkError`, `GeocodingRateLimitError`.
- **How it participates:** Called by `RankingAgent.rank()` when `PatientLocation` has no coordinates. The resolved location (with lat/lon) is written back to `NavigationState`.
- **Interacts with:** `config/settings.py`, `models/schemas.py`, `agents/ranking_agent.py`

### `location/provider_discovery.py`
- **Purpose:** Queries the Overpass API to find nearby healthcare facilities.
- **Contains:** `find_nearby_providers(location, destination, specialty) → List[ProviderCandidate]` — builds and POSTs the Overpass QL query, parses and deduplicates results. Returns `[]` for TELEHEALTH without a network call. Public exception hierarchy: `ProviderDiscoveryError`, `ProviderDiscoveryNetworkError`, `ProviderDiscoveryRateLimitError`.
- **How it participates:** Called by `RankingAgent.rank()` after geocoding resolves coordinates.
- **Interacts with:** `config/settings.py`, `location/osm_tag_map.py`, `models/schemas.py`

### `location/ranking.py`
- **Purpose:** Scores and sorts provider candidates by distance.
- **Contains:** `haversine_km(lat1, lon1, lat2, lon2)` and `rank_providers(patient_lat, patient_lon, candidates, has_pcp_flag, top_n=5)`. Score formula: `max(0, 1 − distance_km/25)` with an optional 0.05 PCP continuity bonus.
- **How it participates:** Called by `RankingAgent.rank()` after provider discovery.
- **Interacts with:** `models/schemas.py`, `agents/ranking_agent.py`

### `location/__init__.py`
- Empty.

---

## `agents/`

### `agents/classification_agent.py`
- **Purpose:** Named wrapper for the rule engine, representing Agent 1 in the pipeline.
- **Contains:** `AlternateCareAgent` class with `decide(patient) → CareDecision`. Instantiates `CareClassifier` in `__init__`.
- **How it participates:** Wrapped as `classify_node` in `orchestrator/graph.py`. Exposes a stable public contract (`decide`) so the graph is insulated from classifier internals.
- **Interacts with:** `engine/care_classifier.py`, `orchestrator/graph.py`

### `agents/ranking_agent.py`
- **Purpose:** Named wrapper for geocoding + provider discovery + scoring, representing Agent 2.
- **Contains:** `RankingAgent` class with `rank(location, decision, has_pcp_flag) → (List[ProviderCandidate], PatientLocation)`. Calls `resolve_location()`, `find_nearby_providers()`, and `rank_providers()` in sequence.
- **How it participates:** Wrapped as `rank_node` in `orchestrator/graph.py`. Returns both the ranked list and the resolved location so `rank_node` can update `state["location"]`.
- **Interacts with:** `location/geocoder.py`, `location/provider_discovery.py`, `location/ranking.py`, `orchestrator/graph.py`

### `agents/appointment_agent.py`
- **Purpose:** Conceptual placeholder marking the Shared Appointment Agent as the third agent in the pipeline.
- **Contains:** `from appointment.client import AppointmentAgentClient  # noqa: F401` — a re-export only.
- **How it participates:** Not called directly; exists so `agents/` reads as the complete agent inventory.
- **Interacts with:** `appointment/client.py`

### `agents/__init__.py`
- Empty.

---

## `orchestrator/`

### `orchestrator/state.py`
- **Purpose:** Defines `NavigationState`, the shared state TypedDict threaded through every LangGraph node.
- **Contains:** Keys: `patient`, `location`, `decision`, `ranked_providers`, `patient_facing_explanation`, `errors`.
- **How it participates:** Imported by `orchestrator/graph.py` and by any node function that needs type hints.
- **Interacts with:** `orchestrator/graph.py`, `models/schemas.py`

### `orchestrator/graph.py`
- **Purpose:** Wires the LangGraph pipeline and exposes the compiled `navigation_graph` singleton.
- **Contains:** All four node functions (`validate_input_node`, `classify_node`, `rank_node`, `explain_node`), the conditional routing function `route_after_classify`, and `build_graph()` which compiles the `StateGraph`. `navigation_graph = build_graph()` is the module-level singleton invoked by `api/routes.py`.
- **How it participates:** `navigation_graph.invoke(state)` runs the full pipeline. The compiled graph is created once at import time.
- **Interacts with:** `orchestrator/state.py`, `agents/classification_agent.py`, `agents/ranking_agent.py`, `engine/explainer.py`, `api/routes.py`

### `orchestrator/__init__.py`
- Empty.

---

## `api/`

### `api/routes.py`
- **Purpose:** FastAPI application and all HTTP route handlers.
- **Contains:** The `app` FastAPI instance; six route handlers (`navigate`, `availability`, `book`, `reschedule`, `cancel`, `get_appointment_status`); module-level singletons `appointment_client` and `appointment_service`; the `_find_location_error()` helper that converts geocoding errors in `state["errors"]` into HTTP 422 responses.
- **How it participates:** `main.py` re-exports `app`. The `/navigate` handler invokes `navigation_graph`, checks for location errors, stores the recommendation, and returns it. The appointment handlers validate against `RecommendationStore` before delegating to `AppointmentService`.
- **Interacts with:** `orchestrator/graph.py`, `api/recommendation_store.py`, `appointment/agent.py`, `appointment/client.py`, `models/schemas.py`, `appointment/schemas.py`

### `api/recommendation_store.py`
- **Purpose:** In-memory server-side store binding `recommendation_id` to the trusted `Recommendation` and `PatientLocation`.
- **Contains:** `_StoredRecommendation` dataclass; `RecommendationStore` class with `create`, `get`, `require`, `get_patient_location`, `get_provider`, `require_provider` methods; module-level singleton `recommendation_store = RecommendationStore(ttl_minutes=30)`.
- **How it participates:** `api/routes.py` imports `recommendation_store` directly. Appointment route handlers call `require_provider()` to validate that a provider belongs to the given recommendation before forwarding to the external service.
- **Interacts with:** `api/routes.py`, `models/schemas.py`

### `api/__init__.py`
- Empty.

---

## `appointment/`

### `appointment/schemas.py`
- **Purpose:** Pydantic models for the appointment workflow.
- **Contains:** `AppointmentPatientContext`, `AppointmentPreferences`, `AppointmentWorkflowRequest`, `AppointmentIntent`, `AvailabilityWorkflowRequest`, `AvailabilityWorkflowResponse`, `BookingWorkflowRequest`, `AppointmentConfirmation`, `AppointmentStatusLiteral`, `RescheduleRequest`, `CancellationRequest`, `AppointmentStatusResponse`. Re-exports `Destination` and `AppointmentSlot` from `models/schemas.py` — no duplicate definitions.
- **How it participates:** Imported by `api/routes.py`, `appointment/agent.py`, `appointment/client.py`, and `appointment/adapter.py`.
- **Interacts with:** `models/schemas.py`, `api/routes.py`, `appointment/agent.py`, `appointment/client.py`

### `appointment/adapter.py`
- **Purpose:** Pure translation between internal Python models and the external Shared Appointment Agent HTTP contract.
- **Contains:** `SharedAppointmentAdapter` — stateless class with `build_*` (internal → external JSON) and `parse_*` (external JSON → internal models) static methods. `recommendation_id` is never forwarded. Documents all confirmed fields, assumptions, and contract gaps.
- **How it participates:** Called by `AppointmentAgentClient` for every outbound request and inbound response. No HTTP I/O here.
- **Interacts with:** `appointment/client.py`, `appointment/schemas.py`, `models/schemas.py`

### `appointment/client.py`
- **Purpose:** Thin HTTP client for the external Shared Appointment Agent.
- **Contains:** `AppointmentAgentClient` with `get_availability`, `book`, `cancel`, `cancel_appointment`, `reschedule`, `get_appointment` methods. All HTTP I/O uses `requests` with a 10-second timeout. All serialisation/deserialisation delegates to `SharedAppointmentAdapter`.
- **How it participates:** Instantiated as a module-level singleton in `api/routes.py` (`appointment_client`) and in `appointment/agent.py`.
- **Interacts with:** `appointment/adapter.py`, `config/settings.py`, `models/schemas.py`, `appointment/schemas.py`

### `appointment/agent.py`
- **Purpose:** Service layer between `api/routes.py` and `AppointmentAgentClient`.
- **Contains:** `AppointmentService` class with `check_availability`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `get_appointment_status` methods. Module-level singleton `appointment_service = AppointmentService()`.
- **How it participates:** Imported by `api/routes.py`. Derives `care_type` and `specialty` from the stored `CareDecision`; never trusts these from the caller.
- **Interacts with:** `appointment/client.py`, `appointment/schemas.py`, `models/schemas.py`

### `appointment/__init__.py`
- Empty.

---

## `tests/`

### `tests/sample_patients.json`
- **Purpose:** 10 deterministic patient test cases, one per routing rule branch.
- **Contains:** Array of `{patient: {...}, expected_rule_id: "..."}` objects.
- **How it participates:** Loaded by `test_rule_engine.py`.
- **Interacts with:** `tests/test_rule_engine.py`

### `tests/test_rule_engine.py`
- **Purpose:** Verifies every routing rule fires correctly on representative patient data.
- **Contains:** Parameterised tests loading `sample_patients.json`, asserting `rule_id` matches expected for each case.
- **Interacts with:** `engine/care_classifier.py`, `tests/sample_patients.json`

### `tests/test_provider_discovery.py`
- **Purpose:** Tests OSM node/way deduplication and destination/specialty→tag mapping.
- **Contains:** `TestProviderDeduplication`, `TestDentalOSMMapping`, `TestPulmonologyOSMMapping`, `TestCardiologyOSMMapping`. Mocks `location.provider_discovery.requests.post`.
- **Interacts with:** `location/provider_discovery.py`, `location/osm_tag_map.py`

### `tests/test_location_maps.py`
- **Purpose:** Comprehensive tests for the full location/maps layer and the `/navigate` error boundary.
- **Contains:** `TestPatientLocationSchema`, `TestGeocode`, `TestResolveLocation`, `TestProviderDiscoveryErrorHandling`, `TestRadiusHandling`, `TestRankingAgentGeocodingWiring`, `TestConfigSettings`, `TestNavigateLocationErrorBoundary`. All external calls mocked.
- **Interacts with:** `models/schemas.py`, `location/geocoder.py`, `location/provider_discovery.py`, `agents/ranking_agent.py`, `config/settings.py`, `api/routes.py`

### `tests/test_appointment_flow.py`
- **Purpose:** End-to-end integration tests via `TestClient` covering the full `/navigate` → store → appointment pipeline.
- **Contains:** 44 tests covering all 6 destinations, recommendation binding, care_type/specialty derivation, location threading, provider_name forwarding, and availability response structure. Uses real `RecommendationStore` and `CareClassifier`; mocks Overpass and Gemini.
- **Interacts with:** `api/routes.py`, `api/recommendation_store.py`, `orchestrator/graph.py`, `appointment/client.py`

### `tests/test_appointment_agent.py`
- **Purpose:** Unit tests for `AppointmentService` and all appointment route handlers.
- **Contains:** All 4 care types × all 4 appointment intents; missing field rejections; wire payload capture tests. Client methods mocked at the instance level.
- **Interacts with:** `api/routes.py`, `appointment/agent.py`, `appointment/client.py`

### `tests/test_appointment_schemas.py`
- **Purpose:** Pydantic validation tests for all appointment workflow models.
- **Contains:** Valid/invalid cases for every schema in `appointment/schemas.py`.
- **Interacts with:** `appointment/schemas.py`, `models/schemas.py`

### `tests/test_shared_appointment_contract.py`
- **Purpose:** Verifies the external wire contract — correct envelope shape and that `recommendation_id` is never forwarded.
- **Contains:** Adapter round-trip tests for all intents, 5 destination × 3 case coverage, payload inspection asserting internal fields are absent.
- **Interacts with:** `appointment/adapter.py`, `appointment/schemas.py`

---

## Files not part of the runtime

The following files in the project root are development/build artefacts from the incremental implementation process. They are not imported by or required by any production code or test:

`*.txt` capture files (`baseline.txt`, `stage1.txt`–`stage9.txt`, `hard_A.txt`–`hard_G.txt`, `test_9b_focused.txt`, etc.), `*.ps1` scripts, `*.bat` scripts, `run_pytest.py`, `run_pytest2.py`, `hello.ps1`, `envcheck.txt`, `versions.txt`, `_import_errors.txt`, and similar. These can be deleted without affecting the application.
