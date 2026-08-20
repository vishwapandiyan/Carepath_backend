"""
Readmission Feature Mapper Service

Maps EHR data to the 25 features required by the readmission prediction model.

Model Features:
- 20 numerical features (age, comorbidities, labs, utilization, admission data, medications)
- 5 categorical features (insurance_type, admission_type, discharge_destination) - one-hot encoded

Author: CarePath AI Team
Date: 2026-08-20
"""

import logging
from typing import Dict, Any, Optional
import pandas as pd
from app.models.ehr import PatientEHR

logger = logging.getLogger(__name__)


class ReadmissionFeatureMapper:
    """
    Maps patient EHR data to features required by the readmission prediction model.
    Handles missing values and one-hot encoding for categorical variables.
    """
    
    # Expected 25 features for the model
    EXPECTED_FEATURES = [
        # Numerical features (20)
        'num__age',
        'num__comorbidity_index',
        'num__diabetes_flag',
        'num__heart_failure_flag',
        'num__copd_flag',
        'num__ckd_flag',
        'num__dementia_flag',
        'num__previous_admissions_12m',
        'num__previous_er_visits_12m',
        'num__prior_30_day_readmission_flag',
        'num__length_of_stay_days',
        'num__icu_stay_flag',
        'num__medication_count_at_discharge',
        'num__polypharmacy_flag',
        'num__high_risk_medication_flag',
        'num__hemoglobin',
        'num__creatinine',
        'num__glucose',
        'num__follow_up_within_7_days_flag',
        'num__total_charges_index_stay',
        # Categorical features (5) - one-hot encoded
        'cat__insurance_type_Medicare',
        'cat__insurance_type_Private',
        'cat__admission_type_emergency',
        'cat__discharge_destination_nursing_home',
        'cat__discharge_destination_rehab',
    ]
    
    def map_ehr_to_features(self, ehr: PatientEHR) -> pd.DataFrame:
        """
        Map EHR data to model features.
        
        Args:
            ehr: PatientEHR database model instance
            
        Returns:
            pd.DataFrame: Single row DataFrame with 25 features in correct order
        """
        try:
            # Extract numerical features
            features = {
                'num__age': ehr.age,
                'num__comorbidity_index': ehr.charlson_comorbidity_index,
                'num__diabetes_flag': ehr.diabetes_flag,
                'num__heart_failure_flag': ehr.heart_failure_flag,
                'num__copd_flag': ehr.copd_asthma_flag,  # Using combined COPD/Asthma flag
                'num__ckd_flag': ehr.ckd_flag,
                'num__dementia_flag': ehr.dementia_flag,
                'num__previous_admissions_12m': ehr.previous_admissions_12m,
                'num__previous_er_visits_12m': ehr.previous_er_visits_12m,
                'num__prior_30_day_readmission_flag': ehr.prior_30_day_readmission_flag,
                'num__length_of_stay_days': self._handle_missing(ehr.length_of_stay_days, default=0),
                'num__icu_stay_flag': ehr.icu_stay_flag,
                'num__medication_count_at_discharge': self._handle_missing(ehr.medication_count_at_discharge, default=0),
                'num__polypharmacy_flag': ehr.polypharmacy_flag,
                'num__high_risk_medication_flag': ehr.high_risk_medication_flag,
                'num__hemoglobin': ehr.hemoglobin,
                'num__creatinine': ehr.creatinine,
                'num__glucose': ehr.glucose,
                'num__follow_up_within_7_days_flag': ehr.follow_up_within_7_days_flag,
                'num__total_charges_index_stay': self._handle_missing(ehr.total_charges_index_stay, default=0.0),
            }
            
            # One-hot encode categorical variables
            categorical_features = self._encode_categorical_features(
                insurance_type=ehr.insurance_type,
                admission_type=ehr.admission_type,
                discharge_destination=ehr.discharge_destination
            )
            
            # Combine all features
            features.update(categorical_features)
            
            # Create DataFrame with features in the correct order
            df = pd.DataFrame([features], columns=self.EXPECTED_FEATURES)
            
            logger.info(f"Mapped EHR data for patient {ehr.patient_id} to {len(self.EXPECTED_FEATURES)} features")
            
            return df
            
        except Exception as e:
            logger.error(f"Error mapping EHR to features for patient {ehr.patient_id}: {str(e)}")
            raise
    
    def _handle_missing(self, value: Optional[Any], default: Any) -> Any:
        """Handle missing values by returning default."""
        return value if value is not None else default
    
    def _encode_categorical_features(
        self,
        insurance_type: Optional[str],
        admission_type: Optional[str],
        discharge_destination: Optional[str]
    ) -> Dict[str, int]:
        """
        One-hot encode categorical features.
        
        Model expects these specific dummy columns:
        - insurance_type: Medicare, Private
        - admission_type: emergency
        - discharge_destination: nursing_home, rehab
        
        Args:
            insurance_type: Insurance type (Medicare, Medicaid, Private, etc.)
            admission_type: Admission type (elective, emergency, urgent)
            discharge_destination: Discharge destination (home, rehab, nursing_home, other)
            
        Returns:
            Dict with one-hot encoded features
        """
        # Insurance type encoding
        insurance_medicare = 1 if insurance_type == "Medicare" else 0
        insurance_private = 1 if insurance_type == "Private" else 0
        
        # Admission type encoding
        admission_emergency = 1 if admission_type == "emergency" else 0
        
        # Discharge destination encoding
        discharge_nursing_home = 1 if discharge_destination == "nursing_home" else 0
        discharge_rehab = 1 if discharge_destination == "rehab" else 0
        
        return {
            'cat__insurance_type_Medicare': insurance_medicare,
            'cat__insurance_type_Private': insurance_private,
            'cat__admission_type_emergency': admission_emergency,
            'cat__discharge_destination_nursing_home': discharge_nursing_home,
            'cat__discharge_destination_rehab': discharge_rehab,
        }
    
    def validate_features(self, features_df: pd.DataFrame) -> bool:
        """
        Validate that all required features are present.
        
        Args:
            features_df: DataFrame with mapped features
            
        Returns:
            True if all features are present, False otherwise
        """
        missing_features = set(self.EXPECTED_FEATURES) - set(features_df.columns)
        
        if missing_features:
            logger.error(f"Missing features: {missing_features}")
            return False
        
        return True


# Singleton instance
readmission_feature_mapper = ReadmissionFeatureMapper()
