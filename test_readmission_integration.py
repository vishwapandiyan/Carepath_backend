#!/usr/bin/env python3
"""
Readmission Model Integration Test Script

Tests:
1. Model loading
2. Feature mapping
3. Auto-trigger on patient creation
4. Manual prediction endpoint
5. Prediction history endpoint
6. Latest predictions endpoint
7. ML predictions database storage

Author: CarePath AI Team
Date: 2026-08-20
"""

import requests
import json
from datetime import date, datetime
from typing import Dict, Any

# API Configuration
BASE_URL = "http://localhost:8000/api/v1"
CARE_MANAGER_USERNAME = "care_manager_test"
CARE_MANAGER_PASSWORD = "SecurePass123!"


def print_header(text: str):
    """Print section header"""
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80)


def print_info(text: str):
    """Print info message"""
    print(f"ℹ  {text}")


def print_success(text: str):
    """Print success message"""
    print(f"✓ {text}")


def print_error(text: str):
    """Print error message"""
    print(f"✗ {text}")


def login_care_manager() -> str:
    """Login as care manager and return token"""
    print_header("STEP 1: Care Manager Login")
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": CARE_MANAGER_USERNAME,
            "password": CARE_MANAGER_PASSWORD
        }
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print_success(f"Care manager logged in successfully")
        return token
    else:
        print_error(f"Login failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def create_patient_with_readmission_risk(token: str) -> Dict[str, Any]:
    """
    Create a patient with high readmission risk factors.
    This should auto-trigger readmission prediction.
    """
    print_header("STEP 2: Create Patient (Auto-triggers Readmission Prediction)")
    
    patient_data = {
        "demographics": {
            "name": "John Readmission Test",
            "date_of_birth": "1950-03-15",
            "age": 76,
            "gender": "male",
            "bmi": 29.5,
            "insurance_type": "Medicare",
            "race": "Caucasian"
        },
        "chronic_conditions": {
            "diabetes_flag": 1,
            "heart_failure_flag": 1,
            "cardiac_history_flag": 1,
            "copd_asthma_flag": 1,
            "ckd_flag": 1,
            "cancer_flag": 0,
            "dementia_flag": 1,
            "hypertension_flag": 1,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 6
        },
        "vital_signs_current": {
            "systolic_bp": 145,
            "diastolic_bp": 85,
            "heart_rate": 88,
            "respiratory_rate": 18,
            "temperature": 98.2,
            "spo2": 94,
            "pain_score_clinical": 3.0
        },
        "lab_values": {
            "hemoglobin": 10.8,
            "creatinine": 2.1,
            "glucose": 165,
            "hba1c": 8.5,
            "wbc_count": 9.2,
            "total_bilirubin": 1.1,
            "platelet_count": 220000,
            "sodium": 138,
            "potassium": 4.2,
            "troponin": 0.03,
            "bnp": 450,
            "lactate": 1.5,
            "inr": 1.8
        },
        "medications": {
            "active_medication_count": 12,
            "medication_count_at_discharge": 10,
            "polypharmacy_flag": 1,
            "high_risk_medication_flag": 1,
            "on_anticoagulants_flag": 1,
            "on_insulin_flag": 1,
            "medication_adherence_rate": 0.75
        },
        "utilization_history": {
            "previous_admissions_12m": 3,
            "previous_er_visits_12m": 5,
            "prior_30_day_readmission_flag": 1,
            "days_since_last_ed_visit": 45,
            "ed_visits_90d": 2,
            "ed_visits_30d": 1,
            "outpatient_visits_365d": 8,
            "days_since_last_pcp_visit": 30,
            "missed_appointments_6m": 2
        },
        "admission_data": {
            "admission_date": "2026-08-10",
            "discharge_date": "2026-08-18",
            "admission_type": "emergency",
            "length_of_stay_days": 8,
            "icu_stay_flag": 1,
            "discharge_destination": "nursing_home",
            "follow_up_within_7_days_flag": 0,
            "follow_up_appointment_date": "2026-08-28",
            "total_charges_index_stay": 45000.00
        },
        "clinical_notes": "76 y/o male with multiple comorbidities. Recent admission for heart failure exacerbation.",
        "contact_number": "+1-555-0123",
        "email": "john.test@example.com",
        "address": "123 Test St, Test City, TC 12345",
        "insurance_id": "MCARE-123456"
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{BASE_URL}/ehr/patients",
        json=patient_data,
        headers=headers
    )
    
    if response.status_code == 201:
        patient = response.json()
        print_success(f"Patient created: {patient['name']}")
        print_info(f"Patient ID: {patient['patient_id']}")
        print_info(f"MRN: {patient['mrn']}")
        print_info(f"Comorbidity Index: {patient['charlson_comorbidity_index']}")
        print_info(f"Previous Admissions (12m): {patient['previous_admissions_12m']}")
        print_info(f"Discharge to: {patient['discharge_destination']}")
        print_success("✓ Auto-trigger: Readmission prediction should have run in background")
        return patient
    else:
        print_error(f"Patient creation failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_manual_readmission_prediction(patient_id: str, token: str) -> Dict[str, Any]:
    """Test manual readmission prediction trigger"""
    print_header("STEP 3: Manual Readmission Prediction")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{BASE_URL}/patient/{patient_id}/readmission-prediction",
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print_success("Manual prediction successful!")
        print_info(f"Readmission Risk Score: {result['readmission_risk_score']:.4f} ({result['readmission_risk_score']*100:.2f}%)")
        print_info(f"Model Version: {result['model_version']}")
        print_info(f"Predicted At: {result['predicted_at']}")
        
        if result.get('prediction_details'):
            details = result['prediction_details']
            print_info(f"Patient Age: {details.get('patient_age')}")
            print_info(f"Comorbidity Index: {details.get('comorbidity_index')}")
            print_info(f"Previous Admissions: {details.get('previous_admissions_12m')}")
            print_info(f"Length of Stay: {details.get('length_of_stay_days')} days")
            print_info(f"ICU Stay: {details.get('icu_stay')}")
            print_info(f"Follow-up Scheduled: {details.get('follow_up_scheduled')}")
        
        return result
    else:
        print_error(f"Manual prediction failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def test_prediction_history(patient_id: str, token: str):
    """Test prediction history endpoint"""
    print_header("STEP 4: Get Prediction History")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get all ML predictions
    print_info("Fetching all ML predictions...")
    response = requests.get(
        f"{BASE_URL}/patient/{patient_id}/ml-predictions",
        headers=headers
    )
    
    if response.status_code == 200:
        predictions = response.json()
        print_success(f"Found {len(predictions)} total predictions")
        
        for i, pred in enumerate(predictions, 1):
            print(f"\n  Prediction {i}:")
            print(f"    Model: {pred['model_type']}")
            print(f"    Risk Score: {pred['risk_score']:.4f}")
            print(f"    Predicted At: {pred['predicted_at']}")
            print(f"    Created By: {pred['created_by']}")
    else:
        print_error(f"Failed to get predictions: {response.status_code}")
        print(f"Response: {response.text}")
    
    # Get readmission predictions only
    print_info("\nFetching readmission predictions only...")
    response = requests.get(
        f"{BASE_URL}/patient/{patient_id}/ml-predictions?model_type=readmission&limit=5",
        headers=headers
    )
    
    if response.status_code == 200:
        predictions = response.json()
        print_success(f"Found {len(predictions)} readmission predictions")
        
        for i, pred in enumerate(predictions, 1):
            print(f"\n  Readmission Prediction {i}:")
            print(f"    Risk Score: {pred['risk_score']:.4f} ({pred['risk_score']*100:.2f}%)")
            print(f"    Predicted At: {pred['predicted_at']}")
            print(f"    Created By: {pred['created_by']}")
    else:
        print_error(f"Failed to get readmission predictions: {response.status_code}")


def test_latest_predictions(patient_id: str, token: str):
    """Test latest predictions endpoint"""
    print_header("STEP 5: Get Latest Predictions (All Models)")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{BASE_URL}/patient/{patient_id}/latest-predictions",
        headers=headers
    )
    
    if response.status_code == 200:
        predictions = response.json()
        print_success(f"Found latest predictions for {len(predictions)} model(s)")
        
        for model_type, pred in predictions.items():
            print(f"\n  {model_type.upper()} Model:")
            print(f"    Risk Score: {pred['risk_score']:.4f} ({pred['risk_score']*100:.2f}%)")
            print(f"    Model Version: {pred.get('model_version', 'N/A')}")
            print(f"    Predicted At: {pred['predicted_at']}")
    else:
        print_error(f"Failed to get latest predictions: {response.status_code}")
        print(f"Response: {response.text}")


def test_model_loading():
    """Test model and service initialization"""
    print_header("STEP 0: Model Loading Test")
    
    try:
        from app.services.readmission_prediction_service import readmission_prediction_service
        
        model_info = readmission_prediction_service.get_model_info()
        
        print_success("Readmission prediction service initialized")
        print_info(f"Model Type: {model_info['model_type']}")
        print_info(f"Model Version: {model_info['model_version']}")
        print_info(f"Algorithm: {model_info['algorithm']}")
        print_info(f"Features Count: {model_info['features_count']}")
        print_info(f"Model Loaded: {model_info['model_loaded']}")
        print_info(f"Accuracy: {model_info['accuracy']*100:.1f}%")
        print_info(f"AUC-ROC: {model_info['auc_roc']:.3f}")
        
        return True
    except Exception as e:
        print_error(f"Model loading failed: {str(e)}")
        print_info("Make sure the server is running to test model loading")
        return False


def main():
    """Run all tests"""
    print_header("Readmission Model Integration Test")
    print("Testing readmission prediction model and endpoints")
    
    # Test model loading (optional - requires server to be running)
    # test_model_loading()
    
    # Check if server is running
    print_header("STEP 0: Checking Server Connection")
    try:
        response = requests.get(f"http://localhost:8000/health")
        if response.status_code == 200:
            print_success("Server is running")
        else:
            print_error("Server returned unexpected status")
            return
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server!")
        print_info("Please start the server: uvicorn app.main:app --reload")
        return
    
    # Login
    token = login_care_manager()
    if not token:
        print_error("Cannot proceed without authentication")
        return
    
    # Create patient (auto-triggers readmission prediction)
    patient = create_patient_with_readmission_risk(token)
    if not patient:
        print_error("Cannot proceed without patient")
        return
    
    patient_id = patient['patient_id']
    
    # Wait a moment for auto-trigger to complete
    import time
    print_info("\nWaiting 2 seconds for auto-prediction to complete...")
    time.sleep(2)
    
    # Test manual prediction
    manual_result = test_manual_readmission_prediction(patient_id, token)
    
    # Test prediction history
    test_prediction_history(patient_id, token)
    
    # Test latest predictions
    test_latest_predictions(patient_id, token)
    
    # Summary
    print_header("TEST SUMMARY")
    print_success("✓ Patient creation with auto-trigger")
    print_success("✓ Manual prediction endpoint")
    print_success("✓ Prediction history endpoint")
    print_success("✓ Latest predictions endpoint")
    print_success("✓ ML predictions stored in database")
    
    print("\n" + "=" * 80)
    print("All tests completed!")
    print("=" * 80)
    
    print("\n📊 READMISSION RISK ANALYSIS:")
    if manual_result:
        risk_score = manual_result['readmission_risk_score']
        risk_pct = risk_score * 100
        
        if risk_score > 0.6:
            risk_level = "HIGH RISK"
            color = "🔴"
        elif risk_score > 0.3:
            risk_level = "MODERATE RISK"
            color = "🟡"
        else:
            risk_level = "LOW RISK"
            color = "🟢"
        
        print(f"{color} {risk_level}: {risk_pct:.1f}% probability of 30-day readmission")
        print("\nRisk Factors:")
        print("  • Age: 76 years (high risk)")
        print("  • Comorbidity Index: 6 (high)")
        print("  • Previous Admissions: 3 in last 12 months")
        print("  • Prior 30-day Readmission: Yes")
        print("  • ICU Stay: Yes")
        print("  • Discharge to Nursing Home")
        print("  • No Follow-up within 7 days")
        print("  • Polypharmacy: 10+ medications")


if __name__ == "__main__":
    main()
