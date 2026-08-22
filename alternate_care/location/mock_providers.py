"""
Mock provider data for development/testing when Overpass API is unavailable
"""

MOCK_AUSTIN_PROVIDERS = [
    {
        "provider_id": "mock:austin:1",
        "provider_name": "Baylor Scott & White Clinic",
        "facility_name": "Baylor Scott & White Clinic - Austin Downtown",
        "type": "clinic",
        "address": "601 E 15th St, Austin, TX 78701",
        "latitude": 30.2747,
        "longitude": -97.7353,
        "distance_km": 0.8
    },
    {
        "provider_id": "mock:austin:2",
        "provider_name": "CommUnityCare Health Centers",
        "facility_name": "CommUnityCare Rosewood-Zaragosa",
        "type": "clinic",
        "address": "2800 Webberville Rd, Austin, TX 78702",
        "latitude": 30.2591,
        "longitude": -97.7073,
        "distance_km": 2.1
    },
    {
        "provider_id": "mock:austin:3",
        "provider_name": "Austin Regional Clinic",
        "facility_name": "Austin Regional Clinic - Downtown",
        "type": "clinic",
        "address": "1301 W 38th St, Austin, TX 78705",
        "latitude": 30.2975,
        "longitude": -97.7488,
        "distance_km": 3.4
    },
    {
        "provider_id": "mock:austin:4",
        "provider_name": "Seton Family of Doctors",
        "facility_name": "Seton Family of Doctors - Central",
        "type": "clinic",
        "address": "1201 W 38th St, Austin, TX 78705",
        "latitude": 30.2974,
        "longitude": -97.7501,
        "distance_km": 3.5
    },
    {
        "provider_id": "mock:austin:5",
        "provider_name": "People's Community Clinic",
        "facility_name": "People's Community Clinic - East",
        "type": "clinic",
        "address": "2909 N IH 35, Austin, TX 78722",
        "latitude": 30.2908,
        "longitude": -97.7221,
        "distance_km": 2.8
    }
]

MOCK_LOCATIONS = {
    "austin": MOCK_AUSTIN_PROVIDERS,
    # Add more cities as needed
}

def get_mock_providers_for_location(latitude: float, longitude: float):
    """Return mock providers based on approximate location"""
    # Austin area (rough bounds)
    if 30.1 <= latitude <= 30.5 and -97.9 <= longitude <= -97.6:
        return MOCK_AUSTIN_PROVIDERS
    
    # Return empty list for other locations (will use actual API)
    return []
