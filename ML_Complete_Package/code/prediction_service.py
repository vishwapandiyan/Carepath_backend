"""
Prediction service - handles all prediction logic
"""
import pandas as pd
import numpy as np
from typing import Dict, List
from uuid import uuid4
from datetime import datetime

from app.models.schemas import (
    PatientFeatures,
    ComprehensivePrediction,
    Layer1Prediction,
    Layer2RiskLevel,
    Layer3Explanation,
    Layer4TimeEstimate,
    Layer5Interventions,
    RiskFactor,
    Recommendation,
    RiskTier,
    Priority
)
from app.ml.model_loader import model_loader


class PredictionService:
    """Service for making predictions"""
    
    def __init__(self):
        self.model = model_loader.get_model()
    
    def predict(self, features: PatientFeatures) -> ComprehensivePrediction:
        """
        Make comprehensive 5-layer prediction
        """
        # Convert Pydantic model to dict
        features_dict = features.model_dump()
        
        # Map field names to match what model expects
        # Model uses lowercase hba1c, not hbA1c
        if 'hbA1c' in features_dict:
            features_dict['hba1c'] = features_dict.pop('hbA1c')
        
        # Ensure drg_code exists (model might not use it but we need it for consistency)
        if 'drg_code' not in features_dict or features_dict.get('drg_code') is None:
            features_dict['drg_code'] = '291'  # Default DRG code
        
        # Validate and convert all numeric fields to proper types, handling None values
        numeric_fields = [
            'age', 'bmi', 'comorbidity_index', 'previous_admissions_12m', 
            'previous_er_visits_12m', 'length_of_stay_days', 
            'medication_count_at_discharge', 'hemoglobin', 'creatinine', 
            'glucose', 'hba1c', 'wbc_count', 'total_bilirubin', 
            'total_charges_index_stay'
        ]
        
        for field in numeric_fields:
            if field in features_dict and features_dict[field] is not None:
                try:
                    features_dict[field] = float(features_dict[field])
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid numeric value for field '{field}': {features_dict[field]}")
        
        # Create DataFrame with EXACT column order from training data
        # This ensures the ColumnTransformer receives features in expected order
        column_order = [
            'age', 'sex', 'bmi', 'insurance_type', 'admission_type',
            'discharge_destination', 'comorbidity_index', 'diabetes_flag',
            'heart_failure_flag', 'copd_flag', 'ckd_flag', 'cancer_flag',
            'dementia_flag', 'previous_admissions_12m', 'previous_er_visits_12m',
            'prior_30_day_readmission_flag', 'length_of_stay_days', 'icu_stay_flag',
            'medication_count_at_discharge', 'polypharmacy_flag',
            'high_risk_medication_flag', 'hemoglobin', 'creatinine', 'glucose',
            'hba1c', 'wbc_count', 'total_bilirubin',
            'follow_up_within_7_days_flag', 'total_charges_index_stay', 'drg_code'
        ]
        
        df = pd.DataFrame([features_dict])[column_order]
        
        # Make prediction using ML model
        try:
            probability = float(self.model.predict_proba(df)[0][1])  # Probability of readmission
            will_readmit = probability > 0.5
        except Exception as e:
            # Log the actual column mismatch for debugging
            import traceback
            error_details = traceback.format_exc()
            print(f"Prediction error details:\n{error_details}")
            print(f"DataFrame columns: {list(df.columns)}")
            print(f"DataFrame dtypes: {df.dtypes.to_dict()}")
            print(f"DataFrame values:\n{df.to_dict()}")
            raise ValueError(f"Prediction failed: {str(e)}")
        
        # Build comprehensive prediction
        prediction = self._build_prediction(features_dict, probability, will_readmit)
        prediction.prediction_id = str(uuid4())
        prediction.timestamp = datetime.now()
        
        return prediction
    
    def _calculate_risk_score(self, features: Dict) -> float:
        """Calculate readmission risk score based on clinical rules"""
        risk_score = 0.0
        
        # Age risk (0-0.15)
        age = features.get('age', 65)
        if age >= 75:
            risk_score += 0.15
        elif age >= 65:
            risk_score += 0.10
        elif age >= 50:
            risk_score += 0.05
        
        # Comorbidity index (0-0.20)
        comorbidity = features.get('comorbidity_index', 0)
        risk_score += min(comorbidity * 0.04, 0.20)
        
        # Previous admissions (0-0.20)
        prev_admits = features.get('previous_admissions_12m', 0)
        if prev_admits >= 3:
            risk_score += 0.20
        elif prev_admits >= 2:
            risk_score += 0.15
        elif prev_admits >= 1:
            risk_score += 0.10
        
        # Emergency visits (0-0.15)
        er_visits = features.get('previous_er_visits_12m', 0)
        if er_visits >= 3:
            risk_score += 0.15
        elif er_visits >= 2:
            risk_score += 0.10
        elif er_visits >= 1:
            risk_score += 0.05
        
        # Length of stay (0-0.10)
        los = features.get('length_of_stay_days', 0)
        if los >= 7:
            risk_score += 0.10
        elif los >= 4:
            risk_score += 0.05
        
        # Polypharmacy (0-0.10)
        if features.get('polypharmacy_flag', 0) == 1:
            risk_score += 0.10
        
        # High-risk medications (0-0.10)
        if features.get('high_risk_medication_flag', 0) == 1:
            risk_score += 0.10
        
        # Chronic conditions (0-0.15)
        chronic_score = 0
        if features.get('diabetes_flag', 0) == 1:
            chronic_score += 0.03
        if features.get('heart_failure_flag', 0) == 1:
            chronic_score += 0.05
        if features.get('copd_flag', 0) == 1:
            chronic_score += 0.04
        if features.get('ckd_flag', 0) == 1:
            chronic_score += 0.03
        risk_score += min(chronic_score, 0.15)
        
        # No follow-up scheduled (0-0.15)
        if features.get('follow_up_within_7_days_flag', 0) == 0:
            risk_score += 0.15
        
        # Prior 30-day readmission (0-0.20)
        if features.get('prior_30_day_readmission_flag', 0) == 1:
            risk_score += 0.20
        
        # ICU stay (0-0.05)
        if features.get('icu_stay_flag', 0) == 1:
            risk_score += 0.05
        
        # Normalize to 0-1 range
        return min(risk_score, 1.0)
    
    def batch_predict(self, features_list: List[PatientFeatures]) -> List[ComprehensivePrediction]:
        """
        Make predictions for multiple patients
        """
        predictions = []
        for features in features_list:
            try:
                pred = self.predict(features)
                predictions.append(pred)
            except Exception as e:
                print(f"Prediction failed for patient: {str(e)}")
                continue
        
        return predictions
    
    def _build_prediction(self, features_dict: Dict, probability: float, will_readmit: bool) -> ComprehensivePrediction:
        """Build comprehensive prediction from basic ML model output"""
        
        # Determine risk tier
        if probability >= 0.7:
            risk_tier = RiskTier.HIGH
            urgency = "Immediate"
        elif probability >= 0.5:
            risk_tier = RiskTier.MODERATE
            urgency = "Within 7 days"
        else:
            risk_tier = RiskTier.LOW
            urgency = "Standard monitoring"
        
        # Layer 1: Basic prediction
        layer1 = Layer1Prediction(
            will_readmit="Yes" if will_readmit else "No",
            probability=probability,
            confidence="high" if probability > 0.7 or probability < 0.3 else "moderate"
        )
        
        # Layer 2: Risk level
        layer2 = Layer2RiskLevel(
            risk_tier=risk_tier,
            urgency=urgency,
            probability_range=f"{int(probability*100-5)}-{int(probability*100+5)}%"
        )
        
        # Layer 3: Simplified explanation based on common features
        risk_factors = []
        if features_dict.get('num_emergency', 0) > 2:
            risk_factors.append(RiskFactor(
                feature="Emergency Visits",
                contribution=0.15,
                impact="High number of emergency visits indicates instability"
            ))
        if features_dict.get('num_medications', 0) > 10:
            risk_factors.append(RiskFactor(
                feature="Medications",
                contribution=0.12,
                impact="High medication count suggests complex health issues"
            ))
        if features_dict.get('num_diagnoses', 0) > 5:
            risk_factors.append(RiskFactor(
                feature="Diagnoses",
                contribution=0.10,
                impact="Multiple diagnoses increase readmission risk"
            ))
        
        # Add default if no risk factors found
        if not risk_factors:
            risk_factors.append(RiskFactor(
                feature="Clinical History",
                contribution=0.20,
                impact="Based on overall clinical profile"
            ))
        
        layer3 = Layer3Explanation(
            risk_factors=risk_factors,
            protective_factors=[],
            risk_profile={
                "overall_risk": f"{probability*100:.1f}%",
                "risk_category": risk_tier.value,
                "summary": f"Patient with {risk_tier.value.lower()} readmission probability"
            }
        )
        
        # Layer 4: Time estimates
        layer4 = Layer4TimeEstimate(
            day7_risk=min(probability * 1.2, 1.0),
            day30_risk=probability,
            day90_risk=max(probability * 0.8, 0.0),
            most_likely_window="7-30 days" if probability > 0.5 else "30-90 days",
            note="Estimates based on historical patterns"
        )
        
        # Layer 5: Interventions
        recommendations = []
        if probability >= 0.7:
            recommendations.extend([
                Recommendation(
                    priority=Priority.HIGH,
                    intervention="Schedule follow-up within 48 hours",
                    rationale="High readmission risk requires immediate attention"
                ),
                Recommendation(
                    priority=Priority.HIGH,
                    intervention="Medication reconciliation",
                    rationale="Ensure medication adherence and prevent complications"
                ),
            ])
        elif probability >= 0.5:
            recommendations.append(
                Recommendation(
                    priority=Priority.MODERATE,
                    intervention="Schedule follow-up within 7 days",
                    rationale="Moderate risk requires timely intervention"
                )
            )
        else:
            recommendations.append(
                Recommendation(
                    priority=Priority.LOW,
                    intervention="Standard discharge protocol",
                    rationale="Low risk allows standard care pathway"
                )
            )
        
        layer5 = Layer5Interventions(recommendations=recommendations)
        
        return ComprehensivePrediction(
            layer1_prediction=layer1,
            layer2_risk_level=layer2,
            layer3_why=layer3,
            layer4_when=layer4,
            layer5_intervention=layer5
        )


# Global instance
prediction_service = PredictionService()
