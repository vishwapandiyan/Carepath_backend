"""
Readmission Feature Mapper
Maps data from PatientEHR -> 30 Features required by best_readmission_model.pkl pipeline.
"""

from typing import Dict, Any, List
import logging
import pandas as pd
from app.models.ehr import PatientEHR

logger = logging.getLogger(__name__)


class ReadmissionFeatureMapper:
    """Maps PatientEHR model instances to the 30 features expected by best_readmission_model.pkl"""

    # Exact 30 feature names expected by the trained pipeline
    EXPECTED_FEATURES: List[str] = [
        'age',
        'sex',
        'bmi',
        'insurance_type',
        'admission_type',
        'discharge_destination',
        'comorbidity_index',
        'diabetes_flag',
        'heart_failure_flag',
        'copd_flag',
        'ckd_flag',
        'cancer_flag',
        'dementia_flag',
        'previous_admissions_12m',
        'previous_er_visits_12m',
        'prior_30_day_readmission_flag',
        'length_of_stay_days',
        'icu_stay_flag',
        'medication_count_at_discharge',
        'polypharmacy_flag',
        'high_risk_medication_flag',
        'hemoglobin',
        'creatinine',
        'glucose',
        'hba1c',
        'wbc_count',
        'total_bilirubin',
        'follow_up_within_7_days_flag',
        'total_charges_index_stay',
        'drg_code',
    ]
    
    def map_ehr_to_features(self, ehr: PatientEHR) -> pd.DataFrame:
        """
        Map EHR data to model features.
        
        Args:
            ehr: PatientEHR database model instance
            
        Returns:
            pd.DataFrame: Single row DataFrame with 30 features in correct order
        """
        try:
            # Map gender string to numeric (1 for male, 0 for female/other)
            gender_lower = str(ehr.gender).lower() if ehr.gender else ""
            sex_numeric = 1 if gender_lower in ["male", "m", "1"] else 0

            features = {
                'age': ehr.age if ehr.age is not None else 50,
                'sex': sex_numeric,
                'bmi': ehr.bmi if ehr.bmi is not None else 25.0,
                'insurance_type': ehr.insurance_type if ehr.insurance_type else "Medicare",
                'admission_type': ehr.admission_type if ehr.admission_type else "emergency",
                'discharge_destination': ehr.discharge_destination if ehr.discharge_destination else "home",
                'comorbidity_index': ehr.charlson_comorbidity_index if ehr.charlson_comorbidity_index is not None else 0,
                'diabetes_flag': ehr.diabetes_flag if ehr.diabetes_flag is not None else 0,
                'heart_failure_flag': ehr.heart_failure_flag if ehr.heart_failure_flag is not None else 0,
                'copd_flag': ehr.copd_asthma_flag if ehr.copd_asthma_flag is not None else 0,
                'ckd_flag': ehr.ckd_flag if ehr.ckd_flag is not None else 0,
                'cancer_flag': ehr.cancer_flag if ehr.cancer_flag is not None else 0,
                'dementia_flag': ehr.dementia_flag if ehr.dementia_flag is not None else 0,
                'previous_admissions_12m': ehr.previous_admissions_12m if ehr.previous_admissions_12m is not None else 0,
                'previous_er_visits_12m': ehr.previous_er_visits_12m if ehr.previous_er_visits_12m is not None else 0,
                'prior_30_day_readmission_flag': ehr.prior_30_day_readmission_flag if ehr.prior_30_day_readmission_flag is not None else 0,
                'length_of_stay_days': ehr.length_of_stay_days if ehr.length_of_stay_days is not None else 3,
                'icu_stay_flag': ehr.icu_stay_flag if ehr.icu_stay_flag is not None else 0,
                'medication_count_at_discharge': ehr.medication_count_at_discharge if ehr.medication_count_at_discharge is not None else 5,
                'polypharmacy_flag': ehr.polypharmacy_flag if ehr.polypharmacy_flag is not None else 0,
                'high_risk_medication_flag': ehr.high_risk_medication_flag if ehr.high_risk_medication_flag is not None else 0,
                'hemoglobin': ehr.hemoglobin if ehr.hemoglobin is not None else 13.5,
                'creatinine': ehr.creatinine if ehr.creatinine is not None else 1.0,
                'glucose': ehr.glucose if ehr.glucose is not None else 110,
                'hba1c': ehr.hba1c if ehr.hba1c is not None else 6.5,
                'wbc_count': ehr.wbc_count if ehr.wbc_count is not None else 7.5,
                'total_bilirubin': ehr.total_bilirubin if ehr.total_bilirubin is not None else 0.8,
                'follow_up_within_7_days_flag': ehr.follow_up_within_7_days_flag if ehr.follow_up_within_7_days_flag is not None else 0,
                'total_charges_index_stay': ehr.total_charges_index_stay if ehr.total_charges_index_stay is not None else 15000.0,
                'drg_code': 0,
            }
            
            df = pd.DataFrame([features], columns=self.EXPECTED_FEATURES)
            logger.info(f"Mapped EHR data for patient {ehr.patient_id} to 30 features")
            return df
            
        except Exception as e:
            logger.error(f"Error mapping EHR to features for patient {ehr.patient_id}: {str(e)}")
            raise

    def validate_features(self, features_df: pd.DataFrame) -> bool:
        """Validate that all required features are present."""
        missing_features = set(self.EXPECTED_FEATURES) - set(features_df.columns)
        if missing_features:
            logger.error(f"Missing features: {missing_features}")
            return False
        return True


# Singleton instance
readmission_feature_mapper = ReadmissionFeatureMapper()
