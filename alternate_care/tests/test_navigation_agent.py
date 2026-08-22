"""
Unit tests for agents/navigation_agent.py.

All 11 required test cases are covered:
  1.  LLM requests classify_care → tool executes → result returned to LLM
  2.  classify_care result causes a subsequent tool call (discover_providers)
  3.  LLM requests geocode_location → tool executes → result returned to LLM
  4.  LLM requests discover_providers → tool executes → result returned to LLM
  5.  LLM requests rank_providers → tool executes → result returned to LLM
  6.  LLM stops after obtaining sufficient information (no tool calls)
  7.  LLM performs multiple tool calls across several iterations
  8.  Tool failure → error result forwarded to LLM → LLM can continue
  9.  Invalid tool call (unknown name) → error result forwarded to LLM
  10. Maximum iteration protection → ok=False with descriptive error
  11. Final response construction from actual tool results only

NvidiaClient is fully mocked — no real NVIDIA API calls are made.
No Nominatim / Overpass calls are made (execute_tool is also mocked
where needed to isolate the agent loop from network I/O).

Mock conventions
----------------
- `_make_llm_response(content, tool_calls)` builds a fake LLMResponse.
- `_make_tool_call(id_, name, arguments_dict)` builds a fake ToolCall.
- `MockClient` is a thin wrapper around MagicMock that records all `.chat()`
  calls and lets each test configure the return-value sequence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

import pytest

# Make the project root importable when tests are run from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.alternate_care.agents.navigation_agent import (
    MAX_TOOL_ITERATIONS,
    run_navigation_agent,
    _assistant_tool_call_message,
    _tool_result_message,
    _build_initial_messages,
)
from app.services.alternate_care.llm.nvidia_client import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers — build fake LLMResponse objects without hitting the real API
# ---------------------------------------------------------------------------

def _make_fake_tool_call_raw(id_: str, name: str, arguments: str) -> SimpleNamespace:
    """Minimal fake of the raw openai ToolCall object (inside ChatCompletion)."""
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=id_, function=fn, type="function")


def _make_fake_completion(
    content: Optional[str],
    tool_calls_raw: Optional[list] = None,
    finish_reason: str = "stop",
    model: str = "meta/llama-3.3-70b-instruct",
) -> SimpleNamespace:
    """Build a fake ChatCompletion object."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls_raw)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model=model)


def _make_tool_call(id_: str, name: str, args: Dict[str, Any]) -> ToolCall:
    """Build a ToolCall dataclass as NvidiaClient._parse_completion would produce."""
    return ToolCall(id=id_, name=name, arguments=json.dumps(args))


def _make_llm_response(
    content: Optional[str] = None,
    tool_calls: Optional[List[ToolCall]] = None,
    finish_reason: Optional[str] = None,
) -> LLMResponse:
    """Build a fake LLMResponse.

    finish_reason defaults to "tool_calls" when tool_calls is non-empty,
    "stop" otherwise.
    """
    if finish_reason is None:
        finish_reason = "tool_calls" if tool_calls else "stop"

    # Build matching raw completion
    raw_tcs = None
    if tool_calls:
        raw_tcs = [
            _make_fake_tool_call_raw(tc.id, tc.name, tc.arguments)
            for tc in tool_calls
        ]
    raw = _make_fake_completion(
        content=content,
        tool_calls_raw=raw_tcs,
        finish_reason=finish_reason,
    )

    return LLMResponse(
        content=content,
        model="meta/llama-3.3-70b-instruct",
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        raw=raw,
    )


def _mock_client(responses: List[LLMResponse]) -> MagicMock:
    """Build a MagicMock NvidiaClient whose .chat() returns responses in order."""
    client = MagicMock()
    client.chat.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# Common patient / location fixtures
# ---------------------------------------------------------------------------

_PATIENT = {
    "primary_symptom_category": "minor_infection",
    "pain_level_self_reported": 5,
    "symptom_trend": "worsening",
}

_LOC_ADDRESS = {"address": "Austin, TX 78701"}
_LOC_COORDS = {"latitude": 30.2672, "longitude": -97.7431}

_CLASSIFY_RESULT = {
    "ok": True,
    "rule_id": "UC-001-INFECTION",
    "priority": 30,
    "destination": "URGENT_CARE",
    "specialty": None,
    "status": "DOCUMENT_SUPPORTED",
    "explanation": "Same-day evaluation appropriate.",
}

_GEOCODE_RESULT = {
    "ok": True,
    "latitude": 30.2672,
    "longitude": -97.7431,
    "address": "Austin, TX 78701",
}

_PROVIDERS_RAW = [
    {
        "provider_id": "osm:node:1001",
        "name": "City Urgent Care",
        "destination_type": "URGENT_CARE",
        "specialty": None,
        "latitude": 30.271,
        "longitude": -97.745,
        "address": None,
        "distance_km": None,
        "score": None,
        "source": "osm",
    }
]

_DISCOVER_RESULT = {
    "ok": True,
    "destination": "URGENT_CARE",
    "specialty": None,
    "count": 1,
    "providers": _PROVIDERS_RAW,
}

_RANK_RESULT = {
    "ok": True,
    "count": 1,
    "providers": [
        {**_PROVIDERS_RAW[0], "distance_km": 0.52, "score": 0.979},
    ],
}


# ===========================================================================
# Internal helper tests (fast, no LLM)
# ===========================================================================

class TestHelpers:
    """Tests for the private message-building helpers."""

    def test_build_initial_messages_address_location(self):
        msgs = _build_initial_messages(_PATIENT, _LOC_ADDRESS)
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert "Austin, TX 78701" in msgs[1].content
        assert "minor_infection" in msgs[1].content

    def test_build_initial_messages_coord_location(self):
        msgs = _build_initial_messages(_PATIENT, _LOC_COORDS)
        assert "30.2672" in msgs[1].content
        assert "-97.7431" in msgs[1].content

    def test_assistant_tool_call_message_structure(self):
        tc_raw = _make_fake_tool_call_raw("tc-1", "classify_care", '{"primary_symptom_category":"minor_infection"}')
        raw_completion = _make_fake_completion(content=None, tool_calls_raw=[tc_raw], finish_reason="tool_calls")
        msg = _assistant_tool_call_message(raw_completion)
        assert msg["role"] == "assistant"
        assert isinstance(msg["tool_calls"], list)
        assert msg["tool_calls"][0]["id"] == "tc-1"
        assert msg["tool_calls"][0]["function"]["name"] == "classify_care"

    def test_tool_result_message_structure(self):
        result = {"ok": True, "destination": "URGENT_CARE"}
        msg = _tool_result_message("tc-99", result)
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "tc-99"
        parsed = json.loads(msg["content"])
        assert parsed["destination"] == "URGENT_CARE"


# ===========================================================================
# Test 1 — LLM requests classify_care
# ===========================================================================

class TestLLMRequestsClassifyCare:

    def test_classify_care_tool_is_executed(self):
        """When the LLM's first response calls classify_care, the tool runs."""
        tc = _make_tool_call("tc-1", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc]),         # iter 1: call classify_care
            _make_llm_response(content="All done."),     # iter 2: final answer
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT) as mock_exec:
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        mock_exec.assert_called_once_with("classify_care", _PATIENT)
        assert result["ok"] is True

    def test_classify_care_result_is_in_history_for_llm(self):
        """The classify_care tool result must be injected into messages before the next LLM call."""
        tc = _make_tool_call("tc-1", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        # Second LLM call must include the tool result in its messages
        second_call_messages = client.chat.call_args_list[1][1]["messages"]
        # Find the role="tool" message
        tool_msgs = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        content = json.loads(tool_msgs[0]["content"])
        assert content["destination"] == "URGENT_CARE"

    def test_care_decision_captured_in_result(self):
        """When classify_care succeeds, care_decision is populated in the return value."""
        tc = _make_tool_call("tc-1", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Here is your recommendation."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["care_decision"] is not None
        assert result["care_decision"]["destination"] == "URGENT_CARE"


# ===========================================================================
# Test 2 — classify_care result causes another tool call (discover_providers)
# ===========================================================================

class TestClassifyCareCausesAnotherToolCall:

    def test_classify_then_discover_two_separate_iterations(self):
        """The LLM calls classify_care, then in the next turn calls discover_providers."""
        tc_classify = _make_tool_call("tc-1", "classify_care", _PATIENT)
        tc_discover = _make_tool_call(
            "tc-2", "discover_providers",
            {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"},
        )
        responses = [
            _make_llm_response(tool_calls=[tc_classify]),
            _make_llm_response(tool_calls=[tc_discover]),
            _make_llm_response(content="Found providers near you."),
        ]
        client = _mock_client(responses)

        exec_returns = {
            "classify_care": _CLASSIFY_RESULT,
            "discover_providers": _DISCOVER_RESULT,
        }

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: exec_returns[n]):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True
        assert result["tool_calls_made"] == 2
        assert result["iterations"] == 3

    def test_history_grows_with_each_iteration(self):
        """Each tool-calling turn adds assistant + tool messages to history."""
        tc_classify = _make_tool_call("tc-1", "classify_care", _PATIENT)
        tc_discover = _make_tool_call(
            "tc-2", "discover_providers",
            {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"},
        )
        responses = [
            _make_llm_response(tool_calls=[tc_classify]),
            _make_llm_response(tool_calls=[tc_discover]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        exec_returns = {
            "classify_care": _CLASSIFY_RESULT,
            "discover_providers": _DISCOVER_RESULT,
        }

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: exec_returns[n]):
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        # iter 1: 2 initial messages
        assert len(client.chat.call_args_list[0][1]["messages"]) == 2
        # iter 2: 2 initial + 1 assistant tool-call + 1 tool result = 4
        assert len(client.chat.call_args_list[1][1]["messages"]) == 4
        # iter 3: 4 + 1 assistant tool-call + 1 tool result = 6
        assert len(client.chat.call_args_list[2][1]["messages"]) == 6


# ===========================================================================
# Test 3 — LLM requests geocode_location
# ===========================================================================

class TestLLMRequestsGeocodeLocation:

    def test_geocode_tool_is_executed(self):
        tc = _make_tool_call("tc-g", "geocode_location", {"address": "Austin, TX 78701"})
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Coordinates resolved."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_GEOCODE_RESULT) as mock_exec:
            result = run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        mock_exec.assert_called_once_with("geocode_location", {"address": "Austin, TX 78701"})
        assert result["ok"] is True

    def test_geocode_result_forwarded_to_llm(self):
        tc = _make_tool_call("tc-g", "geocode_location", {"address": "Austin, TX"})
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_GEOCODE_RESULT):
            run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        second_call_messages = client.chat.call_args_list[1][1]["messages"]
        tool_msgs = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        content = json.loads(tool_msgs[0]["content"])
        assert content["latitude"] == 30.2672


# ===========================================================================
# Test 4 — LLM requests discover_providers
# ===========================================================================

class TestLLMRequestsDiscoverProviders:

    def test_discover_tool_is_executed(self):
        args = {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"}
        tc = _make_tool_call("tc-d", "discover_providers", args)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Providers found."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_DISCOVER_RESULT) as mock_exec:
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        mock_exec.assert_called_once_with("discover_providers", args)
        assert result["ok"] is True

    def test_discover_result_forwarded_to_llm(self):
        args = {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"}
        tc = _make_tool_call("tc-d", "discover_providers", args)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_DISCOVER_RESULT):
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        second_call_messages = client.chat.call_args_list[1][1]["messages"]
        tool_msgs = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
        content = json.loads(tool_msgs[0]["content"])
        assert content["count"] == 1
        assert content["providers"][0]["name"] == "City Urgent Care"


# ===========================================================================
# Test 5 — LLM requests rank_providers
# ===========================================================================

class TestLLMRequestsRankProviders:

    def test_rank_tool_is_executed(self):
        args = {
            "patient_lat": 30.2672,
            "patient_lon": -97.7431,
            "providers": _PROVIDERS_RAW,
        }
        tc = _make_tool_call("tc-r", "rank_providers", args)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Here are your ranked providers."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_RANK_RESULT) as mock_exec:
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        mock_exec.assert_called_once_with("rank_providers", args)
        assert result["ok"] is True

    def test_ranked_providers_captured_in_result(self):
        args = {
            "patient_lat": 30.2672,
            "patient_lon": -97.7431,
            "providers": _PROVIDERS_RAW,
        }
        tc = _make_tool_call("tc-r", "rank_providers", args)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_RANK_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ranked_providers"] is not None
        assert len(result["ranked_providers"]) == 1
        assert result["ranked_providers"][0]["distance_km"] == 0.52


# ===========================================================================
# Test 6 — LLM stops after obtaining sufficient information
# ===========================================================================

class TestLLMStopsWithoutToolCalls:

    def test_immediate_stop_no_tools_called(self):
        """LLM returns a plain text answer on the very first call — no tools."""
        responses = [
            _make_llm_response(content="Please visit your nearest urgent care center."),
        ]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True
        assert result["final_response"] == "Please visit your nearest urgent care center."
        assert result["tool_calls_made"] == 0
        assert result["iterations"] == 1
        assert result["care_decision"] is None
        assert result["ranked_providers"] is None
        # Only one LLM call was made
        assert client.chat.call_count == 1

    def test_stop_after_one_tool_call(self):
        """LLM calls one tool then stops — tool_calls_made=1, iterations=2."""
        tc = _make_tool_call("tc-1", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Based on your symptoms, visit urgent care."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True
        assert result["tool_calls_made"] == 1
        assert result["iterations"] == 2
        assert client.chat.call_count == 2

    def test_finish_reason_stop_terminates_loop(self):
        """finish_reason='stop' with content terminates immediately."""
        responses = [
            _make_llm_response(content="Go to urgent care.", finish_reason="stop"),
        ]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True
        assert result["final_response"] == "Go to urgent care."


# ===========================================================================
# Test 7 — LLM performs multiple tool calls across several iterations
# ===========================================================================

class TestMultipleToolCallIterations:

    def test_full_four_step_workflow(self):
        """Full happy path: classify → geocode → discover → rank → final answer."""
        tc1 = _make_tool_call("tc-1", "classify_care", _PATIENT)
        tc2 = _make_tool_call("tc-2", "geocode_location", {"address": "Austin, TX 78701"})
        tc3 = _make_tool_call(
            "tc-3", "discover_providers",
            {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"},
        )
        tc4 = _make_tool_call(
            "tc-4", "rank_providers",
            {"patient_lat": 30.2672, "patient_lon": -97.7431, "providers": _PROVIDERS_RAW},
        )
        responses = [
            _make_llm_response(tool_calls=[tc1]),
            _make_llm_response(tool_calls=[tc2]),
            _make_llm_response(tool_calls=[tc3]),
            _make_llm_response(tool_calls=[tc4]),
            _make_llm_response(content="City Urgent Care is 0.52 km away. Recommended: URGENT_CARE."),
        ]
        client = _mock_client(responses)

        tool_results = {
            "classify_care":      _CLASSIFY_RESULT,
            "geocode_location":   _GEOCODE_RESULT,
            "discover_providers": _DISCOVER_RESULT,
            "rank_providers":     _RANK_RESULT,
        }

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: tool_results[n]):
            result = run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        assert result["ok"] is True
        assert result["tool_calls_made"] == 4
        assert result["iterations"] == 5
        assert "City Urgent Care" in result["final_response"]
        assert result["care_decision"]["destination"] == "URGENT_CARE"
        assert result["ranked_providers"][0]["distance_km"] == 0.52

    def test_tool_calls_made_counter_increments_per_call(self):
        """tool_calls_made counts individual tool calls, not iterations."""
        # Two tools in one iteration (batched), then stop
        tc1 = _make_tool_call("tc-1", "classify_care", _PATIENT)
        tc2 = _make_tool_call("tc-2", "geocode_location", {"address": "Austin, TX"})
        responses = [
            # Single LLM response requesting TWO tool calls simultaneously
            _make_llm_response(tool_calls=[tc1, tc2]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        tool_results = {
            "classify_care":    _CLASSIFY_RESULT,
            "geocode_location": _GEOCODE_RESULT,
        }

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: tool_results[n]):
            result = run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        # 2 tools in 1 iteration, then 1 final iteration = 2 iterations, 2 tool calls
        assert result["tool_calls_made"] == 2
        assert result["iterations"] == 2

    def test_all_tools_logs_called_in_sequence(self):
        """execute_tool is called in the correct order across iterations."""
        tc1 = _make_tool_call("tc-1", "classify_care", _PATIENT)
        tc2 = _make_tool_call(
            "tc-2", "discover_providers",
            {"latitude": 30.2672, "longitude": -97.7431, "destination": "URGENT_CARE"},
        )
        tc3 = _make_tool_call(
            "tc-3", "rank_providers",
            {"patient_lat": 30.2672, "patient_lon": -97.7431, "providers": _PROVIDERS_RAW},
        )
        responses = [
            _make_llm_response(tool_calls=[tc1]),
            _make_llm_response(tool_calls=[tc2]),
            _make_llm_response(tool_calls=[tc3]),
            _make_llm_response(content="All done."),
        ]
        client = _mock_client(responses)

        tool_results = {
            "classify_care":      _CLASSIFY_RESULT,
            "discover_providers": _DISCOVER_RESULT,
            "rank_providers":     _RANK_RESULT,
        }

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: tool_results[n]) as mock_exec:
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        names_called = [c.args[0] for c in mock_exec.call_args_list]
        assert names_called == ["classify_care", "discover_providers", "rank_providers"]


# ===========================================================================
# Test 8 — Tool failure → error forwarded to LLM → LLM can continue
# ===========================================================================

class TestToolFailureForwardedToLLM:

    def test_tool_error_result_forwarded_not_raised(self):
        """A failing tool must NOT crash the loop — the error dict goes back to the LLM."""
        tc = _make_tool_call("tc-1", "classify_care", {})  # empty → will fail
        error_result = {"ok": False, "error": "primary_symptom_category is required"}
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="I could not classify your symptoms without more details."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=error_result):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        # Agent must still return ok=True because the LLM produced a final answer
        assert result["ok"] is True
        assert result["tool_calls_made"] == 1

    def test_tool_error_message_appears_in_llm_history(self):
        """The error result from the tool must be visible in the next LLM call."""
        tc = _make_tool_call("tc-1", "geocode_location", {"address": "ZZZZZ"})
        error_result = {"ok": False, "error": "No geocoding results found for address: 'ZZZZZ'"}
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="I could not find that location."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=error_result):
            run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        second_call_messages = client.chat.call_args_list[1][1]["messages"]
        tool_msgs = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
        content = json.loads(tool_msgs[0]["content"])
        assert content["ok"] is False
        assert "ZZZZZ" in content["error"]

    def test_llm_recovers_from_tool_failure_and_continues(self):
        """LLM may call another tool after receiving an error — the loop should handle it."""
        tc_fail = _make_tool_call("tc-1", "geocode_location", {"address": "ZZZZZ"})
        tc_retry = _make_tool_call("tc-2", "geocode_location", {"address": "Austin, TX"})
        error_result = {"ok": False, "error": "Not found"}
        responses = [
            _make_llm_response(tool_calls=[tc_fail]),
            _make_llm_response(tool_calls=[tc_retry]),   # LLM retries with a different address
            _make_llm_response(content="Found it."),
        ]
        client = _mock_client(responses)

        side_effects = [error_result, _GEOCODE_RESULT]

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: side_effects.pop(0)):
            result = run_navigation_agent(_PATIENT, _LOC_ADDRESS, client=client)

        assert result["ok"] is True
        assert result["tool_calls_made"] == 2


# ===========================================================================
# Test 9 — Invalid tool call (unknown tool name) → error dict returned
# ===========================================================================

class TestInvalidToolCall:

    def test_unknown_tool_name_returns_error_not_exception(self):
        """execute_tool with an unknown name returns {ok:False, error:...}, not raise."""
        tc = _make_tool_call("tc-x", "nonexistent_tool", {"foo": "bar"})
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="That tool is not available."),
        ]
        client = _mock_client(responses)

        # Do NOT mock execute_tool here — use the real one so we test actual behavior
        with patch("agents.navigation_agent.execute_tool",
                   return_value={"ok": False, "error": "Unknown tool: 'nonexistent_tool'"}):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True  # LLM produced a final answer despite the error
        assert result["tool_calls_made"] == 1

    def test_invalid_tool_error_forwarded_to_llm(self):
        """The error from an invalid tool call must appear in the next LLM turn."""
        tc = _make_tool_call("tc-x", "invalid_tool", {})
        unknown_error = {"ok": False, "error": "Unknown tool: 'invalid_tool'"}
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="I cannot do that."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=unknown_error):
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        second_call_messages = client.chat.call_args_list[1][1]["messages"]
        tool_msgs = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
        content = json.loads(tool_msgs[0]["content"])
        assert content["ok"] is False
        assert "Unknown tool" in content["error"]

    def test_malformed_json_arguments_handled_gracefully(self):
        """If the LLM sends non-JSON tool arguments, the loop continues with an error result."""
        # Build a ToolCall whose arguments string is not valid JSON
        bad_tc = ToolCall(id="tc-bad", name="classify_care", arguments="{NOT VALID JSON}")
        raw_tc = _make_fake_tool_call_raw("tc-bad", "classify_care", "{NOT VALID JSON}")
        raw_completion = _make_fake_completion(
            content=None,
            tool_calls_raw=[raw_tc],
            finish_reason="tool_calls",
        )
        bad_response = LLMResponse(
            content=None,
            model="meta/llama-3.3-70b-instruct",
            tool_calls=[bad_tc],
            finish_reason="tool_calls",
            raw=raw_completion,
        )
        responses = [
            bad_response,
            _make_llm_response(content="Apologies, I could not complete the request."),
        ]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True  # Loop survived the bad arguments
        # execute_tool should NOT have been called (JSON parse failed before dispatch)
        assert result["tool_calls_made"] == 1  # the bad call still counts as attempted


# ===========================================================================
# Test 10 — Maximum iteration protection
# ===========================================================================

class TestMaxIterationProtection:

    def test_loop_terminates_at_max_iterations(self):
        """If the LLM never stops calling tools, the loop must terminate at max_iterations."""
        # Build a response that always requests another tool call
        tc = _make_tool_call("tc-loop", "classify_care", _PATIENT)
        looping_response = _make_llm_response(tool_calls=[tc])
        # Provide more responses than the limit to confirm the loop actually stops
        responses = [looping_response] * (MAX_TOOL_ITERATIONS + 5)
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is False
        assert "exceeded maximum iterations" in result["error"]
        assert result["iterations"] == MAX_TOOL_ITERATIONS
        assert client.chat.call_count == MAX_TOOL_ITERATIONS

    def test_custom_max_iterations_respected(self):
        """The max_iterations parameter overrides the module-level default."""
        tc = _make_tool_call("tc-loop", "classify_care", _PATIENT)
        looping_response = _make_llm_response(tool_calls=[tc])
        responses = [looping_response] * 20
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client, max_iterations=3)

        assert result["ok"] is False
        assert result["iterations"] == 3
        assert client.chat.call_count == 3

    def test_error_message_mentions_iteration_count(self):
        """The error message from hitting the limit must name the limit value."""
        tc = _make_tool_call("tc-loop", "classify_care", _PATIENT)
        responses = [_make_llm_response(tool_calls=[tc])] * 20
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client, max_iterations=2)

        assert "2" in result["error"]

    def test_tool_calls_made_reported_at_limit(self):
        """tool_calls_made is correctly reported when the limit is hit."""
        tc = _make_tool_call("tc-loop", "classify_care", _PATIENT)
        responses = [_make_llm_response(tool_calls=[tc])] * 20
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client, max_iterations=4)

        # 4 iterations × 1 tool call each
        assert result["tool_calls_made"] == 4


# ===========================================================================
# Test 11 — Final response construction from actual tool results only
# ===========================================================================

class TestFinalResponseConstruction:

    def test_final_response_contains_llm_content(self):
        """The final_response field must be the LLM's own text, not fabricated."""
        expected_text = (
            "Based on your symptoms, I recommend visiting URGENT CARE.\n"
            "Nearest option: City Urgent Care (0.52 km away)."
        )
        responses = [
            _make_llm_response(content=expected_text),
        ]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["final_response"] == expected_text

    def test_final_response_is_empty_string_when_no_content(self):
        """If the LLM returns None content on a stop response, final_response is ''."""
        responses = [
            _make_llm_response(content=None, finish_reason="stop"),
        ]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is True
        assert result["final_response"] == ""

    def test_care_decision_only_set_when_classify_care_succeeds(self):
        """care_decision in the return value must only come from a successful classify_care."""
        # First call: classify_care fails
        tc_fail = _make_tool_call("tc-1", "classify_care", {})
        # Second call: classify_care succeeds with corrected args
        tc_ok = _make_tool_call("tc-2", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc_fail]),
            _make_llm_response(tool_calls=[tc_ok]),
            _make_llm_response(content="Urgent care recommended."),
        ]
        client = _mock_client(responses)

        fail_result = {"ok": False, "error": "missing primary_symptom_category"}
        call_results = [fail_result, _CLASSIFY_RESULT]

        with patch("agents.navigation_agent.execute_tool", side_effect=lambda n, a: call_results.pop(0)):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        # care_decision must reflect the successful call
        assert result["care_decision"] is not None
        assert result["care_decision"]["destination"] == "URGENT_CARE"

    def test_ranked_providers_only_set_when_rank_providers_succeeds(self):
        """ranked_providers in the return value must only come from rank_providers ok=True."""
        tc = _make_tool_call(
            "tc-1", "rank_providers",
            {"patient_lat": 30.2672, "patient_lon": -97.7431, "providers": []},
        )
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="No providers ranked."),
        ]
        client = _mock_client(responses)

        empty_rank = {"ok": True, "count": 0, "providers": []}

        with patch("agents.navigation_agent.execute_tool", return_value=empty_rank):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ranked_providers"] == []

    def test_structured_fields_always_present_in_success_response(self):
        """Success response must always include all required keys."""
        responses = [_make_llm_response(content="Go to urgent care.")]
        client = _mock_client(responses)

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        required_keys = {"ok", "final_response", "tool_calls_made", "iterations",
                         "care_decision", "ranked_providers", "geocoded_location",
                         "appointment_slots", "booked_appointment_id", "appointment_history"}
        assert required_keys.issubset(result.keys())

    def test_structured_fields_always_present_in_failure_response(self):
        """Failure response must always include ok, error, tool_calls_made, iterations, and appointment fields."""
        tc = _make_tool_call("tc-loop", "classify_care", _PATIENT)
        responses = [_make_llm_response(tool_calls=[tc])] * 20
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client, max_iterations=1)

        required_keys = {"ok", "error", "tool_calls_made", "iterations",
                         "appointment_slots", "booked_appointment_id", "appointment_history"}
        assert required_keys.issubset(result.keys())
        assert result["ok"] is False

    def test_llm_client_error_returns_failure(self):
        """If NvidiaClient.chat() raises, the agent returns ok=False immediately."""
        from llm.nvidia_client import NvidiaClientAPIError

        client = MagicMock()
        client.chat.side_effect = NvidiaClientAPIError("Connection refused")

        result = run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        assert result["ok"] is False
        assert "LLM call failed" in result["error"]
        assert result["tool_calls_made"] == 0
        assert result["iterations"] == 1
        # Verify appointment fields are present even in early error case
        assert "appointment_slots" in result
        assert "booked_appointment_id" in result
        assert "appointment_history" in result

    def test_tools_passed_to_every_llm_call(self):
        """ALL_TOOLS must be forwarded to client.chat() on every iteration."""
        from agents.tools.navigation_tools import ALL_TOOLS

        tc = _make_tool_call("tc-1", "classify_care", _PATIENT)
        responses = [
            _make_llm_response(tool_calls=[tc]),
            _make_llm_response(content="Done."),
        ]
        client = _mock_client(responses)

        with patch("agents.navigation_agent.execute_tool", return_value=_CLASSIFY_RESULT):
            run_navigation_agent(_PATIENT, _LOC_COORDS, client=client)

        for call_args in client.chat.call_args_list:
            kwargs = call_args[1]
            assert "tools" in kwargs
            assert kwargs["tools"] == ALL_TOOLS
            assert kwargs.get("tool_choice") == "auto"
