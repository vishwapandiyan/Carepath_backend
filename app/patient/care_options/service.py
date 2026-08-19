from datetime import datetime, timezone

from .schemas import CareCategory, CareOptionsResponse

# TODO: import teammate's rule-based categorization agent, e.g.:
# from agents.care_options_engine import classify_patient


def get_care_options(patient_id: str) -> CareOptionsResponse:
    """
    Integration wrapper only — the rule-based logic that buckets the patient
    into PCP / Specialist / Urgent-care / Telehealth lives in the teammate's
    agent. This function calls it and shapes the result.
    """

    # TODO: replace with actual call, e.g.:
    # agent_output = classify_patient(patient_id=patient_id)
    agent_output = _call_care_options_agent(patient_id)

    return CareOptionsResponse(
        patient_id=patient_id,
        category=CareCategory(agent_output["category"]),
        determined_at=datetime.now(timezone.utc),
        raw_agent_output=agent_output,
    )


def _call_care_options_agent(patient_id: str) -> dict:
    """
    Placeholder for the actual call into the teammate's care-options agent.
    """
    raise NotImplementedError("Wire this up to the teammate's care-options agent")
