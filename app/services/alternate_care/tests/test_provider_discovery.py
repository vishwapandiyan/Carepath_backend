"""
Unit tests for location/provider_discovery.py — focused on the
OSM node/way deduplication behaviour added in Step 10D.

Overpass HTTP is mocked in every test; no network calls are made.
"""

from __future__ import annotations
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.alternate_care.models.schemas import PatientLocation
from app.services.alternate_care.location.provider_discovery import find_nearby_providers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOCATION = PatientLocation(latitude=37.7749, longitude=-122.4194, radius_km=5.0)


def _mock_overpass(elements: list):
    """Return a mock requests.Response that yields the given OSM elements."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"elements": elements}
    return resp


def _node(osm_id: int, name: str, lat: float, lon: float) -> dict:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": {"name": name}}


def _way(osm_id: int, name: str, lat: float, lon: float) -> dict:
    """Way elements return coordinates under 'center'."""
    return {"type": "way", "id": osm_id, "center": {"lat": lat, "lon": lon}, "tags": {"name": name}}


# ---------------------------------------------------------------------------
# Step 10D — deduplication tests
# ---------------------------------------------------------------------------

class TestProviderDeduplication:
    """OSM node/way duplicate suppression."""

    def test_node_and_way_same_name_same_location_returns_one_candidate(self):
        """A node and a way that represent the same physical clinic
        (identical name, near-identical coordinates) must produce exactly
        one ProviderCandidate — the node, which appears first."""
        elements = [
            _node(1001, "City Urgent Care", 37.7749, -122.4194),
            _way(2001, "City Urgent Care", 37.77492, -122.41941),  # centroid ~2m away
        ]
        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass(elements)):
            candidates = find_nearby_providers(_LOCATION, "URGENT_CARE", None)

        assert len(candidates) == 1, (
            f"Expected 1 candidate after deduplication; got {len(candidates)}: "
            f"{[c.provider_id for c in candidates]}"
        )
        # First occurrence (node) is kept
        assert candidates[0].provider_id == "osm:node:1001"
        assert candidates[0].name == "City Urgent Care"

    def test_same_name_different_location_not_deduplicated(self):
        """Two providers with the same name at meaningfully different
        coordinates (>~111 m apart) must both be returned — a chain clinic
        with two branches should not be collapsed into one."""
        elements = [
            _node(1001, "MedPlus Clinic", 37.7749, -122.4194),
            _node(1002, "MedPlus Clinic", 37.786, -122.430),  # ~1.3 km away
        ]
        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass(elements)):
            candidates = find_nearby_providers(_LOCATION, "URGENT_CARE", None)

        assert len(candidates) == 2, (
            f"Same-name providers at different locations must not be collapsed; "
            f"got {len(candidates)}"
        )
        ids = {c.provider_id for c in candidates}
        assert "osm:node:1001" in ids
        assert "osm:node:1002" in ids

    def test_unnamed_elements_are_still_filtered(self):
        """Elements without a name tag are discarded regardless of deduplication."""
        elements = [
            {"type": "node", "id": 9001, "lat": 37.7749, "lon": -122.4194, "tags": {}},
            _node(9002, "Named Clinic", 37.7749, -122.4194),
        ]
        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass(elements)):
            candidates = find_nearby_providers(_LOCATION, "URGENT_CARE", None)

        assert len(candidates) == 1
        assert candidates[0].name == "Named Clinic"

    def test_three_elements_two_duplicates_one_distinct(self):
        """node + way duplicate pair + one genuinely distinct provider.
        Result must be exactly 2 candidates."""
        elements = [
            _node(1001, "Downtown Clinic", 37.7749, -122.4194),
            _way(2001, "Downtown Clinic", 37.77491, -122.41939),  # duplicate of above
            _node(1002, "Westside Medical", 37.780, -122.425),    # distinct
        ]
        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass(elements)):
            candidates = find_nearby_providers(_LOCATION, "URGENT_CARE", None)

        assert len(candidates) == 2
        names = {c.name for c in candidates}
        assert names == {"Downtown Clinic", "Westside Medical"}

    def test_telehealth_returns_empty_without_http_call(self):
        """TELEHEALTH must return [] immediately, no Overpass call made."""
        mock_post = MagicMock()
        with patch("location.provider_discovery.requests.post", mock_post):
            candidates = find_nearby_providers(_LOCATION, "TELEHEALTH", None)

        assert candidates == []
        mock_post.assert_not_called()

    def test_provider_id_format_preserved(self):
        """provider_id must still follow 'osm:{type}:{id}' convention."""
        elements = [_node(42, "Sample Clinic", 37.7749, -122.4194)]
        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass(elements)):
            candidates = find_nearby_providers(_LOCATION, "URGENT_CARE", None)

        assert candidates[0].provider_id == "osm:node:42"


# ---------------------------------------------------------------------------
# Step 10E — Dental → DENTISTRY destination routing
# ---------------------------------------------------------------------------

class TestDentalOSMMapping:
    """Verify DENTISTRY (first-class destination) maps to the dentist OSM tag."""

    def test_dentistry_destination_maps_to_dentist_tag(self):
        """tags_for('DENTISTRY', None) must return the dentist amenity tag."""
        from location.osm_tag_map import tags_for
        tags = tags_for("DENTISTRY", None)
        assert '["amenity"="dentist"]' in tags, (
            f"DENTISTRY must map to dentist tag; got {tags}"
        )

    def test_dental_provider_discovered_via_dentistry_destination(self):
        """End-to-end: find_nearby_providers with DENTISTRY destination
        returns a dental provider from the mocked Overpass response."""
        dental_node = _node(5001, "City Dental Clinic", 37.7749, -122.4194)
        dental_node["tags"]["amenity"] = "dentist"

        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass([dental_node])):
            candidates = find_nearby_providers(_LOCATION, "DENTISTRY", None)

        assert len(candidates) == 1
        assert candidates[0].name == "City Dental Clinic"
        assert candidates[0].destination_type == "DENTISTRY"
        assert candidates[0].specialty is None
        assert candidates[0].provider_id == "osm:node:5001"


# ---------------------------------------------------------------------------
# Step 10F — Pulmonology → SPECIALIST/PULMONOLOGY routing
# ---------------------------------------------------------------------------

class TestPulmonologyOSMMapping:
    """Verify SPECIALIST+PULMONOLOGY maps to the correct OSM tags."""

    def test_specialist_pulmonology_maps_to_pulmonology_tag(self):
        """tags_for('SPECIALIST', 'PULMONOLOGY') must return the
        healthcare:speciality=pulmonology tag."""
        from location.osm_tag_map import tags_for
        tags = tags_for("SPECIALIST", "PULMONOLOGY")
        assert '["healthcare:speciality"="pulmonology"]' in tags, (
            f"SPECIALIST/PULMONOLOGY must map to pulmonology speciality tag; got {tags}"
        )

    def test_specialist_pulmonology_includes_generic_doctors_fallback(self):
        """tags_for('SPECIALIST', 'PULMONOLOGY') must also include the
        generic doctors fallback so areas with untagged specialist clinics
        still surface results."""
        from location.osm_tag_map import tags_for
        tags = tags_for("SPECIALIST", "PULMONOLOGY")
        assert '["amenity"="doctors"]' in tags, (
            f"SPECIALIST/PULMONOLOGY must include generic doctors fallback; got {tags}"
        )

    def test_pulmonology_provider_discovered_via_specialist_pulmonology(self):
        """End-to-end: find_nearby_providers with SPECIALIST+PULMONOLOGY
        returns a pulmonology provider from the mocked Overpass response."""
        pulm_node = _node(6001, "City Pulmonology Clinic", 37.7749, -122.4194)
        pulm_node["tags"]["healthcare:speciality"] = "pulmonology"

        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass([pulm_node])):
            candidates = find_nearby_providers(_LOCATION, "SPECIALIST", "PULMONOLOGY")

        assert len(candidates) == 1
        assert candidates[0].name == "City Pulmonology Clinic"
        assert candidates[0].destination_type == "SPECIALIST"
        assert candidates[0].specialty == "PULMONOLOGY"
        assert candidates[0].provider_id == "osm:node:6001"


# ---------------------------------------------------------------------------
# Cardiology → SPECIALIST/CARDIOLOGY OSM mapping
# ---------------------------------------------------------------------------

class TestCardiologyOSMMapping:
    """Verify SPECIALIST+CARDIOLOGY maps to the correct OSM tags.

    Cardiology is supported in the appointment layer (SPECIALTY_TAGS mapping
    and contract tests exist).  No routing rule activates it automatically
    yet — the rule-matrix document marks that rule as requiring clinical
    sign-off.  These tests confirm provider discovery will work correctly
    once a rule activates the CARDIOLOGY specialty.
    """

    def test_specialist_cardiology_maps_to_cardiology_tag(self):
        """tags_for('SPECIALIST', 'CARDIOLOGY') must return the cardiology tag."""
        from location.osm_tag_map import tags_for
        tags = tags_for("SPECIALIST", "CARDIOLOGY")
        assert '["healthcare:speciality"="cardiology"]' in tags, (
            f"SPECIALIST/CARDIOLOGY must map to cardiology speciality tag; got {tags}"
        )

    def test_specialist_cardiology_includes_generic_doctors_fallback(self):
        """tags_for('SPECIALIST', 'CARDIOLOGY') must include the generic fallback."""
        from location.osm_tag_map import tags_for
        tags = tags_for("SPECIALIST", "CARDIOLOGY")
        assert '["amenity"="doctors"]' in tags, (
            f"SPECIALIST/CARDIOLOGY must include generic doctors fallback; got {tags}"
        )

    def test_cardiology_provider_discovered_via_specialist_cardiology(self):
        """End-to-end: find_nearby_providers with SPECIALIST+CARDIOLOGY
        returns a cardiology provider from the mocked Overpass response."""
        cardio_node = _node(7001, "City Cardiology Clinic", 37.7749, -122.4194)
        cardio_node["tags"]["healthcare:speciality"] = "cardiology"

        with patch("location.provider_discovery.requests.post",
                   return_value=_mock_overpass([cardio_node])):
            candidates = find_nearby_providers(_LOCATION, "SPECIALIST", "CARDIOLOGY")

        assert len(candidates) == 1
        assert candidates[0].name == "City Cardiology Clinic"
        assert candidates[0].destination_type == "SPECIALIST"
        assert candidates[0].specialty == "CARDIOLOGY"
        assert candidates[0].provider_id == "osm:node:7001"
