#!/usr/bin/env python3
"""
Regression tests for patient creation API.

This test suite ensures that the patient creation endpoint works correctly
and that critical issues (like the MRN generation bug) do not resurface.

Fixes validated:
- RealDictCursor compatibility in generate_mrn()
- Error handling with proper logging
- MRN auto-generation for new patients
"""
import sys
import os
from datetime import date

# Setup path
sys.path.insert(0, '/Users/subitsha/Desktop/post_care/post_care')

import psycopg2
import psycopg2.extras
import pytest


# Database config
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "carepath_db",
    "user": "subitsha"
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


class TestPatientCreationAPI:
    """Test suite for patient creation API."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test."""
        self.conn = None
        yield
        # Cleanup after each test
        if self.conn:
            self.conn.close()
    
    def test_mrn_generation_with_realdictcursor(self):
        """
        Regression test for MRN generation with RealDictCursor.
        
        Issue: generate_mrn() failed when called with RealDictCursor because
        it tried to access result as a tuple (result[0]) instead of a dict.
        
        Expected: generate_mrn() should work with both tuple and dict results.
        """
        from main import generate_mrn
        
        self.conn = get_db_connection()
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # This should not raise KeyError
            mrn = generate_mrn(cursor)
            
            assert mrn is not None
            assert isinstance(mrn, str)
            assert mrn.startswith("MRN")
            assert len(mrn) == 9  # MRN + 6 digits
        finally:
            cursor.close()
    
    def test_mrn_generation_with_regular_cursor(self):
        """
        Test MRN generation with regular cursor (tuple results).
        
        Expected: generate_mrn() should also work with regular cursor.
        """
        from main import generate_mrn
        
        self.conn = get_db_connection()
        cursor = self.conn.cursor()
        
        try:
            mrn = generate_mrn(cursor)
            
            assert mrn is not None
            assert isinstance(mrn, str)
            assert mrn.startswith("MRN")
        finally:
            cursor.close()
    
    def test_patient_creation_success(self):
        """
        Test successful patient creation via API.
        
        Expected: Patient is created with auto-generated MRN.
        """
        from main import create_patient, PatientCreate
        
        payload = {
            "first_name": "Test",
            "last_name": "Patient",
            "date_of_birth": "1975-06-15",
            "age": 49,
            "gender": "female",
            "bmi": 24.5,
            "insurance_type": "Private",
            
            "diabetes_flag": 0,
            "heart_failure_flag": 0,
            "cardiac_history_flag": 0,
            "copd_asthma_flag": 0,
            "ckd_flag": 0,
            "cancer_flag": 0,
            "dementia_flag": 0,
            "hypertension_flag": 0,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 0,
            
            "hemoglobin": 13.5,
            "creatinine": 1.0,
            "glucose": 100,
            "wbc_count": 7.0,
            
            "previous_admissions_12m": 0,
            "previous_er_visits_12m": 0,
        }
        
        patient_data = PatientCreate(**payload)
        result = create_patient(patient_data)
        
        assert result["message"] == "Patient created successfully"
        assert "patient" in result
        assert result["patient"]["first_name"] == "Test"
        assert result["patient"]["mrn"].startswith("MRN")
        assert result["patient"]["id"] is not None
    
    def test_mrn_sequence(self):
        """
        Test that MRN generation follows correct sequence.
        
        Expected: Each new patient gets a unique MRN in sequence.
        """
        from main import create_patient, PatientCreate
        
        # Get last MRN
        self.conn = get_db_connection()
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT mrn FROM patient_ehr
            WHERE mrn LIKE 'MRN%'
            ORDER BY id DESC LIMIT 1
        """)
        last_row = cursor.fetchone()
        cursor.close()
        self.conn.close()
        
        last_mrn_num = int(last_row[0].replace("MRN", ""))
        
        # Create patient
        payload = {
            "first_name": "Sequence",
            "last_name": "Test",
            "date_of_birth": "1980-01-01",
            "age": 44,
            "gender": "male",
            "bmi": 25.0,
            "insurance_type": "Medicare",
            
            "diabetes_flag": 0,
            "heart_failure_flag": 0,
            "cardiac_history_flag": 0,
            "copd_asthma_flag": 0,
            "ckd_flag": 0,
            "cancer_flag": 0,
            "dementia_flag": 0,
            "hypertension_flag": 0,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 0,
            
            "hemoglobin": 13.5,
            "creatinine": 1.0,
            "glucose": 100,
            "wbc_count": 7.0,
            
            "previous_admissions_12m": 0,
            "previous_er_visits_12m": 0,
        }
        
        patient_data = PatientCreate(**payload)
        result = create_patient(patient_data)
        
        new_mrn_num = int(result["patient"]["mrn"].replace("MRN", ""))
        
        # New MRN should be exactly one more than last
        assert new_mrn_num == last_mrn_num + 1
    
    def test_patient_persists_in_database(self):
        """
        Test that created patient is actually persisted in PostgreSQL.
        
        Expected: Query shows the patient exists.
        """
        from main import create_patient, PatientCreate
        
        payload = {
            "first_name": "Persist",
            "last_name": "Test",
            "date_of_birth": "1985-03-20",
            "age": 39,
            "gender": "other",
            "bmi": 22.0,
            "insurance_type": "Self-pay",
            
            "diabetes_flag": 0,
            "heart_failure_flag": 0,
            "cardiac_history_flag": 0,
            "copd_asthma_flag": 0,
            "ckd_flag": 0,
            "cancer_flag": 0,
            "dementia_flag": 0,
            "hypertension_flag": 0,
            "immunocompromised_flag": 0,
            "charlson_comorbidity_index": 0,
            
            "hemoglobin": 13.5,
            "creatinine": 1.0,
            "glucose": 100,
            "wbc_count": 7.0,
            
            "previous_admissions_12m": 0,
            "previous_er_visits_12m": 0,
        }
        
        patient_data = PatientCreate(**payload)
        result = create_patient(patient_data)
        
        mrn = result["patient"]["mrn"]
        
        # Query database to verify
        self.conn = get_db_connection()
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM patient_ehr WHERE mrn = %s", (mrn,))
        db_patient = cursor.fetchone()
        cursor.close()
        
        assert db_patient is not None
        assert db_patient["mrn"] == mrn
        assert db_patient["first_name"] == "Persist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
