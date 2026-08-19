from datetime import datetime, timezone

from .schemas import PathwayDecision, PathwayResponse

# TODO: import the actual agent/module your teammate built, e.g.:
# from agents.pathway_engine import run_risk_model


def run_pathway(patient_id: str) -> PathwayResponse:
    """
    Integration wrapper only — the CMS claims retrieval, feature engineering,
    and ML risk scoring are handled by the teammate's agent. This function
    calls that agent, then shapes the result into our response schema.
    """

    # TODO: replace with actual call into teammate's agent, e.g.:
    # agent_output = run_risk_model(patient_id=patient_id)
    agent_output = _call_pathway_agent(patient_id)

    decision = (
        PathwayDecision.NOT_AVOIDABLE
        if agent_output["is_not_avoidable"]
        else PathwayDecision.POTENTIALLY_AVOIDABLE
    )

    # TODO: persist this result if the Care Manager's Post Discharge /
    # Analytics views need to read it back later.

    return PathwayResponse(
        patient_id=patient_id,
        risk_score=agent_output["risk_score"],
        decision=decision,
        predicted_at=datetime.now(timezone.utc),
        raw_agent_output=agent_output,
    )


def _call_pathway_agent(patient_id: str) -> dict:
    """
    Placeholder for the actual call into the teammate's agent.
    Swap this out once the agent's real interface (function import or
    internal HTTP call) is confirmed.
    """
    raise NotImplementedError("Wire this up to the teammate's pathway/risk-scoring agent")
