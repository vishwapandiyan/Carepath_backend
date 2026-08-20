"""
LangGraph orchestration wiring the 3 named agents together:

    1. AlternateCareAgent (agents/classification_agent.py) — "the main agent"
    2. RankingAgent       (agents/ranking_agent.py)
    3. Shared Appointment Agent (agents/appointment_agent.py) — external,
       NOT a node in this graph (see note at the bottom)

Node/agent count, stated plainly for your writeup:
- 2 internal agents live inside this LangGraph graph: classification + ranking.
- 1 LLM-backed step: explain_node (LangChain ChatGoogleGenerativeAI call) — this is
  the only node that "reasons" with an LLM; classify/rank/validate are
  deterministic rule- and data-lookups wrapped as nodes so they share state
  and support conditional routing.
- 1 external shared agent (Appointment) is invoked AFTER this graph
  finishes, once the patient picks a provider — it's a separate service
  your team shares, not a node this graph owns or calls automatically.

Graph shape:

    validate_input
          │
          ▼
    classify (AlternateCareAgent) ──(TELEHEALTH)──────┐
          │ (PCP/UC/SPECIALIST)                        │
          ▼                                            │
    rank (RankingAgent: discover+score internally)      │
          │                                            │
          └────────────────────┬───────────────────────┘
                                ▼
                          explain (LangChain LLM)
                                │
                                ▼
                               END

    ── (separate, outside this graph) ──
    patient picks a provider from ranked_providers
                                │
                                ▼
                   Shared Appointment Agent (HTTP)
                   /appointments/availability, /book
"""

from __future__ import annotations
from langgraph.graph import StateGraph, END

from orchestrator.state import NavigationState
from agents.classification_agent import AlternateCareAgent
from agents.ranking_agent import RankingAgent
from engine.explainer import explain_decision

_care_agent = AlternateCareAgent()
_ranking_agent = RankingAgent()


def validate_input_node(state: NavigationState) -> NavigationState:
    errors = state.get("errors", [])
    if not state["patient"].primary_symptom_category:
        errors.append("Missing primary_symptom_category")
    return {"errors": errors}


def classify_node(state: NavigationState) -> NavigationState:
    """Node wrapping Agent 1: AlternateCareAgent."""
    decision = _care_agent.decide(state["patient"])
    return {"decision": decision}


def route_after_classify(state: NavigationState) -> str:
    """Conditional edge: TELEHEALTH has no physical location to search,
    so skip straight to the explanation step."""
    return "explain" if state["decision"].destination == "TELEHEALTH" else "rank"


def rank_node(state: NavigationState) -> NavigationState:
    """Node wrapping Agent 2: RankingAgent (discover + score, one agent).

    If the incoming PatientLocation is address-only (no coordinates), the
    RankingAgent geocodes it first.  The resolved location (with lat/lon)
    is written back to state so the recommendation store persists coordinates
    rather than an unresolved address-only object.

    Geocoding or discovery errors are caught and recorded in state["errors"]
    rather than crashing the pipeline; ranked_providers is set to [] so
    the explain step still runs.
    """
    errors = state.get("errors", [])
    try:
        ranked, resolved_location = _ranking_agent.rank(
            state["location"],
            state["decision"],
            has_pcp_flag=state["patient"].has_pcp_flag,
        )
        return {"ranked_providers": ranked, "location": resolved_location, "errors": errors}
    except Exception as e:
        # Include the exception type in the error string so the route layer
        # can distinguish geocoding failures (→ HTTP 422) from other errors.
        errors.append(f"rank_node failed: {type(e).__name__}: {e}")
        return {"ranked_providers": [], "errors": errors}


def explain_node(state: NavigationState) -> NavigationState:
    errors = state.get("errors", [])
    try:
        text = explain_decision(state["decision"])
    except Exception as e:  # LLM call failing must not break routing
        errors.append(f"explain_node failed: {e}")
        text = None
    return {"patient_facing_explanation": text, "errors": errors}


def build_graph():
    graph = StateGraph(NavigationState)

    graph.add_node("validate_input", validate_input_node)
    graph.add_node("classify", classify_node)   # Agent 1
    graph.add_node("rank", rank_node)           # Agent 2
    graph.add_node("explain", explain_node)     # LangChain LLM step

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "classify")
    graph.add_conditional_edges(
        "classify", route_after_classify, {"rank": "rank", "explain": "explain"}
    )
    graph.add_edge("rank", "explain")
    graph.add_edge("explain", END)

    return graph.compile()


navigation_graph = build_graph()
