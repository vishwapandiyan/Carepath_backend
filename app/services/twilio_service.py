"""
Twilio Voice Service
Handles Twilio API operations and TwiML generation for voice integration.
Phase 2B: Trial-compatible outbound calls with embedded TwiML
"""

import os
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import logging

logger = logging.getLogger(__name__)


class TwilioService:
    """Service for managing Twilio voice operations."""
    
    def __init__(self):
        """Initialize Twilio client with credentials from environment."""
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.phone_number = os.environ.get("TWILIO_PHONE_NUMBER")
        
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            raise ValueError(
                "Missing required Twilio environment variables: "
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER"
            )
        
        self.client = Client(self.account_sid, self.auth_token)
        logger.info("Twilio client initialized successfully")
    
    def initiate_trial_call(self, to_number: str, checkin_id: str = None) -> dict:
        """
        Initiate an outbound test call (Phase 2A/2B - TRIAL ACCOUNT COMPATIBLE).
        
        Trial accounts accept url= parameter. TwiML endpoint reads checkin_id from query param.
        
        Args:
            to_number: Destination phone number (E.164 format, e.g., +916383564788)
            checkin_id: Optional check-in ID to use for the call message
        
        Returns:
            Dictionary with call SID and status
        
        Raises:
            Exception: If Twilio API call fails
        """
        try:
            # Get current ngrok URL from environment
            ngrok_url = os.environ.get("NGROK_URL")
            if not ngrok_url:
                raise ValueError("NGROK_URL is not configured in environment variables")
            
            # Build TwiML URL with optional checkin_id query parameter
            twiml_url = f"{ngrok_url}/api/v1/voice/twiml"
            if checkin_id:
                twiml_url += f"?checkin_id={checkin_id}"
                logger.info(f"Phase 2B: Using URL with checkin_id={checkin_id}")
            else:
                logger.info(f"Phase 2A: Using URL without checkin_id (default message)")
            
            # Trial accounts: Use url= parameter with ngrok endpoint
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                url=twiml_url
            )
            
            logger.info(f"Trial call initiated: {call.sid} to {to_number}")
            logger.info(f"TwiML URL: {twiml_url}")
            
            return {
                "call_sid": call.sid,
                "status": call.status,
                "to": call.to,
                "from": getattr(call, 'from_phone', self.phone_number),
            }
        
        except Exception as e:
            logger.error(f"Failed to initiate trial call: {str(e)}")
            raise
    
    def initiate_test_call(self, to_number: str, webhook_url: str) -> dict:
        """
        Initiate an outbound test call.
        
        Args:
            to_number: Destination phone number (E.164 format, e.g., +1234567890)
            webhook_url: URL where Twilio will send the webhook after call connects
                        (e.g., https://your-domain.com/api/v1/voice/webhook)
        
        Returns:
            Dictionary with call SID and status
        
        Raises:
            Exception: If Twilio API call fails
        """
        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                url=webhook_url,
                method="POST"
            )
            
            logger.info(f"Outbound test call initiated: {call.sid} to {to_number}")
            
            return {
                "call_sid": call.sid,
                "status": call.status,
                "to": call.to,
                "from": getattr(call, 'from_phone', self.phone_number),
            }
        
        except Exception as e:
            logger.error(f"Failed to initiate test call: {str(e)}")
            raise
    
    def generate_test_twiml(self) -> str:
        """
        Generate TwiML response for test call.
        
        Returns:
            TwiML XML string that:
            - Says greeting message
            - Hangs up after message
        """
        response = VoiceResponse()
        response.say("Hello, this is a CarePath test call.")
        response.hangup()
        
        return str(response)


# Initialize service singleton
try:
    twilio_service = TwilioService()
except ValueError as e:
    logger.warning(f"Twilio service not initialized: {str(e)}")
    twilio_service = None
