"""
Data mapper between CarePath and Alternate Care Agent formats
Converts CarePath intake data + EHR → Alternate Care Agent request format
"""
import logging
from typing import Dict, Any, Optional
from app.models.ehr import PatientEHR
from app.constants.mock_locations import MOCK_US_LOCATIONS, get_default_location

logger = logging.getLogger(__name__)


class AlternateCareMapper:
    """Maps CarePath intake data + EHR → Alternate Care Agent request format"""
    
    @staticmethod
    def map_symptom_onset(onset_text: Optional[str]) -> str:
        """Map onset description to sudden/gradual/chronic"""
        if not onset_text:
            return "gradual"
        
        onset_lower = onset_text.lower()
        
        # Sudden onset indicators
        if any(word in onset_lower for word in [
            "sudden", "suddenly", "acute", "now", "today", "this morning",
            "just started", "immediately", "right now", "just now", "hours"
        ]):
            return "sudden"
        
        # Chronic indicators
        elif any(word in onset_lower for word in [
            "chronic", "always", "months", "years", "long time", "ongoing", "forever"
        ]):
            return "chronic"
        
        # Default to gradual
        else:
            return "gradual"
    
    @staticmethod
    def map_symptom_trend(trend: Optional[str]) -> str:
        """Ensure symptom_trend is valid (worsening, stable, improving)"""
        if not trend:
            return "stable"
        
        trend_lower = trend.lower()
        
        if any(word in trend_lower for word in ["wors", "getting worse", "worse", "deteriorat"]):
            return "worsening"
        elif any(word in trend_lower for word in ["improv", "getting better", "better"]):
            return "improving"
        else:
            return "stable"
    
    @staticmethod
    def prepare_navigate_request(
        mrn: str,
        intake_data: Dict[str, Any],
        patient_ehr: PatientEHR,
        selected_location_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Prepare complete /navigate request
        
        Args:
            mrn: Patient MRN
            intake_data: From chatbot (includes primary_symptom_category from classifier)
            patient_ehr: Patient EHR record
            selected_location_name: User-selected mock location (e.g., "Austin, Texas")
        
        Returns:
            Complete request dict for POST /api/v1/care/navigate
        """
        
        # Get location
        if selected_location_name:
            # Use mock location
            location = None
            for loc_key, loc_data in MOCK_US_LOCATIONS.items():
                if loc_data["name"] == selected_location_name:
                    location = {
                        "latitude": loc_data["latitude"],
                        "longitude": loc_data["longitude"],
                        "address": loc_data["address"],
                        "radius_km": 15.0
                    }
                    break
            
            if not location:
                # Default to Austin
                default_loc = get_default_location()
                location = {
                    "latitude": default_loc["latitude"],
                    "longitude": default_loc["longitude"],
                    "address": default_loc["address"],
                    "radius_km": 15.0
                }
        else:
            # Use EHR address or default to Austin
            if patient_ehr.address:
                location = {
                    "address": patient_ehr.address,
                    "radius_km": 15.0
                }
            else:
                default_loc = get_default_location()
                location = {
                    "latitude": default_loc["latitude"],
                    "longitude": default_loc["longitude"],
                    "address": default_loc["address"],
                    "radius_km": 15.0
                }
        
        # Build patient data
        patient_data = {
            # Primary symptom (from constrained LLM classifier)
            "primary_symptom_category": intake_data.get("primary_symptom_category", "mild_general_symptom"),
            
            # Intake fields
            "pain_level_self_reported": intake_data.get("pain_scale"),
            "symptom_trend": AlternateCareMapper.map_symptom_trend(intake_data.get("symptom_trend")),
            "pain_onset": AlternateCareMapper.map_symptom_onset(intake_data.get("symptom_onset")),
            "pain_duration": intake_data.get("pain_duration"),
            "pain_character": intake_data.get("pain_character"),
            "pain_radiating": intake_data.get("pain_radiating"),
            
            # EHR chronic conditions
            "copd_asthma_flag": patient_ehr.copd_asthma_flag or 0,
            "cardiac_history_flag": patient_ehr.cardiac_history_flag or 0,
            "diabetes_flag": patient_ehr.diabetes_flag or 0,
            "ckd_flag": patient_ehr.ckd_flag or 0,
            "cancer_flag": patient_ehr.cancer_flag or 0,
            "hypertension_flag": patient_ehr.hypertension_flag or 0,
            
            # Chronic condition count
            "chronic_condition_count": sum([
                patient_ehr.diabetes_flag or 0,
                patient_ehr.heart_failure_flag or 0,
                patient_ehr.ckd_flag or 0,
                patient_ehr.copd_asthma_flag or 0,
                patient_ehr.cancer_flag or 0,
            ]),
            
            # Comorbidity
            "charlson_comorbidity_index": patient_ehr.charlson_comorbidity_index or 0,
            
            # Utilization
            "ed_visits_past_year": patient_ehr.previous_er_visits_12m or 0,
            "admissions_past_year": patient_ehr.previous_admissions_12m or 0,
            
            # PCP flag
            "has_pcp_flag": 1 if patient_ehr.days_since_last_pcp_visit is not None else 0,
            
            # Demographics
            "age": patient_ehr.age,
            "gender": patient_ehr.gender,
        }
        
        # Build complete request
        request = {
            "mrn": mrn,
            "patient": patient_data,
            "location": location
        }
        
        logger.info(
            f"Prepared navigate request for MRN {mrn}: "
            f"category={patient_data['primary_symptom_category']}, "
            f"location={location.get('address') or f\"({location.get('latitude')}, {location.get('longitude')})\"}",
        )
        
        return request


# Singleton
alternate_care_mapper = AlternateCareMapper()
