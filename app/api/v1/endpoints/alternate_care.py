"""
Alternate Care Navigation endpoint - exposes the alternate care agent APIs.
"""
from app.services.alternate_care.api.routes import app as alternate_care_router

# Re-export the router from the alternate_care service module
router = alternate_care_router
