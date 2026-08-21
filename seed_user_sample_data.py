"""
Seed 5 sample patient EHR records + Patient & Care Manager user accounts into PostgreSQL ehr_db
"""
import io
import asyncio
import pandas as pd
import bcrypt
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

raw_data = """systolic_bp	diastolic_bp	heart_rate	respiratory_rate	temperature	spo2	pain_score_clinical	wbc	hemoglobin	platelet_count	sodium	potassium	creatinine	glucose	troponin	bnp	lactate	inr	diabetes_flag	hypertension_flag	cardiac_history_flag	copd_asthma_flag	ckd_flag	cancer_flag	immunocompromised_flag	chronic_condition_count	charlson_comorbidity_index	active_medication_count	on_anticoagulants_flag	on_insulin_flag	days_since_last_ed_visit	ed_visits_past_year	admissions_past_year	has_pcp_flag	age	gender	month	day_of_week	is_weekend	is_holiday	flu_season	hour_of_day	diabetes	hypertension	heart_disease	copd_asthma	chronic_kidney_disease	ed_visits_365d	days_since_last_ed	ed_visits_90d	ed_visits_30d	outpatient_visits_365d	days_since_last_pcp_visit	inpatient_admissions_365d	missed_appointments_6m	days_since_last_vitals	days_since_last_labs	has_anticoagulant	medication_adherence_rate	race	insurance_type	primary_language	zip_poverty_rate	rural_urban_status	has_primary_care	distance_to_pcp_miles	pqe_category	avoidable_ed
1	109.0	77.0	81.0	15.0	37.0	100.0	5.4	7.0	11.6	259.0	140.4	4.01	1.1	91.0	0.026	50.0	1.41	1.05	0	0	0	0	0	0	1	1	2	3	0	0	107	3	0	0	59	male	10	4	0	0	0	13	0	0	0	0	0	3	107	2	2	0	822	0	0	203	321	0	0.85	Black	Private	Spanish	2.0	Urban	0	7.2	NonPQE_Other	0
2	129.0	89.0	78.0	20.0	36.3	93.0	3.2	5.5	15.9	258.0	134.9	4.77	0.94	157.0	0.009	111.0	1.69	1.17	0	0	1	0	1	0	0	2	4	3	0	0	46	4	0	0	61	female	7	0	0	0	0	14	0	0	1	0	1	4	46	1	0	0	576	0	0	194	349	0	0.89	White	Private	English	10.0	Rural	0	42.8	PQE02_ChronicACSC	1
3	130.0	81.0	89.0	14.0	36.8	99.0	0.7	7.4	11.7	276.0	142.3	4.18	0.74	96.0	0.025	64.0	0.99	0.99	1	0	0	0	0	0	1	2	3	2	0	1	5	7	0	0	59	female	8	2	0	0	0	11	1	0	0	0	0	7	5	1	1	0	828	0	2	291	331	0	0.77	White	Medicaid	English	12.2	Suburban	0	8.3	NonPQE_FollowUp	1
4	115.0	78.0	99.0	21.0	37.3	92.0	1.4	10.5	16.5	252.0	137.1	3.87	1.2	106.0	0.02	48.0	2.1	1.0	0	0	0	1	0	0	0	1	1	3	0	0	169	0	0	0	32	female	12	2	0	0	1	22	0	0	0	1	0	0	169	0	0	0	541	0	1	398	188	0	0.75	White	Private	English	17.2	Suburban	0	1.4	NonPQE_Other	0
5	218.0	87.0	106.0	45.0	34.5	75.0	4.5	10.4	15.0	158.0	137.2	4.64	1.08	102.0	0.04	72.0	0.97	1.05	0	1	1	0	0	0	0	2	1	5	0	0	217	0	0	1	67	female	11	6	1	0	1	5	0	1	1	0	0	0	217	0	0	5	170	0	2	64	3	0	0.62	White	Medicare	Spanish	10.9	Suburban	1	10.4	NonPQE_TrueEmergency	0
"""

df = pd.read_csv(io.StringIO(raw_data), sep=r'\s+', engine='python')

async def seed_data():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        print("[INFO] Seeding patient_ehr records and users into PostgreSQL ehr_db...")
        
        # 1. Seed Care Manager user account
        cm_password_hash = get_password_hash("admin123")
        cm_query = text("""
        INSERT INTO users (username, password_hash, role, patient_id)
        VALUES (:username, :password_hash, :role, NULL)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;
        """)
        await conn.execute(cm_query, {"username": "caremanager", "password_hash": cm_password_hash, "role": "CARE_MANAGER"})
        print("[OK] Care Manager user seeded: username='caremanager', password='admin123'")
        
        # 2. Seed 5 Patients and their User Accounts
        for idx in range(len(df)):
            row = df.iloc[idx]
            row_id = idx + 1
            mrn = f"MRN1000000{row_id}"
            pat_id = f"PAT_0000000{row_id}"
            name = f"Sample Patient {row_id}"
            username = f"patient{row_id}"
            raw_password = "patient123"
            password_hash = get_password_hash(raw_password)
            
            # Convert temp from C to F if < 50
            temp = float(row['temperature'])
            if temp < 50:
                temp = round((temp * 9/5) + 32, 1)
            
            insert_ehr_query = text("""
            INSERT INTO patient_ehr (
                mrn, patient_id, name, date_of_birth, age, gender, bmi, insurance_type, race,
                diabetes_flag, heart_failure_flag, cardiac_history_flag, copd_asthma_flag, ckd_flag,
                cancer_flag, dementia_flag, hypertension_flag, immunocompromised_flag, charlson_comorbidity_index,
                systolic_bp, diastolic_bp, heart_rate, respiratory_rate, temperature, spo2, pain_score_clinical,
                hemoglobin, creatinine, glucose, wbc_count, platelet_count, sodium, potassium, troponin, bnp, lactate, inr,
                active_medication_count, medication_count_at_discharge, polypharmacy_flag, high_risk_medication_flag,
                on_anticoagulants_flag, on_insulin_flag, medication_adherence_rate,
                previous_admissions_12m, previous_er_visits_12m, prior_30_day_readmission_flag,
                days_since_last_ed_visit, ed_visits_90d, ed_visits_30d, outpatient_visits_365d,
                days_since_last_pcp_visit, missed_appointments_6m, clinical_notes, is_active
            ) VALUES (
                :mrn, :patient_id, :name, :date_of_birth, :age, :gender, :bmi, :insurance_type, :race,
                :diabetes_flag, :heart_failure_flag, :cardiac_history_flag, :copd_asthma_flag, :ckd_flag,
                :cancer_flag, :dementia_flag, :hypertension_flag, :immunocompromised_flag, :charlson_comorbidity_index,
                :systolic_bp, :diastolic_bp, :heart_rate, :respiratory_rate, :temperature, :spo2, :pain_score_clinical,
                :hemoglobin, :creatinine, :glucose, :wbc_count, :platelet_count, :sodium, :potassium, :troponin, :bnp, :lactate, :inr,
                :active_medication_count, :medication_count_at_discharge, :polypharmacy_flag, :high_risk_medication_flag,
                :on_anticoagulants_flag, :on_insulin_flag, :medication_adherence_rate,
                :previous_admissions_12m, :previous_er_visits_12m, :prior_30_day_readmission_flag,
                :days_since_last_ed_visit, :ed_visits_90d, :ed_visits_30d, :outpatient_visits_365d,
                :days_since_last_pcp_visit, :missed_appointments_6m, :clinical_notes, 1
            )
            ON CONFLICT (mrn) DO UPDATE SET
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
                updated_at = CURRENT_TIMESTAMP;
            """)
            
            params = {
                "mrn": mrn,
                "patient_id": pat_id,
                "name": name,
                "date_of_birth": date(1965, 1, 1),
                "age": int(row['age']),
                "gender": str(row['gender']).lower(),
                "bmi": 25.0,
                "insurance_type": str(row['insurance_type']),
                "race": str(row['race']),
                "diabetes_flag": int(row['diabetes_flag']),
                "heart_failure_flag": 0,
                "cardiac_history_flag": int(row['cardiac_history_flag']),
                "copd_asthma_flag": int(row['copd_asthma_flag']),
                "ckd_flag": int(row['ckd_flag']),
                "cancer_flag": int(row['cancer_flag']),
                "dementia_flag": 0,
                "hypertension_flag": int(row['hypertension_flag']),
                "immunocompromised_flag": int(row['immunocompromised_flag']),
                "charlson_comorbidity_index": int(row['charlson_comorbidity_index']),
                "systolic_bp": int(row['systolic_bp']),
                "diastolic_bp": int(row['diastolic_bp']),
                "heart_rate": int(row['heart_rate']),
                "respiratory_rate": int(row['respiratory_rate']),
                "temperature": temp,
                "spo2": int(row['spo2']),
                "pain_score_clinical": float(row['pain_score_clinical']),
                "hemoglobin": float(row['hemoglobin']),
                "creatinine": float(row['creatinine']),
                "glucose": int(row['glucose']),
                "wbc_count": float(row['wbc']),
                "platelet_count": int(row['platelet_count']),
                "sodium": float(row['sodium']),
                "potassium": float(row['potassium']),
                "troponin": float(row['troponin']),
                "bnp": int(row['bnp']),
                "lactate": float(row['lactate']),
                "inr": float(row['inr']),
                "active_medication_count": int(row['active_medication_count']),
                "medication_count_at_discharge": int(row['active_medication_count']),
                "polypharmacy_flag": 1 if int(row['active_medication_count']) >= 5 else 0,
                "high_risk_medication_flag": 0,
                "on_anticoagulants_flag": 1 if int(row['on_anticoagulants_flag']) > 0 else 0,
                "on_insulin_flag": int(row['on_insulin_flag']),
                "medication_adherence_rate": float(row['medication_adherence_rate']),
                "previous_admissions_12m": int(row['admissions_past_year']),
                "previous_er_visits_12m": int(row['ed_visits_past_year']),
                "prior_30_day_readmission_flag": 0,
                "days_since_last_ed_visit": int(row['days_since_last_ed_visit']),
                "ed_visits_90d": int(row['ed_visits_90d']),
                "ed_visits_30d": int(row['ed_visits_30d']),
                "outpatient_visits_365d": int(row['outpatient_visits_365d']),
                "days_since_last_pcp_visit": int(row['days_since_last_pcp_visit']),
                "missed_appointments_6m": int(row['missed_appointments_6m']),
                "clinical_notes": f"Sample dataset record {row_id} with PQE category: {row['pqe_category']}, avoidable_ed target: {row['avoidable_ed']}",
            }
            
            await conn.execute(insert_ehr_query, params)
            print(f"[OK] Seeded patient EHR: {name} (MRN: {mrn}, Patient ID: {pat_id})")
            
            # Insert corresponding user account into users table
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
                "patient_id": pat_id
            })
            print(f"[OK] Seeded user account: username='{username}', password='{raw_password}', role='PATIENT', patient_id='{pat_id}'")

    await engine.dispose()
    print("\n[SUCCESS] All 5 sample patients and user credentials successfully populated!")

if __name__ == "__main__":
    asyncio.run(seed_data())
