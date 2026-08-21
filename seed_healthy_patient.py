"""
Seed a healthy normal patient record + user login credentials into PostgreSQL ehr_db
"""
import sys
sys.path.insert(0, ".")
import asyncio
import bcrypt
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def populate_healthy_patient():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        print("[INFO] Seeding Healthy Normal Patient into PostgreSQL ehr_db...")
        
        patient_id = "PAT_HEALTHY_001"
        mrn = "MRN10000099"
        name = "Healthy Patient"
        username = "healthy_patient"
        raw_password = "patient123"
        password_hash = get_password_hash(raw_password)

        # 1. Insert/Update patient_ehr record with all normal/healthy clinical values
        insert_ehr_query = text("""
        INSERT INTO patient_ehr (
            mrn, patient_id, name, date_of_birth, age, gender, bmi, insurance_type, race,
            diabetes_flag, heart_failure_flag, cardiac_history_flag, copd_asthma_flag, ckd_flag,
            cancer_flag, dementia_flag, hypertension_flag, immunocompromised_flag, charlson_comorbidity_index,
            systolic_bp, diastolic_bp, heart_rate, respiratory_rate, temperature, spo2, pain_score_clinical,
            hemoglobin, creatinine, glucose, hba1c, wbc_count, platelet_count, sodium, potassium, troponin, bnp, lactate, inr,
            active_medication_count, medication_count_at_discharge, polypharmacy_flag, high_risk_medication_flag,
            on_anticoagulants_flag, on_insulin_flag, medication_adherence_rate,
            previous_admissions_12m, previous_er_visits_12m, prior_30_day_readmission_flag,
            days_since_last_ed_visit, ed_visits_90d, ed_visits_30d, outpatient_visits_365d,
            days_since_last_pcp_visit, missed_appointments_6m, admission_type, discharge_destination,
            follow_up_within_7_days_flag, length_of_stay_days, total_charges_index_stay,
            clinical_notes, is_active
        ) VALUES (
            :mrn, :patient_id, :name, :date_of_birth, :age, :gender, :bmi, :insurance_type, :race,
            :diabetes_flag, :heart_failure_flag, :cardiac_history_flag, :copd_asthma_flag, :ckd_flag,
            :cancer_flag, :dementia_flag, :hypertension_flag, :immunocompromised_flag, :charlson_comorbidity_index,
            :systolic_bp, :diastolic_bp, :heart_rate, :respiratory_rate, :temperature, :spo2, :pain_score_clinical,
            :hemoglobin, :creatinine, :glucose, :hba1c, :wbc_count, :platelet_count, :sodium, :potassium, :troponin, :bnp, :lactate, :inr,
            :active_medication_count, :medication_count_at_discharge, :polypharmacy_flag, :high_risk_medication_flag,
            :on_anticoagulants_flag, :on_insulin_flag, :medication_adherence_rate,
            :previous_admissions_12m, :previous_er_visits_12m, :prior_30_day_readmission_flag,
            :days_since_last_ed_visit, :ed_visits_90d, :ed_visits_30d, :outpatient_visits_365d,
            :days_since_last_pcp_visit, :missed_appointments_6m, :admission_type, :discharge_destination,
            :follow_up_within_7_days_flag, :length_of_stay_days, :total_charges_index_stay,
            :clinical_notes, 1
        )
        ON CONFLICT (patient_id) DO UPDATE SET
            mrn = EXCLUDED.mrn,
            name = EXCLUDED.name,
            age = EXCLUDED.age,
            gender = EXCLUDED.gender,
            bmi = EXCLUDED.bmi,
            systolic_bp = EXCLUDED.systolic_bp,
            diastolic_bp = EXCLUDED.diastolic_bp,
            heart_rate = EXCLUDED.heart_rate,
            respiratory_rate = EXCLUDED.respiratory_rate,
            temperature = EXCLUDED.temperature,
            spo2 = EXCLUDED.spo2,
            pain_score_clinical = EXCLUDED.pain_score_clinical,
            glucose = EXCLUDED.glucose,
            creatinine = EXCLUDED.creatinine,
            wbc_count = EXCLUDED.wbc_count,
            hemoglobin = EXCLUDED.hemoglobin,
            hba1c = EXCLUDED.hba1c,
            charlson_comorbidity_index = EXCLUDED.charlson_comorbidity_index,
            previous_admissions_12m = EXCLUDED.previous_admissions_12m,
            previous_er_visits_12m = EXCLUDED.previous_er_visits_12m,
            is_active = 1,
            deleted_at = NULL,
            updated_at = CURRENT_TIMESTAMP;
        """)

        params = {
            "mrn": mrn,
            "patient_id": patient_id,
            "name": name,
            "date_of_birth": date(1991, 5, 15),
            "age": 35,
            "gender": "female",
            "bmi": 22.5,
            "insurance_type": "Private",
            "race": "White",
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
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "heart_rate": 72,
            "respiratory_rate": 16,
            "temperature": 98.6,
            "spo2": 98,
            "pain_score_clinical": 0.0,
            "hemoglobin": 14.2,
            "creatinine": 0.9,
            "glucose": 90,
            "hba1c": 5.2,
            "wbc_count": 6.5,
            "platelet_count": 250000,
            "sodium": 140.0,
            "potassium": 4.2,
            "troponin": 0.01,
            "bnp": 40,
            "lactate": 1.0,
            "inr": 1.0,
            "active_medication_count": 0,
            "medication_count_at_discharge": 0,
            "polypharmacy_flag": 0,
            "high_risk_medication_flag": 0,
            "on_anticoagulants_flag": 0,
            "on_insulin_flag": 0,
            "medication_adherence_rate": 1.0,
            "previous_admissions_12m": 0,
            "previous_er_visits_12m": 0,
            "prior_30_day_readmission_flag": 0,
            "days_since_last_ed_visit": 365,
            "ed_visits_90d": 0,
            "ed_visits_30d": 0,
            "outpatient_visits_365d": 1,
            "days_since_last_pcp_visit": 30,
            "missed_appointments_6m": 0,
            "admission_type": "elective",
            "discharge_destination": "home",
            "follow_up_within_7_days_flag": 1,
            "length_of_stay_days": 1,
            "total_charges_index_stay": 5000.0,
            "clinical_notes": "Healthy adult patient. All vitals, labs, and comorbidity indices within normal ranges.",
        }

        await conn.execute(insert_ehr_query, params)
        print(f"[OK] Seeded Healthy Patient EHR: {name} (MRN: {mrn}, Patient ID: {patient_id})")

        # 2. Insert/Update corresponding user account in users table
        user_query = text("""
        INSERT INTO users (username, password_hash, role, patient_id)
        VALUES (:username, :password_hash, :role, :patient_id)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            role = EXCLUDED.role,
            patient_id = EXCLUDED.patient_id,
            updated_at = CURRENT_TIMESTAMP;
        """)
        await conn.execute(user_query, {
            "username": username,
            "password_hash": password_hash,
            "role": "PATIENT",
            "patient_id": patient_id
        })
        print(f"[OK] Seeded user account: username='{username}', password='{raw_password}', role='PATIENT', patient_id='{patient_id}'")

    await engine.dispose()
    print("[SUCCESS] Healthy patient successfully seeded into DB!")

if __name__ == "__main__":
    asyncio.run(populate_healthy_patient())
