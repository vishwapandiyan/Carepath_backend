"""
Maps a CareDecision (destination + specialty) to OpenStreetMap tag filters
for the Overpass API. This is the only place that should need editing when
you add/rename a destination or specialty in the rule file.

OSM tagging reference: https://wiki.openstreetmap.org/wiki/Key:healthcare
"""

from __future__ import annotations
from typing import List

# Each entry is a list of Overpass tag-filter strings; results are unioned.
# DENTISTRY is a first-class destination (not a specialty under SPECIALIST).
DESTINATION_TAGS = {
    "PCP":       ['["amenity"="doctors"]', '["healthcare"="doctor"]'],
    "URGENT_CARE": ['["healthcare"="urgent_care"]', '["amenity"="clinic"]'],
    "DENTISTRY": ['["amenity"="dentist"]'],
    # SPECIALIST falls through to SPECIALTY_TAGS below, keyed by specialty
}

SPECIALTY_TAGS = {
    "PULMONOLOGY":   ['["healthcare:speciality"="pulmonology"]', '["amenity"="doctors"]'],
    "ORTHOPEDICS":   ['["healthcare:speciality"="orthopaedics"]', '["amenity"="doctors"]'],
    "DERMATOLOGY":   ['["healthcare:speciality"="dermatology"]', '["amenity"="doctors"]'],
    "UROLOGY":       ['["healthcare:speciality"="urology"]', '["amenity"="doctors"]'],
    "GYNECOLOGY":    ['["healthcare:speciality"="gynaecology"]', '["amenity"="doctors"]'],
    "GASTROENTEROLOGY": ['["healthcare:speciality"="gastroenterology"]', '["amenity"="doctors"]'],
    "CHRONIC_DISEASE_MANAGEMENT_REVIEW": ['["amenity"="doctors"]'],
    "CARDIOLOGY":    ['["healthcare:speciality"="cardiology"]', '["amenity"="doctors"]'],
    "NEPHROLOGY":    ['["healthcare:speciality"="nephrology"]', '["amenity"="doctors"]'],
    "ENDOCRINOLOGY": ['["healthcare:speciality"="endocrinology"]', '["amenity"="doctors"]'],
    "INFECTIOUS_DISEASE": ['["healthcare:speciality"="infectious_disease"]', '["amenity"="doctors"]'],
    "ONCOLOGY":      ['["healthcare:speciality"="oncology"]', '["amenity"="doctors"]'],
}


def tags_for(destination: str, specialty: str | None) -> List[str]:
    if destination == "SPECIALIST" and specialty:
        return SPECIALTY_TAGS.get(specialty, ['["amenity"="doctors"]'])
    if destination in DESTINATION_TAGS:
        return DESTINATION_TAGS[destination]
    raise ValueError(f"No OSM tag mapping for destination={destination!r} specialty={specialty!r}")
