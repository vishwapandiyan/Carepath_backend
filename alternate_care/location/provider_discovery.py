"""
Provider Discovery — zero-cost backend.

Uses the Overpass API (free, no key) against OpenStreetMap data to find
nearby providers matching the classified destination/specialty. Pair with
Leaflet + OSM raster tiles on the frontend for the map itself (also free).

Overpass has public instances with fair-use rate limits (no auth, but
don't hammer it — cache results per patient session). Swap
``OVERPASS_URL`` (via env var) for a self-hosted instance if you outgrow
the public one.

Error handling
--------------
All failures surface as ``ProviderDiscoveryError`` subclasses so callers
can decide whether to surface the error to the patient or return an empty
list gracefully.  The ranking agent catches these and logs them; the graph
still produces a recommendation (with no ranked providers) rather than
hard-failing the pipeline.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import requests

from app.services.alternate_care.config.settings import OVERPASS_URL, DEFAULT_SEARCH_RADIUS_KM
from app.services.alternate_care.models.schemas import PatientLocation, ProviderCandidate, Destination
from app.services.alternate_care.location.osm_tag_map import tags_for

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15

# Public Overpass API mirrors (in priority order).
# Primary: configured via OVERPASS_URL env var (default: overpass-api.de).
# Fallbacks: used only when the primary returns a transient error (406/5xx/timeout).
_FALLBACK_OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class ProviderDiscoveryError(RuntimeError):
    """Base class for provider discovery failures."""


class ProviderDiscoveryNetworkError(ProviderDiscoveryError):
    """Network or HTTP error contacting the Overpass API."""


class ProviderDiscoveryRateLimitError(ProviderDiscoveryNetworkError):
    """Overpass API returned HTTP 429."""


class NoProvidersFoundError(ProviderDiscoveryError):
    """Overpass query succeeded but returned zero usable results."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_query(lat: float, lon: float, radius_m: int, tag_filters: List[str]) -> str:
    clauses = "".join(
        f'node{tag}(around:{radius_m},{lat},{lon});'
        f'way{tag}(around:{radius_m},{lat},{lon});'
        for tag in tag_filters
    )
    return f"[out:json][timeout:25];({clauses});out center tags;"


def _parse_elements(elements: list, destination: Destination, specialty: str | None) -> List[ProviderCandidate]:
    """Convert raw Overpass elements to deduplicated ProviderCandidates."""
    candidates: List[ProviderCandidate] = []
    seen: set = set()

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # unnamed OSM nodes aren't useful to show a patient

        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        # Deduplicate node/way pairs that represent the same physical
        # facility.  OSM frequently returns both a node (entrance/point)
        # and a way (building polygon centroid) for the same clinic, each
        # with different element IDs but identical name and near-identical
        # coordinates.  Round to ~111m precision to tolerate the small
        # centroid-vs-node offset.
        dedup_key = (name, round(lat, 3), round(lon, 3))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        candidates.append(
            ProviderCandidate(
                provider_id=f"osm:{el['type']}:{el['id']}",
                name=name,
                destination_type=destination,
                specialty=specialty,
                latitude=lat,
                longitude=lon,
                address=tags.get("addr:full") or tags.get("addr:street"),
                source="osm",
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_nearby_providers(
    location: PatientLocation,
    destination: Destination,
    specialty: str | None,
) -> List[ProviderCandidate]:
    """Find nearby healthcare providers via the Overpass/OSM API.

    Parameters
    ----------
    location:
        Patient location.  Must have ``latitude`` and ``longitude`` set
        (call ``location.geocoder.resolve_location()`` first if address-only).
    destination:
        The care destination determined by the routing rules.
    specialty:
        Specialist sub-type, or None for non-specialist destinations.

    Returns
    -------
    List of deduplicated ProviderCandidates (may be empty).

    Raises
    ------
    ValueError
        When ``location`` has no coordinates (lat/lon are None).
    ProviderDiscoveryRateLimitError
        When Overpass returns HTTP 429.
    ProviderDiscoveryNetworkError
        On any other network or HTTP error.
    NoProvidersFoundError
        When the query succeeds but no usable named providers are found.
        This is *not* raised automatically — callers receive an empty list;
        raise it explicitly when a guaranteed result is required.
    """
    if destination == "TELEHEALTH":
        # No physical search needed — telehealth providers come from the
        # shared Appointment Agent's virtual-provider network, not OSM.
        return []

    if location.latitude is None or location.longitude is None:
        raise ValueError(
            "PatientLocation must have coordinates before calling "
            "find_nearby_providers.  Call resolve_location() first when "
            "only an address was supplied."
        )

    # Use the explicit radius on the location object; fall back to the
    # configured default so env-var overrides are respected.
    radius_km = location.radius_km if location.radius_km is not None else DEFAULT_SEARCH_RADIUS_KM
    radius_m = int(radius_km * 1000)

    tag_filters = tags_for(destination, specialty)
    query = _build_query(location.latitude, location.longitude, radius_m, tag_filters)

    logger.debug(
        "Overpass query: destination=%s specialty=%s lat=%.4f lon=%.4f radius_m=%d",
        destination, specialty, location.latitude, location.longitude, radius_m,
    )

    # Build the list of endpoints to try: primary first, then fallbacks.
    endpoints_to_try = [OVERPASS_URL] + [
        url for url in _FALLBACK_OVERPASS_URLS if url != OVERPASS_URL
    ]

    headers = {
        "User-Agent": "AlternateCareNavigationAgent/1.0 (healthcare; contact: dev@example.com)",
    }

    resp = None
    last_error: Optional[Exception] = None

    for endpoint_url in endpoints_to_try:
        try:
            resp = requests.post(
                endpoint_url,
                data={"data": query},
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            logger.warning(
                "Overpass endpoint %s timed out, trying next mirror...", endpoint_url
            )
            last_error = ProviderDiscoveryNetworkError(
                f"Overpass API timed out after {REQUEST_TIMEOUT_SECONDS}s "
                f"(destination={destination}, radius_m={radius_m})"
            )
            last_error.__cause__ = exc
            continue
        except requests.exceptions.ConnectionError as exc:
            logger.warning(
                "Overpass endpoint %s connection error, trying next mirror...", endpoint_url
            )
            last_error = ProviderDiscoveryNetworkError(
                f"Could not connect to Overpass API: {endpoint_url}"
            )
            last_error.__cause__ = exc
            continue
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Overpass endpoint %s request error: %s, trying next mirror...",
                endpoint_url, exc
            )
            last_error = ProviderDiscoveryNetworkError(
                f"Overpass API request failed: {exc}"
            )
            last_error.__cause__ = exc
            continue

        if resp.status_code == 429:
            logger.warning(
                "Overpass endpoint %s returned 429 (rate limit), trying next mirror...",
                endpoint_url
            )
            last_error = ProviderDiscoveryRateLimitError(
                "Overpass API rate limit reached (HTTP 429). "
                "Wait before retrying or self-host Overpass."
            )
            resp = None
            continue

        if resp.status_code >= 400:
            logger.warning(
                "Overpass endpoint %s returned HTTP %d, trying next mirror...",
                endpoint_url, resp.status_code
            )
            last_error = ProviderDiscoveryNetworkError(
                f"Overpass API returned HTTP {resp.status_code}"
            )
            resp = None
            continue

        # Success — break out of the endpoint loop
        logger.debug("Overpass query succeeded via %s", endpoint_url)
        break

    # If all endpoints failed, raise the last error
    if resp is None or resp.status_code >= 400:
        if last_error is not None:
            raise last_error
        raise ProviderDiscoveryNetworkError(
            "All Overpass API endpoints failed"
        )

    try:
        elements = resp.json().get("elements", [])
    except ValueError as exc:
        raise ProviderDiscoveryNetworkError(
            "Overpass API returned non-JSON response"
        ) from exc

    candidates = _parse_elements(elements, destination, specialty)

    logger.debug(
        "Overpass returned %d elements → %d named+deduped candidates",
        len(elements), len(candidates),
    )

    return candidates
