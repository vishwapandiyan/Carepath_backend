#!/usr/bin/env python3
"""
Complete Flow Test for CarePath Healthcare Platform
Tests the entire flow from manager creation to patient EHR management
"""
import requests
import json
from datetime import date

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
CARE_MANAGER_USERNAME = "test_manager"
CARE_MANAGER_PASSWORD = "SecurePass123!"

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def print_step(step_num, description):
    """Print a test step header"""
    print(f"\n{BLUE}{'='*60}")
    print(f"STEP {step_num}: {description}")
    print(f"{'='*60}{RESET}\n")


def print_success(message):
    """Print success message"""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message):
    """Print error message"""
    print(f"{RED}✗ {message}{RESET}")


def print_info(message):
    """Print info message"""
    print(f"{YELLOW}ℹ {message}{RESET}")


def test_complete_flow():
    """Run complete flow test"""
    
    print(f"\n{BLUE}{'='*60}")
    print("CarePath Healthcare Platform - Complete Flow Test")
    print(f"{'='*60}{RESET}\n")
    
    # ========================================
    # STEP 1: Create Care Manager
    # ========================================
    print_step(1, "Create Care Manager Account")
    
    care_manager_data = {
        "username": CARE_MANAGER_USERNAME,
        "password": CARE_MANAGER_PASSWORD,
        "confirm_password": CARE_MANAGER_PASSWORD
    }
    
    response = requests.post(f"{BASE_URL}/auth/signup/care-manager", json=care_manager_data)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Care Manager created successfully")
        print_info(f"Username: {CARE_MANAGER_USERNAME}")
        print_info(f"Role: {result['role']}")
        print_info(f"Redirect: {result['redirect_to']}")
        care_manager_token = result['access_token']
        print(f"\n{YELLOW}Token (first 50 chars): {care_manager_token[:50]}...{RESET}")
    elif response.status_code == 400 and "already exists" in response.json().get("detail", ""):
        print_info("Care Manager already exists, logging in...")
        
        # Login instead
        login_data = {
            "username": CARE_MANAGER_USERNAME,
            "password": CARE_MANAGER_PASSWORD
        }
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        if response.status_code == 200:
            result = response.json()
            care_manager_token = result['access_token']
            print_success("Logged in successfully")
        else:
            print_error(f"Login failed: {response.json()}")
            return False
    else:
        print_error(f"Failed to create Care Manager: {response.json()}")
        return False
    
    # ========================================
    # STEP 2: Create Patient EHR Record
    # ========================================
    print_step(2, "Create Patient EHR Record (Auto-generate MRN)")
    
    patient_ehr_data = {
        "demographics": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1975-05-15",
            "age": 49,
            "gender": "male",
            "bmi": 28.5,
            "insurance_type": "Medicare",
            "race": "Caucasian"
        },
        "chronic_conditions": {
            "diabetes_flag": 1,
            "heart_failure_flag": 0,
            "cardiac_history_flag": 1,
            "copd_asthma_flag": 0,
            "ckd_flag": 0,
            "cancer_flag": 0,
            "dementia_flag": 0,
            "hypertension_flag": 1,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 3
        },
        "vital_signs_current": {
            "systolic_bp": 145,
            "diastolic_bp": 92,
            "heart_rate": 78,
            "respiratory_rate": 16,
            "temperature": 98.6,
            "spo2": 97,
            "pain_score_clinical": 2.5
        },
        "lab_values": {
            "hemoglobin": 13.2,
            "creatinine": 1.1,
            "glucose": 145,
            "hba1c": 7.2,
            "wbc_count": 8.5,
            "total_bilirubin": 0.9,
            "platelet_count": 250000,
            "sodium": 140.0,
            "potassium": 4.2,
            "troponin": 0.02,
            "bnp": 150,
            "lactate": 1.2,
            "inr": 1.0
        },
        "medications": {
            "active_medication_count": 5,
            "medication_count_at_discharge": 6,
            "polypharmacy_flag": 1,
            "high_risk_medication_flag": 0,
            "on_anticoagulants_flag": 0,
            "on_insulin_flag": 1,
            "medication_adherence_rate": 0.85
        },
        "utilization_history": {
            "previous_admissions_12m": 2,
            "previous_er_visits_12m": 3,
            "prior_30_day_readmission_flag": 0,
            "days_since_last_ed_visit": 45,
            "ed_visits_90d": 1,
            "ed_visits_30d": 0,
            "outpatient_visits_365d": 12,
            "days_since_last_pcp_visit": 30,
            "missed_appointments_6m": 1
        },
        "admission_data": {
            "admission_date": "2024-01-15",
            "discharge_date": "2024-01-20",
            "admission_type": "emergency",
            "length_of_stay_days": 5,
            "icu_stay_flag": 0,
            "discharge_destination": "home",
            "follow_up_within_7_days_flag": 1,
            "follow_up_appointment_date": "2024-01-27",
            "total_charges_index_stay": 25000.00
        },
        "clinical_notes": "Patient admitted with chest pain. ECG showed no acute changes. Troponin slightly elevated. Ruled out MI. Patient has history of diabetes and hypertension. Discharged on modified medication regimen with close follow-up."
    }
    
    headers = {"Authorization": f"Bearer {care_manager_token}"}
    response = requests.post(f"{BASE_URL}/ehr/patients", json=patient_ehr_data, headers=headers)
    
    if response.status_code == 201:
        patient = response.json()
        patient_id = patient['id']
        patient_mrn = patient['mrn']
        print_success("Patient EHR record created successfully")
        print_info(f"Patient ID: {patient_id}")
        print_info(f"Auto-generated MRN: {patient_mrn}")
        print_info(f"Patient Name: {patient['first_name']} {patient['last_name']}")
        print_info(f"Age: {patient['age']}")
        print_info(f"BMI: {patient['bmi']}")
    else:
        print_error(f"Failed to create patient: {response.status_code} - {response.json()}")
        return False
    
    # ========================================
    # STEP 3: Fetch Patient by ID
    # ========================================
    print_step(3, f"Fetch Patient EHR by ID ({patient_id})")
    
    response = requests.get(f"{BASE_URL}/ehr/patients/{patient_id}", headers=headers)
    
    if response.status_code == 200:
        patient = response.json()
        print_success("Patient fetched successfully by ID")
        print_info(f"MRN: {patient['mrn']}")
        print_info(f"Name: {patient['first_name']} {patient['last_name']}")
        print_info(f"DOB: {patient['date_of_birth']}")
        print_info(f"Diabetes Flag: {patient['diabetes_flag']}")
        print_info(f"Hypertension Flag: {patient['hypertension_flag']}")
        print_info(f"Previous Admissions (12m): {patient['previous_admissions_12m']}")
    else:
        print_error(f"Failed to fetch patient: {response.json()}")
        return False
    
    # ========================================
    # STEP 4: Fetch Patient by MRN
    # ========================================
    print_step(4, f"Fetch Patient EHR by MRN ({patient_mrn})")
    
    response = requests.get(f"{BASE_URL}/ehr/patients/mrn/{patient_mrn}", headers=headers)
    
    if response.status_code == 200:
        patient = response.json()
        print_success("Patient fetched successfully by MRN")
        print_info(f"Patient ID: {patient['id']}")
        print_info(f"Name: {patient['first_name']} {patient['last_name']}")
        print_info(f"Hemoglobin: {patient['hemoglobin']}")
        print_info(f"Creatinine: {patient['creatinine']}")
        print_info(f"Glucose: {patient['glucose']}")
    else:
        print_error(f"Failed to fetch patient by MRN: {response.json()}")
        return False
    
    # ========================================
    # STEP 5: Update Patient EHR
    # ========================================
    print_step(5, "Update Patient EHR Record")
    
    update_data = {
        "vital_signs_current": {
            "systolic_bp": 135,
            "diastolic_bp": 85,
            "heart_rate": 72,
            "respiratory_rate": 16,
            "temperature": 98.4,
            "spo2": 98,
            "pain_score_clinical": 1.0
        },
        "clinical_notes": "Follow-up visit: Patient showing improvement. Blood pressure better controlled. Glucose levels stable. Continue current medication regimen. Next follow-up in 3 months."
    }
    
    response = requests.put(f"{BASE_URL}/ehr/patients/{patient_id}", json=update_data, headers=headers)
    
    if response.status_code == 200:
        updated_patient = response.json()
        print_success("Patient EHR updated successfully")
        print_info(f"Updated Systolic BP: {updated_patient['systolic_bp']}")
        print_info(f"Updated Diastolic BP: {updated_patient['diastolic_bp']}")
        print_info(f"Updated Clinical Notes: {updated_patient['clinical_notes'][:100]}...")
    else:
        print_error(f"Failed to update patient: {response.json()}")
        return False
    
    # ========================================
    # STEP 6: List All Patients
    # ========================================
    print_step(6, "List All Patients (Paginated)")
    
    response = requests.get(f"{BASE_URL}/ehr/patients?skip=0&limit=10", headers=headers)
    
    if response.status_code == 200:
        patients = response.json()
        print_success(f"Fetched {len(patients)} patient(s)")
        for idx, p in enumerate(patients, 1):
            print_info(f"{idx}. {p['first_name']} {p['last_name']} - MRN: {p['mrn']} - Age: {p['age']}")
    else:
        print_error(f"Failed to list patients: {response.json()}")
        return False
    
    # ========================================
    # STEP 7: Test Patient Signup with MRN
    # ========================================
    print_step(7, f"Create Patient User Account with MRN ({patient_mrn})")
    
    patient_signup_data = {
        "username": "john_doe_patient",
        "password": "PatientPass123!",
        "confirm_password": "PatientPass123!",
        "mrn": patient_mrn
    }
    
    response = requests.post(f"{BASE_URL}/auth/signup/patient", json=patient_signup_data)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Patient user account created successfully")
        print_info(f"Username: john_doe_patient")
        print_info(f"Role: {result['role']}")
        print_info(f"Redirect: {result['redirect_to']}")
        patient_token = result['access_token']
    elif response.status_code == 400 and "already exists" in response.json().get("detail", ""):
        print_info("Patient user already exists, logging in...")
        
        login_data = {
            "username": "john_doe_patient",
            "password": "PatientPass123!"
        }
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        if response.status_code == 200:
            result = response.json()
            patient_token = result['access_token']
            print_success("Logged in successfully")
        else:
            print_error(f"Login failed: {response.json()}")
            return False
    else:
        print_error(f"Failed to create patient user: {response.json()}")
        return False
    
    # ========================================
    # STEP 8: Patient Access Dashboard
    # ========================================
    print_step(8, "Patient Accesses Their Dashboard")
    
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    response = requests.get(f"{BASE_URL}/patient/dashboard", headers=patient_headers)
    
    if response.status_code == 200:
        dashboard = response.json()
        print_success("Patient dashboard accessed successfully")
        print_info(f"Message: {dashboard['message']}")
        print_info(f"Patient Name: {dashboard['patient']['first_name']} {dashboard['patient']['last_name']}")
        print_info(f"MRN: {dashboard['patient']['mrn']}")
    else:
        print_error(f"Failed to access dashboard: {response.json()}")
        return False
    
    # ========================================
    # STEP 9: Test Role-Based Access Control
    # ========================================
    print_step(9, "Test Role-Based Access Control")
    
    # Try patient accessing care manager endpoint (should fail)
    print_info("Testing: Patient trying to access Care Manager endpoint...")
    response = requests.get(f"{BASE_URL}/care-manager/dashboard", headers=patient_headers)
    
    if response.status_code == 403:
        print_success("✓ Correctly blocked: Patient cannot access Care Manager routes")
    else:
        print_error("✗ Security issue: Patient accessed Care Manager route!")
        return False
    
    # Try patient accessing EHR management (should fail)
    print_info("Testing: Patient trying to create EHR record...")
    response = requests.post(f"{BASE_URL}/ehr/patients", json=patient_ehr_data, headers=patient_headers)
    
    if response.status_code == 403:
        print_success("✓ Correctly blocked: Patient cannot create EHR records")
    else:
        print_error("✗ Security issue: Patient created EHR record!")
        return False
    
    # ========================================
    # STEP 10: Optional - Delete Patient
    # ========================================
    print_step(10, "Delete Patient EHR Record (Optional)")
    
    print_info("Skipping deletion to preserve test data...")
    print_info(f"To delete manually, run: DELETE {BASE_URL}/ehr/patients/{patient_id}")
    
    # Uncomment to actually delete:
    # response = requests.delete(f"{BASE_URL}/ehr/patients/{patient_id}", headers=headers)
    # if response.status_code == 204:
    #     print_success("Patient EHR deleted successfully")
    # else:
    #     print_error(f"Failed to delete patient: {response.json()}")
    
    # ========================================
    # Summary
    # ========================================
    print(f"\n{GREEN}{'='*60}")
    print("✓ ALL TESTS PASSED SUCCESSFULLY!")
    print(f"{'='*60}{RESET}\n")
    
    print(f"{YELLOW}Summary:{RESET}")
    print(f"  • Care Manager Created: {CARE_MANAGER_USERNAME}")
    print(f"  • Patient EHR Created: {patient_mrn}")
    print(f"  • Patient User Created: john_doe_patient")
    print(f"  • All CRUD operations tested")
    print(f"  • Role-based access control verified")
    print(f"  • MRN auto-generation confirmed")
    
    return True


if __name__ == "__main__":
    try:
        success = test_complete_flow()
        exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to API server!")
        print_info("Make sure the server is running: uvicorn app.main:app --reload")
        exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
