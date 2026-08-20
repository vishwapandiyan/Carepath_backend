# Readmission Model Integration - Complete ✅

## Overview

Successfully integrated the **30-Day Hospital Readmission Risk Prediction** model into the CarePath AI backend.

**Model Details:**
- Type: Logistic Regression
- Features: 25 (20 numerical + 5 categorical one-hot encoded)
- Performance: 81.9% accuracy, 0.806 AUC-ROC
- Version: 2.0

## Integration Summary

### ✅ Completed Components

#### 1. **Database Model** (`app/models/ml_predictions.py`)
- `ml_predictions` table stores all ML predictions
- Supports multiple model types (readmission, ed_avoidable, future models)
- Fields: id, patient_id, mrn, model_type, risk_score, prediction_result (JSON), predicted_at
- Composite indexes for efficient queries

#### 2. **Feature Mapper** (`app/services/readmission_feature_mapper.py`)
- Maps EHR data → 25 model features
- Handles one-hot encoding for categorical variables:
  - insurance_type (Medicare, Private)
  - admission_type (emergency)
  - discharge_destination (nursing_home, rehab)
- Handles missing values with defaults

#### 3. **Prediction Service** (`app/services/readmission_prediction_service.py`)
- Loads model from `app/ml_models/best_readmission_model.pkl`
- Makes predictions using EHR data
- Returns risk score (0.0 to 1.0)
- Includes prediction metadata

#### 4. **ML Predictions CRUD Service** (`app/services/ml_predictions_service.py`)
- Store/retrieve predictions from database
- Query prediction history
- Get latest prediction by model type
- Get all predictions for a patient

#### 5. **Auto-Trigger Integration** (`app/services/ehr_crud_service.py`)
- **Automatic prediction** when patient EHR is created
- Runs immediately after patient creation
- Stores prediction in database
- Non-blocking: patient creation succeeds even if prediction fails

#### 6. **API Endpoints** (`app/api/v1/endpoints/patient.py`)
Three new endpoints:

a. **Manual Prediction Trigger**
```
POST /api/v1/patient/{patient_id}/readmission-prediction
```
- Triggered from patient profile "Predict" button
- Uses latest EHR data
- Returns risk score + details
- Stores prediction in database

b. **Prediction History**
```
GET /api/v1/patient/{patient_id}/ml-predictions?model_type=readmission&limit=10
```
- Get historical predictions
- Optional filter by model type
- Paginated results

c. **Latest Predictions**
```
GET /api/v1/patient/{patient_id}/latest-predictions
```
- Get latest prediction for each model type
- Returns all ML risk scores for patient profile

#### 7. **Database Migration** (`migrations/create_ml_predictions_table.sql`)
- SQL script to create ml_predictions table
- Indexes for performance
- Foreign key constraints

## Feature Mapping

All 25 required features are available in EHR schema:

| Category | Features | Source |
|----------|----------|--------|
| Demographics | age | ehr.age |
| Comorbidities | diabetes, heart_failure, copd, ckd, dementia | ehr flags |
| Comorbidity Index | charlson_comorbidity_index | ehr.charlson_comorbidity_index |
| Lab Values | hemoglobin, creatinine, glucose | ehr lab values |
| Utilization | previous_admissions_12m, previous_er_visits_12m | ehr utilization |
| Admission Data | length_of_stay, icu_stay, follow_up | ehr admission_data |
| Medications | medication_count, polypharmacy, high_risk | ehr medications |
| Charges | total_charges_index_stay | ehr.total_charges_index_stay |
| Categorical | insurance_type, admission_type, discharge_destination | one-hot encoded |

## Integration Points

### Two Trigger Mechanisms

#### 1. **Automatic Trigger** ✅
**When:** Patient EHR is created
**Endpoint:** `POST /api/v1/ehr/patients`
**Flow:**
```
Care Manager creates patient
    ↓
EHR record saved to database
    ↓
Auto-trigger readmission prediction
    ↓
Store prediction in ml_predictions table
    ↓
Return patient EHR response
```

**Implementation:**
- Hooked into `ehr_crud_service.create_patient_ehr()`
- Runs synchronously after patient creation
- Non-blocking: logs error if prediction fails
- Creates prediction with `created_by="system_auto"`

#### 2. **Manual Trigger** ✅
**When:** User clicks "Predict" in patient profile
**Endpoint:** `POST /api/v1/patient/{patient_id}/readmission-prediction`
**Flow:**
```
User clicks "Predict" button
    ↓
API call with patient_id
    ↓
Fetch latest EHR data
    ↓
Make readmission prediction
    ↓
Store prediction in database
    ↓
Return risk score + details
```

**Implementation:**
- Dedicated API endpoint
- Creates prediction with `created_by="manual_trigger"`
- Returns risk score and prediction details

## API Examples

### 1. Create Patient (Auto-triggers Prediction)

**Request:**
```bash
POST /api/v1/ehr/patients
Authorization: Bearer {care_manager_token}
Content-Type: application/json

{
  "demographics": {
    "name": "John Doe",
    "date_of_birth": "1950-05-15",
    "age": 76,
    "gender": "male",
    "bmi": 28.5,
    "insurance_type": "Medicare"
  },
  "chronic_conditions": {
    "diabetes_flag": 1,
    "heart_failure_flag": 1,
    "charlson_comorbidity_index": 5
  },
  "lab_values": {
    "hemoglobin": 11.2,
    "creatinine": 1.8,
    "glucose": 145,
    "wbc_count": 8.5
  },
  "utilization_history": {
    "previous_admissions_12m": 2,
    "previous_er_visits_12m": 3,
    "prior_30_day_readmission_flag": 1
  },
  "admission_data": {
    "admission_type": "emergency",
    "length_of_stay_days": 5,
    "icu_stay_flag": 1,
    "discharge_destination": "home",
    "follow_up_within_7_days_flag": 1,
    "total_charges_index_stay": 25000.00
  },
  "medications": {
    "medication_count_at_discharge": 8,
    "polypharmacy_flag": 1,
    "high_risk_medication_flag": 1
  }
}
```

**Response:**
```json
{
  "id": 1,
  "patient_id": "PAT_A1B2C3D4",
  "mrn": "MRN12345678",
  "name": "John Doe",
  "age": 76,
  // ... full EHR data ...
}
```

**Background:** Readmission prediction automatically triggered and stored in database.

### 2. Manual Prediction Trigger

**Request:**
```bash
POST /api/v1/patient/PAT_A1B2C3D4/readmission-prediction
```

**Response:**
```json
{
  "readmission_risk_score": 0.68,
  "predicted_at": "2026-08-20T15:30:00Z",
  "model_version": "2.0",
  "prediction_details": {
    "features_used": 25,
    "patient_age": 76,
    "comorbidity_index": 5,
    "previous_admissions_12m": 2,
    "length_of_stay_days": 5,
    "icu_stay": true,
    "follow_up_scheduled": true
  }
}
```

### 3. Get Prediction History

**Request:**
```bash
GET /api/v1/patient/PAT_A1B2C3D4/ml-predictions?model_type=readmission&limit=5
```

**Response:**
```json
[
  {
    "id": 15,
    "patient_id": "PAT_A1B2C3D4",
    "mrn": "MRN12345678",
    "model_type": "readmission",
    "model_version": "2.0",
    "risk_score": 0.68,
    "prediction_result": {
      "features_used": 25,
      "patient_age": 76,
      "comorbidity_index": 5
    },
    "predicted_at": "2026-08-20T15:30:00Z",
    "created_by": "manual_trigger"
  },
  {
    "id": 1,
    "patient_id": "PAT_A1B2C3D4",
    "mrn": "MRN12345678",
    "model_type": "readmission",
    "model_version": "2.0",
    "risk_score": 0.65,
    "prediction_result": {
      "features_used": 25,
      "patient_age": 76,
      "comorbidity_index": 5
    },
    "predicted_at": "2026-08-20T10:00:00Z",
    "created_by": "system_auto"
  }
]
```

### 4. Get Latest Predictions (All Models)

**Request:**
```bash
GET /api/v1/patient/PAT_A1B2C3D4/latest-predictions
```

**Response:**
```json
{
  "readmission": {
    "id": 15,
    "risk_score": 0.68,
    "model_version": "2.0",
    "predicted_at": "2026-08-20T15:30:00Z",
    "prediction_result": {...}
  },
  "ed_avoidable": {
    "id": 8,
    "risk_score": 0.42,
    "model_version": "1.0",
    "predicted_at": "2026-08-19T14:20:00Z",
    "prediction_result": {...}
  }
}
```

## Files Created/Modified

### New Files (8)
1. `app/models/ml_predictions.py` - Database model
2. `app/schemas/ml_predictions.py` - Pydantic schemas
3. `app/services/readmission_feature_mapper.py` - Feature mapping
4. `app/services/readmission_prediction_service.py` - Prediction service
5. `app/services/ml_predictions_service.py` - CRUD service
6. `app/ml_models/best_readmission_model.pkl` - ML model file (23.6 MB)
7. `migrations/create_ml_predictions_table.sql` - Database migration
8. `READMISSION_INTEGRATION_COMPLETE.md` - This documentation

### Modified Files (3)
1. `app/services/ehr_crud_service.py` - Added auto-trigger for readmission prediction
2. `app/api/v1/endpoints/patient.py` - Added 3 new API endpoints
3. `app/models/__init__.py` - Added MLPrediction import

## Database Schema

```sql
CREATE TABLE ml_predictions (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    mrn VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,  -- 'readmission', 'ed_avoidable', etc.
    model_version VARCHAR(20),
    risk_score FLOAT NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    prediction_result JSONB,  -- Additional details
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50),  -- 'system_auto' or 'manual_trigger'
    
    FOREIGN KEY (patient_id) REFERENCES patient_ehr(patient_id)
);

-- Indexes
CREATE INDEX idx_ml_predictions_patient_id ON ml_predictions(patient_id);
CREATE INDEX idx_ml_predictions_mrn ON ml_predictions(mrn);
CREATE INDEX idx_ml_predictions_model_type ON ml_predictions(model_type);
CREATE INDEX idx_ml_predictions_patient_model_time ON ml_predictions(patient_id, model_type, predicted_at DESC);
```

## Testing

### Manual Testing Steps

1. **Test Auto-Trigger:**
   ```bash
   # Create a patient (triggers automatic prediction)
   POST /api/v1/ehr/patients
   
   # Check logs for: "Auto-triggering readmission prediction for patient PAT_XXXXXXXX"
   # Check database: SELECT * FROM ml_predictions WHERE created_by='system_auto'
   ```

2. **Test Manual Trigger:**
   ```bash
   # Manually trigger prediction
   POST /api/v1/patient/PAT_XXXXXXXX/readmission-prediction
   
   # Verify response contains risk_score
   # Check database: SELECT * FROM ml_predictions WHERE created_by='manual_trigger'
   ```

3. **Test Prediction History:**
   ```bash
   # Get prediction history
   GET /api/v1/patient/PAT_XXXXXXXX/ml-predictions?model_type=readmission
   
   # Verify returns list of predictions ordered by predicted_at DESC
   ```

4. **Test Latest Predictions:**
   ```bash
   # Get latest predictions for all models
   GET /api/v1/patient/PAT_XXXXXXXX/latest-predictions
   
   # Verify returns latest prediction for each model_type
   ```

## Next Steps

### To Deploy:

1. **Run Database Migration:**
   ```bash
   psql -U carepath_user -d carepath_db -f migrations/create_ml_predictions_table.sql
   ```

2. **Verify Model File:**
   ```bash
   ls -lh app/ml_models/best_readmission_model.pkl
   # Should show ~23.6 MB
   ```

3. **Start Server:**
   ```bash
   uvicorn app.main:app --reload
   ```

4. **Test Endpoints:**
   - Use provided API examples above
   - Check logs for prediction results

### Future Enhancements:

1. Add ED Avoidable predictions to `ml_predictions` table
2. Add risk stratification thresholds (Low/Medium/High)
3. Add prediction confidence intervals
4. Add model retraining pipeline
5. Add prediction audit trail
6. Add patient risk dashboard

## Model Performance

- **Accuracy:** 81.9%
- **AUC-ROC:** 0.806
- **F1-Score:** 0.409
- **Precision:** 0.653
- **Recall:** 0.297

## Top Risk Factors

1. Discharge to rehab/nursing home
2. Age
3. Comorbidity index
4. Previous admissions (12 months)
5. Heart failure
6. Chronic kidney disease

## Support

For questions or issues:
- Check logs: `tail -f logs/app.log`
- Database queries: `SELECT * FROM ml_predictions ORDER BY predicted_at DESC LIMIT 10`
- Model info: `readmission_prediction_service.get_model_info()`
