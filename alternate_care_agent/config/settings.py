import os

# Base URL of the teammate's shared Appointment Agent service.
APPOINTMENT_AGENT_BASE_URL = os.environ.get(
    "APPOINTMENT_AGENT_BASE_URL", "http://localhost:8001"
)

# Overpass (free OSM) endpoint — override if self-hosting / rate-limited.
OVERPASS_URL = os.environ.get(
    "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
)

DEFAULT_SEARCH_RADIUS_KM = float(os.environ.get("DEFAULT_SEARCH_RADIUS_KM", 15.0))

# Nominatim (free OSM geocoding) endpoint — override for self-hosting.
# Public instance: https://nominatim.openstreetmap.org/search
# Fair-use: max 1 req/s, descriptive User-Agent required.
NOMINATIM_URL = os.environ.get(
    "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
)

# User-Agent sent with every Nominatim request.  Nominatim policy requires
# an application name and contact address.  Override in production.
NOMINATIM_USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "AlternateCareNavigationAgent/1.0 (development; contact: dev@example.com)",
)
