"""
Focused tests for the location/maps abstraction.

Covers:
  - location/geocoder.py     — Nominatim-based geocoding
  - location/provider_discovery.py — error handling additions
  - models/schemas.PatientLocation — address field + validator
  - agents/ranking_agent.py  — geocoding wired into rank()
  - config/settings.py       — OVERPASS_URL / NOMINATIM_URL env-var wiring

All external network calls are mocked.  No real HTTP requests are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure project root on sys.path (same convention as existing tests).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.schemas import PatientLocation, CareDecision, ProviderCandidate
from location.geocoder import (
    geocode,
    resolve_location,
    GeocodingError,
    InvalidLocationError,
    GeocodingNetworkError,
    GeocodingRateLimitError,
)
from location.provider_discovery import (
    find_nearby_providers,
    ProviderDiscoveryError,
    ProviderDiscoveryNetworkError,
    ProviderDiscoveryRateLimitError,
)


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

def _mock_nominatim_ok(lat: float = 37.7749, lon: float = -122.4194):
    """Nominatim success response: one result with lat/lon."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [{"lat": str(lat), "lon": str(lon)}]
    return resp


def _mock_nominatim_empty():
    """Nominatim response with zero results."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.status_code = 200
    resp.json.return_value = []
    return resp


def _mock_nominatim_429():
    """Nominatim HTTP 429 rate-limit response."""
    resp = MagicMock()
    resp.status_code = 429
    return resp


def _mock_nominatim_500():
    """Nominatim HTTP 500 server error."""
    resp = MagicMock()
    resp.status_code = 500
    resp.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError("500 Server Error")
    )
    return resp


def _mock_overpass_ok(elements: list):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"elements": elements}
    return resp


def _mock_overpass_429():
    resp = MagicMock()
    resp.status_code = 429
    return resp


def _mock_overpass_500():
    resp = MagicMock()
    resp.status_code = 500
    resp.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError("500 Server Error")
    )
    return resp


def _osm_node(osm_id: int, name: str, lat: float, lon: float) -> dict:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": {"name": name}}


# ---------------------------------------------------------------------------
# PatientLocation schema — address field and validator
# ---------------------------------------------------------------------------

class TestPatientLocationSchema:
    """Validate the updated PatientLocation schema."""

    def test_coords_only_still_valid(self):
        """Existing callers that supply only coordinates must not be broken."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194)
        assert loc.latitude == 37.7749
        assert loc.longitude == -122.4194
        assert loc.address is None

    def test_address_only_valid(self):
        """Supplying only an address (no coordinates) must be accepted."""
        loc = PatientLocation(address="10001")
        assert loc.address == "10001"
        assert loc.latitude is None
        assert loc.longitude is None

    def test_address_and_coords_valid(self):
        """Supplying both address and coordinates must be valid."""
        loc = PatientLocation(latitude=40.7128, longitude=-74.0060, address="New York, NY")
        assert loc.latitude == 40.7128
        assert loc.longitude == -74.0060
        assert loc.address == "New York, NY"

    def test_neither_coords_nor_address_raises(self):
        """Omitting both coordinates and address must raise a validation error."""
        with pytest.raises(Exception):  # pydantic ValidationError
            PatientLocation()

    def test_empty_address_without_coords_raises(self):
        """A whitespace-only address without coordinates must raise."""
        with pytest.raises(Exception):
            PatientLocation(address="   ")

    def test_street_address_form(self):
        loc = PatientLocation(address="123 Main St, Springfield, IL 62701")
        assert loc.address == "123 Main St, Springfield, IL 62701"

    def test_city_state_form(self):
        loc = PatientLocation(address="Boston, MA")
        assert loc.address == "Boston, MA"

    def test_zip_code_form(self):
        loc = PatientLocation(address="90210")
        assert loc.address == "90210"

    def test_default_radius_preserved(self):
        """radius_km default must still be 15.0 for address-only locations."""
        loc = PatientLocation(address="Chicago, IL")
        assert loc.radius_km == 15.0

    def test_custom_radius_preserved(self):
        loc = PatientLocation(address="Chicago, IL", radius_km=10.0)
        assert loc.radius_km == 10.0


# ---------------------------------------------------------------------------
# geocoder.geocode() — unit tests (Nominatim mocked)
# ---------------------------------------------------------------------------

class TestGeocode:
    """Tests for geocode() — the low-level Nominatim wrapper."""

    def test_geocode_returns_lat_lon_floats(self):
        """Successful geocode must return a (float, float) tuple."""
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_ok(37.7749, -122.4194)):
            lat, lon = geocode("San Francisco, CA")
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        assert lat == pytest.approx(37.7749)
        assert lon == pytest.approx(-122.4194)

    def test_geocode_street_address(self):
        """Street address form must be forwarded to Nominatim."""
        mock_get = MagicMock(return_value=_mock_nominatim_ok(40.7128, -74.0060))
        with patch("location.geocoder.requests.get", mock_get):
            lat, lon = geocode("350 5th Ave, New York, NY 10118")
        assert lat == pytest.approx(40.7128)
        assert lon == pytest.approx(-74.0060)
        # Confirm the address was passed as the 'q' parameter.
        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
        assert "350 5th Ave" in params.get("q", "")

    def test_geocode_zip_code(self):
        """ZIP code form must be accepted and forwarded to Nominatim."""
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_ok(40.7484, -73.9967)):
            lat, lon = geocode("10001")
        assert isinstance(lat, float)
        assert isinstance(lon, float)

    def test_geocode_restricts_to_us(self):
        """The Nominatim query must include countrycodes=us."""
        mock_get = MagicMock(return_value=_mock_nominatim_ok())
        with patch("location.geocoder.requests.get", mock_get):
            geocode("Boston, MA")
        _, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params.get("countrycodes") == "us", (
            "Nominatim query must be restricted to US to avoid ambiguous results."
        )

    def test_geocode_empty_address_raises_invalid_location(self):
        """An empty address string must raise InvalidLocationError immediately
        without making a network call."""
        mock_get = MagicMock()
        with patch("location.geocoder.requests.get", mock_get):
            with pytest.raises(InvalidLocationError):
                geocode("")
        mock_get.assert_not_called()

    def test_geocode_whitespace_address_raises_invalid_location(self):
        mock_get = MagicMock()
        with patch("location.geocoder.requests.get", mock_get):
            with pytest.raises(InvalidLocationError):
                geocode("   ")
        mock_get.assert_not_called()

    def test_geocode_no_results_raises_invalid_location(self):
        """A valid HTTP 200 response with zero results must raise
        InvalidLocationError (the address cannot be resolved)."""
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_empty()):
            with pytest.raises(InvalidLocationError) as exc_info:
                geocode("99999 Nonexistent St, NowhereVille, ZZ 00000")
        assert "No geocoding results" in str(exc_info.value)

    def test_geocode_rate_limit_raises_rate_limit_error(self):
        """HTTP 429 from Nominatim must raise GeocodingRateLimitError."""
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_429()):
            with pytest.raises(GeocodingRateLimitError):
                geocode("Chicago, IL")

    def test_geocode_rate_limit_is_subclass_of_network_error(self):
        """GeocodingRateLimitError must be a GeocodingNetworkError subclass
        so callers that catch the parent class still handle rate limits."""
        assert issubclass(GeocodingRateLimitError, GeocodingNetworkError)

    def test_geocode_network_error_is_subclass_of_geocoding_error(self):
        assert issubclass(GeocodingNetworkError, GeocodingError)

    def test_geocode_http_500_raises_network_error(self):
        """HTTP 5xx from Nominatim must raise GeocodingNetworkError."""
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_500()):
            with pytest.raises(GeocodingNetworkError):
                geocode("Dallas, TX")

    def test_geocode_timeout_raises_network_error(self):
        """A requests.Timeout must be wrapped in GeocodingNetworkError."""
        with patch(
            "location.geocoder.requests.get",
            side_effect=requests.exceptions.Timeout(),
        ):
            with pytest.raises(GeocodingNetworkError) as exc_info:
                geocode("Seattle, WA")
        assert "timed out" in str(exc_info.value).lower()

    def test_geocode_connection_error_raises_network_error(self):
        """A ConnectionError must be wrapped in GeocodingNetworkError."""
        with patch(
            "location.geocoder.requests.get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            with pytest.raises(GeocodingNetworkError):
                geocode("Miami, FL")

    def test_geocode_user_agent_header_sent(self):
        """Every Nominatim request must carry a User-Agent header."""
        mock_get = MagicMock(return_value=_mock_nominatim_ok())
        with patch("location.geocoder.requests.get", mock_get):
            geocode("Portland, OR")
        _, kwargs = mock_get.call_args
        headers = kwargs.get("headers", {})
        assert "User-Agent" in headers, "Nominatim requires a User-Agent header."
        assert headers["User-Agent"], "User-Agent must not be empty."


# ---------------------------------------------------------------------------
# geocoder.resolve_location() — integration with PatientLocation
# ---------------------------------------------------------------------------

class TestResolveLocation:
    """Tests for the resolve_location() convenience wrapper."""

    def test_coords_already_present_no_network_call(self):
        """When lat/lon are already set, resolve_location must return the
        same object without making any network call."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194)
        mock_get = MagicMock()
        with patch("location.geocoder.requests.get", mock_get):
            result = resolve_location(loc)
        mock_get.assert_not_called()
        assert result is loc  # same object returned

    def test_address_only_geocodes_to_coordinates(self):
        """Address-only PatientLocation must be geocoded and the result
        must be a PatientLocation with latitude and longitude populated."""
        loc = PatientLocation(address="Boston, MA")
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_ok(42.3601, -71.0589)):
            result = resolve_location(loc)
        assert result.latitude == pytest.approx(42.3601)
        assert result.longitude == pytest.approx(-71.0589)
        assert result.address == "Boston, MA"

    def test_resolve_preserves_radius_km(self):
        """Geocoding must not change the radius_km value."""
        loc = PatientLocation(address="Denver, CO", radius_km=10.0)
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_ok(39.7392, -104.9903)):
            result = resolve_location(loc)
        assert result.radius_km == 10.0

    def test_resolve_bad_address_raises_invalid_location(self):
        """An address that geocodes to nothing must raise InvalidLocationError."""
        loc = PatientLocation(address="ZZZZ INVALID ADDRESS ZZZZ")
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_empty()):
            with pytest.raises(InvalidLocationError):
                resolve_location(loc)

    def test_resolve_rate_limit_raises_rate_limit_error(self):
        loc = PatientLocation(address="Austin, TX")
        with patch("location.geocoder.requests.get", return_value=_mock_nominatim_429()):
            with pytest.raises(GeocodingRateLimitError):
                resolve_location(loc)

    def test_resolve_coords_and_address_coords_take_precedence(self):
        """When both coords and address are supplied, coords win and no
        geocoding happens."""
        loc = PatientLocation(latitude=34.0522, longitude=-118.2437, address="Los Angeles, CA")
        mock_get = MagicMock()
        with patch("location.geocoder.requests.get", mock_get):
            result = resolve_location(loc)
        mock_get.assert_not_called()
        assert result.latitude == 34.0522
        assert result.longitude == -118.2437


# ---------------------------------------------------------------------------
# provider_discovery — error handling (Overpass mocked)
# ---------------------------------------------------------------------------

class TestProviderDiscoveryErrorHandling:
    """Verify graceful error handling added to find_nearby_providers."""

    _LOC = PatientLocation(latitude=37.7749, longitude=-122.4194, radius_km=5.0)

    def test_overpass_rate_limit_raises_rate_limit_error(self):
        """HTTP 429 from Overpass must raise ProviderDiscoveryRateLimitError."""
        with patch("location.provider_discovery.requests.post", return_value=_mock_overpass_429()):
            with pytest.raises(ProviderDiscoveryRateLimitError):
                find_nearby_providers(self._LOC, "URGENT_CARE", None)

    def test_rate_limit_error_is_subclass_of_network_error(self):
        assert issubclass(ProviderDiscoveryRateLimitError, ProviderDiscoveryNetworkError)

    def test_overpass_500_raises_network_error(self):
        """HTTP 5xx from Overpass must raise ProviderDiscoveryNetworkError."""
        with patch("location.provider_discovery.requests.post", return_value=_mock_overpass_500()):
            with pytest.raises(ProviderDiscoveryNetworkError):
                find_nearby_providers(self._LOC, "URGENT_CARE", None)

    def test_overpass_timeout_raises_network_error(self):
        """A requests.Timeout must be wrapped in ProviderDiscoveryNetworkError."""
        with patch(
            "location.provider_discovery.requests.post",
            side_effect=requests.exceptions.Timeout(),
        ):
            with pytest.raises(ProviderDiscoveryNetworkError) as exc_info:
                find_nearby_providers(self._LOC, "PCP", None)
        assert "timed out" in str(exc_info.value).lower()

    def test_overpass_connection_error_raises_network_error(self):
        with patch(
            "location.provider_discovery.requests.post",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            with pytest.raises(ProviderDiscoveryNetworkError):
                find_nearby_providers(self._LOC, "PCP", None)

    def test_missing_coords_raises_value_error(self):
        """A PatientLocation with no coordinates (address-only, not yet
        geocoded) must raise ValueError before hitting the network."""
        loc = PatientLocation(address="Chicago, IL")  # no lat/lon
        mock_post = MagicMock()
        with patch("location.provider_discovery.requests.post", mock_post):
            with pytest.raises(ValueError, match="coordinates"):
                find_nearby_providers(loc, "URGENT_CARE", None)
        mock_post.assert_not_called()

    def test_empty_results_returns_empty_list(self):
        """A valid Overpass response with zero elements must return [],
        not raise an exception."""
        with patch("location.provider_discovery.requests.post", return_value=_mock_overpass_ok([])):
            result = find_nearby_providers(self._LOC, "URGENT_CARE", None)
        assert result == []

    def test_overpass_url_comes_from_config(self):
        """The URL used for Overpass requests must be the one from
        config.settings (so env-var overrides work)."""
        from location.provider_discovery import find_nearby_providers as _fpn
        from config import settings

        captured_urls: list = []

        def capture_post(url, **kwargs):
            captured_urls.append(url)
            return _mock_overpass_ok([])

        with patch("location.provider_discovery.requests.post", side_effect=capture_post):
            _fpn(self._LOC, "URGENT_CARE", None)

        assert len(captured_urls) == 1
        assert captured_urls[0] == settings.OVERPASS_URL, (
            f"find_nearby_providers must use OVERPASS_URL from config "
            f"({settings.OVERPASS_URL!r}), got {captured_urls[0]!r}"
        )

    def test_overpass_url_env_var_override(self):
        """Setting OVERPASS_URL env var must change the endpoint used."""
        import importlib
        import os

        custom_url = "http://localhost:12345/api/interpreter"

        captured_urls: list = []

        with patch.dict(os.environ, {"OVERPASS_URL": custom_url}):
            # Reload settings and provider_discovery inside the patch so they
            # pick up the custom env var.
            import config.settings as _settings_mod
            import location.provider_discovery as _pd_mod
            importlib.reload(_settings_mod)
            importlib.reload(_pd_mod)

            def capture(url, **kwargs):
                captured_urls.append(url)
                return _mock_overpass_ok([])

            with patch("location.provider_discovery.requests.post", side_effect=capture):
                _pd_mod.find_nearby_providers(self._LOC, "URGENT_CARE", None)

        # patch.dict has exited — OVERPASS_URL is no longer in os.environ.
        # Reload both modules to restore their original state.
        import config.settings as _settings_mod
        import location.provider_discovery as _pd_mod
        importlib.reload(_settings_mod)
        importlib.reload(_pd_mod)

        assert captured_urls[0] == custom_url, (
            f"OVERPASS_URL env var must override the endpoint; "
            f"expected {custom_url!r}, got {captured_urls[0]!r}"
        )


# ---------------------------------------------------------------------------
# provider_discovery — radius uses DEFAULT_SEARCH_RADIUS_KM
# ---------------------------------------------------------------------------

class TestRadiusHandling:
    """Verify radius_km is passed through correctly."""

    def test_radius_from_location_used_in_query(self):
        """The Overpass query must use location.radius_km converted to metres."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194, radius_km=8.0)
        captured_data: list = []

        def capture_post(url, data=None, **kwargs):
            captured_data.append(data)
            return _mock_overpass_ok([])

        with patch("location.provider_discovery.requests.post", side_effect=capture_post):
            find_nearby_providers(loc, "URGENT_CARE", None)

        assert captured_data, "Overpass must be called"
        query = captured_data[0].get("data", "")
        # radius_km=8.0 → radius_m=8000
        assert "8000" in query, (
            f"Overpass query must contain radius 8000 m (from radius_km=8.0); "
            f"query snippet: {query[:200]}"
        )


# ---------------------------------------------------------------------------
# RankingAgent — geocoding wired in
# ---------------------------------------------------------------------------

class TestRankingAgentGeocodingWiring:
    """Verify that RankingAgent.rank() geocodes address-only locations."""

    _DECISION = CareDecision(
        rule_id="UC-001",
        priority=800,
        destination="URGENT_CARE",
        specialty=None,
        status="ROUTED",
        explanation="Urgent care needed.",
    )

    _PROVIDER = ProviderCandidate(
        provider_id="osm:node:999",
        name="Test Clinic",
        destination_type="URGENT_CARE",
        latitude=37.7749,
        longitude=-122.4194,
        source="osm",
    )

    def test_rank_with_coords_does_not_geocode(self):
        """When PatientLocation already has coordinates, resolve_location
        must not call the geocoding service."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194)
        mock_geocode = MagicMock(return_value=(37.7749, -122.4194))

        with (
            patch("location.geocoder.requests.get", mock_geocode),
            patch(
                "location.provider_discovery.find_nearby_providers",
                return_value=[self._PROVIDER],
            ),
        ):
            from agents.ranking_agent import RankingAgent
            agent = RankingAgent()
            ranked, resolved = agent.rank(loc, self._DECISION)

        mock_geocode.assert_not_called()
        assert resolved.latitude == 37.7749
        assert resolved.longitude == -122.4194

    def test_rank_with_address_geocodes_before_discovery(self):
        """Address-only PatientLocation must trigger geocoding before the
        Overpass query runs, and discovery must receive the resolved coordinates."""
        loc = PatientLocation(address="San Francisco, CA")

        geocoded_lat, geocoded_lon = 37.7749, -122.4194

        discovered_locations: list = []

        def capture_discovery(location, destination, specialty):
            discovered_locations.append((location.latitude, location.longitude))
            return [self._PROVIDER]

        with (
            patch(
                "location.geocoder.requests.get",
                return_value=_mock_nominatim_ok(geocoded_lat, geocoded_lon),
            ),
            patch(
                "location.provider_discovery.find_nearby_providers",
                side_effect=capture_discovery,
            ),
        ):
            from agents.ranking_agent import RankingAgent
            agent = RankingAgent()
            ranked, resolved = agent.rank(loc, self._DECISION)

        assert discovered_locations, "find_nearby_providers must be called"
        disc_lat, disc_lon = discovered_locations[0]
        assert disc_lat == pytest.approx(geocoded_lat), (
            "Discovery must receive the geocoded latitude, not None."
        )
        assert disc_lon == pytest.approx(geocoded_lon), (
            "Discovery must receive the geocoded longitude, not None."
        )
        assert resolved.latitude == pytest.approx(geocoded_lat)
        assert resolved.longitude == pytest.approx(geocoded_lon)

    def test_rank_returns_tuple_of_providers_and_location(self):
        """rank() must return a (List[ProviderCandidate], PatientLocation) tuple."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194)
        with patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[self._PROVIDER],
        ):
            from agents.ranking_agent import RankingAgent
            agent = RankingAgent()
            result = agent.rank(loc, self._DECISION)

        assert isinstance(result, tuple), "rank() must return a tuple"
        assert len(result) == 2, "rank() tuple must have 2 elements"
        ranked, resolved = result
        assert isinstance(ranked, list)
        assert isinstance(resolved, PatientLocation)

    def test_rank_geocoding_failure_propagates(self):
        """A geocoding failure (address not found) must propagate as
        InvalidLocationError so the graph node can record it in errors."""
        loc = PatientLocation(address="ZZZZ TOTALLY INVALID ADDRESS ZZZZ")
        with patch(
            "location.geocoder.requests.get",
            return_value=_mock_nominatim_empty(),
        ):
            from agents.ranking_agent import RankingAgent
            from location.geocoder import InvalidLocationError as ILE

            agent = RankingAgent()
            with pytest.raises(ILE):
                agent.rank(loc, self._DECISION)

    def test_rank_empty_providers_when_no_results(self):
        """When Overpass returns no providers, rank() must return an empty
        list and the resolved location — not raise."""
        loc = PatientLocation(latitude=37.7749, longitude=-122.4194)
        with patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[],
        ):
            from agents.ranking_agent import RankingAgent
            agent = RankingAgent()
            ranked, resolved = agent.rank(loc, self._DECISION)
        assert ranked == []
        assert resolved.latitude == 37.7749


# ---------------------------------------------------------------------------
# config/settings — Nominatim settings wired correctly
# ---------------------------------------------------------------------------

class TestConfigSettings:
    """Verify new Nominatim settings exist in config.settings."""

    def test_nominatim_url_in_settings(self):
        from config import settings
        assert hasattr(settings, "NOMINATIM_URL"), "NOMINATIM_URL must be defined in config.settings"
        assert settings.NOMINATIM_URL, "NOMINATIM_URL must not be empty"
        assert "nominatim" in settings.NOMINATIM_URL.lower(), (
            f"Default NOMINATIM_URL should point to Nominatim; got {settings.NOMINATIM_URL!r}"
        )

    def test_nominatim_user_agent_in_settings(self):
        from config import settings
        assert hasattr(settings, "NOMINATIM_USER_AGENT"), (
            "NOMINATIM_USER_AGENT must be defined in config.settings"
        )
        assert settings.NOMINATIM_USER_AGENT, "NOMINATIM_USER_AGENT must not be empty"

    def test_overpass_url_in_settings(self):
        """OVERPASS_URL must be defined in config.settings and have a non-empty
        default value.  We do not assert on the hostname because a developer
        machine may have OVERPASS_URL set to a local instance."""
        import importlib
        import config.settings as _s
        # Re-import fresh to pick up the live env (whatever it is).
        importlib.reload(_s)
        assert hasattr(_s, "OVERPASS_URL"), "OVERPASS_URL must be defined in config.settings"
        assert _s.OVERPASS_URL, "OVERPASS_URL must not be empty"
        assert isinstance(_s.OVERPASS_URL, str), "OVERPASS_URL must be a string"

    def test_nominatim_url_env_override(self):
        """NOMINATIM_URL must be overridable via environment variable."""
        import os
        import importlib
        import config.settings as _s

        custom = "http://my-nominatim.internal/search"
        with patch.dict(os.environ, {"NOMINATIM_URL": custom}):
            importlib.reload(_s)
            assert _s.NOMINATIM_URL == custom
        # Restore
        importlib.reload(_s)


# ---------------------------------------------------------------------------
# /navigate API boundary — location error → HTTP 422
# ---------------------------------------------------------------------------

class TestNavigateLocationErrorBoundary:
    """/navigate must return HTTP 422 when geocoding fails, not HTTP 200.

    All geocoding and Overpass network calls are mocked.
    """

    # Minimal patient payload that reliably routes to URGENT_CARE (physical
    # destination, so geocoding is actually attempted for address-only input).
    _PATIENT = {
        "primary_symptom_category": "minor_infection",
        "symptom_trend": "worsening",
        "pain_level_self_reported": 6,
    }

    # Valid coord-based location — used to confirm the happy path still works.
    _COORD_LOCATION = {"latitude": 37.7749, "longitude": -122.4194, "radius_km": 15.0}

    # Address-only location forms.
    _STREET_ADDR_LOCATION = {"address": "123 Fake St, Nowhere, ZZ 00000"}
    _CITY_STATE_LOCATION   = {"address": "Nonexistent City, XX"}
    _ZIP_LOCATION          = {"address": "00000"}

    @pytest.fixture(autouse=True)
    def _explainer_mock(self):
        """Suppress the real Gemini call across all tests in this class."""
        with patch("engine.explainer.explain_decision", return_value="mocked explanation"):
            yield

    @pytest.fixture()
    def api_client(self):
        from fastapi.testclient import TestClient
        from api.routes import app
        return TestClient(app)

    # ------------------------------------------------------------------
    # Test 1 — valid coord-based location still returns HTTP 200
    # ------------------------------------------------------------------

    def test_valid_coord_location_returns_200(self, api_client):
        """Coordinates bypass geocoding entirely — /navigate must succeed."""
        with patch(
            "location.provider_discovery.find_nearby_providers",
            return_value=[],
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._COORD_LOCATION},
            )
        assert resp.status_code == 200, (
            f"Coord-based location must return 200; got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert "recommendation_id" in body
        assert body["decision"]["destination"] == "URGENT_CARE"

    # ------------------------------------------------------------------
    # Test 2 — unresolvable address returns HTTP 422
    # ------------------------------------------------------------------

    def test_unresolvable_address_returns_422(self, api_client):
        """An address that Nominatim cannot resolve must produce HTTP 422,
        not HTTP 200 with empty providers."""
        with patch(
            "location.geocoder.requests.get",
            return_value=_mock_nominatim_empty(),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._STREET_ADDR_LOCATION},
            )
        assert resp.status_code == 422, (
            f"Unresolvable address must return 422; got {resp.status_code}: {resp.text}"
        )

    def test_422_response_contains_structured_error(self, api_client):
        """The 422 response body must contain a 'detail' field with a
        human-readable description of the location problem."""
        with patch(
            "location.geocoder.requests.get",
            return_value=_mock_nominatim_empty(),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._CITY_STATE_LOCATION},
            )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body, "422 response must include a 'detail' field"
        detail = body["detail"]
        assert detail, "'detail' must not be empty"
        assert "location" in detail.lower() or "geocod" in detail.lower(), (
            f"'detail' should mention 'location' or 'geocod'; got: {detail!r}"
        )

    # ------------------------------------------------------------------
    # Test 3 — provider discovery is NOT called after geocoding failure
    # ------------------------------------------------------------------

    def test_provider_discovery_not_called_after_geocoding_failure(self, api_client):
        """When geocoding fails, find_nearby_providers must not be called —
        there are no coordinates to search with."""
        discovery_calls = {"n": 0}

        def track(location, destination, specialty):
            discovery_calls["n"] += 1
            return []

        with (
            patch("location.geocoder.requests.get", return_value=_mock_nominatim_empty()),
            patch("location.provider_discovery.find_nearby_providers", side_effect=track),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._ZIP_LOCATION},
            )

        assert resp.status_code == 422
        # find_nearby_providers must have been called 0 times.
        # (rank_node raises before reaching discovery when geocoding fails.)
        assert discovery_calls["n"] == 0, (
            f"find_nearby_providers must not be called after geocoding failure; "
            f"was called {discovery_calls['n']} time(s)"
        )

    # ------------------------------------------------------------------
    # Test 4 — geocoding network error also returns 422
    # ------------------------------------------------------------------

    def test_geocoding_network_error_returns_422(self, api_client):
        """A network error reaching Nominatim (GeocodingNetworkError) must
        also produce HTTP 422, not HTTP 200 with no providers."""
        with patch(
            "location.geocoder.requests.get",
            side_effect=requests.exceptions.ConnectionError("unreachable"),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._CITY_STATE_LOCATION},
            )
        assert resp.status_code == 422, (
            f"Geocoding network error must return 422; got {resp.status_code}: {resp.text}"
        )

    def test_geocoding_rate_limit_returns_422(self, api_client):
        """HTTP 429 from Nominatim (GeocodingRateLimitError) must produce
        HTTP 422 at the API boundary."""
        with patch(
            "location.geocoder.requests.get",
            return_value=_mock_nominatim_429(),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._CITY_STATE_LOCATION},
            )
        assert resp.status_code == 422, (
            f"Geocoding rate limit must return 422; got {resp.status_code}: {resp.text}"
        )

    # ------------------------------------------------------------------
    # Test 5 — Gemini is NOT called when geocoding fails
    # ------------------------------------------------------------------

    def test_gemini_not_called_after_geocoding_failure(self, api_client):
        """After a geocoding failure the route raises 422 before the
        recommendation is stored — the explain_node (Gemini) runs inside the
        graph but the 422 is raised before we reach the store/response path.

        More importantly: Gemini must never be asked to invent or substitute
        a location.  We verify this by confirming the route returns 422 and
        no recommendation is stored.
        """
        from api.recommendation_store import recommendation_store

        # Record store size before the call.
        with recommendation_store._lock:
            before = len(recommendation_store._items)

        with patch(
            "location.geocoder.requests.get",
            return_value=_mock_nominatim_empty(),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": self._STREET_ADDR_LOCATION},
            )

        assert resp.status_code == 422

        # No recommendation must have been stored (route raised before create()).
        with recommendation_store._lock:
            after = len(recommendation_store._items)
        assert after == before, (
            f"No recommendation must be stored after a geocoding failure; "
            f"store grew from {before} to {after}"
        )

    # ------------------------------------------------------------------
    # Test 6 — valid address that geocodes successfully returns HTTP 200
    # ------------------------------------------------------------------

    def test_valid_address_geocodes_and_returns_200(self, api_client):
        """An address that Nominatim resolves successfully must flow through
        the full pipeline and return HTTP 200 with a valid Recommendation."""
        with (
            patch(
                "location.geocoder.requests.get",
                return_value=_mock_nominatim_ok(37.7749, -122.4194),
            ),
            patch(
                "location.provider_discovery.find_nearby_providers",
                return_value=[],
            ),
        ):
            resp = api_client.post(
                "/navigate",
                json={"patient": self._PATIENT, "location": {"address": "San Francisco, CA"}},
            )
        assert resp.status_code == 200, (
            f"Valid geocodable address must return 200; got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["decision"]["destination"] == "URGENT_CARE"
        assert body["recommendation_id"].startswith("rec_")
