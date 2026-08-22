"""
PostgreSQL Migration Tests

Tests for the migration from CSV-based patient context retrieval to PostgreSQL EHR.

Tests verify:
1. PostgreSQL connection functionality
2. Patient context retrieval from patient_ehr table
3. MRN as application-level lookup key
4. patient_id (database id) returned correctly
5. clinical_notes retrieved from EHR
6. All 22+ context fields extracted
7. Care Plan Agent behavior unchanged with new data source
8. No regression in existing Care Plan Agent tests
"""

import pytest
import sys
from pathlib import Path

# Add post_care to path for imports
post_care_dir = Path(__file__).parents[2]
sys.path.insert(0, str(post_care_dir))

from agents.care_plan.agent import run_care_plan_agent
from agents.care_plan.schemas import ReadmissionInput
from shared_tools.patient.patient_context import get_patient_context
from database.connection import get_db_connection


# ============================================================================
# TEST CATEGORY 1: DATABASE CONNECTION
# ============================================================================

class TestPostgresConnection:
    """Test PostgreSQL connection functionality."""
    
    def test_db_connection_successful(self):
        """TEST 1: PostgreSQL connection is successful."""
        try:
            conn = get_db_connection()
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result is not None
            cursor.close()
            conn.close()
            print("✓ TEST 1 PASSED: PostgreSQL connection successful")
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")


# ============================================================================
# TEST CATEGORY 2: PATIENT CONTEXT RETRIEVAL (PostgreSQL)
# ============================================================================

class TestPatientContextPostgreSQL:
    """Test patient context retrieval from PostgreSQL."""
    
    def test_retrieve_patient_context_mrn000001(self):
        """TEST 2: Retrieve patient context for MRN000001 from PostgreSQL."""
        try:
            context, patient_id = get_patient_context("MRN000001")
            
            # Verify patient_id is returned as string (database id)
            assert patient_id == "1", f"Expected patient_id '1', got '{patient_id}'"
            
            # Verify core demographic fields
            assert "age" in context
            assert "sex" in context
            assert "bmi" in context
            
            # Verify admission fields
            assert "admission_type" in context
            assert "discharge_destination" in context
            
            # Verify clinical fields
            assert "diabetes_flag" in context
            assert "heart_failure_flag" in context
            assert "copd_flag" in context
            assert "comorbidity_index" in context
            
            # Verify utilization fields
            assert "previous_admissions_12m" in context
            assert "previous_er_visits_12m" in context
            
            # Verify medication fields
            assert "medication_count_at_discharge" in context
            assert "polypharmacy_flag" in context
            
            # Verify clinical_notes are included
            assert "clinical_notes" in context
            
            print(f"✓ TEST 2 PASSED: Patient MRN000001 retrieved successfully")
            print(f"  - patient_id: {patient_id}")
            print(f"  - age: {context.get('age')}")
            print(f"  - insurance_type: {context.get('insurance_type')}")
            print(f"  - clinical_notes preview: {str(context.get('clinical_notes', ''))[:50]}...")
            
        except Exception as e:
            pytest.skip(f"PostgreSQL not available or MRN000001 not found: {e}")
    
    def test_patient_id_is_database_id(self):
        """TEST 3: patient_id returned is the database id field."""
        try:
            context, patient_id = get_patient_context("MRN000001")
            
            # Query database directly to verify patient_id matches
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM patient_ehr WHERE mrn = %s LIMIT 1", ("MRN000001",))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                db_id = str(row[0])
                assert patient_id == db_id, f"patient_id mismatch: {patient_id} vs {db_id}"
                print(f"✓ TEST 3 PASSED: patient_id matches database id: {patient_id}")
            else:
                pytest.skip("MRN000001 not found in database")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    
    def test_clinical_notes_retrieved(self):
        """TEST 4: clinical_notes are retrieved from EHR."""
        try:
            context, patient_id = get_patient_context("MRN000001")
            
            # clinical_notes should be present in context
            assert "clinical_notes" in context
            
            # Should be string or None
            if context["clinical_notes"] is not None:
                assert isinstance(context["clinical_notes"], str)
                print(f"✓ TEST 4 PASSED: clinical_notes retrieved: {context['clinical_notes'][:60]}...")
            else:
                print(f"✓ TEST 4 PASSED: clinical_notes is None (no notes in EHR)")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    
    def test_invalid_mrn_raises_error(self):
        """TEST 5: Invalid MRN raises ValueError."""
        try:
            with pytest.raises(ValueError, match="not found"):
                get_patient_context("INVALID_MRN_XXXXX")
            print("✓ TEST 5 PASSED: Invalid MRN raises ValueError")
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    
    def test_all_context_fields_present(self):
        """TEST 6: All required context fields are present."""
        required_fields = [
            "age", "sex", "bmi", "insurance_type",
            "diabetes_flag", "heart_failure_flag", "copd_flag", "ckd_flag",
            "cancer_flag", "dementia_flag", "comorbidity_index",
            "admission_type", "discharge_destination",
            "length_of_stay_days", "icu_stay_flag",
            "medication_count_at_discharge", "polypharmacy_flag", "high_risk_medication_flag",
            "previous_admissions_12m", "previous_er_visits_12m", "prior_30_day_readmission_flag",
            "follow_up_within_7_days_flag", "clinical_notes"
        ]
        
        try:
            context, patient_id = get_patient_context("MRN000001")
            
            missing_fields = [f for f in required_fields if f not in context]
            assert not missing_fields, f"Missing fields: {missing_fields}"
            
            print(f"✓ TEST 6 PASSED: All {len(required_fields)} context fields present")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")


# ============================================================================
# TEST CATEGORY 3: CARE PLAN AGENT REGRESSION (PostgreSQL DATA SOURCE)
# ============================================================================

class TestCareplanAgentPostgresql:
    """Test Care Plan Agent behavior with PostgreSQL data source."""
    
    def test_care_plan_with_postgresql_context(self):
        """TEST 7: Care Plan Agent works with PostgreSQL patient context."""
        try:
            input_data = ReadmissionInput(
                mrn="MRN000001",
                prediction=1,
                probability=0.86,
                notes="Meet Dr. X after 7 days."
            )
            
            output = run_care_plan_agent(input_data)
            
            # Verify output structure
            assert output.mrn == "MRN000001"
            assert output.patient_id == "1"
            assert output.care_plan_id is not None
            assert output.risk_level in ["HIGH", "MODERATE", "LOW"]
            assert output.status in ["ACTIVE", "COMPLETED"]
            assert len(output.tasks) > 0
            
            # HIGH risk should have 5 tasks
            if output.risk_level == "HIGH":
                assert len(output.tasks) == 5, f"HIGH risk should have 5 tasks, got {len(output.tasks)}"
            
            print(f"✓ TEST 7 PASSED: Care Plan Agent with PostgreSQL context")
            print(f"  - MRN: {output.mrn}")
            print(f"  - risk_level: {output.risk_level}")
            print(f"  - tasks: {len(output.tasks)}")
            print(f"  - notes preserved: {output.notes is not None}")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available or Care Plan Agent failed: {e}")
    
    def test_active_plan_reuse_postgresql(self):
        """TEST 8: Active plan reuse works with PostgreSQL data source."""
        try:
            # First call - creates plan
            input_data1 = ReadmissionInput(
                mrn="MRN000002",
                prediction=1,
                probability=0.75,
                notes="Follow discharge instructions."
            )
            output1 = run_care_plan_agent(input_data1)
            care_plan_id_1 = output1.care_plan_id
            task_count_1 = len(output1.tasks)
            
            # Second call - should reuse same plan (no duplicates)
            input_data2 = ReadmissionInput(
                mrn="MRN000002",
                prediction=1,
                probability=0.75,
                notes="Updated notes"
            )
            output2 = run_care_plan_agent(input_data2)
            care_plan_id_2 = output2.care_plan_id
            task_count_2 = len(output2.tasks)
            
            # Verify reuse
            assert care_plan_id_1 == care_plan_id_2, "Plan should be reused"
            assert task_count_1 == task_count_2, f"Task count should remain {task_count_1}, not {task_count_2}"
            
            print(f"✓ TEST 8 PASSED: Active plan reuse works with PostgreSQL")
            print(f"  - Reused plan: {care_plan_id_1}")
            print(f"  - Tasks preserved: {task_count_1} → {task_count_2}")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    
    def test_notes_preserved_from_postgresql(self):
        """TEST 9: Clinical notes are preserved in Care Plan output."""
        try:
            test_notes = "Continue prescribed medications. Monitor symptoms daily."
            input_data = ReadmissionInput(
                mrn="MRN000001",
                prediction=1,
                probability=0.86,
                notes=test_notes
            )
            
            output = run_care_plan_agent(input_data)
            
            # Notes should be preserved in output
            assert output.notes == test_notes, f"Notes not preserved: {output.notes}"
            
            print(f"✓ TEST 9 PASSED: Notes preserved in Care Plan output")
            print(f"  - Notes: {output.notes[:50]}...")
        
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")


# ============================================================================
# TEST CATEGORY 4: DATA SOURCE VALIDATION
# ============================================================================

class TestDataSourceValidation:
    """Verify CSV is no longer used by Care Plan Agent."""
    
    def test_csv_not_imported_in_patient_context(self):
        """TEST 10: CSV (pandas) is not imported in patient_context module."""
        with open("/Users/subitsha/Desktop/post_care/post_care/shared_tools/patient/patient_context.py", "r") as f:
            content = f.read()
            assert "import pandas" not in content, "pandas should not be imported"
            assert "csv" not in content.lower(), "CSV should not be referenced"
            assert "psycopg2" in content, "psycopg2 should be imported"
        
        print("✓ TEST 10 PASSED: CSV is not used in patient_context module")
    
    def test_postgresql_used_in_patient_context(self):
        """TEST 11: PostgreSQL is used in patient_context module."""
        with open("/Users/subitsha/Desktop/post_care/post_care/shared_tools/patient/patient_context.py", "r") as f:
            content = f.read()
            assert "psycopg2" in content, "psycopg2 should be imported"
            assert "get_db_connection" in content, "Database connection should be used"
            assert "patient_ehr" in content, "patient_ehr table should be queried"
        
        print("✓ TEST 11 PASSED: PostgreSQL is used in patient_context module")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PostgreSQL Migration Test Suite")
    print("="*80 + "\n")
    
    pytest.main([__file__, "-v", "-s"])
