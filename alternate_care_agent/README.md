# Alternate Care Navigation Agent

Scope: patients already classified `avoidable_ed == 1` by the team's upstream ED-avoidance model. This agent does **not** perform red-flag or ED triage — that is handled upstream before any request reaches this service.

---

## What it does

Given a patient's clinical features and location, the agent:

1. **Decides** which care destination is appropriate — PCP, Urgent Care, Specialist (with specialty), Telehealth, or Dentistry — using a deterministic rule engine.
2. **Finds** nearby facilities for physical-care destinations by querying OpenStreetMap via the Overpass API (free, no key required).
3. **Ranks** candidate providers by straight-line distance using the Haversine formula.
4. **Explains** the decision in plain language using Google Gemini (the only LLM call in the system).
5. **Returns** a structured `Recommendation` — destination, specialty, ranked providers, and a patient-facing explanation — stored server-side for the subsequent appointment workflow.

---

## Agent inventory

| # | Name | Type | Owner |
|---|---|----|---|
| 1 | **AlternateCareAgent** (`agents/classification_agent.py`) | Deterministic rule engine wrapped as a LangGraph node | This project |
| 2 | **RankingAgent** (`agents/ranking_agent.py`) | OSM/Overpass discovery + Haversine scoring, one LangGraph node | This project |
| — | **explain_node** (`engine/explainer.py`) | The **only** LLM step — Gemini via LangChain, turns the structured decision into a patient-facing sentence | This project |
| 3 | **Shared Appointment Agent** (`appointment/client.py`) | External HTTP service owned by another team; called **after** the graph finishes | Teammate's service |

Two internal agents + one LLM explanation step orchestrated by LangGraph, handing off to one external shared agent.

---

## High-level architecture

```
PatientFeatures + PatientLocation
            │
            ▼
  ┌─────────────────────────────┐
  │      LangGraph pipeline      │  orchestrator/graph.py
  │                             │
  │  validate_input_node        │  checks required fields
  │          │                  │
  │          ▼                  │
  │  classify_node              │  Agent 1: AlternateCareAgent
  │  (AlternateCareAgent)       │  deterministic rule engine
  │          │                  │  → WHAT care is needed
  │   TELEHEALTH ──┐            │
  │  (skip rank)   │            │
  │          ▼     │            │
  │  rank_node     │            │  Agent 2: RankingAgent
  │  (RankingAgent)│            │  geocode → Overpass → Haversine
  │          │     │            │  → WHERE care is available
  │          ▼     │            │
  │  explain_node ◄┘            │  Gemini (LangChain)
  │  (LLM)                      │  → plain-language explanation only
  └─────────────────────────────┘
            │
            ▼
      Recommendation
  (stored, returned via POST /navigate)
            │
     patient picks a provider
            │
            ▼
  ┌─────────────────────────────┐
  │  Shared Appointment Agent    │  external HTTP service
  │  (teammate's service)        │  /appointments/availability
  └─────────────────────────────┘  /appointments/book
```

**Key design principle:** Routing (WHAT) and location discovery (WHERE) are intentionally separate. Gemini is never asked to find providers, calculate distances, or select care destinations.

---

## Installation

```bash
pip install -r requirements.txt          # production dependencies
pip install -r requirements-dev.txt      # adds pytest for testing
```

Python 3.11+ recommended.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes (for LLM) | — | Google AI Studio API key for Gemini. Free tier available at https://aistudio.google.com/apikey |
| `APPOINTMENT_AGENT_BASE_URL` | Yes (for booking) | `http://localhost:8001` | Base URL of the shared Appointment Agent service |
| `OVERPASS_URL` | No | `https://overpass-api.de/api/interpreter` | Overpass API endpoint; override to self-host |
| `NOMINATIM_URL` | No | `https://nominatim.openstreetmap.org/search` | Nominatim geocoding endpoint; override to self-host |
| `NOMINATIM_USER_AGENT` | No | `AlternateCareNavigationAgent/1.0 (development; ...)` | User-Agent header sent to Nominatim (required by their policy) |
| `DEFAULT_SEARCH_RADIUS_KM` | No | `15.0` | Default provider search radius in kilometres |

Copy `.env.example` to `.env` and fill in values before starting.

---

## Starting the API

```bash
# Set your API key (or place it in .env)
export GOOGLE_API_KEY=your_key_here

# Start with auto-reload (development)
uvicorn main:app --reload

# Start on a specific port
uvicorn main:app --host 0.0.0.0 --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs` once the server is running.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/navigate` | Run the full pipeline: classify → discover → rank → explain. Returns a `Recommendation` with a `recommendation_id`. |
| `POST` | `/appointments/availability` | Check available slots for a provider from an existing recommendation. |
| `POST` | `/appointments/book` | Book an appointment. Provider must belong to the stored recommendation. |
| `POST` | `/appointments/reschedule` | Reschedule an existing appointment (recommendation not required). |
| `POST` | `/appointments/cancel` | Cancel an existing appointment. |
| `GET` | `/appointments/{appointment_id}` | Retrieve appointment status. |

---

## Example: POST /navigate

**Request**

```json
{
  "patient": {
    "primary_symptom_category": "minor_infection",
    "symptom_trend": "worsening",
    "pain_level_self_reported": 6
  },
  "location": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "radius_km": 15.0
  }
}
```

Location can also be supplied as a U.S. address string instead of coordinates:

```json
{
  "patient": { "primary_symptom_category": "minor_infection" },
  "location": { "address": "94102" }
}
```

Supported address forms: street address, city/state, ZIP code.

**Response**

```json
{
  "recommendation_id": "rec_aBcDeFgHiJkL",
  "decision": {
    "rule_id": "UC-001-INFECTION",
    "priority": 30,
    "destination": "URGENT_CARE",
    "specialty": null,
    "status": "DOCUMENT_SUPPORTED",
    "explanation": "Same-day evaluation appropriate for a worsening minor infection..."
  },
  "top_providers": [
    {
      "provider_id": "osm:node:123456",
      "name": "City Urgent Care",
      "destination_type": "URGENT_CARE",
      "specialty": null,
      "latitude": 37.7812,
      "longitude": -122.4153,
      "address": "500 Market St",
      "distance_km": 0.74,
      "score": 0.97,
      "source": "osm"
    }
  ]
}
```

Returns **HTTP 422** if the location address cannot be geocoded (invalid or unrecognised address).

---

## Running tests

```bash
# Full suite (325 tests, no real network calls)
python -m pytest tests/ -q

# Focused: rule engine only
python -m pytest tests/test_rule_engine.py -v

# Focused: location and maps layer
python -m pytest tests/test_location_maps.py tests/test_provider_discovery.py -v
```

All tests mock external network calls (Overpass, Nominatim, Gemini, Appointment Agent). No API keys or internet access are required to run the test suite.

---

## External services

| Service | Used for | Cost | Auth |
|---|---|---|---|
| **Google Gemini** (`gemini-1.5-flash` via LangChain) | Patient-facing explanation only | Free tier available | `GOOGLE_API_KEY` |
| **Overpass API** (OpenStreetMap) | Finding nearby healthcare facilities | Free, fair-use | None |
| **Nominatim** (OpenStreetMap) | Geocoding address/ZIP input to coordinates | Free, fair-use (1 req/s) | None |
| **Shared Appointment Agent** | Availability lookup, booking, rescheduling, cancellation | Internal service | URL only |

Gemini is used **only** to convert the already-determined routing decision into a plain-language sentence. It does not select destinations, find providers, or calculate distances.

---

## Known issues / next steps

- `SAFETY-000` is defined in the YAML as `destination: URGENT_CARE` but the rule matrix document describes it as `ESCALATE_TO_ED`. Resolve before production activation — both are tagged `RECOMMENDED_REQUIRES_VALIDATION`.
- Several rules are tagged `RECOMMENDED_REQUIRES_VALIDATION` and require clinical sign-off before production use. See `rules/RULE_MATRIX_AND_VALIDATION.md`.
- Nominatim's public instance enforces a 1 req/s rate limit. Set `NOMINATIM_URL` to a self-hosted instance under concurrent load.
- The `ProviderCandidate.address` field is populated from OSM tags (`addr:full` / `addr:street`) which are frequently absent in OSM data. Provider addresses will often be `null`.
