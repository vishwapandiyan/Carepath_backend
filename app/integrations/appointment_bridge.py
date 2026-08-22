"""
Appointment Bridge - Integration between Post-Care Agent and Alternate Care Agent

This module bridges the post-discharge monitoring workflow with the alternate
care appointment booking system.

Flow:
    Post-Care Care Continuity Agent
        ↓ (requires_appointment=True)
    Appointment Bridge (this module)
        ↓
    Alternate Care Navigation Agent
        ↓
    Appointment Booking
        ↓
    Return appointment options/confirmation
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class AppointmentBridgeService:
    """
    Service to bridge post-care agent workflow with alternate care appointment system.
    
    Responsibilities:
    - Determine if appointment is needed based on care continuity output
    - Extract patient context from EHR
    - Trigger alternate care navigation agent
    - Coordinate appointment booking workflow
    - Return appointment recommendations to care manager
    """
    
    async def trigger_appointment_workflow(
        self,
        patient_id: str,
        care_continuity_output: Dict[str, Any],
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger appointment workflow when post-care agent determines appointment is needed.
        
        Args:
            patient_id: Patient identifier
            care_continuity_output: Output from care continuity agent
            db: Database session
        
        Returns:
            Dictionary with appointment recommendations or None if not needed
        """
        
        # Check if appointment is required
        if not care_continuity_output.get("requires_appointment", False):
            logger.info(f"Patient {patient_id}: No appointment required")
            return None
        
        logger.info(
            f"Patient {patient_id}: Appointment required. "
            f"Classification: {care_continuity_output.get('classification')}, "
            f"Action: {care_continuity_output.get('continuity_action')}"
        )
        
        try:
            # Get patient EHR data
            from app.models.ehr import PatientEHR
            
            stmt = select(PatientEHR).where(PatientEHR.patient_id == patient_id)
            result = await db.execute(stmt)
            patient_ehr = result.scalar_one_or_none()
            
            if not patient_ehr:
                logger.error(f"Patient {patient_id} not found in EHR")
                return {
                    "success": False,
                    "error": "Patient not found in EHR system",
                    "requires_manual_booking": True
                }
            
            # Extract patient context
            patient_context = self._extract_patient_context(patient_ehr, care_continuity_output)
            
            # Determine urgency level
            urgency = self._determine_urgency(care_continuity_output)
            
            # Build appointment request context
            appointment_context = {
                "patient_id": patient_id,
                "urgency": urgency,
                "patient_context": patient_context,
                "care_continuity": {
                    "classification": care_continuity_output.get("classification"),
                    "continuity_action": care_continuity_output.get("continuity_action"),
                    "reason": care_continuity_output.get("reason"),
                    "symptoms": care_continuity_output.get("symptoms", []),
                    "concerns": care_continuity_output.get("concerns", [])
                },
                "requires_manual_review": care_continuity_output.get("requires_human_review", False)
            }
            
            logger.info(
                f"Patient {patient_id}: Appointment context prepared. "
                f"Urgency: {urgency}, Manual review: {appointment_context['requires_manual_review']}"
            )
            
            # For now, return the context for care manager to review
            # In production, this would trigger the alternate care navigation agent
            return {
                "success": True,
                "appointment_required": True,
                "appointment_context": appointment_context,
                "next_steps": self._get_next_steps(urgency, care_continuity_output),
                "message": f"Appointment recommended: {care_continuity_output.get('reason')}"
            }
            
        except Exception as e:
            logger.error(f"Failed to trigger appointment workflow for patient {patient_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "requires_manual_booking": True
            }
    
    def _extract_patient_context(
        self,
        patient_ehr,
        care_continuity_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract relevant patient context for appointment booking."""
        
        # Build patient location from EHR if available
        location = None
        if patient_ehr.address:
            location = {
                "address": patient_ehr.address,
                "city": getattr(patient_ehr, "city", None),
                "state": getattr(patient_ehr, "state", None),
                "zip_code": getattr(patient_ehr, "zip_code", None)
            }
        
        # Build clinical context
        clinical_flags = []
        if patient_ehr.diabetes_flag:
            clinical_flags.append("diabetes")
        if patient_ehr.heart_failure_flag:
            clinical_flags.append("heart_failure")
        if patient_ehr.hypertension_flag:
            clinical_flags.append("hypertension")
        if patient_ehr.copd_asthma_flag:
            clinical_flags.append("copd_asthma")
        if patient_ehr.ckd_flag:
            clinical_flags.append("ckd")
        
        return {
            "patient_name": patient_ehr.name,
            "mrn": patient_ehr.mrn,
            "age": patient_ehr.age,
            "gender": patient_ehr.gender,
            "location": location,
            "clinical_flags": clinical_flags,
            "discharge_date": str(patient_ehr.discharge_date) if patient_ehr.discharge_date else None,
            "discharge_destination": patient_ehr.discharge_destination,
            "symptoms_reported": care_continuity_output.get("symptoms", []),
            "concerns_reported": care_continuity_output.get("concerns", []),
            "clinical_notes": patient_ehr.clinical_notes
        }
    
    def _determine_urgency(self, care_continuity_output: Dict[str, Any]) -> str:
        """
        Determine appointment urgency level based on care continuity classification.
        
        Returns:
            "urgent" | "high_priority" | "routine"
        """
        classification = care_continuity_output.get("classification")
        
        if classification == "URGENT":
            return "urgent"
        elif classification == "CONCERN":
            return "high_priority"
        else:
            return "routine"
    
    def _get_next_steps(
        self,
        urgency: str,
        care_continuity_output: Dict[str, Any]
    ) -> List[str]:
        """Generate recommended next steps based on urgency."""
        
        steps = []
        
        if urgency == "urgent":
            steps.append("Contact patient immediately")
            steps.append("Schedule urgent appointment within 24-48 hours")
            steps.append("Consider emergency evaluation if symptoms worsen")
        elif urgency == "high_priority":
            steps.append("Review patient response and clinical data")
            steps.append("Schedule appointment within 3-5 days")
            steps.append("Monitor for symptom escalation")
        else:
            steps.append("Review at next scheduled check-in")
            steps.append("Continue monitoring patient responses")
        
        if care_continuity_output.get("requires_human_review"):
            steps.insert(0, "Clinical review required before appointment booking")
        
        return steps
    
    async def book_appointment_from_recommendation(
        self,
        patient_id: str,
        provider_id: str,
        slot_id: str,
        care_type: str,
        specialty: Optional[str],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Book an appointment after care manager reviews recommendations.
        
        This would be called from a new API endpoint when the care manager
        selects a provider and time slot from the recommendations.
        
        Args:
            patient_id: Patient identifier
            provider_id: Selected provider ID
            slot_id: Selected appointment slot ID
            care_type: Type of care needed
            specialty: Medical specialty (optional)
            db: Database session
        
        Returns:
            Appointment confirmation
        """
        
        try:
            # Import alternate care appointment service
            from app.services.alternate_care.appointment.agent import appointment_service
            from app.services.alternate_care.appointment.schemas import BookingWorkflowRequest
            
            # Create booking request
            booking_request = BookingWorkflowRequest(
                patient_id=patient_id,
                provider_id=provider_id,
                slot_id=slot_id,
                recommendation_id=None  # Post-care bookings don't have recommendation_id
            )
            
            # Book appointment
            confirmation = appointment_service.book_appointment(
                request=booking_request,
                care_type=care_type,
                specialty=specialty
            )
            
            logger.info(
                f"Appointment booked for patient {patient_id}: "
                f"appointment_id={confirmation.appointment_id}"
            )
            
            # Update post-discharge status
            await self._update_post_discharge_status(patient_id, confirmation, db)
            
            return {
                "success": True,
                "appointment": {
                    "appointment_id": confirmation.appointment_id,
                    "provider_id": confirmation.provider_id,
                    "provider_name": confirmation.provider_name,
                    "care_type": confirmation.care_type,
                    "specialty": confirmation.specialty,
                    "date": confirmation.date,
                    "time": confirmation.time,
                    "status": confirmation.status
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to book appointment for patient {patient_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _update_post_discharge_status(
        self,
        patient_id: str,
        confirmation: Any,
        db: AsyncSession
    ):
        """Update post-discharge status with appointment information."""
        
        try:
            from app.db.models import PostDischargeStatus
            
            stmt = select(PostDischargeStatus).where(PostDischargeStatus.patient_id == patient_id)
            result = await db.execute(stmt)
            status = result.scalar_one_or_none()
            
            if status:
                # Update appointment field
                status.appointment = {
                    "is_appointment": True,
                    "date": confirmation.date,
                    "appointment_id": confirmation.appointment_id,
                    "provider_name": confirmation.provider_name,
                    "care_type": confirmation.care_type,
                    "status": "BOOKED"
                }
                await db.commit()
                logger.info(f"Updated post-discharge status for patient {patient_id} with appointment")
        
        except Exception as e:
            logger.warning(f"Failed to update post-discharge status: {e}")


# Module-level singleton
appointment_bridge = AppointmentBridgeService()
