"""
Readmission Prediction Service

Loads the trained readmission model and makes predictions on patient EHR data.

Model: Logistic Regression
Purpose: Predict 30-day hospital readmission risk
Features: 25 features (20 numerical + 5 categorical one-hot encoded)
Performance: 81.9% accuracy, 0.806 AUC-ROC

Author: CarePath AI Team
Date: 2026-08-20
"""

import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

from app.models.ehr import PatientEHR
from app.services.readmission_feature_mapper import readmission_feature_mapper

logger = logging.getLogger(__name__)


class ReadmissionPredictionService:
    """
    Service for making readmission predictions using the trained ML model.
    """
    
    MODEL_PATH = Path(__file__).parent.parent / "ml_models" / "best_readmission_model.pkl"
    MODEL_VERSION = "2.0"
    MODEL_TYPE = "readmission"
    
    def __init__(self):
        """Initialize the service and load the model."""
        self.model = None
        self.model_loaded = False
        self.load_model()
    
    def load_model(self) -> bool:
        """
        Load the readmission prediction model from pickle file.
        
        Returns:
            bool: True if model loaded successfully, False otherwise
        """
        try:
            if not self.MODEL_PATH.exists():
                logger.error(f"Model file not found at {self.MODEL_PATH}")
                return False
            
            with open(self.MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)
            
            self.model_loaded = True
            logger.info(f"✓ Readmission model loaded successfully from {self.MODEL_PATH}")
            logger.info(f"  Model version: {self.MODEL_VERSION}")
            logger.info(f"  Model type: Logistic Regression")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to load readmission model: {str(e)}")
            self.model_loaded = False
            return False
    
    def predict(self, ehr: PatientEHR) -> Dict[str, Any]:
        """
        Make readmission risk prediction for a patient.
        
        Args:
            ehr: PatientEHR database model instance
            
        Returns:
            Dict containing:
                - risk_score: Float (0.0 to 1.0) - probability of 30-day readmission
                - model_version: String - model version used
                - prediction_details: Dict with additional details
                
        Raises:
            RuntimeError: If model is not loaded
            ValueError: If feature mapping fails
        """
        if not self.model_loaded or self.model is None:
            raise RuntimeError("Readmission model is not loaded. Cannot make predictions.")
        
        try:
            # Step 1: Map EHR data to model features
            features_df = readmission_feature_mapper.map_ehr_to_features(ehr)
            
            # Step 2: Validate features
            if not readmission_feature_mapper.validate_features(features_df):
                raise ValueError("Feature validation failed - missing required features")
            
            # Step 3: Make prediction
            # predict_proba returns [[prob_class_0, prob_class_1]]
            # We want prob_class_1 (probability of readmission)
            prediction_proba = self.model.predict_proba(features_df)
            risk_score = float(prediction_proba[0][1])  # Probability of positive class (readmission)
            
            # Step 4: Prepare prediction details
            prediction_details = {
                "features_used": len(features_df.columns),
                "patient_age": ehr.age,
                "comorbidity_index": ehr.charlson_comorbidity_index,
                "previous_admissions_12m": ehr.previous_admissions_12m,
                "length_of_stay_days": ehr.length_of_stay_days,
                "icu_stay": bool(ehr.icu_stay_flag),
                "follow_up_scheduled": bool(ehr.follow_up_within_7_days_flag),
            }
            
            logger.info(f"Readmission prediction for patient {ehr.patient_id}: risk_score={risk_score:.4f}")
            
            return {
                "risk_score": risk_score,
                "model_version": self.MODEL_VERSION,
                "model_type": self.MODEL_TYPE,
                "prediction_details": prediction_details
            }
            
        except Exception as e:
            logger.error(f"Error making readmission prediction for patient {ehr.patient_id}: {str(e)}")
            raise
    
    def predict_batch(self, ehr_list: list[PatientEHR]) -> list[Dict[str, Any]]:
        """
        Make readmission predictions for multiple patients.
        
        Args:
            ehr_list: List of PatientEHR instances
            
        Returns:
            List of prediction dictionaries
        """
        if not self.model_loaded or self.model is None:
            raise RuntimeError("Readmission model is not loaded. Cannot make predictions.")
        
        predictions = []
        for ehr in ehr_list:
            try:
                prediction = self.predict(ehr)
                predictions.append({
                    "patient_id": ehr.patient_id,
                    "mrn": ehr.mrn,
                    **prediction
                })
            except Exception as e:
                logger.error(f"Failed to predict for patient {ehr.patient_id}: {str(e)}")
                predictions.append({
                    "patient_id": ehr.patient_id,
                    "mrn": ehr.mrn,
                    "error": str(e)
                })
        
        return predictions
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Dict with model metadata
        """
        return {
            "model_type": self.MODEL_TYPE,
            "model_version": self.MODEL_VERSION,
            "model_loaded": self.model_loaded,
            "model_path": str(self.MODEL_PATH),
            "algorithm": "Logistic Regression",
            "features_count": 25,
            "accuracy": 0.819,
            "auc_roc": 0.806,
            "f1_score": 0.409,
        }


# Singleton instance
readmission_prediction_service = ReadmissionPredictionService()
