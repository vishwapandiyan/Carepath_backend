"""
Patient package — contains all patient-facing features (Intake, Safety, Pathway, etc.).
"""

from app.patient.router import patient_router

__all__ = ["patient_router"]
