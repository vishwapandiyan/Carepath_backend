"""
ED Avoidable Feature Mapper
Maps data from Intake + Safety Screening + EHR → ML Model Features (95 features)

This service transforms the data collected from:
1. Chatbot intake (8 symptom questions)
2. Safety screening (12 red flag questions)
3. EHR database (patient medical history)

Into the 95 features required by the ED Avoidable ML model.
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EDFeatureMapper:
    """Maps collected data to ED Avoidable model features"""
    
    @staticmethod
    def map_primary_symptom_category(chief_complaint: str) -> str:
        """
        Map chief complaint to one of the standard symptom categories.
        
        Categories: abdominal_pain, back_pain, chest_pain, headache, 
                   shortness_of_breath, fever, injury, other
        
        Args:
            chief_complaint: Patient's main symptom description
            
        Returns:
            Symptom category string
        """
        if not chief_complaint:
            return 'other'
            
        chief_complaint_lower = chief_complaint.lower()
        
        # Chest/Cardiac
        if any(word in chief_complaint_lower for word in ['chest', 'heart', 'cardiac']):
            return 'chest_pain'
        
        # Respiratory
        elif any(word in chief_complaint_lower for word in ['breath', 'breathing', 'asthma', 'wheez', 'cough', 'respiratory']):
            return 'shortness_of_breath'
        
        # Abdominal
        elif any(word in chief_complaint_lower for word in ['stomach', 'abdomen', 'belly', 'nausea', 'vomit', 'diarrhea']):
            return 'abdominal_pain'
        
        # Back
        elif any(word in chief_complaint_lower for word in ['back', 'spine']):
            return 'back_pain'
        
        # Head
        elif any(word in chief_complaint_lower for word in ['head', 'migraine', 'headache']):
            return 'headache'
        
        # Fever/Infection
        elif any(word in chief_complaint_lower for word in ['fever', 'temperature', 'hot', 'chills', 'infection']):
            return 'fever'
        
        # Injury/Trauma
        elif any(word in chief_complaint_lower for word in ['injury', 'fall', 'accident', 'trauma', 'fracture', 'broken', 'wound', 'cut']):
            return 'injury'
        
        else:
            return 'other'
    
    @staticmethod
    def map_pain_onset(symptom_onset: str) -> str:
        """
        Map symptom onset description to: sudden, gradual, or chronic
        
        Args:
            symptom_onset: When symptoms started (e.g., "2 hours ago", "gradually over 3 days")
            
        Returns:
            One of: sudden, gradual, chronic
        """
        if not symptom_onset:
            return 'gradual'
            
        onset_lower = symptom_onset.lower()
        
        # Sudden onset (immediate, rapid)
        if any(word in onset_lower for word in ['sudden', 'suddenly', 'immediate', 'instantly', 'all at once', 'right now', 'just now']):
            return 'sudden'
        
        # Chronic (long duration)
        elif any(word in onset_lower for word in ['weeks', 'months', 'years', 'chronic', 'long time', 'always']):
            return 'chronic'
        
        # Gradual (default for "days", "slowly", etc.)
        else:
            return 'gradual'
    
    @staticmethod
    def parse_pain_radiating(pain_radiating: str) -> int:
        """
        Parse pain radiating response to binary flag.
        
        Args:
            pain_radiating: Patient's response about pain spreading
            
        Returns:
            1 if pain radiates, 0 if not
        """
        if not pain_radiating:
            return 0
            
        radiating_lower = pain_radiating.lower()
        
        # Check for affirmative responses
        if any(word in radiating_lower for word in ['yes', 'spread', 'radiate', 'goes to', 'travels']):
            return 1
        
        # Check for negative responses
        elif any(word in radiating_lower for word in ['no', 'not', "doesn't", 'stay', 'local']):
            return 0
        
        # Default to not radiating
        return 0
    
    @staticmethod
    def build_ml_features(
        intake_data: Dict,
        safety_flags: Dict,
        ehr_data: Optional[object] = None
    ) -> Dict:
        """
        Build complete feature dictionary for ML model (95 features).
        
        This is the main function that combines all data sources and creates
        the exact feature set expected by the trained ED Avoidable model.
        
        Args:
            intake_data: Dict with 8 fields from chatbot intake
                - chief_complaint
                - symptom_onset
                - pain_scale
                - location
                - pain_duration
                - pain_character
                - pain_radiating
                - symptom_trend
            
            safety_flags: Dict with 12 red flag fields from safety screening
                - chest_pain
                - difficulty_breathing
                - altered_consciousness
                - severe_bleeding
                - stroke_symptoms
                - suicidal_ideation
                - anaphylaxis
                - high_fever
                - unable_to_walk
                - severe_abdominal_pain
                - vomiting_blood
                - severe_dehydration
            
            ehr_data: Optional PatientEHR object from database
        
        Returns:
            Dict with 95 features ready for ML model prediction
        """
        
        features = {}
        
        # === SYMPTOM DATA (9 fields) ===
        
        # Derive primary symptom category from chief complaint
        features['primary_symptom_category'] = EDFeatureMapper.map_primary_symptom_category(
            intake_data.get('chief_complaint', 'other')
        )
        
        # Pain level (0-10)
        features['pain_level_self_reported'] = intake_data.get('pain_scale', 0) or 0
        
        # Onset classification
        features['pain_onset'] = EDFeatureMapper.map_pain_onset(
            intake_data.get('symptom_onset', 'gradual')
        )
        
        # Duration (keep as string for LabelEncoder)
        features['pain_duration'] = intake_data.get('pain_duration', 'unknown') or 'unknown'
        
        # Location
        features['pain_location'] = intake_data.get('location', 'unknown') or 'unknown'
        
        # Character (quality of pain)
        features['pain_character'] = intake_data.get('pain_character', 'unknown') or 'unknown'
        
        # Radiating (binary)
        features['pain_radiating'] = EDFeatureMapper.parse_pain_radiating(
            intake_data.get('pain_radiating', 'no')
        )
        
        # Symptom trend
        features['symptom_trend'] = intake_data.get('symptom_trend', 'stable') or 'stable'
        
        # === RED FLAGS (10 fields - mapped from 12 safety screening questions) ===
        
        # Direct mappings
        features['flag_shortness_of_breath'] = 1 if safety_flags.get('difficulty_breathing') else 0
        features['flag_chest_pain_sweating_nausea'] = 1 if safety_flags.get('chest_pain') else 0
        features['flag_uncontrolled_bleeding'] = 1 if safety_flags.get('severe_bleeding') else 0
        features['flag_severe_allergic_reaction'] = 1 if safety_flags.get('anaphylaxis') else 0
        features['flag_stroke_signs'] = 1 if safety_flags.get('stroke_symptoms') else 0
        features['flag_high_fever_stiff_neck_rash'] = 1 if safety_flags.get('high_fever') else 0
        features['flag_vomiting_blood_or_blood_in_stool'] = 1 if safety_flags.get('vomiting_blood') else 0
        features['flag_severe_dehydration'] = 1 if safety_flags.get('severe_dehydration') else 0
        
        # Split altered consciousness into two flags
        altered = safety_flags.get('altered_consciousness', False)
        features['flag_loss_of_consciousness'] = 1 if altered else 0
        features['flag_confusion_altered_mental_state'] = 1 if altered else 0
        
        # === EHR DATA (if available, otherwise use defaults) ===
        
        if ehr_data:
            # Patient has existing EHR record - use real data
            
            # Vital Signs (7 fields)
            features['systolic_bp'] = getattr(ehr_data, 'systolic_bp', None) or 120
            features['diastolic_bp'] = getattr(ehr_data, 'diastolic_bp', None) or 80
            features['heart_rate'] = getattr(ehr_data, 'heart_rate', None) or 70
            features['respiratory_rate'] = getattr(ehr_data, 'respiratory_rate', None) or 16
            features['temperature'] = getattr(ehr_data, 'temperature', None) or 98.6
            features['spo2'] = getattr(ehr_data, 'spo2', None) or 98
            # Use clinical pain score if available, otherwise use self-reported
            features['pain_score_clinical'] = getattr(ehr_data, 'pain_score_clinical', None) or features['pain_level_self_reported']
            
            # Lab Values (13 fields) - use wbc_count from EHR but map to 'wbc' for model
            features['wbc'] = getattr(ehr_data, 'wbc_count', None) or 7.0
            features['hemoglobin'] = getattr(ehr_data, 'hemoglobin', None) or 14.0
            features['platelet_count'] = getattr(ehr_data, 'platelet_count', None) or 250000
            features['sodium'] = getattr(ehr_data, 'sodium', None) or 140.0
            features['potassium'] = getattr(ehr_data, 'potassium', None) or 4.0
            features['creatinine'] = getattr(ehr_data, 'creatinine', None) or 1.0
            features['glucose'] = getattr(ehr_data, 'glucose', None) or 100
            features['troponin'] = getattr(ehr_data, 'troponin', None) or 0.01
            features['bnp'] = getattr(ehr_data, 'bnp', None) or 50
            features['lactate'] = getattr(ehr_data, 'lactate', None) or 1.0
            features['inr'] = getattr(ehr_data, 'inr', None) or 1.0
            
            # Chronic Conditions (9 fields)
            features['diabetes_flag'] = getattr(ehr_data, 'diabetes_flag', None) or 0
            features['hypertension_flag'] = getattr(ehr_data, 'hypertension_flag', None) or 0
            features['cardiac_history_flag'] = getattr(ehr_data, 'cardiac_history_flag', None) or 0
            features['copd_asthma_flag'] = getattr(ehr_data, 'copd_asthma_flag', None) or 0
            features['ckd_flag'] = getattr(ehr_data, 'ckd_flag', None) or 0
            features['cancer_flag'] = getattr(ehr_data, 'cancer_flag', None) or 0
            features['immunocompromised_flag'] = getattr(ehr_data, 'immunocompromised_flag', None) or 0
            
            # Comorbidity Scores (2 fields)
            # Calculate chronic condition count
            features['chronic_condition_count'] = sum([
                features['diabetes_flag'],
                features['hypertension_flag'],
                features['cardiac_history_flag'],
                features['copd_asthma_flag'],
                features['ckd_flag'],
                features['cancer_flag']
            ])
            features['charlson_comorbidity_index'] = getattr(ehr_data, 'charlson_comorbidity_index', None) or 0
            
            # Medications (4 fields)
            features['active_medication_count'] = getattr(ehr_data, 'active_medication_count', None) or 0
            features['on_anticoagulants_flag'] = getattr(ehr_data, 'on_anticoagulants_flag', None) or 0
            features['on_insulin_flag'] = getattr(ehr_data, 'on_insulin_flag', None) or 0
            
            # Utilization History (5 fields)
            features['days_since_last_ed_visit'] = getattr(ehr_data, 'days_since_last_ed_visit', None) or 365
            features['ed_visits_past_year'] = getattr(ehr_data, 'previous_er_visits_12m', None) or 0
            features['admissions_past_year'] = getattr(ehr_data, 'previous_admissions_12m', None) or 0
            features['has_pcp_flag'] = 1  # If they have EHR, assume they have a PCP
            
            # Demographics (3 fields)
            features['age'] = getattr(ehr_data, 'age', None) or 30
            features['gender'] = getattr(ehr_data, 'gender', None) or 'unknown'
            
            logger.info(f"Built features with EHR data for patient (age={features['age']})")
            
        else:
            # No EHR record - use population defaults (healthy adult)
            logger.warning("No EHR data available - using population defaults")
            
            # Vital Signs (normal ranges)
            features['systolic_bp'] = 120
            features['diastolic_bp'] = 80
            features['heart_rate'] = 70
            features['respiratory_rate'] = 16
            features['temperature'] = 98.6
            features['spo2'] = 98
            features['pain_score_clinical'] = features['pain_level_self_reported']
            
            # Lab Values (normal ranges)
            features['wbc'] = 7.0
            features['hemoglobin'] = 14.0
            features['platelet_count'] = 250000
            features['sodium'] = 140.0
            features['potassium'] = 4.0
            features['creatinine'] = 1.0
            features['glucose'] = 100
            features['troponin'] = 0.01
            features['bnp'] = 50
            features['lactate'] = 1.0
            features['inr'] = 1.0
            
            # Chronic Conditions (assume healthy)
            features['diabetes_flag'] = 0
            features['hypertension_flag'] = 0
            features['cardiac_history_flag'] = 0
            features['copd_asthma_flag'] = 0
            features['ckd_flag'] = 0
            features['cancer_flag'] = 0
            features['immunocompromised_flag'] = 0
            
            # Comorbidity
            features['chronic_condition_count'] = 0
            features['charlson_comorbidity_index'] = 0
            
            # Medications
            features['active_medication_count'] = 0
            features['on_anticoagulants_flag'] = 0
            features['on_insulin_flag'] = 0
            
            # Utilization History (no prior visits)
            features['days_since_last_ed_visit'] = 365
            features['ed_visits_past_year'] = 0
            features['admissions_past_year'] = 0
            features['has_pcp_flag'] = 0
            
            # Demographics (default young adult)
            features['age'] = 30
            features['gender'] = 'unknown'
        
        logger.info(f"Built {len(features)} features for ED Avoidable prediction")
        
        return features


# Global mapper instance
ed_feature_mapper = EDFeatureMapper()
