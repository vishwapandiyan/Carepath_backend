from .schemas import FollowUpResponse, FollowUpTask

# TODO: import teammate's Telegram follow-up agent, e.g.:
# from agents.followup_engine import start_followup_plan


def run_followup(patient_id: str) -> FollowUpResponse:
    """
    Integration wrapper only — the Telegram-based follow-up plan, check-ins,
    and reminders are handled by the teammate's agent. This function calls
    it and shapes the result for our route / for the Care Manager's
    Post Discharge view.
    """

    # TODO: replace with actual call, e.g.:
    # agent_output = start_followup_plan(patient_id=patient_id)
    agent_output = _call_followup_agent(patient_id)

    tasks = [FollowUpTask(**t) for t in agent_output.get("tasks", [])]

    return FollowUpResponse(
        patient_id=patient_id,
        plan=tasks,
        next_checkin=agent_output.get("next_checkin"),
        is_scheduled=agent_output.get("is_scheduled", False),
        raw_agent_output=agent_output,
    )


def _call_followup_agent(patient_id: str) -> dict:
    """
    Placeholder for the actual call into the teammate's follow-up agent.
    """
    raise NotImplementedError("Wire this up to the teammate's follow-up agent")
