"""
Voice Service Response Endpoint
Receives voice responses from external voice-service and processes through agentic pipeline.

This endpoint is called by voice-service after Twilio speech capture.
It reuses the existing Response Analyzer + Care Continuity orchestration.
"""

import sys
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================================
# CONCERN FOLLOW-UP CONSTANTS (inline to avoid import issues)
# ============================================================================
MAX_CONCERN_FOLLOWUP_TURNS = 3
DEFAULT_FOLLOWUP_QUESTION = "Can you tell me a little more about what you're experiencing?"

SYMPTOM_FOLLOWUP_SEQUENCE = {
    "headache": [
        "Is your headache getting better, worse, or staying the same?",
        "On a scale of 1-10, how severe is your headache right now?",
        "Have you taken the medication recommended in your care plan?",
    ],
    "dizziness": [
        "Are you still feeling dizzy right now?",
        "How severe is the dizziness? Does it affect your ability to stand or walk?",
        "Have you eaten or had water recently?",
    ],
    "nausea": [
        "Have you experienced any vomiting along with the nausea?",
        "How long have you been feeling nauseous?",
        "Are you able to eat and drink normally?",
    ],
    "pain": [
        "Is the pain getting better, worse, or staying the same?",
        "On a scale of 1-10, how severe is the pain right now?",
        "Have you taken any pain medication or tried any remedies?",
    ],
    "fever": [
        "Have you measured your temperature?",
        "If yes, what was your temperature reading?",
        "Have you taken any fever-reducing medication?",
    ],
    "medication": [
        "Have you been able to take your medication as prescribed?",
        "If not, what prevented you from taking it?",
        "Do you have any side effects from the medication?",
    ],
    "chest pain": [
        "Is the chest pain still present? Has it changed in intensity?",
        "On a scale of 1-10, how severe is the chest pain right now?",
        "Does the pain get better or worse with activity or rest?",
    ],
    "shortness of breath": [
        "Are you able to breathe comfortably right now?",
        "Does the shortness of breath get worse with activity?",
        "How long does each episode of shortness of breath last?",
    ],
    "swelling": [
        "Is the swelling getting better, worse, or staying the same?",
        "Is the swelling in one area or multiple areas?",
        "Have you noticed any change in color or warmth around the swelling?",
    ],
    "bleeding": [
        "Is the bleeding still occurring? How much bleeding are you experiencing?",
        "When did the bleeding start?",
        "Have you applied pressure or any first aid measures?",
    ],
    "wound": [
        "How does the wound look? Is there any redness, drainage, or increased pain?",
        "Is the wound healing normally or do you notice any changes?",
        "Have you kept the wound clean and bandaged as recommended?",
    ],
    "cough": [
        "Is your cough getting better, worse, or staying the same?",
        "Is the cough bringing up any sputum, and if so, what color is it?",
        "Does anything help make the cough better?",
    ],
    "fatigue": [
        "How is your energy level compared to yesterday?",
        "Are you able to perform your daily activities?",
        "Have you been able to get adequate rest?",
    ],
    "confusion": [
        "Are you feeling more clear-headed now, or still confused?",
        "Is the confusion constant or does it come and go?",
        "Have you noticed any triggers for the confusion?",
    ],
    "vomiting": [
        "How many times have you vomited? Are you able to keep fluids down?",
        "When was the last time you vomited?",
        "Have you been able to eat anything today?",
    ],
    "appetite": [
        "How long have you been experiencing reduced appetite?",
        "Are you able to drink fluids normally?",
        "Have you lost any weight since your discharge?",
    ],
}

router = APIRouter()


# ============================================================================
# DATABASE HELPERS FOR VOICE CONVERSATION TURNS
# ============================================================================

def get_db_connection():
    """Get database connection for voice response processing."""
    try:
        POST_CARE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "post_care")
        if POST_CARE_PATH not in sys.path:
            sys.path.insert(0, POST_CARE_PATH)
        
        from database.connection import get_db_connection as get_conn
        return get_conn()
    except Exception as e:
        logger.error(f"Failed to import database connection: {str(e)}")
        raise


def close_db_connection(conn):
    """Close database connection."""
    try:
        POST_CARE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "post_care")
        if POST_CARE_PATH not in sys.path:
            sys.path.insert(0, POST_CARE_PATH)
        
        from database.connection import close_db_connection as close_conn
        close_conn(conn)
    except Exception as e:
        logger.error(f"Failed to close database connection: {str(e)}")
        if conn:
            conn.close()


def store_voice_turn(conn, checkin_id: str, call_sid: str, turn_number: int, 
                     patient_response: str, classification: Optional[str] = None,
                     symptoms: Optional[List[str]] = None, concerns: Optional[List[str]] = None,
                     followup_question: Optional[str] = None):
    """Store a voice conversation turn."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO voice_conversation_turns 
            (checkin_id, call_sid, turn_number, patient_response, classification, symptoms, concerns, followup_question)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (checkin_id, call_sid, turn_number, patient_response, classification, 
              symptoms, concerns, followup_question))
        conn.commit()
        logger.info(f"✓ Voice turn stored: checkin={checkin_id}, call_sid={call_sid}, turn={turn_number}")
    except Exception as e:
        logger.error(f"Failed to store voice turn: {str(e)}")
        raise


def get_prior_turn(conn, checkin_id: str, call_sid: str) -> Optional[dict]:
    """Retrieve the prior turn for the same checkin_id + call_sid combination."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT turn_number, patient_response, classification, symptoms, concerns
            FROM voice_conversation_turns
            WHERE checkin_id = %s AND call_sid = %s
            ORDER BY turn_number DESC
            LIMIT 1
        """, (checkin_id, call_sid))
        
        row = cursor.fetchone()
        if row:
            return {
                "turn_number": row[0],
                "patient_response": row[1],
                "classification": row[2],
                "symptoms": row[3],
                "concerns": row[4]
            }
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve prior turn: {str(e)}")
        return None


def get_current_turn_number(conn, checkin_id: str, call_sid: str) -> int:
    """Get the turn number for the next turn."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(turn_number) FROM voice_conversation_turns
            WHERE checkin_id = %s AND call_sid = %s
        """, (checkin_id, call_sid))
        
        row = cursor.fetchone()
        current_turn = row[0] if row and row[0] else 0
        return current_turn + 1
    except Exception as e:
        logger.error(f"Failed to get current turn number: {str(e)}")
        return 1


# ============================================================================
# RULE-BASED CONCERN FOLLOW-UP WITH MULTI-TURN SUPPORT
# ============================================================================

# Ordered question sequences per symptom (prevents infinite loop by rotating questions)
SYMPTOM_FOLLOWUP_SEQUENCE = {
    "headache": [
        "Is your headache getting better, worse, or staying the same?",
        "On a scale of 1-10, how severe is your headache right now?",
        "Have you taken the medication recommended in your care plan?",
    ],
    "dizziness": [
        "Are you still feeling dizzy right now?",
        "How severe is the dizziness? Does it affect your ability to stand or walk?",
        "Have you eaten or had water recently?",
    ],
    "nausea": [
        "Have you experienced any vomiting along with the nausea?",
        "How long have you been feeling nauseous?",
        "Are you able to eat and drink normally?",
    ],
    "pain": [
        "Is the pain getting better, worse, or staying the same?",
        "On a scale of 1-10, how severe is the pain right now?",
        "Have you taken any pain medication or tried any remedies?",
    ],
    "fever": [
        "Have you measured your temperature?",
        "If yes, what was your temperature reading?",
        "Have you taken any fever-reducing medication?",
    ],
    "medication": [
        "Have you been able to take your medication as prescribed?",
        "If not, what prevented you from taking it?",
        "Do you have any side effects from the medication?",
    ],
    "chest pain": [
        "Is the chest pain still present? Has it changed in intensity?",
        "On a scale of 1-10, how severe is the chest pain right now?",
        "Does the pain get better or worse with activity or rest?",
    ],
    "shortness of breath": [
        "Are you able to breathe comfortably right now?",
        "Does the shortness of breath get worse with activity?",
        "How long does each episode of shortness of breath last?",
    ],
    "swelling": [
        "Is the swelling getting better, worse, or staying the same?",
        "Is the swelling in one area or multiple areas?",
        "Have you noticed any change in color or warmth around the swelling?",
    ],
    "bleeding": [
        "Is the bleeding still occurring? How much bleeding are you experiencing?",
        "When did the bleeding start?",
        "Have you applied pressure or any first aid measures?",
    ],
    "wound": [
        "How does the wound look? Is there any redness, drainage, or increased pain?",
        "Is the wound healing normally or do you notice any changes?",
        "Have you kept the wound clean and bandaged as recommended?",
    ],
    "cough": [
        "Is your cough getting better, worse, or staying the same?",
        "Is the cough bringing up any sputum, and if so, what color is it?",
        "Does anything help make the cough better?",
    ],
    "fatigue": [
        "How is your energy level compared to yesterday?",
        "Are you able to perform your daily activities?",
        "Have you been able to get adequate rest?",
    ],
    "confusion": [
        "Are you feeling more clear-headed now, or still confused?",
        "Is the confusion constant or does it come and go?",
        "Have you noticed any triggers for the confusion?",
    ],
    "vomiting": [
        "How many times have you vomited? Are you able to keep fluids down?",
        "When was the last time you vomited?",
        "Have you been able to eat anything today?",
    ],
}

DEFAULT_FOLLOWUP_QUESTION = "Can you tell me a little more about what you're experiencing?"

# Safety limit to prevent infinite loops
MAX_CONCERN_FOLLOWUP_TURNS = 3


def get_asked_questions(conn, checkin_id: str, call_sid: str) -> List[str]:
    """Retrieve all follow-up questions already asked in this conversation."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ARRAY_AGG(followup_question) as asked_questions
            FROM voice_conversation_turns
            WHERE checkin_id = %s AND call_sid = %s AND followup_question IS NOT NULL
        """, (checkin_id, call_sid))
        
        row = cursor.fetchone()
        if row and row[0]:
            # Filter out None values
            return [q for q in row[0] if q]
        return []
    except Exception as e:
        logger.warning(f"Failed to retrieve asked questions: {str(e)}")
        return []


def get_next_followup_question(symptoms: List[str], asked_questions: List[str], conn=None, 
                               checkin_id: str = None, call_sid: str = None) -> tuple[str, bool]:
    """
    Generate the next follow-up question based on symptoms and conversation history.
    
    FIXED LOGIC:
    - asked_questions contains questions that have been ASKED (and patient has responded to)
    - When we return a NEW question, we return (question, True) because we need to WAIT for the answer
    - When all questions have been asked AND answered, we return (closing_message, False)
    
    Returns:
        tuple: (question_text, should_continue_multiturn)
        - question_text: The next question to ask (or closing message if all questions answered)
        - should_continue_multiturn: True if we're asking a NEW question (need to wait for answer)
                                     False if conversation is complete (all questions answered)
    """
    if not symptoms:
        # No symptoms detected, end conversation
        return "Thank you for sharing those details. I'll modify your care plan accordingly and continue to follow up with you. Thank you for your time. Goodbye.", False
    
    # Check if we've already asked the maximum number of follow-up questions
    if len(asked_questions) >= MAX_CONCERN_FOLLOWUP_TURNS:
        logger.info(f"Max concern follow-up turns reached ({MAX_CONCERN_FOLLOWUP_TURNS}). Ending conversation.")
        return "Thank you for sharing those details. I'll modify your care plan accordingly and continue to follow up with you. Thank you for your time. Goodbye.", False
    
    # Find the primary symptom
    primary_symptom = None
    for symptom in symptoms:
        symptom_lower = symptom.lower().strip()
        if symptom_lower in SYMPTOM_FOLLOWUP_SEQUENCE:
            primary_symptom = symptom_lower
            break
        # Try partial matching
        for key in SYMPTOM_FOLLOWUP_SEQUENCE:
            if key in symptom_lower or symptom_lower in key:
                primary_symptom = key
                break
        if primary_symptom:
            break
    
    if not primary_symptom:
        # Symptom not in our database, use default and STOP after this
        logger.info(f"Symptom not in sequence database. Using default question (final turn).")
        return DEFAULT_FOLLOWUP_QUESTION, False
    
    # Get the sequence of questions for this symptom
    question_sequence = SYMPTOM_FOLLOWUP_SEQUENCE[primary_symptom]
    
    # Find the next unanswered question
    # asked_questions contains all questions we've already ASKED (patient has responded to them)
    next_question_index = len(asked_questions)
    
    # Check: Have all questions been asked AND answered?
    # If next_question_index >= len(question_sequence), all questions have been asked and answered
    if next_question_index >= len(question_sequence):
        logger.info(f"All {len(question_sequence)} follow-up questions for {primary_symptom} have been asked and answered. Ending conversation.")
        return "Thank you for sharing those details. I'll modify your care plan accordingly and continue to follow up with you. Thank you for your time. Goodbye.", False
    
    # Get the next question in sequence (this question has NOT been asked yet)
    next_question = question_sequence[next_question_index]
    
    logger.info(f"Generating follow-up question #{next_question_index + 1} of {len(question_sequence)}: {next_question}")
    
    # CRITICAL FIX: We're returning a QUESTION that needs an ANSWER
    # We must return True so voice-service waits for the patient's response
    # Only return False when we return a CLOSING MESSAGE (after all questions answered)
    logger.info(f"Requires follow-up: TRUE (waiting for answer to question #{next_question_index + 1})")
    return next_question, True


def should_ask_followup(classification: str, continuity_action: str) -> bool:
    """Determine if follow-up question should be asked."""
    return classification == "CONCERN" and continuity_action == "CLINICAL_REVIEW"


# ── Request/Response Models ────────────────────────────────────────────────────

class VoiceResponseRequest(BaseModel):
    """Request from voice-service with captured speech response."""
    checkin_id: str = Field(
        ...,
        description="Check-in ID linking to patient/care plan context"
    )
    patient_response: str = Field(
        ...,
        min_length=1,
        description="Speech-to-text transcript from Twilio"
    )
    source: str = Field(
        default="voice",
        description="Source of response (always 'voice' for this endpoint)"
    )
    call_sid: Optional[str] = Field(
        default=None,
        description="Twilio call SID for audit trail"
    )
    from_: Optional[str] = Field(
        default=None,
        alias="from",
        description="Caller phone number"
    )
    to: Optional[str] = Field(
        default=None,
        description="Destination phone number"
    )

    class Config:
        allow_population_by_field_name = True


class VoiceResponseResult(BaseModel):
    """Response from voice response processing."""
    success: bool
    # Response Analyzer output
    classification: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
    symptoms: Optional[list] = None
    concerns: Optional[list] = None
    # Care Continuity output
    continuity_action: Optional[str] = None
    continuity_reason: Optional[str] = None
    requires_appointment: Optional[bool] = None
    # Message for patient (TwiML)
    message: str = "Thank you. Your response has been recorded."
    # Multi-turn conversation support
    requires_followup: bool = False
    followup_question: Optional[str] = None
    # Context
    care_plan_id: Optional[str] = None
    mrn: Optional[str] = None
    error: Optional[str] = None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/send-response",
    response_model=VoiceResponseResult,
    tags=["Voice - Response Processing"],
    summary="Process voice response through agentic pipeline",
    description=(
        "Endpoint for voice-service to send captured speech responses. "
        "Routes through existing Response Analyzer + Care Continuity orchestration. "
        "No authentication required (voice-service is internal)."
    ),
)
async def process_voice_response(
    request: VoiceResponseRequest,
) -> VoiceResponseResult:
    """
    Process voice response from voice-service.
    
    Reuses existing Response Analyzer + Care Continuity logic.
    Steps:
    1. Resolve patient context from checkin_id
    2. Call Response Analyzer Agent
    3. Call Care Continuity Agent
    4. Execute downstream actions if needed
    5. Return classification + action for voice-service
    
    Note: This is an INTERNAL endpoint, no authentication required.
    """

    logger.info(f"🔵 VOICE RESPONSE - Request received from voice-service")
    logger.info(f"   checkin_id: {request.checkin_id}")
    logger.info(f"   response length: {len(request.patient_response)}")
    logger.info(f"   call_sid: {request.call_sid}")
    logger.info(f"   source: {request.source}")

    # ── 1. Load context from checkin_id using PostgreSQL ─────────────────────
    try:
        # Add post_care and database to path for imports
        # Current location: Carepath_backend/app/api/v1/endpoints/
        # Target: Carepath_backend/
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        post_care_path = os.path.join(base_path, "post_care")
        db_path = os.path.join(base_path, "database")
        
        if post_care_path not in sys.path:
            sys.path.insert(0, post_care_path)
        if db_path not in sys.path:
            sys.path.insert(0, db_path)

        from database.connection import get_db_connection as get_conn_func
        from database.connection import close_db_connection as close_conn_func

        conn = get_conn_func()
        cursor = conn.cursor()

        # Step 1: Get task info from checkin_id
        cursor.execute(
            "SELECT task_id, checkin_type, message FROM follow_up_checkins WHERE checkin_id = %s",
            (request.checkin_id,)
        )
        checkin_row = cursor.fetchone()

        if not checkin_row:
            close_conn_func(conn)
            logger.error(f"Check-in {request.checkin_id} not found")
            return VoiceResponseResult(
                success=False,
                error=f"Check-in {request.checkin_id} not found",
                message="Sorry, we could not find your check-in record."
            )

        task_id, task_type, checkin_message = checkin_row
        logger.info(f"✓ Found task: {task_id}, type: {task_type}")

        # Step 2: Get care_plan_id from task
        cursor.execute(
            "SELECT care_plan_id FROM care_plan_tasks WHERE task_id = %s",
            (task_id,)
        )
        task_row = cursor.fetchone()

        if not task_row:
            close_conn_func(conn)
            logger.error(f"Task {task_id} not found")
            return VoiceResponseResult(
                success=False,
                error=f"Task {task_id} not found",
                message="Sorry, we could not find your task record."
            )

        care_plan_id = task_row[0]
        logger.info(f"✓ Found care_plan_id: {care_plan_id}")

        # Step 3: Get MRN and doctor_instructions from care plan
        cursor.execute(
            "SELECT mrn, doctor_instructions FROM care_plans WHERE care_plan_id = %s",
            (care_plan_id,)
        )
        plan_row = cursor.fetchone()

        if not plan_row:
            close_conn_func(conn)
            logger.error(f"Care plan {care_plan_id} not found")
            return VoiceResponseResult(
                success=False,
                error=f"Care plan {care_plan_id} not found",
                message="Sorry, we could not find your care plan."
            )

        mrn, doctor_instructions = plan_row
        logger.info(f"✓ Found MRN: {mrn}")

        # ══════════════════════════════════════════════════════════════════════════════
        # STEP 4: GET TURN NUMBER AND RETRIEVE PRIOR TURN CONTEXT (MULTI-TURN)
        # ══════════════════════════════════════════════════════════════════════════════
        
        turn_number = get_current_turn_number(conn, request.checkin_id, request.call_sid)
        logger.info(f"✓ Current turn number: {turn_number}")
        
        prior_turn = None
        prior_turn_response = None
        prior_classification = None
        prior_symptoms = None
        prior_concerns = None
        
        if turn_number > 1:
            prior_turn = get_prior_turn(conn, request.checkin_id, request.call_sid)
            if prior_turn:
                prior_turn_response = prior_turn.get("patient_response")
                prior_classification = prior_turn.get("classification")
                prior_symptoms = prior_turn.get("symptoms")
                prior_concerns = prior_turn.get("concerns")
                logger.info(f"✓ Prior turn found: classification={prior_classification}, symptoms={prior_symptoms}")

        # Store response in database (will be updated if Response Analyzer processes it)
        cursor.execute(
            "UPDATE follow_up_checkins SET response = %s, status = 'RESPONSE_RECEIVED', response_received_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE checkin_id = %s",
            (request.patient_response, request.checkin_id)
        )
        conn.commit()
        close_conn_func(conn)

        logger.info(f"✓ Response stored: {request.checkin_id}")

    except Exception as e:
        logger.error(f"❌ VOICE RESPONSE ERROR - Database context resolution failed")
        logger.error(f"   checkin_id: {request.checkin_id}")
        logger.error(f"   Error: {str(e)}", exc_info=True)
        return VoiceResponseResult(
            success=False,
            error=f"Failed to load context: {str(e)}",
            message="Sorry, there was an error processing your response."
        )

    # ── 2. Call Response Analyzer Agent ────────────────────────────────────
    try:
        from agents.response_analyzer.agent import orchestrate_response_analysis
        from agents.response_analyzer.schemas import ResponseAnalyzerInput

        analyzer_input = ResponseAnalyzerInput(
            mrn=mrn,
            care_plan_id=care_plan_id,
            task_id=task_id,
            checkin_id=request.checkin_id,
            task_type=task_type,
            patient_response=request.patient_response,
            doctor_instruction=doctor_instructions,
            task_description=checkin_message,
            # NEW: Multi-turn conversation context
            turn_number=turn_number,
            prior_patient_response=prior_turn_response,
            prior_classification=prior_classification,
            prior_symptoms=prior_symptoms,
            prior_concerns=prior_concerns,
        )

        logger.info(f"Calling Response Analyzer for checkin {request.checkin_id}")
        analyzer_output = orchestrate_response_analysis(analyzer_input)

        logger.info(
            f"Response Analyzer result: classification={analyzer_output.classification}, "
            f"confidence={analyzer_output.confidence}"
        )

        # ── 3. Call Care Continuity Agent ──────────────────────────────────
        continuity_action = None
        continuity_reason = None
        requires_appointment = False
        message = "Thank you. Your response has been recorded."
        requires_followup = False
        followup_question = None

        try:
            from agents.care_continuity.agent import process_care_continuity
            from agents.care_continuity.schemas import CareContinuityInput

            continuity_input = CareContinuityInput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                task_id=task_id,
                checkin_id=request.checkin_id,
                classification=analyzer_output.classification,
                summary=analyzer_output.summary,
                symptoms=analyzer_output.symptoms or [],
                concerns=analyzer_output.concerns or [],
                confidence=analyzer_output.confidence,
                doctor_instruction=doctor_instructions,
                task_description=checkin_message,
            )

            logger.info(f"Calling Care Continuity for checkin {request.checkin_id}, "
                       f"classification={analyzer_output.classification}")
            continuity_output = process_care_continuity(continuity_input)

            continuity_action = continuity_output.continuity_action
            continuity_reason = continuity_output.reason
            requires_appointment = continuity_output.requires_appointment

            logger.info(
                f"Care Continuity result: action={continuity_action}, "
                f"requires_appointment={requires_appointment}"
            )

            # ── 4A. URGENT FLOW: Appointment booking ─────────────────────────
            if analyzer_output.classification == "URGENT" and continuity_action == "URGENT_REVIEW":
                logger.info(f"🔴 URGENT classification detected - initiating appointment workflow")
                requires_followup = False
                followup_question = None
                
                try:
                    # Import existing Appointment Agent tools (now using corrected DB config)
                    from app.services.alternate_care.agents.appointment_agent import (
                        search_nearby_providers as apt_search_providers,
                        check_availability as apt_check_availability,
                        book_appointment as apt_book_appointment,
                    )
                    
                    # Patient location: use coordinates near existing provider data
                    # (patient_ehr has no lat/lon; providers are in Chennai test area)
                    patient_lat = 13.08
                    patient_lon = 80.27
                    
                    # Step 1: Search for URGENT_CARE providers using existing tool
                    logger.info(f"URGENT: Calling search_nearby_providers(destination=URGENT_CARE)")
                    search_result = apt_search_providers(
                        latitude=patient_lat,
                        longitude=patient_lon,
                        destination="URGENT_CARE",
                        radius_km=15.0,
                    )
                    
                    if not search_result.get("ok") or search_result.get("count", 0) == 0:
                        # Fallback to PCP
                        logger.info(f"URGENT: No URGENT_CARE providers, trying PCP...")
                        search_result = apt_search_providers(
                            latitude=patient_lat,
                            longitude=patient_lon,
                            destination="PCP",
                            radius_km=15.0,
                        )
                    
                    if not search_result.get("ok") or search_result.get("count", 0) == 0:
                        logger.warning(f"URGENT: No providers found by search_nearby_providers()")
                        message = (
                            "Your symptoms have been classified as requiring urgent medical attention. "
                            "I couldn't find a suitable urgent-care provider near your location. "
                            "I'll notify the care team for further assistance. "
                            "Please contact your doctor or visit the nearest emergency room. "
                            "Take care and goodbye."
                        )
                    else:
                        # Step 2: Select the nearest provider (first in distance-sorted list)
                        provider = search_result["providers"][0]
                        provider_id = provider["provider_id"]
                        provider_name = provider.get("provider_name", "a doctor")
                        facility_name = provider.get("facility_name", provider_name)
                        
                        logger.info(f"URGENT: Provider selected: {provider_name} ({provider_id})")
                        
                        # Step 3: Check availability using existing tool
                        logger.info(f"URGENT: Calling check_availability(provider_id={provider_id})")
                        avail_result = apt_check_availability(
                            provider_id=provider_id,
                            destination="URGENT_CARE",
                            patient_id=mrn,
                        )
                        
                        if not avail_result.get("ok") or avail_result.get("count", 0) == 0:
                            logger.warning(f"URGENT: No available slots returned by check_availability()")
                            message = (
                                "Your symptoms have been classified as requiring urgent medical attention. "
                                f"I found {provider_name} near your location, "
                                "but I couldn't find an available appointment right now. "
                                "I'll notify the care team so they can assist you. "
                                "Take care and goodbye."
                            )
                        else:
                            # Step 4: Select the earliest slot
                            slot = avail_result["slots"][0]
                            slot_id = slot["slot_id"]
                            start_time = slot["start_time"]
                            
                            # Format time for speech
                            from datetime import datetime
                            try:
                                dt = datetime.fromisoformat(start_time)
                                formatted_time = dt.strftime("%B %d at %I:%M %p")
                            except Exception:
                                formatted_time = start_time
                            
                            logger.info(f"URGENT: Slot selected: {slot_id} at {start_time}")
                            
                            # Step 5: Book the appointment using existing tool
                            logger.info(f"URGENT: Calling book_appointment(provider={provider_id}, slot={slot_id}, patient={mrn})")
                            try:
                                booking_result = apt_book_appointment(
                                    provider_id=provider_id,
                                    slot_id=slot_id,
                                    patient_id=mrn,
                                )
                            except Exception as book_tool_err:
                                # book_appointment tool requires external service;
                                # fallback to direct DB booking using same schema
                                logger.warning(f"URGENT: book_appointment() tool error: {book_tool_err}, using direct DB booking")
                                conn_book = get_db_connection()
                                booking_result = {"ok": False}
                                if conn_book:
                                    try:
                                        import uuid
                                        cur_book = conn_book.cursor()
                                        cur_book.execute(
                                            "UPDATE provider_slots SET status = 'BOOKED', updated_at = CURRENT_TIMESTAMP WHERE slot_id = %s AND status = 'AVAILABLE'",
                                            (slot_id,)
                                        )
                                        if cur_book.rowcount > 0:
                                            apt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
                                            cur_book.execute(
                                                "INSERT INTO appointments (appointment_id, mrn, provider_id, slot_id, start_time, end_time, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, 'BOOKED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                                                (apt_id, mrn, provider_id, slot_id, slot["start_time"], slot["end_time"])
                                            )
                                            conn_book.commit()
                                            booking_result = {"ok": True, "appointment_id": apt_id, "status": "BOOKED"}
                                            logger.info(f"✓ URGENT: Direct DB booking succeeded: {apt_id}")
                                        else:
                                            conn_book.rollback()
                                    finally:
                                        close_db_connection(conn_book)
                            
                            if booking_result.get("ok"):
                                booked_apt_id = booking_result.get("appointment_id", "")
                                logger.info(f"✓ URGENT: book_appointment() succeeded: {booked_apt_id}")
                                message = (
                                    "Your symptoms have been classified as requiring urgent medical attention. "
                                    f"I've booked an appointment for you with {provider_name} "
                                    f"at {facility_name} for {formatted_time}. "
                                    "Please visit the facility at the scheduled time. "
                                    "Take your discharge information with you. "
                                    "Your post-care team will also follow up with you. "
                                    "Take care."
                                )
                            else:
                                booking_error = booking_result.get("error", "unknown error")
                                logger.warning(f"URGENT: book_appointment() failed: {booking_error}")
                                message = (
                                    "Your symptoms have been classified as requiring urgent medical attention. "
                                    "Your appointment could not be confirmed right now. "
                                    "I'll notify the care team for assistance. "
                                    "Please contact your doctor directly if symptoms persist. "
                                    "Take care and goodbye."
                                )
                
                except Exception as urgent_err:
                    logger.error(f"URGENT appointment workflow failed: {urgent_err}", exc_info=True)
                    message = (
                        "Your symptoms have been classified as requiring urgent medical attention. "
                        "I was unable to check appointment availability at this time. "
                        "Please contact your care team directly or visit your nearest emergency room. "
                        "Your care team has been notified. Take care and goodbye."
                    )
                
                except Exception as urgent_err:
                    logger.error(f"URGENT appointment workflow failed: {urgent_err}", exc_info=True)
                    message = (
                        "I understand. Your symptoms require urgent medical attention. "
                        "I was unable to check appointment availability at this time. "
                        "Please contact your care team directly or visit your nearest emergency room. "
                        "Your care team has been notified. Take care and goodbye."
                    )

            # ── 4B. Generate Multi-Turn Follow-Up for CONCERN ────────────────
            # Check if follow-up question is needed
            elif should_ask_followup(analyzer_output.classification, continuity_action):
                # Reconnect to database to get conversation history
                conn_for_history = get_db_connection()
                try:
                    # Get questions already asked in this conversation
                    asked_questions = get_asked_questions(conn_for_history, request.checkin_id, request.call_sid or "unknown")
                    
                    logger.info(f"═══════════════════════════════════════════════════════════")
                    logger.info(f"TURN {turn_number} - CONCERN MULTI-TURN DECISION")
                    logger.info(f"Patient Response: {request.patient_response}")
                    logger.info(f"Classification: {analyzer_output.classification}")
                    logger.info(f"Care Continuity Action: {continuity_action}")
                    logger.info(f"Symptoms: {analyzer_output.symptoms}")
                    logger.info(f"Previously Asked Questions ({len(asked_questions)}): {asked_questions}")
                    
                    # Generate next follow-up question (respects question sequence)
                    next_question, should_continue = get_next_followup_question(
                        symptoms=analyzer_output.symptoms or [],
                        asked_questions=asked_questions,
                        conn=conn_for_history,
                        checkin_id=request.checkin_id,
                        call_sid=request.call_sid or "unknown"
                    )
                    
                    requires_followup = should_continue
                    
                    if should_continue:
                        followup_question = next_question
                        # Generate combined message (acknowledgment + question)
                        acknowledgment = "I understand."
                        message = f"{acknowledgment} {followup_question}"
                        
                        logger.info(f"New Follow-up Question: {followup_question}")
                        logger.info(f"Waiting For Patient Answer: YES")
                        logger.info(f"requires_followup: TRUE")
                        logger.info(f"═══════════════════════════════════════════════════════════")
                    else:
                        # All questions answered - CONCERN assessment complete
                        followup_question = None
                        logger.info(f"All questions answered - assessment complete")
                        logger.info(f"Waiting For Patient Answer: NO")
                        logger.info(f"requires_followup: FALSE")
                        
                        # ── 4B-1. REVISE CARE PLAN FOR CONCERN (when assessment complete) ───
                        try:
                            from post_care.services.care_plan_service_postgresql import revise_care_plan
                            from post_care.agents.follow_up.agent import orchestrate_follow_up
                            from post_care.agents.follow_up.schemas import FollowUpInput
                            
                            logger.info(f"───────────────────────────────────────────────────────────")
                            logger.info(f"CARE PLAN UPDATE")
                            logger.info(f"Care Plan ID: {care_plan_id}")
                            logger.info(f"Symptoms: {analyzer_output.symptoms}")
                            logger.info(f"Continuity Action: {continuity_action}")
                            
                            # Revise the existing care plan (does NOT create a new one)
                            revised_plan = revise_care_plan(
                                care_plan_id=care_plan_id,
                                mrn=mrn,
                                continuity_action=continuity_action,
                                classification=analyzer_output.classification,
                                symptoms=analyzer_output.symptoms or [],
                                concerns=analyzer_output.concerns or [],
                                summary=analyzer_output.summary,
                                confidence=analyzer_output.confidence,
                            )
                            
                            # Re-run Follow-up Agent with updated tasks
                            revised_tasks = revised_plan.get("tasks", [])
                            logger.info(f"Tasks Added/Updated: {len(revised_tasks)}")
                            
                            if revised_tasks:
                                for task in revised_tasks:
                                    logger.info(f"  - {task.get('task_type')}: {task.get('description')}")
                                
                                follow_up_input = FollowUpInput(
                                    mrn=mrn,
                                    care_plan_id=care_plan_id,
                                    risk_level=revised_plan.get("risk_level", "HIGH"),
                                    intensity=revised_plan.get("intensity", "INTENSIVE"),
                                    tasks=[
                                        {
                                            "task_id": t.get("task_id"),
                                            "task_type": t.get("task_type"),
                                            "status": t.get("status", "PENDING"),
                                            "description": t.get("description"),
                                            "doctor_instruction": t.get("doctor_instruction"),
                                        }
                                        for t in revised_tasks
                                    ],
                                )
                                
                                follow_up_output = orchestrate_follow_up(follow_up_input)
                                
                                # Generate updated closing message
                                message = (
                                    "Thank you for sharing that with me. I've reviewed your responses and updated your care plan accordingly. "
                                    "I've added the necessary follow-up tasks and monitoring. Your care team will continue to follow up with you. "
                                    "Take care and goodbye."
                                )
                                logger.info(f"Care Plan Modified: YES")
                                logger.info(f"Final Message: {message}")
                            else:
                                # No new tasks, use default closing message
                                message = next_question  # This contains the closing message
                                logger.info(f"Care Plan Modified: NO (no new tasks needed)")
                                logger.info(f"Final Message: {message}")
                            
                            logger.info(f"───────────────────────────────────────────────────────────")
                        
                        except Exception as care_plan_err:
                            logger.warning(f"CONCERN: Care plan revision failed (non-fatal): {care_plan_err}", exc_info=True)
                            # Use default closing message if care plan revision fails
                            message = next_question  # This contains the closing message
                            logger.info(f"Care Plan Modified: FAILED")
                            logger.info(f"Final Message (fallback): {message}")
                        
                        logger.info(f"═══════════════════════════════════════════════════════════")
                finally:
                    close_db_connection(conn_for_history)
            else:
                # NORMAL or other classifications: keep default message
                requires_followup = False
                followup_question = None
                logger.info(f"No follow-up required for classification={analyzer_output.classification}")

        except Exception as cc_err:
            logger.error(f"Care Continuity failed (non-fatal): {cc_err}", exc_info=True)
            # Continue with Response Analyzer result only

        # ══════════════════════════════════════════════════════════════════════════════
        # STEP 5: STORE VOICE CONVERSATION TURN FOR FUTURE CONTEXT
        # ══════════════════════════════════════════════════════════════════════════════
        
        try:
            conn = get_db_connection()
            store_voice_turn(
                conn=conn,
                checkin_id=request.checkin_id,
                call_sid=request.call_sid or "unknown",
                turn_number=turn_number,
                patient_response=request.patient_response,
                classification=analyzer_output.classification,
                symptoms=analyzer_output.symptoms,
                concerns=analyzer_output.concerns,
                followup_question=followup_question
            )
            close_db_connection(conn)
        except Exception as turn_err:
            logger.warning(f"Failed to store voice turn (non-fatal): {turn_err}")
            # Continue even if turn storage fails

        return VoiceResponseResult(
            success=True,
            classification=analyzer_output.classification,
            confidence=analyzer_output.confidence,
            summary=analyzer_output.summary,
            symptoms=analyzer_output.symptoms or [],
            concerns=analyzer_output.concerns or [],
            continuity_action=continuity_action,
            continuity_reason=continuity_reason,
            requires_appointment=requires_appointment,
            message=message,
            requires_followup=requires_followup,
            followup_question=followup_question,
            care_plan_id=care_plan_id,
            mrn=mrn,
        )

    except Exception as e:
        logger.error(f"❌ VOICE RESPONSE ERROR - Response Analyzer failed")
        logger.error(f"   checkin_id: {request.checkin_id}")
        logger.error(f"   Error: {str(e)}", exc_info=True)
        return VoiceResponseResult(
            success=False,
            error=f"Analysis failed: {str(e)}",
            message="Sorry, there was an error analyzing your response.",
            care_plan_id=care_plan_id if 'care_plan_id' in locals() else None,
            mrn=mrn if 'mrn' in locals() else None,
        )
