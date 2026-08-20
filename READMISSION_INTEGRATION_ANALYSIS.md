# Readmission Model Integration Analysis

## Model Information
- **Model Type**: Logistic Regression
- **Purpose**: Predict 30-day hospital readmission risk
- **Total Features**: 25 features
- **Model Version**: 2.0
- **Training Date**: 2026-08-11
- **Performance**: 
  - Accuracy: 81.9%
  - AUC-ROC: 0.806
  - F1-Score: 0.409

## Required Features for Readmission Model

### ✅ AVAILABLE in Current EHR Schema (25/25 = 100%)

| Feature Name | EHR Field | Type | Notes |
|--------------|-----------|------|-------|
| **Demographics** |
| `num__age` | `age` | Integer | ✅ Available |
| **Chronic Conditions** |
| `num__comorbidity_index` | `charlson_comorbidity_index` | Integer | ✅ Available (needs mapping) |
| `num__diabetes_flag` | `diabetes_flag` | Integer (0/1) | ✅ Available |
| `num__heart_failure_flag` | `heart_failure_flag` | Integer (0/1) | ✅ Available |
| `num__copd_flag` | `copd_asthma_flag` | Integer (0/1) | ✅ Available |
| `num__ckd_flag` | `ckd_flag` | Integer (0/1) | ✅ Available |
| `num__dementia_flag` | `dementia_flag` | Integer (0/1) | ✅ Available |
| **Lab Values** |
| `num__hemoglobin` | `hemoglobin` | Float | ✅ Available |
| `num__creatinine` | `creatinine` | Float | ✅ Available |
| `num__glucose` | `glucose` | Integer | ✅ Available |
| **Utilization History** |
| `num__previous_admissions_12m` | `previous_admissions_12m` | Integer | ✅ Available |
| `num__previous_er_visits_12m` | `previous_er_visits_12m` | Integer | ✅ Available |
| `num__prior_30_day_readmission_flag` | `prior_30_day_readmission_flag` | Integer (0/1) | ✅ Available |
| **Admission Data** |
| `num__length_of_stay_days` | `length_of_stay_days` | Integer | ✅ Available |
| `num__icu_stay_flag` | `icu_stay_flag` | Integer (0/1) | ✅ Available |
| `num__follow_up_within_7_days_flag` | `follow_up_within_7_days_flag` | Integer (0/1) | ✅ Available |
| `num__total_charges_index_stay` | `total_charges_index_stay` | Float | ✅ Available |
| **Medications** |
| `num__medication_count_at_discharge` | `medication_count_at_discharge` | Integer | ✅ Available |
| `num__polypharmacy_flag` | `polypharmacy_flag` | Integer (0/1) | ✅ Available |
| `num__high_risk_medication_flag` | `high_risk_medication_flag` | Integer (0/1) | ✅ Available |
| **Categorical Features** |
| `cat__insurance_type_Medicare` | `insurance_type` | String | ✅ One-hot encode |
| `cat__insurance_type_Private` | `insurance_type` | String | ✅ One-hot encode |
| `cat__admission_type_emergency` | `admission_type` | String | ✅ One-hot encode |
| `cat__discharge_destination_nursing_home` | `discharge_destination` | String | ✅ One-hot encode |
| `cat__discharge_destination_rehab` | `discharge_destination` | String | ✅ One-hot encode |

## Feature Mapping Notes

### 1. Comorbidity Index
- **Model expects**: `num__comorbidity_index`
- **EHR has**: `charlson_comorbidity_index`
- **Action**: Direct mapping (same field)

### 2. COPD Flag
- **Model expects**: `num__copd_flag`
- **EHR has**: `copd_asthma_flag` (combined COPD/Asthma)
- **Action**: Use `copd_asthma_flag` directly

### 3. Categorical Variables (One-Hot Encoding)
The model expects specific one-hot encoded columns:
- `insurance_type`: Create `Medicare` and `Private` dummy columns
- `admission_type`: Create `emergency` dummy column
- `discharge_destination`: Create `nursing_home` and `rehab` dummy columns

## Integration Requirements

### Two Trigger Points

#### 1. **Automatic Trigger: When Patient EHR is Created**
- **Location**: Patient creation endpoint
- **Trigger**: POST `/api/v1/ehr/` or similar patient creation endpoint
- **Action**: Automatically run readmission prediction after EHR creation
- **Store**: Save prediction result in database

#### 2. **Manual Trigger: On-Demand Prediction**
- **Location**: Patient profile/dashboard
- **Trigger**: POST `/api/v1/patient/{patient_id}/readmission-prediction`
- **Action**: Run prediction on latest EHR data
- **Return**: Fresh prediction result

### Implementation Components

#### 1. **Readmission Feature Mapper Service**
- Map EHR fields to 25 model features
- Handle one-hot encoding for categorical variables
- Handle missing values (if any)

#### 2. **Readmission Prediction Service**
- Load the trained model (best_model.pkl)
- Accept EHR data
- Return prediction probability and risk level

#### 3. **Readmission Result Storage**
- Store prediction results in database
- Track prediction history
- Associate with patient_id and timestamp

#### 4. **API Endpoints**
- `POST /api/v1/patient/{patient_id}/readmission-prediction` - Manual prediction
- `GET /api/v1/patient/{patient_id}/readmission-history` - Get prediction history

#### 5. **Background Task Integration**
- Hook into patient creation flow
- Automatically trigger prediction after EHR creation

## Questions & Clarifications

### ✅ Resolved
1. **All 25 features are available in current EHR schema** ✅
2. **No missing fields** ✅
3. **Data types match** ✅

### ⚠️ Clarifications Needed

1. **Prediction Storage**
   - Should we store prediction results in a separate `readmission_predictions` table?
   - What fields should we store? (prediction_probability, risk_level, predicted_at, etc.)

2. **Risk Level Classification**
   - How should we classify risk levels from probability?
     - Low Risk: < 30%?
     - Medium Risk: 30-60%?
     - High Risk: > 60%?

3. **Automatic Prediction on EHR Creation**
   - Should prediction run immediately after EHR creation?
   - Or should it run as a background async task?
   - What if prediction fails? Retry logic?

4. **Missing Data Handling**
   - Some fields are optional (e.g., `medication_count_at_discharge`)
   - Should we use default values (e.g., 0) or handle differently?

5. **Model File Location**
   - Current: `/ML_Complete_Package/data/best_model.pkl` (23.6 MB)
   - Should move to: `app/ml_models/best_readmission_model.pkl`?

6. **Prediction Update Frequency**
   - If EHR data changes (e.g., new lab results), should we auto-rerun prediction?
   - Or only on manual request?

## Recommended Implementation Order

1. ✅ **Analysis Complete** - Verify all features available
2. **Create Database Schema** - `readmission_predictions` table
3. **Readmission Feature Mapper** - Map EHR → Model features
4. **Readmission Prediction Service** - Load model, make predictions
5. **API Endpoint** - Manual prediction trigger
6. **Auto-trigger Integration** - Hook into patient creation
7. **Testing** - End-to-end integration tests
8. **Documentation** - API docs and usage guide

## Next Steps

Please confirm:
1. Risk level thresholds (Low/Medium/High)
2. Prediction storage structure
3. Auto-prediction timing (immediate vs async)
4. Missing data handling strategy

Once confirmed, I'll proceed with the implementation.
