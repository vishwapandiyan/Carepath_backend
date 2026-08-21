"""
Navigation Agent — LLM-driven tool-calling loop.

Architecture
------------
The agent receives a patient's clinical features and location, then drives
a bounded tool-calling loop using the NVIDIA LLM (meta/llama-3.3-70b-instruct
via NvidiaClient).  The LLM decides which tool to invoke next; Python only
executes the tools and returns their results.

The hard pipeline  classify → rank → explain  is NOT implemented here.
The LLM sees the available tools and constructs its own call sequence.

Tool-calling protocol (OpenAI-compatible)
-----------------------------------------
Each iteration:
  1. Send the full message history to the LLM with tools=ALL_TOOLS.
  2. If finish_reason == "tool_calls":
       a. Append the raw assistant tool-call message to history.
       b. Execute each requested tool via execute_tool().
       c. Append one role="tool" message per result to history.
       d. Continue.
  3. If finish_reason == "stop" (or no tool calls):
       The LLM has finished; extract the final response.
  4. If iteration count reaches MAX_TOOL_ITERATIONS, abort with an error.
  5. If the LLM calls an unknown or repeatedly failing tool, the error
     result is sent back so the LLM can decide what to do next.

Authoritative sources
---------------------
- Medical routing:  CareClassifier  (via classify_care tool)
- Geocoding:        geocode()        (via geocode_location tool)
- Provider search:  find_nearby_providers() (via discover_providers tool)
- Distance/ranking: rank_providers() (via rank_providers tool)

The LLM may NOT invent CareDecision values, provider locations, or
distance calculations.  It only interprets tool results and decides
what to call next.

Entry point
-----------
    from agents.navigation_agent import run_navigation_agent
    result = run_navigation_agent(
        patient_features={"primary_symptom_category": "minor_infection", ...},
        location_input={"address": "Austin, TX 78701"},   # OR lat/lon dict
    )

Result schema
-------------
On success:
    {
        "ok": True,
        "final_response": str,          # LLM's prose answer to the patient
        "tool_calls_made": int,         # how many tool calls were executed
        "iterations": int,              # loop iterations consumed
        "care_decision": dict | None,   # classify_care result if obtained
        "ranked_providers": list | None # rank_providers result if obtained
    }

On failure:
    {
        "ok": False,
        "error": str,
        "tool_calls_made": int,
        "iterations": int
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from app.services.alternate_care.agents.tools.navigation_tools import ALL_TOOLS, execute_tool
from app.services.alternate_care.llm.nvidia_client import ChatMessage, NvidiaClient, NvidiaClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Absolute upper bound on loop iterations.  Each iteration is one LLM call.
#: A full navigation workflow typically needs 3–4 (classify → geocode →
#: discover → rank), so 10 is a generous safety ceiling.
MAX_TOOL_ITERATIONS: int = 10

_SYSTEM_PROMPT = """\
You are a medical alternate-care navigation assistant.

Your job is to help a patient find the right non-emergency care setting,
nearby healthcare providers, and optionally assist with appointment scheduling.

You MUST use the provided tools to obtain all information.
You MUST NOT invent, estimate, or assume:
  - Care destinations or specialties (use classify_care)
  - Patient coordinates (use geocode_location when only a text address is given)
  - Provider names or locations (use discover_providers)
  - Distances to providers (use rank_providers)
  - Appointment availability or booking status (use appointment tools)

Workflow rules — follow these based on actual tool results, not a fixed sequence:

  Step 1 — Classification (always required first):
    Call classify_care with the patient's clinical features.
    Wait for the result before deciding anything else.

  Step 2 — After receiving the CareDecision, branch on destination:

    If destination == TELEHEALTH:
      - Do NOT call discover_providers.
      - Do NOT call rank_providers.
      - No physical location is needed.
      - Proceed directly to composing the final response or checking appointment
        availability if the patient explicitly requests scheduling help.

    If destination is PCP, URGENT_CARE, SPECIALIST, or DENTISTRY:
      a. Coordinates — if the patient supplied only a text address (no
         latitude/longitude), call geocode_location to resolve coordinates.
         Skip this step if coordinates are already known.
      b. Provider discovery — call discover_providers using the coordinates
         and the destination/specialty from the classify_care result.
      c. Ranking — call rank_providers with the patient coordinates and the
         provider list returned by discover_providers.
      d. Proceed to Step 3 (appointment operations) if the patient requests
         scheduling help, or compose the final response.

  Step 3 — Appointment operations (optional, patient-driven):

    CRITICAL: ONLY invoke appointment tools when the patient EXPLICITLY requests:
      - Checking appointment availability
      - Booking an appointment
      - Rescheduling an existing appointment
      - Cancelling an existing appointment

    DO NOT call appointment tools unless the patient explicitly asks for scheduling.
    DO NOT assume the patient wants to book — always confirm first.

    Appointment workflow (when patient requests scheduling):
      1. check_availability — Query available appointment slots for a specific
         provider from the ranked list.
         - Required parameters: recommendation_id (from classify_care result),
           provider_id (from rank_providers result), patient_id
         - Optional parameters: date_range, preferred_date, preferred_time
         - Call this AFTER rank_providers completes to show the patient when
           a chosen provider has open appointments.

      2. book_appointment — Book a specific appointment slot.
         - Required parameters: recommendation_id, patient_id, provider_id,
           slot_id (from check_availability result)
         - Call this AFTER check_availability returns slots AND the patient
           has selected a specific slot.
         - Always confirm the patient's slot choice before booking.

      3. reschedule_appointment — Change an existing appointment to a new time.
         - Required parameters: patient_id, appointment_id
         - Optional parameters: recommendation_id, new_slot_id, preferred_date,
           preferred_time
         - Supports two workflows:
           A) Direct slot selection: provide new_slot_id from check_availability
           B) Preference-based: provide preferred_date/preferred_time
         - For workflow A, call check_availability first to present options.

      4. cancel_appointment — Cancel an existing appointment.
         - Required parameters: patient_id, appointment_id
         - Call this ONLY when the patient explicitly requests cancellation.
         - The slot will be freed and become available to other patients.

    Error handling for appointment tools:
      - If an appointment tool returns {"ok": false, "error": "..."}, explain
        the error to the patient in plain language.
      - Suggest alternatives when possible (e.g., different provider, different
        time slot, calling the provider directly).
      - DO NOT retry the same operation automatically without patient guidance.
      - If recommendation_id is expired, inform the patient they may need to
        restart the navigation workflow.

  Step 4 — Final response:
    Synthesise a clear, helpful answer for the patient that includes:
      - The recommended care setting and why.
      - The top-ranked nearby facilities (name, approximate distance),
        unless destination is TELEHEALTH.
      - Appointment confirmation details if booking succeeded.
      - Any relevant guidance (e.g. "seek care today", "telehealth available").

At every step, decide the next action based on the actual result of the
previous tool call — not by blindly following a fixed sequence.

If a tool returns an error, explain what went wrong and, where possible,
suggest an alternative or provide partial information from successful calls.

Be concise and use plain language — the patient may be worried or in discomfort.
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_initial_messages(
    patient_features: Dict[str, Any],
    location_input: Dict[str, Any],
) -> List[Union[ChatMessage, dict]]:
    """Construct the opening system + user messages for the agent loop."""
    # Describe location naturally
    if "address" in location_input and location_input["address"]:
        location_description = f"address: {location_input['address']}"
    elif "latitude" in location_input and "longitude" in location_input:
        location_description = (
            f"latitude {location_input['latitude']}, "
            f"longitude {location_input['longitude']}"
        )
    else:
        location_description = json.dumps(location_input)

    user_content = (
        "Please help me find the right care setting and nearby providers.\n\n"
        f"Patient clinical features:\n{json.dumps(patient_features, indent=2)}\n\n"
        f"Patient location: {location_description}"
    )

    return [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def _assistant_tool_call_message(response_raw: Any) -> dict:
    """Build the raw assistant dict that re-injects the model's tool-call turn.

    This is the OpenAI protocol: after the model returns tool_calls, the
    caller must append the assistant's own message back to the history
    before appending the tool results.

    Parameters
    ----------
    response_raw :
        The raw ChatCompletion object from LLMResponse.raw.
    """
    choice_message = response_raw.choices[0].message
    tool_calls_raw = []
    if choice_message.tool_calls:
        for tc in choice_message.tool_calls:
            tool_calls_raw.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
    return {
        "role": "assistant",
        "content": choice_message.content,   # usually None on tool-call turns
        "tool_calls": tool_calls_raw,
    }


def _tool_result_message(tool_call_id: str, result: Dict[str, Any]) -> dict:
    """Build a role="tool" message carrying the result of one tool execution."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_navigation_agent(
    patient_features: Dict[str, Any],
    location_input: Dict[str, Any],
    *,
    client: Optional[NvidiaClient] = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> Dict[str, Any]:
    """Run the LLM-driven navigation agent loop.

    Parameters
    ----------
    patient_features : dict
        Patient clinical data as a flat dict.  Keys must match
        ``PatientFeatures`` fields; ``primary_symptom_category`` is required.
        Extra keys are silently forwarded and accepted by the tool.
    location_input : dict
        Patient location.  One of:
          - ``{"address": "Austin, TX 78701"}``
          - ``{"latitude": 30.27, "longitude": -97.74}``
          - ``{"latitude": ..., "longitude": ..., "address": ...}``
    client : NvidiaClient | None
        Optionally inject a pre-constructed NvidiaClient.  When None (the
        default) a new instance is created from environment variables.
        Pass a mock here in tests.
    max_iterations : int
        Override the loop ceiling.  Default ``MAX_TOOL_ITERATIONS`` (10).

    Returns
    -------
    dict
        See module docstring for the success / failure schemas.
    """
    # ------------------------------------------------------------------
    # 1. Initialise
    # ------------------------------------------------------------------
    if client is None:
        try:
            client = NvidiaClient()
        except NvidiaClientError as exc:
            logger.error("NavigationAgent: failed to create NvidiaClient: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "tool_calls_made": 0,
                "iterations": 0,
                "appointment_slots": None,
                "booked_appointment_id": None,
                "appointment_history": [],
            }

    messages: List[Union[ChatMessage, dict]] = _build_initial_messages(
        patient_features, location_input
    )

    # Tracking state across iterations
    tool_calls_made: int = 0
    iterations: int = 0
    care_decision: Optional[dict] = None
    ranked_providers: Optional[list] = None
    geocoded_location: Optional[dict] = None  # set when geocode_location succeeds
    
    # Appointment workflow state
    appointment_slots: Optional[List[dict]] = None  # set when check_availability succeeds
    booked_appointment_id: Optional[str] = None  # set when book_appointment succeeds
    appointment_history: List[Dict[str, Any]] = []  # append-only log of appointment operations

    logger.info(
        "NavigationAgent: starting loop (max_iterations=%d)", max_iterations
    )

    # ------------------------------------------------------------------
    # 2. Bounded tool-calling loop
    # ------------------------------------------------------------------
    while iterations < max_iterations:
        iterations += 1
        logger.debug("NavigationAgent: iteration %d/%d", iterations, max_iterations)

        # -- LLM call --------------------------------------------------
        try:
            response = client.chat(
                messages=list(messages),   # snapshot — avoids mock capturing a live reference
                tools=ALL_TOOLS,
                tool_choice="auto",
            )
        except NvidiaClientError as exc:
            logger.error("NavigationAgent: LLM call failed at iteration %d: %s", iterations, exc)
            return {
                "ok": False,
                "error": f"LLM call failed: {exc}",
                "tool_calls_made": tool_calls_made,
                "iterations": iterations,
                "appointment_slots": appointment_slots,
                "booked_appointment_id": booked_appointment_id,
                "appointment_history": appointment_history,
            }

        logger.debug(
            "NavigationAgent: finish_reason=%s has_tool_calls=%s",
            response.finish_reason,
            response.has_tool_calls,
        )

        # -- Final answer -----------------------------------------------
        if not response.has_tool_calls:
            final_text = response.content or ""
            logger.info(
                "NavigationAgent: done after %d iterations, %d tool calls",
                iterations,
                tool_calls_made,
            )
            return {
                "ok": True,
                "final_response": final_text,
                "tool_calls_made": tool_calls_made,
                "iterations": iterations,
                "care_decision": care_decision,
                "ranked_providers": ranked_providers,
                "geocoded_location": geocoded_location,
                # Appointment workflow state
                "appointment_slots": appointment_slots,
                "booked_appointment_id": booked_appointment_id,
                "appointment_history": appointment_history,
            }

        # -- Tool execution turn ----------------------------------------
        # Re-inject the assistant's own tool-call message into history
        # (required by the OpenAI protocol before tool result messages).
        messages.append(_assistant_tool_call_message(response.raw))

        for tc in response.tool_calls:
            logger.debug(
                "NavigationAgent: executing tool %r with args %r",
                tc.name,
                tc.arguments,
            )
            tool_calls_made += 1

            # Parse the LLM's JSON arguments string
            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "NavigationAgent: could not parse tool arguments for %r: %s",
                    tc.name,
                    exc,
                )
                tool_result = {
                    "ok": False,
                    "error": f"Invalid JSON in tool arguments: {exc}",
                }
            else:
                # Execute via the deterministic tool dispatcher
                tool_result = execute_tool(tc.name, args)
                logger.debug(
                    "NavigationAgent: tool %r result ok=%s",
                    tc.name,
                    tool_result.get("ok"),
                )

            # Cache notable results for the structured return value
            if tc.name == "classify_care" and tool_result.get("ok"):
                care_decision = tool_result
            elif tc.name == "geocode_location" and tool_result.get("ok"):
                geocoded_location = tool_result   # carries latitude, longitude, address
            elif tc.name == "rank_providers" and tool_result.get("ok"):
                ranked_providers = tool_result.get("providers")
            # Appointment tool result tracking
            elif tc.name == "check_availability":
                appointment_history.append({
                    "operation": "check_availability",
                    "ok": tool_result.get("ok"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if tool_result.get("ok"):
                    appointment_slots = tool_result.get("slots")
            elif tc.name == "book_appointment":
                appointment_history.append({
                    "operation": "book_appointment",
                    "ok": tool_result.get("ok"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if tool_result.get("ok"):
                    booked_appointment_id = tool_result.get("appointment_id")
            elif tc.name == "reschedule_appointment":
                appointment_history.append({
                    "operation": "reschedule_appointment",
                    "ok": tool_result.get("ok"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                # Note: booked_appointment_id is NOT updated for reschedule
            elif tc.name == "cancel_appointment":
                appointment_history.append({
                    "operation": "cancel_appointment",
                    "ok": tool_result.get("ok"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if tool_result.get("ok") and tool_result.get("appointment_id") == booked_appointment_id:
                    booked_appointment_id = None  # Clear if the just-booked appointment was cancelled

            # Append the tool result so the LLM can read it next turn
            messages.append(_tool_result_message(tc.id, tool_result))

    # ------------------------------------------------------------------
    # 3. Iteration limit reached
    # ------------------------------------------------------------------
    logger.error(
        "NavigationAgent: exceeded max_iterations=%d (tool_calls_made=%d)",
        max_iterations,
        tool_calls_made,
    )
    return {
        "ok": False,
        "error": (
            f"Agent loop exceeded maximum iterations ({max_iterations}).  "
            "The LLM did not produce a final answer within the allowed number "
            "of tool-calling turns."
        ),
        "tool_calls_made": tool_calls_made,
        "iterations": iterations,
        "appointment_slots": appointment_slots,
        "booked_appointment_id": booked_appointment_id,
        "appointment_history": appointment_history,
    }
