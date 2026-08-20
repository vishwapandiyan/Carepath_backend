from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Dict, Optional, List
import logging

from app.core.security import get_current_patient
from app.db.session import get_db
from app.models import User
from app.models.ehr import PatientEHR
from app.services.ed_feature_mapper import ed_feature_mapper
from app.services.ed_prediction_service import ed_prediction_service
from app.services.readmission_prediction_service import readmission_prediction_service
from app.services.ml_predictions_service import ml_predictions_service
from app.schemas.ml_predictions import (
    MLPredictionCreate,
    MLPredictionResponse,
    ReadmissionPredictionResponse
)
from app.services.ehr_crud_service import ehr_crud_service

logger = logging.getLogger(__name__)

router = APIRouter()


# === Request/Response Models ===

class EDPredictionRequest(BaseModel):
    """Request for ED Avoidable prediction"""
    patient_mrn: Optional[str] = Field(None, description="Patient MRN for EHR lookup (optional)")
    intake_data: Dict = Field(..., description="8 fields from chatbot intake")
    safety_flags: Dict = Field(..., description="12 red flag fields from safety screening")
    
    class Config:
        json_schema_extra = {
            "example": {
                "patient_mrn": "MRN-2024-001234",
                "intake_data": {
                    "chief_complaint": "chest pain",
                    "symptom_onset": "2 hours ago",
                    "pain_scale": 7,
                    "location": "left chest",
                    "pain_duration": "2 hours",
                    "pain_character": "pressure",
                    "pain_radiating": "yes, to left arm",
                    "symptom_trend": "getting worse"
                },
                "safety_flags": {
                    "chest_pain": True,
                    "difficulty_breathing": False,
                    "altered_consciousness": False,
                    "severe_bleeding": False,
                    "stroke_symptoms": False,
                    "suicidal_ideation": False,
                    "anaphylaxis": False,
                    "high_fever": False,
                    "unable_to_walk": False,
                    "severe_abdominal_pain": False,
                    "vomiting_blood": False,
                    "severe_dehydration": False
                }
            }
        }


class EDPredictionResponse(BaseModel):
    """Response from ED Avoidable prediction"""
    success: bool = Field(..., description="Whether prediction was successful")
    avoidable_ed: str = Field(..., description="YES if avoidable, NO if ED needed")
    probability: float = Field(..., description="Probability that visit is avoidable (0-1)")
    confidence: str = Field(..., description="Confidence level: high, medium, or low")
    recommendation: str = Field(..., description="Clinical recommendation")
    features_used: int = Field(..., description="Number of features used in prediction")
    used_ehr: bool = Field(..., description="Whether EHR data was available")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "avoidable_ed": "NO",
                "probability": 0.35,
                "confidence": "high",
                "recommendation": "Based on the clinical assessment, this ED visit appears necessary. Patient should proceed to the emergency department for evaluation and treatment.",
                "features_used": 95,
                "used_ehr": True
            }
        }


# === API Endpoints ===

@router.post("/ed-prediction", response_model=EDPredictionResponse)
async def predict_ed_avoidable(
    request: EDPredictionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Predict if ED visit is avoidable based on symptoms, red flags, and medical history.
    
    **Flow:**
    1. Called after safety screening returns "NO" (not emergency)
    2. Combines intake data + safety flags + EHR (if available)
    3. Maps to 95 ML model features
    4. Returns YES (avoidable) or NO (ED needed)
    
    **Usage:**
    - If avoidable_ed = "YES" → Route to alternative care pathways
    - If avoidable_ed = "NO" → Route to emergency department
    """
    
    logger.info(f"ED prediction request received for patient MRN: {request.patient_mrn}")
    
    try:
        # Get EHR data if patient MRN provided
        ehr_data = None
        used_ehr = False
        
        if request.patient_mrn:
            try:
                # Query EHR database
                result = await db.execute(
                    select(PatientEHR).where(PatientEHR.mrn == request.patient_mrn)
                )
                ehr_data = result.scalar_one_or_none()
                
                if ehr_data:
                    used_ehr = True
                    logger.info(f"Found EHR data for MRN: {request.patient_mrn}")
                else:
                    logger.warning(f"No EHR data found for MRN: {request.patient_mrn}, using defaults")
                    
            except Exception as e:
                logger.warning(f"Failed to fetch EHR data: {e}, using defaults")
        
        # Map to ML features (95 features)
        features = ed_feature_mapper.build_ml_features(
            intake_data=request.intake_data,
            safety_flags=request.safety_flags,
            ehr_data=ehr_data
        )
        
        logger.info(f"Mapped {len(features)} features for prediction")
        
        # Make prediction
        result = ed_prediction_service.predict(features)
        
        logger.info(
            f"Prediction complete: {result['avoidable_ed']} "
            f"(probability={result['probability']:.3f}, confidence={result['confidence']})"
        )
        
        # Store prediction in ml_predictions table if EHR data is available
        if ehr_data:
            try:
                prediction_data = MLPredictionCreate(
                    patient_id=ehr_data.patient_id,
                    mrn=ehr_data.mrn,
                    model_type="ed_avoidable",
                    model_version="1.0",
                    risk_score=result['probability'],
                    prediction_result={
                        "avoidable_ed": result['avoidable_ed'],
                        "confidence": result['confidence'],
                        "recommendation": result['recommendation'],
                        "features_used": len(features),
                        "intake_data": request.intake_data,
                        "safety_flags": request.safety_flags
                    },
                    created_by="chatbot_flow"
                )
                
                await ml_predictions_service.create_prediction(db, prediction_data)
                logger.info(f"✓ ED prediction stored for patient {ehr_data.patient_id}")
                
            except Exception as e:
                # Log error but don't fail the prediction response
                logger.error(f"Failed to store ED prediction: {str(e)}")
        
        return EDPredictionResponse(
            success=True,
            avoidable_ed=result['avoidable_ed'],
            probability=result['probability'],
            confidence=result['confidence'],
            recommendation=result['recommendation'],
            features_used=len(features),
            used_ehr=used_ehr
        )
        
    except ValueError as e:
        logger.error(f"Prediction validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"ED prediction failed: {str(e)}"
        )


@router.get("/dashboard")
async def get_patient_dashboard(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db)
):
    """
    Patient dashboard endpoint.
    Only accessible by users with PATIENT role.
    """
    return {
        "message": "Welcome to Patient Dashboard",
        "user": {
            "username": current_user.username,
            "role": current_user.role.value
        },
        "patient": {
            "mrn": getattr(current_user, "patient", None).mrn if getattr(current_user, "patient", None) else None,
        },
    }


# === Readmission Prediction Endpoints ===

@router.post("/{patient_id}/readmission-prediction", response_model=ReadmissionPredictionResponse)
async def predict_readmission_risk(
    patient_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Manual trigger for readmission risk prediction.
    
    **Purpose:** Predict 30-day hospital readmission risk based on patient EHR data.
    
    **Usage:**
    - Triggered manually from patient profile when user clicks "Predict"
    - Uses latest patient EHR data
    - Returns risk score (0.0 to 1.0)
    
    **Parameters:**
    - patient_id: Patient ID (PAT_XXXXXXXX format)
    
    **Returns:**
    - readmission_risk_score: Probability of 30-day readmission (0.0 to 1.0)
    - predicted_at: Timestamp of prediction
    - model_version: Version of ML model used
    - prediction_details: Additional details (age, comorbidities, etc.)
    """
    
    logger.info(f"Manual readmission prediction request for patient: {patient_id}")
    
    try:
        # Fetch patient EHR data
        ehr = await ehr_crud_service.get_patient_by_patient_id(db, patient_id)
        
        if not ehr:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with ID {patient_id} not found"
            )
        
        # Make readmission prediction
        prediction_result = readmission_prediction_service.predict(ehr)
        
        # Store prediction in database
        prediction_data = MLPredictionCreate(
            patient_id=ehr.patient_id,
            mrn=ehr.mrn,
            model_type=prediction_result["model_type"],
            model_version=prediction_result["model_version"],
            risk_score=prediction_result["risk_score"],
            prediction_result=prediction_result["prediction_details"],
            created_by="manual_trigger"  # Manual prediction
        )
        
        stored_prediction = await ml_predictions_service.create_prediction(db, prediction_data)
        
        logger.info(
            f"✓ Readmission prediction completed for patient {patient_id}: "
            f"risk_score={prediction_result['risk_score']:.4f}"
        )
        
        return ReadmissionPredictionResponse(
            readmission_risk_score=prediction_result["risk_score"],
            predicted_at=stored_prediction.predicted_at,
            model_version=prediction_result["model_version"],
            prediction_details=prediction_result["prediction_details"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readmission prediction failed for patient {patient_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Readmission prediction failed: {str(e)}"
        )


@router.get("/{patient_id}/ml-predictions", response_model=List[MLPredictionResponse])
async def get_ml_predictions_history(
    patient_id: str,
    model_type: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """
    Get ML prediction history for a patient.
    
    **Purpose:** Retrieve historical predictions for a patient across all ML models.
    
    **Parameters:**
    - patient_id: Patient ID (PAT_XXXXXXXX format)
    - model_type: Optional filter by model type (readmission, ed_avoidable, etc.)
    - limit: Maximum number of records to return (default: 10)
    
    **Returns:**
    - List of ML predictions with risk scores and timestamps
    """
    
    logger.info(f"Fetching ML predictions for patient: {patient_id}, model_type: {model_type}")
    
    try:
        # Verify patient exists
        ehr = await ehr_crud_service.get_patient_by_patient_id(db, patient_id)
        
        if not ehr:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with ID {patient_id} not found"
            )
        
        # Get prediction history
        predictions = await ml_predictions_service.get_prediction_history(
            db,
            patient_id=patient_id,
            model_type=model_type,
            limit=limit
        )
        
        logger.info(f"Retrieved {len(predictions)} predictions for patient {patient_id}")
        
        return predictions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve predictions for patient {patient_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve predictions: {str(e)}"
        )


@router.get("/{patient_id}/latest-predictions")
async def get_latest_predictions_by_model(
    patient_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the latest prediction for each model type for a patient.
    
    **Purpose:** Show current risk scores across all ML models on patient profile.
    
    **Parameters:**
    - patient_id: Patient ID (PAT_XXXXXXXX format)
    
    **Returns:**
    - Dict mapping model_type -> latest prediction
    - Example: {"readmission": {...}, "ed_avoidable": {...}}
    """
    
    logger.info(f"Fetching latest predictions for patient: {patient_id}")
    
    try:
        # Verify patient exists
        ehr = await ehr_crud_service.get_patient_by_patient_id(db, patient_id)
        
        if not ehr:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with ID {patient_id} not found"
            )
        
        # Get latest predictions for all model types
        predictions_by_model = await ml_predictions_service.get_all_predictions_for_patient(
            db,
            patient_id=patient_id
        )
        
        # Convert to response format
        response = {}
        for model_type, prediction in predictions_by_model.items():
            response[model_type] = {
                "id": prediction.id,
                "risk_score": prediction.risk_score,
                "model_version": prediction.model_version,
                "predicted_at": prediction.predicted_at,
                "prediction_result": prediction.prediction_result
            }
        
        logger.info(f"Retrieved latest predictions for {len(response)} models for patient {patient_id}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve latest predictions for patient {patient_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve latest predictions: {str(e)}"
        )

