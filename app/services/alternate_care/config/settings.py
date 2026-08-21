from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class AlternateCareSettings(BaseSettings):
    """Settings for the Alternate Care Agent"""
    
    # Base URL of the teammate's shared Appointment Agent service.
    appointment_agent_base_url: str = "http://localhost:8001"
    
    # NVIDIA NIM / OpenAI-compatible LLM endpoint
    # NVIDIA_API_KEY has NO default — the client raises at construction time if
    # the variable is absent or empty so failures are loud, not silent.
    nvidia_api_key: Optional[str] = None  # no default — must be set
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    
    # Overpass (free OSM) endpoint — override if self-hosting / rate-limited.
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    default_search_radius_km: float = 15.0
    
    # Nominatim (free OSM geocoding) endpoint — override for self-hosting.
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    nominatim_user_agent: str = "AlternateCareNavigationAgent/1.0 (development; contact: dev@mycompany.io)"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = AlternateCareSettings()

# Export as module-level constants for backward compatibility
NVIDIA_API_KEY = settings.nvidia_api_key
NVIDIA_BASE_URL = settings.nvidia_base_url
NVIDIA_MODEL = settings.nvidia_model
APPOINTMENT_AGENT_BASE_URL = settings.appointment_agent_base_url
OVERPASS_URL = settings.overpass_url
DEFAULT_SEARCH_RADIUS_KM = settings.default_search_radius_km
NOMINATIM_URL = settings.nominatim_url
NOMINATIM_USER_AGENT = settings.nominatim_user_agent

