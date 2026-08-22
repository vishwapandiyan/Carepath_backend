"""
Geocoding abstraction for the Alternate Care Navigation Agent.

Service used: Nominatim (OpenStreetMap)
  - Free, no API key required.
  - Fair-use policy: max 1 request/second, provide a descriptive User-Agent.
  - Endpoint: https://nominatim.openstreetmap.org/search

Why Nominatim?
  - Zero cost, no sign-up.
  - Handles U.S. street addresses, city/state, and ZIP codes reliably.
  - OSM-based — consistent with Overpass (also OSM) used for provider search.
  - Override via NOMINATIM_URL env var for self-hosting or test doubles.

Architecture note
-----------------
This module is the ONLY place that talks to a geocoding service.
The rest of the pipeline works exclusively with (latitude, longitude) floats.
Swap the implementation here (e.g. to a self-hosted Photon instance) without
touching any other module.

No geocoding is performed when coordinates are already present on
PatientLocation — this module is only invoked when address-only input arrives.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import requests

from app.services.alternate_care.config.settings import NOMINATIM_URL, NOMINATIM_USER_AGENT

logger = logging.getLogger(__name__)

# Nominatim's fair-use policy requires a descriptive User-Agent identifying
# the application and a contact address.  Set NOMINATIM_USER_AGENT in the
# environment for production deployments.
_HEADERS = {"User-Agent": NOMINATIM_USER_AGENT}

REQUEST_TIMEOUT_SECONDS = 10


# ---------------------------------------------------------------------------
# Public exceptions — callers catch these, not raw requests exceptions.
# ---------------------------------------------------------------------------

class GeocodingError(RuntimeError):
    """Base class for all geocoding failures."""


class InvalidLocationError(GeocodingError):
    """The supplied address string cannot be geocoded (no results found)."""


class GeocodingNetworkError(GeocodingError):
    """Network or HTTP error while contacting the geocoding service."""


class GeocodingRateLimitError(GeocodingNetworkError):
    """The geocoding service returned HTTP 429 (rate limited)."""


# ---------------------------------------------------------------------------
# Core geocoding function
# ---------------------------------------------------------------------------

def geocode(address: str) -> Tuple[float, float]:
    """Resolve a U.S. address string to (latitude, longitude).

    Supported input forms:
      - Street address: "123 Main St, Springfield, IL 62701"
      - City/state:     "Boston, MA"
      - ZIP code:       "10001"

    Returns
    -------
    (latitude, longitude) as floats.

    Raises
    ------
    InvalidLocationError
        When the address produces no geocoding results.
    GeocodingRateLimitError
        When the service responds with HTTP 429.
    GeocodingNetworkError
        When any other network or HTTP error occurs.
    """
    if not address or not address.strip():
        raise InvalidLocationError("Address must be a non-empty string.")

    params = {
        "q": address.strip(),
        "format": "json",
        "limit": 1,
        "countrycodes": "us",  # restrict to United States
        "addressdetails": 0,
    }

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as exc:
        raise GeocodingNetworkError(
            f"Geocoding request timed out after {REQUEST_TIMEOUT_SECONDS}s "
            f"for address: {address!r}"
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise GeocodingNetworkError(
            f"Could not connect to geocoding service for address: {address!r}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise GeocodingNetworkError(
            f"Geocoding request failed for address: {address!r}"
        ) from exc

    if resp.status_code == 429:
        raise GeocodingRateLimitError(
            "Geocoding service rate limit reached (HTTP 429). "
            "Wait before retrying or self-host Nominatim."
        )

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise GeocodingNetworkError(
            f"Geocoding service returned HTTP {resp.status_code} "
            f"for address: {address!r}"
        ) from exc

    try:
        results = resp.json()
    except ValueError as exc:
        raise GeocodingNetworkError(
            f"Geocoding service returned non-JSON response for address: {address!r}"
        ) from exc

    if not results:
        raise InvalidLocationError(
            f"No geocoding results found for address: {address!r}. "
            "Check that the address is a valid U.S. location."
        )

    best = results[0]
    try:
        lat = float(best["lat"])
        lon = float(best["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingNetworkError(
            f"Geocoding service returned unexpected result format for address: {address!r}"
        ) from exc

    logger.debug("Geocoded %r → (%.6f, %.6f)", address, lat, lon)
    return lat, lon


# ---------------------------------------------------------------------------
# Convenience: resolve a PatientLocation in-place
# ---------------------------------------------------------------------------

def resolve_location(location: "PatientLocation") -> "PatientLocation":  # type: ignore[name-defined]
    """Return a PatientLocation guaranteed to have latitude and longitude set.

    - If coordinates are already present, returns the same object unchanged.
    - If only address is present, geocodes it and returns a new PatientLocation
      with latitude, longitude, radius_km, and address all populated.

    This is the single call-site that converts address-only input into the
    coordinate pair every downstream module expects.

    Raises
    ------
    InvalidLocationError
        When address is provided but geocoding returns no results.
    GeocodingNetworkError / GeocodingRateLimitError
        On network or service failures.
    """
    # Lazy import avoids a circular dependency since models.schemas imports
    # nothing from location/.
    from models.schemas import PatientLocation

    if location.latitude is not None and location.longitude is not None:
        return location  # already resolved — nothing to do

    # Address-only path.
    lat, lon = geocode(location.address)  # type: ignore[arg-type]
    return PatientLocation(
        latitude=lat,
        longitude=lon,
        radius_km=location.radius_km,
        address=location.address,
    )
