"""
Patient context retrieval module for Care Plan Agent.

Provides utilities to fetch patient demographic and clinical context data
from PostgreSQL EHR using MRN (Medical Record Number) as the lookup key.
This data is used to inform care plan generation.

Data source: PostgreSQL database (carepath_db) / patient_ehr table
Application-level identifier: MRN (Medical Record Number)
Internal identifier: patient_id (database id field)
"""

from typing import Dict, Any, Tuple, Optional
from post_care.database.connection import get_db_connection, close_db_connection


def get_patient_context(mrn: str) -> Tuple[Dict[str, Any], str]:
    """
    Retrieve patient context data from PostgreSQL EHR using MRN.
    
    Queries the patient_ehr table by MRN (Medical Record Number) and extracts 
    relevant patient-context fields. Patient context includes demographic,
    admission, and clinical information that informs post-care pathway selection
    and task generation.
    
    Includes clinical_notes from the same EHR record (preserved as-is, not modified).
    
    Args:
        mrn: Medical Record Number (application-level unique patient identifier)
             e.g., "MRN000001"
    
    Returns:
        Tuple of (patient_context_dict, patient_id):
        - patient_context_dict: Dictionary containing patient context fields:
            - Demographics: age, sex (0=female, 1=male), bmi, insurance_type
            - Admission: admission_type, discharge_destination
            - Clinical: comorbidity_index, diabetes_flag, heart_failure_flag, copd_flag,
                       ckd_flag, cancer_flag, dementia_flag
            - Utilization: previous_admissions_12m, previous_er_visits_12m,
                          prior_30_day_readmission_flag
            - Hospitalization: length_of_stay_days, icu_stay_flag
            - Medication: medication_count_at_discharge, polypharmacy_flag,
                         high_risk_medication_flag
            - Follow-up: follow_up_within_7_days_flag
            - Clinical notes: clinical_notes (preserved as-is from EHR record)
        - patient_id: Internal patient identifier (database id field)
    
    Raises:
        ValueError: If MRN not found in patient_ehr table
        psycopg2.Error: If database connection fails
    
    Note:
        Clinical notes come from the SAME patient_ehr record.
        Notes are preserved exactly as stored (no modification, summarization, or LLM processing).
        NULL notes are returned as None.
        Whitespace-only notes are normalized to None by Care Plan Agent.
    """
    
    # SQL query to retrieve patient context from patient_ehr table
    # Note: Database column names may differ from context field names
    # (e.g., gender vs sex, copd_asthma_flag vs copd_flag)
    query = """
    SELECT 
        id,
        mrn,
        age,
        gender,
        bmi,
        insurance_type,
        diabetes_flag,
        heart_failure_flag,
        copd_asthma_flag,
        ckd_flag,
        cancer_flag,
        dementia_flag,
        charlson_comorbidity_index,
        admission_type,
        discharge_destination,
        length_of_stay_days,
        icu_stay_flag,
        medication_count_at_discharge,
        polypharmacy_flag,
        high_risk_medication_flag,
        previous_admissions_12m,
        previous_er_visits_12m,
        prior_30_day_readmission_flag,
        follow_up_within_7_days_flag,
        clinical_notes
    FROM patient_ehr
    WHERE mrn = %s
    LIMIT 1
    """
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, (mrn,))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(
                f"Patient with MRN '{mrn}' not found in patient_ehr table."
            )
        
        # Extract database id as patient_id (for internal tracking)
        patient_id = str(row[0])
        
        # Map database columns to context dictionary
        # Order must match SELECT statement above
        # Note: Some column names are mapped (gender→sex, copd_asthma_flag→copd_flag, etc)
        patient_context = {
            "age": row[2],
            "sex": row[3],  # from gender column
            "bmi": row[4],
            "insurance_type": row[5],
            "diabetes_flag": row[6],
            "heart_failure_flag": row[7],
            "copd_flag": row[8],  # from copd_asthma_flag column
            "ckd_flag": row[9],
            "cancer_flag": row[10],
            "dementia_flag": row[11],
            "comorbidity_index": row[12],  # from charlson_comorbidity_index
            "admission_type": row[13],
            "discharge_destination": row[14],
            "length_of_stay_days": row[15],
            "icu_stay_flag": row[16],
            "medication_count_at_discharge": row[17],
            "polypharmacy_flag": row[18],
            "high_risk_medication_flag": row[19],
            "previous_admissions_12m": row[20],
            "previous_er_visits_12m": row[21],
            "prior_30_day_readmission_flag": row[22],
            "follow_up_within_7_days_flag": row[23],
            "clinical_notes": row[24]  # Preserved as-is from EHR
        }
        
        # Normalize clinical_notes: NULL or whitespace-only → None
        if isinstance(patient_context["clinical_notes"], str):
            if patient_context["clinical_notes"].strip():
                # Has meaningful content, keep it
                patient_context["clinical_notes"] = patient_context["clinical_notes"]
            else:
                # Whitespace-only, normalize to None
                patient_context["clinical_notes"] = None
        # If already None, leave it
        
        return patient_context, patient_id
    
    except ValueError:
        # Re-raise ValueError (patient not found)
        raise
    except Exception as e:
        raise Exception(
            f"Failed to retrieve patient context for MRN '{mrn}' from PostgreSQL: {e}"
        )
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                print(f"Warning: Error closing cursor: {e}")
        if conn:
            close_db_connection(conn)

