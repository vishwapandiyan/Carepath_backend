# ED Avoidable Model Integration Plan

## 📋 Overview

This document outlines the plan to integrate the **ED Avoidable ML Model** into the existing CarePath AI backend system.

### Flow Architecture
```
User Input → Chatbot UI → Intake (4 questions) → Safety Screening (10 red flags) 
                                                          ↓
                                                    Decision Point
                                                          ↓
                                    YES (Emergency)              NO (Not Emergency)
                                          ↓                            ↓
                                  Emergency Room                 ML Pathway
                                                                       ↓
                                                          ED Avoidable Model
                                                                       ↓
                                                            YES / NO Decision
```

---

## 🎯 Current System Analysis

### ✅ What Already Exists

1. **Chatbot UI** (`chatbot_ui.py`)
   - Phase 1: Intake - Collects 4 basic fields via conversational interface
   - Phase 2: Safety Screening - 10 YES/NO red flag questions
   - Phase 3: Verdict - Shows if emergency or routes to "ML Pathway"

2. **Intake Data Collection** (from chatbot)
   - `chief_complaint` - Main symptom
   - `symptom_onset` - When symptoms started
   - `pain_scale` - Pain level (0-10)
   - `location` - Body location of symptom

3. **Safety Screening** (10 Red Flags)
   - `chest_pain`
   - `difficulty_breathing`
   - `altered_consciousness`
   - `severe_bleeding`
   - `stroke_symptoms`
   - `suicidal_ideation`
   - `anaphylaxis`
   - `high_fever`
   - `unable_to_walk`
   - `severe_abdominal_pain`

4. **EHR System** (`app/models/ehr.py`, `app/schemas/ehr.py`)
   - Comprehensive patient health records with 50+ medical fields
   - Demographics, chronic conditions, vital signs, lab values, medications, utilization history

5. **ML Model Package** (`ML_Complete_Package/`)
   - Trained model: `best_avoidable_ed_model.pkl`
   - Training code: `ml_pipeline_avoidable_ed.py`
   - Prediction service: `code/prediction_service.py` (for readmission model)
   - Schemas: `code/schemas.py`

---

## 🔍 Gap Analysis

### ❌ What's Missing

#### 1. **Feature Mapping Gap**
The ML model requires **95 features**, but we only collect:
- **4 fields** from intake (conversational chatbot)
- **10 fields** from safety screening (yes/no questions)
- **Total: 14 fields** vs **95 required**

#### 2. **Data Source Mismatch**

**ML Model Expects** (from `ml_pipeline_avoidable_ed.py`):

| Category | Features | Source |
|----------|----------|--------|
| **Symptom Data** (9 fields) | `primary_symptom_category`, `pain_level_self_reported`, `pain_onset`, `pain_duration`, `pain_location`, `pain_character`, `pain_radiating`, `symptom_trend` | ❌ **NOT COLLECTED** (only basic info) |
| **Red Flags** (10 fields) | `flag_shortness_of_breath`, `flag_chest_pain_sweating_nausea`, etc. | ✅ **Available** (from safety screening) |
| **Vital Signs** (7 fields) | `systolic_bp`, `diastolic_bp`, `heart_rate`, `respiratory_rate`, `temperature`, `spo2`, `pain_score_clinical` | ✅ **Available** (from EHR) |
| **Lab Values** (13 fields) | `wbc`, `hemoglobin`, `platelet_count`, `sodium`, `potassium`, `creatinine`, `glucose`, `troponin`, `bnp`, `lactate`, `inr` | ✅ **Available** (from EHR) |
| **Chronic Conditions** (9 fields) | `diabetes_flag`, `hypertension_flag`, `cardiac_history_flag`, etc. | ✅ **Available** (from EHR) |
| **Comorbidity** (2 fields) | `chronic_condition_count`, `charlson_comorbidity_index` | ✅ **Available** (from EHR) |
| **Medications** (4 fields) | `active_medication_count`, `on_anticoagulants_flag`, `on_insulin_flag` | ✅ **Available** (from EHR) |
| **Utilization History** (5 fields) | `days_since_last_ed_visit`, `ed_visits_past_year`, `admissions_past_year`, `has_pcp_flag` | ✅ **Available** (from EHR) |
| **Demographics** (3 fields) | `age`, `gender` | ✅ **Available** (from EHR) |

**Key Gap**: We're missing detailed symptom characterization questions:
- `pain_duration` - How long have you had this pain?
- `pain_character` - Sharp, dull, throbbing, burning, cramping?
- `pain_radiating` - Does the pain spread to other areas? (yes/no)
- `symptom_trend` - Are symptoms getting better, worse, or staying the same?
- `primary_symptom_category` - Needs to be classified from chief_complaint

#### 3. **Field Name Mismatches**

| ML Model Field | EHR Field | Match? |
|----------------|-----------|--------|
| `wbc` | `wbc_count` | ❌ Different name |
| `pain_level_self_reported` | `pain_scale` (from intake) | ❌ Different name |
| `pain_score_clinical` | Not in current EHR | ❌ Missing |
| `has_pcp_flag` | Not in current EHR | ❌ Missing |
| `ed_visits_past_year` | `previous_er_visits_12m` | ❌ Different name |
| `admissions_past_year` | `previous_admissions_12m` | ❌ Different name |

#### 4. **Missing API Endpoints**
- No endpoint to trigger ED Avoidable prediction after safety screening
- No endpoint to collect extended symptom details
- No endpoint to return ED Avoidable result to UI

---

## ✅ Integration Solution

### Phase 1: Extend Data Collection

#### A. **Extend Intake Questions** (Add 4 more questions)

Update `app/services/vocabulary.py` to add:

```python
QUESTION_TEMPLATES = {
    # Existing
    "chief_complaint": "What is your main symptom or concern today?",
    "symptom_onset": "When did your symptoms begin?",
    "pain_scale": "On a scale of 0 to 10, how severe is your pain?",
    "location": "Where are you experiencing this symptom?",
    
    # NEW - Add these 4
    "pain_duration": "How long have you been experiencing this symptom? (hours/days/weeks)",
    "pain_character": "How would you describe the pain? (sharp, dull, throbbing, burning, cramping, pressure)",
    "pain_radiating": "Does the pain spread or radiate to other parts of your body?",
    "symptom_trend": "Are your symptoms getting better, worse, or staying the same?"
}

REQUIRED_FIELD_ORDER = [
    "chief_complaint",
    "symptom_onset",
    "pain_scale",
    "location",
    "pain_duration",      # NEW
    "pain_character",     # NEW
    "pain_radiating",     # NEW
    "symptom_trend"       # NEW
]
```

#### B. **Map Safety Screening to ML Model Red Flags**

Current safety screening fields → ML model fields:

| Chatbot Field | ML Model Field | Mapping |
|---------------|----------------|---------|
| `chest_pain` | `flag_chest_pain_sweating_nausea` | Direct |
| `difficulty_breathing` | `flag_shortness_of_breath` | Direct |
| `altered_consciousness` | `flag_confusion_altered_mental_state` + `flag_loss_of_consciousness` | Split logic |
| `severe_bleeding` | `flag_uncontrolled_bleeding` | Direct |
| `stroke_symptoms` | `flag_stroke_signs` | Direct |
| `suicidal_ideation` | None (not in ML model) | Skip |
| `anaphylaxis` | `flag_severe_allergic_reaction` | Direct |
| `high_fever` | `flag_high_fever_stiff_neck_rash` | Direct |
| `unable_to_walk` | None (not in ML model) | Skip |
| `severe_abdominal_pain` | None (could map to `primary_symptom_category`) | Skip |

**Missing ML Red Flags** (need to add to chatbot OR default to False):
- `flag_vomiting_blood_or_blood_in_stool` → **Need to add**
- `flag_severe_dehydration` → **Need to add**

### Phase 2: Create Feature Engineering Service

Create `app/services/ed_feature_mapper.py`:

```python
"""
ED Avoidable Feature Mapper
Maps data from Intake + Safety + EHR → ML Model Features
"""

from typing import Dict, Optional
from app.models.ehr import PatientEHR


class EDFeatureMapper:
    """Maps collected data to ED Avoidable model features"""
    
    @staticmethod
    def map_primary_symptom_category(chief_complaint: str) -> str:
        """
        Map chief complaint to one of:
        abdominal_pain, back_pain, chest_pain, headache, 
        shortness_of_breath, fever, injury, other
        """
        # Use keyword matching or LLM classification
        chief_complaint_lower = chief_complaint.lower()
        
        if any(word in chief_complaint_lower for word in ['chest', 'heart']):
            return 'chest_pain'
        elif any(word in chief_complaint_lower for word in ['breath', 'breathing', 'asthma']):
            return 'shortness_of_breath'
        elif any(word in chief_complaint_lower for word in ['stomach', 'abdomen', 'belly']):
            return 'abdominal_pain'
        elif any(word in chief_complaint_lower for word in ['back']):
            return 'back_pain'
        elif any(word in chief_complaint_lower for word in ['head', 'migraine']):
            return 'headache'
        elif any(word in chief_complaint_lower for word in ['fever', 'temperature', 'hot']):
            return 'fever'
        elif any(word in chief_complaint_lower for word in ['injury', 'fall', 'accident', 'trauma']):
            return 'injury'
        else:
            return 'other'
    
    @staticmethod
    def map_pain_onset(symptom_onset: str) -> str:
        """
        Map symptom onset to: sudden, gradual, chronic
        """
        onset_lower = symptom_onset.lower()
        
        if any(word in onset_lower for word in ['sudden', 'suddenly', 'immediately', 'instant', 'now']):
            return 'sudden'
        elif any(word in onset_lower for word in ['gradual', 'slowly', 'progressive', 'over time']):
            return 'gradual'
        elif any(word in onset_lower for word in ['days', 'weeks', 'months', 'chronic', 'long']):
            return 'chronic'
        else:
            return 'gradual'  # default
    
    @staticmethod
    def build_ml_features(
        intake_data: Dict,
        safety_flags: Dict,
        ehr_data: Optional[PatientEHR]
    ) -> Dict:
        """
        Build complete feature dict for ML model
        
        Args:
            intake_data: From chatbot intake (8 fields)
            safety_flags: From safety screening (10 fields)
            ehr_data: From EHR database (optional, for existing patients)
        
        Returns:
            Dict with 95 features for ML model
        """
        
        features = {}
        
        # === Symptom Data (9 fields) ===
        features['primary_symptom_category'] = EDFeatureMapper.map_primary_symptom_category(
            intake_data.get('chief_complaint', 'other')
        )
        features['pain_level_self_reported'] = intake_data.get('pain_scale', 0)
        features['pain_onset'] = EDFeatureMapper.map_pain_onset(
            intake_data.get('symptom_onset', 'gradual')
        )
        features['pain_duration'] = intake_data.get('pain_duration', 'unknown')
        features['pain_location'] = intake_data.get('location', 'unknown')
        features['pain_character'] = intake_data.get('pain_character', 'unknown')
        features['pain_radiating'] = 1 if intake_data.get('pain_radiating', '').lower() in ['yes', 'true'] else 0
        features['symptom_trend'] = intake_data.get('symptom_trend', 'stable')
        
        # === Red Flags (10 fields) ===
        features['flag_shortness_of_breath'] = 1 if safety_flags.get('difficulty_breathing') else 0
        features['flag_chest_pain_sweating_nausea'] = 1 if safety_flags.get('chest_pain') else 0
        features['flag_loss_of_consciousness'] = 1 if safety_flags.get('altered_consciousness') else 0
        features['flag_confusion_altered_mental_state'] = 1 if safety_flags.get('altered_consciousness') else 0
        features['flag_uncontrolled_bleeding'] = 1 if safety_flags.get('severe_bleeding') else 0
        features['flag_severe_allergic_reaction'] = 1 if safety_flags.get('anaphylaxis') else 0
        features['flag_stroke_signs'] = 1 if safety_flags.get('stroke_symptoms') else 0
        features['flag_vomiting_blood_or_blood_in_stool'] = 0  # Default False (not in current screening)
        features['flag_high_fever_stiff_neck_rash'] = 1 if safety_flags.get('high_fever') else 0
        features['flag_severe_dehydration'] = 0  # Default False (not in current screening)
        
        # === EHR Data (if available) ===
        if ehr_data:
            # Vital Signs (7 fields)
            features['systolic_bp'] = ehr_data.systolic_bp or 120
            features['diastolic_bp'] = ehr_data.diastolic_bp or 80
            features['heart_rate'] = ehr_data.heart_rate or 70
            features['respiratory_rate'] = ehr_data.respiratory_rate or 16
            features['temperature'] = ehr_data.temperature or 98.6
            features['spo2'] = ehr_data.spo2 or 98
            features['pain_score_clinical'] = ehr_data.pain_score_clinical or features['pain_level_self_reported']
            
            # Lab Values (13 fields)
            features['wbc'] = ehr_data.wbc_count or 7.0
            features['hemoglobin'] = ehr_data.hemoglobin or 14.0
            features['platelet_count'] = ehr_data.platelet_count or 250000
            features['sodium'] = ehr_data.sodium or 140.0
            features['potassium'] = ehr_data.potassium or 4.0
            features['creatinine'] = ehr_data.creatinine or 1.0
            features['glucose'] = ehr_data.glucose or 100
            features['troponin'] = ehr_data.troponin or 0.01
            features['bnp'] = ehr_data.bnp or 50
            features['lactate'] = ehr_data.lactate or 1.0
            features['inr'] = ehr_data.inr or 1.0
            
            # Chronic Conditions (9 fields)
            features['diabetes_flag'] = ehr_data.diabetes_flag or 0
            features['hypertension_flag'] = ehr_data.hypertension_flag or 0
            features['cardiac_history_flag'] = ehr_data.cardiac_history_flag or 0
            features['copd_asthma_flag'] = ehr_data.copd_asthma_flag or 0
            features['ckd_flag'] = ehr_data.ckd_flag or 0
            features['cancer_flag'] = ehr_data.cancer_flag or 0
            features['immunocompromised_flag'] = ehr_data.immunocompromised_flag or 0
            
            # Comorbidity (2 fields)
            features['chronic_condition_count'] = sum([
                features['diabetes_flag'],
                features['hypertension_flag'],
                features['cardiac_history_flag'],
                features['copd_asthma_flag'],
                features['ckd_flag'],
                features['cancer_flag']
            ])
            features['charlson_comorbidity_index'] = ehr_data.charlson_comorbidity_index or 0
            
            # Medications (4 fields)
            features['active_medication_count'] = ehr_data.active_medication_count or 0
            features['on_anticoagulants_flag'] = ehr_data.on_anticoagulants_flag or 0
            features['on_insulin_flag'] = ehr_data.on_insulin_flag or 0
            
            # Utilization History (5 fields)
            features['days_since_last_ed_visit'] = ehr_data.days_since_last_ed_visit or 365
            features['ed_visits_past_year'] = ehr_data.previous_er_visits_12m or 0
            features['admissions_past_year'] = ehr_data.previous_admissions_12m or 0
            features['has_pcp_flag'] = 1  # Assume yes if EHR exists
            
            # Demographics (3 fields)
            features['age'] = ehr_data.age or 30
            features['gender'] = ehr_data.gender or 'unknown'
            
        else:
            # === Default Values for Patients WITHOUT EHR ===
            # Use population averages / safe defaults
            
            # Vital Signs
            features['systolic_bp'] = 120
            features['diastolic_bp'] = 80
            features['heart_rate'] = 70
            features['respiratory_rate'] = 16
            features['temperature'] = 98.6
            features['spo2'] = 98
            features['pain_score_clinical'] = features['pain_level_self_reported']
            
            # Lab Values (use normal ranges)
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
            
            # Utilization History
            features['days_since_last_ed_visit'] = 365
            features['ed_visits_past_year'] = 0
            features['admissions_past_year'] = 0
            features['has_pcp_flag'] = 0
            
            # Demographics
            features['age'] = 30  # Default age
            features['gender'] = 'unknown'
        
        return features
```

### Phase 3: Create ED Prediction Service

Create `app/services/ed_prediction_service.py`:

```python
"""
ED Avoidable Prediction Service
Loads model and makes predictions
"""

import pickle
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict


class EDPredictionService:
    """Service for ED Avoidable predictions"""
    
    def __init__(self):
        self.model_path = Path("ML_Complete_Package/best_avoidable_ed_model.pkl")
        self.model_bundle = None
        self.load_model()
    
    def load_model(self):
        """Load the trained ED Avoidable model"""
        try:
            with open(self.model_path, "rb") as f:
                self.model_bundle = pickle.load(f)
            print(f"✓ ED Avoidable model loaded successfully")
            print(f"  Model: {self.model_bundle['model_name']}")
            print(f"  Features: {len(self.model_bundle['feature_columns'])}")
        except Exception as e:
            print(f"✗ Failed to load ED Avoidable model: {e}")
            raise
    
    def predict(self, features: Dict) -> Dict:
        """
        Make prediction on whether ED visit is avoidable
        
        Args:
            features: Dict with 95 features from EDFeatureMapper
        
        Returns:
            {
                "avoidable_ed": "YES" | "NO",
                "probability": float (0-1),
                "confidence": "high" | "medium" | "low",
                "recommendation": str
            }
        """
        if not self.model_bundle:
            raise RuntimeError("Model not loaded")
        
        # Get model components
        model = self.model_bundle['model']
        feature_columns = self.model_bundle['feature_columns']
        needs_scaling = self.model_bundle['needs_scaling']
        scaler = self.model_bundle.get('scaler')
        encoders = self.model_bundle.get('categorical_encoders', {})
        
        # Create DataFrame with exact column order
        df = pd.DataFrame([features])[feature_columns]
        
        # Apply categorical encoding
        for col, le in encoders.items():
            if col in df.columns:
                try:
                    df[col] = le.transform(df[col].astype(str))
                except ValueError:
                    # Unknown category - use most frequent
                    df[col] = le.transform([le.classes_[0]])[0]
        
        # Apply scaling if needed
        if needs_scaling and scaler:
            df = scaler.transform(df)
        
        # Make prediction
        probability = float(model.predict_proba(df)[0][1])  # Probability of avoidable
        prediction = "YES" if probability > 0.5 else "NO"
        
        # Determine confidence
        if probability > 0.7 or probability < 0.3:
            confidence = "high"
        elif probability > 0.6 or probability < 0.4:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Generate recommendation
        if prediction == "YES":
            recommendation = (
                "This ED visit appears to be avoidable. Consider telemedicine consultation, "
                "urgent care, or primary care follow-up instead of emergency department."
            )
        else:
            recommendation = (
                "This ED visit appears necessary. Patient should proceed to emergency department "
                "for evaluation and treatment."
            )
        
        return {
            "avoidable_ed": prediction,
            "probability": probability,
            "confidence": confidence,
            "recommendation": recommendation
        }


# Global instance
ed_prediction_service = EDPredictionService()
```

### Phase 4: Create API Endpoints

Add to `app/api/v1/endpoints/patient.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Optional

from app.core.security import get_current_patient
from app.db.session import get_db
from app.models import User
from app.services.ed_feature_mapper import EDFeatureMapper
from app.services.ed_prediction_service import ed_prediction_service
from app.services.ehr_service import get_patient_ehr_by_mrn

router = APIRouter()


class EDPredictionRequest(BaseModel):
    """Request for ED Avoidable prediction"""
    patient_mrn: Optional[str] = None
    intake_data: Dict
    safety_flags: Dict


class EDPredictionResponse(BaseModel):
    """Response from ED Avoidable prediction"""
    avoidable_ed: str  # YES or NO
    probability: float
    confidence: str
    recommendation: str
    features_used: int


@router.post("/ed-prediction", response_model=EDPredictionResponse)
async def predict_ed_avoidable(
    request: EDPredictionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Predict if ED visit is avoidable
    Called after safety screening returns "NO" (not emergency)
    """
    
    # Get EHR data if patient MRN provided
    ehr_data = None
    if request.patient_mrn:
        try:
            ehr_data = await get_patient_ehr_by_mrn(db, request.patient_mrn)
        except:
            pass  # Continue without EHR data
    
    # Map features
    features = EDFeatureMapper.build_ml_features(
        intake_data=request.intake_data,
        safety_flags=request.safety_flags,
        ehr_data=ehr_data
    )
    
    # Make prediction
    result = ed_prediction_service.predict(features)
    
    return EDPredictionResponse(
        avoidable_ed=result['avoidable_ed'],
        probability=result['probability'],
        confidence=result['confidence'],
        recommendation=result['recommendation'],
        features_used=len(features)
    )


@router.get("/dashboard")
async def get_patient_dashboard(
    current_user: User = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db)
):
    """Patient dashboard endpoint"""
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
```

### Phase 5: Update Chatbot UI

Update `chatbot_ui.py` verdict phase to call ED prediction:

```python
elif st.session_state.phase == "verdict":
    result = st.session_state.safety_result or {}
    outcome = result.get("result", "ERROR")
    next_action = result.get("next_action", "ERROR")
    triggered = result.get("triggered_rules", [])

    st.progress(1.0, text="Step 3 of 3 — Complete")

    if outcome == "YES":
        # ... existing emergency code ...
    
    elif outcome == "NO":
        st.markdown(
            """
            <div style="background:#1a7a4a;border-radius:16px;padding:32px;text-align:center;color:white;">
                <h1 style="margin:0;font-size:3rem;">✅ No Emergency Detected</h1>
                <p style="font-size:1.4rem;margin-top:8px;">Analyzing if ED visit is necessary...</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # === NEW: Call ED Avoidable Prediction ===
        with st.spinner("Running ED Avoidable analysis..."):
            ed_request = {
                "patient_mrn": st.session_state.patient_id,
                "intake_data": st.session_state.intake_features or {},
                "safety_flags": st.session_state.red_flags or {}
            }
            
            ed_result = api_post("/patient/ed-prediction", ed_request)
            
            if ed_result:
                st.divider()
                
                if ed_result['avoidable_ed'] == "YES":
                    st.success("✅ **ED Visit May Be Avoidable**")
                    st.metric("Confidence", ed_result['confidence'].upper())
                    st.info(f"**Recommendation**: {ed_result['recommendation']}")
                else:
                    st.warning("⚠️ **ED Visit Recommended**")
                    st.metric("Confidence", ed_result['confidence'].upper())
                    st.info(f"**Recommendation**: {ed_result['recommendation']}")
                
                st.metric("Probability of Avoidable", f"{ed_result['probability']*100:.1f}%")
```

---

## 🚨 Critical Questions to Clarify

### 1. **Missing EHR Fields**
The EHR model currently does NOT have:
- `pain_score_clinical` - Clinical pain assessment
- `has_pcp_flag` - Does patient have a primary care physician?

**Question**: Should we add these fields to the EHR schema? Or use defaults?

**Recommendation**: 
- Add `pain_score_clinical` to EHR (can differ from self-reported pain)
- Add `has_pcp_flag` to EHR utilization history

### 2. **New Patients Without EHR**
What happens when a NEW patient (no EHR record) uses the chatbot?

**Options**:
- **Option A**: Require EHR creation first (blocks emergency triage!)
- **Option B**: Use population defaults (recommended)
- **Option C**: Collect vital signs + basic medical history during intake

**Question**: Which approach do you prefer?

**Recommendation**: Use **Option B** (defaults) for true emergency triage, then create EHR after.

### 3. **Additional Symptom Questions**
ML model needs 4 more detailed questions beyond current intake:
- `pain_duration` - How long have you had symptoms?
- `pain_character` - Type of pain (sharp, dull, etc.)
- `pain_radiating` - Does pain spread?
- `symptom_trend` - Getting better/worse?

**Question**: Should we add these to the conversational intake (8 total questions instead of 4)?

**Recommendation**: **YES** - Add these 4 questions. Total intake becomes 8 questions, more comprehensive.

### 4. **Missing Red Flag Questions**
ML model has 2 red flags not in current safety screening:
- `flag_vomiting_blood_or_blood_in_stool`
- `flag_severe_dehydration`

**Question**: Should we add these 2 to the safety checklist (12 total instead of 10)?

**Recommendation**: **YES** - Add these for completeness. Update safety screening to 12 questions.

### 5. **Model Output Interpretation**
ML model predicts: **"Is ED visit avoidable?"** (YES/NO)
- YES = Patient can use telemedicine/urgent care instead
- NO = Patient should go to ED

This is AFTER safety screening already said "not emergency".

**Question**: What should the UI show?
- Safety = NO (not emergency) + ED Avoidable = YES → "Use telemedicine or urgent care"
- Safety = NO (not emergency) + ED Avoidable = NO → "Go to ED for evaluation"

**Recommendation**: Show both results clearly with guidance.

### 6. **Feature Engineering Location**
Where should feature engineering happen?

**Options**:
- **Option A**: In ML service (keeps ML logic together)
- **Option B**: Separate mapper service (cleaner separation)
- **Option C**: In API endpoint (quick but messy)

**Recommendation**: **Option B** - Separate `EDFeatureMapper` service for reusability and testing.

---

## 📝 Implementation Checklist

### Phase 1: Data Collection ✅
- [ ] Add 4 new intake questions to `vocabulary.py`
- [ ] Update `REQUIRED_FIELD_ORDER` to include new fields
- [ ] Add 2 new red flag questions to safety screening UI
- [ ] Update `safety_rules.json` with new rules

### Phase 2: Feature Mapping ✅
- [ ] Create `app/services/ed_feature_mapper.py`
- [ ] Implement `EDFeatureMapper.build_ml_features()`
- [ ] Add symptom category classification logic
- [ ] Add onset time classification logic
- [ ] Test with sample data

### Phase 3: ML Service ✅
- [ ] Create `app/services/ed_prediction_service.py`
- [ ] Load model on startup
- [ ] Implement prediction function
- [ ] Add error handling for missing model file

### Phase 4: API Endpoints ✅
- [ ] Add `/patient/ed-prediction` POST endpoint
- [ ] Create request/response Pydantic models
- [ ] Add endpoint to API router
- [ ] Test with Postman/curl

### Phase 5: UI Integration ✅
- [ ] Update `chatbot_ui.py` verdict phase
- [ ] Add ED prediction API call
- [ ] Display results with recommendations
- [ ] Add loading spinners

### Phase 6: EHR Updates (Optional) ⚠️
- [ ] Add `pain_score_clinical` field to EHR schema
- [ ] Add `has_pcp_flag` field to EHR schema
- [ ] Run database migration
- [ ] Update EHR CRUD endpoints

### Phase 7: Testing 🧪
- [ ] Unit test `EDFeatureMapper`
- [ ] Unit test `EDPredictionService`
- [ ] Integration test full flow
- [ ] Test with patient WITH EHR
- [ ] Test with patient WITHOUT EHR
- [ ] Test edge cases (missing data)

### Phase 8: Documentation 📚
- [ ] Document new API endpoints
- [ ] Update README with ED integration
- [ ] Document feature mapping logic
- [ ] Add example API calls

---

## 🎯 Expected Timeline

| Phase | Estimated Time | Status |
|-------|----------------|--------|
| Phase 1: Data Collection | 2 hours | ⏳ Pending |
| Phase 2: Feature Mapping | 3 hours | ⏳ Pending |
| Phase 3: ML Service | 2 hours | ⏳ Pending |
| Phase 4: API Endpoints | 2 hours | ⏳ Pending |
| Phase 5: UI Integration | 2 hours | ⏳ Pending |
| Phase 6: EHR Updates | 3 hours | ⏳ Optional |
| Phase 7: Testing | 4 hours | ⏳ Pending |
| Phase 8: Documentation | 2 hours | ⏳ Pending |
| **Total** | **20 hours** | - |

---

## ⚠️ Known Issues and Risks

### 1. **Model File Location**
- Current: `ML_Complete_Package/best_avoidable_ed_model.pkl`
- Must be accessible from FastAPI app
- **Solution**: Copy to `app/ml_models/` or use absolute path

### 2. **Feature Count Mismatch**
- Model trained on 95 features (after feature engineering + selection)
- Must ensure exact same features in exact same order
- **Solution**: Use `model_bundle['feature_columns']` list from pickle

### 3. **Categorical Encoding**
- Model expects encoded categorical values
- Must use same LabelEncoders from training
- **Solution**: Encoders saved in `model_bundle['categorical_encoders']`

### 4. **Missing Data Handling**
- Patients without EHR → use defaults
- Missing lab values → use population averages
- **Solution**: Implemented in `EDFeatureMapper.build_ml_features()`

### 5. **Performance**
- Loading pickle model on every prediction is slow
- **Solution**: Load once on startup, cache in memory

---

## 🔄 Future Enhancements

1. **Active Learning**: Collect feedback on predictions to improve model
2. **Real-time Vitals**: Integrate with wearables for live vital signs
3. **Multi-language**: Support intake in multiple languages
4. **Voice Input**: Allow voice responses for accessibility
5. **Provider Integration**: Send predictions to care team dashboard
6. **Cost Estimation**: Show estimated cost savings from avoided ED visits
7. **Follow-up Tracking**: Monitor outcomes of avoidable ED predictions

---

## 📞 Next Steps

Please review this plan and answer the **6 Critical Questions** above. Once clarified, I will:

1. ✅ Implement Phase 1-5 (core integration)
2. ✅ Create test scripts
3. ✅ Update documentation
4. ✅ Provide deployment instructions

---

**Created**: January 2027  
**Status**: 🟡 Awaiting Clarification  
**Priority**: 🔴 High
