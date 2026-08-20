#!/usr/bin/env python3
"""
Setup Test Data Script
Creates a Care Manager and a Patient with complete EHR data for testing
"""
import requests
import json
from datetime import date, timedelta

BASE_URL = "http://localhost:8000"

def print_header(title):
    print("\n" + "="*80)
    print(title.center(80))
    print("="*80)

def print_success(message):
    print(f"✓ {message}")

def print_error(message):
    print(f"✗ {message}")

def create_care_manager():
    print_header("STEP 1: Create Care Manager")
    
    care_manager_data = {
        "username": "care_manager_test",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/signup/care-manager",
            json=care_manager_data
        )
        
        if response.status_code == 201:
            print_success("Care Manager created successfully")
            print(f"   Username: {care_manager_data['username']}")
            print(f"   Password: {care_manager_data['password']}")
            return {"username": care_manager_data["username"], "password": care_manager_data["password"]}
        elif response.status_code == 400 and "already exists" in response.text:
            print_success("Care Manager already exists (using existing)")
            print(f"   Username: {care_manager_data['username']}")
            print(f"   Password: {care_manager_data['password']}")
            return {"username": care_manager_data["username"], "password": care_manager_data["password"]}
        else:
            print_error(f"Failed to create Care Manager: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error creating Care Manager: {str(e)}")
        return None

def login_care_manager(credentials):
    print_header("STEP 2: Login as Care Manager")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json=credentials
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print_success("Care Manager logged in successfully")
            print(f"   Token: {token[:50]}...")
            return token
        else:
            print_error(f"Login failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error during login: {str(e)}")
        return None

def create_patient_ehr(token):
    print_header("STEP 3: Create Patient with Complete EHR Data")
    
    # Calculate dates
    dob = date.today() - timedelta(days=365*65)  # 65 years old
    admission_date = date.today() - timedelta(days=5)
    discharge_date = date.today() - timedelta(days=2)
    followup_date = date.today() + timedelta(days=5)
    
    patient_ehr_data = {
        "demographics": {
            "name": "Test Patient",
            "date_of_birth": str(dob),
            "age": 65,
            "gender": "male",
            "bmi": 28.5,
            "insurance_type": "Medicare",
            "race": "Caucasian"
        },
        "chronic_conditions": {
            "diabetes_flag": 1,
            "heart_failure_flag": 1,
            "cardiac_history_flag": 0,
            "copd_asthma_flag": 1,
            "ckd_flag": 0,
            "cancer_flag": 0,
            "dementia_flag": 0,
            "hypertension_flag": 1,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 5
        },
        "vital_signs_current": {
            "systolic_bp": 145,
            "diastolic_bp": 90,
            "heart_rate": 88,
            "respiratory_rate": 18,
            "temperature": 98.6,
            "spo2": 95,
            "pain_score_clinical": 3.0
        },
        "lab_values": {
            "hemoglobin": 12.5,
            "creatinine": 1.2,
            "glucose": 145,
            "hba1c": 7.5,
            "wbc_count": 8.5,
            "total_bilirubin": 1.0,
            "platelet_count": 250000,
            "sodium": 140.0,
            "potassium": 4.2,
            "troponin": 0.02,
            "bnp": 180,
            "lactate": 1.5,
            "inr": 1.1
        },
        "medications": {
            "active_medication_count": 8,
            "medication_count_at_discharge": 9,
            "polypharmacy_flag": 1,
            "high_risk_medication_flag": 1,
            "on_anticoagulants_flag": 0,
            "on_insulin_flag": 1,
            "medication_adherence_rate": 0.85
        },
        "utilization_history": {
            "previous_admissions_12m": 2,
            "previous_er_visits_12m": 3,
            "prior_30_day_readmission_flag": 0,
            "days_since_last_ed_visit": 90,
            "ed_visits_90d": 1,
            "ed_visits_30d": 0,
            "outpatient_visits_365d": 12,
            "days_since_last_pcp_visit": 30,
            "missed_appointments_6m": 1
        },
        "admission_data": {
            "admission_date": str(admission_date),
            "discharge_date": str(discharge_date),
            "admission_type": "emergency",
            "length_of_stay_days": 3,
            "icu_stay_flag": 0,
            "discharge_destination": "home",
            "follow_up_within_7_days_flag": 1,
            "follow_up_appointment_date": str(followup_date),
            "total_charges_index_stay": 15000.00
        },
        "clinical_notes": "Patient admitted with CHF exacerbation and diabetes management issues. Discharged stable on optimized medications.",
        "contact_number": "+1-555-0123",
        "email": "test.patient@example.com",
        "address": "123 Test Street, Test City, TS 12345",
        "insurance_id": "MED123456789"
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/ehr/patients",
            json=patient_ehr_data,
            headers=headers
        )
        
        if response.status_code == 201:
            data = response.json()
            mrn = data.get("mrn")
            patient_id = data.get("patient_id")
            print_success("Patient EHR created successfully")
            print(f"   Patient ID: {patient_id}")
            print(f"   MRN: {mrn}")
            print(f"   Name: {data.get('name')}")
            print(f"   Age: {data.get('age')}")
            print(f"   Chronic Conditions: Diabetes, Heart Failure, COPD, Hypertension")
            return {"mrn": mrn, "patient_id": patient_id}
        else:
            print_error(f"Failed to create patient: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error creating patient: {str(e)}")
        return None

def create_patient_user(mrn):
    print_header("STEP 4: Create Patient User Account")
    
    patient_user_data = {
        "username": "test_patient",
        "password": "PatientPass123!",
        "confirm_password": "PatientPass123!",
        "mrn": mrn
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/signup/patient",
            json=patient_user_data
        )
        
        if response.status_code == 201:
            print_success("Patient user account created successfully")
            print(f"   Username: test_patient")
            print(f"   Password: PatientPass123!")
            print(f"   MRN: {mrn}")
            return {"username": "test_patient", "password": "PatientPass123!", "mrn": mrn}
        elif response.status_code == 400 and "already exists" in response.text:
            print_success("Patient user already exists (using existing)")
            print(f"   Username: test_patient")
            print(f"   Password: PatientPass123!")
            print(f"   MRN: {mrn}")
            return {"username": "test_patient", "password": "PatientPass123!", "mrn": mrn}
        else:
            print_error(f"Failed to create patient user: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error creating patient user: {str(e)}")
        return None

def main():
    print_header("CarePath Test Data Setup")
    print("This script creates test users and patient data for testing")
    
    # Step 1: Create Care Manager
    care_manager_creds = create_care_manager()
    if not care_manager_creds:
        print_error("Cannot continue without Care Manager")
        return
    
    # Step 2: Login as Care Manager
    cm_token = login_care_manager(care_manager_creds)
    if not cm_token:
        print_error("Cannot continue without authentication")
        return
    
    # Step 3: Create Patient EHR
    patient_info = create_patient_ehr(cm_token)
    if not patient_info:
        print_error("Cannot continue without patient EHR")
        return
    
    # Step 4: Create Patient User Account
    patient_user = create_patient_user(patient_info["mrn"])
    
    # Summary
    print_header("SETUP COMPLETE - Test Credentials Summary")
    print("\n📋 CARE MANAGER CREDENTIALS:")
    print(f"   Username: {care_manager_creds['username']}")
    print(f"   Password: {care_manager_creds['password']}")
    
    print("\n👤 PATIENT CREDENTIALS:")
    if patient_user:
        print(f"   Username: {patient_user['username']}")
        print(f"   Password: {patient_user['password']}")
    print(f"   MRN: {patient_info['mrn']}")
    print(f"   Patient ID: {patient_info['patient_id']}")
    
    print("\n🔗 API ENDPOINTS:")
    print(f"   Base URL: {BASE_URL}")
    print(f"   Login: {BASE_URL}/api/v1/auth/login")
    print(f"   EHR: {BASE_URL}/api/v1/ehr/patients")
    print(f"   Readmission: {BASE_URL}/api/v1/care-manager/patients/{patient_info['patient_id']}/readmission/predict")
    
    print("\n✅ You can now run your integration tests!")
    print("="*80)

if __name__ == "__main__":
    main()
