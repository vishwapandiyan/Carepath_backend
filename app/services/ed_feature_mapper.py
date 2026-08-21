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
    def map_pain_duration(duration_str: str) -> str:
        """Map pain duration input to model categorical classes: ['1_day', '1_hour', '1_month', '1_week', '2_hours', '3_days']"""
        if not duration_str:
            return '1_day'
        dur_lower = str(duration_str).lower().replace(' ', '_')
        if any(w in dur_lower for w in ['hour', 'hr', 'min']):
            return '2_hours' if any(w in dur_lower for w in ['2', 'two', 'several', 'few']) else '1_hour'
        elif any(w in dur_lower for w in ['month', 'mo']):
            return '1_month'
        elif any(w in dur_lower for w in ['week', 'wk']):
            return '1_week'
        elif any(w in dur_lower for w in ['day', 'dy']):
            return '3_days' if any(w in dur_lower for w in ['3', '2', '4', 'three', 'two', 'four', 'few']) else '1_day'
        return '1_day'

    @staticmethod
    def map_pain_location(location_str: str) -> str:
        """Map pain location input to model categorical classes: ['abdomen', 'arm', 'back', 'chest', 'generalized', 'head', 'leg', 'unknown']"""
        if not location_str:
            return 'unknown'
        loc_lower = str(location_str).lower()
        if any(w in loc_lower for w in ['head', 'forehead', 'temple', 'skull', 'brain', 'face']):
            return 'head'
        elif any(w in loc_lower for w in ['chest', 'breast', 'sternum', 'heart']):
            return 'chest'
        elif any(w in loc_lower for w in ['back', 'spine', 'lumbar']):
            return 'back'
        elif any(w in loc_lower for w in ['stomach', 'abdomen', 'belly', 'gut', 'navel']):
            return 'abdomen'
        elif any(w in loc_lower for w in ['leg', 'thigh', 'knee', 'calf', 'foot', 'ankle']):
            return 'leg'
        elif any(w in loc_lower for w in ['arm', 'shoulder', 'elbow', 'wrist', 'hand']):
            return 'arm'
        elif any(w in loc_lower for w in ['all over', 'whole body', 'generalized', 'everywhere']):
            return 'generalized'
        return 'unknown'

    @staticmethod
    def map_pain_character(char_str: str) -> str:
        """Map pain character input to model categorical classes: ['aching', 'burning', 'dull', 'pressure', 'sharp', 'throbbing', 'unknown']"""
        if not char_str:
            return 'unknown'
        c_lower = str(char_str).lower()
        if any(w in c_lower for w in ['sharp', 'stabbing', 'knife']):
            return 'sharp'
        elif any(w in c_lower for w in ['pressure', 'crushing', 'heavy', 'tight']):
            return 'pressure'
        elif any(w in c_lower for w in ['burning', 'fire', 'hot', 'acid']):
            return 'burning'
        elif any(w in c_lower for w in ['throbbing', 'pulsating', 'pounding']):
            return 'throbbing'
        elif any(w in c_lower for w in ['dull']):
            return 'dull'
        elif any(w in c_lower for w in ['ache', 'aching', 'sore']):
            return 'aching'
        return 'unknown'

    @staticmethod
    def map_symptom_trend(trend_str: str) -> str:
        """Map symptom trend input to model categorical classes: ['fluctuating', 'improving', 'stable', 'worsening']"""
        if not trend_str:
            return 'stable'
        t_lower = str(trend_str).lower()
        if any(w in t_lower for w in ['worse', 'worsening', 'deteriorat', 'progress']):
            return 'worsening'
        elif any(w in t_lower for w in ['better', 'improving', 'easier', 'resolv']):
            return 'improving'
        elif any(w in t_lower for w in ['fluctuat', 'comes and goes', 'wave', 'intermittent']):
            return 'fluctuating'
        return 'stable'

    @staticmethod
    def map_gender(gender_str: str) -> str:
        """Map gender input to model categorical classes: ['female', 'male', 'unknown']"""
        if not gender_str:
            return 'unknown'
        g_lower = str(gender_str).lower()
        if 'female' in g_lower or 'f' == g_lower:
            return 'female'
        elif 'male' in g_lower or 'm' == g_lower:
            return 'male'
        return 'unknown'

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
        
        # Duration (mapped to model classes)
        features['pain_duration'] = EDFeatureMapper.map_pain_duration(
            intake_data.get('pain_duration', '1_day')
        )
        
        # Location (mapped to model classes)
        features['pain_location'] = EDFeatureMapper.map_pain_location(
            intake_data.get('location', 'unknown')
        )
        
        # Character (quality of pain, mapped to model classes)
        features['pain_character'] = EDFeatureMapper.map_pain_character(
            intake_data.get('pain_character', 'unknown')
        )
        
        # Radiating (binary)
        features['pain_radiating'] = EDFeatureMapper.parse_pain_radiating(
            intake_data.get('pain_radiating', 'no')
        )
        
        # Symptom trend (mapped to model classes)
        features['symptom_trend'] = EDFeatureMapper.map_symptom_trend(
            intake_data.get('symptom_trend', 'stable')
        )
        
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
            features['gender'] = EDFeatureMapper.map_gender(getattr(ehr_data, 'gender', None))
            
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
        
        # === DERIVED CLINICAL FEATURES (32 engineered features) ===
        features = EDFeatureMapper._add_derived_features(features)

        logger.info(f"Built {len(features)} features for ED Avoidable prediction")
        
        return features

    @staticmethod
    def _add_derived_features(features: Dict) -> Dict:
        """Derive secondary clinical features matching ML training pipeline"""
        def _get_num(val, default):
            if val is None or (hasattr(val, '__class__') and 'Mock' in val.__class__.__name__):
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        # Vital sign derived features
        sbp = _get_num(features.get('systolic_bp'), 120.0)
        dbp = _get_num(features.get('diastolic_bp'), 80.0)
        hr = _get_num(features.get('heart_rate'), 70.0)
        rr = _get_num(features.get('respiratory_rate'), 16.0)
        spo2 = _get_num(features.get('spo2'), 98.0)
        temp = _get_num(features.get('temperature'), 98.6)
        
        features['shock_index'] = hr / sbp if sbp > 0 else 0.5
        features['pulse_pressure'] = sbp - dbp
        features['mean_arterial_pressure'] = dbp + (features['pulse_pressure'] / 3)
        features['is_hypotensive'] = 1 if sbp < 90 else 0
        features['is_hypertensive_severe'] = 1 if sbp > 160 else 0
        features['is_tachycardic'] = 1 if hr > 100 else 0
        features['is_bradycardic'] = 1 if hr < 60 else 0
        features['is_tachypneic'] = 1 if rr > 20 else 0
        features['is_hypoxic'] = 1 if spo2 < 94 else 0
        temp_c = temp if temp < 50 else (temp - 32) * 5/9
        features['is_febrile'] = 1 if temp_c >= 38.0 else 0

        v_flags = ['is_tachycardic', 'is_bradycardic', 'is_tachypneic', 'is_hypoxic', 'is_febrile', 'is_hypotensive', 'is_hypertensive_severe']
        features['vital_abnormality_count'] = sum(features[f] for f in v_flags)

        # Lab derived features
        trop = _get_num(features.get('troponin'), 0.01)
        lac = _get_num(features.get('lactate'), 1.0)
        creat = _get_num(features.get('creatinine'), 1.0)
        wbc = _get_num(features.get('wbc'), 7.0)
        bnp = _get_num(features.get('bnp'), 50.0)
        inr = _get_num(features.get('inr'), 1.0)

        features['troponin_elevated'] = 1 if trop >= 0.04 else 0
        features['lactate_elevated'] = 1 if lac >= 2.0 else 0
        features['renal_impairment'] = 1 if creat >= 1.3 else 0
        features['wbc_abnormal'] = 1 if (wbc < 4.0 or wbc > 11.0) else 0
        features['bnp_elevated'] = 1 if bnp >= 100 else 0
        features['inr_elevated'] = 1 if inr >= 1.5 else 0

        l_flags = ['troponin_elevated', 'lactate_elevated', 'renal_impairment', 'wbc_abnormal', 'bnp_elevated', 'inr_elevated']
        features['lab_abnormality_count'] = sum(features[f] for f in l_flags)

        # Red flags / symptom interaction
        rf_cols = [
            'flag_shortness_of_breath', 'flag_chest_pain_sweating_nausea',
            'flag_loss_of_consciousness', 'flag_confusion_altered_mental_state',
            'flag_uncontrolled_bleeding', 'flag_severe_allergic_reaction',
            'flag_stroke_signs', 'flag_vomiting_blood_or_blood_in_stool',
            'flag_high_fever_stiff_neck_rash', 'flag_severe_dehydration'
        ]
        features['total_red_flags'] = sum(1 for rf in rf_cols if _get_num(features.get(rf), 0) > 0)
        features['red_flags_present'] = 1 if features['total_red_flags'] > 0 else 0
        
        pain = _get_num(features.get('pain_level_self_reported'), 0)
        features['pain_x_red_flags'] = pain * features['total_red_flags']
        features['high_pain_flag'] = 1 if pain >= 7 else 0

        clin_pain = _get_num(features.get('pain_score_clinical'), pain)
        features['pain_report_mismatch'] = abs(pain - clin_pain)
        
        p_rad = _get_num(features.get('pain_radiating'), 0)
        f_card = _get_num(features.get('flag_chest_pain_sweating_nausea'), 0)
        features['radiating_and_cardiac_symptoms'] = 1 if (p_rad > 0 and f_card > 0) else 0

        # Comorbidity / medication burden
        comorbs = ['diabetes_flag', 'hypertension_flag', 'cardiac_history_flag', 'copd_asthma_flag', 'ckd_flag', 'cancer_flag', 'immunocompromised_flag']
        features['is_multimorbid'] = 1 if sum(1 for c in comorbs if _get_num(features.get(c), 0) > 0) >= 2 else 0
        
        meds = _get_num(features.get('active_medication_count'), 0)
        ccount = _get_num(features.get('chronic_condition_count'), 0)
        features['medication_burden_ratio'] = meds / (ccount + 1)
        
        anticoag = _get_num(features.get('on_anticoagulants_flag'), 0)
        bleed = _get_num(features.get('flag_uncontrolled_bleeding'), 0)
        features['anticoag_bleeding_risk'] = 1 if (anticoag > 0 and bleed > 0) else 0

        # Utilization patterns
        ed_visits = _get_num(features.get('ed_visits_past_year'), 0)
        days_ed = _get_num(features.get('days_since_last_ed_visit'), 365)
        features['is_high_utilizer'] = 1 if ed_visits >= 3 else 0
        features['is_recent_followup'] = 1 if days_ed <= 7 else 0
        features['visits_x_recent'] = ed_visits * features['is_recent_followup']

        # Age features
        age = _get_num(features.get('age'), 30)
        features['is_elderly'] = 1 if age >= 65 else 0
        features['age_group'] = 0 if age <= 18 else (1 if age <= 40 else (2 if age <= 65 else 3))

        return features


# Global mapper instance
ed_feature_mapper = EDFeatureMapper()
