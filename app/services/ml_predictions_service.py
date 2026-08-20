"""
ML Predictions Service

CRUD operations for ML predictions database.
Handles storing and retrieving predictions from all ML models.

Author: CarePath AI Team
Date: 2026-08-20
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.ml_predictions import MLPrediction
from app.schemas.ml_predictions import MLPredictionCreate

logger = logging.getLogger(__name__)


class MLPredictionsService:
    """
    Service for managing ML predictions in the database.
    """
    
    async def create_prediction(
        self,
        db: AsyncSession,
        prediction_data: MLPredictionCreate
    ) -> MLPrediction:
        """
        Store a new ML prediction in the database.
        
        Args:
            db: Database session
            prediction_data: Prediction data to store
            
        Returns:
            MLPrediction: Created prediction record
        """
        try:
            prediction = MLPrediction(
                patient_id=prediction_data.patient_id,
                mrn=prediction_data.mrn,
                model_type=prediction_data.model_type,
                model_version=prediction_data.model_version,
                risk_score=prediction_data.risk_score,
                prediction_result=prediction_data.prediction_result,
                created_by=prediction_data.created_by,
                predicted_at=datetime.utcnow()
            )
            
            db.add(prediction)
            await db.commit()
            await db.refresh(prediction)
            
            logger.info(
                f"Stored {prediction_data.model_type} prediction for patient {prediction_data.patient_id}: "
                f"risk_score={prediction_data.risk_score:.4f}"
            )
            
            return prediction
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error storing prediction: {str(e)}")
            raise
    
    async def get_latest_prediction(
        self,
        db: AsyncSession,
        patient_id: str,
        model_type: str
    ) -> Optional[MLPrediction]:
        """
        Get the most recent prediction for a patient and model type.
        
        Args:
            db: Database session
            patient_id: Patient ID
            model_type: Model type (readmission, ed_avoidable, etc.)
            
        Returns:
            MLPrediction or None if not found
        """
        try:
            stmt = select(MLPrediction).where(
                MLPrediction.patient_id == patient_id,
                MLPrediction.model_type == model_type
            ).order_by(desc(MLPrediction.predicted_at)).limit(1)
            
            result = await db.execute(stmt)
            prediction = result.scalar_one_or_none()
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error retrieving latest prediction: {str(e)}")
            raise
    
    async def get_prediction_history(
        self,
        db: AsyncSession,
        patient_id: str,
        model_type: Optional[str] = None,
        limit: int = 10
    ) -> List[MLPrediction]:
        """
        Get prediction history for a patient.
        
        Args:
            db: Database session
            patient_id: Patient ID
            model_type: Optional model type filter
            limit: Maximum number of records to return
            
        Returns:
            List of MLPrediction records
        """
        try:
            stmt = select(MLPrediction).where(
                MLPrediction.patient_id == patient_id
            )
            
            if model_type:
                stmt = stmt.where(MLPrediction.model_type == model_type)
            
            stmt = stmt.order_by(desc(MLPrediction.predicted_at)).limit(limit)
            
            result = await db.execute(stmt)
            predictions = result.scalars().all()
            
            return list(predictions)
            
        except Exception as e:
            logger.error(f"Error retrieving prediction history: {str(e)}")
            raise
    
    async def get_prediction_by_id(
        self,
        db: AsyncSession,
        prediction_id: int
    ) -> Optional[MLPrediction]:
        """
        Get a specific prediction by ID.
        
        Args:
            db: Database session
            prediction_id: Prediction ID
            
        Returns:
            MLPrediction or None if not found
        """
        try:
            stmt = select(MLPrediction).where(MLPrediction.id == prediction_id)
            result = await db.execute(stmt)
            prediction = result.scalar_one_or_none()
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error retrieving prediction by ID: {str(e)}")
            raise
    
    async def get_all_predictions_for_patient(
        self,
        db: AsyncSession,
        patient_id: str
    ) -> Dict[str, MLPrediction]:
        """
        Get the latest prediction for each model type for a patient.
        
        Args:
            db: Database session
            patient_id: Patient ID
            
        Returns:
            Dict mapping model_type -> latest MLPrediction
        """
        try:
            stmt = select(MLPrediction).where(
                MLPrediction.patient_id == patient_id
            ).order_by(desc(MLPrediction.predicted_at))
            
            result = await db.execute(stmt)
            all_predictions = result.scalars().all()
            
            # Keep only the latest prediction for each model type
            latest_by_model = {}
            for pred in all_predictions:
                if pred.model_type not in latest_by_model:
                    latest_by_model[pred.model_type] = pred
            
            return latest_by_model
            
        except Exception as e:
            logger.error(f"Error retrieving all predictions for patient: {str(e)}")
            raise


# Singleton instance
ml_predictions_service = MLPredictionsService()
