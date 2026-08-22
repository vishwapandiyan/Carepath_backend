"""
Post-Care → Shared Appointment Agent Handoff

Connects the Post-care workflow to the existing Shared Appointment Agent
when Care Continuity determines requires_appointment = True.

This module:
1. Builds the appointment context from Post-care data
2. Generates a session_id for the appointment workflow
3. Calls run_appointment_agent() (existing, shared, not duplicated)
4. Persists the appointment session with source="POST_CARE"
5. Returns the provider discovery result

Does NOT:
- Auto-select a provider
- Auto-book an appointment
- Duplicate the Appointment Agent
- Create a new database
"""

import sys
import os
import logging
from typing import Dict, Any, List, Optional
from secrets import token_urlsafe

logger = logging.getLogger(__name__)

# Ensure alternate_care is importable
_ALTERNATE_CARE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "alternate_care"
)
if _ALTERNATE_CARE_PATH not in sys.path:
    sys.path.insert(0, _ALTERNATE_CARE_PATH)


def handoff_to_appointment_agent(
    mrn: str,
    care_plan_id: str,
    classification: str,
    symptoms: List[str],
    concerns: List[str],
    summary: str,
    confidence: float,
    latitude: float = 13.0827,   # Default: Chennai (patient location from EHR in future)
    longitude: float = 80.2707,
    radius_km: float = 15.0,
) -> Dict[str, Any]:
    """
    Hand off from Post-care to the existing Shared Appointment Agent.
    
    Determines destination/specialty from clinical context and calls
    run_appointment_agent() for provider discovery.
    
    Args:
        mrn: Patient MRN (preserved through to appointment_sessions)
        care_plan_id: Post-care plan ID (preserved for traceability)
        classification: URGENT or CONCERN from Response Analyzer
        symptoms: Extracted symptoms
        concerns: Extracted concerns
        summary: Response summary
        confidence: Analysis confidence
        latitude: Patient latitude (default for now)
        longitude: Patient longitude (default for now)
        radius_km: Search radius
    
    Returns:
        Dict with appointment handoff result
    """
    
    # ── 1. Determine destination and specialty from clinical context ──────
    destination, specialty = _derive_destination_specialty(symptoms, concerns, classification)
    
    # ── 2. Generate session_id ────────────────────────────────────────────
    session_id = f"pc_{token_urlsafe(12)}"
    
    logger.info(
        f"Appointment handoff: mrn={mrn}, care_plan_id={care_plan_id}, "
        f"destination={destination}, specialty={specialty}, session={session_id}"
    )
    
    # ── 3. Call the existing Shared Appointment Agent ─────────────────────
    try:
        from agents.appointment_agent import run_appointment_agent
        
        agent_result = run_appointment_agent(
            recommendation_id=session_id,
            destination=destination,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            specialty=specialty,
            source="POST_CARE",
            appointment_urgency="IMMEDIATE" if classification == "URGENT" else "THIS_WEEK",
            reason=summary,
            care_plan_id=care_plan_id,
        )
    except Exception as e:
        logger.error(f"Appointment Agent call failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Appointment Agent failed: {str(e)}",
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "session_id": session_id,
        }
    
    if not agent_result.get("ok"):
        return {
            "success": False,
            "error": agent_result.get("error", "Unknown error from Appointment Agent"),
            "mrn": mrn,
            "care_plan_id": care_plan_id,
            "session_id": session_id,
        }
    
    # ── 4. Persist appointment session with source=POST_CARE ──────────────
    try:
        from post_care.database.appointment_repository import AppointmentSessionRepository
        
        session_data = AppointmentSessionRepository.create_session(
            mrn=mrn,
            destination=destination,
            specialty=specialty,
            rule_id=f"post_care_{classification.lower()}",
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            source="POST_CARE",
            care_plan_id=care_plan_id,
            session_id=session_id,
            conversation_state=agent_result.get("messages"),
        )
        
        # Update session with provider candidates
        providers = agent_result.get("providers")
        if providers:
            from post_care.database.appointment_repository import AppointmentSessionRepository as Repo
            from post_care.database.connection import get_db_connection, close_db_connection
            import json
            
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE appointment_sessions SET provider_candidates = %s::jsonb, workflow_stage = 'PROVIDERS_SEARCHED', updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                    (json.dumps(providers), session_id)
                )
                conn.commit()
            finally:
                close_db_connection(conn)
        
        logger.info(f"Appointment session persisted: session_id={session_id}, source=POST_CARE")
        
    except Exception as persist_err:
        logger.error(f"Session persistence failed (non-fatal): {persist_err}", exc_info=True)
        # Agent succeeded but persistence failed — still return the result
    
    # ── 5. Return result ──────────────────────────────────────────────────
    return {
        "success": True,
        "source": "POST_CARE",
        "mrn": mrn,
        "care_plan_id": care_plan_id,
        "session_id": session_id,
        "destination": destination,
        "specialty": specialty,
        "workflow_stage": "PROVIDERS_SEARCHED" if agent_result.get("providers") else "NAVIGATION_COMPLETE",
        "providers": agent_result.get("providers"),
        "provider_count": len(agent_result.get("providers") or []),
        "agent_response": agent_result.get("response"),
        "appointment_id": None,
        "appointment_status": None,
    }


def _derive_destination_specialty(
    symptoms: List[str],
    concerns: List[str],
    classification: str,
) -> tuple:
    """
    Derive appointment destination and specialty from clinical context.
    
    Uses symptom keywords to determine appropriate care type.
    Does NOT invent medical diagnoses — just maps symptoms to facility types.
    
    Returns:
        (destination, specialty) tuple
    """
    all_context = " ".join(symptoms + concerns).lower()
    
    # Cardiac symptoms → SPECIALIST / CARDIOLOGY
    cardiac_keywords = ["chest", "heart", "cardiac", "palpitation", "blood pressure", "bp"]
    if any(kw in all_context for kw in cardiac_keywords):
        return "SPECIALIST", "CARDIOLOGY"
    
    # Respiratory symptoms → SPECIALIST / PULMONOLOGY
    respiratory_keywords = ["breath", "breathing", "respiratory", "cough", "lung", "asthma", "copd"]
    if any(kw in all_context for kw in respiratory_keywords):
        return "SPECIALIST", "PULMONOLOGY"
    
    # URGENT classification with no specific specialty → URGENT_CARE
    if classification == "URGENT":
        return "URGENT_CARE", None
    
    # Default for CONCERN → PCP
    return "PCP", None
