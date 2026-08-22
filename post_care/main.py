from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
import psycopg2
import psycopg2.extras
import re

app = FastAPI(
    title="CarePath EHR API",
    version="1.0.0"
)

# ============================================================
# PostgreSQL Configuration
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "carepath_db",
    "user": "vishwa"
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# EHR Input Schema
# ============================================================

class PatientCreate(BaseModel):
    # Demographics
    first_name: str
    last_name: str
    date_of_birth: date
    age: int = Field(ge=0, le=120)
    gender: str
    bmi: float = Field(ge=10.0, le=80.0)
    insurance_type: str
    race: Optional[str] = None

    # Chronic Conditions
    diabetes_flag: int = Field(default=0, ge=0, le=1)
    heart_failure_flag: int = Field(default=0, ge=0, le=1)
    cardiac_history_flag: int = Field(default=0, ge=0, le=1)
    copd_asthma_flag: int = Field(default=0, ge=0, le=1)
    ckd_flag: int = Field(default=0, ge=0, le=1)
    cancer_flag: int = Field(default=0, ge=0, le=1)
    dementia_flag: int = Field(default=0, ge=0, le=1)
    hypertension_flag: int = Field(default=0, ge=0, le=1)
    immunocompromised_flag: int = Field(default=0, ge=0, le=1)
    charlson_comorbidity_index: int = Field(default=0, ge=0, le=37)

    # Vital Signs
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = Field(default=None, ge=70, le=100)
    pain_score_clinical: Optional[float] = Field(default=None, ge=0, le=10)

    # Labs
    hemoglobin: float
    creatinine: float
    glucose: int
    hba1c: Optional[float] = None
    wbc_count: float
    total_bilirubin: Optional[float] = None
    platelet_count: Optional[int] = None
    sodium: Optional[float] = None
    potassium: Optional[float] = None
    troponin: Optional[float] = None
    bnp: Optional[int] = None
    lactate: Optional[float] = None
    inr: Optional[float] = None

    # Medications
    active_medication_count: int = Field(default=0, ge=0)
    medication_count_at_discharge: Optional[int] = None
    polypharmacy_flag: int = Field(default=0, ge=0, le=1)
    high_risk_medication_flag: int = Field(default=0, ge=0, le=1)
    on_anticoagulants_flag: int = Field(default=0, ge=0, le=1)
    on_insulin_flag: int = Field(default=0, ge=0, le=1)
    medication_adherence_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=1
    )

    # Utilization History
    previous_admissions_12m: int = Field(ge=0)
    previous_er_visits_12m: int = Field(ge=0)
    prior_30_day_readmission_flag: int = Field(default=0, ge=0, le=1)
    days_since_last_ed_visit: Optional[int] = None
    ed_visits_90d: Optional[int] = None
    ed_visits_30d: Optional[int] = None
    outpatient_visits_365d: Optional[int] = None
    days_since_last_pcp_visit: Optional[int] = None
    missed_appointments_6m: Optional[int] = None

    # Admission Data
    admission_date: Optional[date] = None
    discharge_date: Optional[date] = None
    admission_type: Optional[str] = None
    length_of_stay_days: Optional[int] = None
    icu_stay_flag: int = Field(default=0, ge=0, le=1)
    discharge_destination: Optional[str] = None
    follow_up_within_7_days_flag: int = Field(default=0, ge=0, le=1)
    follow_up_appointment_date: Optional[date] = None
    total_charges_index_stay: Optional[float] = None

    # Clinical Notes
    clinical_notes: Optional[str] = None


# ============================================================
# MRN Generation
# ============================================================

def generate_mrn(cursor):
    """
    Generate the next MRN in the format:
    MRN000001
    MRN000002
    ...
    
    Args:
        cursor: psycopg2 cursor (may be RealDictCursor or regular cursor)
    
    Returns:
        str: Next MRN in sequence
    """

    cursor.execute("""
        SELECT mrn
        FROM patient_ehr
        WHERE mrn LIKE 'MRN%'
        ORDER BY id DESC
        LIMIT 1
    """)

    result = cursor.fetchone()

    if result is None:
        return "MRN000001"

    # Handle both RealDictCursor (dict) and regular cursor (tuple)
    if isinstance(result, dict):
        last_mrn = result.get('mrn')
    else:
        last_mrn = result[0]
    
    if not last_mrn:
        return "MRN000001"

    match = re.match(r"MRN(\d+)", last_mrn)

    if not match:
        return "MRN000001"

    next_number = int(match.group(1)) + 1

    return f"MRN{next_number:06d}"


# ============================================================
# Health Check
# ============================================================

@app.get("/")
def root():
    return {
        "service": "CarePath EHR API",
        "status": "running"
    }


# ============================================================
# CREATE PATIENT
# ============================================================

@app.post("/api/v1/ehr/patients")
def create_patient(patient: PatientCreate):

    conn = None

    try:
        conn = get_db_connection()

        cursor = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        # Generate MRN
        try:
            mrn = generate_mrn(cursor)
        except Exception as e:
            raise ValueError(f"Failed to generate MRN: {str(e)}")

        # Insert patient
        try:
            cursor.execute("""
                INSERT INTO patient_ehr (
                    mrn,
                    first_name,
                    last_name,
                    date_of_birth,
                    age,
                    gender,
                    bmi,
                    insurance_type,
                    race,

                    diabetes_flag,
                    heart_failure_flag,
                    cardiac_history_flag,
                    copd_asthma_flag,
                    ckd_flag,
                    cancer_flag,
                    dementia_flag,
                    hypertension_flag,
                    immunocompromised_flag,
                    charlson_comorbidity_index,

                    systolic_bp,
                    diastolic_bp,
                    heart_rate,
                    respiratory_rate,
                    temperature,
                    spo2,
                    pain_score_clinical,

                    hemoglobin,
                    creatinine,
                    glucose,
                    hba1c,
                    wbc_count,
                    total_bilirubin,
                    platelet_count,
                    sodium,
                    potassium,
                    troponin,
                    bnp,
                    lactate,
                    inr,

                    active_medication_count,
                    medication_count_at_discharge,
                    polypharmacy_flag,
                    high_risk_medication_flag,
                    on_anticoagulants_flag,
                    on_insulin_flag,
                    medication_adherence_rate,

                    previous_admissions_12m,
                    previous_er_visits_12m,
                    prior_30_day_readmission_flag,
                    days_since_last_ed_visit,
                    ed_visits_90d,
                    ed_visits_30d,
                    outpatient_visits_365d,
                    days_since_last_pcp_visit,
                    missed_appointments_6m,

                    admission_date,
                    discharge_date,
                    admission_type,
                    length_of_stay_days,
                    icu_stay_flag,
                    discharge_destination,
                    follow_up_within_7_days_flag,
                    follow_up_appointment_date,
                    total_charges_index_stay,

                    clinical_notes
                )
                VALUES (
                    %(mrn)s,
                    %(first_name)s,
                    %(last_name)s,
                    %(date_of_birth)s,
                    %(age)s,
                    %(gender)s,
                    %(bmi)s,
                    %(insurance_type)s,
                    %(race)s,

                    %(diabetes_flag)s,
                    %(heart_failure_flag)s,
                    %(cardiac_history_flag)s,
                    %(copd_asthma_flag)s,
                    %(ckd_flag)s,
                    %(cancer_flag)s,
                    %(dementia_flag)s,
                    %(hypertension_flag)s,
                    %(immunocompromised_flag)s,
                    %(charlson_comorbidity_index)s,

                    %(systolic_bp)s,
                    %(diastolic_bp)s,
                    %(heart_rate)s,
                    %(respiratory_rate)s,
                    %(temperature)s,
                    %(spo2)s,
                    %(pain_score_clinical)s,

                    %(hemoglobin)s,
                    %(creatinine)s,
                    %(glucose)s,
                    %(hba1c)s,
                    %(wbc_count)s,
                    %(total_bilirubin)s,
                    %(platelet_count)s,
                    %(sodium)s,
                    %(potassium)s,
                    %(troponin)s,
                    %(bnp)s,
                    %(lactate)s,
                    %(inr)s,

                    %(active_medication_count)s,
                    %(medication_count_at_discharge)s,
                    %(polypharmacy_flag)s,
                    %(high_risk_medication_flag)s,
                    %(on_anticoagulants_flag)s,
                    %(on_insulin_flag)s,
                    %(medication_adherence_rate)s,

                    %(previous_admissions_12m)s,
                    %(previous_er_visits_12m)s,
                    %(prior_30_day_readmission_flag)s,
                    %(days_since_last_ed_visit)s,
                    %(ed_visits_90d)s,
                    %(ed_visits_30d)s,
                    %(outpatient_visits_365d)s,
                    %(days_since_last_pcp_visit)s,
                    %(missed_appointments_6m)s,

                    %(admission_date)s,
                    %(discharge_date)s,
                    %(admission_type)s,
                    %(length_of_stay_days)s,
                    %(icu_stay_flag)s,
                    %(discharge_destination)s,
                    %(follow_up_within_7_days_flag)s,
                    %(follow_up_appointment_date)s,
                    %(total_charges_index_stay)s,

                    %(clinical_notes)s
                )
                RETURNING id, mrn, first_name, last_name, clinical_notes
            """, {
                "mrn": mrn,
                **patient.model_dump()
            })
        except psycopg2.IntegrityError as e:
            raise ValueError(f"Data integrity error: {str(e)}")
        except psycopg2.DatabaseError as e:
            raise ValueError(f"Database error during patient insert: {str(e)}")

        result = cursor.fetchone()

        conn.commit()

        return {
            "message": "Patient created successfully",
            "patient": dict(result)
        }

    except ValueError as e:
        # User-friendly error (safe to expose)
        if conn:
            conn.rollback()
        print(f"Patient creation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
    except psycopg2.Error as e:
        # Database connection error (log server-side, expose generic message)
        if conn:
            conn.rollback()
        print(f"Database error during patient creation: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Database error occurred. Please check server logs."
        )
    
    except Exception as e:
        # Unexpected error (log server-side, expose generic message)
        if conn:
            conn.rollback()
        print(f"Unexpected error during patient creation: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please contact support."
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# GET PATIENT BY MRN
# ============================================================

@app.get("/api/v1/ehr/patients/mrn/{mrn}")
def get_patient_by_mrn(mrn: str):

    conn = None

    try:
        conn = get_db_connection()

        cursor = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cursor.execute("""
            SELECT *
            FROM patient_ehr
            WHERE mrn = %s
        """, (mrn,))

        patient = cursor.fetchone()

        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with MRN {mrn} not found"
            )

        return {
            "patient": dict(patient)
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# GET PATIENT BY DATABASE ID
# ============================================================

@app.get("/api/v1/ehr/patients/{patient_id}")
def get_patient(patient_id: int):

    conn = None

    try:
        conn = get_db_connection()

        cursor = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cursor.execute("""
            SELECT *
            FROM patient_ehr
            WHERE id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found"
            )

        return {
            "patient": dict(patient)
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            conn.close()
