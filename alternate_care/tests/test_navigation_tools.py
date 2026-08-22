"""
Unit tests for agents/tools/navigation_tools.py.

All underlying deterministic functions are mocked.
No real API calls (Nominatim, Overpass, NVIDIA) are made.

Test coverage:
  1.  classify_care  — happy path
  2.  classify_care  — missing required field
  3.  classify_care  — underlying classifier raises
  4.  classify_care  — output is JSON-serializable
  5.  classify_care  — correct function called with correct args
  6.  geocode_location  — happy path
  7.  geocode_location  — InvalidLocationError → "error"
  8.  geocode_location  — GeocodingNetworkError → "error"
  9.  geocode_location  — output is JSON-serializable
  10. geocode_location  — correct function called with correct args
  11. discover_providers  — happy path (physical destination)
  12. discover_providers  — TELEHEALTH returns empty list without API call
  13. discover_providers  — ProviderDiscoveryError → "error"
  14. discover_providers  — output is JSON-serializable
  15. discover_providers  — correct args forwarded to find_nearby_providers
  16. rank_providers  — happy path
  17. rank_providers  — malformed provider dict → "error"
  18. rank_providers  — output is JSON-serializable
  19. rank_providers  — correct args forwarded to underlying rank_providers
  20. rank_providers  — has_pcp_flag and top_n forwarded correctly
  21. execute_tool  — dispatches to classify_care
  22. execute_tool  — dispatches to geocode_location
  23. execute_tool  — dispatches to discover_providers
  24. execute_tool  — dispatches to rank_providers
  25. execute_tool  — unknown tool name returns error
  26. ALL_TOOLS     — contains exactly 4 tool definitions
  27. ALL_TOOLS     — every tool has required structure fields
  28. ALL_TOOLS     — tool names match callable registry
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.alternate_care.agents.tools.navigation_tools import (
    ALL_TOOLS,
    CLASSIFY_CARE_TOOL_DEF,
    DISCOVER_PROVIDERS_TOOL_DEF,
    GEOCODE_LOCATION_TOOL_DEF,
    RANK_PROVIDERS_TOOL_DEF,
    classify_care,
    discover_providers,
    execute_tool,
    geocode_location,
    rank_providers,
)
from app.services.alternate_care.location.geocoder import (
    GeocodingNetworkError,
    GeocodingRateLimitError,
    InvalidLocationError,
)
from app.services.alternate_care.location.provider_discovery import (
    ProviderDiscoveryNetworkError,
    ProviderDiscoveryRateLimitError,
)
from app.services.alternate_care.models.schemas import CareDecision, ProviderCandidate


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_care_decision(**kwargs) -> CareDecision:
    defaults = dict(
        rule_id="UC-001-INFECTION",
        priority=30,
        destination="URGENT_CARE",
        specialty=None,
        status="DOCUMENT_SUPPORTED",
        explanation="Same-day evaluation appropriate.",
    )
    defaults.update(kwargs)
    return CareDecision(**defaults)


def _make_provider(**kwargs) -> ProviderCandidate:
    defaults = dict(
        provider_id="osm:node:1001",
        name="City Urgent Care",
        destination_type="URGENT_CARE",
        specialty=None,
        latitude=30.2701,
        longitude=-97.7448,
        address=None,
        distance_km=None,
        score=None,
        source="osm",
    )
    defaults.update(kwargs)
    return ProviderCandidate(**defaults)


def _provider_dict(**kwargs) -> dict:
    return _make_provider(**kwargs).model_dump()


_PATIENT_ARGS = {
    "primary_symptom_category": "minor_infection",
    "symptom_trend": "worsening",
    "pain_level_self_reported": 6,
}

_LAT, _LON = 30.2672, -97.7431


# ===========================================================================
# 1–5. classify_care
# ===========================================================================

class TestClassifyCare:

    def test_happy_path_returns_care_decision_fields(self):
        """Successful classify_care returns all CareDecision fields with ok=True."""
        decision = _make_care_decision()
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            result = classify_care(_PATIENT_ARGS)

        assert result["ok"] is True
        assert result["rule_id"] == "UC-001-INFECTION"
        assert result["destination"] == "URGENT_CARE"
        assert result["specialty"] is None
        assert result["priority"] == 30
        assert result["status"] == "DOCUMENT_SUPPORTED"
        assert "explanation" in result

    def test_missing_primary_symptom_category_returns_error(self):
        """PatientFeatures requires primary_symptom_category; missing it → error."""
        result = classify_care({})
        assert result["ok"] is False
        assert "error" in result
        assert result["error"]  # non-empty

    def test_classifier_raises_runtime_error_returns_error(self):
        """If CareClassifier.classify raises RuntimeError, tool returns error dict."""
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.side_effect = RuntimeError("No rule matched")
            result = classify_care(_PATIENT_ARGS)

        assert result["ok"] is False
        assert "No rule matched" in result["error"]

    def test_output_is_json_serializable(self):
        """Every field in the result must round-trip through json.dumps/loads."""
        decision = _make_care_decision()
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            result = classify_care(_PATIENT_ARGS)

        serialized = json.dumps(result)
        restored = json.loads(serialized)
        assert restored["destination"] == "URGENT_CARE"

    def test_correct_function_called_with_patient_features(self):
        """classify_care must call _classifier.classify with a PatientFeatures object."""
        from models.schemas import PatientFeatures

        decision = _make_care_decision()
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            classify_care(_PATIENT_ARGS)

        mock_clf.classify.assert_called_once()
        arg = mock_clf.classify.call_args[0][0]
        assert isinstance(arg, PatientFeatures)
        assert arg.primary_symptom_category == "minor_infection"

    def test_specialist_decision_includes_specialty(self):
        """When destination is SPECIALIST, specialty is returned."""
        decision = _make_care_decision(
            rule_id="SPEC-002-PULM",
            destination="SPECIALIST",
            specialty="PULMONOLOGY",
            priority=50,
        )
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            result = classify_care({
                "primary_symptom_category": "mild_breathing_difficulty",
                "copd_asthma_flag": 1,
                "chronic_condition_count": 3,
            })

        assert result["ok"] is True
        assert result["destination"] == "SPECIALIST"
        assert result["specialty"] == "PULMONOLOGY"

    def test_extra_patient_fields_accepted(self):
        """PatientFeatures has extra='allow'; extra fields must not cause failure."""
        decision = _make_care_decision()
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            result = classify_care({
                **_PATIENT_ARGS,
                "unknown_field_xyz": "should be silently allowed",
            })
        assert result["ok"] is True


# ===========================================================================
# 6–10. geocode_location
# ===========================================================================

class TestGeocodeLocation:

    def test_happy_path_returns_lat_lon(self):
        """Successful geocode returns ok=True with latitude and longitude."""
        with patch("agents.tools.navigation_tools.geocode", return_value=(_LAT, _LON)):
            result = geocode_location("Austin, TX 78701")

        assert result["ok"] is True
        assert result["latitude"] == _LAT
        assert result["longitude"] == _LON
        assert result["address"] == "Austin, TX 78701"

    def test_invalid_location_error_returns_error(self):
        """InvalidLocationError → ok=False with error message."""
        with patch(
            "agents.tools.navigation_tools.geocode",
            side_effect=InvalidLocationError("No geocoding results found for address: 'ZZZZ'"),
        ):
            result = geocode_location("ZZZZ INVALID ZZZZ")

        assert result["ok"] is False
        assert "error" in result
        assert result["error"]

    def test_geocoding_network_error_returns_error(self):
        """GeocodingNetworkError → ok=False with error message."""
        with patch(
            "agents.tools.navigation_tools.geocode",
            side_effect=GeocodingNetworkError("Connection refused"),
        ):
            result = geocode_location("Austin, TX")

        assert result["ok"] is False
        assert "error" in result

    def test_rate_limit_error_returns_error(self):
        """GeocodingRateLimitError → ok=False with error message."""
        with patch(
            "agents.tools.navigation_tools.geocode",
            side_effect=GeocodingRateLimitError("HTTP 429"),
        ):
            result = geocode_location("Boston, MA")

        assert result["ok"] is False
        assert "error" in result

    def test_output_is_json_serializable(self):
        with patch("agents.tools.navigation_tools.geocode", return_value=(_LAT, _LON)):
            result = geocode_location("Austin, TX")

        serialized = json.dumps(result)
        restored = json.loads(serialized)
        assert restored["latitude"] == _LAT

    def test_correct_function_called_with_address(self):
        """geocode_location must call geocode() with the exact address string."""
        with patch("agents.tools.navigation_tools.geocode", return_value=(_LAT, _LON)) as mock_gc:
            geocode_location("Austin, TX 78701")

        mock_gc.assert_called_once_with("Austin, TX 78701")


# ===========================================================================
# 11–15. discover_providers
# ===========================================================================

class TestDiscoverProviders:

    def test_happy_path_returns_providers(self):
        """Successful discover returns ok=True with providers list."""
        provider = _make_provider()
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[provider],
        ):
            result = discover_providers(
                latitude=_LAT,
                longitude=_LON,
                destination="URGENT_CARE",
            )

        assert result["ok"] is True
        assert result["count"] == 1
        assert len(result["providers"]) == 1
        assert result["providers"][0]["provider_id"] == "osm:node:1001"
        assert result["destination"] == "URGENT_CARE"
        assert result["specialty"] is None

    def test_telehealth_returns_empty_without_api_call(self):
        """TELEHEALTH destination skips Overpass; find_nearby_providers returns []."""
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[],
        ) as mock_fn:
            result = discover_providers(
                latitude=_LAT,
                longitude=_LON,
                destination="TELEHEALTH",
            )

        assert result["ok"] is True
        assert result["count"] == 0
        assert result["providers"] == []
        # find_nearby_providers is still called (it handles TELEHEALTH internally)
        mock_fn.assert_called_once()

    def test_discovery_error_returns_error(self):
        """ProviderDiscoveryNetworkError → ok=False with error message."""
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            side_effect=ProviderDiscoveryNetworkError("Overpass unreachable"),
        ):
            result = discover_providers(
                latitude=_LAT,
                longitude=_LON,
                destination="URGENT_CARE",
            )

        assert result["ok"] is False
        assert "error" in result

    def test_rate_limit_error_returns_error(self):
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            side_effect=ProviderDiscoveryRateLimitError("HTTP 429"),
        ):
            result = discover_providers(
                latitude=_LAT,
                longitude=_LON,
                destination="PCP",
            )

        assert result["ok"] is False
        assert "error" in result

    def test_output_is_json_serializable(self):
        provider = _make_provider()
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[provider],
        ):
            result = discover_providers(_LAT, _LON, "URGENT_CARE")

        serialized = json.dumps(result)
        restored = json.loads(serialized)
        assert restored["count"] == 1

    def test_correct_args_forwarded_to_find_nearby_providers(self):
        """discover_providers must construct PatientLocation and pass it correctly."""
        from models.schemas import PatientLocation

        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[],
        ) as mock_fn:
            discover_providers(
                latitude=_LAT,
                longitude=_LON,
                destination="SPECIALIST",
                specialty="PULMONOLOGY",
                radius_km=10.0,
            )

        mock_fn.assert_called_once()
        call_args = mock_fn.call_args
        loc_arg = call_args[1]["location"] if call_args[1] else call_args[0][0]
        assert isinstance(loc_arg, PatientLocation)
        assert loc_arg.latitude == _LAT
        assert loc_arg.longitude == _LON
        assert loc_arg.radius_km == 10.0

        dest_arg = call_args[1].get("destination") or call_args[0][1]
        assert dest_arg == "SPECIALIST"

        spec_arg = call_args[1].get("specialty") or call_args[0][2]
        assert spec_arg == "PULMONOLOGY"

    def test_empty_results_returns_ok_with_zero_count(self):
        """No providers found is not an error — returns ok=True count=0."""
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[],
        ):
            result = discover_providers(_LAT, _LON, "URGENT_CARE")

        assert result["ok"] is True
        assert result["count"] == 0
        assert result["providers"] == []


# ===========================================================================
# 16–20. rank_providers
# ===========================================================================

class TestRankProviders:

    def _ranked_provider(self) -> ProviderCandidate:
        p = _make_provider()
        p.distance_km = 0.36
        p.score = 0.986
        return p

    def test_happy_path_returns_ranked_providers(self):
        """Successful rank returns ok=True with scored providers."""
        ranked = [self._ranked_provider()]
        with patch(
            "agents.tools.navigation_tools._rank_providers",
            return_value=ranked,
        ):
            result = rank_providers(
                patient_lat=_LAT,
                patient_lon=_LON,
                providers=[_provider_dict()],
            )

        assert result["ok"] is True
        assert result["count"] == 1
        p = result["providers"][0]
        assert p["distance_km"] == 0.36
        assert p["score"] == 0.986

    def test_malformed_provider_dict_returns_error(self):
        """A provider dict missing required fields → Pydantic error → ok=False."""
        result = rank_providers(
            patient_lat=_LAT,
            patient_lon=_LON,
            providers=[{"bad_key": "no required fields here"}],
        )
        assert result["ok"] is False
        assert "error" in result

    def test_output_is_json_serializable(self):
        ranked = [self._ranked_provider()]
        with patch("agents.tools.navigation_tools._rank_providers", return_value=ranked):
            result = rank_providers(_LAT, _LON, [_provider_dict()])

        serialized = json.dumps(result)
        restored = json.loads(serialized)
        assert restored["count"] == 1

    def test_correct_args_forwarded_to_rank_providers_function(self):
        """rank_providers tool must pass patient_lat, patient_lon, candidates, flags."""
        from models.schemas import ProviderCandidate as PC

        with patch(
            "agents.tools.navigation_tools._rank_providers",
            return_value=[],
        ) as mock_fn:
            rank_providers(
                patient_lat=_LAT,
                patient_lon=_LON,
                providers=[_provider_dict()],
                has_pcp_flag=1,
                top_n=3,
            )

        mock_fn.assert_called_once()
        _, kwargs = mock_fn.call_args
        assert kwargs["patient_lat"] == _LAT
        assert kwargs["patient_lon"] == _LON
        assert kwargs["has_pcp_flag"] == 1
        assert kwargs["top_n"] == 3
        assert all(isinstance(c, PC) for c in kwargs["candidates"])

    def test_has_pcp_flag_and_top_n_defaults(self):
        """has_pcp_flag defaults to None and top_n defaults to 5."""
        with patch(
            "agents.tools.navigation_tools._rank_providers",
            return_value=[],
        ) as mock_fn:
            rank_providers(
                patient_lat=_LAT,
                patient_lon=_LON,
                providers=[],
            )

        _, kwargs = mock_fn.call_args
        assert kwargs["has_pcp_flag"] is None
        assert kwargs["top_n"] == 5

    def test_empty_providers_returns_ok_with_zero_count(self):
        """Empty input list returns ok=True count=0."""
        with patch("agents.tools.navigation_tools._rank_providers", return_value=[]):
            result = rank_providers(_LAT, _LON, [])

        assert result["ok"] is True
        assert result["count"] == 0
        assert result["providers"] == []


# ===========================================================================
# 21–25. execute_tool
# ===========================================================================

class TestExecuteTool:

    def test_dispatches_to_classify_care(self):
        """execute_tool('classify_care', args) calls classify_care(args)."""
        decision = _make_care_decision()
        with patch("agents.tools.navigation_tools._classifier") as mock_clf:
            mock_clf.classify.return_value = decision
            result = execute_tool("classify_care", _PATIENT_ARGS)

        assert result["ok"] is True
        assert result["destination"] == "URGENT_CARE"

    def test_dispatches_to_geocode_location(self):
        """execute_tool('geocode_location', args) calls geocode_location(args)."""
        with patch("agents.tools.navigation_tools.geocode", return_value=(_LAT, _LON)):
            result = execute_tool("geocode_location", {"address": "Austin, TX"})

        assert result["ok"] is True
        assert result["latitude"] == _LAT

    def test_dispatches_to_discover_providers(self):
        """execute_tool('discover_providers', args) calls discover_providers(args)."""
        with patch(
            "agents.tools.navigation_tools.find_nearby_providers",
            return_value=[],
        ):
            result = execute_tool(
                "discover_providers",
                {"latitude": _LAT, "longitude": _LON, "destination": "URGENT_CARE"},
            )

        assert result["ok"] is True
        assert result["count"] == 0

    def test_dispatches_to_rank_providers(self):
        """execute_tool('rank_providers', args) calls rank_providers(args)."""
        with patch("agents.tools.navigation_tools._rank_providers", return_value=[]):
            result = execute_tool(
                "rank_providers",
                {"patient_lat": _LAT, "patient_lon": _LON, "providers": []},
            )

        assert result["ok"] is True
        assert result["count"] == 0

    def test_unknown_tool_name_returns_error(self):
        """An unrecognized tool name must return ok=False with a clear error."""
        result = execute_tool("does_not_exist", {})
        assert result["ok"] is False
        assert "Unknown tool" in result["error"]
        assert "does_not_exist" in result["error"]

    def test_unknown_tool_does_not_raise(self):
        """execute_tool must never raise — it always returns a dict."""
        try:
            result = execute_tool("no_such_tool", {"x": 1})
        except Exception as exc:
            pytest.fail(f"execute_tool raised unexpectedly: {exc}")
        assert isinstance(result, dict)

    def test_result_always_json_serializable(self):
        """execute_tool output must always be JSON-serializable (both success and error)."""
        # Success path
        with patch("agents.tools.navigation_tools.geocode", return_value=(_LAT, _LON)):
            ok_result = execute_tool("geocode_location", {"address": "Austin, TX"})
        json.dumps(ok_result)  # must not raise

        # Error path
        err_result = execute_tool("nonexistent", {})
        json.dumps(err_result)  # must not raise


# ===========================================================================
# 26–28. ALL_TOOLS structure
# ===========================================================================

class TestAllTools:

    def test_all_tools_contains_exactly_four_definitions(self):
        assert len(ALL_TOOLS) == 4

    def test_every_tool_has_type_function(self):
        for tool in ALL_TOOLS:
            assert tool["type"] == "function", (
                f"Tool missing type='function': {tool}"
            )

    def test_every_tool_has_name(self):
        for tool in ALL_TOOLS:
            assert "name" in tool["function"], (
                f"Tool missing 'name': {tool}"
            )
            assert tool["function"]["name"], "Tool name must not be empty"

    def test_every_tool_has_description(self):
        for tool in ALL_TOOLS:
            assert "description" in tool["function"], (
                f"Tool missing 'description': {tool}"
            )
            assert tool["function"]["description"]

    def test_every_tool_has_parameters_with_type_object(self):
        for tool in ALL_TOOLS:
            params = tool["function"].get("parameters", {})
            assert params.get("type") == "object", (
                f"parameters.type must be 'object' for {tool['function']['name']}"
            )

    def test_tool_names_match_callable_registry(self):
        """Tool def names must exactly match the dispatch registry keys."""
        from agents.tools.navigation_tools import _TOOL_REGISTRY
        all_tool_names = {t["function"]["name"] for t in ALL_TOOLS}
        registry_names = set(_TOOL_REGISTRY.keys())
        assert all_tool_names == registry_names, (
            f"Mismatch — ALL_TOOLS names: {all_tool_names}, "
            f"registry names: {registry_names}"
        )

    def test_classify_care_requires_primary_symptom_category(self):
        """classify_care must list primary_symptom_category as required."""
        fn = CLASSIFY_CARE_TOOL_DEF["function"]
        assert "primary_symptom_category" in fn["parameters"].get("required", [])

    def test_geocode_location_requires_address(self):
        """geocode_location must list address as required."""
        fn = GEOCODE_LOCATION_TOOL_DEF["function"]
        assert "address" in fn["parameters"].get("required", [])

    def test_discover_providers_requires_lat_lon_destination(self):
        """discover_providers must require latitude, longitude, destination."""
        fn = DISCOVER_PROVIDERS_TOOL_DEF["function"]
        required = fn["parameters"].get("required", [])
        assert "latitude" in required
        assert "longitude" in required
        assert "destination" in required

    def test_rank_providers_requires_patient_lat_lon_providers(self):
        """rank_providers must require patient_lat, patient_lon, providers."""
        fn = RANK_PROVIDERS_TOOL_DEF["function"]
        required = fn["parameters"].get("required", [])
        assert "patient_lat" in required
        assert "patient_lon" in required
        assert "providers" in required

    def test_discover_providers_destination_enum_contains_all_destinations(self):
        """destination parameter must enumerate all 5 valid destinations."""
        fn = DISCOVER_PROVIDERS_TOOL_DEF["function"]
        enum_values = fn["parameters"]["properties"]["destination"]["enum"]
        expected = {"PCP", "URGENT_CARE", "SPECIALIST", "TELEHEALTH", "DENTISTRY"}
        assert set(enum_values) == expected, (
            f"Destination enum {set(enum_values)} does not match expected {expected}"
        )

    def test_all_tools_serializable_as_json(self):
        """ALL_TOOLS must round-trip through JSON without error."""
        serialized = json.dumps(ALL_TOOLS)
        restored = json.loads(serialized)
        assert len(restored) == 4
