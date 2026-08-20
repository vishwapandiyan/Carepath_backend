from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Dict, Optional
import logging

from app.core.security import get_current_patient
from app.db.session import get_db
from app.models import User
from app.models.ehr import PatientEHR
from app.services.ed_feature_mapper import ed_feature_mapper
from app.services.ed_prediction_service import ed_prediction_service

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
