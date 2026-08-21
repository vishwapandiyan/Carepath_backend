"""
ED Avoidable Prediction Service

Loads the trained Random Forest model and makes predictions on whether
an emergency department visit is avoidable based on patient symptoms,
red flags, and medical history.

Model Output:
- avoidable_ed = "YES" → ED visit can be avoided, use alternative care
- avoidable_ed = "NO" → ED visit is necessary, proceed to emergency department
"""

import pickle
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class EDPredictionService:
    """Service for ED Avoidable predictions"""
    
    def __init__(self):
        """Initialize service and load ML model"""
        self.model_path = Path("app/ml_models/best_avoidable_ed_model.pkl")
        self.model_bundle = None
        self.model = None
        self.feature_columns = None
        self.needs_scaling = False
        self.scaler = None
        self.encoders = {}
        self.load_model()
    
    def load_model(self):
        """
        Load the trained ED Avoidable model from pickle file.
        
        The pickle contains:
        - model: Trained Random Forest classifier
        - feature_columns: Exact list of features in correct order
        - needs_scaling: Whether to apply StandardScaler
        - scaler: StandardScaler object (if needed)
        - categorical_encoders: LabelEncoders for categorical features
        - model_name: Name of the model (Random Forest)
        - test_metrics: Performance metrics from training
        """
        try:
            if not self.model_path.exists():
                logger.warning(f"⚠️ Model file not found at {self.model_path}")
                logger.warning("⚠️ ED prediction endpoint will not work until model is available")
                return
            
            with open(self.model_path, "rb") as f:
                self.model_bundle = pickle.load(f)
            
            # Extract components
            self.model = self.model_bundle['model']
            self.feature_columns = self.model_bundle['feature_columns']
            self.needs_scaling = self.model_bundle.get('needs_scaling', False)
            self.scaler = self.model_bundle.get('scaler')
            self.encoders = self.model_bundle.get('categorical_encoders', {})
            
            model_name = self.model_bundle.get('model_name', 'Unknown')
            test_metrics = self.model_bundle.get('test_metrics', {})
            
            logger.info("✓ ED Avoidable model loaded successfully")
            logger.info(f"  Model: {model_name}")
            logger.info(f"  Features: {len(self.feature_columns)}")
            logger.info(f"  Test Recall: {test_metrics.get('recall', 'N/A')}")
            logger.info(f"  Test ROC-AUC: {test_metrics.get('roc_auc', 'N/A')}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load ED Avoidable model: {e}")
            logger.warning("⚠️ ED prediction endpoint will not work until model loads successfully")
            logger.warning("⚠️ This is expected with Python 3.14 + sklearn version mismatch")
            # Don't raise - allow server to start
    
    def _apply_categorical_encoding(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply LabelEncoder transformations to categorical columns.
        
        Args:
            df: DataFrame with raw categorical values
            
        Returns:
            DataFrame with encoded categorical values
        """
        df_encoded = df.copy()

        for col, encoder in self.encoders.items():
            if col not in df_encoded.columns:
                continue

            known = set(map(str, encoder.classes_))
            default_code = int(encoder.transform([encoder.classes_[0]])[0])

            def _encode_value(value, _col=col, _encoder=encoder, _known=known, _default=default_code):
                s = str(value)
                if s in _known:
                    return int(_encoder.transform([s])[0])
                # Unseen category → this silently distorts the model input, so make it loud.
                logger.warning(
                    "ED model categorical mismatch: feature '%s' got unseen value %r; "
                    "expected one of %s. Falling back to '%s'.",
                    _col, s, list(_encoder.classes_), _encoder.classes_[0],
                )
                return _default

            df_encoded[col] = df_encoded[col].map(_encode_value)

        return df_encoded
    
    def predict(self, features: Dict) -> Dict:
        """
        Make prediction on whether ED visit is avoidable.
        
        Args:
            features: Dict with 95 features from EDFeatureMapper
        
        Returns:
            {
                "avoidable_ed": "YES" | "NO",
                "probability": float (0-1), probability that visit IS avoidable
                "confidence": "high" | "medium" | "low",
                "recommendation": str
            }
        
        Raises:
            RuntimeError: If model not loaded
            ValueError: If prediction fails
        """
        if not self.model_bundle or not self.model:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        try:
            # Create DataFrame with exact column order from training
            df = pd.DataFrame([features])
            
            # Ensure we have all required features
            missing_features = set(self.feature_columns) - set(df.columns)
            if missing_features:
                logger.error(f"Missing features: {missing_features}")
                raise ValueError(f"Missing required features: {missing_features}")
            
            # Select and order columns to match training
            df = df[self.feature_columns]
            
            # Apply categorical encoding
            df = self._apply_categorical_encoding(df)
            
            # Apply scaling if needed (Logistic Regression uses scaling)
            if self.needs_scaling and self.scaler:
                df = pd.DataFrame(
                    self.scaler.transform(df),
                    columns=df.columns,
                    index=df.index
                )
            
            # Make prediction
            # predict_proba returns [[prob_class_0, prob_class_1]]
            # We want probability of class 1 (avoidable_ed = 1, meaning YES)
            probabilities = self.model.predict_proba(df)
            probability_avoidable = float(probabilities[0][1])
            
            # Binary prediction
            prediction = "YES" if probability_avoidable > 0.5 else "NO"
            
            # Determine confidence level
            if probability_avoidable > 0.7 or probability_avoidable < 0.3:
                confidence = "high"
            elif probability_avoidable > 0.6 or probability_avoidable < 0.4:
                confidence = "medium"
            else:
                confidence = "low"
            
            # Generate recommendation
            if prediction == "YES":
                recommendation = (
                    "Based on the clinical assessment, this ED visit may be avoidable. "
                    "Consider alternative care pathways such as telemedicine consultation, "
                    "urgent care clinic, or primary care follow-up."
                )
            else:
                recommendation = (
                    "Based on the clinical assessment, this ED visit appears necessary. "
                    "Patient should proceed to the emergency department for evaluation and treatment."
                )
            
            result = {
                "avoidable_ed": prediction,
                "probability": probability_avoidable,
                "confidence": confidence,
                "recommendation": recommendation
            }
            
            logger.info(
                f"ED Prediction: {prediction} (probability={probability_avoidable:.3f}, "
                f"confidence={confidence})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            raise ValueError(f"ED prediction failed: {str(e)}")
    
    def batch_predict(self, features_list: list[Dict]) -> list[Dict]:
        """
        Make predictions for multiple patients.
        
        Args:
            features_list: List of feature dicts
            
        Returns:
            List of prediction result dicts
        """
        results = []
        
        for idx, features in enumerate(features_list):
            try:
                result = self.predict(features)
                results.append(result)
            except Exception as e:
                logger.error(f"Prediction failed for patient {idx}: {str(e)}")
                results.append({
                    "avoidable_ed": "ERROR",
                    "probability": 0.0,
                    "confidence": "none",
                    "recommendation": f"Prediction failed: {str(e)}"
                })
        
        return results


# Global singleton instance
# Loaded once at startup for efficiency
ed_prediction_service = EDPredictionService()
