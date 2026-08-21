"""
Mock US locations for testing (developer-friendly for India-based team)
Real patient locations should come from patient_ehr.address
"""

MOCK_US_LOCATIONS = {
    "austin_tx": {
        "name": "Austin, Texas",
        "latitude": 30.2672,
        "longitude": -97.7431,
        "address": "Austin, TX 78701",
        "zip": "78701",
        "state": "TX"
    },
    "san_francisco_ca": {
        "name": "San Francisco, California",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "address": "San Francisco, CA 94102",
        "zip": "94102",
        "state": "CA"
    },
    "new_york_ny": {
        "name": "New York City, New York",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "address": "New York, NY 10001",
        "zip": "10001",
        "state": "NY"
    },
    "boston_ma": {
        "name": "Boston, Massachusetts",
        "latitude": 42.3601,
        "longitude": -71.0589,
        "address": "Boston, MA 02108",
        "zip": "02108",
        "state": "MA"
    },
    "seattle_wa": {
        "name": "Seattle, Washington",
        "latitude": 47.6062,
        "longitude": -122.3321,
        "address": "Seattle, WA 98101",
        "zip": "98101",
        "state": "WA"
    },
    "chicago_il": {
        "name": "Chicago, Illinois",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "address": "Chicago, IL 60601",
        "zip": "60601",
        "state": "IL"
    },
    "miami_fl": {
        "name": "Miami, Florida",
        "latitude": 25.7617,
        "longitude": -80.1918,
        "address": "Miami, FL 33101",
        "zip": "33101",
        "state": "FL"
    }
}


def get_location_choices():
    """Return list of location names for UI dropdown"""
    return [loc["name"] for loc in MOCK_US_LOCATIONS.values()]


def get_location_by_name(name: str):
    """Get location dict by display name"""
    for key, loc in MOCK_US_LOCATIONS.items():
        if loc["name"] == name:
            return loc
    # Default to Austin
    return MOCK_US_LOCATIONS["austin_tx"]


def get_default_location():
    """Get default location (Austin)"""
    return MOCK_US_LOCATIONS["austin_tx"]
