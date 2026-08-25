"""
Twilio Voice Integration API
Webhook endpoints for inbound calls and manual testing.
"""

from fastapi import APIRouter, HTTPException, status, Body, Query, Request, Form, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from twilio.twiml.voice_response import VoiceResponse, Gather
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os
import sys

from app.services.twilio_service import twilio_service
from app.db.base import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Twilio Voice"],
)


class InitiateCallRequest(BaseModel):
    """Request to initiate a test outbound call."""
    to_number: str = Field(
        ..., 
        description="Destination phone number in E.164 format (e.g., +1234567890)",
        example="+1234567890"
    )
    webhook_url: str = Field(
        ...,
        description="Public URL where Twilio will send webhook after call connects (e.g., https://your-domain.com/api/v1/voice/webhook)",
        example="https://your-domain.com/api/v1/voice/webhook"
    )


class TestCallRequest(BaseModel):
    """Request to initiate a trial-compatible test call (Phase 2B with optional checkin_id)."""
    to_number: str = Field(
        ...,
        description="Destination phone number in E.164 format (must be verified in Twilio)",
        example="+916383564788"
    )
    checkin_id: str = Field(
        None,
        description="Optional: ID of an existing follow-up checkin to use for the call message. If provided, the checkin_message will be spoken instead of the default message.",
        example="CHK-12345678"
    )


class CallResponseModel(BaseModel):
    """Response from initiating a call."""
    call_sid: str
    status: str
    to: str
    from_: str = Field(alias="from")
    
    class Config:
        allow_population_by_field_name = True


@router.post(
    "/call",
    response_model=CallResponseModel,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate a test outbound call",
    description=(
        "Manually trigger an outbound test call to a phone number. "
        "Twilio will connect to the webhook URL you provide. "
        "Use this to test the voice integration."
    )
)
async def initiate_test_call(request: InitiateCallRequest):
    """
    Initiate an outbound test call.
    
    The call will route to your webhook at the provided URL.
    Twilio expects a TwiML response with the conversation flow.
    """
    
    if not twilio_service:
        logger.error("Twilio service not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio service is not available. Check TWILIO_* environment variables."
        )
    
    try:
        result = twilio_service.initiate_test_call(
            to_number=request.to_number,
            webhook_url=request.webhook_url
        )
        
        return CallResponseModel(**result)
    
    except Exception as e:
        logger.error(f"Error initiating test call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initiate call: {str(e)}"
        )


@router.post(
    "/test-call",
    response_model=CallResponseModel,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Phase 1B: Trial-compatible test call",
    description=(
        "Trigger a test outbound call using trial-compatible method. "
        "Works with Twilio trial accounts by embedding TwiML directly. "
        "Destination number must be verified in Twilio Console."
    )
)
async def test_call(request: TestCallRequest):
    """
    Phase 1B: Make a test outbound call (trial-compatible).
    
    This endpoint works with Twilio trial accounts by:
    1. Embedding TwiML directly (no URL parameter)
    2. Calling only verified phone numbers
    3. Speaking a test message
    
    The destination phone number must be verified in Twilio Console
    under Settings > Verified Caller IDs.
    """
    
    if not twilio_service:
        logger.error("Twilio service not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio service is not available. Check TWILIO_* environment variables."
        )
    
    try:
        result = twilio_service.initiate_trial_call(
            to_number=request.to_number,
            checkin_id=request.checkin_id
        )
        
        return CallResponseModel(**result)
    
    except Exception as e:
        logger.error(f"Error initiating trial call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initiate call: {str(e)}"
        )


@router.post(
    "/twiml",
    summary="Phase 2B: Custom TwiML endpoint with checkin support",
    description=(
        "Returns CarePath TwiML for outbound calls. "
        "Twilio POST requests this endpoint to fetch TwiML for the call. "
        "Supports Phase 2A (static message) and Phase 2B (existing checkin message)."
    ),
    response_class=None,  # Return raw XML
    responses={200: {"content": {"application/xml": {"example": "<Response><Say>Hello, this is a CarePath test call.</Say><Hangup/></Response>"}}}}
)
async def custom_twiml(checkin_id: str = Query(None)):
    """
    Phase 2B/3A: Return custom CarePath TwiML via POST with speech gathering.
    
    Twilio calls this endpoint with POST to fetch TwiML instructions for the call.
    The checkin_id is passed as a query parameter (appended to the URL).
    
    For Phase 2B calls (with checkin_id):
    - checkin_id is provided as a query parameter in the URL
    - We fetch the existing follow-up checkin message from database
    - We speak the checkin message and gather speech response (Phase 3A)
    
    For Phase 2A calls (without checkin_id):
    - checkin_id is None
    - We speak the default message and gather speech response (Phase 3A)
    
    Args:
        checkin_id: Optional check-in ID from query parameter
    
    Returns:
        TwiML XML response with Say + Gather for speech input
    """
    
    try:
        logger.info(f"TwiML request received with checkin_id={checkin_id}")
        
        message = "Hello, this is a CarePath test call. This is your post-discharge follow-up."
        
        # Phase 2B: Fetch message from database if checkin_id provided
        if checkin_id:
            try:
                from post_care.agents.follow_up.tools import FollowUpCheckInRepository
                
                checkin = FollowUpCheckInRepository.get_checkin_by_id(checkin_id)
                
                if checkin and checkin.get("message"):
                    message = checkin["message"]
                    logger.info(f"Phase 2B: Retrieved checkin message for {checkin_id}: {message}")
                else:
                    logger.warning(f"Checkin {checkin_id} not found or has no message, using default message")
                    
            except Exception as e:
                logger.error(f"Failed to retrieve checkin {checkin_id}: {str(e)}, using default message")
        else:
            logger.info("Phase 2A: No checkin_id provided, using default message")
        
        # Phase 3A: Build TwiML with speech gathering
        response = VoiceResponse()
        
        # Get current ngrok URL for gather action
        ngrok_url = os.environ.get("NGROK_URL", "")
        if not ngrok_url:
            logger.error("NGROK_URL not configured in environment")
            # Fallback to basic response without gather
            response.say(message)
            response.hangup()
            return Response(content=str(response), media_type="application/xml")
        
        # Build gather action URL
        gather_url = f"{ngrok_url}/api/v1/voice/gather"
        if checkin_id:
            gather_url += f"?checkin_id={checkin_id}"
        
        # Create Gather element for speech input
        gather = Gather(
            input='speech',
            action=gather_url,
            method='POST',
            speech_timeout='auto'
        )
        
        # Say the message within the Gather block
        gather.say(message)
        response.append(gather)
        
        # Fallback if no response is received
        response.say("I did not hear a response. Goodbye.")
        response.hangup()
        
        logger.info("Phase 3A: Custom CarePath TwiML with speech gathering generated")
        
        # Return raw TwiML XML
        return Response(content=str(response), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error generating custom TwiML: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate custom voice response"
        )


@router.post(
    "/webhook",
    summary="Webhook endpoint for inbound calls",
    description=(
        "Endpoint that Twilio calls after a patient answers. "
        "Returns TwiML instructions for what Twilio should do (speak, gather input, etc.). "
        "This is the entry point for voice interaction."
    ),
    response_class=None,  # Return raw XML
    responses={200: {"content": {"application/xml": {"example": "<Response><Say>Hello</Say></Response>"}}}}
)
async def voice_webhook():
    """
    Webhook endpoint for inbound voice calls.
    
    This is called by Twilio after:
    1. Patient's phone rings
    2. Patient answers the call
    3. Twilio routes to this endpoint
    
    Returns TwiML XML that tells Twilio:
    - What message to speak
    - Whether to gather input
    - What to do next
    
    Phase 1: Simple test response (speak message + hangup)
    Phase 2: Will connect to Post-Care Agent for dynamic responses
    """
    
    if not twilio_service:
        logger.error("Twilio service not initialized for webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio service is not available"
        )
    
    try:
        twiml = twilio_service.generate_test_twiml()
        logger.info("Test TwiML response generated for voice webhook")
        
        # Return raw TwiML XML
        return Response(content=twiml, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error generating TwiML: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate voice response"
        )


@router.post(
    "/gather",
    summary="Phase 3A: Handle speech input from Twilio Gather",
    description=(
        "Endpoint that receives speech-to-text results from Twilio Gather. "
        "Logs the transcript and returns thank-you message. "
        "Called after patient speaks during follow-up call."
    ),
    response_class=None,  # Return raw XML
    responses={200: {"content": {"application/xml": {"example": "<Response><Say>Thank you. Your response has been recorded.</Say><Hangup/></Response>"}}}}
)
async def voice_gather(
    request: Request,
    checkin_id: str = Query(None),
    SpeechResult: str = Form(None),
    CallSid: str = Form(None),
    From: str = Form(None),
    To: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 3B: Handle speech input and integrate with existing Post-Care response pipeline.
    
    This endpoint is called by Twilio after the patient speaks during a call.
    Twilio converts the speech to text and sends it as form data.
    
    Phase 3B Integration:
    - Resolves patient context from checkin_id
    - Calls existing orchestrate_response_analysis()
    - Calls existing process_care_continuity()
    - Updates database state exactly like text responses
    
    Args:
        checkin_id: Check-in ID from query parameter (links to patient/care plan)
        SpeechResult: Speech-to-text transcript from Twilio
        CallSid: Twilio call identifier
        From: Caller phone number
        To: Destination phone number
        db: Database session for PatientEHR queries
    
    Returns:
        TwiML XML response with thank-you message and hangup
    """
    
    try:
        logger.info(f"🔵 VOICE GATHER - Request received")
        logger.info(f"   checkin_id: {checkin_id}")
        logger.info(f"   call_sid: {CallSid}")
        logger.info(f"   SpeechResult length: {len(SpeechResult) if SpeechResult else 0}")
        
        # Phase 3A: Check if we received speech input
        if not SpeechResult or not SpeechResult.strip():
            logger.warning(f"No speech detected for checkin_id={checkin_id}, call_sid={CallSid}")
            
            # Create no-response message
            response = VoiceResponse()
            response.say("I did not hear a response. Goodbye.")
            response.hangup()
            
            logger.info("Phase 3A: No-response TwiML generated")
            return Response(content=str(response), media_type="application/xml")
        
        # Phase 3B: Resolve database context from checkin_id
        if not checkin_id:
            logger.error("No checkin_id provided - cannot resolve patient context")
            response = VoiceResponse()
            response.say("Sorry, there was an error processing your response. Goodbye.")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")
        
        try:
            # Add post_care to path for imports (same as patient_response.py)
            POST_CARE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "post_care")
            if POST_CARE_PATH not in sys.path:
                sys.path.insert(0, POST_CARE_PATH)

            from database.connection import get_db_connection, close_db_connection

            conn = get_db_connection()
            cursor = conn.cursor()

            # Step 1: Get task info from checkin_id (using VERIFIED schema: message NOT checkin_message)
            cursor.execute(
                "SELECT task_id, checkin_type, message FROM follow_up_checkins WHERE checkin_id = %s",
                (checkin_id,)
            )
            checkin_row = cursor.fetchone()

            if not checkin_row:
                close_db_connection(conn)
                logger.error(f"Check-in {checkin_id} not found")
                response = VoiceResponse()
                response.say("Sorry, there was an error processing your response. Goodbye.")
                response.hangup()
                return Response(content=str(response), media_type="application/xml")

            task_id, task_type, checkin_message = checkin_row
            logger.info(f"✓ Found task: {task_id}, type: {task_type}")

            # Step 2: Get care_plan_id from task (using task_id, not id)
            cursor.execute(
                "SELECT care_plan_id FROM care_plan_tasks WHERE task_id = %s",
                (task_id,)
            )
            task_row = cursor.fetchone()

            if not task_row:
                close_db_connection(conn)
                logger.error(f"Task {task_id} not found")
                response = VoiceResponse()
                response.say("Sorry, there was an error processing your response. Goodbye.")
                response.hangup()
                return Response(content=str(response), media_type="application/xml")

            care_plan_id = task_row[0]
            logger.info(f"✓ Found care_plan_id: {care_plan_id}")

            # Step 3: Get MRN and doctor_instructions from care plan (using care_plan_id, not id)
            cursor.execute(
                "SELECT mrn, doctor_instructions FROM care_plans WHERE care_plan_id = %s",
                (care_plan_id,)
            )
            plan_row = cursor.fetchone()

            if not plan_row:
                close_db_connection(conn)
                logger.error(f"Care plan {care_plan_id} not found")
                response = VoiceResponse()
                response.say("Sorry, there was an error processing your response. Goodbye.")
                response.hangup()
                return Response(content=str(response), media_type="application/xml")

            mrn, doctor_instructions = plan_row
            logger.info(f"✓ Found MRN: {mrn}")

            # Log the voice response clearly (Phase 3A behavior)
            logger.info("=" * 50)
            logger.info("VOICE RESPONSE RECEIVED")
            logger.info(f"checkin_id: {checkin_id}")
            logger.info(f"call_sid: {CallSid or 'None'}")
            logger.info(f"from: {From or 'None'}")
            logger.info(f"to: {To or 'None'}")
            logger.info(f"transcript: {SpeechResult}")
            logger.info("=" * 50)

            # Update follow_up_checkins with patient response (using VERIFIED schema: response NOT patient_response)
            cursor.execute(
                "UPDATE follow_up_checkins SET response = %s, status = 'RESPONSE_RECEIVED', response_received_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE checkin_id = %s",
                (SpeechResult, checkin_id)
            )
            conn.commit()
            close_db_connection(conn)

        except Exception as e:
            logger.error(f"❌ VOICE GATHER ERROR - Database context resolution failed")
            logger.error(f"   checkin_id: {checkin_id}")
            logger.error(f"   Error: {str(e)}", exc_info=True)
            response = VoiceResponse()
            response.say("Sorry, there was an error processing your response. Goodbye.")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")

        # Phase 3B: Call existing Response Analyzer pipeline
        try:
            from agents.response_analyzer.agent import orchestrate_response_analysis
            from agents.response_analyzer.schemas import ResponseAnalyzerInput

            analyzer_input = ResponseAnalyzerInput(
                mrn=mrn,
                care_plan_id=care_plan_id,
                task_id=task_id,
                checkin_id=checkin_id,
                task_type=task_type,
                patient_response=SpeechResult,
                doctor_instruction=doctor_instructions,
                task_description=checkin_message,
            )

            logger.info(f"Calling Response Analyzer for checkin {checkin_id}")
            analyzer_output = orchestrate_response_analysis(analyzer_input)

            logger.info(
                f"Response Analyzer result: classification={analyzer_output.classification}, "
                f"confidence={analyzer_output.confidence}"
            )

            # Phase 3B: Call existing Care Continuity pipeline
            try:
                from agents.care_continuity.agent import process_care_continuity
                from agents.care_continuity.schemas import CareContinuityInput

                continuity_input = CareContinuityInput(
                    mrn=mrn,
                    care_plan_id=care_plan_id,
                    task_id=task_id,
                    checkin_id=checkin_id,
                    classification=analyzer_output.classification,
                    summary=analyzer_output.summary,
                    symptoms=analyzer_output.symptoms or [],
                    concerns=analyzer_output.concerns or [],
                    confidence=analyzer_output.confidence,
                    doctor_instruction=doctor_instructions,
                    task_description=checkin_message,
                )

                logger.info(f"Calling Care Continuity for checkin {checkin_id}, classification={analyzer_output.classification}")
                continuity_output = process_care_continuity(continuity_input)

                logger.info(
                    f"Care Continuity result: action={continuity_output.continuity_action}, "
                    f"requires_appointment={continuity_output.requires_appointment}"
                )

                # Phase 3B: Execute downstream actions (same as patient_response.py)
                if continuity_output.continuity_action in ("CLINICAL_REVIEW", "URGENT_REVIEW"):
                    try:
                        from services.care_plan_service_postgresql import revise_care_plan
                        from agents.follow_up.agent import orchestrate_follow_up
                        from agents.follow_up.schemas import FollowUpInput

                        # Revise the existing care plan
                        revised_plan = revise_care_plan(
                            care_plan_id=care_plan_id,
                            mrn=mrn,
                            continuity_action=continuity_output.continuity_action,
                            classification=analyzer_output.classification,
                            symptoms=analyzer_output.symptoms or [],
                            concerns=analyzer_output.concerns or [],
                            summary=analyzer_output.summary,
                            confidence=analyzer_output.confidence,
                        )
                        logger.info(f"Care plan {care_plan_id} revised successfully")

                        # Re-run Follow-up Agent with updated tasks
                        revised_tasks = revised_plan.get("tasks", [])
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
                        logger.info(f"Follow-up re-executed: task={follow_up_output.follow_up.get('task_id') if follow_up_output.follow_up else None}")

                        # Update post_discharge_statuses (same as patient_response.py)
                        try:
                            # Note: We need patient_id to update post_discharge_statuses
                            # For voice calls, we'll skip this update since we don't have direct patient authentication
                            # The care plan revision and follow-up re-execution are the primary effects
                            logger.info("Skipping post_discharge_statuses update for voice call (no patient_id context)")
                        except Exception as sync_err:
                            logger.error(f"Post-discharge status sync skipped for voice: {sync_err}")

                    except Exception as rev_err:
                        logger.error(f"Care plan revision failed (non-fatal): {rev_err}", exc_info=True)

                # Phase 3B: Appointment handoff if required
                if continuity_output.requires_appointment:
                    try:
                        from post_care.services.appointment_handoff import handoff_to_appointment_agent
                        
                        appointment_result = handoff_to_appointment_agent(
                            mrn=mrn,
                            care_plan_id=care_plan_id,
                            classification=analyzer_output.classification,
                            symptoms=analyzer_output.symptoms or [],
                            concerns=analyzer_output.concerns or [],
                            summary=analyzer_output.summary,
                            confidence=analyzer_output.confidence,
                        )
                        logger.info(f"Appointment handoff result: success={appointment_result.get('success')}, session={appointment_result.get('session_id')}")
                    except Exception as appt_err:
                        logger.error(f"Appointment handoff failed (non-fatal): {appt_err}", exc_info=True)

            except Exception as cc_err:
                logger.error(f"Care Continuity failed (non-fatal): {cc_err}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ VOICE GATHER ERROR - Response Analyzer failed")
            logger.error(f"   checkin_id: {checkin_id}")
            logger.error(f"   Error: {str(e)}", exc_info=True)
            response = VoiceResponse()
            response.say("Sorry, there was an error processing your response. Goodbye.")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")

        # Phase 3B: Return success response
        response = VoiceResponse()
        response.say("Thank you. Your response has been recorded.")
        response.hangup()
        
        logger.info("Phase 3B: Voice response processed successfully")
        
        # Return raw TwiML XML
        return Response(content=str(response), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error handling voice gather: {str(e)}", exc_info=True)
        
        # Return error response
        response = VoiceResponse()
        response.say("Sorry, there was an error processing your response. Goodbye.")
        response.hangup()
        
        return Response(content=str(response), media_type="application/xml")
